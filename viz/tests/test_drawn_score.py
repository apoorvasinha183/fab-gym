"""The drawn film's score and voice-over (docs/DRAWN-FILM.md, M1 to M5, V1 to V3). Written before the code. Made-up
cues and lines stand in for Muse Spark's; no Meta call is made. Standard library only:

    python3 -m unittest viz.tests.test_drawn_score      (from the repo root)
"""

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def cue(**over):
    c = {"cue": "smelt", "from": 22.0, "to": 34.0, "tempo": 120, "meter": [4, 4], "key": "D minor",
         "parts": {"Violin I": [["D5", 2], ["F5", 1], ["A5", 1]] * 6,          # 6 bars of 4/4: 12 s at 120
                   "Tuba": [["D2", 4], ["A1", 4]] * 3,
                   "Timpani": [["D3", 1], ["r", 3], ["A2", 1], ["r", 3]] * 3}}
    c.update(over)
    return c


class Tempo(unittest.TestCase):
    def test_m1_hit_points_fall_on_beats(self):
        from viz.drawn import score
        hits = [23.5, 26.0, 31.0]
        t = score.fit_tempo(22.0, hits, lo=60, hi=160)
        self.assertTrue(60 <= t <= 160, t)
        beat = 60.0 / t
        for h in hits:
            k = round((h - 22.0) / beat)
            self.assertLessEqual(abs(22.0 + k * beat - h), 1 / 24, (t, h))
        self.assertEqual(score.check_hits(22.0, hits, t), [])
        self.assertTrue(score.check_hits(22.0, [23.51 + 0.2], 120), "a hit off the beat is named")


class Score(unittest.TestCase):
    def test_m2_parts_add_up_and_the_cue_lasts_its_length(self):
        from viz.drawn import score
        self.assertEqual(score.check(cue()), [])
        bad = cue(parts=dict(cue()["parts"], Tuba=[["D2", 4]] * 11))
        self.assertTrue(any("Tuba" in e for e in score.check(bad)))
        short = cue(to=40.0)
        self.assertTrue(any("lasts" in e for e in score.check(short)))

    def test_m3_notes_stay_inside_their_instruments(self):
        from viz.drawn import score
        low = cue(parts=dict(cue()["parts"], **{"Violin I": [["C3", 2], ["F5", 1], ["A5", 1]] * 6}))
        errs = score.check(low)
        self.assertTrue(any("Violin I" in e and "C3" in e for e in errs), errs)

    def test_m4_each_cue_becomes_valid_musicxml(self):
        from viz.drawn import score
        xml = score.musicxml(cue())
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, "score-partwise")
        names = [p.findtext("part-name") for p in root.iter("score-part")]
        self.assertEqual(names, ["Violin I", "Tuba", "Timpani"])
        div = int(root.find("part/measure/attributes/divisions").text)
        for part in root.iter("part"):
            ms = part.findall("measure")
            self.assertEqual(len(ms), 6)
            for m in ms:
                total = sum(int(n.findtext("duration")) for n in m.findall("note") if n.find("chord") is None)
                self.assertEqual(total, 4 * div)

    def test_m5_the_orchestra_is_a_full_symphony(self):
        from viz.drawn import score
        full = ["Flute", "Oboe", "Clarinet in B♭", "Bassoon", "Horn in F", "Trumpet in B♭", "Trombone", "Tuba",
                "Timpani", "Harp", "Violin I", "Violin II", "Viola", "Violoncello", "Contrabass"]
        self.assertEqual(score.families_missing(full), [])
        self.assertEqual(score.families_missing(["Violin I", "Flute", "Harp"]), ["brass", "percussion"])
        for name in full:
            self.assertIn(name, score.RANGES)


class Voice(unittest.TestCase):
    shots = [{"id": "2-1", "start": 22.0, "end": 26.0}, {"id": "2-2", "start": 26.0, "end": 30.0}]

    def test_v1_lines_fit_their_shots_and_their_pace(self):
        from viz.drawn import voice
        ok = [{"shot": "2-1", "who": "narrator", "text": "Heat it with carbon, hotter than lava.", "from": 22.3, "to": 25.6}]
        self.assertEqual(voice.check(ok, self.shots), [])
        out = [{"shot": "2-1", "who": "narrator", "text": "Heat it.", "from": 25.0, "to": 27.0}]
        self.assertTrue(voice.check(out, self.shots))
        fast = [{"shot": "2-2", "who": "narrator", "text": " ".join(["word"] * 14), "from": 26.0, "to": 30.0}]
        self.assertTrue(any("words a second" in e for e in voice.check(fast, self.shots)))

    def test_v2_the_narrators_numbers_are_the_scripts(self):
        from viz.drawn import voice
        script = (ROOT / "docs/CHIP-FILM.md").read_text()
        self.assertEqual(voice.numbers_not_in_script(["Silicon melts at about 1,414 °C."], script), [])
        self.assertEqual(voice.numbers_not_in_script(["It melts at 2,000 degrees."], script), ["2,000"])

    def test_v3_grain_and_lou_say_little(self):
        from viz.drawn import voice
        lines = [{"shot": "2-1", "who": "grain", "text": "Hey! Those are my twins!", "from": 22.5, "to": 24.0}] * 9
        self.assertTrue(any("Grain" in e for e in voice.cast_limits(lines)))
        self.assertTrue(any("Lou" in e for e in voice.cast_limits(lines[:2])), "Lou needs at least one line")
        good = lines[:3] + [{"shot": "6-1", "who": "lou", "text": "Simulated from here!", "from": 75, "to": 76.5}]
        self.assertEqual(voice.cast_limits(good), [])


if __name__ == "__main__":
    unittest.main()
