"""Tests for the blueprint, the campus as a drawing set for an architect (docs/BLUEPRINT.md). Written before
the code. A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab. Standard library only:

    python3 -m unittest viz.tests.test_blueprint      (from the repo root)

Needs the scene file (data/layout-real/scene-optimised.json, from `viz/prep.py --real`) and skips without it.
The PDF test runs only when Google Chrome is installed.
"""

import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCENE = ROOT / "data/layout-real/scene-optimised.json"
LAYOUT = ROOT / "results/layout-real/layout.json"
SCRIPT = ROOT / "viz/blueprint/blueprint.py"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SHEETS = ["A-000", "A-100", "A-101", "A-102", "A-110", "A-301", "A-500", "A-900"]
SCALES = {"A-100": 2000, "A-101": 500, "A-102": 500, "A-110": 100, "A-301": 200, "A-500": 750}
US_SCALES = {"A-100": ('1" = 200\'-0"', 2400), "A-101": ('1/32" = 1\'-0"', 384), "A-102": ('1/32" = 1\'-0"', 384),
             "A-110": ('1/8" = 1\'-0"', 96), "A-301": ('1/16" = 1\'-0"', 192), "A-500": ('1/64" = 1\'-0"', 768)}
PLACES = ROOT / "viz/blueprint/places"
CODE_TOPICS = ["seismic design", "fire and hazardous-materials occupancy", "exits and egress", "hazardous gas storage",
               "cleanroom classification and air", "accessibility"]
LAYERS = ["A-GRID", "A-WALL", "A-SPINE", "A-BAY", "A-EQPM", "A-STKR", "A-OHT", "A-ANNO", "A-SITE"]


def build(out, pdf=False, place=None):
    args = [sys.executable, str(SCRIPT), "--scene", str(SCENE), "--layout", str(LAYOUT), "--out", str(out)]
    if place:
        args += ["--place", place]
    if not pdf:
        args.append("--no-pdf")
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(p.stdout + p.stderr)
    return p.stdout


def ftin(m):
    """A length in metres as feet and inches, to the nearest inch."""
    inches = round(m / 0.0254)
    return f"{inches // 12}'-{inches % 12}\""


def phase_of(scene, t):
    return 1 if t["x0"] >= scene["offsets"][1] - 1e-6 else 0


def dxf_pairs(text):
    lines = text.splitlines()
    return [(lines[i].strip(), lines[i + 1].rstrip("\r")) for i in range(0, len(lines) - 1, 2)]


