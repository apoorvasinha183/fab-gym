# The floor page, cleaned up

Written 29 October 2026, before the code, from a tester's critique of the floor page (29 points; the founder: "Put
all of these in a plan and execute the cleanup"; Apple-like where it makes sense, balancing elegance with
information). On the SMT2020 model, a published research model of a wafer fab.

## Principles

- One obvious way to do each thing. One place to ask, one place for answers, one place for settings.
- The floor stays visible. Panels dock beside it; nothing covers it whole.
- Calm by default: fewer colours, fewer words always on screen, detail when you zoom or ask.
- One name per thing, and one type family, with tabular numbers.

## Deliverables, in order (critique points in brackets)

1. **One dock.** A panel on the right with five tabs: Ask, Change, Numbers, Results, Glossary. It replaces the left
   drawer, the Try a change panel and the three overlays that covered the floor. Ask and Change are narrow; Numbers,
   Results and Glossary are wide; the floor fits the space left either way. When the dock is closed, a slim rail of
   the five tabs stays on the right edge. **One Ask:** the top bar is the only place to type a question (⌘K); the
   opening screen is the same box on first load; its answer opens in the dock's Ask tab, with the scenario editor
   under Advanced. The pink footer button goes. A change's result shows under its own controls. [1, 2, 3, 4, 17]
2. **A calm bottom bar.** Time only: play, clock, speed, the run's waiting-lots line (labelled), and Fit (labelled). [5]
3. **A floor key and a quieter log.** A small key always on screen: machine states, lots, what "+N" means and what
   Holding is. The log pauses while hovered and names a tool by its area. The controls hint shows once and fades. [7, 10, 14, 15]
4. **Fewer colours, each with one meaning.** Teal for actions; pink only for prototype lots; red only for a broken
   tool or a worse verdict; amber for waiting heat; the track in steel with teal chevrons. [8, 9, 25]
5. **Detail by zoom.** At the overview, groups show without their "+N" chips, queue belts and names; these appear
   as you zoom in. The board's empty margin shrinks. [6, 11]
6. **The views.** Day becomes Live. Prototype lots is disabled, with its reason, when the fab has none. Flows gets
   pause, restart and a choice of product 3 or 4. [12]
7. **A compact hover card.** Counts and waits only, placed beside the cursor and inside the screen. The drawing stays
   in How a chip is made. [13]
8. **The Change tab.** One line of help under each dial, the Simulate and compare button pinned at the bottom, rule
   names in full, outage hours off until a group is chosen, seed and days under Advanced. [16]
9. **Ask's answers.** A plain status line, candidates named by what they change, Side by side as the main button
   and On the floor as a link. [17]
10. **Numbers.** The grid first; the method in a closed "How this was measured"; the interval chart under a
    disclosure, its text neutral with ✓ and ✗; the shares chart clips far points and marks them; money rounded to
    what the assumed prices can carry ($0.67M); the WIP-cap study as its own section. [18, 19, 20, 21, 22]
11. **Results.** A search box and filter chips by kind; the two-family entry opens Numbers. [23]
12. **Glossary.** A softer underline; codes (P1, D2) left out of a term's other names. [24]
13. **Type and words.** One family with tabular numbers (no monospace in the chrome), nothing under 12 px, muted text
    lighter; one name per policy and floor everywhere; "$ a day" throughout. [26, 27]
14. **Rest.** The fab starts paused when the viewer asks for reduced motion, and pauses while the page is hidden. [28]
15. **Narrow screens.** Under 900 px wide the dock becomes a bottom sheet and the bar wraps; checked at 390 px. [29]

## Tests (`web/tests/cleanup.test.mjs`)

1. The page has one question box outside the opening (the top bar), no Ask button in the footer and no question box
   in the dock; the dock has the five tabs; Numbers, Results, Glossary and the Change controls are inside it.
2. The footer holds only time controls, with Fit and the waiting-lots line labelled in words.
3. The floor key names the five machine states, the three kinds of lot, "+N" and Holding.
4. The palette gives each colour one role: red only broken and worse, pink only prototype lots, heat amber, the
   primary button teal.
5. Detail by zoom: names, chips and queue belts switch on in that order as the scale grows, and stay on above it.
6. The views read Live, Waiting heat, Prototype lots, Flows.
7. The hover card's place keeps it inside the screen and off the cursor.
8. A candidate's name comes from what it changes, in the page's words.
9. The shares chart's range leaves out far points and lists them.
10. Money is rounded to three significant figures.
11. Results filter by words and by kind.
12. A glossary term's shown other names leave out codes.
13. One name per policy and floor; the chrome's CSS uses no monospace; no text under 12 px in the chrome.
14. The page honours reduced motion and pauses while hidden.
15. The CSS turns the dock into a bottom sheet under 900 px.

## Changes

- 29 Oct, during the build: two older tests changed with the plan. The hover card names its group's stage and
  drops the drawing (`web/tests/stages.test.mjs`); the Glossary opens from the dock's rail and tabs, so its own
  footer button is gone (`web/tests/glossary.test.mjs`). Found on the way: "+N" on a group counts lots waiting in
  its queue beyond those drawn (the critique had read it as tools); the floor key says so.

