"""Country profiles for the drawing set (docs/BIM.md): paper, units, scales and building-code topics.

A profile changes how the one building model is drawn and written. It changes nothing in the building: every code
topic is "not checked" until its code is read and cited.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
INCH = 0.0254
FOOT = 0.3048


def f(v, nd=2):
    s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def ftin(m):
    """A length in metres as feet and inches, to the nearest inch: 60 m is 196'-10"."""
    inches = round(m / INCH)
    sign = "-" if inches < 0 else ""
    inches = abs(inches)
    return f"{sign}{inches // 12}'-{inches % 12}\""


class Profile:
    def __init__(self, d):
        self.d = d
        self.id = d["id"]
        self.name = d["name"]
        self.paper = d["paper"]["name"]
        self.w = float(d["paper"]["w_mm"])
        self.h = float(d["paper"]["h_mm"])
        self.imperial = d["units"] == "feet-inches"
        self.scales = d["scales"]
        self.bars = d["scalebars"]
        self.codes = d["codes"]
        self.dxf_unit_m = float(d["dxf"]["unit_m"])
        self.insunits = int(d["dxf"]["insunits"])
        self.dxf_unit = d["dxf"]["unit"]
        self.bar_unit_m = FOOT if self.imperial else 1.0
        self.bar_unit = "ft" if self.imperial else "m"
        self.unit_words = "feet and inches" if self.imperial else "metres"

    def ratio(self, sid):
        return self.scales[sid]["ratio"]

    def scale_label(self, sid):
        return self.scales[sid]["label"]

    def scale_text(self, sid):
        return f"{self.scales[sid]['label']} on {self.paper}"

    def dist(self, m, nd=1):
        """A length with no unit for a dimension line: 60 or 196'-10"."""
        return ftin(m) if self.imperial else f(m, nd)

    def distu(self, m, nd=1):
        """A length with its unit, for running text: 60 m or 196'-10"."""
        return ftin(m) if self.imperial else f"{f(m, nd)} m"

    def size(self, *ms, nd=2):
        """Sizes joined with x: 4.5 x 11 m or 14'-9" x 36'-1"."""
        if self.imperial:
            return " x ".join(ftin(m) for m in ms)
        return " x ".join(f(m, nd) for m in ms) + " m"

    def level(self, z):
        """A level above the support floor slab: +7.50 or EL. +24'-7"."""
        return f"EL. +{ftin(z)}" if self.imperial else f"+{z:.2f}"

    def speed(self, m_per_min):
        """A speed per minute: 60 m/min or 197 ft/min."""
        return f"{f(m_per_min / FOOT, 0)} ft/min" if self.imperial else f"{f(m_per_min)} m/min"

    def units_line(self):
        if self.imperial:
            return f"Units: feet and inches. Elevations above the support floor slab ({self.level(0)})."
        return "Units: metres. Levels above the support floor slab (+0.00)."


def load(pid):
    path = HERE / "places" / f"{pid}.json"
    if not path.exists():
        raise SystemExit(f"no profile {pid!r}; profiles: {', '.join(ids())}")
    return Profile(json.loads(path.read_text()))


def ids():
    return sorted(p.stem for p in (HERE / "places").glob("*.json"))
