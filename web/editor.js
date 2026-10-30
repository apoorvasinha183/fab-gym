// The map editor's page (docs/EDITOR.md): the 2.5D floor, editing, the simulator's checks and a run's moods, with
// the cast's cards. The pure parts are in editor-core.js. On the SMT2020 model or a teaching fab; not a real fab.
(function () {
  "use strict";
  const E = window.FabEditor;
  const $ = (id) => document.getElementById(id);
  const D = [[1, 0], [0, 1], [-1, 0], [0, -1]];
  const FAM = { litho: "#F2B33D", lithomet: "#C9D3DA", dry: "#FF8A5B", wet: "#FF8A5B", diff: "#FF5E7A", diel: "#5FA8FF", tf: "#5FA8FF", tfmet: "#C9D3DA", imp: "#B48CFF", cmp: "#3FD0C4", defmet: "#C9D3DA" };
  const AREA_NAME = { litho: "Lithography", lithomet: "Litho metrology", dry: "Dry etch", wet: "Wet etch and clean", diff: "Diffusion", diel: "Dielectric", tf: "Thin film", tfmet: "Thin film metrology", imp: "Ion implant", cmp: "Polishing (CMP)", defmet: "Defect inspection" };
  const EXERCISE = { litho: "Posing under the spotlight", lithomet: "One-leg balance", dry: "Heavy bag", wet: "Laps in its own tank", diff: "Hot yoga", diel: "Squat with layered plates", tf: "Kettlebell swing", tfmet: "Tiny curls on a scale", imp: "Medicine-ball launcher", cmp: "The plank", defmet: "Spotting the bench press" };
  const MOOD = {
    work: ["In the zone", "#3DDC84"], sleep: ["Dozing off", "#AAB4BA"], tired: ["Gassed", "#FFB020"], full: ["Hands full", "#FFB020"], batch: ["Waiting for the class", "#AAB4BA"],
    setup: ["Changing kit", "#5FA8FF"], pm: ["Rest day", "#5FA8FF"], hurt: ["Pulled a muscle", "#FF4D4F"], physio: ["At the physio", "#FF4D4F"], hold: ["Benched", "#FFB020"],
  };
  const LOT = { fresh: "Fresh", line: "In line", impatient: "Impatient", clock: "On the clock", missed: "Missed", bench: "On the bench", ride: "Riding", batch: "Class", redo: "Do-over", hold: "Quarantined", grad: "Graduated" };

  let base = E.TEACHING_SHOP, s = E.template("teaching");
  let tool = "select", sel = null, hover = null, drag = null, flash = null;
  let checks = null, moods = null, frame = 0, stale = false;
  const groupsOfBase = () => base.split("\n").filter((l) => l.startsWith("group\t")).map((l) => l.split("\t")[1]);
  const areaOfGroup = {};

  // ---------- the 2.5D floor (the floor page's look)
  const ISO = { r: -0.36, q: 0.5, pad: 0.03 };
  const cv = $("map"), ctx = cv.getContext("2d");
  let F = null;
  function fit(cw) {
    const co = Math.cos(ISO.r), sn = Math.sin(ISO.r);
    const pts = [[0, 0], [s.W, 0], [0, s.H], [s.W, s.H]].map(([x, y]) => [x * co - y * sn, (x * sn + y * co) * ISO.q]);
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const pad = cw * ISO.pad, sc = (cw - 2 * pad) / (Math.max(...xs) - Math.min(...xs));
    const lift = sc * 1.4, depth = sc * 0.7;
    return { s: sc, co, sn, ox: pad - Math.min(...xs) * sc, oy: pad + lift - Math.min(...ys) * sc, ch: (Math.max(...ys) - Math.min(...ys)) * sc + 2 * pad + lift + depth, depth };
  }
  const P = (x, y, z) => [F.ox + (x * F.co - y * F.sn) * F.s, F.oy + (x * F.sn + y * F.co) * ISO.q * F.s - (z || 0) * F.s];
  const unP = (sx, sy) => { const X = (sx - F.ox) / F.s, Y = (sy - F.oy) / (ISO.q * F.s); return [X * F.co + Y * F.sn, -X * F.sn + Y * F.co]; };
  function poly(pts) { ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.closePath(); }
  function shade(hex, a) { const n = parseInt(hex.slice(1), 16); const f = (v) => Math.max(0, Math.min(255, Math.round(v * (1 + a)))); return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`; }

  function draw() {
    const dpr = window.devicePixelRatio || 1, cw = cv.parentElement.clientWidth;
    F = fit(cw);
    cv.width = Math.round(cw * dpr); cv.height = Math.round(F.ch * dpr); cv.style.height = F.ch + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, F.ch);
    const slab = [P(0, 0), P(s.W, 0), P(s.W, s.H), P(0, s.H)];
    ctx.save(); ctx.translate(0, F.depth); poly(slab); ctx.fillStyle = "#071013"; ctx.fill(); ctx.restore();
    poly(slab); ctx.fillStyle = "#0F1D22"; ctx.fill(); ctx.strokeStyle = "rgba(126,232,216,.55)"; ctx.lineWidth = 1.2; ctx.stroke();
    ctx.strokeStyle = "rgba(126,232,216,0.06)"; ctx.beginPath();
    for (let x = 0; x <= s.W; x += 5) { const a = P(x, 0), b = P(x, s.H); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); }
    for (let y = 0; y <= s.H; y += 5) { const a = P(0, y), b = P(s.W, y); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); }
    ctx.stroke();
    // rails, tinted by jam after a run
    const jam = {};
    if (moods && moods.stretches.length) {
      const fr = moods.frames[frame];
      moods.stretches.forEach((n, i) => (jam[n] = fr.rails[i]));
    }
    const bad = new Set((checks && checks.issues ? checks.issues : []).filter((i) => i.severity === "error").flatMap((i) => i.at));
    for (const k of Object.keys(s.rail)) {
      const [x, y] = k.split(",").map(Number);
      s.rail[k].o.forEach((on, d) => {
        if (!on) return;
        const n = E.key(x + D[d][0], y + D[d][1]), live = !!s.rail[n];
        const a = P(x + 0.5, y + 0.5, 0.08), b = P(x + 0.5 + D[d][0] * (live ? 1 : 0.45), y + 0.5 + D[d][1] * (live ? 1 : 0.45), 0.08);
        const name = `c${x}_${y}>c${x + D[d][0]}_${y + D[d][1]}`;
        const j = jam[name] || 0;
        ctx.strokeStyle = bad.has(`c${x}_${y}`) ? "#FF6B57" : j > 0.05 ? `rgba(255,${Math.max(80, 200 - j * 60) | 0},90,0.95)` : "#2C5560";
        ctx.lineWidth = Math.max(2, F.s * 0.32); ctx.lineCap = "round";
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
        if ((x + y) % 2 === 0 || s.rail[k].o.reduce((p, q) => p + q) > 1) {
          const m = P(x + 0.5 + D[d][0] * 0.5, y + 0.5 + D[d][1] * 0.5, 0.08), ang = Math.atan2(b[1] - a[1], b[0] - a[0]), r = Math.max(2, F.s * 0.14);
          ctx.save(); ctx.translate(m[0], m[1]); ctx.rotate(ang); ctx.strokeStyle = "rgba(126,232,216,.85)"; ctx.lineWidth = 1.3;
          ctx.beginPath(); ctx.moveTo(-r * 0.6, -r); ctx.lineTo(r * 0.6, 0); ctx.lineTo(-r * 0.6, r); ctx.stroke(); ctx.restore();
        }
      });
      if (sel && sel.rail === k) { poly([P(x, y), P(x + 1, y), P(x + 1, y + 1), P(x, y + 1)]); ctx.strokeStyle = "#7EE8D8"; ctx.lineWidth = 2; ctx.stroke(); }
    }
    // blocks, back to front
    const items = s.blocks.map((b) => ({ b, d: P(b.x + b.w / 2, b.y + b.h / 2)[1] })).sort((a, b) => a.d - b.d);
    for (const { b } of items) {
      const col = b.kind === "group" ? FAM[b.area] || "#8FB3AE" : b.kind === "stocker" ? "#8FB3AE" : "#7EE8D8";
      const tall = b.kind === "group" ? (b.area === "litho" ? 1.05 : b.area === "diff" ? 1.15 : 0.75) : b.kind === "stocker" ? 0.9 : 0.35;
      const i = 0.14;
      const bs = [P(b.x + i, b.y + i), P(b.x + b.w - i, b.y + i), P(b.x + b.w - i, b.y + b.h - i), P(b.x + i, b.y + b.h - i)];
      const tp = bs.map((p) => [p[0], p[1] - tall * F.s]);
      const faces = [0, 1, 2, 3].map((q) => ({ p: [bs[q], bs[(q + 1) % 4], tp[(q + 1) % 4], tp[q]], d: (bs[q][1] + bs[(q + 1) % 4][1]) / 2 })).sort((a, c) => a.d - c.d);
      faces.forEach((f, k) => { poly(f.p); ctx.fillStyle = k >= 2 ? "#26343B" : "#1A252B"; ctx.fill(); ctx.strokeStyle = "rgba(10,20,24,.9)"; ctx.lineWidth = 1; ctx.stroke(); });
      poly(tp); ctx.fillStyle = "#3A4A52"; ctx.fill();
      const cx = tp.reduce((a, p) => a + p[0], 0) / 4, cy = tp.reduce((a, p) => a + p[1], 0) / 4;
      poly(tp.map((p) => [cx + (p[0] - cx) * 0.72, cy + (p[1] - cy) * 0.72])); ctx.fillStyle = col; ctx.globalAlpha = 0.9; ctx.fill(); ctx.globalAlpha = 1;
      if (F.s >= 12) {
        ctx.font = `600 ${Math.max(8, Math.round(F.s * 0.4))}px "Chakra Petch",sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillStyle = "#0B1418";
        const lab = b.kind === "group" ? `${b.count}` : b.kind === "stocker" ? "S" : b.kind === "entry" ? "IN" : "OUT";
        ctx.fillText(lab, cx, cy);
      }
      const mood = moodOf(b);
      if (mood) {
        const tr = tp.reduce((a, p) => (p[0] - p[1] > a[0] - a[1] ? p : a), tp[0]), r = Math.max(4, F.s * 0.34);
        ctx.fillStyle = MOOD[mood][1]; ctx.beginPath(); ctx.arc(tr[0], tr[1], r, 0, 7); ctx.fill(); ctx.strokeStyle = "#0B1418"; ctx.lineWidth = 1.5; ctx.stroke();
      }
      if (b.kind === "group" && (bad.has(b.group) || [...bad].some((a) => a.startsWith(b.group + "#")))) { ctx.save(); ctx.setLineDash([5, 4]); ctx.strokeStyle = "#FF6B57"; ctx.lineWidth = 2; poly(tp); ctx.stroke(); ctx.restore(); }
      if (sel && sel.id === b.id) { ctx.strokeStyle = "#7EE8D8"; ctx.lineWidth = 2; poly(tp); ctx.stroke(); }
    }
    if (flash) { const p = P(flash[0] + 0.5, flash[1] + 0.5); ctx.strokeStyle = "#FF6B57"; ctx.lineWidth = 3; ctx.beginPath(); ctx.ellipse(p[0], p[1], F.s * 1.8, F.s * 0.9, 0, 0, 7); ctx.stroke(); }
    if (hover && ["group", "stocker", "entry", "exit"].includes(tool)) {
      const [w, h] = tool === "entry" || tool === "exit" ? [1, 2] : [2, 2];
      poly([P(hover[0], hover[1]), P(hover[0] + w, hover[1]), P(hover[0] + w, hover[1] + h), P(hover[0], hover[1] + h)]);
      ctx.fillStyle = free(hover[0], hover[1], w, h) ? "rgba(126,232,216,.3)" : "rgba(255,107,87,.35)"; ctx.fill();
    }
  }

  function moodOf(b) {
    if (!moods || b.kind !== "group") return null;
    return E.blockMood(moods, frame, b.group);
  }

  // ---------- editing
  const blockAt = (x, y, skip) => s.blocks.find((b) => b !== skip && x >= b.x && x < b.x + b.w && y >= b.y && y < b.y + b.h);
  function free(x, y, w, h, skip) {
    if (x < 0 || y < 0 || x + w > s.W || y + h > s.H) return false;
    for (let i = 0; i < w; i++) for (let j = 0; j < h; j++) if (s.rail[E.key(x + i, y + j)] || blockAt(x + i, y + j, skip)) return false;
    return true;
  }
  function edited() { stale = true; checks = null; $("verdict").innerHTML = '<span class="chip warning">edited</span>'; renderIssues(); draw(); }
  function cellOf(e) { const r = cv.getBoundingClientRect(); const [x, y] = unP(e.clientX - r.left, e.clientY - r.top); return [Math.floor(x), Math.floor(y)]; }
  cv.addEventListener("pointerdown", (e) => {
    const [x, y] = cellOf(e);
    if (x < 0 || y < 0 || x >= s.W || y >= s.H) return;
    const k = E.key(x, y), b = blockAt(x, y);
    if (tool === "select") {
      sel = b ? { id: b.id } : s.rail[k] ? { rail: k } : null;
      if (b) { drag = { move: b, dx: x - b.x, dy: y - b.y }; cv.setPointerCapture(e.pointerId); }
      inspector(); draw(); return;
    }
    if (tool === "erase") { if (b) s.blocks = s.blocks.filter((z) => z !== b); else delete s.rail[k]; sel = null; inspector(); edited(); drag = { erase: true }; cv.setPointerCapture(e.pointerId); return; }
    if (tool === "rail") { if (b) return; if (!s.rail[k]) s.rail[k] = { o: [0, 0, 0, 0] }; drag = { last: k }; sel = { rail: k }; cv.setPointerCapture(e.pointerId); inspector(); edited(); return; }
    const [w, h] = tool === "entry" || tool === "exit" ? [1, 2] : [2, 2];
    if (!free(x, y, w, h)) return;
    const id = Math.max(0, ...s.blocks.map((z) => z.id)) + 1;
    if (tool === "group") {
      const g = $("group").value;
      if (!g) return;
      s.blocks.push({ id, kind: "group", group: g, area: areaOfGroup[g], count: 1, x, y, w, h });
      fillGroups();
    } else s.blocks.push({ id, kind: tool, x, y, w, h });
    sel = { id }; inspector(); edited();
  });
  cv.addEventListener("pointermove", (e) => {
    const [x, y] = cellOf(e), inb = x >= 0 && y >= 0 && x < s.W && y < s.H;
    hover = inb ? [x, y] : null;
    if (drag && inb) {
      const k = E.key(x, y);
      if (drag.move) {
        const b = drag.move, nx = x - drag.dx, ny = y - drag.dy;
        if ((nx !== b.x || ny !== b.y) && free(nx, ny, b.w, b.h, b)) { b.x = nx; b.y = ny; edited(); }
      } else if (drag.erase) {
        const b = blockAt(x, y);
        if (b) s.blocks = s.blocks.filter((z) => z !== b); else if (s.rail[k]) delete s.rail[k]; else return;
        edited();
      } else if (k !== drag.last && !blockAt(x, y)) {
        const [lx, ly] = drag.last.split(",").map(Number), dx = x - lx, dy = y - ly;
        if (Math.abs(dx) + Math.abs(dy) === 1) {
          s.rail[drag.last].o[D.findIndex((v) => v[0] === dx && v[1] === dy)] = 1;
          if (!s.rail[k]) s.rail[k] = { o: [0, 0, 0, 0] };
          drag.last = k; sel = { rail: k }; edited();
        }
      }
    }
    card(e, inb ? blockAt(x, y) : null);
    status(x, y, inb);
    if (!drag) draw();
  });
  cv.addEventListener("pointerup", () => { drag = null; inspector(); });
  cv.addEventListener("pointerleave", () => { hover = null; $("hover").hidden = true; draw(); });

  function status(x, y, inb) {
    if (!inb) return ($("status").textContent = "");
    const b = blockAt(x, y), k = E.key(x, y);
    if (b && b.kind === "group") $("status").textContent = `(${x}, ${y})  ${b.group}: ${b.count} tool(s), ${AREA_NAME[b.area] || ""}${moodOf(b) ? ", " + MOOD[moodOf(b)][0].toLowerCase() : ""}`;
    else if (b) $("status").textContent = `(${x}, ${y})  ${b.kind === "stocker" ? "stocker" : b.kind === "entry" ? "wafer start" : "ship"}`;
    else if (s.rail[k]) $("status").textContent = `(${x}, ${y})  rail, out ${s.rail[k].o.map((o, i) => (o ? ["east", "south", "west", "north"][i] : null)).filter(Boolean).join(" and ") || "nowhere"}`;
    else $("status").textContent = `(${x}, ${y})  floor`;
  }

  function card(e, b) {
    const hov = $("hover");
    if (!b || b.kind !== "group") return (hov.hidden = true);
    const mood = moodOf(b) || "work", col = FAM[b.area] || "#7EE8D8";
    const tools = moods ? moods.groups.reduce((n, g) => n + (g === b.group ? 1 : 0), 0) : b.count;
    hov.innerHTML = `<div class="card" style="--fam:${col}"><div class="hd"><span class="nm">${b.group}</span><span class="fm">${b.count} tools</span></div>
      <div class="art" style="background:${col}33"><img src="cast/${b.area}/${mood}.webp" alt="${AREA_NAME[b.area]}, ${MOOD[mood][0]}"></div>
      <div class="ex">${AREA_NAME[b.area]} · ${EXERCISE[b.area]}</div>
      <div class="st" style="background:${MOOD[mood][1]}">${moods ? MOOD[mood][0] : "Before a run"}</div>
      <div class="ex">${moods ? `${tools} tools in the run, at ${tlabel(frame)}` : "Run the fab to see its mood."}</div></div>`;
    const r = $("mapwrap").getBoundingClientRect();
    let lx = e.clientX - r.left + 16, ly = e.clientY - r.top + 12;
    if (lx + 230 > r.width) lx = e.clientX - r.left - 236;
    hov.style.left = Math.max(4, lx) + "px"; hov.style.top = Math.max(4, Math.min(ly, r.height - 330)) + "px"; hov.hidden = false;
  }

  function inspector() {
    const ins = $("insp");
    if (sel && sel.id) {
      const b = s.blocks.find((z) => z.id === sel.id);
      if (!b) { sel = null; return inspector(); }
      if (b.kind === "group") {
        ins.innerHTML = `<div><b>${b.group}</b><br><span class="note">${AREA_NAME[b.area] || ""}</span></div>
          <div class="row"><span>Tools</span><span><button id="dn" aria-label="One fewer">−</button> <b>${b.count}</b> <button id="up" aria-label="One more">+</button></span></div>
          <div class="row"><button id="del">Remove</button></div>`;
        $("up").onclick = () => { b.count++; inspector(); edited(); };
        $("dn").onclick = () => { b.count = Math.max(1, b.count - 1); inspector(); edited(); };
      } else ins.innerHTML = `<div><b>${b.kind === "stocker" ? "Stocker" : b.kind === "entry" ? "Wafer start" : "Ship"}</b></div><div class="row"><button id="del">Remove</button></div>`;
      $("del").onclick = () => { s.blocks = s.blocks.filter((z) => z !== b); sel = null; fillGroups(); inspector(); edited(); };
    } else if (sel && sel.rail && s.rail[sel.rail]) {
      const v = s.rail[sel.rail];
      ins.innerHTML = `<div><b>Rail piece</b> <span class="note">(${sel.rail})</span></div><div class="row"><span>Ways out</span><span>${["E", "S", "W", "N"].map((d, i) => `<button data-d="${i}" aria-pressed="${!!v.o[i]}">${d}</button>`).join(" ")}</span></div>`;
      ins.querySelectorAll("[data-d]").forEach((bt) => (bt.onclick = () => { const d = +bt.dataset.d; v.o[d] = v.o[d] ? 0 : 1; inspector(); edited(); }));
    } else ins.innerHTML = '<p class="note" style="margin:0">Click a block or a rail piece.</p>';
  }

  function fillGroups() {
    const placed = new Set(s.blocks.filter((b) => b.kind === "group").map((b) => b.group));
    const left = groupsOfBase().filter((g) => !placed.has(g) && !(s.stores || []).includes(g));
    $("group").innerHTML = left.length ? left.map((g) => `<option value="${g}">${g} (${AREA_NAME[areaOfGroup[g]] || "?"})</option>`).join("") : '<option value="">every group is placed</option>';
  }

  // ---------- checks and runs, from the simulator through the helper
  const fab = () => E.fabText(base, s, { vehicles: s.vehicles });
  async function post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  }
  function renderIssues() {
    const ul = $("issues");
    if (!checks) { ul.innerHTML = '<li><span class="chip warning">to check</span><span>Press Check, or Run.</span></li>'; return; }
    if (checks.error) { ul.innerHTML = `<li><span class="chip error">refused</span><span>${checks.error}</span></li>`; $("verdict").innerHTML = '<span class="chip error">refused</span>'; return; }
    const errs = checks.issues.filter((i) => i.severity === "error").length;
    $("verdict").innerHTML = errs ? `<span class="chip error">${errs} to fix</span>` : '<span class="chip ok">ready to run</span>';
    ul.innerHTML = checks.issues.length
      ? checks.issues.map((i, n) => `<li data-n="${n}"><span class="chip ${i.severity}">${i.severity === "error" ? "fix" : "note"}</span><span>${i.message}</span></li>`).join("")
      : '<li><span class="chip ok">ok</span><span>Every tool has a stop, every stop is on the way from the wafer start to the ship point, and every route can be followed.</span></li>';
    ul.querySelectorAll("li[data-n]").forEach((li) => (li.onclick = () => {
      const i = checks.issues[+li.dataset.n];
      const at = i.at.map((a) => E.cellOfNode(a)).find(Boolean) || (() => { const b = s.blocks.find((z) => i.at.includes(z.group) || i.at.some((a) => z.group && a.startsWith(z.group + "#"))); return b ? [b.x, b.y] : null; })();
      if (at) { flash = at; draw(); setTimeout(() => { flash = null; draw(); }, 1400); }
    }));
  }
  $("check").onclick = async () => {
    $("check").disabled = true;
    try { checks = await post("/api/fab/check", { fab: fab() }); } catch (err) { checks = { error: "The helper did not answer: run python3 -m agent.helper." }; }
    $("check").disabled = false; renderIssues(); draw();
  };
  $("run").onclick = async () => {
    $("run").disabled = true; $("run").textContent = "Running…";
    try {
      const r = await post("/api/fab/run", { fab: fab(), seed: 1, days: Number($("days").value), every: 60 });
      checks = r.checks || null;
      if (r.error) { if (!checks || checks.ok) checks = { error: r.error }; moods = null; }
      else { moods = r.moods; stale = false; frame = moods.frames.length - 1; }
    } catch (err) { checks = { error: "The helper did not answer: run python3 -m agent.helper." }; }
    $("run").disabled = false; $("run").textContent = "Run";
    renderIssues(); timeline(); draw();
  };
  const tlabel = (k) => { const t = moods.frames[k].t; return `day ${Math.floor(t / 1440) + 1} ${String(Math.floor((t % 1440) / 60)).padStart(2, "0")}:00`; };
  function timeline() {
    $("time").hidden = !moods;
    if (!moods) return;
    $("slider").max = moods.frames.length - 1; $("slider").value = frame; $("tlabel").textContent = tlabel(frame);
    const fr = moods.frames[frame];
    $("lots").innerHTML = Object.keys(LOT).map((m) => `<div><img src="cast/lots/${m}.webp" alt=""><b>${fr.lots[m] || 0}</b>${LOT[m]}</div>`).join("");
  }
  $("slider").oninput = () => { frame = +$("slider").value; timeline(); draw(); };

  // ---------- templates
  async function load(name) {
    moods = null; checks = null; sel = null;
    if (name === "teaching") { base = E.TEACHING_SHOP; s = E.template("teaching"); for (const g of groupsOfBase()) areaOfGroup[g] = E.AREA_OF[g.replace(/_T$/, "")]; }
    else {
      const d = await (await fetch("/api/fab/base?name=smt2020")).json();
      if (d.error) { checks = { error: d.error }; renderIssues(); return; }
      base = d.shop; s = E.template("smt2020", d);
      for (const l of d.areas.split("\n")) { const [g, a] = l.split("\t"); if (g) areaOfGroup[g] = E.AREA_OF[a]; }
    }
    fillGroups(); inspector(); renderIssues(); timeline(); draw();
  }
  $("template").onchange = () => load($("template").value);
  document.querySelectorAll("[data-tool]").forEach((b) => (b.onclick = () => { tool = b.dataset.tool; document.querySelectorAll("[data-tool]").forEach((z) => z.setAttribute("aria-pressed", String(z === b))); }));
  window.addEventListener("resize", draw);
  load("teaching");
})();
