"""Construction documents sheets for one bay (docs/CONSTRUCTION-DOCS.md, CD9): the bay's plans for every trade at
1/8 in = 1 ft, its schedules and its details, and the specifications in three parts. Drawn from the same model as the
IFC; every sheet carries the truth line and NOT FOR CONSTRUCTION (the frame in sheets.py).
"""

import blueprint as bp
from blueprint import GREY, INK, RED, Map, line, rect, text
from ctx import FT
from dd_sheets import window
from profiles import f
from sheets import AMBER, BLUE, GREEN, SCALES, boxes, notes, scale_label, table

SHEETS = [
    ("A-110", "Bay 09 floor plan"), ("A-130", "Bay 09 ceiling plan"), ("A-610", "Bay 09 schedules"),
    ("S-110", "Bay 09 framing"), ("S-510", "Structural details and site values"), ("M-110", "Bay 09 sub-fab"),
    ("PP-110", "Bay 09 process piping"), ("E-110", "Bay 09 power"), ("FP-110", "Bay 09 sprinklers"),
    ("FA-110", "Bay 09 alarm and detection"),
]
RATIO = 96


def bay(C):
    D = C.P["cd"]["bay"]
    x0, y0, x1, y1 = D["box"]
    return D, x0, y0, x1, y1


def sel(C, pred):
    return [e for e in C.M["elements"] + C.new if e["box"] is not None and pred(e)]


def plan(C, sid, title, layers, note_lines, table_rows=None, cols=None):
    SCALES[sid] = scale_label(RATIO)
    D, x0, y0, x1, y1 = bay(C)
    ox, oy = bp.AX0 + 10, bp.AY0 + 26
    M = Map(RATIO, x0 - 1, y1 + 1, ox, oy)
    w, h = (x1 - x0 + 2) * 1000 / RATIO, (y1 - y0 + 2) * 1000 / RATIO
    inb = lambda e: e["box"][0] < x1 + 1 and e["box"][3] > x0 - 1 and e["box"][1] < y1 + 1 and e["box"][4] > y0 - 1
    o = [text(bp.AX0 + 10, bp.AY0 + 10, title, 4.2, weight="bold"),
         f'<clipPath id="cl{sid}"><rect x="{f(ox)}" y="{f(oy)}" width="{f(w)}" height="{f(h)}"/></clipPath><g clip-path="url(#cl{sid})">']
    for pred, st, fi, sw in layers:
        o.append(boxes(M, [e["box"] for e in sel(C, lambda e: inb(e) and pred(e))], st, fi, sw))
    o.append("</g>")
    o.append(rect(ox, oy, w, h, INK, 0.3))
    bx, by, bw, bh = M.box(x0, y0, x1, y1)
    o.append(rect(bx, by, bw, bh, RED, 0.25, "none", ' stroke-dasharray="3 1.5"'))
    o.append(text(ox, oy + h + 5, f"Bay 09: {bp.PR.size(x1 - x0, y1 - y0)}, spine at the bottom, perimeter at the top. Red dashes: the bay.", 2.4, fill=GREY))
    tx = ox + w + 20
    yy = oy
    if table_rows:
        t, yy = table(tx, oy, cols, table_rows, 2.4)
        o.append(t)
        yy += 10
    t, _ = notes(tx, yy + 4, note_lines, 2.6, 95, "NOTES")
    o.append(t)
    return "".join(o)


TOOL = (lambda e: (e["key"] or "").startswith("tool/"), GREY, "#eceef1", 0.06)


