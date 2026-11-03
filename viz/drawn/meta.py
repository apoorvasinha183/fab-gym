"""Meta's models for the drawn film, through one metered client (docs/DRAWN-FILM.md, D9). Every call is written to a
ledger with its cost; a call that would pass the cap is refused before it is sent; a repeated request (same model,
inputs and prompt) is answered from the cache at $0. The key is read from ~/.config/fab-gym/meta.key and never printed.

Prices from Meta's rate sheet (docs/BASETEN-PRICING.md): Muse Image $0.01 a picture; SAM 3.1 $2.50 per 1,000
images; muse-spark-1.3-contributor $0.10 per million tokens in and $0.20 out. Muse Voice Transcribe is not on the
sheet read: counted at an assumed $0.05 a call against the cap until its price is known."""

import base64
import hashlib
import json
import time
import urllib.request
from pathlib import Path

BASE = "https://api.meta.ai/v1"
KEY = Path.home() / ".config/fab-gym/meta.key"
IMAGE = "muse-image-1.0"
SPARK = "muse-spark-1.3-contributor"
SAM = "sam-3.1"
VOICE = "muse-voice-transcribe-1.0"
PRICE = {IMAGE: 0.01, SAM: 0.0025, VOICE: 0.05}       # dollars a call (VOICE assumed)
SPARK_IN, SPARK_OUT = 0.10 / 1e6, 0.20 / 1e6           # dollars a token


class OverCap(Exception):
    pass


def _http(path, body, key_file=KEY, base=BASE, timeout=240):
    key = Path(key_file).read_text().strip()
    req = urllib.request.Request(base.rstrip("/") + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class Client:
    def __init__(self, ledger, cache, cap_usd, transport=None):
        self.ledger = Path(ledger)
        self.cache = Path(cache)
        self.cap = float(cap_usd)
        self.transport = transport or _http
        self.cache.mkdir(parents=True, exist_ok=True)
        self.ledger.parent.mkdir(parents=True, exist_ok=True)

    def spent(self):
        if not self.ledger.exists():
            return 0.0
        return sum(json.loads(x)["usd"] for x in self.ledger.read_text().splitlines() if x.strip())

    def _log(self, model, usd, what, cached):
        with open(self.ledger, "a") as f:
            f.write(json.dumps({"t": round(time.time(), 1), "model": model, "usd": round(usd, 6),
                                "cached": cached, "what": what[:120]}) + "\n")

    def _call(self, model, path, body, price, what, parse):
        key = hashlib.sha256(json.dumps([model, path, body], sort_keys=True).encode()).hexdigest()
        hit = self.cache / key
        if hit.exists():
            self._log(model, 0.0, what, True)
            return parse(json.loads(hit.read_text()))
        if self.spent() + price > self.cap + 1e-9:
            raise OverCap(f"{what[:60]!r} would take the spend to ${self.spent() + price:.2f}, over the ${self.cap:.2f} cap")
        out = self.transport(path, body)
        hit.write_text(json.dumps(out))
        usd = price
        if model == SPARK and isinstance(out, dict) and "usage" in out:
            u = out["usage"]
            usd = u.get("prompt_tokens", 0) * SPARK_IN + u.get("completion_tokens", 0) * SPARK_OUT
        self._log(model, usd, what, False)
        return parse(out)

    def image(self, prompt, refs=(), size=None):
        """A picture from Muse Image: generated, or edited from reference pictures (PNG or JPEG bytes)."""
        body = {"model": IMAGE, "prompt": prompt, "n": 1}
        if size:
            body["size"] = size
        if refs:
            body["images"] = [{"image_url": _data_url(r)} for r in refs]
        path = "/images/edits" if refs else "/images/generations"
        return self._call(IMAGE, path, body, PRICE[IMAGE], prompt, lambda o: base64.b64decode(o["data"][0]["b64_json"]))

    def chat(self, messages, what, effort="low", max_tokens=4000):
        """Muse Spark's answer as text; a message may hold pictures as image_url parts."""
        body = {"model": SPARK, "messages": messages, "reasoning_effort": effort, "max_tokens": max_tokens}
        return self._call(SPARK, "/chat/completions", body, 0.01, what,
                          lambda o: o["choices"][0]["message"]["content"])


def _multipart(path, fields, file_field, filename, mime, data, key_file=KEY, base=BASE, timeout=240):
    import uuid
    key = Path(key_file).read_text().strip()
    bd = uuid.uuid4().hex
    parts = [f'--{bd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields]
    parts += [f'--{bd}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
              f'Content-Type: {mime}\r\n\r\n'.encode(), data, f"\r\n--{bd}--\r\n".encode()]
    req = urllib.request.Request(base.rstrip("/") + path, data=b"".join(parts), method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": f"multipart/form-data; boundary={bd}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def transcribe(client, audio, mime="audio/mpeg"):
    """The soundtrack's words with their times, from Muse Voice Transcribe (word times when the service gives them,
    else its segments). Metered and cached like every other call."""
    digest = hashlib.sha256(audio).hexdigest()
    fields = [("model", VOICE), ("response_format", "verbose_json"), ("timestamp_granularities[]", "word"),
              ("timestamp_granularities[]", "segment")]
    t = client.transport if client.transport is not _http else (
        lambda path, body: _multipart(path, fields, "file", "soundtrack.mp3", mime, audio))
    saved = client.transport
    client.transport = t
    try:
        return client._call(VOICE, "/audio/transcriptions", {"model": VOICE, "audio_sha256": digest, "words": True},
                            PRICE[VOICE], f"transcribe {digest[:12]}", lambda o: o)
    finally:
        client.transport = saved


def _data_url(b):
    mime = "image/jpeg" if b[:2] == b"\xff\xd8" else ("image/webp" if b[8:12] == b"WEBP" else "image/png")
    return f"data:{mime};base64," + base64.b64encode(b).decode()
