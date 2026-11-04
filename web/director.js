// The demo video's director: with ?auto=N in the address, the page plays beat N of video/script.json by itself
// (scrolls, points, types the what-if and waits for the real answer), shows your line as a subtitle (?subs=0 hides
// them) and Lou's box at each cue, then goes on to the next beat's page. Built by video/director.py; nobody else sees it.
(() => {
  const qs = new URLSearchParams(location.search), at = qs.get("auto");
  if (at === null) return;
  const SCRIPT = [{"screen": "Site · top", "url": "http://127.0.0.1:8777/", "items": [["you", "Hello! Thank you for this opportunity. This is my project, Fab Gym: a digital twin of a semiconductor fab, and we'll tackle one problem to get a feel for it. I'm joined by my friend, Mr. Lou Latency.", 10.22, "c34b772d8d2bb5d6.mp3"], ["lou", "hello"], ["you", "Mr. Lou has the best wafer fabs in the world, in his own words, and he wants us to raise this factory's throughput.", 5.15, "ea47db35c7260b35.mp3"], ["lou", "problem"]], "acts": {"2": [{"scrollby": 500}]}}, {"screen": "Site · the cast", "url": "http://127.0.0.1:8777/", "items": [["you", "It's a queueing problem. He has an impressive cast of tools, but every lot crosses hundreds of steps, 583 for one product, on 1,043 shared machines and rails.", 9.29, "5fc50a17acd1d83d.mp3"]], "acts": {"0": [{"scroll": "#cast"}, {"focus": ".champ", "n": 4, "every": 1.4}]}}, {"screen": "App · the live Floor", "url": "http://127.0.0.1:8766/#floor", "items": [["lou", "q1"], ["lou", "q2"], ["you", "Scheduling, layout, and a thousand more: far too many answers to try them all. So Meta's models make the first guesses, and our Rust simulator predicts their impact.", 8.73, "eed8b9f0956a114c.mp3"]], "acts": {"0": [{"point": "#h-wip"}], "2": [{"point": "#h-toolbar"}]}}, {"screen": "App · the ask bar: Muse Spark Open live", "url": "http://127.0.0.1:8766/#floor", "items": [["you", "Watch. I ask a what-if in plain words. Muse Spark Open, Meta's open-weights model, turns it into an experiment: what changes, what to compare, every value marked said or assumed.", 11.19, "a1e16d194d71def6.mp3"], ["you", "The simulator runs today's fab against each answer on ten paired seeds and reports the difference with 95% intervals. I read the card, and I sign.", 7.85, "ccc68b44d8cfe2bf.mp3"]], "acts": {"0": [{"ask": "What if the polishers break down twice as often? Would capping the work in the fab protect output?"}], "1": [{"waitfor": "Done in", "max": 45}, {"point": "#ask-result"}]}}, {"screen": "The rule Muse Spark Open wrote tonight", "url": "http://127.0.0.1:8778/card.html", "items": [["you", "Muse Spark Open also writes the dispatch rule itself, in Rust, scored on days it never saw. Tonight's rule tied the fab's own rule, with about two hundred fewer queue-time breaches.", 10.31, "efaf13efa6591d7c.mp3"], ["lou", "honest"]], "acts": {"0": [{"slowscroll": 1}]}}, {"screen": "App · Evidence", "url": "http://127.0.0.1:8766/#evidence", "items": [["you", "And you don't have to take the model's word for it. Every scored run is checked by a referee written in Lean: 120 of 120 passed. And on a teaching fab, Muse Spark supervising added 117 wafers a day.", 12.26, "35ad0457c142805d.mp3"]], "acts": {"0": [{"point": "#find-list"}]}}, {"screen": "Build: Muse Wonder racing live", "url": "http://127.0.0.1:8766/editor.html", "items": [["you", "For layouts, design your own fab right in the browser, or race Muse Wonder, Meta's model, playing the same challenge with the same moves you have.", 6.59, "bc87d0c613101b2e.mp3"], ["hold", 2]], "acts": {"0": [{"click": "#ai-go"}]}, "end": true}, {"screen": "Site · the close", "url": "http://127.0.0.1:8777/#new", "items": [["you", "Fab Gym is open: play it in your browser, run it locally with your own key, or load it as a reinforcement-learning environment.", 6.22, "33584a9d9fa3a0d3.mp3"], ["lou", "close"]], "acts": {"0": [{"scroll": "#new"}]}, "end": true}], CUES = [{"id": "hello", "text": "Friends, our hour of destiny has arrived. Welcome to my fab, where we will end the world's memory shortage."}, {"id": "problem", "text": "Destiny demands more memory, but my fab is too slow. Wafers queue in lines while good machines stand idle."}, {"id": "q1", "text": "With all lots bound to the same machines and rails, who goes next for the empire, and shall rush prototypes jump the line?"}, {"id": "q2", "text": "Given these rails and the wafers pouring in, where shall each tool stand in my empire?"}, {"id": "honest", "text": "We set the industry's best practices, dude!"}, {"id": "tour", "text": "I will show you my empire fab in person, then we will watch my finest films together in my cinema hall."}, {"id": "close", "text": "My friends, our empire of memory awaits your dreams, so let us build onward together."}], WPS = 2.6, TYPE = 60;
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