def a110(C):
    A = C.P["cd"]["arch"]
    cz = C.S["clean_z"]
    tile = lambda e: (e["otype"] or "") == "raised floor tile"
    return plan(C, "A-110", "BAY 09 FLOOR PLAN: raised floor tiles, chase panels, doors (clean floor)", [
        (lambda e: tile(e) and "perforated" not in e["name"], "#c9ced6", "#f7f8fa", 0.03),
        (lambda e: tile(e) and "perforated" in e["name"], BLUE, "#dbe8f7", 0.03),
        TOOL,
        (lambda e: (e["otype"] or "") == "chase partition panel", RED, RED, 0.06),
        (lambda e: e["cls"] == "IfcDoor" and e["box"][2] >= cz - 0.1, GREEN, GREEN, 0.15)],
        [f"{A['tiles']:,} tiles of {A['tile_mm']} mm cover the bay ({A['tile_coverage']:.1%}); {A['perforated']} perforated along the aisle (blue).",
         f"Chase partitions as {A['panels']} panels, the widest {A['max_panel_width_m']} m; tools bulkheaded through (red).",
         "Chase doors (green) at the cross aisle; hardware on A-610.",
         f"Service clearances from each tool's card kept free: {len(C.P['cd']['clearances']['violations'])} elements in them."])


def a130(C):
    A = C.P["cd"]["arch"]["ffu"][0]
    F = C.P["cd"]["fire"]
    return plan(C, "A-130", "BAY 09 CEILING PLAN: fan filter units, sprinkler heads, chase exhaust grilles", [
        (lambda e: (e["otype"] or "") == "fan filter unit", "#5a8f6a", "#e6f4ea", 0.04),
        (lambda e: (e["otype"] or "") == "sprinkler head", RED, RED, 0.2),
        (lambda e: (e["otype"] or "") == "chase exhaust" and e["cls"] == "IfcAirTerminal", AMBER, AMBER, 0.2)],
        [f"{A['units']} fan filter units of 1200 x 600 mm: coverage {A['coverage']:.0%} against {A['target']:.0%} for the bay's class (assumed).",
         f"{F['heads']} sprinkler heads ({F['chase_heads']} in the chases), at most {F['max_spacing_ft']} ft apart and "
         f"{F['max_area_per_head_sqft']} sq ft a head ({F['basis']}).",
         "Chase exhaust grilles at the top of each chase (amber)."])


def s110(C):
    St = C.P["cd"]["structure"]
    return plan(C, "S-110", "BAY 09 FRAMING: columns, base plates, waffle ribs, roof trusses", [
        (lambda e: (e["otype"] or "") == "waffle rib", "#9aa3b2", "#e1e4ea", 0.03),
        (lambda e: e["cls"] == "IfcColumn" and not e["key"].startswith("permit/"), INK, INK, 0.05),
        (lambda e: (e["otype"] or "") == "base plate", RED, "none", 0.2),
        (lambda e: (e["otype"] or "").startswith("truss member") and "chord" in e["name"], BLUE, "none", 0.25)],
        [f"{len(St['columns'])} columns under the bay, each with a base plate and four anchor rods (S-510).",
         f"{St['ribs']} waffle rib pieces at {St['rib_pitch_m']} m, split around every drop through the slab.",
         f"Roof trusses over the bay as chords and verticals ({St['truss_members']} members); diagonals per the truss detail.",
         "Every member preliminary, for licensed review; seismic forces wait for ASCE 7."])


def m110(C):
    S = C.P["cd"]["services"]
    lat = lambda e: "/lat/" in e["key"]
    return plan(C, "M-110", "BAY 09 SUB-FAB: laterals and their hangers", [
        (lambda e: e["cls"] == "IfcColumn" and not e["key"].startswith("permit/"), INK, INK, 0.05),
        (lambda e: lat(e) and e["cls"] == "IfcDuctSegment", AMBER, "#fbefd9", 0.08),
        (lambda e: lat(e) and e["cls"] == "IfcPipeSegment", BLUE, "none", 0.08),
        (lambda e: lat(e) and e["cls"] == "IfcCableCarrierSegment", RED, "none", 0.08),
        (lambda e: (e["otype"] or "") == "pipe hanger rod", INK, INK, 0.3)],
        [f"{S['hangers']} hanger rods from the waffle slab, the widest spacing {S['max_hanger_spacing_m']} m (2.4 m largest, assumed; "
         "MSS SP-58 not read).",
         "Amber: exhaust ducts. Blue: process pipes and drains. Red: cable trays."])


