"""Tests for construction documents of one bay (docs/CONSTRUCTION-DOCS.md). Written before the code. A gigafab-style
layout of our own design on the SMT2020 model; not a real fab. Every sheet stays NOT FOR CONSTRUCTION.

    .venv/bin/python -m unittest viz.tests.test_cd      (from the repo root)

The data checks need nothing; the rest needs the cross aisle scene (docs/DESIGN-DEV.md, DD2) and IfcOpenShell in the
repo's .venv, and skips without them. The NFPA checks follow what has been read: met or not met once the NFPA sections
are in the register, cannot say before.
"""

import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCENE = ROOT / "data/layout-real-dd/scene-optimised.json"
LAYOUT = ROOT / "results/layout-real-dd/layout.json"
RUN = ROOT / "viz/permit/run.py"
PERMIT = ROOT / "viz/permit"
TRUTH = "On the SMT2020 model. A layout of our own design. Not a real fab."
VERDICTS = {"met", "not met", "cannot say"}
DD_SHEETS = ["G-001", "G-002", "G-003", "G-101", "G-102", "C-101", "C-201", "S-001", "S-101", "S-201", "A-401",
             "A-601", "M-101", "M-401", "M-601", "PP-101", "PP-301", "P-101", "FP-101", "FA-101", "E-001", "E-601",
             "A-201", "A-301", "A-402", "A-501", "A-602", "S-301", "S-601", "M-201", "M-602", "PP-201", "P-201", "FP-201",
             "FA-201", "E-101", "E-602"]
CD_SHEETS = ["A-110", "A-130", "A-610", "S-110", "S-510", "M-110", "PP-110", "E-110", "FP-110", "FA-110"]
ARCH_SHEETS = ["A-001", "A-100", "A-111", "A-112", "A-121", "A-122", "A-131", "A-132", "A-141", "A-142", "A-202", "A-311",
               "A-411", "A-412", "A-413", "A-414", "A-521", "A-531", "A-541", "A-551", "A-611", "A-612", "A-613", "A-614",
               "A-701", "A-702"]   # docs/ARCH-DOCS.md
SHEETS = DD_SHEETS + CD_SHEETS + ARCH_SHEETS
NFPA_RULES = {"NFPA 13": ("sprinklers.spacing", "sprinklers.branch_sizing"), "NFPA 72": ("alarm.detector_spacing",),
              "NFPA 70": ("elec.conductors",)}

sys.path.insert(0, str(PERMIT))
sys.path.insert(0, str(ROOT / "viz/blueprint"))

try:
    import ifcopenshell
    import ifcopenshell.util.element as uel
    import ifcopenshell.validate
    HAVE = True
except ImportError:
    HAVE = False


