"""Tests for the permit-set workflow (docs/PERMIT.md). Written before the code. A gigafab-style layout of our own
design from the SMT2020 testbed; not a real fab. Every sheet stays NOT FOR CONSTRUCTION.

    .venv/bin/python -m unittest viz.tests.test_permit      (from the repo root)

The rule engine's hand cases need nothing; the rest needs the scene file (viz/prep.py --real) and IfcOpenShell in
the repo's .venv, and skips without them. D10's check reads the committed rescore in results/layout-real-permit.
"""

import hashlib
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
SCENE = ROOT / "data/layout-real/scene-optimised.json"
LAYOUT = ROOT / "results/layout-real/layout.json"
RUN = ROOT / "viz/permit/run.py"
PERMIT = ROOT / "viz/permit"
RESCORE = ROOT / "results/layout-real-permit/rescore.json"
FT = 0.3048
TRUTH = "From the SMT2020 testbed. A layout of our own design. Not a real fab."
STATUSES = {"missing", "drawn", "checked", "assumed", "open", "licensed review"}
VERDICTS = {"met", "not met", "cannot say"}
SHEETS = ["G-001", "G-002", "G-003", "G-101", "G-102", "C-101", "C-201", "S-001", "S-101", "S-201", "A-401",
          "A-601", "M-101", "M-401", "M-601", "PP-101", "PP-301", "P-101", "FP-101", "FA-101", "E-001", "E-601"]
DIVISIONS = ["03", "05", "07", "08", "09", "13", "21", "22", "23", "26", "28"]

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


def q(v, lo=None, hi=None, basis="model"):
    return {"value": v, "lo": v if lo is None else lo, "hi": v if hi is None else hi, "basis": basis}


class Engine(unittest.TestCase):
    """The rule engine on hand cases: met, not met, cannot say."""

    REG = {"sections": {"X 1": {"facts": {"lim": 200}}}, "not_read": [{"id": "Y"}]}
    RULE = {"id": "t.travel", "topic": "exits and egress", "cite": ["X 1"], "binds": "building", "input": "d",
            "op": "le", "limit": {"section": "X 1", "fact": "lim"}, "fix": "add an exit"}

    def ev(self, inputs, **change):
        import rules
        return rules.evaluate({**self.RULE, **change}, inputs, self.REG)

    def test_met_and_not_met(self):
        self.assertEqual(self.ev({"d": q(150)})["verdict"], "met")
        self.assertEqual(self.ev({"d": q(250)})["verdict"], "not met")
        self.assertEqual(self.ev({"d": q(200)})["limit"], 200)
        self.assertEqual(self.ev({"d": q(250)}, op="ge")["verdict"], "met")

    def test_assumed_input_that_could_flip(self):
        self.assertEqual(self.ev({"d": q(190, 170, 230, "assumed")})["verdict"], "cannot say")
        self.assertEqual(self.ev({"d": q(190, 170, 195, "assumed")})["verdict"], "met")
        # a computed input carries no range of doubt
        self.assertEqual(self.ev({"d": q(190, 190, 190, "computed:x")})["verdict"], "met")

    def test_missing_input_or_law_not_read(self):
        self.assertEqual(self.ev({})["verdict"], "cannot say")
        r = self.ev({"d": q(150)}, rests_on=["Y"])
        self.assertEqual(r["verdict"], "cannot say")
        self.assertIn("not read", r["why"])

    def test_true_test(self):
        self.assertEqual(self.ev({"d": q(True)}, op="true", limit=None)["verdict"], "met")
        self.assertEqual(self.ev({"d": q(False)}, op="true", limit=None)["verdict"], "not met")

    def test_cites_only_what_was_read(self):
        with self.assertRaises(ValueError):
            self.ev({"d": q(150)}, cite=["Z 9"])