def pp110(C):
    S = C.P["cd"]["services"]
    rows = []
    for i, g in sorted(S["tools"].items(), key=lambda kv: int(kv[0]))[:30]:
        rows.append([i, C.S["tools"][int(i)]["kind"], len(g["drops"]), len(g["valves"]), "yes" if g["feeder"] else "no",
                     ", ".join(g["gas_lines"]) or "none"])
    return plan(C, "PP-110", "BAY 09 PROCESS PIPING: a drop and a valve per utility per tool", [
        TOOL,
        (lambda e: (e["otype"] or "") == "tool drop" and e["cls"] == "IfcPipeSegment", BLUE, BLUE, 0.05),
        (lambda e: (e["otype"] or "") == "tool drop" and e["cls"] == "IfcDuctSegment", AMBER, AMBER, 0.05),
        (lambda e: (e["otype"] or "") == "isolation valve", RED, "none", 0.1)],
        [f"{S['valves']} isolation valves under the waffle slab, one on every pipe drop; exhaust drops take no valve and no damper.",
         "Gas lines: the bay's scanners and tracks draw no hazardous gas, so none are drawn here.",
         "Pipe sizes by each tool's own flow at the velocity limits of D6 (assumed)."],
        rows, [("Tool", 12), ("Kind", 20), ("Drops", 14), ("Valves", 14), ("Feeder", 14), ("Gas lines", 24)])


def e110(C):
    F = C.P["cd"]["services"]["feeders"]
    rows = [[i, f"{v['kva']:g}", f"{v['amps_125pct']:.0f}", v["conductor"]] for i, v in sorted(F.items(), key=lambda kv: int(kv[0]))]
    return plan(C, "E-110", "BAY 09 POWER: a feeder to every tool", [
        TOOL,
        (lambda e: (e["otype"] or "") == "power feeder", RED, RED, 0.1),
        (lambda e: e["cls"] == "IfcElectricDistributionBoard", INK, "#f3d1cf", 0.2)],
        ["Feeders at 480 V, three phase, at 125% of the tool's load as continuous (NFPA 70-2023 215.2(A)(1)), copper from the "
         "75 C column of Table 310.16 (terminals rated 75 C, assumed).", "Fault current, overcurrent protection and hazardous "
         "locations are not checked. The bay's panelboards on E-602."],
        rows, [("Tool", 12), ("kVA", 14), ("A x 1.25", 18), ("Conductor", 28)])


def fp110(C):
    F = C.P["cd"]["fire"]
    return plan(C, "FP-110", "BAY 09 SPRINKLERS: heads and branch lines", [
        TOOL,
        (lambda e: (e["otype"] or "") == "sprinkler branch line", BLUE, "none", 0.15),
        (lambda e: (e["otype"] or "") == "sprinkler head", RED, RED, 0.3)],
        [f"{F['heads']} heads in three rooms: the bay between its chase partitions and the two chases (the partitions reach "
         "within the top 15% of the ceiling, so each is a wall).",
         f"At most {F['max_spacing_ft']} ft apart (15 asked), {F['max_area_per_head_sqft']} sq ft a head (130), {F['max_wall_distance_ft']} ft "
         f"from a wall (7.5), at least {F['min_between_ft']} ft apart (6): NFPA 13-2022 Table 10.2.4.2.1(b) and 10.2.5.",
         f"Design density {F['density']['gpm_sqft']} gpm/sq ft over {F['density']['area_sqft']:,} sq ft for ordinary hazard group 2 "
         "(Table 19.2.3.1.1). Branch and main sizes wait for the site's water supply: the bay is over 5,000 sq ft (19.2.2.3), "
         "so a water supply test and a hydraulic calculation decide them.",
         "Fire protection shop drawings follow (107.2.2), by the installing contractor."])


