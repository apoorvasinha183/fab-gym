#!/usr/bin/env python3
"""A bill of materials read from the faithful BIM (docs/BOM.md).

    .venv/bin/python viz/bim/bom.py --ifc data/layout-real-dd/permit-cd/us/fab-permit.ifc --out DIR

Every shape in the construction-documents IFC is an extruded profile or a placed copy of one, so lengths, volumes
and counts are read from the profiles without meshing. Writes bom.json, bom.csv and bom.md; the same IFC gives the
same bytes. A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab. NOT FOR CONSTRUCTION.
"""

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element as ue

TRUTH = ("From the SMT2020 testbed: quantities counted from the Fab Gym BIM, a gigafab-style layout of our own design. "
         "Not a real fab. NOT FOR CONSTRUCTION. Lengths and volumes are of the modelled shapes (pipes and ducts as "
         "solid sections; the waffle slab, roof deck and filter ceiling as solid layers); no fittings, waste "
         "allowance or prices.")
SKIP = ("IfcSpace", "IfcOpeningElement")
SECTIONS = ["structure", "architecture", "mechanical", "piping", "fire", "electrical", "process equipment", "site"]
SECTION = {
    "IfcFooting": "structure", "IfcColumn": "structure", "IfcBeam": "structure", "IfcMember": "structure",
    "IfcSlab": "structure", "IfcReinforcingBar": "structure", "IfcPlate": "structure", "IfcMechanicalFastener": "structure",
    "IfcWall": "architecture", "IfcDoor": "architecture", "IfcStair": "architecture", "IfcStairFlight": "architecture",
    "IfcRailing": "architecture", "IfcCovering": "architecture", "IfcFurniture": "architecture",
    "IfcSanitaryTerminal": "architecture", "IfcWasteTerminal": "architecture", "IfcBuildingElementPart": "architecture",
    "IfcTransportElement": "architecture",
    "IfcDuctSegment": "mechanical", "IfcAirTerminal": "mechanical", "IfcFan": "mechanical", "IfcFilter": "mechanical",
    "IfcChiller": "mechanical", "IfcUnitaryEquipment": "mechanical",
    "IfcPipeSegment": "piping", "IfcValve": "piping",
    "IfcFireSuppressionTerminal": "fire", "IfcAlarm": "fire", "IfcSensor": "fire",
    "IfcCableCarrierSegment": "electrical", "IfcElectricDistributionBoard": "electrical", "IfcTransformer": "electrical",
    "IfcElectricGenerator": "electrical", "IfcLightFixture": "electrical",
    "IfcBuildingElementProxy": "process equipment",
}
LINEAR = {"IfcPipeSegment", "IfcDuctSegment", "IfcCableCarrierSegment", "IfcBeam", "IfcMember", "IfcColumn",
          "IfcReinforcingBar", "IfcRailing"}
VOLUME = {"IfcFooting", "IfcSlab", "IfcWall", "IfcPlate", "IfcStairFlight", "IfcCovering"}


def mm(v):
    return f"{v * 1000:.0f}"


def area(p):
    """Area of a profile, in square metres."""
    if p.is_a("IfcRectangleProfileDef"):
        return p.XDim * p.YDim
    if p.is_a("IfcCircleProfileDef"):
        return math.pi * p.Radius ** 2
    if p.is_a("IfcIShapeProfileDef"):
        return 2 * p.OverallWidth * p.FlangeThickness + (p.OverallDepth - 2 * p.FlangeThickness) * p.WebThickness
    if p.is_a("IfcUShapeProfileDef"):
        return 2 * p.FlangeWidth * p.FlangeThickness + (p.Depth - 2 * p.FlangeThickness) * p.WebThickness
    if p.is_a("IfcArbitraryClosedProfileDef") and p.OuterCurve.is_a("IfcPolyline"):
        pts = [tuple(c.Coordinates[:2]) for c in p.OuterCurve.Points]
        return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2
    raise SystemExit(f"bom: no area rule for profile {p.is_a()} #{p.id()}")


