// Small live charts for the Floor and Build (docs/CURVES.md): each line is drawn up to now, a thin line marks now, and
// the latest value sits beside the chart's name. Read from the run already on the page; nothing is simulated here.
// On a teaching fab of our own and the SMT2020 testbed; not a real fab.
(function (root) {
  const W = 220, H = 64, PX = 4, PY = 6;

  /** The value of a stepped series at time t: the last sample at or before t. */
  function at(xs, ys, t) {
    let lo = 0, hi = xs.length - 1, k = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (xs[m] <= t) { k = m; lo = m + 1; } else hi = m - 1; }
    return k < 0 ? ys[0] : ys[k];
  }

  /**
   * Draw one chart into el. o = { name, xs, series: [{ label, ys, cls }], until, now, fmt, top }: xs in fab minutes,
   * the first series is the one on screen; top fixes the vertical scale (else the largest value of every series).
   */
  function render(el, o) {
    const x = (t) => PX + (Math.max(0, Math.min(o.until, t)) / o.until) * (W - 2 * PX);
    const top = o.top || Math.max(1e-9, ...o.series.flatMap((s) => s.ys));
    const y = (v) => H - PY - (v / top) * (H - 2 * PY);
    const now = Math.min(o.now, o.until);
    const lines = o.series.map((s) => {
      const pts = [];
      for (let i = 0; i < o.xs.length && o.xs[i] <= now; i++) pts.push(`${x(o.xs[i]).toFixed(1)},${y(s.ys[i]).toFixed(1)}`);
      pts.push(`${x(now).toFixed(1)},${y(at(o.xs, s.ys, now)).toFixed(1)}`); // the line ends exactly at now
      return `<polyline class="series ${s.cls || ""}" points="${pts.join(" ")}"/>`;
    }).join("");
    const last = at(o.xs, o.series[0].ys, now);
    el.dataset.name = o.name;
    el.dataset.last = String(last);
    const key = o.series.length > 1 ? `<div class="key">${o.series.map((s) => `<span class="${s.cls || ""}">${s.label}</span>`).join("")}</div>` : "";
    el.innerHTML = `<div class="hd"><span class="nm">${o.name}</span><b>${o.fmt ? o.fmt(last) : last}</b></div>` +
      `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${o.name} over the run, up to now">` +
      `<line class="base" x1="${PX}" y1="${H - PY}" x2="${W - PX}" y2="${H - PY}"/>${lines}` +
      `<line class="now" x1="${x(now).toFixed(1)}" y1="2" x2="${x(now).toFixed(1)}" y2="${H - 2}"/></svg>${key}`;
  }

  const api = { render, at };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.FabCharts = api;
})(typeof window !== "undefined" ? window : globalThis);