def fa110(C):
    F = C.P["cd"]["fire"]
    return plan(C, "FA-110", "BAY 09 ALARM AND DETECTION: sampling points, the bay's detector and horn", [
        TOOL,
        (lambda e: (e["otype"] or "") == "sampling point", GREEN, GREEN, 0.3),
        (lambda e: e["cls"] == "IfcSensor" and "smoke" in (e["name"] or "").lower(), RED, RED, 0.3),
        (lambda e: e["cls"] == "IfcAlarm", AMBER, AMBER, 0.3)],
        [f"{F['sampling_points']} sampling ports ({F['chase_ports']} in the chases) on the bay's air-sampling detector, at most "
         f"{F['max_port_spacing_ft']} ft apart and {F['max_port_wall_ft']} ft from a wall: each port spaced as a spot detector, 30 ft "
         "nominal (NFPA 72-2022 17.7.4.6, 17.7.4.2.3.1).",
         "Transport time from the farthest port at most 120 s, by the maker's calculation; horn and strobe layout per NFPA 72 "
         "chapter 18, not checked."])


def a610(C):
    A = C.P["cd"]["arch"]
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "BAY 09 SCHEDULES: raised floor, chase panels, door hardware", 4.2, weight="bold")]
    rows = [["solid", A["tiles"] - A["perforated"], "600 x 600 mm, conductive, 1,500 kg point load (assumed)"],
            ["perforated", A["perforated"], "600 x 600 mm, 25% open, dampers for balancing (assumed)"]]
    t, y = table(bp.AX0 + 10, bp.AY0 + 18, [("Tiles", 30), ("Count", 18), ("Specification", 120)], rows, 2.6)
    o.append(t)
    rows = [["WT-C panels", A["panels"], f"at most {A['max_panel_width_m']} m wide, cleanroom panel on steel studs, unrated"]]
    t, y = table(bp.AX0 + 10, y + 10, [("Chase partitions", 30), ("Count", 18), ("Specification", 120)], rows, 2.6)
    o.append(t)
    rows = [["chase door", A["door_hardware"]]]
    t, _ = table(bp.AX0 + 10, y + 10, [("Door", 30), ("Hardware set", 200)], rows, 2.6)
    o.append(t)
    return "".join(o)


