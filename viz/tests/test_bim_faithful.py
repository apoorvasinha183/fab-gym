"""Tests for the faithful BIM of the construction documents (docs/BIM-FAITHFUL.md). Written before the code.
A gigafab-style layout of our own design on the SMT2020 model; not a real fab. NOT FOR CONSTRUCTION.

    .venv/bin/python -m unittest viz.tests.test_bim_faithful      (from the repo root)

Needs the cross aisle scene (docs/DESIGN-DEV.md, DD2) and IfcOpenShell in the repo's .venv; skips without them.
"""

import collections
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

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
SCENE = ROOT / "data/layout-real-dd/scene-optimised.json"
LAYOUT = ROOT / "results/layout-real-dd/layout.json"
SCENE0 = ROOT / "data/layout-real/scene-optimised.json"
LAYOUT0 = ROOT / "results/layout-real/layout.json"
RUN = ROOT / "viz/permit/run.py"
TOL = 1e-3
# the schematic and design development IFCs before this work (28 Oct 2026, fab-gym 7ffad51)
BEFORE = {"full": "ee6f7371b913ad423b46ac808cba486bc71ffc11f2de9e1d33c51deb59b6a187",
          "dd": "b1dd306612606677d4ee58880edc232f77fd60f6ef1ff4f6dc3b7855ecc91b74"}
ROUND_M = [0.1, 0.125, 0.16, 0.2, 0.25, 0.315, 0.4, 0.5]
FLOOR_LANDING = 2.10
MID_LANDING_MIN = 1.118

try:
    import ifcopenshell
    import ifcopenshell.util.element as uel
    import ifcopenshell.validate
    import bimgeo as G
    HAVE = True
except ImportError:
    HAVE = False


