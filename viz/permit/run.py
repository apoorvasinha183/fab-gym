"""The permit-set workflow (docs/PERMIT.md): from the concept model to a schematic set for every trade, with the code
analysis, the readiness ledger, an IFC model and a PDF. Every sheet stays NOT FOR CONSTRUCTION.

    .venv/bin/python viz/permit/run.py --place us [--scene data/layout-real/scene-optimised.json]
        [--layout results/layout-real/layout.json] [--out data/layout-real/permit/us] [--stage concept|full] [--no-pdf]

--stage concept runs only the code analysis on the concept model (no passes): its exit rules fail, as they should.
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
    S = json.loads(Path(scene).read_text())
    C = Ctx(S, reg, rules, pdata, prof)
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
    arch.run(C, stage)
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
    L = ledger.build(C, V)
    sheets.write_ledger_sheet(C, L, out, layout)
    dump(out / "verdicts.json", V)
    dump(out / "ledger.json", L)
    dump(out / "permit.json", C.P)
    msg = [f"wrote {out}: {len(V)} verdicts, {C.P['elements_added']} elements added, {len(C.P['clashes'])} clashes, "
           f"ledger {L['counts']}"]
    if pdf:
        msg.append(sheets.pdf(out))
    return "\n".join(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="us")
    ap.add_argument("--scene", default=str(ROOT / "data/layout-real/scene-optimised.json"))
    ap.add_argument("--layout", default=str(ROOT / "results/layout-real/layout.json"))
    ap.add_argument("--out", default=None, help="default data/layout-real/permit/<place>")
    ap.add_argument("--stage", default="full", choices=["concept", "full"])
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()
    out = a.out or str(ROOT / "data/layout-real/permit" / a.place)
    print(build(a.scene, a.layout, out, a.place, a.stage, pdf=not a.no_pdf))


if __name__ == "__main__":
    main()