class Data(unittest.TestCase):
    """D1 and D2 and D0's list: the register, the profile, the cards, the items, the rules."""

    @classmethod
    def setUpClass(cls):
        cls.reg = json.loads((PERMIT / "codes/us-2024.json").read_text())
        cls.us = json.loads((ROOT / "viz/blueprint/places/us.json").read_text())
        cls.rules = json.loads((PERMIT / "rules/us.json").read_text())
        cls.items = json.loads((PERMIT / "items.json").read_text())

    def test_register(self):
        secs = self.reg["sections"]
        self.assertGreaterEqual(len(secs), 40)
        for k, s in secs.items():
            self.assertRegex(s["sha256"], r"^[0-9a-f]{64}$", k)
            self.assertEqual(s["opened"], "2026-10-27", k)
            self.assertTrue(s["url"].startswith("https://codes.iccsafe.org/content/I"), k)
            self.assertIn(s["code"], ("IBC 2024", "IFC 2024"), k)
            self.assertGreater(s["chars"], 0, k)
            self.assertIn("facts", s)
        ids = " ".join(n["id"] for n in self.reg["not_read"])
        for want in ("ASCE 7", "NFPA 13", "NFPA 72", "ISO 14644-1", "ICC A117.1"):
            self.assertIn(want, ids)
        self.assertIn("hypothetical", self.reg["jurisdiction"])

    def test_profile_v2(self):
        p = self.us["permit"]
        self.assertIn("hypothetical", p["jurisdiction"])
        self.assertEqual(p["register"], "viz/permit/codes/us-2024.json")
        for k, v in p["design_data"].items():
            self.assertLessEqual(v["lo"], v["value"], k)
            self.assertLessEqual(v["value"], v["hi"], k)
            self.assertEqual(v["basis"], "assumed", k)
        self.assertEqual(len(p["site"]["lot"]), 4)
        self.assertNotIn("permit", json.loads((ROOT / "viz/blueprint/places/intl.json").read_text()))

    @unittest.skipUnless(SCENE.exists(), "needs the scene file")
    def test_cards(self):
        S = json.loads(SCENE.read_text())
        for kind in S["kinds"]:
            card = json.loads((PERMIT / "tool-cards" / f"{kind}.json").read_text())
            self.assertEqual(card["kind"], kind)
            n = 0
            for path, v in _quantities(card):
                n += 1
                self.assertLessEqual(v["lo"], v["value"], f"{kind} {path}")
                self.assertLessEqual(v["value"], v["hi"], f"{kind} {path}")
                b = v["basis"]
                self.assertTrue(b == "assumed" or (b.startswith("cited:") and b[6:] in self.reg["sections"]),
                                f"{kind} {path} {b}")
            self.assertGreaterEqual(n, 12, kind)
            for c in card["chemistry"]:
                self.assertIn(c["where"], ("in tool", "gas room", "dispense room"))
                self.assertIn(c["hazard"], ("flammable gas", "pyrophoric gas", "toxic gas", "highly toxic gas",
                                            "oxidizing gas", "corrosive liquid", "flammable liquid IB",
                                            "oxidizer liquid class 2", "corrosive gas"))

    def test_rules_cite_the_register(self):
        nr = {n["id"] for n in self.reg["not_read"]}
        topics = set()
        for r in self.rules:
            topics.add(r["topic"])
            self.assertTrue(r["cite"], r["id"])
            for c in r["cite"]:
                self.assertIn(c, self.reg["sections"], r["id"])
            for x in r.get("rests_on", []):
                self.assertIn(x, nr, r["id"])
            self.assertIn(r["binds"], ("site", "building", "story", "fab area", "room", "bay", "element"))
        for t in ("occupancy", "construction type", "fab areas", "exits and egress", "service corridors",
                  "HPM and gas rooms", "ventilation", "gas detection", "alarms", "emergency power", "sprinklers",
                  "structure", "cleanroom air", "accessibility"):
            self.assertIn(t, topics)
        self.assertEqual(len({r["id"] for r in self.rules}), len(self.rules))

    def test_items(self):
        ids = [i["id"] for i in self.items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 60)
        for i in self.items:
            self.assertIn(i["discipline"], ("G", "C", "S", "A", "M", "PP", "P", "FP", "FA", "E", "spec"), i["id"])
            self.assertIn(i["stage"], ("D3", "D4", "D5", "D6", "D7", "D8", "D9"), i["id"])
            self.assertIn(i["sheet"], SHEETS + ["specs.md", "fab-permit.ifc"], i["id"])
            self.assertIsInstance(i["licensed_review"], bool)


def _quantities(d, path=""):
    if isinstance(d, dict):
        if set(d) >= {"value", "lo", "hi", "basis"}:
            yield path, d
            return
        for k, v in d.items():
            yield from _quantities(v, f"{path}/{k}")
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from _quantities(v, f"{path}/{i}")


