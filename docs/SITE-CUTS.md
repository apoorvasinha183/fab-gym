# Fewer doors: the site's cuts and merges

Written 31 October 2026, before the tests and the code. From the whole-site audit "Every page, every tab" and the founder's answers the same day
(`~/HACKATHON-README.md`): the cuts and merges first, then the bugs; no story on the site (the founder shows it as a
movie in the Godot building); the nav becomes Home · Floor · Build · Evidence. From the SMT2020 testbed; not a real fab.

## Why

The floor's first screen showed 21 controls, an 18-item key, four numbers and five panel tabs; "Ask" could be reached
four ways and an answer appeared in three places; the study results sat in two drawers of the floor. Apple's test: does
it need to exist, and does it need to exist now?

## What changes

**Everywhere**
1. The nav on both pages: Home · Floor · Build · Evidence (`index.html`, `index.html#floor`, `editor.html`,
   `index.html#evidence`). "Ask" leaves the nav; `#ask` links still open the floor with the answer panel.
2. A tab icon on both pages (an inline SVG), so no page asks for a missing `favicon.ico`.

**Home**
3. "or explore the floor" goes: the nav's Floor does it. The two doors stay.

**Floor**
4. The view bar (Live, Queues, Prototypes, Routes) goes. Live is the floor; one button, "Follow one lot", takes its
   place: it opens the route view and follows a lot, as Routes → Follow did, and reads "Back to the floor" while it
   does. A "Show prototypes" button stands beside it only while prototype lots are in the fab (today the Prototypes
   view sat there disabled). The Queues view's glow goes; each group's pods already show its line.
5. Two numbers stay at the top: lots finished and lots waiting. "Deliveries, last hour" and "machines busy" go (each
   group's hover card already says how many of its machines are working).
6. The key shows three marks (working, broken down, a lot of 25 wafers) and a "More about the marks" disclosure, closed,
   holding the rest (the other states, the moods, urgent and prototype lots, +N and Holding).
7. One speed button cycles 1× → 3× → 12× in place of three.
8. The panel rail holds two buttons: "Try a change" and "?" (the glossary). The Ask, Numbers and Results tabs go.
   Asking from the bar still opens the answer in the panel, without a tab of its own; words linked in notes still open
   their glossary article.

**Evidence** (`index.html#evidence`, a page of its own)
9. Everything we found, in one place: the long WIP-cap study (from Numbers), the prototype money table (from Numbers)
   and the results list with its search and filters (from Results).

**Build**
10. The Run and Build mode buttons go: editing no longer stops the run, so the modes mean nothing.
11. Three score cards: wafers out a day, days a wafer takes, extra spend. "Longest line" and "jammed track pieces" go
    (the map shows both).
12. "The lots right now" (twelve tiles, most reading 0) goes.

Bugs and copy (the empty waiting chart, "0 waiting" at a run's end, stale results, small text, a flat view in Build,
candidate names, one answer card) are the next step, not this one.

## Tests (written before the code), `web/tests/sitecuts.test.mjs`

In Node, on the pages' files:
- **K1** the nav on both pages is Home, Floor, Build, Evidence with those links.
- **K2** both pages declare a tab icon.
- **K3** Home has its two doors and no "or explore the floor".
- **K4** the floor has no view bar, a "Follow one lot" button and a hidden "Show prototypes" button, two numbers (lots finished, lots waiting), a key of three
  marks and a closed "More about the marks", one speed button, and a rail of exactly "Try a change" and "?".
- **K5** Build has no mode buttons and no "lots right now"; its score is three cards.

In headless Chrome with a helper of its own in quick mode (skipped without Google Chrome):
- **K6** the floor's first screen has at most 13 controls (it had 21), and the page loads with no failed request.
- **K7** `#evidence` shows the WIP-cap study, the prototype money table and the results list under the heading
  "Evidence".
- **K8** a question typed in the bar opens the answer panel; `#ask` still opens it too.
- **K9** speed: the one button goes 1×, 3×, 12× and back to 1×.

Earlier tests that pinned what is cut change with this spec, each listed in Changes.

## Changes

- 31 Oct, K6: the bound was 12, an estimate made before counting. The cuts above leave 14 on the first screen: the four
  nav links, How a chip is made, the ask bar, Follow one lot, the rail's two buttons, the key's disclosure, play, speed,
  the time slider and Fit. Fit now shows only once the view has been moved (it does nothing before), which leaves 13;
  the bound is 13. Cutting further would remove something kept on purpose (How a chip is made, the glossary).
- 31 Oct, earlier tests changed with this spec, each pinning something cut: `plainwords.test.mjs` no longer asks for
  "machines busy" and "Longest line"; `cleanup.test.mjs` test 1 checks the dock's title and the rail's two buttons in
  place of five tabs, and test 6 checks there is no view bar and that Follow one lot and Show prototypes exist;
  `frontdoor.test.mjs` checks "or explore the floor" is gone and the nav ends with Evidence.
- 31 Oct, results: K1 to K9 pass and all 133 page tests. The floor's first screen went from 21 controls to 13. Evidence
  opens at its top (the results' search box no longer takes the focus there). One run of the whole suite failed the
  editor's P4 (box select and paste) once; it passed alone twice and in the next whole run. The page tests start
  several headless browsers at once, and P4 waits fixed times, so it can miss under load: a timing weakness of the
  test, noted for the bug pass.