def run(stage, scene, layout, out):
    p = subprocess.run([sys.executable, str(RUN), "--place", "us", "--stage", stage, "--scene", str(scene), "--layout",
                        str(layout), "--out", str(out), "--no-pdf"], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(p.stdout + p.stderr)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def profiles(e):
    return [it.SweptArea for it in G.items(e) if it.is_a("IfcSweptAreaSolid")]


def inside(lo, hi, box, tol=TOL):
    return all(lo[k] >= box[k] - tol and hi[k] <= box[k + 3] + tol for k in range(3))


@unittest.skipUnless(SCENE.exists() and HAVE, "needs the cross aisle scene and IfcOpenShell (.venv)")
class Faithful(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "us"
        run("cd", SCENE, LAYOUT, cls.out)
        cls.P = json.loads((cls.out / "permit.json").read_text())
        cls.S = json.loads(SCENE.read_text())
        cls.cz = cls.S["clean_z"]
        cls.B = json.loads((cls.out / "boxes.json").read_text())
        cls.f = ifcopenshell.open(str(cls.out / "fab-permit.ifc"))
        cls.prods = [e for e in cls.f.by_type("IfcProduct") if e.Representation and not e.is_a("IfcOpeningElement")]
        keep = {e.GlobalId for e in cls.f.by_type("IfcStairFlight")} | {e.GlobalId for e in cls.f.by_type("IfcRailing")}
        cls.bounds, cls.verts = G.world_bounds(cls.f, cls.prods, keep)
        cls.obounds, _ = G.world_bounds(cls.f, cls.f.by_type("IfcOpeningElement"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def box(self, e):
        return self.B[e.GlobalId]["box"]

    def of(self, cls, otype=None, pre=None):
        return [e for e in self.f.by_type(cls) if (otype is None or e.ObjectType == otype)
                and (pre is None or getattr(e, "PredefinedType", None) == pre)]

    # ---------------------------------------------------------------- doors, openings, hatches
    def test_doors_fill_openings(self):
        doors = self.f.by_type("IfcDoor")
        self.assertEqual(len(doors), 278)
        for d in doors:
            fills = d.FillsVoids
            self.assertEqual(len(fills), 1, d.Name)
            op = fills[0].RelatingOpeningElement
            hosts = op.VoidsElements
            self.assertEqual(len(hosts), 1, d.Name)
            host = hosts[0].RelatingBuildingElement
            hb = self.box(host)
            lo, hi = self.obounds[op.GlobalId]
            if d.PredefinedType == "TRAPDOOR":
                self.assertTrue(host.is_a("IfcSlab"), d.Name)
                self.assertLessEqual(lo[2], hb[2] + TOL)
                self.assertGreaterEqual(hi[2], hb[5] - TOL)
                continue
            self.assertTrue(host.is_a("IfcWall"), (d.Name, host.is_a()))
            thin = 0 if hb[3] - hb[0] < hb[4] - hb[1] else 1
            long = 1 - thin
            self.assertLessEqual(lo[thin], hb[thin] + TOL, d.Name)
            self.assertGreaterEqual(hi[thin], hb[thin + 3] - TOL, d.Name)
            self.assertGreaterEqual(lo[long], hb[long] - TOL, d.Name)
            self.assertLessEqual(hi[long], hb[long + 3] + TOL, d.Name)
            self.assertGreaterEqual(len(G.items(d)), 4, d.Name)    # two jambs, a head, a leaf
            cw = uel.get_psets(d).get("FabGym_Door", {}).get("ClearWidth")
            self.assertIsNotNone(cw, d.Name)
            self.assertLess(cw, d.OverallWidth, d.Name)

    def test_hatch_ladders(self):
        hatches = self.of("IfcDoor", pre="TRAPDOOR")
        ladders = self.of("IfcStair", otype="fixed ladder")
        self.assertEqual(len(ladders), len(hatches))
        ceil_top = [fl for fl in self.S["floors"] if fl["name"] == "air space"][0]["z0"]
        roof0 = [fl for fl in self.S["floors"] if fl["name"] == "roof"][0]["z0"]
        for h in hatches:
            hb = self.box(h)
            mine = [l for l in ladders if G.boxes_overlap(((self.box(l)[0], self.box(l)[1], -1), (self.box(l)[3], self.box(l)[4], 1)),
                                                         ((hb[0], hb[1], -1), (hb[3], hb[4], 1)))]
            self.assertEqual(len(mine), 1, h.Name)
            lo, hi = self.bounds[mine[0].GlobalId]
            self.assertAlmostEqual(lo[2], ceil_top, delta=0.05)
            self.assertAlmostEqual(hi[2], roof0, delta=0.05)

    # ---------------------------------------------------------------- stairs
    def test_stairs(self):
        r = self.cz / 44
        stairs = [s for s in self.f.by_type("IfcStair") if s.ObjectType != "fixed ladder"]
        self.assertEqual(len(stairs), 24)
        for s in stairs:
            sb = self.box(s)
            self.assertIsNone(s.Representation, s.Name)
            parts = [p for rel in s.IsDecomposedBy for p in rel.RelatedObjects]
            flights = [p for p in parts if p.is_a("IfcStairFlight")]
            landings = [p for p in parts if p.is_a("IfcSlab") and p.PredefinedType == "LANDING"]
            rails = [p for p in parts if p.is_a("IfcRailing") and p.PredefinedType == "HANDRAIL"]
            self.assertEqual((len(flights), len(landings), len(rails)), (2, 2, 4), s.Name)
            for fl in flights:
                self.assertEqual((fl.NumberOfRisers, fl.NumberOfTreads), (22, 21), s.Name)
                self.assertAlmostEqual(fl.RiserHeight, r, delta=TOL)
                self.assertAlmostEqual(fl.TreadLength, 0.28, delta=TOL)
                lo, hi = self.bounds[fl.GlobalId]
                self.assertAlmostEqual(hi[0] - lo[0], 21 * 0.28, delta=TOL, msg=s.Name)
                self.assertAlmostEqual(hi[2] - lo[2], 21 * r, delta=2 * TOL, msg=s.Name)
                self.assertGreaterEqual(hi[1] - lo[1], 1.118 - TOL)
            for ld in landings:
                lo, hi = self.bounds[ld.GlobalId]
                self.assertGreaterEqual(hi[0] - lo[0], MID_LANDING_MIN - TOL, s.Name)
            for rl in rails:
                v = self.verts[rl.GlobalId]
                lo, hi = v.min(0), v.max(0)
                xm, zm = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
                fl = min(flights, key=lambda f_: abs((self.bounds[f_.GlobalId][0][1] + self.bounds[f_.GlobalId][1][1]) / 2
                                                     - (lo[1] + hi[1]) / 2))
                fv = self.verts[fl.GlobalId]
                flo, fhi = self.bounds[fl.GlobalId]
                z_at_lo = fv[np.abs(fv[:, 0] - flo[0]) < 1e-4][:, 2].max()
                rises_east = z_at_lo < (flo[2] + fhi[2]) / 2
                xb = flo[0] if rises_east else fhi[0]
                nosing = flo[2] + r + abs(xm - xb) * r / 0.28
                top = zm + 0.02 / math.cos(math.atan(r / 0.28))   # the top of a 40 mm rail over its axis
                self.assertGreaterEqual(top - nosing, 0.864 - 0.01, (s.Name, rl.Name))
                self.assertLessEqual(top - nosing, 0.965 + 0.01, (s.Name, rl.Name))
            doors = [d for d in self.f.by_type("IfcDoor") if s.Name.split()[-1] in (d.Name or "")]
            self.assertGreaterEqual(len(doors), 2, s.Name)
            for d in doors:
                db = self.box(d)
                self.assertGreaterEqual(db[0], sb[3] - FLOOR_LANDING - TOL, (s.Name, d.Name))
                self.assertLessEqual(db[3], sb[3] + 0.21, (s.Name, d.Name))
                self.assertTrue(min(abs(db[2]), abs(db[2] - self.cz)) < 0.01, (s.Name, d.Name))

    def test_cores_open_slabs(self):
        for s in [s for s in self.f.by_type("IfcStair") if s.ObjectType != "fixed ladder"] + self.f.by_type("IfcTransportElement"):
            sb = self.box(s)
            for slab in self.f.by_type("IfcSlab") + self.f.by_type("IfcCovering"):
                if slab.PredefinedType not in ("FLOOR", "FLOORING") or slab.ObjectType is not None or slab.GlobalId not in self.B:
                    continue
                bb = self.box(slab)
                if not (sb[2] < bb[2] and sb[5] > bb[5] and G.boxes_overlap((sb[:3], sb[3:]), (bb[:3], bb[3:]))):
                    continue
                ops = [rel.RelatedOpeningElement for rel in slab.HasOpenings]
                ok = False
                for op in ops:
                    lo, hi = self.obounds[op.GlobalId]
                    if lo[0] <= sb[0] + TOL and lo[1] <= sb[1] + TOL and hi[0] >= sb[3] - TOL and hi[1] >= sb[4] - TOL:
                        ok = True
                self.assertTrue(ok, (s.Name, slab.Name))

    # ---------------------------------------------------------------- round things and sections
    def test_round(self):
        for cls, otype in (("IfcPipeSegment", None), ("IfcCableCarrierSegment", "power feeder"), ("IfcMember", "pipe hanger rod"),
                           ("IfcMechanicalFastener", None), ("IfcReinforcingBar", None)):
            els = self.of(cls, otype)
            self.assertTrue(els, cls)
            for e in els:
                pr = profiles(e)
                self.assertTrue(pr, e.Name)
                self.assertTrue(all(p.is_a("IfcCircleProfileDef") for p in pr), (cls, e.Name))
        for e in self.f.by_type("IfcDuctSegment"):
            b = self.box(e)
            d = sorted([b[3] - b[0], b[4] - b[1], b[5] - b[2]])
            if abs(d[0] - d[1]) < 1e-6 and any(abs(d[0] - s) < 1e-6 for s in ROUND_M):
                self.assertTrue(all(p.is_a("IfcCircleProfileDef") for p in profiles(e)), e.Name)
        for e in self.of("IfcCableCarrierSegment", pre="CABLETRAYSEGMENT"):
            self.assertTrue(all(p.is_a("IfcUShapeProfileDef") for p in profiles(e)), e.Name)
        for e in self.of("IfcBeam", otype="roof beam"):
            self.assertTrue(all(p.is_a("IfcIShapeProfileDef") for p in profiles(e)), e.Name)
        for e in self.of("IfcReinforcingBar"):
            n = int(re.match(r"(\d+) bars", uel.get_psets(e)["FabGym_Permit"]["Numbers"]).group(1))
            self.assertEqual(len(G.items(e)), 2 * n, e.Name)

    def test_trusses_and_bracing(self):
        for t in self.of("IfcBeam", otype="roof truss"):
            parts = [p for rel in t.IsDecomposedBy for p in rel.RelatedObjects]
            if parts:
                self.assertIsNone(t.Representation, t.Name)
                self.assertTrue(all(p.is_a("IfcMember") for p in parts), t.Name)
            else:
                self.assertGreaterEqual(len(G.items(t)), 6, t.Name)    # two chords, verticals and diagonals
        for b in self.of("IfcMember", pre="BRACE"):
            pr = profiles(b)
            self.assertEqual(len(pr), 2, b.Name)
            self.assertTrue(all(p.is_a("IfcCircleProfileDef") for p in pr), b.Name)

    # ---------------------------------------------------------------- repeats
    def test_arrays_hold_their_counts(self):
        for cls, otype, word, want in (("IfcFireSuppressionTerminal", "sprinkler array", "heads", 11289),
                                       ("IfcAirTerminal", "fan filter unit array", "units", 38546)):
            counted = 0
            for e in self.of(cls, otype):
                self.assertTrue(G.is_mapped(e), e.Name)
                ib = G.instance_boxes(e)
                self.assertGreater(len(ib), 0, e.Name)
                m = re.match(rf"(\d+) {word}", uel.get_psets(e)["FabGym_Permit"]["Numbers"])
                if m:
                    self.assertEqual(len(ib), int(m.group(1)), e.Name)
                    counted += len(ib)
                b = self.box(e)
                for lo, hi in ib:
                    self.assertTrue(inside(lo, hi, b), e.Name)
                self.assertEqual(G.overlapping(ib), [], e.Name)
            self.assertEqual(counted, want, otype)

    def test_pedestals(self):
        floors = [c for c in self.f.by_type("IfcCovering") if c.PredefinedType == "FLOORING" and c.ObjectType is None]
        peds = [e for e in self.f.by_type("IfcProduct") if e.ObjectType == "raised floor pedestals"]
        self.assertEqual(len(peds), len(floors))
        blockers = [self.box(e) for cls in ("IfcColumn", "IfcWall", "IfcStair", "IfcTransportElement", "IfcPipeSegment",
                                            "IfcDuctSegment", "IfcCableCarrierSegment") for e in self.f.by_type(cls)
                    if e.GlobalId in self.B]
        rf = [fl for fl in self.S["floors"] if fl["name"] == "raised floor"][0]
        blockers = [b for b in blockers if b[2] < rf["z1"] and b[5] > rf["z0"]]
        for p in peds:
            pb = self.box(p)
            ib = G.instance_boxes(p)
            self.assertGreater(len(ib), 10000, p.Name)
            c = (ib[:, 0, :2] + ib[:, 1, :2]) / 2
            off = (c - c[0]) / 0.6
            self.assertLess(np.abs(off - np.round(off)).max(), 1e-3, p.Name)
            grid = math.floor((pb[3] - pb[0]) / 0.6 + 1e-6) * math.floor((pb[4] - pb[1]) / 0.6 + 1e-6)
            self.assertGreater(len(ib), 0.8 * grid, p.Name)
            if blockers:
                Bk = np.array(blockers)
                for k in range(0, len(ib), 2000):
                    ch = ib[k:k + 2000]
                    lo = np.maximum(ch[:, None, 0, :], Bk[None, :, :3])
                    hi = np.minimum(ch[:, None, 1, :], Bk[None, :, 3:])
                    hit = np.all(hi - lo > 1e-4, axis=2)
                    self.assertFalse(hit.any(), (p.Name, ch[np.argwhere(hit)[0][0]].tolist() if hit.any() else None))

    # ---------------------------------------------------------------- fit-out, facade, parapets
    def test_toilets(self):
        parts = self.of("IfcWall", otype="toilet partition")
        mirrors = self.of("IfcFurniture", otype="mirror")
        wcs = self.of("IfcSanitaryTerminal", pre="TOILETPAN")
        lavs = self.of("IfcSanitaryTerminal", pre="WASHHANDBASIN")
        pb = [self.box(p) for p in parts]
        for w in wcs:
            b = self.box(w)
            ok = False
            for ax in (0, 1):
                o = 1 - ax
                beside = [p for p in pb if p[o] < b[o + 3] and p[o + 3] > b[o] and p[2] < b[5]]
                left = any(b[ax] - 0.6 <= p[ax + 3] <= b[ax] + 0.05 for p in beside)
                right = any(b[ax + 3] - 0.05 <= p[ax] <= b[ax + 3] + 0.6 for p in beside)
                ok = ok or (left and right)
            self.assertTrue(ok, w.Name)
        mb = [self.box(m) for m in mirrors]
        for l in lavs:
            b = self.box(l)
            self.assertTrue(any(m[2] >= b[5] - TOL and abs((m[0] + m[3]) / 2 - (b[0] + b[3]) / 2) < 0.3 + (b[3] - b[0]) / 2
                                and abs((m[1] + m[4]) / 2 - (b[1] + b[4]) / 2) < 0.3 + (b[4] - b[1]) / 2 for m in mb), l.Name)

    def test_gowning(self):
        rooms = [r for r in self.P["rooms"] if r["kind"] == "gowning"]
        self.assertTrue(rooms)
        for r in rooms:
            x0, y0, z0, x1, y1, z1 = r["box"]

            def within(e):
                b = self.box(e)
                return b[0] >= x0 - TOL and b[1] >= y0 - TOL and b[3] <= x1 + TOL and b[4] <= y1 + TOL and b[2] >= z0 - TOL

            got = collections.Counter(e.ObjectType for e in self.f.by_type("IfcFurniture") if within(e))
            self.assertGreaterEqual(got["bench"], 1, r["id"])
            self.assertEqual(got["locker"], 8, r["id"])
            self.assertGreaterEqual(got["garment rack"], 1, r["id"])
            shower = [e for e in self.of("IfcUnitaryEquipment", otype="air shower") if within(e)]
            self.assertEqual(len(shower), 1, r["id"])
            door = [d for d in self.f.by_type("IfcDoor") if self.B[d.GlobalId]["key"] == f"permit/door/{r['id']}"]
            self.assertEqual(len(door), 1, r["id"])
            sb, db = self.box(shower[0]), self.box(door[0])
            gap = max(0.0, max(sb[0], db[0]) - min(sb[3], db[3])) + max(0.0, max(sb[1], db[1]) - min(sb[4], db[4]))
            self.assertLess(gap, 3.0, r["id"])

    def test_facade_and_parapets(self):
        facade = [w for w in self.of("IfcWall", pre="SOLIDWALL") if re.match(r"Phase \d fab, (north|south|east|west) wall", w.Name or "")]
        self.assertTrue(facade)
        for w in facade:
            b = self.box(w)
            L = max(b[3] - b[0], b[4] - b[1])
            pr = profiles(w)
            self.assertEqual(len(pr), math.ceil(L / 1.2 - 1e-6), w.Name)
            for p in pr:
                self.assertLessEqual(max(p.XDim, p.YDim), 1.2 + 1e-6, w.Name)
        for w in self.of("IfcWall", pre="PARAPET"):
            depths = sorted(round(it.Depth, 3) for it in G.items(w))
            self.assertEqual(depths, [0.05, 0.95], w.Name)

    # ---------------------------------------------------------------- every element
    def test_inside_its_box(self):
        bad = []
        for e in self.prods:
            if e.GlobalId not in self.B:
                bad.append(("no box", e.is_a(), e.Name))
                continue
            b = self.B[e.GlobalId]["box"]
            if G.is_mapped(e):
                ib = G.instance_boxes(e)
                if not all(inside(lo, hi, b) for lo, hi in ib):
                    bad.append(("repeat outside", e.Name))
            elif e.GlobalId in self.bounds:
                lo, hi = self.bounds[e.GlobalId]
                if not inside(lo, hi, b):
                    bad.append((e.Name, [round(v, 3) for v in lo], [round(v, 3) for v in hi], b))
        self.assertEqual(bad[:10], [])

    def test_materials(self):
        bad = []
        for e in self.prods:
            if e.is_a("IfcSpace"):
                continue
            if uel.get_material(e) is None:
                bad.append(("no material", e.Name))
            its = [x for it in G.items(e) for x in (it.MappingSource.MappedRepresentation.Items if it.is_a("IfcMappedItem") else [it])]
            if not all(x.StyledByItem for x in its):
                bad.append(("no style", e.Name))
        self.assertEqual(bad[:10], [])

    def test_set(self):
        self.assertEqual(self.P["clashes"], [])
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(self.f, logger)
        self.assertEqual([s for s in logger.statements if s.get("level", "").lower() == "error"][:5], [])
        again = self.tmp / "again"
        run("cd", SCENE, LAYOUT, again)
        self.assertEqual(sha(again / "fab-permit.ifc"), sha(self.out / "fab-permit.ifc"))
        run("full", SCENE0, LAYOUT0, self.tmp / "full")
        self.assertEqual(sha(self.tmp / "full" / "fab-permit.ifc"), BEFORE["full"])
        run("dd", SCENE, LAYOUT, self.tmp / "dd")
        self.assertEqual(sha(self.tmp / "dd" / "fab-permit.ifc"), BEFORE["dd"])
        for p in self.out.rglob("*"):
            if p.suffix in (".json", ".ifc"):
                self.assertNotIn("TSMC", p.read_text(), p.name)


if __name__ == "__main__":
    unittest.main()