@unittest.skipUnless(SCENE.exists() and HAVE, "needs the scene file and IfcOpenShell (.venv)")
class Concept(unittest.TestCase):
    """D3 on the concept model, before any pass adds exits: the exit rules fail."""

    def test_concept_fails_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            run(["--place", "us", "--scene", SCENE, "--layout", LAYOUT, "--out", tmp, "--stage", "concept"])
            V = json.loads((Path(tmp) / "verdicts.json").read_text())
            got = {(v["rule"], v["scope"]): v["verdict"] for v in V}
            self.assertEqual(got[("egress.exit_count", "P1 clean floor")], "not met")
            self.assertEqual(got[("egress.travel", "P1 clean floor")], "not met")
            self.assertTrue(all(v["verdict"] in VERDICTS for v in V))

    def test_intl_has_no_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = run(["--place", "intl", "--scene", SCENE, "--layout", LAYOUT, "--out", tmp], check=False)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("no codes read", p.stdout + p.stderr)


@unittest.skipUnless(SCENE.exists() and HAVE, "needs the scene file and IfcOpenShell (.venv)")
class PermitSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "us"
        run(["--place", "us", "--scene", SCENE, "--layout", LAYOUT, "--out", cls.out])
        cls.P = json.loads((cls.out / "permit.json").read_text())
        cls.V = json.loads((cls.out / "verdicts.json").read_text())
        cls.L = json.loads((cls.out / "ledger.json").read_text())
        cls.reg = json.loads((PERMIT / "codes/us-2024.json").read_text())
        cls.S = json.loads(SCENE.read_text())
        cls.f = ifcopenshell.open(str(cls.out / "fab-permit.ifc"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def fact(self, sec, k):
        return self.reg["sections"][sec]["facts"][k]

    def verdict(self, rule, scope):
        got = [v for v in self.V if v["rule"] == rule and v["scope"] == scope]
        self.assertEqual(len(got), 1, (rule, scope))
        return got[0]

    # ---- D0
    def test_ledger(self):
        items = json.loads((PERMIT / "items.json").read_text())
        self.assertEqual([i["id"] for i in self.L["items"]], [i["id"] for i in items])
        for i in self.L["items"]:
            self.assertIn(i["status"], STATUSES, i["id"])
            self.assertTrue(i["why"], i["id"])
        self.assertEqual(self.L["counts"].get("missing", 0), 0, [i["id"] for i in self.L["items"] if i["status"] == "missing"])
        for i in self.L["items"]:
            if i["licensed_review"]:
                self.assertEqual(i["status"], "licensed review", i["id"])

    # ---- D3
    def test_every_rule_has_a_verdict(self):
        rules = json.loads((PERMIT / "rules/us.json").read_text())
        seen = {v["rule"] for v in self.V}
        self.assertEqual(seen, {r["id"] for r in rules})
        for v in self.V:
            self.assertIn(v["verdict"], VERDICTS)
            self.assertTrue(v["why"])
            if v["verdict"] == "not met":
                self.assertTrue(v["fix"], v["rule"])

    def test_occupancy_and_construction(self):
        self.assertEqual(self.verdict("occupancy.h5", "P1")["verdict"], "met")
        c = self.P["construction"]
        self.assertIn(c["type"], ("IA", "IB"))
        for b in ("P1", "P2"):
            for rule in ("construction.height", "construction.stories", "construction.area"):
                self.assertEqual(self.verdict(rule, b)["verdict"], "met", (rule, b))
        self.assertEqual(self.verdict("structure.seismic", "P1")["verdict"], "cannot say")

    # ---- D4
    def test_nothing_in_the_fab_moved(self):
        import model
        M = model.build(self.S)
        boxes = [e["box"] for e in M["elements"] if e["cls"] == "IfcBuildingElementProxy" and e["box"]]
        rails = [e["rail"] for e in M["elements"] if e["rail"]]
        want = hashlib.sha256(json.dumps([boxes, rails]).encode()).hexdigest()
        self.assertEqual(self.P["fab_digest"], want)

    def test_egress(self):
        limit = self.fact("IBC T1017.2", "H5_sprinklered_ft") * FT
        for b in ("P1", "P2"):
            for story in ("clean floor", "support floor"):
                e = self.P["egress"][b][story]
                self.assertLessEqual(e["max_travel_m"], limit + 1e-6, (b, story))
                need = 2 if e["occupant_load"] <= 500 else 3 if e["occupant_load"] <= 1000 else 4
                self.assertGreaterEqual(e["exits"], need, (b, story))
                self.assertGreaterEqual(e["max_separation_m"], e["diagonal_m"] / 3, (b, story))
                self.assertLessEqual(e["common_path_m"], self.fact("IBC T1006.2.1", "H5_common_path_ft") * FT + 1e-6)
                for rule in ("egress.travel", "egress.exit_count", "egress.separation", "egress.common_path"):
                    self.assertEqual(self.verdict(rule, f"{b} {story}")["verdict"], "met", (rule, b, story))
            c = self.P["egress"][b]["clean floor"]
            self.assertGreaterEqual(c["stair_width_in"], 0.3 * c["occupant_load"] - 1e-6)
            self.assertEqual(self.verdict("egress.stair_capacity", f"{b} clean floor")["verdict"], "met")
        for x in self.P["exits"]:
            self.assertGreaterEqual(x["width_m"], 44 * 0.0254, x["id"])

    def test_rooms_and_lot(self):
        lot = 30 * FT
        kinds = {r["kind"] for r in self.P["rooms"]}
        self.assertTrue({"gas room", "chemical dispense", "gowning", "emergency control"} <= kinds, kinds)
        for r in self.P["rooms"]:
            if r["kind"] in ("gas room", "chemical dispense"):
                self.assertTrue(r["exterior_wall"], r["id"])
                self.assertGreaterEqual(r["lot_distance_m"], lot, r["id"])
                want = 2 if r["area_sqft"] >= (300 if r["kind"] == "gas room" else 150) else 1
                self.assertGreaterEqual(r["rating_h"], want, r["id"])
                self.assertEqual(self.verdict("hpm.room_location", r["id"])["verdict"], "met")
            if r["kind"] == "emergency control":
                self.assertFalse(r["in_fab_area"])

    def test_fab_areas(self):
        for a in self.P["fab_areas"]:
            self.assertLessEqual(a["gas_cf"], a["gas_limit_cf"] + 1e-6, a["id"])
            self.assertLessEqual(a["flammable_liquid_gal"], a["flammable_liquid_limit_gal"] + 1e-6, a["id"])
            self.assertGreaterEqual(a["barrier_h"], 1, a["id"])
        self.assertEqual({a["building"] for a in self.P["fab_areas"]}, {"P1", "P2"})

    # ---- D5
    def test_frame(self):
        F = self.P["frame"]
        loads = sum(x["load_kN"] for x in F["footings"])
        self.assertAlmostEqual(loads, F["total_load_kN"], delta=F["total_load_kN"] * 1e-3)
        cols = {c["id"] for c in F["columns"]}
        self.assertEqual(cols, {x["column"] for x in F["footings"]})
        self.assertEqual(F["live_load_psf"]["clean floor"], self.fact("IBC T1607.1", "manufacturing_heavy_psf"))
        self.assertGreater(len(F["bays"]), 30)
        for b in F["bays"]:
            self.assertGreater(b["f1_hz"], 0)

    # ---- D6
    def test_every_tool_connected(self):
        U = self.P["utilities"]
        self.assertEqual(len(U["connections"]), len(self.S["tools"]))
        for i, t in enumerate(self.S["tools"]):
            card = json.loads((PERMIT / "tool-cards" / f"{t['kind']}.json").read_text())
            need = {u for u, v in card["utilities"].items() if v["value"] > 0}
            self.assertTrue(need <= set(U["connections"][str(i)]), (i, need))
        for u, d in U["demand"].items():
            self.assertGreaterEqual(U["plant"][u]["capacity"], d["diversified"], u)
        for s in U["segments"]:
            self.assertLessEqual(s["velocity"], s["limit"] + 1e-9, s["id"])
        for k in ("HPM exhaust ventilation", "gas cabinet ventilation", "gas detection", "emergency alarm",
                  "fire alarm", "sprinkler monitoring"):
            self.assertTrue(any(k in x for x in U["emergency_loads"]), k)

    # ---- D7
    def test_air_and_fire(self):
        A, F = self.P["air"], self.P["fire"]
        for b in A["bays"]:
            self.assertGreaterEqual(b["coverage"], b["target"] - 1e-9, b["bay"])
        self.assertGreaterEqual(A["chiller_kw"], A["cooling_kw"])
        self.assertGreaterEqual(A["recirc_cfm_sqft_avg"], 4)
        self.assertGreaterEqual(A["recirc_cfm_sqft_min"], 3)
        for bay, n in F["hpm_gas_tools_by_bay"].items():
            self.assertGreaterEqual(F["gas_sensors_by_bay"].get(bay, 0), n, bay)
        for rid, g in F["gas_rooms"].items():
            self.assertGreaterEqual(g["sensors"], 1, rid)
            self.assertGreaterEqual(g["alarms"], 1, rid)
        self.assertEqual(set(F["covered_fab_areas"]), {a["id"] for a in self.P["fab_areas"]})
        self.assertEqual(self.verdict("sprinklers.density", "P1")["verdict"], "cannot say")

    # ---- D8
    def test_no_hard_clashes(self):
        self.assertEqual(self.P["clashes"], [])
        self.assertGreater(self.P["elements_added"], 500)

    def test_ifc(self):
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(self.f, logger)
        errors = [s for s in logger.statements if s.get("level", "").lower() == "error"]
        self.assertEqual(errors, [])
        new = 0
        for e in self.f.by_type("IfcProduct"):
            ps = uel.get_psets(e)
            if "FabGym_Permit" in ps:
                new += 1
                self.assertIn(ps["FabGym_Permit"]["LOD"], (100, 200, 300, 350), e.Name)
                self.assertIn("NOT FOR CONSTRUCTION", ps["FabGym_Basis"]["Status"])
        self.assertEqual(new, self.P["elements_added"])
        for cls in ("IfcDoor", "IfcStair", "IfcBeam", "IfcFooting", "IfcPipeSegment", "IfcDuctSegment",
                    "IfcCableCarrierSegment", "IfcChiller", "IfcTransformer", "IfcElectricGenerator",
                    "IfcAirTerminal", "IfcFireSuppressionTerminal", "IfcSensor", "IfcAlarm"):
            self.assertGreater(len(self.f.by_type(cls)), 0, cls)

    def test_same_every_run(self):
        other = self.tmp / "again"
        run(["--place", "us", "--scene", SCENE, "--layout", LAYOUT, "--out", other, "--no-pdf"])
        for name in ("fab-permit.ifc", "permit.json", "verdicts.json", "ledger.json", "specs.md"):
            self.assertEqual((self.out / name).read_bytes(), (other / name).read_bytes(), name)

    # ---- D9
    def test_sheets(self):
        idx = json.loads((self.out / "index.json").read_text())
        self.assertEqual([s["id"] for s in idx], SHEETS)
        rules = json.loads((PERMIT / "rules/us.json").read_text())
        for s in idx:
            svg = (self.out / "sheets" / f"{s['id']}.svg").read_text()
            self.assertIn(TRUTH, svg, s["id"])
            self.assertIn("NOT FOR CONSTRUCTION", svg, s["id"])
            self.assertIn('viewBox="0 0 1066.8 762"', svg, s["id"])
        g2 = (self.out / "sheets/G-002.svg").read_text()
        for r in rules:
            self.assertIn(r["id"], g2)
        g3 = (self.out / "sheets/G-003.svg").read_text()
        for i in self.L["items"]:
            self.assertIn(i["id"], g3)
        for i in self.L["items"]:
            if i["sheet"].endswith(".svg") or re.match(r"^[A-Z]+-\d{3}$", i["sheet"]):
                self.assertIn(i["sheet"], SHEETS)

    def test_specs(self):
        md = (self.out / "specs.md").read_text()
        for d in DIVISIONS:
            self.assertRegex(md, rf"(?m)^## Division {d} ")
        self.assertIn("NOT FOR CONSTRUCTION", md)
        self.assertIn(TRUTH, md)

    def test_clean_text(self):
        for p in self.out.rglob("*"):
            if p.suffix in (".svg", ".json", ".md", ".ifc", ".html"):
                t = p.read_text()
                self.assertNotIn("TSMC", t, p.name)
                self.assertTrue(t.isascii() or p.suffix in (".svg", ".html", ".md"), p.name)

    def test_pdf(self):
        if not Path("/Applications/Google Chrome.app").exists():
            self.skipTest("needs Google Chrome for the PDF")
        pdf = (self.out / "permit-set.pdf").read_bytes()
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page[^s]", pdf)), len(SHEETS))


class Rescore(unittest.TestCase):
    """D10: the wider chase as a constraint for the optimiser, rescored on paired seeds."""

    def test_rescore(self):
        R = json.loads(RESCORE.read_text())
        self.assertIn("SMT2020 testbed", R["truth"])
        self.assertEqual(R["chase_before_m"], 1.5)
        self.assertGreaterEqual(R["chase_after_m"], 5 * FT)
        L = json.loads((ROOT / "results/layout-real-permit/layout.json").read_text())
        self.assertAlmostEqual(L["assumed"]["chase"], R["chase_after_m"])
        self.assertGreater(R["hoist_m_per_day"]["after"], 0)
        self.assertGreaterEqual(R["seeds"], 5)
        for m in R["measures"]:
            self.assertLessEqual(m["lo"], m["diff"])
            self.assertLessEqual(m["diff"], m["hi"])


if __name__ == "__main__":
    unittest.main()
