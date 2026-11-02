"""The cinema's floor plan as an SVG, drawn from plan.json (docs/FAB-3D.md, F11), so the sheet and the building never
disagree. From the SMT2020 testbed's campus, our own design; not a real building.

    python3 -m viz.cinema.sheet data/cinema/plan.json data/cinema/check.json OUT.svg
"""

import json
import sys

S = 20.0      # pixels a metre


def svg(p, c):
    x0, y0, x1, y1 = p["footprint"]
    W, H = (x1 - x0) * S + 120, (y1 - y0) * S + 110

    def X(x):
        return 40 + (x - x0) * S

    def Y(y):
        return 50 + (y1 - y) * S

    def rect(b, fill, stroke="none", sw=1, extra=""):
        return (f'<rect x="{X(b[0]):.1f}" y="{Y(b[3]):.1f}" width="{(b[2] - b[0]) * S:.1f}" height="{(b[3] - b[1]) * S:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')

    def text(x, y, s, size=11, fill="#1c2733", anchor="start", weight=400):
        return (f'<text x="{X(x):.1f}" y="{Y(y):.1f}" font-family="IBM Plex Sans, sans-serif" font-size="{size}" '
                f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{s}</text>')

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
           f'aria-label="Floor plan of the cinema generated from rules">',
           f'<rect width="{W:.0f}" height="{H:.0f}" fill="#ffffff"/>',
           rect([x0, y0, x1, y1], "#f7f8fa", "#1c2733", 6)]
    colours = {"hall": "#f2f4f7", "lobby": "#fbf7ef", "front passage": "#eef5ec", "ramp": "#e8f0fa",
               "exit stair": "#f6e9e6", "projection room": "#efeaf6", "toilets": "#eef1f4"}
    for r in p["rooms"]:
        out.append(rect(r["box"], colours.get(r["name"], "#eee"), "#1c2733", 2))
    for ca in p["cross_aisles"]:
        out.append(rect(ca["box"], "#dfe9f3", "#9fb3c8", 1))
    for a in p["aisles"]:
        out.append(rect(a["box"], "#fff4d6", "#d9b66a", 1))
        bx = a["box"]
        out.append(f'<line x1="{X(bx[0]):.1f}" y1="{Y((bx[1] + bx[3]) / 2):.1f}" x2="{X(bx[2]):.1f}" y2="{Y((bx[1] + bx[3]) / 2):.1f}" '
                   f'stroke="#8a6d2c" stroke-width="1.5" stroke-dasharray="4 3"/>')
    for r in p["rows"]:
        out.append(f'<line x1="{X(r["x0"]):.1f}" y1="{Y(p["rooms"][0]["box"][1]):.1f}" x2="{X(r["x0"]):.1f}" '
                   f'y2="{Y(p["rooms"][0]["box"][3]):.1f}" stroke="#e2e6eb" stroke-width="1"/>')
    for s in p["seats"]:
        out.append(f'<rect x="{X(s["x"]) - 5:.1f}" y="{Y(s["y"]) - 5:.1f}" width="10" height="10" rx="2" fill="#a3262a"/>')
    for w in p["wheelchair"]:
        out.append(rect(w["box"], "#1f5fa8", "#123d6e", 1))
        cx, cy = (w["box"][0] + w["box"][2]) / 2, (w["box"][1] + w["box"][3]) / 2
        out.append(text(cx, cy - 0.15, "WC", 9, "#ffffff", "middle", 600))
        a = w["companion_at"]
        out.append(f'<rect x="{X(a[0]) - 5:.1f}" y="{Y(a[1]) - 5:.1f}" width="10" height="10" rx="2" fill="#e3a21a"/>')
    sc = p["screen"]
    out.append(f'<rect x="{X(sc["x"]):.1f}" y="{Y(sc["y_centre"] + sc["width_m"] / 2):.1f}" width="5" height="{sc["width_m"] * S:.1f}" fill="#1f5fa8"/>')
    out.append(text(sc["x"] + 0.5, sc["y_centre"] + 0.1, f'screen {sc["width_m"]:.0f} m', 10, "#1f5fa8"))
    for d in p["doors"]:
        col = "#2f8a4f" if d.get("exit") else "#5d6b7a"
        out.append(f'<circle cx="{X(d["at"][0]):.1f}" cy="{Y(d["at"][1]):.1f}" r="6" fill="{col}" stroke="#ffffff" stroke-width="1.5"/>')
        dy = -0.9 if d["at"][1] > y1 - 1 else 0.7
        out.append(text(d["at"][0], d["at"][1] + dy, d["name"] + (" (exit)" if d.get("exit") else ""), 9.5, col, "middle", 500))
    for r in p["rooms"]:
        b = r["box"]
        if r["name"] in ("hall",):
            continue
        lab = r["name"].upper() + (f" ↗ {r['rises_to']} m" if r.get("rises_to") else "")
        ty = (b[1] + b[3]) / 2 - 0.2 if r["name"] != "exit stair" else b[1] + 1.2
        out.append(text((b[0] + b[2]) / 2, ty, lab, 10.5, "#1c2733", "middle", 600))
    for ca in p["cross_aisles"]:
        b = ca["box"]
        cx, cy = X((b[0] + b[2]) / 2) + 3, Y((b[1] + b[3]) / 2)
        out.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="IBM Plex Mono, monospace" font-size="9" '
                   f'fill="#3d5873" text-anchor="middle" transform="rotate(-90 {cx:.1f} {cy:.1f})">'
                   f'{ca["name"]} · +{ca["level"]} m</text>')
    out.append(text(x0 + 0.2, y0 - 1.4, f'{p["occupants"]} occupants · {c["met"]} rules met · {c["not_met"]} not met · '
                                        f'{c["cannot_say"]} cannot say · 1 : 200 · N ↑', 11, "#5d6b7a"))
    out.append('</svg>')
    return "\n".join(out)


if __name__ == "__main__":
    p = json.load(open(sys.argv[1]))
    c = json.load(open(sys.argv[2]))
    open(sys.argv[3], "w").write(svg(p, c))
    print("sheet ->", sys.argv[3])
