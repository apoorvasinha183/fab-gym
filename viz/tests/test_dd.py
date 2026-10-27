"""Tests for design development (docs/DESIGN-DEV.md). Written before the code. A gigafab-style layout of our own design
on the SMT2020 model; not a real fab. Every sheet stays NOT FOR CONSTRUCTION.

    .venv/bin/python -m unittest viz.tests.test_dd      (from the repo root)

The data checks need nothing; the rest needs the scene of the layout with 1.6 m chases and cross aisles (DD2) and
IfcOpenShell in the repo's .venv, and skips without them. DD2's rescore is read from results/layout-real-dd.
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
RESCORE = ROOT / "results/layout-real-dd/rescore.json"
RUN = ROOT / "viz/permit/run.py"
PERMIT = ROOT / "viz/permit"
FT = 0.3048
TRUTH = "On the SMT2020 model. A layout of our own design. Not a real fab."
VERDICTS = {"met", "not met", "cannot say"}
STATUSES = {"missing", "drawn", "checked", "assumed", "open", "licensed review"}
SCHEMATIC = ["G-001", "G-002", "G-003", "G-101", "G-102", "C-101", "C-201", "S-001", "S-101", "S-201", "A-401",
             "A-601", "M-101", "M-401", "M-601", "PP-101", "PP-301", "P-101", "FP-101", "FA-101", "E-001", "E-601"]
NEW = ["A-201", "A-301", "A-402", "A-501", "A-602", "S-301", "S-601", "M-201", "M-602", "PP-201", "P-201", "FP-201",
       "FA-201", "E-101", "E-602"]
SHEETS = SCHEMATIC + NEW
DIVISIONS = ["03", "05", "07", "08", "09", "10", "13", "14", "21", "22", "23", "26", "28"]
CODES = ("IBC 2024", "IFC 2024", "IPC 2024", "IMC 2024")

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


class Data(unittest.TestCase):
    """DD1 and the stage's data: the second register, the rules, the items, the profile."""

    @classmethod
    def setUpClass(cls):
        cls.base = load(PERMIT / "codes/us-2024.json")
        cls.reg = load(PERMIT / "codes/us-2024-dd.json")
        cls.us = load(ROOT / "viz/blueprint/places/us.json")
        cls.rules = load(PERMIT / "rules/us-dd.json")
        cls.base_rules = load(PERMIT / "rules/us.json")
        cls.items = load(PERMIT / "items-dd.json")
        cls.base_items = load(PERMIT / "items.json")

    def test_register(self):
        secs = self.reg["sections"]
        self.assertGreaterEqual(len(secs), 30)
        for k, s in secs.items():
            self.assertRegex(s["sha256"], r"^[0-9a-f]{64}$", k)
            self.assertEqual(s["opened"], "2026-10-27", k)
            self.assertTrue(s["url"].startswith("https://codes.iccsafe.org/content/I"), k)
            self.assertIn(s["code"], CODES, k)
            self.assertGreater(s["chars"], 0, k)
            self.assertNotIn(k, self.base["sections"], k)
        for want in ("IPC 403.1", "IPC 403.3.3", "IBC T716.1(2)", "IBC T721.1(2) item 13", "IBC 905.3.1",
                     "IBC 907.4.2.1", "IBC 1013.1", "IBC 1008.3.2", "IBC 1104.4", "IFC 6004.2.2.9", "IFC 6004.1.2",
                     "IMC 509.4"):
            self.assertIn(want, secs)
        ids = " ".join(n["id"] for n in self.reg["not_read"])
        for want in ("ASCE 7", "NFPA 13", "NFPA 70", "NFPA 72", "ISO 14644-1", "ICC A117.1", "ISEA Z358.1"):
            self.assertIn(want, ids)
        self.assertFalse(secs["IPC 403.1"]["facts"]["h_listed"])

    def test_profile(self):
        dd = self.us["permit"]["dd"]
        self.assertEqual(dd["register"], "viz/permit/codes/us-2024-dd.json")
        self.assertEqual(dd["rules"], "viz/permit/rules/us-dd.json")
        self.assertEqual(dd["items"], "viz/permit/items-dd.json")
        j = dd["judgements"]
        self.assertIs(j["chase_is_service_corridor"]["value"], True)
        self.assertEqual(j["risk_category"]["value"], 4)
        for v in j.values():
            self.assertIn("assumed", v["basis"])

    def test_rules(self):
        secs = set(self.base["sections"]) | set(self.reg["sections"])
        nr = {n["id"] for n in self.reg["not_read"]}
        base_ids = {r["id"] for r in self.base_rules}
        ids = [r["id"] for r in self.rules]
        self.assertEqual(len(ids), len(set(ids)))
        for r in self.rules:
            self.assertTrue(r["cite"], r["id"])
            for c in r["cite"]:
                self.assertIn(c, secs, r["id"])
            for x in r.get("rests_on", []):
                self.assertIn(x, nr, r["id"])
        for want in ("service.dead_end", "walls.types", "doors.rating", "penetrations.firestop", "plumbing.fixtures",
                     "plumbing.separate", "plumbing.toilet_travel", "plumbing.drains", "plumbing.showers",
                     "access.levels", "access.stairs", "egress.exit_signs", "egress.emergency_lighting",
                     "fire.standpipes", "alarm.box_location", "alarm.box_height", "gas.cabinets",
                     "gas.cabinet_room_exhaust", "exhaust.incompatible", "exhaust.no_dampers", "exhaust.makeup",
                     "elec.emergency_panels", "elec.wiring"):
            self.assertIn(want, ids)
        # the three base rules that rested on law now read are replaced
        for rid in ("access.route", "alarm.smoke_detection", "alarm.notification"):
            self.assertIn(rid, ids)
            self.assertIn(rid, base_ids)

    def test_items(self):
        base = {i["id"] for i in self.base_items}
        ids = [i["id"] for i in self.items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 30)
        for i in self.items:
            self.assertNotIn(i["id"], base)
            self.assertEqual(i["stage"], "DD", i["id"])
            self.assertIn(i["discipline"], ("G", "C", "S", "A", "M", "PP", "P", "FP", "FA", "E", "spec"), i["id"])
            self.assertIn(i["sheet"], SHEETS + ["specs.md", "fab-permit.ifc"], i["id"])
            self.assertIsInstance(i["licensed_review"], bool)
        for s in NEW:
            self.assertIn(s, {i["sheet"] for i in self.items}, s)


