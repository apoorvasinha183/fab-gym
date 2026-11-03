"""Sizes that make sense and cel motion (docs/DRAWN-FILM.md, D18, D19). A plate's ground has a horizon; the pixels a
metre covers fall linearly to nothing at the horizon (a flat ground seen by an upright camera)."""

SIZES_M = {"grain-01-sand": 0.0005, "grain-02-quartz": 0.03, "grain-03-grey": 0.10, "grain-04-wisp": 0.10,
           "grain-05-crystal": 2.0, "grain-06-wafer": 0.30, "grain-07-coach": 0.30, "grain-08-die": 0.01,
           "grain-10-packaged": 0.025, "lou-latency": 1.8}


def px_per_m(plate, y):
    """Pixels a metre covers on the ground at screen row y (the plate's horizon, reference row and its pixels a metre)."""
    h, ry, k = float(plate["horizon"]), float(plate["ref_y"]), float(plate["px_per_m"])
    if ry - h < 150:
        return k            # a front-on stage (the horizon just behind the ground's front): no perspective to speak of
    return max(0.0, k * (y - h) / (ry - h))


def height_px(plate, y, metres):
    return px_per_m(plate, y) * float(metres)


def check(plate, placed, tol=0.15):
    """placed: [(name, feet_y, real_height_m, drawn_height_px)]; the ones more than tol off their real size (D18)."""
    out = []
    for name, y, m, drawn in placed:
        want = height_px(plate, y, m)
        if want <= 0 or abs(drawn - want) / want > tol:
            out.append(f"{name}: {drawn:.0f} px tall where {m} m at row {y:.0f} is {want:.0f} px")
    return out


def sliding_drawings(sheet, limit=3):
    """Levels that move while showing one drawing for more than `limit` frames (cut-out sliding, not cel motion)."""
    out = []
    for lv in sheet.levels:
        run = 0
        for f in range(1, sheet.frames):
            moved = sheet.place(lv, f) != sheet.place(lv, f - 1)
            same = lv.timeline[f] == lv.timeline[f - 1]
            run = run + 1 if (moved and same) else 0
            if run >= limit:
                out.append(lv.name)
                break
    return out


def inbetween_ok(a, b, mid, slack=0.15):
    """An in-between sits between its keys: its contact point and height between theirs (with a little slack)."""
    def between(x, p, q):
        lo, hi = min(p, q), max(p, q)
        pad = max((hi - lo) * slack, 0.02 * abs(x), 2)     # never stricter than 2% of the size
        return lo - pad <= x <= hi + pad
    return (between(mid["contact"][0], a["contact"][0], b["contact"][0])
            and between(mid["contact"][1], a["contact"][1], b["contact"][1])
            and between(mid["height"], a["height"], b["height"]))