def run(args, check=True):
    p = subprocess.run([sys.executable, str(RUN), *map(str, args)], cwd=ROOT, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise AssertionError(p.stdout + p.stderr)
    return p


def load(p):
    return json.loads(Path(p).read_text())


def nfpa_read():
    """The NFPA documents read so far (the register exists once any is read)."""
    p = PERMIT / "codes/us-nfpa.json"
    if not p.exists():
        return set()
    return {s["code"].split(" 20")[0] for s in load(p)["sections"].values()}


class Data(unittest.TestCase):
    def test_site_register(self):
        R = load(PERMIT / "codes/us-site-willamette.json")
        self.assertEqual(R["region"], "Willamette Valley, Oregon")
        self.assertEqual((R["point"]["lat"], R["point"]["lon"]), (44.9, -123.0))
        s = R["seismic"]
        self.assertTrue(s["url"].startswith("https://earthquake.usgs.gov/ws/building-codes/asce7-22/calculate"))
        self.assertRegex(s["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(s["risk_category"], "IV")
        self.assertIn("assumed", s["site_class_basis"])
        v = s["values"]
        self.assertEqual(v["sdc"], "D")
        self.assertAlmostEqual(v["sds"], 0.8)
        self.assertAlmostEqual(v["sd1"], 0.54)
        for k in ("wind", "snow"):
            self.assertEqual(R[k]["basis"], "assumed")
            self.assertTrue(R[k]["why"])
            self.assertLessEqual(R[k]["lo"], R[k]["value"])
            self.assertLessEqual(R[k]["value"], R[k]["hi"])
        self.assertNotIn("TSMC", json.dumps(R))

    def test_profile_rules_items(self):
        cd = load(ROOT / "viz/blueprint/places/us.json")["permit"]["cd"]
        self.assertEqual(cd["bay"], 8)
        self.assertEqual(cd["site"], "viz/permit/codes/us-site-willamette.json")
        rules = load(ROOT / cd["rules"])
        ids = {r["id"] for r in rules}
        for want in ("site.seismic_values", "cd.base_plates", "cd.footing_mats", "cd.tiles", "cd.ffu_coverage",
                     "cd.drops", "cd.hangers", "cd.gas_lines", "cd.clearances", "sprinklers.spacing",
                     "sprinklers.branch_sizing", "alarm.detector_spacing", "elec.conductors"):
            self.assertIn(want, ids)
        base = {i["id"] for i in load(PERMIT / "items.json") + load(PERMIT / "items-dd.json")}
        items = load(ROOT / cd["items"])
        self.assertGreaterEqual(len(items), 15)
        for i in items:
            self.assertNotIn(i["id"], base)
            self.assertEqual(i["stage"], "CD")
            self.assertIn(i["sheet"], SHEETS + ["specs.md", "fab-permit.ifc"], i["id"])
        for s in CD_SHEETS:
            self.assertIn(s, {i["sheet"] for i in items}, s)


@unittest.skipUnless(SCENE.exists() and HAVE, "needs the cross aisle scene and IfcOpenShell (.venv)")
class ConstructionDocuments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "us"
        run(["--place", "us", "--stage", "cd", "--scene", SCENE, "--layout", LAYOUT, "--out", cls.out])
        cls.P = load(cls.out / "permit.json")
        cls.V = load(cls.out / "verdicts.json")
        cls.L = load(cls.out / "ledger.json")
        cls.S = load(SCENE)
        cls.f = ifcopenshell.open(str(cls.out / "fab-permit.ifc"))
        cls.D = cls.P["cd"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def verdicts(self, rule):
        got = [v for v in self.V if v["rule"] == rule]
        self.assertTrue(got, rule)
        return got

    def all_are(self, rule, want):
        for v in self.verdicts(rule):
            self.assertEqual(v["verdict"], want, (rule, v["scope"], v["why"]))

    def test_stage_bay_site(self):
        self.assertEqual(self.P["stage"], "cd")
        self.assertIn("SMT2020", self.P["truth"])
        b = self.D["bay"]
        self.assertEqual(b["index"], 8)
        self.assertEqual(self.S["bays"][8]["area"], "Litho")
        site = self.D["site"]
        self.assertAlmostEqual(site["seismic"]["sds"], 0.8)
        self.assertEqual(site["seismic"]["sdc"], "D")
        self.assertIn("USGS", site["seismic"]["basis"])
        self.all_are("site.seismic_values", "met")
        self.all_are("structure.seismic", "cannot say")
        for v in self.V:
            self.assertIn(v["verdict"], VERDICTS)

    def test_structure(self):
        St = self.D["structure"]
        self.assertTrue(St["columns"])
        for c in St["columns"]:
            self.assertGreaterEqual(c["anchors"], 4, c["id"])
            self.assertGreater(c["plate_mm"], 0, c["id"])
        for ft in St["footings"]:
            self.assertGreater(ft["bars"], 0, ft["id"])
            self.assertGreaterEqual(ft["as_provided_mm2"], ft["as_needed_mm2"], ft["id"])
        self.assertGreater(St["ribs"], 0)
        self.assertGreater(St["truss_members"], 0)
        self.assertEqual(St["truss_envelopes_left_over_bay"], 0)
        for rule in ("cd.base_plates", "cd.footing_mats"):
            self.all_are(rule, "met")

    def test_architecture(self):
        A = self.D["arch"]
        self.assertGreaterEqual(A["tile_coverage"], 0.99)
        self.assertLessEqual(A["tile_coverage"], 1.0 + 1e-9)
        self.assertGreater(A["perforated"], 0)
        for a in A["ffu"]:
            self.assertGreaterEqual(a["coverage"], a["target"] - 1e-9, a["array"])
        self.assertLessEqual(A["max_panel_width_m"], 1.2 + 1e-9)
        self.assertGreater(A["panels"], 0)
        for rule in ("cd.tiles", "cd.ffu_coverage"):
            self.all_are(rule, "met")

    def test_services(self):
        Sv = self.D["services"]
        bay = [i for i, t in enumerate(self.S["tools"]) if t["bay"] == 8]
        self.assertEqual(sorted(int(i) for i in Sv["tools"]), bay)
        for i in bay:
            card = load(PERMIT / "tool-cards" / f"{self.S['tools'][i]['kind']}.json")
            need = {u for u, v in card["utilities"].items() if v["value"] > 0}
            got = Sv["tools"][str(i)]
            self.assertEqual(set(got["drops"]), need - {"power_kva"}, i)
            self.assertEqual(set(got["valves"]), {u for u in need if u != "power_kva" and not u.startswith("exhaust")}, i)
            self.assertEqual(got["feeder"], "power_kva" in need, i)
            haz = {c["material"] for c in card["chemistry"] if c["hazard"].endswith("gas")}
            self.assertEqual(set(got["gas_lines"]), haz, i)
        self.assertLessEqual(Sv["max_hanger_spacing_m"], 2.4 + 1e-9)
        self.assertGreater(Sv["hangers"], 0)
        self.assertEqual(self.D["clearances"]["violations"], [])
        for rule in ("cd.drops", "cd.hangers", "cd.gas_lines", "cd.clearances"):
            self.all_are(rule, "met")

    def test_nfpa_rules(self):
        read = nfpa_read()
        for doc, rules in NFPA_RULES.items():
            for rule in rules:
                if doc in read:
                    for v in self.verdicts(rule):
                        if rule == "sprinklers.branch_sizing" and v["verdict"] == "cannot say":
                            # a system this size needs the site's water supply to be sized (19.2.2.3, 19.2.3)
                            self.assertIn("water supply", v["why"])
                            continue
                        self.assertIn(v["verdict"], ("met", "not met"), (rule, v["why"]))
                else:
                    self.all_are(rule, "cannot say")
        F = self.D["fire"]
        if "NFPA 13" in read:
            self.assertLessEqual(F["max_spacing_ft"], 15 + 1e-6)
            self.assertLessEqual(F["max_area_per_head_sqft"], 130 + 1e-6)
            self.assertLessEqual(F["max_wall_distance_ft"], 7.5 + 1e-6)
            self.assertGreaterEqual(F["min_between_ft"], 6 - 1e-6)
            self.assertGreater(F["chase_heads"], 0)
        if "NFPA 72" in read:
            self.assertLessEqual(F["max_port_spacing_ft"], 30 + 1e-6)
            self.assertLessEqual(F["max_port_wall_ft"], 15 + 1e-6)
            self.assertGreater(F["chase_ports"], 0)
        if "NFPA 70" in read:
            for i, fd in self.D["services"]["feeders"].items():
                self.assertGreaterEqual(fd["ampacity_A"], fd["amps_125pct"] - 1e-6, i)

    def test_lod_and_ifc(self):
        self.assertEqual(self.P["clashes"], [])
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(self.f, logger)
        errors = [s for s in logger.statements if s.get("level", "").lower() == "error"]
        self.assertEqual(errors, [])
        n400 = 0
        for e in self.f.by_type("IfcProduct"):
            ps = uel.get_psets(e)
            if "FabGym_Permit" in ps:
                self.assertIn(ps["FabGym_Permit"]["LOD"], (100, 200, 300, 350, 400), e.Name)
                if ps["FabGym_Permit"]["Stage"] == "CD":
                    self.assertEqual(ps["FabGym_Permit"]["LOD"], 400, e.Name)
                    n400 += 1
        self.assertGreater(n400, 3000)
        for cls in ("IfcPlate", "IfcMechanicalFastener", "IfcReinforcingBar", "IfcMember", "IfcValve", "IfcCovering",
                    "IfcAirTerminal", "IfcPipeSegment", "IfcCableCarrierSegment"):
            self.assertGreater(len(self.f.by_type(cls)), 0, cls)

    def test_same_every_run(self):
        other = self.tmp / "again"
        run(["--place", "us", "--stage", "cd", "--scene", SCENE, "--layout", LAYOUT, "--out", other, "--no-pdf"])
        for name in ("fab-permit.ifc", "permit.json", "verdicts.json", "ledger.json", "specs.md"):
            self.assertEqual((self.out / name).read_bytes(), (other / name).read_bytes(), name)

    def test_sheets_specs_ledger(self):
        idx = load(self.out / "index.json")
        self.assertEqual([s["id"] for s in idx], SHEETS)
        for s in idx:
            svg = (self.out / "sheets" / f"{s['id']}.svg").read_text()
            self.assertIn(TRUTH, svg, s["id"])
            self.assertIn("NOT FOR CONSTRUCTION", svg, s["id"])
            self.assertIn('viewBox="0 0 1066.8 762"', svg, s["id"])
        self.assertIn("construction documents", (self.out / "sheets/G-001.svg").read_text().lower())
        md = (self.out / "specs.md").read_text()
        for part in ("Part 1 General", "Part 2 Products", "Part 3 Execution"):
            self.assertIn(part, md)
        self.assertIn("NOT FOR CONSTRUCTION", md)
        items = load(PERMIT / "items.json") + load(PERMIT / "items-dd.json") + load(PERMIT / "items-cd.json")
        self.assertEqual([i["id"] for i in self.L["items"]], [i["id"] for i in items])
        self.assertEqual(self.L["counts"].get("missing", 0), 0,
                         [i["id"] for i in self.L["items"] if i["status"] == "missing"])
        for i in self.L["items"]:
            if i["licensed_review"]:
                self.assertEqual(i["status"], "licensed review", i["id"])
        for p in self.out.rglob("*"):
            if p.suffix in (".svg", ".json", ".md", ".ifc", ".html"):
                self.assertNotIn("TSMC", p.read_text(), p.name)

    def test_pdf(self):
        if not Path("/Applications/Google Chrome.app").exists():
            self.skipTest("needs Google Chrome for the PDF")
        pdf = (self.out / "permit-set.pdf").read_bytes()
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page[^s]", pdf)), len(SHEETS))


if __name__ == "__main__":
    unittest.main()