@unittest.skipUnless(SCENE.exists(), "needs the scene of the cross aisle layout (DD2)")
class Scene(unittest.TestCase):
    """DD2: the layout D10 rescored with a cross aisle on every wall of tools; every chase is clear."""

    def test_scene_is_the_wider_chase(self):
        L = load(LAYOUT)
        self.assertAlmostEqual(L["assumed"]["chase"], 1.6)
        self.assertAlmostEqual(L["assumed"]["cross"], 1.6)
        depth = L["assumed"]["bay_depth"]
        g0, g1 = (depth - 1.6) / 2, (depth + 1.6) / 2
        for t in L["plans"]["optimised"]["tools"]:
            y0, y1 = t[6], t[7]
            self.assertFalse(y0 < g1 - 1e-6 and y1 > g0 + 1e-6, t)
        S = load(SCENE)
        self.assertIn("SMT2020", S["what"])
        chase = L["assumed"]["chase"]
        bays = S["bays"]
        for t in S["tools"]:
            b = bays[t["bay"]]
            self.assertGreaterEqual(t["x0"], b["x0"] + chase - 1e-6, t)
            self.assertLessEqual(t["x1"], b["x1"] - chase + 1e-6, t)


@unittest.skipUnless(SCENE.exists() and HAVE, "needs the 1.6 m chase scene and IfcOpenShell (.venv)")
class DesignDevelopment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "us"
        run(["--place", "us", "--stage", "dd", "--scene", SCENE, "--layout", LAYOUT, "--out", cls.out])
        cls.P = load(cls.out / "permit.json")
        cls.V = load(cls.out / "verdicts.json")
        cls.L = load(cls.out / "ledger.json")
        cls.S = load(SCENE)
        reg = load(PERMIT / "codes/us-2024.json")
        dd = load(PERMIT / "codes/us-2024-dd.json")
        cls.secs = {**reg["sections"], **dd["sections"]}
        cls.f = ifcopenshell.open(str(cls.out / "fab-permit.ifc"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def fact(self, sec, k):
        return self.secs[sec]["facts"][k]

    def verdicts(self, rule):
        got = [v for v in self.V if v["rule"] == rule]
        self.assertTrue(got, rule)
        return got

    def all_met(self, rule):
        for v in self.verdicts(rule):
            self.assertEqual(v["verdict"], "met", (rule, v["scope"], v["why"]))

    def all_cannot_say(self, rule):
        for v in self.verdicts(rule):
            self.assertEqual(v["verdict"], "cannot say", (rule, v["scope"], v["why"]))

    # ---- the stage
    def test_stage_and_judgements(self):
        self.assertEqual(self.P["stage"], "dd")
        self.assertIn("SMT2020", self.P["truth"])
        j = self.P["judgements"]
        self.assertIs(j["chase_is_service_corridor"]["value"], True)
        self.assertEqual(j["risk_category"]["value"], 4)
        rules = load(PERMIT / "rules/us.json")
        dd_rules = load(PERMIT / "rules/us-dd.json")
        want = {r["id"] for r in rules} | {r["id"] for r in dd_rules}
        self.assertEqual({v["rule"] for v in self.V}, want)
        for v in self.V:
            self.assertIn(v["verdict"], VERDICTS)
            self.assertTrue(v["why"], v["rule"])

    # ---- DD3
    def test_service_corridors(self):
        for rule in ("service.corridor_width", "service.corridor_travel", "service.corridor_ventilation",
                     "service.dead_end"):
            self.all_met(rule)
        chases = self.P["chases"]
        self.assertEqual(len(chases), 2 * len(self.S["bays"]))
        for c in chases:
            self.assertGreaterEqual(c["width_m"], 5 * FT - 1e-9, c["id"])
            self.assertLessEqual(c["max_travel_m"], 75 * FT + 1e-6, c["id"])
            self.assertLessEqual(c["dead_end_m"], 4 * FT + 1e-6, c["id"])
            self.assertGreaterEqual(c["ach"], 6 - 1e-9, c["id"])
        self.all_met("structure.risk_category")

    # ---- DD4
    def test_walls_doors_firestops(self):
        self.all_met("walls.types")
        self.all_met("doors.rating")
        self.all_met("penetrations.firestop")
        types = self.P["wall_types"]
        self.assertEqual(types["WT-1"]["rating_h"], 1)
        self.assertEqual(types["WT-2"]["rating_h"], 2)
        for w in self.P["walls"]:
            if w["rating_h"] > 0:
                self.assertIn(w["type"], types, w["key"])
                self.assertGreaterEqual(types[w["type"]]["rating_h"], w["rating_h"], w["key"])
        table = {"fire barrier 2 h": 1.5, "exit enclosure 2 h": 1.5, "exit enclosure 1 h": 1,
                 "exit passageway 1 h": 1, "other fire barrier 1 h": 0.75, "corridor 1 h": 1 / 3}
        self.assertTrue(self.P["doors"])
        for d in self.P["doors"]:
            if d["wall_kind"] in table:
                self.assertGreaterEqual(d["rating_h"], table[d["wall_kind"]] - 1e-6, d["key"])
        for p in self.P["firestops"]:
            self.assertGreaterEqual(p["f_rating_h"], p["wall_rating_h"], p)

    def test_toilets(self):
        for rule in ("plumbing.fixtures", "plumbing.separate", "plumbing.toilet_travel", "plumbing.drains"):
            self.all_met(rule)
        T = self.P["toilets"]
        for b in ("P1", "P2"):
            t = T["by_building"][b]
            per_sex = math.ceil(t["occupants"] / 2 / 100)
            self.assertGreaterEqual(t["wc_men"], per_sex, b)
            self.assertGreaterEqual(t["wc_women"], per_sex, b)
            self.assertGreaterEqual(t["lav_men"], per_sex, b)
            self.assertGreaterEqual(t["lav_women"], per_sex, b)
            self.assertGreaterEqual(t["drinking_fountains"], math.ceil(t["occupants"] / 400), b)
            self.assertGreaterEqual(t["service_sinks"], 1, b)
            for story in ("clean floor", "support floor"):
                self.assertLessEqual(t["travel_m"][story], 500 * FT + 1e-6, (b, story))
        for c in T["cores"]:
            self.assertTrue(c["men_room"] and c["women_room"], c["id"])
        for d in self.P["drains"]:
            self.assertGreaterEqual(d["building_drain_in"], 3, d)

    def test_showers_lifts_access(self):
        self.all_cannot_say("plumbing.showers")
        at = {s["at"] for s in self.P["showers"]}
        for r in self.P["rooms"]:
            if r["kind"] == "chemical dispense":
                self.assertIn(r["id"], at)
        wet = {i for i, b in enumerate(self.S["bays"]) if b["area"] == "Wet_Etch"}
        for i in wet:
            self.assertIn(f"bay {i + 1:02d}", at)
        lifts = self.P["lifts"]
        self.assertEqual(sorted(l["building"] for l in lifts), ["P1", "P2"])
        for l in lifts:
            self.assertEqual(set(l["serves"]), {"support floor", "clean floor"})
        self.all_met("access.levels")
        self.all_met("access.stairs")
        self.all_cannot_say("access.route")

    def test_signs_and_lighting(self):
        self.all_met("egress.exit_signs")
        self.all_met("egress.emergency_lighting")
        for b in ("P1", "P2"):
            s = self.P["exit_signs"][b]
            self.assertLessEqual(s["max_to_sign_ft"], 100 + 1e-6, b)
            e = self.P["emergency_lighting"][b]
            self.assertGreaterEqual(e["avg_fc_lo"], 1 - 1e-9, b)
            self.assertGreaterEqual(e["min_fc_lo"], 0.1 - 1e-9, b)
            self.assertGreaterEqual(e["duration_min"], 90, b)

    def test_alarms_and_standpipes(self):
        for rule in ("alarm.box_location", "alarm.box_height", "alarm.smoke_detection", "fire.standpipes"):
            self.all_met(rule)
        self.all_cannot_say("alarm.notification")
        for a in self.P["alarm_boxes"]:
            self.assertLessEqual(a["to_exit_ft"], 5 + 1e-6, a)
            self.assertTrue(42 - 1e-6 <= a["handle_in"] <= 48 + 1e-6, a)
        sp = self.P["standpipes"]
        self.assertFalse(sp["required"])
        self.assertLess(sp["highest_floor_ft"], 30)
        h = self.P["ht_detection"]
        self.assertTrue(h["rooms"] or h["bays"])
        self.assertTrue(set(h["rooms"]) <= set(h["detected_rooms"]))
        self.assertTrue(set(h["bays"]) <= set(h["detected_bays"]))
        self.assertGreaterEqual(self.P["notification"]["spare_capacity"], 0.2)

    def test_gas_and_exhaust(self):
        for rule in ("gas.cabinets", "gas.cabinet_room_exhaust", "exhaust.incompatible", "exhaust.no_dampers",
                     "exhaust.makeup"):
            self.all_met(rule)
        cabs = self.P["gas_cabinets"]
        self.assertTrue(cabs)
        for c in cabs:
            self.assertLessEqual(c["cylinders"], 3, c["id"])
            self.assertGreaterEqual(c["face_fpm"], 200, c["id"])
            self.assertGreater(c["exhaust_cfm"], 0, c["id"])
            self.assertTrue(c["sprinkler"], c["id"])
        X = self.P["exhaust"]
        self.assertTrue({"general", "acid", "solvent", "toxic"} <= set(X["systems"]))
        self.assertEqual(X["dampers_on_hazardous"], 0)
        for b, m in self.P["makeup"].items():
            self.assertLessEqual(abs(m["makeup_cfm"] / m["exhaust_cfm"] - 1), 0.1 + 1e-9, b)
        U = self.P["utilities"]
        for u, d in U["demand"].items():
            self.assertGreaterEqual(U["plant"][u]["capacity"], d["diversified"], u)
        self.assertGreater(len(self.P["valve_boxes"]), 0)

    # ---- DD5 and DD9
    def test_members_and_panels(self):
        M = self.P["members"]
        cols = {c["id"] for c in self.P["frame"]["columns"]}
        self.assertEqual({c["id"] for c in M["columns"]}, cols)
        for c in M["columns"]:
            self.assertGreater(c["area_mm2"], 0, c["id"])
        for b in M["beams"]:
            self.assertGreater(b["sx_mm3"], 0, b["id"])
        self.all_cannot_say("structure.seismic")
        self.all_cannot_say("structure.wind")
        panels = {p["id"]: p for p in self.P["panels"]}
        self.assertEqual(len(self.P["tool_panel"]), len(self.S["tools"]))
        for i, pid in self.P["tool_panel"].items():
            self.assertIn(pid, panels, i)
        for p in panels.values():
            self.assertLessEqual(p["load_kva"], p["rating_kva"] + 1e-6, p["id"])
        self.assertTrue(any(p["emergency"] for p in panels.values()))
        self.all_met("elec.emergency_panels")
        self.all_cannot_say("elec.wiring")
        self.all_cannot_say("sprinklers.density")

    # ---- DD10
    def test_coordination_and_ifc(self):
        self.assertEqual(self.P["clashes"], [])
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(self.f, logger)
        errors = [s for s in logger.statements if s.get("level", "").lower() == "error"]
        self.assertEqual(errors, [])
        n300 = 0
        for e in self.f.by_type("IfcProduct"):
            ps = uel.get_psets(e)
            if "FabGym_Permit" in ps:
                lod = ps["FabGym_Permit"]["LOD"]
                self.assertIn(lod, (100, 200, 300, 350), e.Name)
                n300 += lod == 300
                if e.is_a("IfcWall") or e.is_a("IfcDoor") or e.is_a("IfcPipeSegment") or e.is_a("IfcDuctSegment"):
                    self.assertEqual(lod, 300, e.Name)
            if e.is_a("IfcWall") and "FabGym_Rating" in ps and ps["FabGym_Rating"]["Rating_h"] > 0:
                self.assertIn("721.1(2)", ps["FabGym_Rating"]["Cite"], e.Name)
        self.assertGreater(n300, 1000)
        for cls in ("IfcTransportElement", "IfcSanitaryTerminal", "IfcFan", "IfcUnitaryEquipment", "IfcValve",
                    "IfcElectricDistributionBoard", "IfcLightFixture", "IfcFilter"):
            self.assertGreater(len(self.f.by_type(cls)), 0, cls)

    def test_same_every_run(self):
        other = self.tmp / "again"
        run(["--place", "us", "--stage", "dd", "--scene", SCENE, "--layout", LAYOUT, "--out", other, "--no-pdf"])
        for name in ("fab-permit.ifc", "permit.json", "verdicts.json", "ledger.json", "specs.md"):
            self.assertEqual((self.out / name).read_bytes(), (other / name).read_bytes(), name)

    # ---- DD11
    def test_sheets_and_ledger(self):
        idx = load(self.out / "index.json")
        self.assertEqual([s["id"] for s in idx], SHEETS)
        for s in idx:
            svg = (self.out / "sheets" / f"{s['id']}.svg").read_text()
            self.assertIn(TRUTH, svg, s["id"])
            self.assertIn("NOT FOR CONSTRUCTION", svg, s["id"])
            self.assertIn('viewBox="0 0 1066.8 762"', svg, s["id"])
        g2 = (self.out / "sheets/G-002.svg").read_text()
        for r in load(PERMIT / "rules/us-dd.json"):
            self.assertIn(r["id"], g2)
        self.assertIn("design development", (self.out / "sheets/G-001.svg").read_text().lower())
        items = load(PERMIT / "items.json") + load(PERMIT / "items-dd.json")
        self.assertEqual([i["id"] for i in self.L["items"]], [i["id"] for i in items])
        g3 = (self.out / "sheets/G-003.svg").read_text()
        for i in self.L["items"]:
            self.assertIn(i["id"], g3)
            self.assertIn(i["status"], STATUSES, i["id"])
            if i["licensed_review"]:
                self.assertEqual(i["status"], "licensed review", i["id"])
        self.assertEqual(self.L["counts"].get("missing", 0), 0,
                         [i["id"] for i in self.L["items"] if i["status"] == "missing"])

    def test_specs_and_text(self):
        md = (self.out / "specs.md").read_text()
        for d in DIVISIONS:
            self.assertRegex(md, rf"(?m)^## Division {d} ")
        self.assertIn("NOT FOR CONSTRUCTION", md)
        self.assertIn(TRUTH, md)
        for p in self.out.rglob("*"):
            if p.suffix in (".svg", ".json", ".md", ".ifc", ".html"):
                t = p.read_text()
                self.assertNotIn("TSMC", t, p.name)
                self.assertTrue(t.isascii() or p.suffix in (".svg", ".html", ".md"), p.name)

    def test_rescore(self):
        R = load(RESCORE)
        self.assertIn("SMT2020 model", R["truth"])
        self.assertEqual(R["cross_before_m"], 0.0)
        self.assertEqual(R["cross_after_m"], 1.6)
        self.assertEqual(R["chase_m"], 1.6)
        self.assertGreaterEqual(R["seeds"], 5)
        for m in R["measures"]:
            self.assertLessEqual(m["lo"], m["diff"])
            self.assertLessEqual(m["diff"], m["hi"])

    def test_pdf(self):
        if not Path("/Applications/Google Chrome.app").exists():
            self.skipTest("needs Google Chrome for the PDF")
        pdf = (self.out / "permit-set.pdf").read_bytes()
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page[^s]", pdf)), len(SHEETS))


if __name__ == "__main__":
    unittest.main()