def s510(C):
    St, site = C.P["cd"]["structure"], C.P["cd"]["site"]
    s = site["seismic"]
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "STRUCTURAL DETAILS AND SITE VALUES", 4.2, weight="bold")]
    rows = [["1. Risk category", "IV (the stricter reading, assumed)"], ["2. Importance factor Ie", f"{s['importance_factor']}"],
            ["3. SS and S1", f"{s['ss']} g, {s['s1']} g"], ["4. Site class", s["site_class"]],
            ["5. SDS and SD1", f"{s['sds']} g, {s['sd1']} g"], ["6. Seismic design category", s["sdc"]]] + \
           [[f"{n}. {x}", "cannot say: ASCE 7 not read"] for n, x in zip(range(7, 12), site["not_shown"])]
    t, y = table(bp.AX0 + 10, bp.AY0 + 18, [("Earthquake design data (1603.1.5)", 70), ("Value", 70)], rows, 2.6)
    o.append(t)
    o.append(text(bp.AX0 + 10, y + 6, f"{site['region']}, a point near Salem at {site['point']['lat']} N, {-site['point']['lon']} W "
                                      "(rounded; no parcel). " + s["basis"] + ".", 2.4, fill=GREY))
    o.append(text(bp.AX0 + 10, y + 11, f"Wind {site['wind']['value']} mph and snow {site['snow']['value']} psf assumed: "
                                       + site["wind"]["why"] + ".", 2.4, fill=GREY))
    rows = [[ft["id"].replace("permit/footing/", ""), f"{ft['load_kN']:,.0f}", f"{ft['side_m']:.2f}", f"{ft['as_needed_mm2']:,}",
             f"{ft['bars']} x {ft['bar_mm']} mm", f"{ft['as_provided_mm2']:,}"] for ft in St["footings"]]
    t, _ = table(bp.AX0 + 10, y + 20, [("Footing", 50), ("Load kN", 18), ("Side m", 16), ("As needed mm2", 26), ("Bars each way", 26),
                                       ("As provided", 22)], rows, 2.4)
    o.append(t)
    # base plate detail
    dx, dy = bp.AX0 + 420, bp.AY0 + 30
    o.append(text(dx, dy - 6, "DETAIL 1: base plate and anchor rods, plan and section (diagrammatic)", 3.0, weight="bold"))
    o.append(rect(dx, dy, 70, 70, INK, 0.3, "#f1efe8"))
    o.append(rect(dx + 20, dy + 20, 30, 30, INK, 0.3, "#30343c"))
    for ax, ay in ((10, 10), (60, 10), (10, 60), (60, 60)):
        o.append(f'<circle cx="{f(dx + ax)}" cy="{f(dy + ay)}" r="2" fill="none" stroke="{RED}" stroke-width="0.3"/>')
    sx = dx + 100
    o.append(rect(sx, dy, 80, 4, INK, 0.3, "#f1efe8"))
    o.append(rect(sx + 25, dy - 30, 30, 30, INK, 0.3, "#30343c"))
    o.append(rect(sx - 10, dy + 4, 100, 50, INK, 0.3, "#e9e3d7"))
    for ax in (8, 72):
        o.append(line(sx + ax, dy - 2, sx + ax, dy + 34, RED, 0.5))
    o.append(line(sx - 5, dy + 48, sx + 85, dy + 48, BLUE, 0.6, "2 1"))
    o.append(text(sx + 40, dy + 62, "700 x 700 x 40 mm plate, 4 rods 25 mm, bottom mat (assumed)", 2.2, "middle", fill=GREY))
    # truss joint
    tx, ty = dx, dy + 110
    o.append(text(tx, ty - 6, "DETAIL 2: truss panel point (diagrammatic)", 3.0, weight="bold"))
    o.append(rect(tx, ty, 160, 6, BLUE, 0.3, "#dbe6f5"))
    o.append(rect(tx, ty + 50, 160, 6, BLUE, 0.3, "#dbe6f5"))
    for vx in (20, 80, 140):
        o.append(rect(tx + vx, ty + 6, 4, 44, BLUE, 0.3, "#dbe6f5"))
    o.append(line(tx + 24, ty + 50, tx + 80, ty + 6, BLUE, 0.6))
    o.append(line(tx + 84, ty + 6, tx + 140, ty + 50, BLUE, 0.6))
    o.append(text(tx + 80, ty + 66, "chords, verticals every 3 m, diagonals; gusset plates by the engineer", 2.2, "middle", fill=GREY))
    t, _ = notes(dx, ty + 80, ["Every size here is preliminary and assumed, for licensed review: plates, rods, bars and members.",
                               "Concrete and steel grades, cover, laps and welds follow ACI 318 and AISC 360, not read."], 2.6, 90, "NOTES")
    o.append(t)
    return "".join(o)


BODIES = {"A-110": a110, "A-130": a130, "A-610": a610, "S-110": s110, "S-510": s510, "M-110": m110, "PP-110": pp110,
          "E-110": e110, "FP-110": fp110, "FA-110": fa110}


