// Race the AI (docs/RACE-AI.md): Muse Wonder plays the challenge on screen through the editor's own moves. The helper
// holds the key and the spend cap; this page runs the game, carries out each move in the editor and shows it.
// On a teaching fab of our own; not a real fab.
(function () {
  const $ = (id) => document.getElementById(id);
  const MAX_MOVES = 30;
  let stop = false, playing = false, gameUsd = 0;

  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const stars = (n) => "★".repeat(n) + "☆".repeat(3 - n);
  async function post(path, body) {
    try {
      const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      return await r.json();
    } catch (e) { return { error: "The helper did not answer. Start it with: python3 -m agent.helper" }; }
  }
  function status(text) { $("ai-status").textContent = text; }
  function money(r) {
    if (!r || r.cap_usd == null) return;
    gameUsd += r.cost_usd || 0;
    $("ai-cost").textContent = `${r.model === "stand-in" ? "stand-in (recorded game)" : r.model || "Muse Wonder"} · this game $${gameUsd.toFixed(2)} · $${(r.spent_usd || 0).toFixed(2)} of $${r.cap_usd} spent so far`;
  }
  function move(name, why, result) {
    const li = document.createElement("li");
    li.className = "ai-move" + (result && result.ok === false ? " refused" : "");
    const said = result && result.error ? `refused: ${result.error}` : result && result.note ? result.note
      : result && result.ran ? `${result.wafers_a_day} wafers a day${result.stars != null ? ` · ${stars(result.stars)}` : ""}` : result && result.ran === false ? result.note : "";
    li.innerHTML = `<code>${esc(name)}</code>${why ? `<span class="why">${esc(why)}</span>` : ""}${said ? `<span class="res">${esc(said)}</span>` : ""}`;
    $("ai-moves").appendChild(li);
    li.scrollIntoView({ block: "nearest" });
  }
  function opening() {
    const c = window.FabEditorTools.challenge();
    return c ? `Play this challenge. ${c.title}. ${c.problem} ${c.goal} Target: ${c.target.wafers} wafers a day${c.target.budget != null ? `, budget $${c.target.budget.toLocaleString()}` : ""}.`
      : "This is a free build. Make the fab put out as many wafers a day as you can.";
  }

  async function play() {
    if (playing) return;
    playing = true; stop = false; gameUsd = 0;
    $("ai-panel").hidden = false; $("ai-moves").innerHTML = ""; $("ai-stars").textContent = ""; $("ai-stop").disabled = false;
    status("Playing…");
    window.FabEditorTools.setPlaying(true);
    const messages = [{ role: "user", content: opening() }];
    let moves = 0, best = 0, ending = "";
    try {
      while (!ending) {
        if (stop) { ending = "Stopped by you."; break; }
        const r = await post("/api/race/step", { messages });
        money(r);
        if (r.error) { ending = `Stopped: ${r.error}`; break; }
        const msg = r.message;
        messages.push(msg);
        const calls = msg.tool_calls || [];
        if (!calls.length) { ending = `Ended: ${msg.content || "the AI made no more moves."}`; break; }
        for (let i = 0; i < calls.length; i++) {
          const call = calls[i], name = call.function && call.function.name;
          let args = {}, result;
          try { args = JSON.parse(call.function.arguments || "{}"); } catch (e) { result = { ok: false, error: "its arguments are not JSON" }; }
          if (!result) result = await window.FabEditorTools.call(name, args);
          const shown = name === "look" ? { note: "read the map" } : result;
          move(name, i === 0 ? msg.content : "", shown);
          messages.push({ role: "tool", tool_call_id: call.id, content: JSON.stringify(result) });
          if (result && result.stars != null) { best = Math.max(best, result.stars); $("ai-stars").textContent = stars(best); }
          moves++;
          await new Promise((ok) => setTimeout(ok, 250));
        }
        if (best >= 3) ending = "Ended with three stars.";
        else if (moves >= MAX_MOVES) ending = `Ended: ${MAX_MOVES} moves, the most a game allows.`;
      }
    } finally {
      window.FabEditorTools.setPlaying(false);
      status(ending + (best ? ` Best: ${stars(best)}` : ""));
      $("ai-stop").disabled = true;
      playing = false;
    }
  }

  window.addEventListener("DOMContentLoaded", () => {
    $("ai-go").onclick = play;
    $("ai-stop").onclick = () => { stop = true; status("Stopping after this move…"); };
    $("ai-close").onclick = () => { $("ai-panel").hidden = true; };
  });
})();
