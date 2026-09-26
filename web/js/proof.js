/* Proof: every claim in the deck, checked against a held-out week of real running data. */
App.views.proof = (() => {
  const A = App;
  let R = null, E = null;

  // ---- small chart kit (one axis, thin marks, hover everywhere, table twins via data) ----
  function hbars(el, rows, { fmt = v => v.toFixed(1), unit = "", hl = () => false, max } = {}) {
    const W = Math.max(320, el.clientWidth || 520), rowH = 30, L = 250, R = 70, H = rows.length * rowH + 10;
    const X = A.lin(0, max || Math.max(...rows.map(r => r.v)) * 1.08, L, W - R);
    el.innerHTML = "";
    const g = A.svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, el);
    rows.forEach((r, i) => {
      const y = 6 + i * rowH, w = Math.max(2, X(r.v) - L);
      A.text(g, L - 10, y + 15, r.label, { "text-anchor": "end", "font-size": 12, fill: hl(r) ? "var(--ink)" : "var(--ink-2)", "font-weight": hl(r) ? 700 : 400 });
      const b = A.svg("path", { d: `M${L} ${y + 4} h${w - 4} a4 4 0 0 1 4 4 v8 a4 4 0 0 1 -4 4 h${-(w - 4)} z`, fill: hl(r) ? "var(--accent)" : "var(--axis)" }, g);
      A.text(g, L + w + 6, y + 15, `${fmt(r.v)}${unit}`, { "font-size": 12, fill: "var(--ink)", "font-weight": hl(r) ? 700 : 500 });
      A.bindTip(b, () => `<b>${A.esc(r.label)}</b><br>${fmt(r.v)}${unit}${r.note ? `<br><span class="muted">${A.esc(r.note)}</span>` : ""}`);
    });
  }

  function lines(el, xs, series, { xl, yl, yfmt = v => v.toFixed(0), H = 240 } = {}) {
    const W = Math.max(320, el.clientWidth || 520), L = 46, R = 90, T = 12, B = 34;
    const all = series.flatMap(s => s.v).filter(v => v != null);
    const X = A.lin(xs[0], xs[xs.length - 1], L, W - R), Y = A.lin(0, Math.max(...all) * 1.1, H - B, T);
    el.innerHTML = "";
    const g = A.svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, el);
    const ax = A.svg("g", { class: "ax" }, g);
    const yt = Math.max(...all) * 1.1, step = yt > 30 ? 10 : yt > 12 ? 5 : 2;
    for (let v = 0; v <= yt; v += step) { A.svg("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "gridl" }, ax); A.text(ax, L - 6, Y(v) + 3.5, yfmt(v), { "text-anchor": "end" }); }
    xs.forEach(x => A.text(ax, X(x), H - B + 15, String(x), { "text-anchor": "middle" }));
    if (xl) A.text(ax, (L + W - R) / 2, H - 4, xl, { "text-anchor": "middle" });
    if (yl) A.text(ax, L, T - 2, yl, { "font-size": 10.5 });
    series.forEach(s => {
      A.svg("polyline", { points: xs.map((x, i) => `${X(x)},${Y(s.v[i])}`).join(" "), fill: "none", stroke: s.c, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, g);
      xs.forEach((x, i) => A.svg("circle", { cx: X(x), cy: Y(s.v[i]), r: 4, fill: s.c, stroke: "var(--surface)", "stroke-width": 2 }, g));
      const li = xs.length - 1;
      A.text(g, X(xs[li]) + 8, Y(s.v[li]) + 4, s.name, { "font-size": 11.5, fill: "var(--ink-2)" });
    });
    const cross = A.svg("line", { y1: T, y2: H - B, stroke: "var(--ink-2)", opacity: 0 }, g);
    const hit = A.svg("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent" }, g);
    hit.addEventListener("pointermove", e => {
      const r = g.getBoundingClientRect(), xv = X.inv(e.clientX - r.left);
      const i = xs.reduce((b, x, k) => Math.abs(x - xv) < Math.abs(xs[b] - xv) ? k : b, 0);
      cross.setAttribute("x1", X(xs[i])); cross.setAttribute("x2", X(xs[i])); cross.setAttribute("opacity", .5);
      A.tip(e, `<b>${xl ? xl.split("(")[0] : ""} ${xs[i]}</b>` + series.map(s => `<div class="row"><span><span class="key" style="background:${s.c}"></span>${s.name}</span><b>${yfmt(s.v[i])}</b></div>`).join(""));
    });
    hit.addEventListener("pointerleave", () => { cross.setAttribute("opacity", 0); A.tip(null); });
  }

  function calib(el, cal) {
    const W = Math.max(300, el.clientWidth || 360), H = 260, L = 44, R = 16, T = 12, B = 34;
    const X = A.lin(40, 100, L, W - R), Y = A.lin(30, 100, H - B, T);
    el.innerHTML = "";
    const g = A.svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, el);
    const ax = A.svg("g", { class: "ax" }, g);
    for (let v = 40; v <= 100; v += 10) { A.svg("line", { x1: X(v), x2: X(v), y1: T, y2: H - B, class: "gridl" }, ax); A.text(ax, X(v), H - B + 15, v + "%", { "text-anchor": "middle" }); }
    for (let v = 30; v <= 100; v += 10) { A.svg("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "gridl" }, ax); A.text(ax, L - 6, Y(v) + 3.5, v + "%", { "text-anchor": "end" }); }
    A.text(ax, (L + W - R) / 2, H - 4, "promised coverage", { "text-anchor": "middle" });
    A.svg("line", { x1: X(40), y1: Y(40), x2: X(100), y2: Y(100), stroke: "var(--axis)", "stroke-width": 1.5 }, g);
    A.text(g, X(97), Y(99) + 14, "perfect", { "text-anchor": "end", "font-size": 10.5, fill: "var(--muted)" });
    for (const c of cal) {
      A.svg("line", { x1: X(c.level), x2: X(c.level), y1: Y(100 * c.raw), y2: Y(100 * c.calibrated), stroke: "var(--axis)", "stroke-width": 1.5 }, g);
      for (const [k, col, nm] of [["raw", "var(--up)", "raw quantiles"], ["calibrated", "var(--dn)", "after conformal"]]) {
        const d = A.svg("circle", { cx: X(c.level), cy: Y(100 * c[k]), r: 5.5, fill: col, stroke: "var(--surface)", "stroke-width": 2 }, g);
        A.bindTip(d, () => `<b>${c.level}% window</b><div class="row"><span><span class="key" style="background:${col}"></span>${nm}</span><b>${(100 * c[k]).toFixed(1)}%</b></div><span class="muted">held-out 25–30 Sep · mean width ${c.width.toFixed(0)} min</span>`);
      }
    }
  }

  function dumbbell(el, rows) {
    const W = Math.max(320, el.clientWidth || 520), rowH = 24, L = 118, R = 20, T = 22, H = T + rows.length * rowH + 26;
    const vals = rows.flatMap(r => [r.promised, r.actual]);
    const X = A.lin(Math.min(-10, ...vals), Math.max(...vals) + 3, L, W - R);
    el.innerHTML = "";
    const g = A.svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, el);
    const ax = A.svg("g", { class: "ax" }, g);
    for (let v = -10; v <= Math.max(...vals) + 3; v += 5) { A.svg("line", { x1: X(v), x2: X(v), y1: T - 6, y2: H - 22, class: "gridl", stroke: v === 0 ? "var(--axis)" : null }, ax); A.text(ax, X(v), H - 8, `${v}`, { "text-anchor": "middle" }); }
    A.text(ax, W - R, T - 10, "minutes recovered (late trains, median)", { "text-anchor": "end" });
    rows.forEach((r, i) => {
      const y = T + i * rowH + 8;
      A.text(g, L - 8, y + 4, r.name.replace(" Jn", ""), { "text-anchor": "end", "font-size": 11.5 });
      A.svg("line", { x1: X(r.actual), x2: X(r.promised), y1: y, y2: y, stroke: "var(--axis)", "stroke-width": 2 }, g);
      A.svg("circle", { cx: X(r.promised), cy: y, r: 5, fill: "var(--up)", stroke: "var(--surface)", "stroke-width": 2 }, g);
      const d = A.svg("circle", { cx: X(r.actual), cy: y, r: 5, fill: "var(--dn)", stroke: "var(--surface)", "stroke-width": 2 }, g);
      const hit = A.svg("rect", { x: L, y: y - 11, width: W - L - R, height: 22, fill: "transparent" }, g);
      A.bindTip(hit, () => `<b>Arriving ${A.esc(r.name)}</b> · ${r.n} late-train forecasts<div class="row"><span><span class="key" style="background:var(--up)"></span>timetable promises</span><b>${r.promised.toFixed(0)} min</b></div><div class="row"><span><span class="key" style="background:var(--dn)"></span>route actually gave</span><b>${r.actual.toFixed(0)} min</b></div>`);
    });
  }

  function groupedBars(el, cats, series, { H = 220 } = {}) {
    const W = Math.max(320, el.clientWidth || 520), L = 40, R = 10, T = 10, B = 34;
    const max = Math.max(...series.flatMap(s => s.v));
    const X = A.lin(0, cats.length, L, W - R), Y = A.lin(0, max * 1.12, H - B, T);
    el.innerHTML = "";
    const g = A.svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, el);
    const ax = A.svg("g", { class: "ax" }, g);
    for (let v = 0; v <= max * 1.1; v += 10) { A.svg("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "gridl" }, ax); A.text(ax, L - 6, Y(v) + 3.5, v + "%", { "text-anchor": "end" }); }
    const band = (X(1) - X(0)), bw = Math.min(24, (band - 16) / series.length);
    cats.forEach((c, i) => {
      A.text(ax, X(i) + band / 2, H - B + 15, c, { "text-anchor": "middle" });
      series.forEach((s, k) => {
        const x = X(i) + band / 2 - (series.length * (bw + 2)) / 2 + k * (bw + 2), v = s.v[i], y = Y(v), h = Y(0) - y;
        const p = A.svg("path", { d: `M${x} ${Y(0)} v${-Math.max(0, h - 4)} a4 4 0 0 1 4 -4 h${bw - 8} a4 4 0 0 1 4 4 v${Math.max(0, h - 4)} z`, fill: s.c }, g);
        A.bindTip(p, () => `<b>${c} ${c === "5+" ? "" : ""}change${c === "1" ? "" : "s"} in the last 3 h</b><div class="row"><span><span class="key" style="background:${s.c}"></span>${s.name}</span><b>${v.toFixed(1)}% of arrivals</b></div>`);
      });
    });
    A.text(ax, (L + W - R) / 2, H - 3, "times the arrival time was restated later by 5+ min (final 3 hours)", { "text-anchor": "middle" });
  }

  async function render() {
    if (!R) { const x = await A.api("report"); R = x.report; E = x.evidence; }
    const lad = R.ladder, b0 = lad.find(l => l.key === "B0"), prod = lad.find(l => l.key === R.production);
    const cal80 = R.calibration.find(c => c.level === 80), cal90 = R.calibration.find(c => c.level === 90), cal50 = R.calibration.find(c => c.level === 50);
    const vol = E.volatility || {}, rake = E.rake || {};
    const pct = v => `${(100 * v).toFixed(0)}%`;
    const gain = 100 * (b0.mae - R.production_mae) / b0.mae;
    A.$("proof").innerHTML = `
      <div class="card"><div class="pipeline">
        <div class="stage"><div class="n">1 · PERCEIVE</div><h4>Read the whole corridor</h4><p>${A.fmt(E.dataset?.corridor_reports || 0)} trusted station reports from ${A.fmt(E.dataset?.corridor_trips || 0)} real trips (${A.fmt(E.dataset?.quality?.phantom || 0)} placeholders removed); every train dead-reckoned between reports; hourly rain for all 19 stations.</p></div>
        <div class="stage"><div class="n">2 · MODEL</div><h4>Learn the route, not the timetable</h4><p>Quantile gradient boosting on what this train really gains or loses on each stretch; network and topology layers tested, not assumed.</p></div>
        <div class="stage"><div class="n">3 · PUBLISH</div><h4>An honest, damped window</h4><p>Conformal calibration makes "8 in 10" true; a publisher only moves the window when it matters, earlier at once, later only for 10+ min.</p></div>
        <div class="stage"><div class="n">4 · DECIDE</div><h4>Leave now or wait. Hold or run.</h4><p>Asymmetric advice for boarders vs receivers; passenger-minute hold/let-run for controllers; SMS, 139 and boards from day one.</p></div>
      </div></div>

      <div class="grid g-tiles" style="margin-top:16px">
        <div class="card tile"><div class="label">Error vs today's ETA</div><div class="value">−${gain.toFixed(0)}%</div><div class="delta">MAE ${b0.mae.toFixed(1)} → ${R.production_mae.toFixed(1)} min · ${A.fmt(R.rows.test)} held-out forecasts</div></div>
        <div class="card tile"><div class="label">"8 in 10" window holds</div><div class="value">${pct(cal80.calibrated)}</div><div class="delta">raw quantiles alone: ${pct(cal80.raw)} · 90% window: ${pct(cal90.calibrated)}</div></div>
        <div class="card tile"><div class="label">Times the time moved (last 3 h)</div><div class="value">${(vol.pub_rev || 0).toFixed(2)}</div><div class="delta">today's ETA: ${(vol.b0_changes || 0).toFixed(2)} changes, ${(vol.b0_slips || 0).toFixed(2)} of them later</div></div>
        <div class="card tile"><div class="label">Promise kept 1 h before</div><div class="value">${pct(vol.kept_60 || 0)}</div><div class="delta">${A.fmt(vol.n || 0)} real arrivals, 6 days never seen in training</div></div>
        <div class="card tile"><div class="label">Timetable optimism</div><div class="value">${(b0.bias).toFixed(1)} → ${lad.find(l => l.key === "B1").bias.toFixed(1)}</div><div class="delta">min late on average vs forecast: today / crediting all recovery time</div></div>
      </div>

      <div class="grid g-2-1" style="margin-top:16px">
        <div class="card"><h3>The ablation ladder</h3><div class="sub">Held-out test week, 25–30 Sep 2024. Each layer had to beat the one below on separate validation days (19–21 Sep) before it could ship.</div>
          <table class="lad"><thead><tr><th>Forecaster</th><th>MAE (min)</th><th>90th pct error</th><th>Bias</th><th>80% window coverage</th><th>Width (min)</th></tr></thead><tbody>
          ${lad.map(l => `<tr class="${l.key === R.production ? "prod" : ""}"><td>${l.key} · ${A.esc(l.name)}${l.key === R.production ? " · <b>ships</b>" : ""}</td><td>${l.mae.toFixed(2)}</td><td>${l.p90_abs.toFixed(0)}</td><td>${l.bias >= 0 ? "+" : ""}${l.bias.toFixed(1)}</td><td>${l.cov80 != null ? pct(l.cov80) + (l.cov80_raw != null ? ` <span class="muted">(raw ${pct(l.cov80_raw)})</span>` : "") : "n/a (single time)"}</td><td>${l.width80 != null ? l.width80.toFixed(0) : "–"}</td></tr>`).join("")}
          </tbody></table>
          <div id="pfMae" style="margin-top:14px"></div></div>
        <div class="card"><h3>What did not ship, and why that's the point</h3><div class="sub">The deck promised "baseline first; the topological layer ships only if an ablation proves it earns its place." It was run.</div>
          ${R.verdicts.map(v => `<div class="verdict"><span class="badge ${v.ships ? "yes" : "no"}">${v.ships ? "SHIPS" : "HELD BACK"}</span><div><b>${v.layer === "M2" ? "Network layer" : "Topology layer"}</b> (${v.layer} over ${v.over}): ${v.val_pinball_gain_pct >= 0 ? "+" : ""}${v.val_pinball_gain_pct.toFixed(2)}% on validation, better on ${v.val_days_better}/${v.val_days} days. Threshold: ≥1% and ≥2 of 3 days.</div></div>`).join("")}
          <p class="ink2" style="font-size:12.5px;margin:10px 0 0">Why: public data only logs <b>halts</b> (every 30–80 km), so "the train ahead" is inferred, not observed. The deck's real inputs (30 s positions, block occupancy, signal aspects) are exactly what's missing. The one place it clearly helps is heavy rain on the path (−3.4% error, on 2.5% of forecasts); a slower train close ahead makes no measurable difference at halt-level resolution. The network view still drives the controller's hold/let-run calls and the explanations.</p>
          <div class="verdict"><span class="badge yes">FOUND</span><div><b>Rake links matter.</b> In ${A.fmt(rake.n || 0)} inferred turnarounds, when the incoming rake ate into the turnaround (${rake.n_tight} cases) the return working ran a median <b>${Math.round(rake.out_delay_tight || 0)} min</b> late two stops later, vs <b>${Math.round(rake.out_delay_loose || 0)} min</b> otherwise (r = ${(rake.corr || 0).toFixed(2)}). The CRIS rake-link table is the highest-value data to add.</div></div>
        </div>
      </div>

      <div class="grid g-3" style="margin-top:16px">
        <div class="card"><h3>Are the windows honest?</h3><div class="sub">Share of real arrivals inside the window, by promised level. Conformal calibration moves every point onto the line.</div><div id="pfCal"></div>
          <div class="legend"><span><i class="box" style="background:var(--up)"></i>raw model quantiles</span><span><i class="box" style="background:var(--dn)"></i>after conformal calibration</span></div></div>
        <div class="card"><h3>How early can we tell?</h3><div class="sub">Error by time left until the real arrival. Today's ETA only learns about a delay once it has happened.</div><div id="pfLead"></div></div>
        <div class="card"><h3>The optimism bias, measured</h3><div class="sub">Trains running 15+ min late: recovery the timetable allows vs what the route actually gave back, by arrival station.</div><div id="pfOpt"></div>
          <div class="legend"><span><i class="box" style="background:var(--up)"></i>timetable promises</span><span><i class="box" style="background:var(--dn)"></i>route gave</span></div></div>
      </div>

      ${E.passenger_sim ? `<div class="card" style="margin-top:16px"><div class="card-head"><div><h3>What a boarding passenger would have lived through</h3>
        <div class="sub">Every real arrival in the test week (${A.fmt(E.passenger_sim.saarthi.n)}). The passenger checks 90 minutes before the train actually came and chooses when to be on the platform. <b>Missed</b> = the train had already left.</div></div></div>
        <table class="lad"><thead><tr><th>How they decided</th><th>Missed the train</th><th>Median wait on the platform</th><th>Bad-day wait (90th pct)</th></tr></thead><tbody>
        ${[["timetable", "Went by the printed time (10 min early)"], ["today", "Trusted today's ETA (10 min early)"], ["saarthi", "Followed SAARTHI's leave-by"]].map(([k, l]) => {
          const x = E.passenger_sim[k];
          return `<tr class="${k === "saarthi" ? "prod" : ""}"><td>${l}</td><td>${(100 * x.missed).toFixed(1)}%</td><td>${Math.round(x.wait_med)} min</td><td>${Math.round(x.wait_p90)} min</td></tr>`;
        }).join("")}</tbody></table>
        <p class="ink2" style="font-size:12.5px;margin:10px 0 0">Going by the timetable almost never misses, but it's how people end up waiting hours on a platform. Trusting a single-number ETA cuts the wait but misses the train when it makes up time. SAARTHI keeps the miss rate near the timetable's while cutting the long waits. That's the "leave now or wait" promise, measured.</p></div>` : ""}

      <div class="grid g-2-1" style="margin-top:16px">
        <div class="card"><h3>"20 minutes", five times in a row</h3><div class="sub">For each real arrival: how often the time was restated later by 5+ min in the final three hours. ${pct(vol.share_b0_3plus || 0)} of arrivals got 3+ such slips from today's ETA, vs ${pct(vol.share_pub_3plus || 0)} from SAARTHI.</div><div id="pfVol"></div>
          <div class="legend"><span><i class="box" style="background:var(--up)"></i>today's single-number ETA</span><span><i class="box" style="background:var(--dn)"></i>SAARTHI published window</span></div></div>
        <div class="card"><h3>Which reports to trust</h3>
          ${E.dataset?.quality ? `<div class="verdict" style="border-top:0;padding-top:0"><span class="badge yes">FOUND</span><div><b>${A.fmt(E.dataset.quality.phantom)} records (${E.dataset.quality.phantom_pct.toFixed(1)}%) were placeholders</b>: a missing report arrives as "actual = scheduled, 0 min late", e.g. 509 min late at Kanpur, then "on time" at New Delhi. They touched ${A.fmt(E.dataset.quality.trips_with_phantom)} of ${A.fmt(E.dataset.quality.trips)} trips. Left in, they teach impossible recoveries and score correct forecasts as wrong. SAARTHI treats them as missing.</div></div>` : ""}
          <div class="sub">Share of each station's logged times that imply a physically impossible run (faster than 70% of the fastest scheduled). The model learns the reporting habit.</div>
          <table class="lad"><thead><tr><th>Station</th><th>Reports</th><th>Implausible</th><th>Excess rounding</th></tr></thead><tbody>
          ${(E.reliability || []).slice(0, 8).map(r => `<tr><td>${A.esc(r.name)}</td><td>${A.fmt(r.n)}</td><td>${(100 * r.implausible).toFixed(1)}%</td><td>${(100 * r.round5).toFixed(1)}%</td></tr>`).join("")}
          </tbody></table></div>
      </div>

      <div class="grid g-2-1" style="margin-top:16px">
        <div class="card"><h3>What the production model listens to</h3><div class="sub">Gain importance of the median model. The route's learned recovery beats the train's current delay.</div><div id="pfImp"></div></div>
        <div class="card"><h3>What's real in this prototype</h3>
          <table class="honest" style="width:100%;border-collapse:collapse">
          <tr><td class="tag-real">REAL</td><td>Every scheduled and actual arrival (RSTGCN dataset: Chowdhury, Koley, Chakraborty, Ghosh, IIT Kharagpur / IIIT Bhubaneswar, IEEE T-ITS). ${A.fmt(E.dataset?.corridor_reports || 0)} reports, ${E.dataset?.corridor_trains} trains, ${E.dataset?.stations} stations, ${Math.round(E.dataset?.km || 0)} km.</td></tr>
          <tr><td class="tag-real">REAL</td><td>Hourly rain per station, Sept 2024 (Open-Meteo ERA5 reanalysis, standing in for the IMD feed).</td></tr>
          <tr><td class="tag-real">REAL</td><td>Station coordinates (datameet/railways), chainage solved from route distances (Kanpur 441 km, actual 440).</td></tr>
          <tr><td class="tag-inf">CLEANED</td><td>Zero-filled placeholder records removed as missing (physically impossible recoveries).</td></tr>
          <tr><td class="tag-inf">INFERRED</td><td>Train positions between halts, train ahead, block occupancy, rake pairs (odd/even convention).</td></tr>
          <tr><td class="tag-sim">ASSUMED</td><td>Platform numbers, passenger loads per train class, 6-min headway, DLT IDs and the missed-call number.</td></tr>
          <tr><td class="tag-sim">NOT SENT</td><td>No SMS or call leaves this laptop.</td></tr>
          </table>
          <p class="ink2" style="font-size:12.5px;margin:10px 0 0"><b>Limits.</b> September has no fog; the winter IMD fog feed is the biggest untested input. Departure delay equals arrival delay in 100% of source rows, so dwell overruns are invisible. Early arrivals are recorded as 0 minutes late.</p></div>
      </div>`;
    hbars(A.$("pfMae"), lad.map(l => ({ label: `${l.key} · ${l.name}`, v: l.mae, key: l.key })), { unit: " min", fmt: v => v.toFixed(1), hl: r => r.key === R.production });
    calib(A.$("pfCal"), R.calibration);
    const lead = R.lead.filter(r => r.hi <= 300);
    lines(A.$("pfLead"), lead.map(r => r.hi), [{ name: "today's ETA", v: lead.map(r => r.mae_b0), c: "var(--up)" }, { name: "SAARTHI", v: lead.map(r => r.mae_prod), c: "var(--dn)" }], { xl: "minutes before arrival (bin end)", yl: "mean error, min" });
    dumbbell(A.$("pfOpt"), E.optimism || []);
    const cats = ["0", "1", "2", "3", "4", "5+"];
    const dist = (o, n) => { const v = [0, 0, 0, 0, 0, 0]; for (const [k, c] of Object.entries(o || {})) v[Math.min(5, +k)] += c; return v.map(x => 100 * x / (n || 1)); };
    groupedBars(A.$("pfVol"), cats, [{ name: "today's ETA", v: dist(vol.b0_slip_dist, vol.n), c: "var(--up)" }, { name: "SAARTHI", v: dist(vol.pub_rev_dist, vol.n), c: "var(--dn)" }]);
    const NM = { hist_train: "this train's own history on this stretch", delay: "current delay", tt_slack: "timetable recovery time", dmax: "worst delay so far", tgt: "which station", pair_med: "all trains' history on this stretch", speed: "train speed class", d_origin: "delay at origin", pair_q90: "bad-day history on this stretch", trend: "delay trend (last report)", dow: "day of week", trend2: "delay trend (2 reports)", hod_c: "time of day", hod_s: "time of day (phase)", hist_n: "how much history", h_sch: "scheduled time to go", overdue: "overdue at next station", age: "minutes since last report", km_rem: "distance to go", n_halts: "halts to go", is_terminal: "terminal arrival", priority: "priority", dir: "direction", src_in_corr: "report from inside corridor" };
    hbars(A.$("pfImp"), R.importance.slice(0, 10).map(r => ({ label: NM[r.feature] || r.feature, v: 100 * r.gain / R.importance.reduce((s, x) => s + x.gain, 0) })), { unit: "%", fmt: v => v.toFixed(0) });
  }
  return { render };
})();
