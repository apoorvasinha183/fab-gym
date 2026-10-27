"""The permit-set workflow (docs/PERMIT.md): from the concept model to a schematic set for every trade, with the code
analysis, the readiness ledger, an IFC model and a PDF. Every sheet stays NOT FOR CONSTRUCTION.

    .venv/bin/python viz/permit/run.py --place us [--scene data/layout-real/scene-optimised.json]
        [--layout results/layout-real/layout.json] [--out data/layout-real/permit/us] [--stage concept|full|dd] [--no-pdf]

--stage concept runs only the code analysis on the concept model (no passes): its exit rules fail, as they should.
--stage dd is design development (docs/DESIGN-DEV.md): the place profile's permit.dd block names its scene, layout,
second register, rules, items and judgements; its defaults are the 1.6 m chase layout and data/layout-real-permit.
A place whose profile has no codes read stops. The same input gives the same files byte for byte (not the PDF).
A gigafab-style layout of our own design on the SMT2020 model; not a real fab.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "viz/blueprint"))

import profiles  # noqa: E402
import rules as R  # noqa: E402
from ctx import Ctx, TRUTH  # noqa: E402


def fab_digest(M):
    boxes = [e["box"] for e in M["elements"] if e["cls"] == "IfcBuildingElementProxy" and e["box"]]
    rails = [e["rail"] for e in M["elements"] if e["rail"]]
    return hashlib.sha256(json.dumps([boxes, rails]).encode()).hexdigest()


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, sort_keys=False) + "\n")


def build(scene, layout, out, place="us", stage="full", pdf=True):
    pdata = json.loads((ROOT / "viz/blueprint/places" / f"{place}.json").read_text())
    if "permit" not in pdata:
        raise SystemExit(f"place {place!r}: no codes read for this place; the permit set needs a profile with a codes register")
    prof = profiles.load(place)
    reg = json.loads((ROOT / pdata["permit"]["register"]).read_text())
    rules = json.loads((ROOT / pdata["permit"]["rules"]).read_text())
    items = None
    if stage in ("dd", "cd"):
        dd = pdata["permit"].get("dd")
        if not dd:
            raise SystemExit(f"place {place!r}: no design development block in its profile")
        reg2 = json.loads((ROOT / dd["register"]).read_text())
        reg = {**reg, "sections": {**reg["sections"], **reg2["sections"]}, "not_read": reg2["not_read"],
               "sources": {**reg["sources"], **reg2["sources"]}}
        more = json.loads((ROOT / dd["rules"]).read_text())
        by_id = {r["id"]: r for r in more}
        base_ids = {r["id"] for r in rules}
        rules = [by_id.get(r["id"], r) for r in rules] + [r for r in more if r["id"] not in base_ids]
        items = json.loads((HERE / "items.json").read_text()) + json.loads((ROOT / dd["items"]).read_text())
    if stage == "cd":
        cdb = pdata["permit"]["cd"]
        reg3 = json.loads((HERE / "codes/us-2024-cd.json").read_text())
        reg = {**reg, "sections": {**reg["sections"], **reg3["sections"]}}
        nf = ROOT / cdb["nfpa"]
        if nf.exists():      # NFPA read in the founder's session: its sections in, its documents off the not-read list
            reg4 = json.loads(nf.read_text())
            done = {s["code"].split(" 20")[0] for s in reg4["sections"].values()}
            reg = {**reg, "sections": {**reg["sections"], **reg4["sections"]},
                   "not_read": [n for n in reg["not_read"] if n["id"] not in done]}
        more = json.loads((ROOT / cdb["rules"]).read_text())
        by_id = {r["id"]: r for r in more}
        base_ids = {r["id"] for r in rules}
        rules = [by_id.get(r["id"], r) for r in rules] + [r for r in more if r["id"] not in base_ids]
        items = items + json.loads((ROOT / cdb["items"]).read_text())
    S = json.loads(Path(scene).read_text())
    C = Ctx(S, reg, rules, pdata, prof)
    C.dd = {}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    import arch
    C.P["truth"] = TRUTH
    C.P["status"] = "Schematic for review, NOT FOR CONSTRUCTION"
    C.P["place"] = place
    C.P["jurisdiction"] = pdata["permit"]["jurisdiction"]
    C.P["stage"] = stage
    C.P["fab_digest"] = fab_digest(C.M)
    C.P["layout_sha256"] = hashlib.sha256(Path(layout).read_bytes()).hexdigest()
    C.made.update({"register", "design_data", "lot"})
    arch.run(C, "full" if stage in ("dd", "cd") else stage)
    if stage in ("dd", "cd"):
        import dd_arch
        C.made.add("dd:register")
        dd_arch.pre(C, json.loads(Path(layout).read_text())["assumed"]["chase"])
    if stage == "concept":
        V = R.run_all(rules, C.cases, reg)
        dump(out / "verdicts.json", V)
        dump(out / "permit.json", C.P)
        n = {k: sum(1 for v in V if v["verdict"] == k) for k in ("met", "not met", "cannot say")}
        return f"concept: {len(V)} verdicts, {n}"
    import airfire
    import coord
    import frame
    import ifc
    import ledger
    import utilities
    frame.run(C)
    utilities.run(C)
    airfire.run(C)
    if stage in ("dd", "cd"):
        design_development(C)
    if stage == "cd":
        import cd
        cd.run(C)
    coord.run(C)
    V = R.run_all(rules, C.cases, reg)
    C.made.add("verdicts")
    M = C.model()
    ifc_text = ifc.write(M, "fab-permit.ifc")
    (out / "fab-permit.ifc").write_text(ifc_text)
    C.made.add("ifc")
    for e in C.new:
        C.made.add("ifc:" + e["cls"])
    import sheets
    sheets_written = sheets.write(C, V, out, layout)
    C.made.update("sheet:" + s for s in sheets_written)
    C.made.add("specs")
    L = ledger.build(C, V, items)
    sheets.write_ledger_sheet(C, L, out, layout)
    dump(out / "verdicts.json", V)
    dump(out / "ledger.json", L)
    dump(out / "permit.json", C.P)
    msg = [f"wrote {out}: {len(V)} verdicts, {C.P['elements_added']} elements added, {len(C.P['clashes'])} clashes, "
           f"ledger {L['counts']}"]
    if pdf:
        msg.append(sheets.pdf(out))
    return "\n".join(msg)


def design_development(C):
    """DD3 to DD10 (docs/DESIGN-DEV.md), in an order where each pass places its elements around the ones before."""
    import dd_arch
    import dd_systems
    from dd_place import Index
    X = Index(C)
    dd_arch.chases(C, X)
    dd_arch.judge(C)
    dd_systems.sprinklers(C, X)
    dd_arch.toilets(C, X)
    dd_arch.lifts(C, X)
    dd_systems.gas(C, X)
    dd_systems.exhaust(C, X)
    dd_systems.makeup(C, X)
    dd_systems.showers(C, X)
    dd_systems.electrical(C, X)
    dd_arch.signs_and_lighting(C, X)
    dd_systems.alarms(C, X)
    dd_systems.members(C)
    dd_systems.drains(C)
    dd_arch.walls_and_doors(C)
    dd_arch.firestops(C)
    dd_systems.lod(C)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="us")
    ap.add_argument("--scene", default=None, help="default data/layout-real/scene-optimised.json (dd: the profile's)")
    ap.add_argument("--layout", default=None, help="default results/layout-real/layout.json (dd: the profile's)")
    ap.add_argument("--out", default=None, help="default data/layout-real/permit/<place> (dd: the profile's)")
    ap.add_argument("--stage", default="full", choices=["concept", "full", "dd", "cd"])
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()
    dd = {}
    if a.stage in ("dd", "cd"):
        pm = json.loads((ROOT / "viz/blueprint/places" / f"{a.place}.json").read_text()).get("permit", {})
        dd = dict(pm.get("dd", {}))
        if a.stage == "cd":
            dd["out"] = pm.get("cd", {}).get("out", dd.get("out"))
    scene = a.scene or str(ROOT / dd.get("scene", "data/layout-real/scene-optimised.json"))
    layout = a.layout or str(ROOT / dd.get("layout", "results/layout-real/layout.json"))
    out = a.out or str(ROOT / dd.get("out", f"data/layout-real/permit/{a.place}"))
    print(build(scene, layout, out, a.place, a.stage, pdf=not a.no_pdf))


if __name__ == "__main__":
    main()
