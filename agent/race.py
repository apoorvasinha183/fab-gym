"""Race the AI (docs/RACE-AI.md): Muse Wonder plays a Build challenge through the editor's own moves.

The page runs the game: it sends the conversation here, the helper adds the system prompt and the tools and asks the
model, and the page carries out each tool call in the editor, where it shows on the map, is checked, reruns and can be
undone. Nothing here touches the fab; the simulator scores every change. On a teaching fab of our own; not a real fab."""

import json
from pathlib import Path

MODEL = "muse-wonder-1.0"
MAX_MESSAGES = 200
ROLES = {"user", "assistant", "tool"}


def _tool(name, description, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


_XY = {"x": {"type": "integer", "description": "column, 0 at the left"}, "y": {"type": "integer", "description": "row, 0 at the top"}}
TOOLS = [
    _tool("look", "Read the map: the floor's size, every piece (kind, machine group, place, machines), the track with its directions "
          "and broken pieces, the checks, the advice line, the last score, the stars, the target and the budget."),
    _tool("lay_track", "Lay track along a path of neighbouring cells, like dragging with the Track tool. Each step goes one cell "
          "left, right, up or down, and the track runs the way the path goes. Starting on existing track joins it.",
          {"path": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                    "minItems": 1, "description": "cells as [x, y], in order"}}, ["path"]),
    _tool("set_track_direction", "Turn one way out of a track piece on or off. Two ways out make a junction.",
          {**_XY, "dir": {"type": "string", "enum": ["N", "E", "S", "W"]}, "on": {"type": "boolean"}}, ["x", "y", "dir", "on"]),
    _tool("erase", "Remove the track piece or the piece that covers a cell.", dict(_XY), ["x", "y"]),
    _tool("place", "Place a piece with its top-left corner at a cell: a machine group by its area, storage, wafers in or wafers out.",
          {"piece": {"type": "string", "description": "an area name from look, or stocker, entry, exit"}, **_XY}, ["piece", "x", "y"]),
    _tool("set_machines", "Set how many machines a machine group has (each costs its price).",
          {"group": {"type": "string"}, "count": {"type": "integer", "minimum": 1}}, ["group", "count"]),
    _tool("set_when_it_breaks", "Choose what happens when a machine group or a track piece breaks. For a group: as set, "
          "swap_to_spare (with spares) or repair_and_hold_lots. For a track piece at x, y: wait or route_around.",
          {"group": {"type": "string"}, **_XY, "kind": {"type": "string"}, "spares": {"type": "integer", "minimum": 1}}, ["kind"]),
    _tool("set_cars", "Set how many cars run on the track.", {"count": {"type": "integer", "minimum": 1}}, ["count"]),
    _tool("set_cap", "Cap how many lots may be inside the fab at once; 0 means no cap.", {"lots": {"type": "integer", "minimum": 0}}, ["lots"]),
    _tool("run", "Wait for the simulator to rerun the fab with your changes, and read the score, the stars and the advice."),
]

SYSTEM = """You are playing a challenge in Fab Gym's Build page: a small chip fab drawn on a grid, run by a simulator.
Wafers come in, visit machines along the track carried by cars, and go out. Your score is wafers out a day.
A challenge has a target and sometimes a budget. Meeting the target earns one star; beating it by 2% earns two
stars, by 5% three stars. Spending over the budget earns none.

Your moves are tools, the same moves a player has: look, lay_track, set_track_direction, erase, place,
set_machines, set_when_it_breaks, set_cars, set_cap and run. Start with look. Make one small change at a time,
then call run to see what it did. Every change shows on the player's map and can be undone.

With every tool call, write one short sentence saying why, in plain words a player follows. Stop calling tools
when you have three stars or no better idea, and say in one sentence what you did. Never invent numbers: use the
ones look and run give you."""


def validate(messages):
    """None when the conversation is acceptable, else the reason it is refused."""
    if not isinstance(messages, list) or not messages:
        return "messages must be a list of the game's turns"
    if len(messages) > MAX_MESSAGES:
        return f"a game is at most {MAX_MESSAGES} turns"
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in ROLES:
            return "each turn comes from the user, the assistant or a tool"
    return None


def replay(stand_in, messages):
    """The stand-in's reply for this move: the number of model turns so far picks the recorded line."""
    lines = [json.loads(x) for x in (Path(stand_in) / "race.jsonl").read_text().splitlines() if x.strip()]
    k = sum(1 for m in messages if m.get("role") == "assistant")
    return lines[min(k, len(lines) - 1)] if lines else {"role": "assistant", "content": "The stand-in has no recorded game."}
