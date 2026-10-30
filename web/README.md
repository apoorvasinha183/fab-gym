# web

The fab floor in a browser. The simulator (Rust, `crates/fabweb`) is compiled to WebAssembly and
runs in the page, with no server work: 3 simulated days from the SMT2020 testbed take about 0.15 to
0.25 s in Chrome on an M1. The page plays the run back on a factory-floor layout:

- a spine belt running clockwise, with halls of tool groups on both sides; the three check areas
  share one hall;
- the halls are placed by a seeded local search so lots' trips along the spine are short, and the
  layout takes the screen's shape;
- each tool is a square coloured by its state, with each group's waiting lots on a queue belt;
- lots move between halls along the spine, timed to the simulator's departure and arrival;
- "Try a change" reruns the simulator with another dispatch rule or a tool group taken down.

Build and serve locally (needs the SMT2020 files in `data/smt2020/hvlm`):

    web/build.sh
    python3 -m http.server 8765 --bind 127.0.0.1 --directory web

Every number on the page is from the simulator on the SMT2020 testbed (a published set of a fab's tool groups, routes and times), never a real fab.
