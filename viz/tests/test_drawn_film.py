"""The hand-drawn silicon film's engine (docs/DRAWN-FILM.md, D1 to D12). Written before the code. Small made-up
drawings stand in for the real ones; no Meta call is made (the client is given a stand-in transport). From the
SMT2020 testbed for the fab's part; the rest is general knowledge.

    python3 -m unittest viz.tests.test_drawn_film      (from the repo root; needs numpy and Pillow)
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    np = None

W, H = 320, 180


def drawings():
    """A plate, a six-drawing glow cycle and two character poses, as RGBA images."""
    d = {}
    # a painted plate that shades across the frame, so a jump of the camera changes most of its pixels
    yy, xx = np.mgrid[0:H + 40, 0:W + 80]
    rgba = np.stack([60 + xx * 0.45, 40 + yy * 0.6, 120 + 0 * xx, 255 + 0 * xx], axis=-1).clip(0, 255).astype("uint8")
    d["plate"] = Image.fromarray(rgba, "RGBA")
    for k in range(6):
        g = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        for x in range(40):
            for y in range(40):
                if (x - 20) ** 2 + (y - 20) ** 2 < (10 + k) ** 2:
                    g.putpixel((x, y), (255, 150 + 15 * k, 60, 255))
        d[f"glow_{k + 1}"] = g
    for name, colour in (("G_a", (251, 241, 230, 255)), ("G_b", (163, 166, 173, 255))):
        c = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
        for x in range(4, 26):
            for y in range(4, 26):
                c.putpixel((x, y), colour)
        d[name] = c
    return d


def sheet(**over):
    s = {"shot": "t-1", "frames": 24, "fps": 24, "palette": "test",
         "levels": [{"name": "plate", "depth": 1.0, "cels": [["plate", 24]], "at": [-40, -20]},
                    {"name": "glow", "depth": 0.8, "cycle": [f"glow_{k}" for k in range(1, 7)], "on": 2, "at": [140, 70]},
                    {"name": "grain", "depth": 0.5, "cels": [["G_a", 12], ["G_b", 12]], "at": [60, 100]}],
         "camera": [[0, {"x": 0, "y": 0, "zoom": 1.0}], [24, {"x": 40, "y": 0, "zoom": 1.0}]],
         "cuts": [], "captions": []}
    s.update(over)
    return s


@unittest.skipIf(np is None, "numpy and Pillow are needed")
class Engine(unittest.TestCase):
    def setUp(self):
        from viz.drawn import compose, sheet as sh
        self.compose, self.sh = compose, sh
        self.d = drawings()

    def test_d1_every_frame_resolves_to_a_drawing(self):
        s = self.sh.load(sheet())
        self.assertEqual(self.sh.validate(s, set(self.d)), [])
        bad = self.sh.load(sheet(levels=sheet()["levels"] + [{"name": "x", "depth": 0.3, "cels": [["nope", 24]]}]))
        errors = self.sh.validate(bad, set(self.d))
        self.assertTrue(errors and any("nope" in e for e in errors), errors)
        short = self.sh.load(sheet(levels=[{"name": "plate", "depth": 1.0, "cels": [["plate", 10]]}]))
        self.assertTrue(self.sh.validate(short, set(self.d)), "a level shorter than the shot leaves frames without a drawing")

    def test_d2_a_held_drawing_is_rendered_once(self):
        r = self.compose.Renderer(self.d, (W, H))
        frames = list(r.frames(self.sh.load(sheet())))
        self.assertEqual(len(frames), 24)
        self.assertEqual(r.rendered, 1 + 6 + 2, "each unique drawing prepared once")

    def test_d3_a_cycle_on_twos_changes_every_second_frame(self):
        s = self.sh.load(sheet())
        seq = [s.at(f)["glow"] for f in range(24)]
        for f in range(0, 24, 2):
            self.assertEqual(seq[f], seq[f + 1])
        self.assertEqual(seq[0], "glow_1")
        self.assertEqual(seq[2], "glow_2")
        self.assertEqual(seq[12], "glow_1", "the cycle repeats")

    def test_d4_nearer_levels_slide_further(self):
        cam = {"x": 40, "y": 0, "zoom": 1.0}
        far = self.compose.offset(1.0, cam)
        near = self.compose.offset(0.5, cam)
        nearest = self.compose.offset(0.0, cam)
        self.assertLess(abs(far[0]), abs(near[0]))
        self.assertLess(abs(near[0]), abs(nearest[0]))

    def test_d5_no_pop_except_at_a_marked_cut(self):
        r = self.compose.Renderer(self.d, (W, H))
        frames = list(r.frames(self.sh.load(sheet())))
        self.assertEqual(self.compose.pops(frames, cuts=[]), [])
        jumpy = sheet(camera=[[0, {"x": 0, "y": 0, "zoom": 1.0}], [11, {"x": 0, "y": 0, "zoom": 1.0}],
                              [12, {"x": 80, "y": 30, "zoom": 1.5}], [24, {"x": 80, "y": 30, "zoom": 1.5}]])
        frames = list(self.compose.Renderer(self.d, (W, H)).frames(self.sh.load(jumpy)))
        self.assertEqual(self.compose.pops(frames, cuts=[]), [12])
        self.assertEqual(self.compose.pops(frames, cuts=[12]), [])

    def test_d6_the_same_sheet_renders_the_same_frames(self):
        def digest():
            h = hashlib.sha256()
            for f in self.compose.Renderer(self.d, (W, H)).frames(self.sh.load(sheet())):
                h.update(np.ascontiguousarray(f).tobytes())
            return h.hexdigest()
        self.assertEqual(digest(), digest())

    @unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg is needed")
    def test_d7_only_the_video_is_written(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            out = tmp / "shot.mp4"
            self.compose.encode(self.compose.Renderer(self.d, (W, H)), self.sh.load(sheet()), out)
            self.assertTrue(out.exists() and out.stat().st_size > 0)
            self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["shot.mp4"])
        finally:
            shutil.rmtree(tmp)


@unittest.skipIf(np is None, "numpy and Pillow are needed")
class Ink(unittest.TestCase):
    def test_d8_colour_lock_keeps_every_painted_pixel_on_the_palette(self):
        from viz.drawn import ink
        palette = [(28, 22, 38), (251, 241, 230), (230, 207, 186), (224, 80, 63)]
        img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        for x in range(40):
            for y in range(40):
                img.putpixel((x, y), (min(255, 240 + x % 7), 236 - y % 5, 222 + (x + y) % 9, 255) if x < 30 else (0, 0, 0, 0))
        out = ink.colour_lock(img, palette)
        self.assertLessEqual(ink.palette_distance(out, palette), 1.0)
        a = np.asarray(out)[..., 3]
        self.assertTrue((a[:, 30:] == 0).all(), "transparent stays transparent")


class Meta(unittest.TestCase):
    def test_d9_the_spend_cap_the_ledger_and_the_cache(self):
        from viz.drawn import meta
        tmp = Path(tempfile.mkdtemp())
        calls = []

        def transport(path, body):
            calls.append((path, body))
            return {"data": [{"b64_json": "aGVsbG8="}]}

        try:
            c = meta.Client(ledger=tmp / "ledger.jsonl", cache=tmp / "cache", cap_usd=0.025, transport=transport)
            a = c.image("Grain, model sheet, front view")
            b = c.image("Grain, model sheet, front view")
            self.assertEqual(a, b)
            self.assertEqual(len(calls), 1, "a repeat is answered from the cache")
            c.image("Grain, gasping")
            with self.assertRaises(meta.OverCap):
                c.image("Grain, grey and alone")
            lines = [json.loads(x) for x in (tmp / "ledger.jsonl").read_text().splitlines()]
            self.assertEqual([round(x["usd"], 3) for x in lines], [0.01, 0.0, 0.01])
            self.assertEqual({x["model"] for x in lines}, {"muse-image-1.0"})
            self.assertAlmostEqual(c.spent(), 0.02)
        finally:
            shutil.rmtree(tmp)


class Words(unittest.TestCase):
    def test_d10_captions_follow_the_word_times(self):
        from viz.drawn import captions
        words = [{"word": "Heat", "start": 0.40, "end": 0.62}, {"word": "it", "start": 0.62, "end": 0.71},
                 {"word": "with", "start": 0.71, "end": 0.90}, {"word": "carbon,", "start": 0.90, "end": 1.40},
                 {"word": "hotter", "start": 1.70, "end": 2.00}, {"word": "than", "start": 2.00, "end": 2.15},
                 {"word": "lava.", "start": 2.15, "end": 2.70}]
        cues = captions.cues(["Heat it with carbon,", "hotter than lava."], words)
        self.assertEqual(len(cues), 2)
        self.assertLessEqual(abs(cues[0]["from"] - 0.40), 1 / 24)
        self.assertLessEqual(abs(cues[1]["from"] - 1.70), 1 / 24)
        self.assertLessEqual(abs(cues[1]["to"] - 2.70), 1 / 24)

    def test_d11_every_caption_is_the_scripts_own_words(self):
        from viz.drawn import captions
        script = (ROOT / "docs/CHIP-FILM.md").read_text()
        self.assertEqual(captions.not_in_script(["Heat it with carbon, hotter than lava, and the carbon steals the oxygen."], script), [])
        self.assertEqual(captions.not_in_script(["Silicon is made of cheese."], script), ["Silicon is made of cheese."])

    def test_d12_the_end_card_names_the_models_and_the_music(self):
        from viz.drawn import endcard
        text = endcard.credits()
        for name in ("Muse Image", "SAM 3.1", "Muse Spark", "Muse Voice Transcribe", "The Budding of Consciousness",
                     "Yoiyami", "New Sunrise", "nene", "CC0", "SMT2020"):
            self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
