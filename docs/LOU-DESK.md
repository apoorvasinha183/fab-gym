# Lou's Desktop: the opening page in Lou's voice

Written 4 November 2026, before the tests and the code. The founder: "the opening page should be thought of as Lou's
Desktop ... the layout is fine". Wordings drawn on the real page first; chosen by quiz the same day, all on the recommendation. Only words change; the layout stays.

## Decided

- **Title:** "Morning. I'm Lou. My fab is running late again, so I built it a twin." Above it: "Lou Latency · CEO · his
  desk".
- **The paragraph** names the two Meta models a visitor meets from this page: "This is my desk. My staff are Meta's
  models. Muse Spark Open answers your questions and writes my rules. Muse Wonder takes on anyone who thinks they can do
  my job. The simulator scores every change, and I sign."
- **The first door** is "My in-tray": the four challenges, each tile with one line in Lou's voice under its name, "Four
  problems I haven't solved. Fix one and hit the target. Muse Wonder will try too.", "4 problems · a free build · up to 3
  stars each", and the button "Take problem 1 →".
- **The second door** (Lou's portrait) is "Walk the floor with me", with the button "Show me the floor →".
- **Around the site:** the nav's first link reads "Desk" on every page; the ask bar reads "Ask Lou anything about the
  fab…". The Floor, Build and Evidence keep their plain words.
- **Fine print:** "Lou is a cartoon. His fab starts from the SMT2020 testbed ...".

## Tests (changed before the code)

- `web/tests/frontdoor.test.mjs`: the title, the doors and the nav names (FD), and **LD1** the paragraph names Muse
  Spark Open and Muse Wonder, **LD2** each tile carries a quip, **LD3** the ask bar's placeholder speaks as Lou.
- `web/tests/home.test.mjs` HO3, HO4 and `web/tests/sitecuts.test.mjs`, `web/tests/demopath.test.mjs`: the new door
  names, button and count line.
