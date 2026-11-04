"""The documented Meta file-transcription contract, tested without an API key or network."""
import io
import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from agent import fab3d, spend


def recording(rate=24000, seconds=1.25, channels=1):
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\0\0" * int(rate * seconds) * channels)
    return out.getvalue()


class VoiceProtocol(unittest.TestCase):
    def test_request_response_and_charge_use_the_voice_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "test.key"
            key.write_text("test-only")
            meter = spend.Meter({}, cap_usd=1)
            response = io.BytesIO(json.dumps({"transcript": "Where is polishing?", "audioDurationMs": 1250}).encode())
            with patch("urllib.request.urlopen", return_value=response) as send:
                text = fab3d.transcribe("https://api.meta.ai/v1", key, recording(), "audio/wav", meter=meter)
            req = send.call_args.args[0]
            self.assertEqual(req.full_url, "https://api.meta.ai/v1/asr/transcribe")
            self.assertIn(b'name="request"', req.data)
            self.assertIn(b'"audioEncoding": "WAV"', req.data)
            self.assertIn(b'name="audio"', req.data)
            self.assertEqual(text, "Where is polishing?")
            self.assertEqual(meter.calls, 1)
            self.assertAlmostEqual(meter.usd, 0.18 / 3600)

    def test_audio_cost_is_checked_before_a_request(self):
        meter = spend.Meter({}, cap_usd=0.00001)
        with patch("urllib.request.urlopen") as send:
            with self.assertRaises(spend.CapReached):
                fab3d.transcribe("https://api.meta.ai/v1", Path("no-key-needed"), recording(), "audio/wav", meter=meter)
        send.assert_not_called()

    def test_supported_wav_needs_no_conversion(self):
        data = recording()
        with patch("subprocess.run", side_effect=AssertionError("no converter needed")):
            wav, seconds = fab3d.prepare_audio(data)
        self.assertEqual(wav, data)
        self.assertEqual(seconds, 1.25)

    @unittest.skipUnless(shutil.which("ffmpeg"), "requires FFmpeg")
    def test_microphone_format_is_converted_to_supported_pcm(self):
        data, seconds = fab3d.prepare_audio(recording(rate=44100, channels=2))
        with wave.open(io.BytesIO(data), "rb") as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 24000))
        self.assertAlmostEqual(seconds, 1.25, places=3)

    def test_empty_recording_is_refused(self):
        with self.assertRaisesRegex(ValueError, "seconds"):
            fab3d.prepare_audio(recording(seconds=0))
