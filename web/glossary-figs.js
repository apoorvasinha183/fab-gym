// The glossary's figures (docs/GLOSSARY-PLUS.md, part 1): flowcharts, states, timelines and comparisons drawn as SVG
// from data, in the page's own colours (classes styled in floor-ui.css). Each figure has a one-line caption. Numbers
// shown are ones the glossary already states. In the page this defines window.FabGlossaryFigs; under Node,
// module.exports. On a teaching fab of our own and the SMT2020 testbed; not a real fab.
(function (root) {
  "use strict";
  const CW = 168, RH = 84, BW = 128, BH = 50, PAD = 14, FONT = 12, LINE = 14, CHARS = 17;
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  /** Split a label into lines of at most `n` characters, breaking at spaces. */
  function wrap(text, n = CHARS) {
    const lines = [];
    let cur = "";
    for (const w of String(text).split(/\s+/)) {
      if (cur && (cur + " " + w).length > n) { lines.push(cur); cur = w; } else cur = cur ? cur + " " + w : w;
    }
    if (cur) lines.push(cur);
    return lines;
  }
  const textBlock = (lines, cx, cy, cls = "") => {
    const y0 = cy - ((lines.length - 1) * LINE) / 2;
    return `<text class="${cls}" x="${cx}" text-anchor="middle" font-size="${FONT}">` +
      lines.map((l, i) => `<tspan x="${cx}" y="${(y0 + i * LINE + 4).toFixed(1)}">${esc(l)}</tspan>`).join("") + `</text>`;
  };

  // ---------------------------------------------------------------- flowcharts and state diagrams on a grid
  // nodes: { id: [col, row, label, kind] } with kind start | step | ask | end | bad | hot | ghost
  // edges: [from, to, label, opts] with opts { curve: "above" | "below", dx, dy, lx, ly }
  function flow(f) {
    const N = {};
    let cols = 0, rows = 0;
    const top = (f.edges || []).some((e) => e[3] && e[3].curve === "above") ? 40 : 0; // room for a curve over the boxes
    for (const [id, [c, r, label, kind]] of Object.entries(f.nodes)) {
      N[id] = { c, r, label, kind: kind || "step", x: PAD + c * CW + (CW - BW) / 2, y: PAD + top + r * RH };
      cols = Math.max(cols, c + 1); rows = Math.max(rows, r + 1);
    }
    const W = PAD * 2 + cols * CW, H = PAD * 2 + top + (rows - 1) * RH + BH + (f.extraBottom || 0);
    let edges = "", labels = "";
    for (const [a, b, label, o = {}] of f.edges || []) {
      const A = N[a], B = N[b];
      const acx = A.x + BW / 2, acy = A.y + BH / 2, bcx = B.x + BW / 2, bcy = B.y + BH / 2;
      let d, lx, ly;
      if (o.curve) {
        const up = o.curve === "above", ya = up ? A.y : A.y + BH, yb = up ? B.y : B.y + BH, bend = up ? -30 : 30;
        const yc = (up ? Math.min(ya, yb) : Math.max(ya, yb)) + bend;
        d = `M${acx},${ya} C${acx},${yc} ${bcx},${yc} ${bcx},${yb + (up ? -2 : 2)}`;
        lx = (acx + bcx) / 2; ly = yc + (up ? 4 : 6);
      } else if (A.r === B.r) {
        const dir = Math.sign(bcx - acx), dy = o.dy || 0;
        const x1 = dir > 0 ? A.x + BW : A.x, x2 = dir > 0 ? B.x - 2 : B.x + BW + 2;
        d = `M${x1},${acy + dy} L${x2},${bcy + dy}`;
        lx = (x1 + x2) / 2; ly = acy + dy - 6;
      } else if (A.c === B.c) {
        const dir = Math.sign(bcy - acy), dx = o.dx || 0;
        const y1 = dir > 0 ? A.y + BH : A.y, y2 = dir > 0 ? B.y - 2 : B.y + BH + 2;
        d = `M${acx + dx},${y1} L${bcx + dx},${y2}`;
        lx = acx + dx + (dx < 0 ? -6 : 6); ly = (y1 + y2) / 2 + 4;
      } else {
        // diagonal: from the side of A facing B to the top or bottom of B
        const down = bcy > acy, right = bcx > acx;
        const x1 = right ? A.x + BW : A.x, y1 = acy;
        const x2 = bcx + (right ? -BW / 4 : BW / 4), y2 = down ? B.y - 2 : B.y + BH + 2;
        d = `M${x1},${y1} L${x2},${y2}`;
        // the label sits beside the line's middle, off to the side away from the boxes it joins
        const len = Math.hypot(x2 - x1, y2 - y1) || 1, nx = -(y2 - y1) / len, ny = (x2 - x1) / len, s = ny > 0 ? -1 : 1;
        lx = (x1 + x2) / 2 + s * nx * 12; ly = (y1 + y2) / 2 + s * ny * 12 + 4;
        o.anchor = o.anchor || (s * nx > 0 ? "start" : "end");
      }
      edges += `<path class="edge${o.cls ? " " + o.cls : ""}" d="${d}"${o.noArrow ? "" : ' marker-end="url(#gl-arrow)"'}/>`;
      if (label) {
        const anchor = o.anchor || (A.c === B.c ? (o.dx < 0 ? "end" : "start") : "middle");
        labels += `<text class="elabel" x="${(lx + (o.lx || 0)).toFixed(1)}" y="${(ly + (o.ly || 0)).toFixed(1)}" text-anchor="${anchor}" font-size="11">${esc(label)}</text>`;
      }
    }
    let nodes = "";
    for (const n of Object.values(N)) {
      const lines = wrap(n.label);
      nodes += `<g class="node ${n.kind}"><rect x="${n.x}" y="${n.y}" width="${BW}" height="${BH}" rx="${n.kind === "ask" ? 18 : 8}"/>` +
        textBlock(lines, n.x + BW / 2, n.y + BH / 2) + `</g>`;
    }
    let extra = "";
    for (const t of f.texts || []) extra += `<text class="${t.cls || "elabel"}" x="${t.x}" y="${t.y}" text-anchor="${t.anchor || "middle"}" font-size="${t.size || 12}">${esc(t.text)}</text>`;
    return svg(W, H, edges + nodes + labels + extra, f.title);
  }

  // ---------------------------------------------------------------- timelines: segments on one bar, brackets below
  // segs: [label, length, kind]; brackets: [from segment, to segment, label]
  function timeline(f) {
    const total = f.segs.reduce((s, x) => s + x[1], 0), W = 600, X0 = PAD, span = W - 2 * PAD, Y = PAD + 6;
    let x = X0, out = "";
    const xs = [];
    for (const [label, len, kind] of f.segs) {
      const w = (len / total) * span;
      xs.push([x, x + w]);
      out += `<g class="node ${kind || "step"}"><rect x="${x.toFixed(1)}" y="${Y}" width="${(w - 3).toFixed(1)}" height="${BH}" rx="6"/>` +
        textBlock(wrap(label, Math.max(4, Math.floor((w - 14) / 6.6))), x + (w - 3) / 2, Y + BH / 2) + `</g>`;
      x += w;
    }
    // brackets under the bar; one that overlaps the last goes on a new row
    let yb = Y + BH + 14, lastEnd = -1, used = false;
    for (const [a, b, label] of f.brackets || []) {
      if (used && a <= lastEnd) yb += 40;
      const x1 = xs[a][0] + 2, x2 = xs[b][1] - 5;
      out += `<path class="bracket" d="M${x1.toFixed(1)},${yb} v8 H${x2.toFixed(1)} v-8"/>` +
        `<text class="elabel" x="${((x1 + x2) / 2).toFixed(1)}" y="${yb + 24}" text-anchor="middle" font-size="12">${esc(label)}</text>`;
      lastEnd = b; used = true;
    }
    if (used) yb += 40;
    for (const m of f.marks || []) {
      const mx = xs[m[0]][0];
      out += `<text class="mark ${m[2] || ""}" x="${mx.toFixed(1)}" y="${Y - 4}" text-anchor="middle" font-size="12">${esc(m[1])}</text>`;
    }
    const top = f.marks ? 14 : 0;
    return svg(W, yb + 6, out, f.title, top);
  }

  // ---------------------------------------------------------------- intervals around zero
  // rows: [label, lo, mean, hi, kind]; values on a shared axis from -1 to 1
  function intervals(f) {
    const W = 600, X0 = 190, X1 = W - PAD - 10, Y0 = PAD + 22, RHI = 40;
    const sx = (v) => X0 + ((v + 1) / 2) * (X1 - X0);
    let out = `<line class="zero" x1="${sx(0)}" y1="${PAD + 14}" x2="${sx(0)}" y2="${Y0 + f.rows.length * RHI - 10}"/>` +
      `<text class="elabel" x="${sx(0)}" y="${PAD + 8}" text-anchor="middle" font-size="11">no difference</text>` +
      `<text class="elabel" x="${X1}" y="${PAD + 8}" text-anchor="end" font-size="11">better →</text>` +
      `<text class="elabel" x="${X0}" y="${PAD + 8}" text-anchor="start" font-size="11">← worse</text>`;
    f.rows.forEach(([label, lo, mean, hi, kind], i) => {
      const y = Y0 + i * RHI + 12;
      out += `<g class="ival ${kind || ""}"><line x1="${sx(lo)}" y1="${y}" x2="${sx(hi)}" y2="${y}"/>` +
        `<line x1="${sx(lo)}" y1="${y - 7}" x2="${sx(lo)}" y2="${y + 7}"/><line x1="${sx(hi)}" y1="${y - 7}" x2="${sx(hi)}" y2="${y + 7}"/>` +
        `<circle cx="${sx(mean)}" cy="${y}" r="5"/></g>` +
        `<text class="rlabel ${kind || ""}" x="${PAD}" y="${y + 4}" font-size="12">${esc(label)}</text>`;
    });
    return svg(W, Y0 + f.rows.length * RHI + 4, out, f.title);
  }

  function svg(W, H, body, title, top = 0) {
    return `<svg viewBox="0 ${-top} ${W} ${H + top}" role="img" aria-label="${esc(title)}" xmlns="http://www.w3.org/2000/svg">` +
      `<defs><marker id="gl-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">` +
      `<path d="M0,0 L10,5 L0,10 z" class="arrowhead"/></marker></defs>${body}</svg>`;
  }

  // ---------------------------------------------------------------- the twenty figures
  const FIGS = {
    route: { type: flow, title: "A route, simplified", caption: "A route, simplified: product 3 repeats print, etch, clean and check layer by layer, 583 steps in all.",
      nodes: { a: [0, 0, "Bare wafer", "start"], b: [1, 0, "Print a pattern (lithography)"], c: [2, 0, "Etch it"], d: [3, 0, "Clean it"],
        e: [3, 1, "Check it"], f: [2, 1, "More layers to build?", "ask"], g: [1, 1, "Finished wafer", "end"] },
      edges: [["a", "b"], ["b", "c"], ["c", "d"], ["d", "e"], ["e", "f"], ["f", "g", "no"], ["f", "b", "yes"]] },
    lot: { type: flow, title: "A lot's life in the fab", caption: "Every lot repeats wait, work and ride until its last step; then it leaves the fab.",
      nodes: { a: [0, 0, "Released at the door", "start"], b: [1, 0, "Waits in a tool's line"], c: [2, 0, "Worked on by a tool"],
        d: [1, 1, "Rides the track to the next tool"], e: [2, 1, "Was that its last step?", "ask"], f: [3, 1, "Leaves the fab", "end"] },
      edges: [["a", "b"], ["b", "c"], ["c", "e"], ["e", "d", "no"], ["d", "b"], ["e", "f", "yes"]] },
    dispatch: { type: flow, title: "How a dispatch rule picks", caption: "Each time a tool comes free, the dispatch rule picks its next lot from the line.",
      nodes: { a: [0, 0, "A tool comes free", "start"], b: [1, 0, "Any lots waiting for it?", "ask"], c: [2, 0, "The rule ranks the line"],
        d: [3, 0, "The tool takes the top lot", "end"], e: [1, 1, "The tool stays idle", "ghost"] },
      edges: [["a", "b"], ["b", "c", "yes"], ["c", "d"], ["b", "e", "no", { dx: 0 }]] },
    rework: { type: flow, title: "Rework", caption: "A lot that fails its check goes back and redoes the step, costing time and another turn on a tool.",
      nodes: { a: [0, 0, "Step done", "start"], b: [1, 0, "Checked", "ask"], c: [2, 0, "On to the next step", "end"], d: [1, 1, "Sent back to redo the step", "bad"] },
      edges: [["a", "b"], ["b", "c", "pass"], ["b", "d", "fail", { dx: 0 }], ["d", "a"]] },
    hold: { type: flow, title: "A defect hold", caption: "Held lots stop where they are until a person looks and releases them.",
      nodes: { a: [0, 0, "A check finds a problem", "bad"], b: [1, 0, "Lots on hold, not moving"], c: [2, 0, "An engineer looks"], d: [3, 0, "Released back to the line", "end"] },
      edges: [["a", "b"], ["b", "c"], ["c", "d"]] },
    batch: { type: flow, title: "Filling a batch", caption: "A batch tool waits until enough lots gather, then works on all of them at once.",
      nodes: { a: [0, 0, "Lots arrive at the tool", "start"], b: [1, 0, "Enough for a batch?", "ask"], c: [2, 0, "Run them all together", "end"], d: [1, 1, "Wait for more lots", "ghost"] },
      edges: [["a", "b"], ["b", "c", "yes"], ["b", "d", "no", { dx: -16 }], ["d", "b", "more arrive", { dx: 16 }]] },
    wipcap: { type: flow, title: "A WIP cap at the door", caption: "A cap holds new lots at the door, so fewer lots crowd the floor at once.",
      nodes: { a: [0, 0, "A new lot at the door", "start"], b: [1, 0, "Fewer lots inside than the cap?", "ask"], c: [2, 0, "It enters the fab", "end"], d: [1, 1, "It waits at the door", "ghost"] },
      edges: [["a", "b"], ["b", "c", "yes"], ["b", "d", "no", { dx: -16 }], ["d", "b", "a lot leaves", { dx: 16 }]] },
    simulator: { type: flow, title: "What the simulator does", caption: "The simulator plays the fab forward from published data and a seed's luck, and reports what came out.",
      nodes: { a: [0, 0, "The fab's data from SMT2020", "start"], b: [1, 0, "Simulator plays the days"], c: [2, 0, "Numbers: wafers, waits, money", "end"],
        d: [1, 1, "Random luck, fixed by a seed", "ghost"] },
      edges: [["a", "b"], ["b", "c"], ["d", "b"]] },
    rl: { type: flow, title: "Reinforcement learning", caption: "The learner tries, the simulator scores, and the learner shifts toward what scored well.", extraBottom: 26,
      nodes: { a: [0, 0, "The learner picks an action", "start"], b: [1, 0, "The simulator plays it"], c: [2, 0, "A reward comes back", "end"] },
      edges: [["a", "b"], ["b", "c"], ["c", "a", "learn from it, try again", { curve: "below" }]] },
    e2: { type: flow, title: "Evolutionary search", caption: "Each generation keeps the best scoring rules and mixes them into the next.", extraBottom: 26,
      nodes: { a: [0, 0, "A set of rules", "start"], b: [1, 0, "Score each one in the simulator"], c: [2, 0, "Keep the best"], d: [3, 0, "Mix and change them"] },
      edges: [["a", "b"], ["b", "c"], ["c", "d"], ["d", "a", "the next generation", { curve: "below" }]] },
    tool: { type: flow, title: "A tool's states", caption: "A tool is in one of these states at every moment; the Floor's lights show which.",
      nodes: { i: [0, 0, "Idle", "ghost"], w: [1, 0, "Working", "end"], s: [2, 0, "Changing setup"], m: [0, 1, "Maintenance"], b: [1, 1, "Broken down", "bad"], r: [2, 1, "Under repair"] },
      edges: [["i", "w", "", { dy: -8 }], ["w", "i", "", { dy: 8 }], ["w", "s", "", { dy: -8 }], ["s", "w", "", { dy: 8 }], ["w", "b"], ["b", "r"], ["r", "w"], ["i", "m", "", { dx: -14 }], ["m", "i", "", { dx: 14 }]] },
    breakdown: { type: timeline, title: "A breakdown and its repair", caption: "A breakdown stops the tool; the repair time runs until it works again.",
      segs: [["Working", 4, "end"], ["Broken, waiting", 2, "bad"], ["Being repaired", 3], ["Working", 3, "end"]],
      marks: [[1, "✕ breaks", "bad"]], brackets: [[1, 2, "repair time: the tool does no work"]] },
    qtime: { type: timeline, title: "A queue-time limit", caption: "After some steps the next one must start within a limit; a lot that waits too long is redone.",
      segs: [["Step A done", 3, "end"], ["Waiting in line", 4, "ask"], ["Step B starts", 3, "end"]],
      brackets: [[1, 1, "must be shorter than the limit"]] },
    setup: { type: timeline, title: "A setup change", caption: "Switching a tool to a different recipe takes time in which it makes nothing.",
      segs: [["Lots on recipe A", 4, "end"], ["Setup change", 2, "bad"], ["Lots on recipe B", 4, "end"]],
      brackets: [[1, 1, "time lost"]] },
    warmup: { type: timeline, title: "Warm-up and window", caption: "A run's first days are left out while the fab fills up; only the window counts.",
      segs: [["Warm-up: left out", 3, "ghost"], ["Window: counted in the score", 7, "end"]],
      brackets: [[0, 0, "the fab fills up"], [1, 1, "averages taken here"]] },
    hotlot: { type: flow, title: "A hot lot jumps the line", caption: "A hot lot goes to the front of every line it joins.", extraBottom: 0,
      nodes: { t: [0, 0, "The tool", "end"], a: [1, 0, "Lot"], b: [2, 0, "Lot"], c: [3, 0, "Lot"], h: [4, 0, "Hot lot", "hot"] },
      edges: [["h", "t", "jumps to the front", { curve: "above" }]] },
    paired: { type: flow, title: "Paired seeds", caption: "Each seed runs twice, as today and as changed; the differences are averaged, so luck cancels out.",
      nodes: { a: [1, 0, "Seed 1, today"], b: [2, 0, "Seed 2, today"], c: [3, 0, "Seed 3, today"],
        d: [1, 1, "Seed 1, changed", "end"], e: [2, 1, "Seed 2, changed", "end"], f: [3, 1, "Seed 3, changed", "end"] },
      edges: [["a", "d", "same luck", { noArrow: true, cls: "pair" }], ["b", "e", "same luck", { noArrow: true, cls: "pair" }], ["c", "f", "same luck", { noArrow: true, cls: "pair" }]],
      texts: [{ x: PAD + CW / 2, y: PAD + BH / 2 + 4, text: "Today's fab" }, { x: PAD + CW / 2, y: PAD + RH + BH / 2 + 4, text: "Changed fab" }] },
    interval: { type: intervals, title: "A 95% interval", caption: "The dot is the average difference over the seeds; the bar is the range the true difference lies in, with 95% confidence.",
      rows: [["Average difference", 0.12, 0.38, 0.64, "better"]] },
    verdict: { type: intervals, title: "Three verdicts", caption: "Better or worse only when the whole interval sits on one side of zero; otherwise no clear effect.",
      rows: [["Better", 0.15, 0.45, 0.75, "better"], ["Worse", -0.8, -0.5, -0.2, "worse"], ["No clear effect", -0.3, 0.1, 0.5, "unclear"]] },
    little: { type: flow, title: "Little's law", caption: "On a steady run, lots inside equal lots out a day times the days a lot spends inside.",
      nodes: { a: [0, 0, "Lots inside (WIP)", "end"], b: [1, 0, "Lots out a day"], c: [2, 0, "Days inside (cycle time)"] },
      edges: [],
      texts: [{ x: PAD + CW, y: PAD + BH / 2 + 6, text: "=", size: 18 }, { x: PAD + 2 * CW, y: PAD + BH / 2 + 6, text: "×", size: 18 }] },
  };

  function draw(id) {
    const f = FIGS[id];
    return f ? f.type(f) : "";
  }

  const api = { FIGS, draw, wrap };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.FabGlossaryFigs = api;
})(typeof window !== "undefined" ? window : globalThis);
