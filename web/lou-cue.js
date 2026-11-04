// Lou's box for the demo video: the 3D fab's dialogue window (portrait, pixel font, a line that types out, a bobbing
// arrow), shown only when the page's address has ?cue. ] shows Lou's next line and [ the one before; ?cue=N starts so
// that the next ] shows line N. The lines are video/lou-cues.json, written by Meta's Muse Spark; rebuild this list
// from it with video/cues.py. Nobody else sees any of this.
(() => {
  const CUES = [{"id": "hello", "text": "Friends, our hour of destiny has arrived. Welcome to my fab, where we will end the world's memory shortage."}, {"id": "problem", "text": "Destiny demands more memory, but my fab is too slow. Wafers queue in lines while good machines stand idle."}, {"id": "q1", "text": "With all lots bound to the same machines and rails, who goes next for the empire, and shall rush prototypes jump the line?"}, {"id": "q2", "text": "Given these rails and the wafers pouring in, where shall each tool stand in my empire?"}, {"id": "honest", "text": "We set the industry's best practices, dude!"}, {"id": "tour", "text": "I will show you my empire fab in person, then we will watch my finest films together in my cinema hall."}, {"id": "close", "text": "My friends, our empire of memory awaits your dreams, so let us build onward together."}];
  const qs = new URLSearchParams(location.search), arg = qs.get("cue");
  if (arg === null && qs.get("auto") === null) return;
  const here = document.currentScript ? document.currentScript.src : location.href;
  const base = here.slice(0, here.lastIndexOf("/") + 1);
  const css = `
#lou-cue{position:fixed;left:24px;right:24px;bottom:22px;display:flex;gap:16px;z-index:2147483000;pointer-events:none;
  opacity:0;transform:translateY(12px);transition:opacity .25s,transform .25s}
#lou-cue.on{opacity:1;transform:none}
#lou-cue .w{background:rgba(18,26,84,.94);border:4px solid #f7f7f7;border-radius:8px;box-shadow:0 6px 22px rgba(5,8,30,.7)}
#lou-cue .face{width:112px;flex:none;padding:8px 8px 5px;text-align:center}
#lou-cue .face img{width:92px;height:92px;display:block;margin:0 auto;background:#fff;border-radius:2px}
#lou-cue .face span{display:block;margin-top:4px;font:9px 'Press Start 2P',monospace;color:#ffd84a;letter-spacing:0}
#lou-cue .talk{flex:1;max-width:1100px;padding:12px 20px 14px;position:relative;min-height:112px}
#lou-cue .who{font:12px 'Press Start 2P',monospace;color:#ffd84a;letter-spacing:1px;margin-bottom:8px}
#lou-cue .line{font:19px/1.7 'Press Start 2P',monospace;color:#f3f4ff;letter-spacing:0;text-transform:uppercase}
#lou-cue .next{position:absolute;right:22px;bottom:14px;width:0;height:0;border-left:9px solid transparent;
  border-right:9px solid transparent;border-top:12px solid #f3f4ff;animation:loubob .8s ease-in-out infinite alternate}
@keyframes loubob{to{transform:translateY(5px)}}`;
  const fl = document.createElement("link"); fl.rel = "stylesheet";
  fl.href = "https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap"; document.head.appendChild(fl);
  const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
  const box = document.createElement("div"); box.id = "lou-cue"; box.setAttribute("aria-live", "polite");
  box.innerHTML = `<div class="w face"><img src="${base}cast/lou-portrait.png" alt=""><span>LOU LATENCY</span></div>
<div class="w talk"><div class="who">LOU LATENCY, CEO</div><div class="line"></div><div class="next" hidden></div></div>`;
  const add = () => document.body.appendChild(box);
  document.body ? add() : document.addEventListener("DOMContentLoaded", add);
  const line = box.querySelector(".line"), next = box.querySelector(".next");
  let i = Math.max(0, (parseInt(arg, 10) || 1) - 1) - 1, timer = 0, hide = 0;
  const RATE = new URLSearchParams(location.search).get("auto") === null ? 48 : 60;   // characters a second, as in the 3D fab
  function show(k) {
    if (k < 0 || k >= CUES.length) return;
    i = k; clearInterval(timer); clearTimeout(hide);
    const text = CUES[k].text; let n = 0;
    line.textContent = ""; next.hidden = true; box.classList.add("on");
    const t0 = performance.now();
    timer = setInterval(() => {
      n = Math.min(text.length, Math.floor((performance.now() - t0) / 1000 * RATE)); line.textContent = text.slice(0, n);
      if (n >= text.length) {
        clearInterval(timer); next.hidden = false;
        hide = setTimeout(() => box.classList.remove("on"), Math.max(3500, text.length * 45));
      }
    }, 30);
  }
  window.LouCue = { show, hide: () => { clearTimeout(hide); box.classList.remove("on"); }, count: CUES.length };   // the video's director (director.js) calls this
  addEventListener("keydown", e => {
    if (e.key === "]") { e.preventDefault(); e.stopPropagation(); show(i + 1); }
    else if (e.key === "[") { e.preventDefault(); e.stopPropagation(); show(Math.max(0, i - 1)); }
  }, true);
})();
