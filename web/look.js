// The Fab Gym look, shared by the floor and the editor (docs/FLOOR-LOOK.md): icons, area colours and names, the ten
// tool moods with their badges, a group's label and mood, and small drawing helpers for a 2D canvas. In the page this
// defines window.FabLook; under Node, module.exports. On the SMT2020 model or a teaching fab of our own; not a real fab.
(function (root) {
  "use strict";

  // 24 x 24 line icons, drawn by us
  const ICONS = {
    litho: "M12 2v3 M9 5h6l-1.5 4h-3z M10.5 9 6 17 M13.5 9 18 17 M4 19h16 M6 17h12",
    lithomet: "M10 4a6 6 0 1 0 0 12a6 6 0 1 0 0-12z M10 7v6 M7 10h6 M14.5 14.5 20 20",
    dry: "M4 18h16 M6 18v2h12v-2 M13 3l-4 7h4l-3 6",
    wet: "M3 12h18v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M3 15h18 M8 4c0 2 2 3 2 5a2 2 0 0 1-4 0c0-2 2-3 2-5z M16 6c0 1.5 1.5 2.2 1.5 3.5a1.5 1.5 0 0 1-3 0c0-1.3 1.5-2 1.5-3.5z",
    diff: "M4 10h16v6H4z M8 10v6 M12 10v6 M16 10v6 M8 3c-1 1.5 1 2.5 0 4 M12 3c-1 1.5 1 2.5 0 4 M16 3c-1 1.5 1 2.5 0 4 M6 16v3 M18 16v3",
    diel: "M3 17l9 4 9-4 M3 13l9 4 9-4 M3 9l9-4 9 4-9 4z",
    tf: "M3 18h18 M3 21h18 M7 3v9 M4.5 9.5 7 12l2.5-2.5 M17 3v9 M14.5 9.5 17 12l2.5-2.5 M12 5v7 M9.5 9.5 12 12l2.5-2.5",
    tfmet: "M4 20h16 M4 16h16 M8 4v10 M16 4v10 M8 8h8 M10.5 6 8 8l2.5 2 M13.5 6 16 8l-2.5 2",
    imp: "M3 7h8 M3 12h10 M3 17h8 M15 4v16 M18.5 8.5v.01 M18.5 12v.01 M18.5 15.5v.01 M21 10.2v.01 M21 13.8v.01",
    cmp: "M12 4a8 8 0 1 0 0 16a8 8 0 1 0 0-16z M14 10a3 3 0 1 0 0 6a3 3 0 1 0 0-6z M5.5 6.5A9 9 0 0 1 10 3.2 M10 3.2 8 2 M10 3.2 8.6 5",
    defmet: "M12 5a7 7 0 1 0 0 14a7 7 0 1 0 0-14z M12 2v4 M12 18v4 M2 12h4 M18 12h4 M10 10l4 4 M14 10l-4 4",
    rail: "M3 7h18 M3 17h18 M6 9.5l2.5 2.5L6 14.5 M11 9.5l2.5 2.5-2.5 2.5 M16 9.5l2.5 2.5-2.5 2.5",
    split: "M3 12h8 M11 12l8-7 M11 12l8 7 M16 4h3v3 M16 20h3v-3",
    stocker: "M4 3h16v18H4z M4 9h16 M4 15h16 M7 5h4v3H7z M13 11h4v3h-4z M7 17h4v3H7z",
    entry: "M2 12h9 M8 9l3 3-3 3 M14 4h7v16h-7 M17.5 9.5a2.5 2.5 0 1 0 0 5a2.5 2.5 0 1 0 0-5z",
    exit: "M3 4h7v16H3 M10 12h11 M18 9l3 3-3 3 M6.5 9.5a2.5 2.5 0 1 0 0 5a2.5 2.5 0 1 0 0-5z",
    select: "M5 3l14 8-6 2-2 6z",
    erase: "M16 3l5 5-11 11H5l-2-2z M9 9l6 6 M5 21h15",
    fab: "M3 21V9l6 4V9l6 4V5h6v16z M7 17h2 M12 17h2 M17 17h2",
    bolt: "M13 2 6 13h5l-1 9 7-11h-5z",
    b_work: "M7 12l3 3 7-7", b_sleep: "M6 7h6l-6 7h6 M14 4h5l-5 5h5", b_tired: "M12 3c3 5 6 8 6 11a6 6 0 0 1-12 0c0-3 3-6 6-11z",
    b_full: "M4 8h7v9H4z M13 8h7v9h-7z M6 8V5h3v3 M15 8V5h3v3", b_batch: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z M12 7v5l3 2",
    b_setup: "M4 9h13l-4-4 M20 15H7l4 4", b_pm: "M4 5h16v15H4z M4 10h16 M8 3v4 M16 3v4 M8 14h3v3H8z", b_hurt: "M13 2 6 13h5l-1 9 7-11h-5z",
    b_physio: "M9 3h6v6h6v6h-6v6H9v-6H3V9h6z", b_hold: "M5 21V4 M5 4h12l-3 4 3 4H5",
  };
  const FAM = { litho: "#F2B33D", lithomet: "#C9D3DA", dry: "#FF8A5B", wet: "#FF8A5B", diff: "#FF5E7A", diel: "#5FA8FF", tf: "#5FA8FF", tfmet: "#C9D3DA", imp: "#B48CFF", cmp: "#3FD0C4", defmet: "#C9D3DA" };
  const AREA = {
    litho: { name: "Lithography", short: "Litho", exercise: "Posing under the spotlight", about: "Prints the circuit pattern with light through a mask." },
    lithomet: { name: "Litho metrology", short: "Litho Met", exercise: "The posing judge", about: "Checks each printed layer lines up and has the right width." },
    dry: { name: "Dry etch", short: "Dry etch", exercise: "Heavy bag", about: "Cuts the pattern into the layer with plasma." },
    wet: { name: "Wet etch and clean", short: "Wet etch", exercise: "Laps in its own tank", about: "Cleans and etches in chemical baths." },
    diff: { name: "Diffusion", short: "Diffusion", exercise: "Hot yoga", about: "Furnaces that grow and anneal layers, in batches." },
    diel: { name: "Dielectric", short: "Dielectric", exercise: "Squat with layered plates", about: "Lays down insulating layers." },
    tf: { name: "Thin film", short: "Thin film", exercise: "Kettlebell swing", about: "Deposits metal and other thin films." },
    tfmet: { name: "Thin film metrology", short: "TF Met", exercise: "Tiny curls on a scale", about: "Measures film thickness." },
    imp: { name: "Ion implant", short: "Implant", exercise: "Medicine-ball launcher", about: "Fires ions into the wafer to set its electrical behaviour." },
    cmp: { name: "Polishing (CMP)", short: "CMP", exercise: "The plank", about: "Polishes the wafer flat between layers." },
    defmet: { name: "Defect inspection", short: "Defect", exercise: "Spotting the bench press", about: "Looks for defects and sends bad lots back." },
  };
  // SMT2020's area names to the cast's areas; Delay_32 (lots resting in stockers) has none
  const AREA_OF = { Litho: "litho", Litho_Met: "lithomet", Dry_Etch: "dry", Wet_Etch: "wet", Diffusion: "diff", Dielectric: "diel", TF: "tf", TF_Met: "tfmet", Implant: "imp", Planar: "cmp", Def_Met: "defmet" };
  const TOOL_MOODS = ["work", "sleep", "tired", "full", "batch", "setup", "pm", "hurt", "physio", "hold"];
  const MOOD = {
    work: { name: "In the zone", color: "#3DDC84", badge: "b_work" }, sleep: { name: "Dozing off", color: "#AAB4BA", badge: "b_sleep" },
    tired: { name: "Gassed", color: "#FFB020", badge: "b_tired" }, full: { name: "Hands full", color: "#FFB020", badge: "b_full" },
    batch: { name: "Waiting for the class", color: "#AAB4BA", badge: "b_batch" }, setup: { name: "Changing kit", color: "#5FA8FF", badge: "b_setup" },
    pm: { name: "Rest day", color: "#5FA8FF", badge: "b_pm" }, hurt: { name: "Pulled a muscle", color: "#FF4D4F", badge: "b_hurt" },
    physio: { name: "At the physio", color: "#FF4D4F", badge: "b_physio" }, hold: { name: "Benched", color: "#FFB020", badge: "b_hold" },
  };
  const LOTS = { fresh: "Fresh", line: "In line", impatient: "Impatient", hot: "Hot", clock: "On the clock", missed: "Missed", bench: "On the bench", ride: "Riding", batch: "Class", redo: "Do-over", hold: "Quarantined", grad: "Graduated" };
  // a tie between moods goes to the more serious
  const SERIOUS = ["hurt", "physio", "hold", "full", "tired", "batch", "setup", "pm", "sleep", "work"];

  const areaOf = (smtArea) => AREA_OF[smtArea] || null;
  /** A group's label: its area's short name, with the group's FE or BE number when it has one. */
  function label(group, area) {
    const a = AREA[area], m = /_(FE|BE)_(\d+)$/.exec(group);
    return a ? (m ? `${a.short} ${m[1]} ${m[2]}` : a.short) : group;
  }
  /** A group's mood at a frame of a moods run: the commonest among its tools, a tie to the more serious. */
  function groupMood(m, frame, group) {
    const f = m.frames[frame];
    if (!f) return null;
    const n = {};
    m.groups.forEach((g, i) => {
      if (g === group) {
        const mood = m.tool_moods[f.tools[i]];
        n[mood] = (n[mood] || 0) + 1;
      }
    });
    const moods = Object.keys(n);
    if (!moods.length) return null;
    moods.sort((a, b) => n[b] - n[a] || SERIOUS.indexOf(a) - SERIOUS.indexOf(b));
    return moods[0];
  }

  // ---------- drawing on a 2D canvas
  const paths = {};
  const path = (name) => paths[name] || (paths[name] = new Path2D(ICONS[name]));
  function icon(ctx, name, cx, cy, size, col, lw) {
    ctx.save(); ctx.translate(cx - size / 2, cy - size / 2); ctx.scale(size / 24, size / 24);
    ctx.strokeStyle = col; ctx.lineWidth = lw || 1.8; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.stroke(path(name)); ctx.restore();
  }
  /** A mood badge: a coloured disc with its icon. */
  function badge(ctx, mood, x, y, r) {
    const M = MOOD[mood];
    if (!M) return;
    ctx.fillStyle = M.color; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
    ctx.strokeStyle = "#0B1418"; ctx.lineWidth = 1.5; ctx.stroke();
    icon(ctx, M.badge, x, y, r * 1.35, "#15191C", 2.2);
  }
  /** A label on a dark pill, its top at y; returns the pill's height. */
  function pill(ctx, text, x, y, size) {
    ctx.font = `600 ${size}px "Chakra Petch",sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const w = ctx.measureText(text).width + 8, h = Math.max(13, size * 1.35);
    ctx.fillStyle = "rgba(7,16,19,.8)"; ctx.beginPath(); ctx.roundRect(x - w / 2, y, w, h, 4); ctx.fill();
    ctx.fillStyle = "#CFE3E0"; ctx.fillText(text, x, y + h / 2 + 0.5);
    return h;
  }
  /** Lots waiting: a row of pods centred at x with its top at y, the ninth and on as a count. */
  function pods(ctx, x, y, n, h) {
    if (!n) return;
    const k = Math.min(n, 8), pw = Math.max(6, h * 0.55), ph = Math.max(5, h * 0.45), gap = 2;
    const more = n > k ? `+${n - k}` : "";
    ctx.font = `700 ${Math.max(9, Math.round(h * 0.7))}px "Chakra Petch",sans-serif`;
    const tw = more ? ctx.measureText(more).width + 4 : 0, W = k * (pw + gap) - gap + tw + 8;
    ctx.fillStyle = "rgba(7,16,19,.8)"; ctx.beginPath(); ctx.roundRect(x - W / 2, y, W, ph + 6, 4); ctx.fill();
    let px = x - W / 2 + 4;
    for (let i = 0; i < k; i++, px += pw + gap) {
      ctx.fillStyle = n >= 8 ? "#FFB020" : "#F4E7C6"; ctx.fillRect(px, y + 3, pw, ph);
      ctx.strokeStyle = "#0B1418"; ctx.lineWidth = 1; ctx.strokeRect(px, y + 3, pw, ph);
    }
    if (more) { ctx.fillStyle = "#FFB020"; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(more, px + 2, y + 3 + ph / 2 + 0.5); ctx.textAlign = "center"; }
  }
  /** An inline SVG of an icon, for HTML. */
  const svg = (name, col) => `<svg viewBox="0 0 24 24" fill="none" stroke="${col || "currentColor"}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICONS[name]}"/></svg>`;

  const api = { ICONS, FAM, AREA, AREA_OF, TOOL_MOODS, MOOD, LOTS, areaOf, label, groupMood, icon, badge, pill, pods, svg };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FabLook = api;
})(typeof window !== "undefined" ? window : globalThis);
