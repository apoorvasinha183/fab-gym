"""Write the building model as IFC4 (docs/BIM.md), with the standard library only.

One project, one site, a building per phase with a storey per level; walls, columns, slabs, coverings, spaces, and
tools, stockers, rails and campus buildings as proxies typed by kind. Every element and space carries FabGym_Basis;
each tool carries FabGym_Tool. Ids are fixed from each element's key, so the file is the same on every run.
Lengths in metres. A gigafab-style layout of our own design on the SMT2020 model; not a real fab.
"""

import math
import uuid

CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"


def guid(key):
    """IFC's 22-character id from a UUID made from the key."""
    n = uuid.uuid5(uuid.NAMESPACE_URL, "fab-gym:" + key).int
    out = []
    for _ in range(22):
        out.append(CHARS[n % 64])
        n //= 64
    return "".join(reversed(out))


def r(v):
    s = f"{v:.6f}".rstrip("0")
    if s in ("-0.", "-"):
        s = "0."
    return s


def s(text):
    t = str(text)
    if not t.isascii():
        raise ValueError(f"IFC text must be ASCII here: {t!r}")
    return "'" + t.replace("\\", "\\\\").replace("'", "''") + "'"


class Step:
    def __init__(self):
        self.lines = []
        self.cache = {}

    def add(self, body):
        self.lines.append(body)
        return f"#{len(self.lines)}"

    def once(self, body):
        if body not in self.cache:
            self.cache[body] = self.add(body)
        return self.cache[body]

    def text(self, name):
        head = ("ISO-10303-21;\nHEADER;\n"
                "FILE_DESCRIPTION(('ViewDefinition [DesignTransferView]'),'2;1');\n"
                f"FILE_NAME({s(name)},'2026-10-27T00:00:00',('Fab Gym'),('Fab Gym'),'Fab Gym blueprint pipeline','viz/blueprint/ifc.py','');\n"
                "FILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n")
        body = "".join(f"#{i + 1}={b};\n" for i, b in enumerate(self.lines))
        return head + body + "ENDSEC;\nEND-ISO-10303-21;\n"