@unittest.skipUnless(SCENE.exists(), "needs data/layout-real/scene-optimised.json (viz/prep.py --real)")
class Blueprint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "a"
        build(cls.out)
        cls.scene = json.loads(SCENE.read_text())
        cls.svg = {s: (cls.out / "sheets" / f"{s}.svg").read_text() for s in SHEETS}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_files(self):
        for s in SHEETS:
            self.assertTrue((self.out / "sheets" / f"{s}.svg").exists(), s)
        for f in ["fab-blueprint.html", "fab-plan.dxf", "brief.md", "fab-model.ifc"]:
            self.assertTrue((self.out / f).exists(), f)
        html = (self.out / "fab-blueprint.html").read_text()
        self.assertEqual([m for m in re.findall(r'data-sheet="([A-Z]-\d+)"', html)], SHEETS)
        self.assertIn("841mm 594mm", html.replace(" ", " "))

    def test_title_blocks(self):
        sha = hashlib.sha256(LAYOUT.read_bytes()).hexdigest()[:12]
        for s, svg in self.svg.items():
            self.assertTrue(svg.startswith("<svg"), s)
            self.assertIn('viewBox="0 0 841 594"', svg, s)
            for w in ["Fab Gym campus", s, "27 Oct 2026", "P1 for review", "From the SMT2020 testbed.",
                      "A layout of our own design.", "Not a real fab.", "NOT FOR CONSTRUCTION", sha]:
                self.assertIn(w, svg, f"{s} lacks {w!r}")
            if s in SCALES:
                self.assertIn(f"1:{SCALES[s]}", svg, s)
            self.assertNotIn("TSMC", svg, s)

    def test_plans_draw_everything_once(self):
        tools = self.scene["tools"]
        bays = self.scene["bays"]
        offs = self.scene["offsets"]

        def phase_of(t):
            return 1 if t["x0"] >= offs[1] - 1e-6 else 0

        want = [sum(1 for t in tools if phase_of(t) == p) for p in (0, 1)]
        got = [len(re.findall(r'data-tool="\d+"', self.svg[s])) for s in ("A-101", "A-102")]
        self.assertEqual(got, want)
        self.assertEqual(sum(got), 1043)
        ids = sorted(int(i) for s in ("A-101", "A-102") for i in re.findall(r'data-tool="(\d+)"', self.svg[s]))
        self.assertEqual(ids, list(range(len(tools))))
        nb = sum(len(re.findall(r'data-bay="\d+"', self.svg[s])) for s in ("A-101", "A-102"))
        self.assertEqual(nb, len(bays))
        self.assertEqual(len(bays), 39)
        ns = sum(len(re.findall(r'data-stocker="\d+"', self.svg[s])) for s in ("A-101", "A-102"))
        self.assertEqual(ns, 5)
        for s in ("A-101", "A-102", "A-100"):
            self.assertIn('data-north="1"', self.svg[s], s)

    def test_scale_bars(self):
        for s, scale in SCALES.items():
            m = re.search(r'<g data-scalebar="(\d+(?:\.\d+)?)" data-mm="(\d+(?:\.\d+)?)"', self.svg[s])
            self.assertIsNotNone(m, f"{s} has no scale bar")
            metres, mm = float(m.group(1)), float(m.group(2))
            self.assertAlmostEqual(mm, metres * 1000.0 / scale, places=3, msg=s)

    def test_section_levels(self):
        svg = self.svg["A-301"]
        for f in self.scene["floors"]:
            self.assertIn(f["name"], svg.lower())
            for z in (f["z0"], f["z1"]):
                self.assertIn(f"+{z:.2f}", svg)
        self.assertIn(f"+{self.scene['rail_z']:.2f}", svg)
        self.assertEqual(f"{self.scene['rail_z']:.2f}", "11.70")

    def test_dxf(self):
        text = (self.out / "fab-plan.dxf").read_text()
        pairs = dxf_pairs(text)
        self.assertEqual(pairs[-1], ("0", "EOF"))
        i = pairs.index(("9", "$INSUNITS"))
        self.assertEqual(pairs[i + 1], ("70", "6"))
        layers = {v for (c, v), prev in zip(pairs[1:], pairs) if c == "2" and prev == ("0", "LAYER")}
        for layer in LAYERS:
            self.assertIn(layer, layers)
        # entities: closed polylines with their layer
        ents, cur = [], None
        for c, v in pairs:
            if c == "0":
                if cur:
                    ents.append(cur)
                cur = {"type": v, "layer": None, "flag": 0, "xs": [], "ys": []}
            elif cur is not None:
                if c == "8" and cur["layer"] is None:
                    cur["layer"] = v
                elif c == "70" and cur["type"] == "POLYLINE":
                    cur["flag"] = int(v)
                elif c == "10":
                    cur["xs"].append(float(v))
                elif c == "20":
                    cur["ys"].append(float(v))
        eq = [e for e in ents if e["type"] == "POLYLINE" and e["layer"] == "A-EQPM"]
        self.assertEqual(len(eq), 1043)
        self.assertTrue(all(e["flag"] & 1 for e in eq))
        g = self.scene["ground"]
        for e in ents:
            for x in e["xs"]:
                self.assertTrue(g["x0"] - 1 <= x <= g["x1"] + 1, e)
            for y in e["ys"]:
                self.assertTrue(g["y0"] - 1 <= y <= g["y1"] + 1, e)

    def test_brief(self):
        brief = (self.out / "brief.md").read_text()
        layout = json.loads(LAYOUT.read_text())
        for k in ["bay_depth", "bay_aisle", "chase", "spine", "bridge"]:
            self.assertIn(k.replace("_", " "), brief.lower(), k)
        for f in self.scene["floors"]:
            self.assertIn(f["name"], brief.lower())
        for kind in layout["assumed"]["kinds"]:
            self.assertIn(kind.replace("_", " "), brief.lower(), kind)
        self.assertIn("cited", brief.lower())
        self.assertIn("assumed", brief.lower())
        q = brief.split("## Questions for the architect", 1)
        self.assertEqual(len(q), 2, "no questions section")
        self.assertGreaterEqual(len(re.findall(r"^\d+\. ", q[1], flags=re.M)), 8)
        self.assertIn("Not a real fab", brief)
        self.assertNotIn("TSMC", brief)
        for w in ["NOT FOR CONSTRUCTION"]:
            self.assertIn(w, self.svg["A-900"])

    def test_same_every_run(self):
        b = self.tmp / "b"
        build(b)
        for rel in [f"sheets/{s}.svg" for s in SHEETS] + ["fab-plan.dxf", "brief.md", "fab-blueprint.html", "fab-model.ifc"]:
            self.assertEqual((self.out / rel).read_bytes(), (b / rel).read_bytes(), rel)

    @unittest.skipUnless(CHROME.exists(), "needs Google Chrome")
    def test_pdf(self):
        c = self.tmp / "c"
        build(c, pdf=True)
        b = (c / "fab-blueprint.pdf").read_bytes()
        self.assertTrue(b.startswith(b"%PDF"))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page[^s]", b)), 8)
        boxes = re.findall(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", b)
        self.assertEqual(len(boxes), 8)
        for w, h in boxes:
            self.assertAlmostEqual(float(w) / 72 * 25.4, 841, delta=0.5)
            self.assertAlmostEqual(float(h) / 72 * 25.4, 594, delta=0.5)

    def test_codes_not_checked(self):
        prof = json.loads((PLACES / "intl.json").read_text())
        self.assertEqual([c["topic"] for c in prof["codes"]], CODE_TOPICS)
        self.assertTrue(all(c["status"] == "not checked" for c in prof["codes"]))
        brief = (self.out / "brief.md").read_text()
        part = brief.split("## Building codes", 1)
        self.assertEqual(len(part), 2, "no building codes section")
        for t in CODE_TOPICS:
            self.assertIn(t, self.svg["A-000"])
            self.assertIn(t, part[1])
        self.assertIn("not checked", self.svg["A-000"])
        self.assertIn("not checked", part[1])

    def test_axonometric(self):
        svg = self.svg["A-500"]
        want = sum(1 for t in self.scene["tools"] if phase_of(self.scene, t) == 0)
        ids = [int(i) for i in re.findall(r'data-axo-tool="(\d+)"', svg)]
        self.assertEqual(len(ids), want)
        self.assertEqual(len(set(ids)), want)
        self.assertEqual(sorted(set(re.findall(r'data-axo-layer="([a-z-]+)"', svg))),
                         sorted(["support-floor", "waffle-slab", "clean-floor", "filter-ceiling", "roof"]))
        for w in ["Support floor", "Waffle slab", "Clean floor", "Filter ceiling", "Roof"]:
            self.assertIn(w, svg)


@unittest.skipUnless(SCENE.exists(), "needs data/layout-real/scene-optimised.json (viz/prep.py --real)")
class BlueprintUS(unittest.TestCase):
    """The same model drawn on the US profile: feet and inches, ARCH E1, US architectural scales."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "us"
        build(cls.out, place="us")
        cls.scene = json.loads(SCENE.read_text())
        cls.svg = {s: html.unescape((cls.out / "sheets" / f"{s}.svg").read_text()) for s in SHEETS}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_paper_and_scales(self):
        for s, svg in self.svg.items():
            self.assertIn('viewBox="0 0 1066.8 762"', svg, s)
            self.assertIn("ARCH E1", svg, s)
            self.assertIn("Not a real fab.", svg, s)
            self.assertIn("NOT FOR CONSTRUCTION", svg, s)
            if s in US_SCALES:
                label, ratio = US_SCALES[s]
                self.assertIn(label, svg, s)
                m = re.search(r'<g data-scalebar="(\d+(?:\.\d+)?)" data-mm="(\d+(?:\.\d+)?)"', svg)
                self.assertIsNotNone(m, f"{s} has no scale bar")
                self.assertAlmostEqual(float(m.group(2)), float(m.group(1)) * 1000.0 / ratio, places=3, msg=s)

    def test_plans_draw_everything_once(self):
        tools = self.scene["tools"]
        ids = sorted(int(i) for s in ("A-101", "A-102") for i in re.findall(r'data-tool="(\d+)"', self.svg[s]))
        self.assertEqual(ids, list(range(len(tools))))

    def test_feet_and_inches(self):
        svg = self.svg["A-301"]
        for f in self.scene["floors"]:
            for z in (f["z0"], f["z1"]):
                self.assertIn(f"EL. +{ftin(z)}", svg)
        self.assertIn(f"EL. +{ftin(self.scene['rail_z'])}", svg)
        self.assertIn(ftin(self.scene["depth"]), self.svg["A-101"])
        brief = (self.out / "brief.md").read_text()
        self.assertIn(ftin(self.scene["depth"]), brief)
        self.assertIn("## Building codes", brief)
        for t in CODE_TOPICS:
            self.assertIn(t, brief)

    def test_dxf_in_inches(self):
        pairs = dxf_pairs((self.out / "fab-plan.dxf").read_text())
        i = pairs.index(("9", "$INSUNITS"))
        self.assertEqual(pairs[i + 1], ("70", "1"))
        k = 1 / 0.0254
        g = self.scene["ground"]
        n_eq, cur = 0, None
        for (c, v), prev in zip(pairs[1:], pairs):
            if prev == ("0", "POLYLINE"):
                cur = "POLYLINE"
            if cur == "POLYLINE" and c == "8":
                n_eq += v == "A-EQPM"
                cur = None
            if c == "10":
                self.assertTrue(g["x0"] * k - 40 <= float(v) <= g["x1"] * k + 40, v)
            if c == "20":
                self.assertTrue(g["y0"] * k - 40 <= float(v) <= g["y1"] * k + 40, v)
        self.assertEqual(n_eq, 1043)

    def test_same_ifc_for_every_place(self):
        a = self.tmp / "intl"
        build(a)
        self.assertEqual((a / "fab-model.ifc").read_bytes(), (self.out / "fab-model.ifc").read_bytes())

    @unittest.skipUnless(CHROME.exists(), "needs Google Chrome")
    def test_pdf(self):
        c = self.tmp / "uspdf"
        build(c, pdf=True, place="us")
        b = (c / "fab-blueprint.pdf").read_bytes()
        boxes = re.findall(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", b)
        self.assertEqual(len(boxes), 8)
        for w, h in boxes:
            self.assertAlmostEqual(float(w) / 72, 42, delta=0.05)
            self.assertAlmostEqual(float(h) / 72, 30, delta=0.05)


if __name__ == "__main__":
    unittest.main()
