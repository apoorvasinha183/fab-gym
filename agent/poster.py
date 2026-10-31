"""The three-star poster (docs/POSTER.md): Muse Image redraws the player's map as a poster with the challenge's name, the
wafers a day and the stars. The words on it are built here from the run's numbers; the page cannot add other text.
On a teaching fab of our own; not a real fab."""

import base64
import json
import re
import urllib.request

MODEL = "muse-image-1.0"
PRICE_USD = 0.01  # a generated image, Meta's price sheet (docs/BASETEN-PRICING.md)
MAX_BYTES = 8 * 1024 * 1024
PNG_URL = "data:image/png;base64,"
WORDS = {0: "no", 1: "one", 2: "two", 3: "three"}


def clean_title(t):
    """A challenge's name for the poster: one line, at most 60 characters."""
    return " ".join(str(t or "").split())[:60]


def check(body):
    """{} when the request can make a poster, else {"error": why}."""
    img = body.get("image")
    if not isinstance(img, str) or not img.startswith(PNG_URL):
        return {"error": "the map's picture must be a PNG data URL"}
    if (len(img) - len(PNG_URL)) * 3 // 4 > MAX_BYTES:
        return {"error": "the map's picture is over 8 MB"}
    w, s = body.get("wafers"), body.get("stars")
    if not isinstance(w, int) or isinstance(w, bool) or w < 0:
        return {"error": "wafers must be a whole number"}
    if not isinstance(s, int) or isinstance(s, bool) or not 0 <= s <= 3:
        return {"error": "stars must be 0 to 3"}
    return {}


def prompt(title, wafers, stars):
    return (f"Redraw this picture of a small chip factory's floor plan, seen from above on grid paper, as a bright, friendly "
            f"cartoon poster in flat colours. Keep every machine tile and every piece of track where it is. At the top, a "
            f"banner reading \"{clean_title(title)}\". At the bottom, \"{wafers} wafers a day\" and {WORDS[stars]} gold "
            f"star{'s' if stars != 1 else ''}. No other words and no logos.")


def kind(data):
    """The picture's real format from its first bytes: (mime type, file extension). Muse Image answers WebP by default."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg", "jpg"
    return "image/png", "png"


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", clean_title(t).lower()).strip("-") or "fab"


def edit(base_url, key, image_url, text, timeout=180):
    """Muse Image's edit: the poster's PNG bytes."""
    body = json.dumps({"model": MODEL, "prompt": text, "images": [{"image_url": image_url}], "n": 1}).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/images/edits", data=body, method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return base64.b64decode(out["data"][0]["b64_json"])