def signature(p):
    """A profile's size, as a person would read it."""
    if p.is_a("IfcCircleProfileDef"):
        return f"Ø{mm(2 * p.Radius)} mm"
    if p.is_a("IfcRectangleProfileDef"):
        a, b = sorted((p.XDim, p.YDim))
        return f"{mm(a)}×{mm(b)} mm"
    if p.is_a("IfcIShapeProfileDef"):
        return f"I {mm(p.OverallDepth)}×{mm(p.OverallWidth)} mm"
    if p.is_a("IfcUShapeProfileDef"):
        return f"U {mm(p.Depth)}×{mm(p.FlangeWidth)} mm"
    return "custom section"


def material(e):
    m = ue.get_material(e)
    if m is None:
        return ""
    if m.is_a("IfcMaterial"):
        return m.Name
    if m.is_a("IfcMaterialConstituentSet"):
        return ", ".join(sorted({c.Material.Name for c in m.MaterialConstituents}))
    return getattr(m, "Name", "") or m.is_a()


def kind(e):
    """The element's type as the model names it: its ObjectType, else its PredefinedType."""
    ot = getattr(e, "ObjectType", None)
    if ot:
        return ot
    return (getattr(e, "PredefinedType", None) or "").lower().replace("_", " ")


def length_and_section(i):
    """A solid's length along the run and its cross-section. A rectangle's longest dimension is its length, whether
    the model drew it in the profile or as the extrusion depth (ducts, ribs and chords are drawn both ways)."""
    p = i.SweptArea
    if p.is_a("IfcRectangleProfileDef"):
        a, b, c = sorted((p.XDim, p.YDim, i.Depth))
        return c, f"{mm(a)}×{mm(b)} mm"
    return i.Depth, signature(p)


def items(e):
    return [i for r in e.Representation.Representations for i in r.Items]


def line_for(e):
    cls = e.is_a()
    its = items(e)
    mapped = [i for i in its if i.is_a("IfcMappedItem")]
    solids = [i for i in its if i.is_a("IfcExtrudedAreaSolid")]
    typ = kind(e)
    if not mapped and "array" in typ:
        typ += ", blank panel"
    units = len(mapped) or 1
    volume = sum(area(i.SweptArea) * i.Depth for i in solids)
    if mapped:
        unit, qty, size = "each", float(units), ""
    elif cls in LINEAR:
        runs = [length_and_section(i) for i in solids]
        unit, qty = "m", sum(r[0] for r in runs)
        size = " + ".join(sorted({r[1] for r in runs}))
    elif cls in VOLUME and "tile" not in typ:
        unit, qty, size = "m3", volume, ""
    else:
        unit, qty = "each", 1.0
        size = f"{mm(e.OverallWidth)}×{mm(e.OverallHeight)} mm" if cls == "IfcDoor" and e.OverallWidth else ""
    sec = "site" if typ.startswith("campus") else SECTION.get(cls)
    if sec is None:
        raise SystemExit(f"bom: no section for {cls} ({e.Name})")
    return (sec, cls, typ, material(e), size, unit), qty, units, (0.0 if mapped else volume)


def build(ifc_path):
    f = ifcopenshell.open(str(ifc_path))
    groups = {}
    for e in f.by_type("IfcProduct"):
        if not e.Representation or any(e.is_a(s) for s in SKIP):
            continue
        key, qty, units, vol = line_for(e)
        g = groups.setdefault(key, [0.0, 0, 0, 0.0])
        g[0] += qty
        g[1] += 1
        g[2] += units
        g[3] += vol
    order = {s: n for n, s in enumerate(SECTIONS)}
    lines = []
    for key in sorted(groups, key=lambda k: (order[k[0]], k[1], k[2], k[3], k[4], k[5])):
        sec, cls, typ, mat, size, unit = key
        qty, n, units, vol = groups[key]
        lines.append({"section": sec, "class": cls, "type": typ, "material": mat, "size": size, "unit": unit,
                      "quantity": round(qty, 6), "elements": n, "units": units, "volume_m3": round(vol, 6)})
    return lines


