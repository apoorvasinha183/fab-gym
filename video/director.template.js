// The demo video's director: with ?auto=N in the address, the page plays beat N of video/script.json by itself
// (scrolls, points, types the what-if and waits for the real answer), shows your line as a subtitle (?subs=0 hides
// them) and Lou's box at each cue, then goes on to the next beat's page. Built by video/director.py; nobody else sees it.
(() => {
  const qs = new URLSearchParams(location.search), at = qs.get("auto");
  if (at === null) return;
  const SCRIPT = __SCRIPT__, CUES = __CUES__, WPS = __WPS__, TYPE = 60;
  const subs = qs.get("subs") === "1";   // the lines are voiced; ?subs=1 also shows them as text
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const cueNo = Object.fromEntries(CUES.map((c, i) => [c.id, i]));
  const css = `
#dir-sub{position:fixed;left:50%;top:78px;transform:translateX(-50%);max-width:1100px;width:calc(100% - 80px);z-index:2147483001;
  background:rgba(8,10,28,.86);color:#fff;font:600 27px/1.4 Inter,"Helvetica Neue",Arial,sans-serif;padding:14px 22px;
  border-radius:10px;text-align:center;opacity:0;transition:opacity .2s;pointer-events:none}
#dir-sub.on{opacity:1}
#dir-ring{position:fixed;z-index:2147483000;border:4px solid #ffd84a;border-radius:12px;box-shadow:0 0 0 6px rgba(255,216,74,.25),0 0 30px rgba(255,216,74,.55);
  pointer-events:none;opacity:0;transition:all .45s ease}
#dir-ring.on{opacity:1}`;
  const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
  const sub = document.createElement("div"); sub.id = "dir-sub";
  const ring = document.createElement("div"); ring.id = "dir-ring";
  const mount = () => { document.body.append(sub, ring); };
  document.body ? mount() : document.addEventListener("DOMContentLoaded", mount);

  const byText = t => [...document.querySelectorAll("h1,h2,h3,h4")].find(e => e.textContent.trim().startsWith(t));
  function point(el) {
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    const place = () => { const r = el.getBoundingClientRect();
      Object.assign(ring.style, { left: r.left - 8 + "px", top: r.top - 8 + "px", width: r.width + 16 + "px", height: r.height + 16 + "px" });
      ring.classList.add("on"); };
    setTimeout(place, 500); setTimeout(place, 1100);
  }
  async function act(a) {
    if (a.scroll) document.querySelector(a.scroll)?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (a.scrolltext) byText(a.scrolltext)?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (a.scrollby) scrollBy({ top: a.scrollby, behavior: "smooth" });
    if (a.slowscroll) { const end = Date.now() + 9000; (async () => { while (Date.now() < end) { scrollBy(0, 2); await sleep(30); } })(); }
    if (a.point) point(document.querySelector(a.point));
    if (a.click) { const el = document.querySelector(a.click); point(el); await sleep(700); el && el.click(); }
    if (a.focus) { const els = [...document.querySelectorAll(a.focus)];
      (async () => { for (let k = 0; k < Math.min(a.n || 3, els.length); k++) { els[(k * 3 + 1) % els.length].focus(); await sleep((a.every || 1.2) * 1000); }
        document.activeElement?.blur(); })(); }
    if (a.ask) { const q = document.getElementById("cmd-q"), f = document.getElementById("cmd");
      q.focus(); q.value = "";
      for (const ch of a.ask) { q.value += ch; await sleep(28); }
      await sleep(400); document.getElementById("cmd-examples").hidden = true; f.requestSubmit(); }
    if (a.waitfor) { const end = Date.now() + (a.max || 60) * 1000;
      const ready = () => { const r = document.getElementById("ask-result"), t = document.body.innerText;
        return (r && r.innerText.trim().length > 40) || t.includes(a.waitfor) || t.includes("was refused"); };
      while (Date.now() < end && !ready()) await sleep(300);
      await sleep(800); }
  }
  function say(text) { sub.textContent = text; sub.classList.toggle("on", subs); }

  async function play(n) {
    const b = SCRIPT[n];
    await sleep(1200);
    for (let i = 0; i < b.items.length; i++) {
      for (const a of (b.acts || {})[i] || []) await act(a);
      const [kind, val] = b.items[i];
      if (kind === "hold") { await sleep(val * 1000); continue; }
      if (kind === "you") {
        // the cut lays the founder's recorded line at this mark (its time in ms is in the address)
        fetch(`http://127.0.0.1:8778/mark/${Date.now()}-${n}-${i}`, { mode: "no-cors" }).catch(() => {});
        say(val);
        const dur = b.items[i][2];
        await sleep((dur ? dur + 0.35 : val.split(/\s+/).length / WPS + 0.5) * 1000);
        sub.classList.remove("on");
      } else if (kind === "lou") {
        const text = CUES[cueNo[val]].text;
        window.LouCue && window.LouCue.show(cueNo[val]);
        await sleep((text.length / TYPE + Math.max(1.6, text.length / 40)) * 1000);
        window.LouCue && window.LouCue.hide && window.LouCue.hide();
      }
      await sleep(250);
    }
    ring.classList.remove("on");
    const next = SCRIPT[n + 1];
    if (b.end || !next) { fetch("http://127.0.0.1:8778/mark/end-" + n, { mode: "no-cors" }).catch(() => {}); return; }
    const here = new URL(location.href), there = new URL(next.url);
    if (here.origin === there.origin && here.pathname === there.pathname) {
      if (there.hash && there.hash !== here.hash) location.hash = there.hash;
      await sleep(600);
      return play(n + 1);
    }
    there.searchParams.set("auto", String(n + 1));
    if (subs) there.searchParams.set("subs", "1");
    location.href = there.toString();
  }
  addEventListener("load", () => play(+at));
})();
