"""Tests for the realistic fab (docs/FAB-LOOK-PROBLEM.md, docs/FAB-LOOK.md, docs/FAB-FILM-SCRIPT.md).

A gigafab-style layout of our own design on the SMT2020 model. Standard library only:

    python3 -m unittest discover -s viz/tests

Tests that need generated files (the re-packed layout, its scene, the film's captions) skip
when those files are missing; `viz/look/build.sh` makes them.
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "viz" / "look"))
sys.path.insert(0, str(ROOT / "viz" / "film"))

SIZES = json.loads((ROOT / "viz/look/sizes.json").read_text())
SHOTS = json.loads((ROOT / "viz/film/shots.json").read_text())
REAL_LAYOUT = ROOT / "results/layout-real/layout.json"
SCENE = ROOT / "data/layout-real/scene-optimised.json"
TRACE = ROOT / "data/layout-real/trace-optimised.json"
GROUPS = [g["name"] for g in json.loads((ROOT / "results/layout/layout.json").read_text())["groups"]] + ["Delay_32"]

# makers of fab tools, carriers and hoists, and fabs: none may appear on a model, texture or caption
BRANDS = ["ASML", "TSMC", "Tokyo Electron", "TEL ", "Applied Materials", "Lam Research", "KLA", "Axcelis",
          "Entegris", "Daifuku", "Murata", "Muratec", "Ebara", "SCREEN", "Kokusai", "Canon", "Nikon",
          "Samsung", "Intel", "Hitachi", "Shin-Etsu", "Miraial", "Purion", "TWINSCAN"]

TOL = 0.05


def kind_rows():
    """The tool table of FAB-LOOK.md: kind -> (W, D, H)."""
    rows = {}
    for line in (ROOT / "docs/FAB-LOOK.md").read_text().splitlines():
        m = re.match(r"\|\s*([A-Za-z ()]+?)\s*\|[^|]*\|\s*([\d.]+) × ([\d.]+) × ([\d.]+)", line)
        if m:
            rows[m.group(1).lower().replace("(cmp)", "").strip().replace(" ", "_")] = tuple(float(m.group(i)) for i in (2, 3, 4))
    return rows


def bbox(parts, skip=("light",)):
    ps = [p for p in parts if p.get("role") not in skip]
    lo = [min(p["min"][i] for p in ps) for i in range(3)]
    hi = [max(p["max"][i] for p in ps) for i in range(3)]
    return lo, hi


def near(a, b, tol=TOL):
    return abs(a - b) <= tol * abs(b) + 1e-9


class SizeBook(unittest.TestCase):
    def test_the_json_matches_the_book(self):
        rows = kind_rows()
        names = {"coat_and_develop_track": "track", "vertical_furnace": "furnace", "ion_implanter": "implanter",
                 "polisher": "polisher", "wet_bench": "wet_bench", "etch_cluster_tool": "etch",
                 "deposition_cluster_tool": "deposition"}
        got = {names.get(k, k): v for k, v in rows.items()}
        for k in SIZES["kinds"]:
            self.assertIn(k["kind"], got, f"{k['kind']} missing from FAB-LOOK.md")
            self.assertEqual(got[k["kind"]], (k["w"], k["d"], k["h"]), k["kind"])
        book = (ROOT / "docs/FAB-LOOK.md").read_text()
        c = SIZES["carrier"]
        self.assertIn(f"{c['w']:.3f} × {c['d']:.3f} × {c['h']:.3f}", book)
        self.assertIn("| wafers in a lot | 25 |", book)

    def test_every_group_has_one_kind(self):
        import kit
        want = {"LithoMet_BE_18": "metrology", "Litho_REG_BE_63": "metrology", "TF_Met_FE_45": "metrology",
                "LithoTrack_FE_95": "track", "Litho_FE_35": "scanner", "DefMEt_FE_118": "inspection",
                "DE_BE_65": "etch", "TF_BE_2": "deposition", "Dielectric_FE_29": "deposition", "EPI_36": "epitaxy",
                "Diffusion_BE_123": "furnace", "Implant_74": "implanter", "Planar_BE_75": "polisher",
                "WE_BE_9": "wet_bench", "Delay_32": "stocker"}
        for g, k in want.items():
            self.assertEqual(kit.kind_of(g), k, g)
        for g in GROUPS:
            self.assertIsNotNone(kit.kind_of(g), g)

    @unittest.skipUnless(REAL_LAYOUT.exists(), "re-packed layout not built")
    def test_the_layout_uses_the_book(self):
        lay = json.loads(REAL_LAYOUT.read_text())
        kinds = lay["assumed"]["kinds"]
        for k in SIZES["kinds"]:
            self.assertEqual((kinds[k["kind"]]["w"], kinds[k["kind"]]["d"]), (k["w"], k["d"]), k["kind"])
        self.assertEqual(lay["assumed"]["phase_rule"], "where its lots come from")


class Models(unittest.TestCase):
    def test_each_tool_matches_its_size(self):
        import kit
        for k in SIZES["kinds"]:
            parts = kit.model(k["kind"])
            lo, hi = bbox(parts)
            dims = [hi[i] - lo[i] for i in range(3)]
            for got, want, axis in zip(dims, (k["w"], k["d"], k["h"]), "WDH"):
                self.assertTrue(near(got, want), f"{k['kind']} {axis}: {got:.3f} against {want}")
            self.assertAlmostEqual(lo[2], 0.0, places=6, msg=f"{k['kind']} stands on the floor")

    def test_close_up_detail(self):
        import kit
        for k in SIZES["kinds"]:
            parts = kit.model(k["kind"])
            self.assertGreaterEqual(len(parts), 30, f"{k['kind']} needs close-up detail")
            self.assertGreaterEqual(len({p["mat"] for p in parts}), 4, f"{k['kind']} needs several materials")
            for p in parts:
                self.assertIn(p["shape"], ("box", "cyl"))
                self.assertTrue(all(p["max"][i] > p["min"][i] for i in range(3)), f"{k['kind']}: {p['name']} is flat")

    def test_ports_and_lights(self):
        import kit
        seat = SIZES["port_seat"]
        for k in SIZES["kinds"]:
            parts = kit.model(k["kind"])
            ports = [p for p in parts if p.get("role") == "port"]
            self.assertEqual(len(ports), k["ports"], f"{k['kind']} load ports")
            for p in ports:
                self.assertAlmostEqual(p["max"][2], seat, delta=0.02, msg=f"{k['kind']} carrier seat height")
                self.assertLess(p["min"][1], 0.8, f"{k['kind']} ports face the aisle")
            if k["kind"] != "stocker":
                lights = [p for p in parts if p.get("role") == "light"]
                self.assertTrue(lights, f"{k['kind']} has a status light")
                self.assertTrue(near(max(p["max"][2] for p in lights) - min(p["min"][2] for p in lights), SIZES["status_light"], 0.1))

    def test_carrier_and_hoist(self):
        import kit
        c, v = SIZES["carrier"], SIZES["vehicle"]
        lo, hi = bbox(kit.carrier())
        for got, want in zip([hi[i] - lo[i] for i in range(3)], (c["w"], c["d"], c["h"])):
            self.assertTrue(near(got, want), f"carrier {got:.3f} against {want}")
        lo, hi = bbox(kit.vehicle())
        for got, want in zip([hi[i] - lo[i] for i in range(3)], (v["l"], v["w"], v["h"])):
            self.assertTrue(near(got, want), f"hoist car {got:.3f} against {want}")

    def test_no_maker_names(self):
        import kit
        texts = [json.dumps([kit.model(k["kind"]) for k in SIZES["kinds"]]), json.dumps(kit.carrier()), json.dumps(kit.vehicle()),
                 (ROOT / "viz/look/kit.py").read_text(), json.dumps(SHOTS)]
        for t in texts:
            for b in BRANDS:
                self.assertNotIn(b, t, b)


class Building(unittest.TestCase):
    def test_the_floors_stack(self):
        import kit
        b = SIZES["building"]
        f = kit.floors()
        self.assertEqual([x["name"] for x in f], ["support floor", "waffle slab", "raised floor", "cleanroom", "air space", "roof"])
        z = 0.0
        for x, h in zip(f, (b["support_floor"], b["waffle_slab"], b["raised_floor"], b["cleanroom"], b["air_space"], b["roof_slab"])):
            self.assertAlmostEqual(x["z0"], z, places=6, msg=x["name"])
            self.assertAlmostEqual(x["z1"], z + h, places=6, msg=x["name"])
            z += h
        self.assertAlmostEqual(kit.clean_floor_z(), b["support_floor"] + b["waffle_slab"] + b["raised_floor"])


@unittest.skipUnless(SCENE.exists(), "realistic scene not built")
class Scene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = json.loads(SCENE.read_text())

    def test_true_size_carriers_and_rail(self):
        import kit
        s, c = self.s, SIZES["carrier"]
        self.assertEqual(s["foup"], [c["w"], c["d"], c["h"]], "carriers at true size")
        z = kit.clean_floor_z()
        self.assertAlmostEqual(s["port_z"], z + SIZES["port_seat"], places=6)
        self.assertAlmostEqual(s["rail_z"], z + SIZES["rail_underside"], places=6)
        self.assertAlmostEqual(s["ride_z"], s["rail_z"] - SIZES["vehicle"]["h"] - c["h"], places=6)
        for lot in s["lots"]:
            for k in lot["k"]:
                self.assertGreaterEqual(k[3], s["port_z"] - 1e-6, lot["id"])
                self.assertLessEqual(k[3], s["ride_z"] + 1e-6, lot["id"])

    def test_floors_and_kinds(self):
        import kit
        self.assertEqual(self.s["floors"], kit.floors())
        kinds = {t["kind"] for t in self.s["tools"]}
        self.assertEqual(kinds, {k["kind"] for k in SIZES["kinds"]} - {"stocker"})
        for t in self.s["tools"]:
            self.assertEqual(t["kind"], kit.kind_of(self.s["groups"][t["g"]]["name"]))

    def test_states_follow_the_run(self):
        # every state change names a tool that exists, in time order
        n = len(self.s["tools"])
        last = -1e18
        for t, tool, code in self.s["states"]:
            self.assertGreaterEqual(t, last)
            self.assertTrue(0 <= tool < n)
            self.assertIn(code, (0, 1, 2, 3))
            last = t

    @unittest.skipUnless(TRACE.exists(), "trace not built")
    def test_lots_sit_where_the_run_puts_them(self):
        tr = json.loads(TRACE.read_text())
        keys = {l["id"]: l["k"] for l in self.s["lots"]}
        tools = self.s["tools"]
        checked = 0
        for lot in tr["lots"][:300]:
            for a, b, e, ti, g in lot["steps"]:
                if ti < 0 or not (tr["from"] <= b <= tr["to"]):
                    continue
                at = [k for k in keys[lot["id"]] if abs(k[0] - b) < 1e-6]
                self.assertTrue(at, f"{lot['id']} has a key when it starts on tool {ti}")
                t = tools[ti]
                x, y = at[-1][1], at[-1][2]
                self.assertTrue(t["x0"] - 1.5 <= x <= t["x1"] + 1.5 and t["y0"] - 1.5 <= y <= t["y1"] + 1.5,
                                f"{lot['id']} at ({x:.1f},{y:.1f}) is not at its tool {ti}")
                checked += 1
        self.assertGreater(checked, 50)

    def test_no_maker_names_in_the_scene(self):
        t = SCENE.read_text()
        for b in BRANDS:
            self.assertNotIn(b, t, b)
        self.assertIn("on the SMT2020 model", self.s["what"])


class Film(unittest.TestCase):
    def test_the_shot_list_follows_the_script(self):
        shots = SHOTS["shots"]
        self.assertEqual([s["id"] for s in shots], [str(i) for i in range(1, 14)] + ["end"])
        self.assertEqual([s["act"] for s in shots], [1, 1, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 5, 5])
        self.assertEqual(shots[0]["start"], 0)
        for a, b in zip(shots, shots[1:]):
            self.assertEqual(a["end"], b["start"], f"gap after shot {a['id']}")
        self.assertEqual(shots[-1]["end"], 127)
        for s in shots[:-1]:
            self.assertIn(s["lens"], (24, 35, 50, 85), s["id"])
        script = " ".join((ROOT / "docs/FAB-FILM-SCRIPT.md").read_text().split())
        for s in shots:
            for c in s["captions"]:
                self.assertIn(" ".join(c.split()), script, f"shot {s['id']}: {c}")
        for s in shots:
            # read at three words a second, every caption of a shot inside the shot
            n = sum(len(c.split()) for c in s["captions"])
            self.assertLessEqual(n / 3.0, s["end"] - s["start"] + 0.5, f"shot {s['id']}: {n} words in {s['end'] - s['start']} s")
        self.assertIn("on the SMT2020 model", shots[0]["captions"][0])
        self.assertIn("Not a real fab", shots[-1]["captions"][0])

    def test_outside_inside_lot_outside(self):
        acts = {s["act"] for s in SHOTS["shots"]}
        self.assertEqual(acts, {1, 2, 3, 4, 5})
        self.assertEqual(SHOTS["shots"][0]["lens"], SHOTS["shots"][12]["lens"], "the film ends on its opening angle")

    @unittest.skipUnless(TRACE.exists() and SCENE.exists(), "re-packed run not built")
    def test_the_lot_follows_the_rule(self):
        import film
        tr = json.loads(TRACE.read_text())
        s = json.loads(SCENE.read_text())
        lot = film.choose_lot(tr, s)
        steps = [x for x in lot["steps"] if x[0] >= tr["from"] - 30]
        kinds = {film.kind_of_group(s, x[4]) for x in steps}
        self.assertIn("scanner", kinds)
        self.assertTrue(kinds & {"metrology", "inspection"})
        self.assertIn("etch", kinds)
        self.assertTrue(any(x[1] - x[0] > 60 for x in steps), "a wait of over an hour")
        caps = film.captions(tr, s, lot)
        self.assertEqual(sorted(caps), sorted(x["id"] for x in SHOTS["shots"]))
        for x in SHOTS["shots"]:
            self.assertEqual(len(caps[x["id"]]), len(x["captions"]), x["id"])
        self.assertIn("on the SMT2020 model", caps["1"][0])
        for t in caps.values():
            for b in BRANDS:
                self.assertNotIn(b, " ".join(t))


if __name__ == "__main__":
    unittest.main()
