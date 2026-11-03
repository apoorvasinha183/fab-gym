"""The hand-drawn silicon film's engine (docs/DRAWN-FILM.md, D1 to D12). Written before the code. Small made-up
drawings stand in for the real ones; no Meta call is made (the client is given a stand-in transport). From the
SMT2020 testbed for the fab's part; the rest is general knowledge.

    python3 -m unittest viz.tests.test_drawn_film      (from the repo root; needs numpy and Pillow)
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    np = None

W, H = 320, 180


def drawings():
    """A plate, a six-drawing glow cycle and two character poses, as RGBA images."""
    d = {}
    # a painted plate that shades across the frame, so a jump of the camera changes most of its pixels
    yy, xx = np.mgrid[0:H + 40, 0:W + 80]
    rgba = np.stack([60 + xx * 0.45, 40 + yy * 0.6, 120 + 0 * xx, 255 + 0 * xx], axis=-1).clip(0, 255).astype("uint8")
    d["plate"] = Image.fromarray(rgba, "RGBA")
    for k in range(6):
        g = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        for x in range(40):
            for y in range(40):
                if (x - 20) ** 2 + (y - 20) ** 2 < (10 + k) ** 2:
                    g.putpixel((x, y), (255, 150 + 15 * k, 60, 255))
        d[f"glow_{k + 1}"] = g
    for name, colour in (("G_a", (251, 241, 230, 255)), ("G_b", (163, 166, 173, 255))):
        c = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
        for x in range(4, 26):
            for y in range(4, 26):
                c.putpixel((x, y), colour)
        d[name] = c
    return d


def sheet(**over):
    s = {"shot": "t-1", "frames": 24, "fps": 24, "palette": "test",
         "levels": [{"name": "plate", "depth": 1.0, "cels": [["plate", 24]], "at": [-40, -20]},
                    {"name": "glow", "depth": 0.8, "cycle": [f"glow_{k}" for k in range(1, 7)], "on": 2, "at": [140, 70]},
                    {"name": "grain", "depth": 0.5, "cels": [["G_a", 12], ["G_b", 12]], "at": [60, 100]}],
         "camera": [[0, {"x": 0, "y": 0, "zoom": 1.0}], [24, {"x": 40, "y": 0, "zoom": 1.0}]],
         "cuts": [], "captions": []}
    s.update(over)
    return s


@unittest.skipIf(np is None, "numpy and Pillow are needed")
class Engine(unittest.TestCase):
    def setUp(self):
        from viz.drawn import compose, sheet as sh
        self.compose, self.sh = compose, sh
        self.d = drawings()

    def test_d1_every_frame_resolves_to_a_drawing(self):
        s = self.sh.load(sheet())
        self.assertEqual(self.sh.validate(s, set(self.d)), [])
        bad = self.sh.load(sheet(levels=sheet()["levels"] + [{"name": "x", "depth": 0.3, "cels": [["nope", 24]]}]))
        errors = self.sh.validate(bad, set(self.d))
        self.assertTrue(errors and any("nope" in e for e in errors), errors)
        short = self.sh.load(sheet(levels=[{"name": "plate", "depth": 1.0, "cels": [["plate", 10]]}]))
        self.assertTrue(self.sh.validate(short, set(self.d)), "a level shorter than the shot leaves frames without a drawing")

    def test_d2_a_held_drawing_is_rendered_once(self):
        r = self.compose.Renderer(self.d, (W, H))
        frames = list(r.frames(self.sh.load(sheet())))
        self.assertEqual(len(frames), 24)
        self.assertEqual(r.rendered, 1 + 6 + 2, "each unique drawing prepared once")

    def test_d3_a_cycle_on_twos_changes_every_second_frame(self):
        s = self.sh.load(sheet())
        seq = [s.at(f)["glow"] for f in range(24)]
        for f in range(0, 24, 2):
            self.assertEqual(seq[f], seq[f + 1])
        self.assertEqual(seq[0], "glow_1")
        self.assertEqual(seq[2], "glow_2")
        self.assertEqual(seq[12], "glow_1", "the cycle repeats")

    def test_d4_nearer_levels_slide_further(self):
        cam = {"x": 40, "y": 0, "zoom": 1.0}
        far = self.compose.offset(1.0, cam)
        near = self.compose.offset(0.5, cam)
        nearest = self.compose.offset(0.0, cam)
        self.assertLess(abs(far[0]), abs(near[0]))
        self.assertLess(abs(near[0]), abs(nearest[0]))

    def test_d5_no_pop_except_at_a_marked_cut(self):
        r = self.compose.Renderer(self.d, (W, H))
        frames = list(r.frames(self.sh.load(sheet())))
        self.assertEqual(self.compose.pops(frames, cuts=[]), [])
        jumpy = sheet(camera=[[0, {"x": 0, "y": 0, "zoom": 1.0}], [11, {"x": 0, "y": 0, "zoom": 1.0}],
                              [12, {"x": 80, "y": 30, "zoom": 1.5}], [24, {"x": 80, "y": 30, "zoom": 1.5}]])
        frames = list(self.compose.Renderer(self.d, (W, H)).frames(self.sh.load(jumpy)))
        self.assertEqual(self.compose.pops(frames, cuts=[]), [12])
        self.assertEqual(self.compose.pops(frames, cuts=[12]), [])

    def test_d6_the_same_sheet_renders_the_same_frames(self):
        def digest():
            h = hashlib.sha256()
            for f in self.compose.Renderer(self.d, (W, H)).frames(self.sh.load(sheet())):
                h.update(np.ascontiguousarray(f).tobytes())
            return h.hexdigest()
        self.assertEqual(digest(), digest())

    @unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg is needed")
    def test_d7_only_the_video_is_written(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            out = tmp / "shot.mp4"
            self.compose.encode(self.compose.Renderer(self.d, (W, H)), self.sh.load(sheet()), out)
            self.assertTrue(out.exists() and out.stat().st_size > 0)
            self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["shot.mp4"])
        finally:
            shutil.rmtree(tmp)


@unittest.skipIf(np is None, "numpy and Pillow are needed")
class Ink(unittest.TestCase):
    def test_d8_colour_lock_keeps_every_painted_pixel_on_the_palette(self):
        from viz.drawn import ink
        palette = [(28, 22, 38), (251, 241, 230), (230, 207, 186), (224, 80, 63)]
        img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        for x in range(40):
            for y in range(40):
                img.putpixel((x, y), (min(255, 240 + x % 7), 236 - y % 5, 222 + (x + y) % 9, 255) if x < 30 else (0, 0, 0, 0))
        out = ink.colour_lock(img, palette)
        self.assertLessEqual(ink.palette_distance(out, palette), 1.0)
        a = np.asarray(out)[..., 3]
        self.assertTrue((a[:, 30:] == 0).all(), "transparent stays transparent")


class Meta(unittest.TestCase):
    def test_d9_the_spend_cap_the_ledger_and_the_cache(self):
        from viz.drawn import meta
        tmp = Path(tempfile.mkdtemp())
        calls = []

        def transport(path, body):
            calls.append((path, body))
            return {"data": [{"b64_json": "aGVsbG8="}]}

        try:
            c = meta.Client(ledger=tmp / "ledger.jsonl", cache=tmp / "cache", cap_usd=0.025, transport=transport)
            a = c.image("Grain, model sheet, front view")
            b = c.image("Grain, model sheet, front view")
            self.assertEqual(a, b)
            self.assertEqual(len(calls), 1, "a repeat is answered from the cache")
            c.image("Grain, gasping")
            with self.assertRaises(meta.OverCap):
                c.image("Grain, grey and alone")
            lines = [json.loads(x) for x in (tmp / "ledger.jsonl").read_text().splitlines()]
            self.assertEqual([round(x["usd"], 3) for x in lines], [0.01, 0.0, 0.01])
            self.assertEqual({x["model"] for x in lines}, {"muse-image-1.0"})
            self.assertAlmostEqual(c.spent(), 0.02)
        finally:
            shutil.rmtree(tmp)


class Words(unittest.TestCase):
    def test_d10_captions_follow_the_word_times(self):
        from viz.drawn import captions
        words = [{"word": "Heat", "start": 0.40, "end": 0.62}, {"word": "it", "start": 0.62, "end": 0.71},
                 {"word": "with", "start": 0.71, "end": 0.90}, {"word": "carbon,", "start": 0.90, "end": 1.40},
                 {"word": "hotter", "start": 1.70, "end": 2.00}, {"word": "than", "start": 2.00, "end": 2.15},
                 {"word": "lava.", "start": 2.15, "end": 2.70}]
        cues = captions.cues(["Heat it with carbon,", "hotter than lava."], words)
        self.assertEqual(len(cues), 2)
        self.assertLessEqual(abs(cues[0]["from"] - 0.40), 1 / 24)
        self.assertLessEqual(abs(cues[1]["from"] - 1.70), 1 / 24)
        self.assertLessEqual(abs(cues[1]["to"] - 2.70), 1 / 24)

    def test_d11_every_caption_is_the_scripts_own_words(self):
        from viz.drawn import captions
        script = (ROOT / "docs/CHIP-FILM.md").read_text()
        self.assertEqual(captions.not_in_script(["Heat it with carbon, hotter than lava, and the carbon steals the oxygen."], script), [])
        self.assertEqual(captions.not_in_script(["Silicon is made of cheese."], script), ["Silicon is made of cheese."])

    def test_d12_the_end_card_names_the_models_and_the_music(self):
        from viz.drawn import endcard
        text = endcard.credits()
        for name in ("Muse Image", "SAM 3.1", "Muse Spark", "Muse Voice Transcribe", "The Budding of Consciousness",
                     "Yoiyami", "New Sunrise", "nene", "CC0", "SMT2020"):
            self.assertIn(name, text)


def blob(canvas, box, colour=(251, 241, 230, 255)):
    """A pose on its own canvas: a filled rounded body at box (x0, y0, x1, y1), the rest clear."""
    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    x0, y0, x1, y1 = box
    a = np.zeros((canvas[1], canvas[0], 4), dtype=np.uint8)
    yy, xx = np.mgrid[0:canvas[1], 0:canvas[0]]
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    m = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0
    a[m] = colour
    return Image.fromarray(a, "RGBA")


@unittest.skipIf(np is None, "numpy and Pillow are needed")
class Poses(unittest.TestCase):
    """Keeping a character steady across drawings made one at a time (docs/DRAWN-FILM.md, D13 to D17)."""

    def setUp(self):
        from viz.drawn import compose, poses, sheet as sh
        self.compose, self.poses, self.sh = compose, poses, sh

    def test_d13_anchors_are_measured_from_the_cut_out(self):
        m = self.poses.measure(blob((100, 100), (30, 20, 70, 80)))
        self.assertLessEqual(abs(m["contact"][0] - 50), 1)
        self.assertLessEqual(abs(m["contact"][1] - 79), 1)
        self.assertLessEqual(abs(m["height"] - 60), 1)
        fx, fy = m["face"]
        self.assertTrue(30 <= fx <= 70 and 20 <= fy <= 60, m)

    def test_d14_swapping_poses_keeps_the_contact_point_and_the_size(self):
        a = blob((100, 100), (30, 20, 70, 80))
        b = self.poses.fit(blob((140, 140), (10, 50, 70, 130)), 60)      # drawn bigger and lower on a larger canvas
        self.assertLessEqual(abs(self.poses.measure(b)["height"] - 60), 1)
        d = {"plate": Image.new("RGBA", (W, H), (0, 0, 0, 255)), "A": a, "B": b}
        anchors = {k: self.poses.measure(v)["contact"] for k, v in (("A", a), ("B", b))}
        s = self.sh.load({"shot": "p", "frames": 4, "fps": 24, "levels": [
            {"name": "plate", "depth": 1.0, "cels": [["plate", 4]]},
            {"name": "grain", "depth": 0.5, "cels": [["A", 2], ["B", 2]], "at": [160, 150]}], "camera": []})
        r = self.compose.Renderer(d, (W, H), anchors=anchors)
        feet = []
        for f in (0, 2):
            fr = r.frame(s, f)
            ys, xs = np.nonzero(fr.sum(-1) > 300)
            low = ys.max()
            feet.append((xs[ys == low].mean(), low))
        self.assertLessEqual(abs(feet[0][0] - feet[1][0]), 1.0)
        self.assertLessEqual(abs(feet[0][1] - feet[1][1]), 1.0)
        self.assertLessEqual(abs(feet[0][1] - 150), 1.0, "the contact point lands where the sheet says")

    def test_d15_a_planted_pose_that_moves_is_reported(self):
        base = {"shot": "p", "frames": 6, "fps": 24, "camera": []}
        moving = self.sh.load(dict(base, levels=[{"name": "grain", "depth": 0.5, "cels": [["stand", 6]],
                                                  "path": [[0, 100, 150], [5, 130, 150]]}]))
        self.assertEqual(self.poses.sliding(moving, planted={"stand"}), [1, 2, 3, 4, 5])
        self.assertEqual(self.poses.sliding(moving, planted={"hop"}), [])
        still = self.sh.load(dict(base, levels=[{"name": "grain", "depth": 0.5, "cels": [["stand", 6]], "at": [100, 150]}]))
        self.assertEqual(self.poses.sliding(still, planted={"stand"}), [])

    def test_d16_the_face_sits_on_the_face_point(self):
        from viz.drawn import faces
        drawings, anchors = faces.face_set(scale=1.0)
        for name in ("eyes_open", "eyes_half", "eyes_shut", "mouth_rest", "mouth_a", "mouth_o", "mouth_e", "mouth_m", "mouth_smile"):
            self.assertIn(name, drawings)
            self.assertIn(name, anchors)
        d = dict(drawings, plate=Image.new("RGBA", (W, H), (233, 211, 181, 255)))
        s = self.sh.load({"shot": "f", "frames": 1, "fps": 24, "levels": [
            {"name": "plate", "depth": 1.0, "cels": [["plate", 1]]},
            {"name": "eyes", "depth": 0.5, "cels": [["eyes_open", 1]], "at": [120, 80]}], "camera": []})
        fr = self.compose.Renderer(d, (W, H), anchors=anchors).frame(s, 0)
        ys, xs = np.nonzero(fr.max(-1) < 60)                     # the dark pupils
        self.assertLessEqual(abs(xs.mean() - 120), 2.0)
        self.assertLessEqual(abs(ys.mean() - 80), 2.0)

    def test_d17_a_tracked_character_moves_smoothly_unless_it_jumps(self):
        from viz.drawn import track
        a = blob((100, 100), (30, 20, 70, 80))
        b = blob((100, 100), (10, 30, 50, 90))                   # the same body drawn somewhere else on its canvas
        d = {"plate": Image.new("RGBA", (W, H), (0, 0, 0, 255)), "A": a, "B": b}
        anchors = {k: self.poses.measure(v)["contact"] for k, v in (("A", a), ("B", b))}
        lv = {"name": "grain", "depth": 0.0, "cels": [["A", 6], ["B", 6]], "path": [[0, 100, 150], [11, 155, 150]]}
        s = self.sh.load({"shot": "t", "frames": 12, "fps": 24, "camera": [],
                          "levels": [{"name": "plate", "depth": 1.0, "cels": [["plate", 12]]}, lv]})
        key = (251, 241, 230)
        pegged = track.centres(self.compose.Renderer(d, (W, H), anchors=anchors).frames(s), key)
        self.assertEqual(track.jumps(pegged, limit=12.0), [])
        # unpegged, the sheet's place is the drawing's corner: keep that corner inside the frame
        lv_loose = dict(lv, path=[[0, 100, 40], [11, 155, 40]])
        s_loose = self.sh.load({"shot": "t", "frames": 12, "fps": 24, "camera": [],
                                "levels": [{"name": "plate", "depth": 1.0, "cels": [["plate", 12]]}, lv_loose]})
        loose = track.centres(self.compose.Renderer(d, (W, H)).frames(s_loose), key)
        self.assertEqual(track.jumps(loose, limit=12.0), [6])


@unittest.skipIf(np is None, "numpy and Pillow are needed")
class Scale(unittest.TestCase):
    """Sizes that make sense (docs/DRAWN-FILM.md, D18) and cel motion (D19)."""

    def test_d18_height_on_screen_follows_real_size_and_perspective(self):
        from viz.drawn import scale
        plate = {"horizon": 300.0, "ref_y": 900.0, "px_per_m": 2000.0}   # 2,000 px a metre where y = 900
        self.assertAlmostEqual(scale.px_per_m(plate, 900.0), 2000.0)
        self.assertAlmostEqual(scale.px_per_m(plate, 600.0), 1000.0, msg="half way to the horizon, half the size")
        self.assertAlmostEqual(scale.height_px(plate, 900.0, 0.10), 200.0, msg="a 10 cm lump")
        self.assertEqual(scale.check(plate, [("grain", 900.0, 0.10, 210.0)]), [])
        self.assertTrue(scale.check(plate, [("grain", 900.0, 0.10, 330.0)]), "a lump drawn 65% too big is named")

    def test_d19_moving_characters_change_drawing_and_inbetweens_sit_between_keys(self):
        from viz.drawn import scale
        base = {"shot": "c", "frames": 12, "fps": 24, "camera": []}
        slid = self.sh_load(dict(base, levels=[{"name": "grain", "depth": 0.2, "cels": [["A", 12]],
                                                "path": [[0, 100, 900], [11, 400, 900]]}]))
        self.assertEqual(scale.sliding_drawings(slid, limit=3), ["grain"])
        drawn = self.sh_load(dict(base, levels=[{"name": "grain", "depth": 0.2,
                                                 "cels": [["A", 2], ["B", 2], ["C", 2], ["D", 2], ["E", 2], ["F", 2]],
                                                 "path": [[0, 100, 900], [11, 400, 900]]}]))
        self.assertEqual(scale.sliding_drawings(drawn, limit=3), [])
        keys = {"k1": {"contact": (50, 100), "height": 100}, "k2": {"contact": (70, 100), "height": 120}}
        self.assertEqual(scale.inbetween_ok(keys["k1"], keys["k2"], {"contact": (60, 100), "height": 110}), True)
        self.assertEqual(scale.inbetween_ok(keys["k1"], keys["k2"], {"contact": (95, 100), "height": 160}), False)

    def sh_load(self, d):
        from viz.drawn import sheet
        return sheet.load(d)


if __name__ == "__main__":
    unittest.main()


class Looks(unittest.TestCase):
    """D20 to D22 (docs/ART-DIRECTION.md, docs/FILM-PLAYBOOK.md): the film's looks are data, the chosen look covers every
    scene's light, and the first cut's prompts are unchanged by the look switch."""

    def setUp(self):
        import json
        from pathlib import Path
        self.root = Path(__file__).resolve().parents[2]
        self.data = json.loads((self.root / "film/drawn/looks.json").read_text())

    def test_d20_every_look_says_how_it_paints_and_has_its_style_pictures(self):
        for name, look in self.data["looks"].items():
            for k in ("name", "plate", "cel", "style_ref", "cel_ref", "colour"):
                self.assertIn(k, look, f"{name} has no {k}")
            for k in ("style_ref", "cel_ref"):
                self.assertTrue((self.root / look[k]).is_file(), f"{name}: {look[k]} is missing")

    def test_d21_the_chosen_look_lights_every_scene(self):
        chosen = self.data["looks"][self.data["chosen"]]
        scenes = sorted(int(p.stem) for p in (self.root / "film/drawn/scenes").glob("*.json"))
        self.assertEqual(sorted(int(k) for k in chosen["colour"]), scenes)

    def test_d22_the_comic_look_keeps_the_first_cuts_prompts_and_folders(self):
        from viz.drawn import pilot, produce, scene
        scene.use("comic")
        self.assertEqual(scene.char(2), scene.CHAR)
        self.assertEqual(scene.backdrop(2), produce.BACKDROP)
        self.assertEqual(scene.plate_text(2, {"prompt": "x"}), pilot.PLATE + "x")
        self.assertEqual(scene.ART, self.root / "data/drawn/scenes")
        scene.use("storybook")
        self.assertIn("lit by", scene.char(2))
        self.assertEqual(scene.ART, self.root / "data/drawn/storybook/scenes")

    def test_d23_every_picture_a_shot_uses_is_directed_so_any_look_can_paint_it(self):
        import json
        for f in sorted((self.root / "film/drawn/scenes").glob("*.json")):
            sc = json.loads(f.read_text())
            known = set(sc.get("plates", {})) | set(sc.get("drawings", {})) | set(sc.get("machines", {})) | {"none"}
            known |= {f"{k}~{i + 1}" for k, p in sc.get("plates", {}).items() for i in range(int(p.get("variants", 0)))}
            known |= {f"{k}@{s}" for k, dd in sc.get("drawings", {}).items() if dd.get("mouths") for s in ("rest", "ah", "ee", "oh", "oo", "ff", "ll", "ss")}
            for shot in sc["shots"]:
                for lv in shot["levels"]:
                    used = [x[0] for x in lv.get("cels", [])] + list(lv.get("cycle", []))
                    self.assertFalse(set(used) - known, f"{shot['id']} {lv['name']}: {sorted(set(used) - known)} not directed")
                for ins in shot.get("insets", []):
                    used = {x[0] for x in ins["cels"]}
                    self.assertFalse(used - known, f"{shot['id']} inset: {sorted(used - known)} not directed")


class Lipsync(unittest.TestCase):
    """D24: a line's mouth shapes come from its letters, are held on twos and fill only the line's own frames."""

    def test_d24_mouths_follow_the_line_and_hold_on_twos(self):
        from viz.drawn import lipsync
        self.assertEqual(lipsync.shapes("I've grown.")[:3], ["ah", "ff", "ee"])
        lines = [{"who": "grain", "from": 1.0, "to": 2.0, "text": "There go my travelling companions!"},
                 {"who": "narrator", "from": 2.0, "to": 3.0, "text": "Not Grain's line."}]
        cels = lipsync.talk([["G", 72]], "G", lines, 0.0, "grain")
        self.assertEqual(sum(k for _, k in cels), 72)
        self.assertEqual(cels[0], ["G", 24])                       # nothing before the line starts at 1 s
        self.assertEqual(cels[-1], ["G", 24])                      # the narrator's line moves no mouth of Grain's
        inner = cels[1:-1]
        self.assertTrue(all(name.startswith("G@") for name, _ in inner))
        self.assertTrue(all(k >= 2 for _, k in inner[:-1]))         # on twos