def write(model, name="fab-model.ifc"):
    F = Step()
    O3 = F.once("IFCCARTESIANPOINT((0.,0.,0.))")
    O2 = F.once("IFCCARTESIANPOINT((0.,0.))")
    Z = F.once("IFCDIRECTION((0.,0.,1.))")
    X = F.once("IFCDIRECTION((1.,0.,0.))")
    A3 = F.once(f"IFCAXIS2PLACEMENT3D({O3},{Z},{X})")
    A2 = F.once(f"IFCAXIS2PLACEMENT2D({O2},$)")
    ctx = F.add(f"IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,{A3},$)")
    body = F.add(f"IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Body','Model',*,*,*,*,{ctx},$,.MODEL_VIEW.,$)")
    units = [F.add("IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)"), F.add("IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)"),
             F.add("IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.)"), F.add("IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.)")]
    ua = F.add(f"IFCUNITASSIGNMENT(({','.join(units)}))")
    proj = F.add(f"IFCPROJECT({s(guid('project'))},$,'Fab Gym campus',{s(model['truth'])},$,'Fab Gym campus: concept',"
                 f"{s(model['status'])},({ctx}),{ua})")

    def placement(rel, x=0.0, y=0.0, z=0.0, ref=None):
        if x == 0 and y == 0 and z == 0 and ref is None:
            ax = A3
        else:
            pt = F.add(f"IFCCARTESIANPOINT(({r(x)},{r(y)},{r(z)}))")
            rd = X if ref is None else F.once(f"IFCDIRECTION(({r(ref[0])},{r(ref[1])},0.))")
            ax = F.add(f"IFCAXIS2PLACEMENT3D({pt},{Z},{rd})")
        return F.add(f"IFCLOCALPLACEMENT({rel if rel else '$'},{ax})")

    def solid(xdim, ydim, depth, centre=None):
        if centre is None:
            pos = A2
        else:
            pos = F.once(f"IFCAXIS2PLACEMENT2D({F.once(f'IFCCARTESIANPOINT(({r(centre[0])},{r(centre[1])}))')},$)")
        prof = F.once(f"IFCRECTANGLEPROFILEDEF(.AREA.,$,{pos},{r(xdim)},{r(ydim)})")
        sol = F.add(f"IFCEXTRUDEDAREASOLID({prof},{A3},{Z},{r(depth)})")
        rep = F.add(f"IFCSHAPEREPRESENTATION({body},'Body','SweptSolid',({sol}))")
        return F.add(f"IFCPRODUCTDEFINITIONSHAPE($,$,({rep}))")

    site_pl = placement(None)
    site = F.add(f"IFCSITE({s(guid('site'))},$,'Fab Gym site',{s('Site drawn only outside the fab buildings')},$,{site_pl},$,$,.ELEMENT.,$,$,$,$,$)")
    F.add(f"IFCRELAGGREGATES({s(guid('rel/project-site'))},$,$,$,{proj},({site}))")
    bld_ids, storeys = [], {}
    for b in model["buildings"]:
        pl = placement(site_pl)
        bid = F.add(f"IFCBUILDING({s(guid('bld/' + b['key']))},$,{s(b['name'])},$,$,{pl},$,$,.ELEMENT.,$,$,$)")
        bld_ids.append(bid)
        sts = []
        for fl in model["floors"]:
            spl = placement(pl, z=fl["z0"])
            sid = F.add(f"IFCBUILDINGSTOREY({s(guid('storey/' + b['key'] + '/' + fl['name']))},$,{s(fl['name'])},$,$,{spl},$,$,.ELEMENT.,{r(fl['z0'])})")
            storeys[(len(bld_ids) - 1, fl["name"])] = (sid, spl, fl["z0"])
            sts.append(sid)
        F.add(f"IFCRELAGGREGATES({s(guid('rel/bld-storeys/' + b['key']))},$,$,$,{bid},({','.join(sts)}))")
    F.add(f"IFCRELAGGREGATES({s(guid('rel/site-blds'))},$,$,$,{site},({','.join(bld_ids)}))")

    contained = {}     # storey or site -> element ids
    spaces = {}        # storey -> space ids
    basis = {}         # numbers-from -> element ids
    tool_psets = []
    permit_psets = []  # the permit set's elements (viz/permit): stage, level of development, review, numbers
    rating_psets = []  # design development: a wall's type and fire-resistance rating
    for e in model["elements"]:
        if e["bld"] is None:
            rel_pl, z_ref, holder = site_pl, 0.0, site
        else:
            holder, rel_pl, z_ref = storeys[(e["bld"], e["storey"])]
        if e["rail"] is not None:
            (ax, ay, az), (cx, cy, _) = e["rail"]
            L = math.hypot(cx - ax, cy - ay)
            pl = placement(rel_pl, ax, ay, az - z_ref, ((cx - ax) / L, (cy - ay) / L))
            shape = solid(L, 0.15, 0.1, centre=(L / 2, 0.0))
        else:
            x0, y0, z0, x1, y1, z1 = e["box"]
            pl = placement(rel_pl, (x0 + x1) / 2, (y0 + y1) / 2, z0 - z_ref)
            shape = solid(x1 - x0, y1 - y0, z1 - z0)
        g = s(guid(e["key"]))
        nm = s(e["name"])
        ot = s(e["otype"]) if e["otype"] else "$"
        pre = f".{e['pre']}." if e["pre"] else ".NOTDEFINED."
        if e["cls"] == "IfcSpace":
            eid = F.add(f"IFCSPACE({g},$,{nm},$,$,{pl},{shape},$,.ELEMENT.,{pre},$)")
            spaces.setdefault(holder, []).append(eid)
        elif e.get("door"):
            hgt, wid, op = e["door"]
            eid = F.add(f"IFCDOOR({g},$,{nm},$,{ot},{pl},{shape},$,{r(hgt)},{r(wid)},.DOOR.,.{op}.,$)")
            contained.setdefault(holder, []).append(eid)
        else:
            eid = F.add(f"{e['cls'].upper()}({g},$,{nm},$,{ot},{pl},{shape},$,{pre})")
            contained.setdefault(holder, []).append(eid)
        basis.setdefault(e["from"], []).append(eid)
        if e["tool"]:
            tool_psets.append((e["key"], eid, e["tool"]))
        if e.get("permit"):
            permit_psets.append((e["key"], eid, e["permit"]))
        if e.get("rating"):
            rating_psets.append((e["key"], eid, e["rating"]))
    for n, (holder, ids) in enumerate(contained.items()):
        F.add(f"IFCRELCONTAINEDINSPATIALSTRUCTURE({s(guid(f'rel/contains/{n}'))},$,$,$,({','.join(ids)}),{holder})")
    for n, (holder, ids) in enumerate(spaces.items()):
        F.add(f"IFCRELAGGREGATES({s(guid(f'rel/spaces/{n}'))},$,$,$,{holder},({','.join(ids)}))")
    for n, (frm, ids) in enumerate(basis.items()):
        props = [F.add(f"IFCPROPERTYSINGLEVALUE('Basis',$,IFCTEXT({s(model['truth'])}),$)"),
                 F.add(f"IFCPROPERTYSINGLEVALUE('Status',$,IFCTEXT({s(model['status'])}),$)"),
                 F.add(f"IFCPROPERTYSINGLEVALUE('NumbersFrom',$,IFCTEXT({s(frm)}),$)")]
        ps = F.add(f"IFCPROPERTYSET({s(guid(f'pset/basis/{n}'))},$,'FabGym_Basis',$,({','.join(props)}))")
        F.add(f"IFCRELDEFINESBYPROPERTIES({s(guid(f'rel/basis/{n}'))},$,$,$,({','.join(ids)}),{ps})")
    kinds = {"SceneIndex": "IFCINTEGER", "ToolGroup": "IFCLABEL", "Area": "IFCLABEL", "Kind": "IFCLABEL", "Bay": "IFCINTEGER",
             "Width": "IFCPOSITIVELENGTHMEASURE", "Depth": "IFCPOSITIVELENGTHMEASURE", "Height": "IFCPOSITIVELENGTHMEASURE",
             "LoadPorts": "IFCINTEGER", "SizeSource": "IFCTEXT"}
    for key, eid, tool in tool_psets:
        props = []
        for k, typ in kinds.items():
            v = tool[k]
            val = str(int(v)) if typ == "IFCINTEGER" else (r(v) if "MEASURE" in typ else s(v))
            props.append(F.add(f"IFCPROPERTYSINGLEVALUE('{k}',$,{typ}({val}),$)"))
        ps = F.add(f"IFCPROPERTYSET({s(guid('pset/tool/' + key))},$,'FabGym_Tool',$,({','.join(props)}))")
        F.add(f"IFCRELDEFINESBYPROPERTIES({s(guid('rel/tool/' + key))},$,$,$,({eid}),{ps})")
    pkinds = {"Stage": "IFCLABEL", "LOD": "IFCINTEGER", "Review": "IFCLABEL", "Numbers": "IFCTEXT"}
    for key, eid, pm in permit_psets:
        props = []
        for k, typ in pkinds.items():
            v = pm[k]
            props.append(F.add(f"IFCPROPERTYSINGLEVALUE('{k}',$,{typ}({str(int(v)) if typ == 'IFCINTEGER' else s(v)}),$)"))
        ps = F.add(f"IFCPROPERTYSET({s(guid('pset/permit/' + key))},$,'FabGym_Permit',$,({','.join(props)}))")
        F.add(f"IFCRELDEFINESBYPROPERTIES({s(guid('rel/permit/' + key))},$,$,$,({eid}),{ps})")
    for key, eid, rt in rating_psets:
        props = [F.add(f"IFCPROPERTYSINGLEVALUE('Rating_h',$,IFCREAL({r(rt['Rating_h'])}),$)"),
                 F.add(f"IFCPROPERTYSINGLEVALUE('WallType',$,IFCLABEL({s(rt['WallType'])}),$)"),
                 F.add(f"IFCPROPERTYSINGLEVALUE('Assembly',$,IFCTEXT({s(rt['Assembly'])}),$)"),
                 F.add(f"IFCPROPERTYSINGLEVALUE('Cite',$,IFCLABEL({s(rt['Cite'])}),$)")]
        ps = F.add(f"IFCPROPERTYSET({s(guid('pset/rating/' + key))},$,'FabGym_Rating',$,({','.join(props)}))")
        F.add(f"IFCRELDEFINESBYPROPERTIES({s(guid('rel/rating/' + key))},$,$,$,({eid}),{ps})")
    return F.text(name)