def table(lines):
    rows = ["| Section | Class | Type | Material | Size | Quantity | Unit | Elements |", "|---|---|---|---|---|---:|---|---:|"]
    for ln in lines:
        q = f"{ln['quantity']:,.0f}" if ln["unit"] == "each" else f"{ln['quantity']:,.1f}"
        rows.append(f"| {ln['section']} | {ln['class'][3:]} | {ln['type']} | {ln['material']} | {ln['size']} | {q} | "
                    f"{ln['unit']} | {ln['elements']:,} |")
    return "\n".join(rows)


def summary(lines):
    def tot(pred, field="quantity"):
        return sum(ln[field] for ln in lines if pred(ln))
    ffu = lambda l: l["class"] == "IfcAirTerminal" and l["type"].startswith("fan filter unit") and "blank panel" not in l["type"]
    hi = [
        ("Concrete in footings", tot(lambda l: l["class"] == "IfcFooting"), "m³"),
        ("Concrete in floor slabs (waffle slab modelled solid)", tot(lambda l: l["class"] == "IfcSlab" and l["material"] == "concrete"), "m³"),
        ("Concrete columns", tot(lambda l: l["class"] == "IfcColumn" and l["material"] == "concrete"), "m"),
        ("Steel beams, members and braces", tot(lambda l: l["class"] in ("IfcBeam", "IfcMember") and l["material"] == "steel"), "m"),
        ("Walls and partitions", tot(lambda l: l["class"] == "IfcWall"), "m³"),
        ("Pipe", tot(lambda l: l["class"] == "IfcPipeSegment"), "m"),
        ("Duct", tot(lambda l: l["class"] == "IfcDuctSegment"), "m"),
        ("Cable tray and conduit", tot(lambda l: l["class"] == "IfcCableCarrierSegment"), "m"),
        ("Doors and hatches", tot(lambda l: l["class"] == "IfcDoor", "units"), "each"),
        ("Sprinkler heads", tot(lambda l: l["class"] == "IfcFireSuppressionTerminal", "units"), "each"),
        ("Fan filter units", tot(ffu, "units"), "each"),
        ("Raised floor tiles", tot(lambda l: l["class"] == "IfcCovering" and "tile" in l["type"], "units"), "each"),
        ("Raised floor pedestals", tot(lambda l: l["class"] == "IfcBuildingElementPart", "units"), "each"),
        ("Process tools", tot(lambda l: l["section"] == "process equipment" and l["material"] == "tool", "units"), "each"),
    ]
    out = ["| Item | Quantity | Unit |", "|---|---:|---|"]
    for name, q, unit in hi:
        out.append(f"| {name} | {q:,.0f} | {unit} |" if unit == "each" else f"| {name} | {q:,.1f} | {unit} |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ifc", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ifc = Path(a.ifc)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lines = build(ifc)
    doc = {"truth": TRUTH, "source": {"ifc": ifc.name, "sha256": hashlib.sha256(ifc.read_bytes()).hexdigest()},
           "units": {"m": "metres of length", "m3": "cubic metres", "each": "units (each placed copy counts)"},
           "lines": lines}
    (out / "bom.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(lines[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(lines)
    (out / "bom.csv").write_text(buf.getvalue())
    md = [f"# Bill of materials", "", TRUTH, "", f"Source: `{ifc.name}`, SHA-256 `{doc['source']['sha256']}`.", "",
          "## Highlights", "", summary(lines), "", "## All lines", "", table(lines), ""]
    (out / "bom.md").write_text("\n".join(md))
    print(f"wrote {out}: {len(lines)} lines from {sum(l['elements'] for l in lines)} elements, "
          f"{sum(l['units'] for l in lines)} units")


if __name__ == "__main__":
    main()