def specs_cd(C):
    """Three-part sections for the bay's work: products by kind and performance, never by maker."""
    A, St, Sv, F = C.P["cd"]["arch"], C.P["cd"]["structure"], C.P["cd"]["services"], C.P["cd"]["fire"]
    secs = [
        ("03 30 00", "Cast-in-place concrete (bay 09 footings and waffle slab)",
         ["Submittals: mix designs, reinforcement shop drawings. Quality: ACI 318 (not read; licensed review)."],
         [f"Concrete as the engineer specifies (assumed 35 MPa); reinforcing bars 20 mm, fy {420} MPa (assumed); "
          f"{len(St['footings'])} footing mats per S-510."],
         ["Place bottom mats with 75 mm cover; form the waffle ribs at 1.5 m; leave sleeves for every drop shown on PP-110."]),
        ("05 12 00", "Structural steel framing (bay 09 trusses, base plates)",
         ["Submittals: shop drawings and connection calculations by the fabricator's engineer."],
         [f"Base plates 700 x 700 x 40 mm, four 25 mm anchor rods each ({len(St['columns'])} columns); truss chords and verticals by "
          "required properties (S-601)."],
         ["Set anchor rods with templates; grout under plates; erect trusses to the plumb and camber the engineer gives."]),
        ("09 69 00", "Access flooring (bay 09)",
         ["Submittals: tile and pedestal data, load tests, conductivity."],
         [f"{A['tiles']:,} tiles of 600 x 600 mm, conductive; {A['perforated']} perforated tiles 25% open with balancing dampers."],
         ["Install level within the tolerance the cleanroom asks; cut tiles around every drop with sealed edges."]),
        ("13 21 00", "Cleanroom partitions and fan filter units (bay 09)",
         ["Submittals: panel and unit data, filter test reports. Cleanliness per ISO 14644-1 (not read)."],
         [f"{A['panels']} chase partition panels at most 1.2 m wide; {A['ffu'][0]['units']} fan filter units of 1200 x 600 mm, H14 filters."],
         ["Seal tool bulkheads; leak-test filters in place; certify the bay's class after installation."]),
        ("21 13 13", "Wet-pipe sprinkler systems (bay 09)",
         ["Submittals: shop drawings and hydraulic calculations (107.2.2); NFPA 13 governs (not read)."],
         [f"{F['heads']} quick-response pendent heads on an assumed {F['spacing_m']} m grid; branch lines per FP-110."],
         ["Hang and brace per NFPA 13; test hydrostatically before the ceiling closes."]),
        ("22 11 00", "Process piping and tool drops (bay 09)",
         ["Submittals: materials by utility, weld procedures for high-purity lines."],
         [f"A drop per utility per tool, {Sv['valves']} lockable ball valves; hangers at most 2.4 m apart ({Sv['hangers']} rods)."],
         ["Purge and test every line; label each drop by utility and tool."]),
        ("26 05 19", "Low-voltage conductors (bay 09 tool feeders)",
         ["Submittals: conductor data; NFPA 70 governs (not read)."],
         ["Copper feeders at 480 V three phase per E-110, sized on an assumed table."],
         ["Pull, terminate and megger-test each feeder; label at both ends."]),
        ("28 31 00", "Fire detection and alarm (bay 09)",
         ["Submittals: device data and layout; NFPA 72 governs (not read)."],
         [f"Air-sampling detector with {F['sampling_points']} sampling points; horn and strobe at the bay's perimeter end."],
         ["Commission with smoke tests at each sampling point; record transport times."]),
    ]
    md = ["", "# Bay 09: specifications in three parts", "",
          "Construction documents for lithography bay 09. On the SMT2020 model. A layout of our own design. Not a real fab. "
          "NOT FOR CONSTRUCTION. Products by kind and performance, never by maker; every number assumed unless cited.", ""]
    for num, title, p1, p2, p3 in secs:
        md += [f"## Section {num} {title}", "", "### Part 1 General", ""] + [f"- {x}" for x in p1] + \
              ["", "### Part 2 Products", ""] + [f"- {x}" for x in p2] + ["", "### Part 3 Execution", ""] + [f"- {x}" for x in p3] + [""]
    return "\n".join(md) + "\n"
