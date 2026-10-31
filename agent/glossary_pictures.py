"""The glossary's pictures and newcomer lines (docs/GLOSSARY-PLUS.md, part 1).

Pictures: Muse Image draws each term that the cast has no picture for, in the cast's style, with the cast's hero picture
and two cast members as references. Made once and kept in web/glossary/; a term whose picture is on disk is skipped, so
none is bought twice. Newcomer lines: Muse Spark drafts one plain line a term from the glossary's own text; a person
signs them off before they go into web/glossary.js. Both count on the glossary meter (data/ask/spend-glossary.json).

    python -m agent.glossary_pictures pictures      # makes the missing pictures
    python -m agent.glossary_pictures plain OUT     # drafts newcomer lines into OUT (JSON) for review

On a teaching fab of our own and the SMT2020 testbed; not a real fab."""

import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from agent import spend

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
PICTURES = WEB / "glossary" / "pictures.json"
MODEL = "muse-image-1.0"
PRICE_USD = 0.01  # a generated image, Meta's price sheet (docs/BASETEN-PRICING.md)
TEXT_MODEL = "muse-spark-1.3-contributor"
CAP_USD = 5.0
MAX_WORDS = 20


def glossary_meter(data_dir):
    """The glossary's own meter, shared with the helper's (agent/helper.py)."""
    return spend.Meter(spend.price("meta", TEXT_MODEL), cap_usd=CAP_USD, path=Path(data_dir) / "spend-glossary.json")


def terms():
    """The glossary's terms, read from web/glossary.js with Node."""
    out = subprocess.run(["node", "-e", "process.stdout.write(JSON.stringify(require(process.argv[1]).TERMS))", str(WEB / "glossary.js")],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _scrub(text, key):
    return str(text).replace(key, "[secret]") if key else str(text)


def shrink(data, path, width=384):
    """Save a picture as WebP at most `width` px wide and under 60 KB."""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.webp"
        src.write_bytes(data)
        for q in (80, 70, 60, 50):
            subprocess.run(["cwebp", "-quiet", "-q", str(q), "-resize", str(width), "0", str(src), "-o", str(path)], check=True)
            if path.stat().st_size <= 60 * 1024:
                return
    raise RuntimeError(f"{path.name} stays over 60 KB")


def make_pictures(jobs, web_dir, meter, call, key=None, save=shrink, log_path=None):
    """Make each job's picture unless it is on disk. jobs: {term: {"prompt", "file"}}; call(prompt) gives the bytes.
    Stops before a picture would pass the meter's cap. Returns {"made", "skipped", "failed", "stopped"}."""
    web_dir = Path(web_dir)
    made, skipped, failed, stopped = [], [], [], ""
    log = []
    for term, job in jobs.items():
        path = web_dir / job["file"]
        if path.is_file():
            skipped.append(term)
            continue
        if meter.usd + PRICE_USD > meter.cap_usd + 1e-9:
            stopped = f"Glossary pictures have used their ${meter.cap_usd:g} budget. Raise its cap to make more."
            break
        t0 = time.time()
        try:
            data = call(job["prompt"])
        except Exception as e:  # noqa: BLE001 - written to the log without the key
            msg = _scrub(e.read()[:300].decode("utf-8", "replace") if hasattr(e, "read") else e, key)[:300]
            failed.append({"term": term, "error": msg})
            log.append({"term": term, "error": msg})
            continue
        meter.add_usd(PRICE_USD)
        path.parent.mkdir(parents=True, exist_ok=True)
        save(data, path)
        made.append(term)
        log.append({"term": term, "file": job["file"], "seconds": round(time.time() - t0, 1)})
    if log_path:
        Path(log_path).write_text(_scrub(json.dumps(log, indent=1), key))
    return {"made": made, "skipped": skipped, "failed": failed, "stopped": stopped}


def muse_image(base_url, key, references, timeout=240):
    """call(prompt) for make_pictures: Muse Image's edit with the reference pictures attached."""
    images = [{"image_url": "data:image/" + ("jpeg" if p.suffix == ".jpg" else "webp") + ";base64," + base64.b64encode(p.read_bytes()).decode()}
              for p in references]

    def call(prompt):
        body = json.dumps({"model": MODEL, "prompt": prompt, "images": images, "n": 1}).encode()
        req = urllib.request.Request(base_url.rstrip("/") + "/images/edits", data=body, method="POST",
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return base64.b64decode(json.loads(r.read())["data"][0]["b64_json"])
    return call


PLAIN_PROMPT = """Below are entries from a glossary of a chip factory simulator. For each term, write ONE plain sentence a \
newcomer with no factory or statistics background can use: at most 20 words, everyday words, no jargon, no formulas, \
no numbers unless they help, ending with a full stop. Say what the thing is or does; do not start with the term's name. \
Answer with a JSON object only, mapping each term exactly as given to its sentence.

{entries}"""


def draft_plain(entries, complete):
    """One newcomer line a term, drafted in one request from the glossary's own text (meaning, here, example).
    A line that is missing, too long or not a sentence comes back as None for a person to write."""
    text = "\n\n".join(f"Term: {t['term']}\nMeaning: {t['meaning']}\nIn this fab: {t['here']}\nExample: {t['example']}" for t in entries)
    raw = complete([{"role": "user", "content": PLAIN_PROMPT.format(entries=text)}])
    raw = raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw else "{}"
    try:
        got = json.loads(raw)
    except ValueError:
        got = {}
    out = {}
    for t in entries:
        line = " ".join(str(got.get(t["term"]) or "").split())
        ok = line and len(line.split()) <= MAX_WORDS and line.endswith(".")
        out[t["term"]] = line if ok else None
    return out


def plain_model(data_dir, key_file=None):
    """Muse Spark on the glossary meter."""
    from agent.fabgym_agent import HttpModel
    from agent.helper import PRESETS
    p = PRESETS["meta"]
    return HttpModel(p["base_url"], TEXT_MODEL, key_file=key_file or p["key_file"].expanduser(), max_tokens=8000,
                     reasoning_effort="low", meter=glossary_meter(data_dir), timeout=240)


def main(argv):
    from agent.helper import PRESETS
    data_dir = ROOT / "data" / "ask"
    if argv[:1] == ["pictures"]:
        spec = json.loads(PICTURES.read_text())
        p = PRESETS["meta"]
        key = p["key_file"].expanduser().read_text().strip()
        meter = glossary_meter(data_dir)
        # a term may name its own reference pictures; jobs run in groups that share them
        groups = {}
        for t, e in spec["terms"].items():
            if "prompt" in e:
                groups.setdefault(tuple(e.get("references") or spec["references"]), {})[t] = e
        for refs, jobs in groups.items():
            call = muse_image(p["base_url"], key, [ROOT / r for r in refs])
            r = make_pictures(jobs, WEB, meter, call, key=key, log_path=data_dir / "glossary-pictures-log.json")
            print(json.dumps({k: (v if k != "skipped" else len(v)) for k, v in r.items()}, indent=1))
        return 0
    if argv[:1] == ["plain"] and len(argv) == 2:
        entries = terms()
        lines = {}
        m = plain_model(data_dir)
        for i in range(0, len(entries), 24):  # three requests for the whole glossary
            lines.update(draft_plain(entries[i:i + 24], m.complete))
        Path(argv[1]).write_text(json.dumps(lines, indent=1, ensure_ascii=False))
        print(f"{sum(v is not None for v in lines.values())} of {len(lines)} lines drafted; spent ${m.meter.usd:.4f} on the glossary meter")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
