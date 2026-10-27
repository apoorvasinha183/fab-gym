"""What the permit passes share: the scene, the concept model, the register, the cards, and the new elements.

Every element a pass adds carries the concept model's fields plus `permit` (stage, level of development, review,
its numbers), so the IFC, the sheets and the ledger read one list.
"""

import json
from pathlib import Path

import model as bmodel

FT = 0.3048
IN = 0.0254
SQFT = FT * FT
CFM = 0.000471947      # m3/s in one cfm
TRUTH = bmodel.TRUTH
STATUS = "Schematic for review, NOT FOR CONSTRUCTION"
HERE = Path(__file__).resolve().parent


class Ctx:
    def __init__(self, S, reg, rules, place, profile):
        self.S = S
        self.M = bmodel.build(S)
        self.reg = reg
        self.rules = rules
        self.place = place
        self.profile = profile
        self.permit = place["permit"]
        self.cards = {k: json.loads((HERE / "tool-cards" / f"{k}.json").read_text()) for k in S["kinds"]}
        self.fl = {f["name"]: f for f in S["floors"]}
        self.blds = [bmodel.building(S, p) for p in (0, 1)]
        self.keys = ["P1", "P2"]
        self.new = []
        self.P = {}
        self.cases = {}          # rule id -> [(scope, inputs)]
        self.grids = {}          # drawings only: walking distances, never written to permit.json
        self.made = set()

    def fact(self, sec, k):
        return self.reg["sections"][sec]["facts"][k]

    def add(self, key, cls, name, box, bld, storey, pre, otype=None, frm="assumed", lod=200, stage="D4",
            review="schematic", numbers="", door=None):
        e = {"key": "permit/" + key, "cls": cls, "name": name, "box": tuple(round(v, 4) for v in box), "bld": bld,
             "storey": storey, "otype": otype, "pre": pre, "from": frm, "tool": None, "rail": None, "door": door,
             "permit": {"Stage": stage, "LOD": lod, "Review": review, "Numbers": numbers}}
        self.new.append(e)
        return e

    def case(self, rule, scope, **inputs):
        self.cases.setdefault(rule, []).append((scope, inputs))

    def tools_in(self, p):
        return [(i, t) for i, t in enumerate(self.S["tools"]) if bmodel.phase_of_x(self.S, t["x0"]) == p]

    def model(self):
        m = dict(self.M)
        m["status"] = STATUS
        m["elements"] = self.M["elements"] + self.new
        return m
