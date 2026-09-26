/* Control room: tiles, live corridor strip, time-distance chart, hold/let-run, train drawer. */
App.views.control = (() => {
  const A = App;
  let mareyDir = 0, decisions = {}, hoverRec = null, drawerTarget = null;

  function tiles(st) {
    const s = st.stats;
    const t = [
      [A.lang === "hi" ? "कॉरिडोर पर गाड़ियाँ" : "Trains on the corridor", s.on_corridor, A.lang === "hi" ? "दोनों दिशाओं में" : "both directions, dead-reckoned"],
      [A.lang === "hi" ? "औसत (मध्य) देरी" : "Median delay now", `${Math.round(s.median_delay)} min`, A.lang === "hi" ? "कॉरिडोर पर" : "across trains on the trunk"],
      [A.lang === "hi" ? "60+ मिनट देर" : "Running 60+ min late", s.late60, `${Math.round(100 * s.late60 / Math.max(1, s.on_corridor))}% ${A.lang === "hi" ? "गाड़ियाँ" : "of trains"}`],
      [A.lang === "hi" ? "स्थिर वादे" : "Windows never revised", `${Math.round(100 * s.stable_share)}%`, `${s.windows} ${A.lang === "hi" ? "प्रकाशित विंडो" : "live published windows"}`],
      [A.lang === "hi" ? "रोकें/चलने दें सुझाव" : "Hold / let-run calls", s.recs, A.lang === "hi" ? "अगले 45 मिनट में" : "decisions due in the next 45 min"],
    ];
    A.$("ctlTiles").innerHTML = t.map(([l, v, d]) => `<div class="card tile"><div class="label">${l}</div><div class="value">${v}</div><div class="delta">${d}</div></div>`).join("");
  }

  function strip(st) {
    const box = A.$("strip");
    const W = Math.max(700, box.clientWidth || 1200), H = 190, L = 96, R = 28;
    const kms = A.meta.stations.map(s => s.km), X = A.lin(0, kms[kms.length - 1], L, W - R);
    box.innerHTML = "";
    const g = A.svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Corridor map" }, box);
    const yD = 64, yU = 112;
    // hotspots (context only)
    for (const h of st.hot) {
      const x = X(kms[h.ci]), y = h.dir === 1 ? yD : yU, r = Math.min(46, 12 + h.pers * 0.8);
      const e = A.svg("ellipse", { cx: x, cy: y, rx: r, ry: 13, fill: "var(--serious)", opacity: 0.16 }, g);
      A.bindTip(e, () => `<b>Persistent hotspot · ${A.esc(A.sname(A.meta.stations[h.ci].code))}</b><br>${h.dir === 1 ? "Towards Prayagraj" : "Towards Delhi"} trains here have lost ${Math.round(h.pers)} min more than usual, and it persists across the last 3 h (H0 persistence).<br><span class="muted">Topology layer: shown as context; it did not earn a place in the forecast.</span>`);
    }
    // tracks
    for (const [y, lab] of [[yD, A.lang === "hi" ? "प्रयागराज →" : "to Prayagraj →"], [yU, A.lang === "hi" ? "← दिल्ली" : "← to Delhi"]]) {
      A.svg("line", { x1: L, x2: W - R, y1: y, y2: y, stroke: "var(--axis)", "stroke-width": 3, "stroke-linecap": "round" }, g);
      A.text(g, 6, y + 4, lab, { "font-size": 11.5, fill: "var(--ink-2)", "font-weight": 600 });
    }
    const big = new Set(["NDLS", "GZB", "ALJN", "TDL", "ETW", "CNB", "PRYJ"]);
    let lastX = [-1e9, -1e9], lastName = -1e9;
    A.meta.stations.forEach((s, i) => {
      const x = X(s.km);
      const row = x - lastX[0] < 30 ? 1 : 0;
      lastX[row] = x;
      A.svg("line", { x1: x, x2: x, y1: yD - 6, y2: yU + 6, stroke: "var(--axis)", "stroke-width": big.has(s.code) ? 1.5 : 1 }, g);
      A.svg("circle", { cx: x, cy: yD, r: big.has(s.code) ? 4.5 : 3, fill: "var(--surface)", stroke: "var(--ink-2)", "stroke-width": 1.5 }, g);
      A.svg("circle", { cx: x, cy: yU, r: big.has(s.code) ? 4.5 : 3, fill: "var(--surface)", stroke: "var(--ink-2)", "stroke-width": 1.5 }, g);
      A.text(g, x, 146 + row * 13, s.code, { "font-size": 10.5, "text-anchor": "middle", fill: big.has(s.code) ? "var(--ink)" : "var(--muted)", "font-weight": big.has(s.code) ? 650 : 400 });
      if (big.has(s.code) && row === 0 && x - lastName > 70) {
        lastName = x;
        A.text(g, x, 172, A.lang === "hi" ? s.hi : s.name.replace(" Jn", "").replace(" Central", ""), { "font-size": 10, "text-anchor": "middle", fill: "var(--muted)", class: A.lang === "hi" ? "hi" : "" });
      }
      const rain = st.rain[i];
      if (rain >= 0.5) {
        const d = A.svg("path", { d: `M${x} ${22} c 4 6 6 9 6 12 a6 6 0 0 1 -12 0 c0 -3 2 -6 6 -12z`, fill: "var(--rain)", opacity: Math.min(1, 0.35 + rain / 8) }, g);
        A.bindTip(d, () => `<b>${A.esc(s.name)}</b><br>Rain ${rain} mm in the last hour (ERA5 reanalysis)`);
      }
    });
    A.text(g, L, 186, "0 km", { "font-size": 10, fill: "var(--muted)", "text-anchor": "middle" });
    A.text(g, W - R, 186, `${Math.round(kms[kms.length - 1])} km`, { "font-size": 10, fill: "var(--muted)", "text-anchor": "middle" });
    // trains
    for (const tr of st.trains) {
      if (tr.x < -5 || tr.x > kms[kms.length - 1] + 5) continue;
      const x = X(Math.max(0, Math.min(kms[kms.length - 1], tr.x))), y = tr.dir === 1 ? yD - 14 : yU + 14;
      const sel = A.sel === tr.tid, s = sel ? 1.5 : 1;
      const mk = A.svg("g", { class: "train-mk", transform: `translate(${x},${y})` }, g);
      const p = tr.dir === 1 ? `M${-7 * s} ${-6 * s} L${7 * s} 0 L${-7 * s} ${6 * s} Z` : `M${7 * s} ${-6 * s} L${-7 * s} 0 L${7 * s} ${6 * s} Z`;
      A.svg("path", { d: p, fill: A.scolor(tr.delay), stroke: "var(--surface)", "stroke-width": 2, "stroke-linejoin": "round", class: "mk-body" }, mk);
      A.svg("circle", { r: 13, fill: "transparent" }, mk);
      if (sel) A.text(mk, 0, tr.dir === 1 ? -12 : 20, String(tr.no), { "font-size": 11, "text-anchor": "middle", fill: "var(--ink)", "font-weight": 700 });
      mk.addEventListener("click", () => select(tr.tid));
      A.bindTip(mk, () => {
        const nx = tr.fc[0];
        return `<b>${tr.no} ${A.esc(A.lang === "hi" ? tr.name_hi : tr.name)}</b><br>${A.chip(tr.delay)} <span class="muted">${A.esc(tr.cls)}</span><br>` +
          `Last report ${A.esc(tr.last)} · ${tr.age} min ago${tr.overdue > 0 ? ` · <b>overdue ${tr.overdue} min</b>` : ""}<br>` +
          (nx ? `Next: <b>${A.esc(A.sname(nx.st))}</b> ${A.c24(nx.pub[0])}–${A.c24(nx.pub[1])}` : "") +
          (tr.ahead ? `<br><span class="muted">Train ahead: ${tr.ahead}, ${tr.ahead_gap} km, ${tr.ahead_delay} min late</span>` : "") + `<br><span class="muted">Click for details</span>`;
      });
    }
    A.$("stripLegend").innerHTML = [["good", "< 15 min"], ["warn", "15–60"], ["serious", "1–3 h"], ["critical", "3 h+"]]
      .map(([k, l]) => `<span><i class="box" style="background:var(--${k})"></i>${l}</span>`).join("") +
      `<span><i class="box" style="background:var(--rain)"></i>${A.lang === "hi" ? "बारिश" : "rain"}</span><span><i class="box" style="background:var(--serious);opacity:.3"></i>${A.lang === "hi" ? "हॉटस्पॉट" : "hotspot"}</span>`;
  }

  function marey(st) {
    const box = A.$("marey");
    const W = Math.max(600, box.clientWidth || 900), H = 470, L = 56, R = 14, T = 10, B = 26;
    const kms = A.meta.stations.map(s => s.km);
    const t0 = A.t - 180, t1 = A.t + 180;
    const X = A.lin(t0, t1, L, W - R), Y = A.lin(0, kms[kms.length - 1], T, H - B);
    box.innerHTML = "";
    const g = A.svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Time-distance chart" }, box);
    const clip = A.svg("clipPath", { id: "mclip" }, A.svg("defs", {}, g));
    A.svg("rect", { x: L, y: 0, width: W - L - R, height: H - B + 4 }, clip);
    const big = new Set(["NDLS", "GZB", "ALJN", "TDL", "ETW", "CNB", "PRYJ"]);
    const ax = A.svg("g", { class: "ax" }, g);
    A.meta.stations.forEach(s => {
      if (!big.has(s.code) && W < 900) return;
      A.svg("line", { x1: L, x2: W - R, y1: Y(s.km), y2: Y(s.km), class: "gridl" }, ax);
      A.text(ax, L - 6, Y(s.km) + 3.5, s.code, { "text-anchor": "end", "font-weight": big.has(s.code) ? 650 : 400 });
    });
    for (let h = Math.ceil(t0 / 60) * 60; h <= t1; h += 60) {
      A.svg("line", { x1: X(h), x2: X(h), y1: T, y2: H - B, class: "gridl" }, ax);
      A.text(ax, X(h), H - 8, A.c24(h), { "text-anchor": "middle" });
    }
    const plot = A.svg("g", { "clip-path": "url(#mclip)" }, g);
    const byTid = Object.fromEntries(st.trains.map(t => [t.tid, t]));
    const hl = new Set();
    if (hoverRec) { hl.add(hoverRec.leader); hoverRec.followers.forEach(f => hl.add(f.no)); }
    const order = Object.entries(st.marey).sort(([a], [b]) => (+a === A.sel) - (+b === A.sel));
    for (const [tid, m] of order) {
      const tr = byTid[tid]; if (!tr) continue;
      if (mareyDir && tr.dir !== mareyDir) continue;
      const sel = +tid === A.sel, hot = hl.has(tr.no);
      const col = tr.dir === 1 ? "var(--dn)" : "var(--up)";
      const op = sel || hot ? 1 : (A.sel || hoverRec ? 0.22 : 0.55);
      if (sel && m.fut.length) {
        const up = [[A.t, tr.x], ...m.fut.map(f => [f[2], f[1]])], dn = [[A.t, tr.x], ...m.fut.map(f => [f[3], f[1]])];
        const pts = up.map(p => `${X(p[0])},${Y(p[1])}`).concat(dn.reverse().map(p => `${X(p[0])},${Y(p[1])}`));
        A.svg("polygon", { points: pts.join(" "), fill: col, opacity: 0.12 }, plot);
      }
      const past = m.past.filter(p => p[1] >= -20 && p[1] <= kms[kms.length - 1] + 20);
      if (past.length > 1) A.svg("polyline", { points: past.map(p => `${X(p[0])},${Y(p[1])}`).join(" "), fill: "none", stroke: col, "stroke-width": sel || hot ? 2.5 : 1.5, opacity: op, "stroke-linejoin": "round" }, plot);
      if (m.fut.length) {
        const fut = [[A.t, tr.x], ...m.fut.map(f => [f[0], f[1]])];
        A.svg("polyline", { points: fut.map(p => `${X(p[0])},${Y(p[1])}`).join(" "), fill: "none", stroke: col, "stroke-width": sel || hot ? 2.5 : 1.5, "stroke-dasharray": "5 4", opacity: op }, plot);
      }
      if (tr.x >= 0 && tr.x <= kms[kms.length - 1]) A.svg("circle", { cx: X(A.t), cy: Y(tr.x), r: sel ? 5 : 3.5, fill: col, stroke: "var(--surface)", "stroke-width": 2, opacity: Math.max(op, .6) }, plot);
      // wide transparent hit path
      const all = [...past, [A.t, tr.x], ...m.fut.map(f => [f[0], f[1]])];
      const hit = A.svg("polyline", { points: all.map(p => `${X(p[0])},${Y(p[1])}`).join(" "), fill: "none", stroke: "transparent", "stroke-width": 12, style: "cursor:pointer" }, plot);
      hit.addEventListener("click", () => select(+tid));
      A.bindTip(hit, () => `<b>${tr.no} ${A.esc(tr.name)}</b><br>${A.chip(tr.delay)} · ${tr.dir === 1 ? "→ Prayagraj" : "→ Delhi"}<br><span class="muted">${A.esc(tr.cls)} · ~${A.fmt(tr.load)} passengers</span>`);
    }
    A.svg("line", { x1: X(A.t), x2: X(A.t), y1: T, y2: H - B, stroke: "var(--ink)", "stroke-width": 1.5 }, g);
    A.text(g, X(A.t) + 4, T + 10, A.lang === "hi" ? "अभी" : "now", { "font-size": 11, fill: "var(--ink)", "font-weight": 650 });
    A.$("mareyLegend").innerHTML = `<span><i style="background:var(--dn)"></i>${A.lang === "hi" ? "प्रयागराज की ओर" : "towards Prayagraj"}</span><span><i style="background:var(--up)"></i>${A.lang === "hi" ? "दिल्ली की ओर" : "towards Delhi"}</span>` +
      `<span><i style="background:var(--ink-2)"></i>${A.lang === "hi" ? "हुआ" : "actual"}</span><span><i style="background:repeating-linear-gradient(90deg,var(--ink-2) 0 5px,transparent 5px 9px)"></i>${A.lang === "hi" ? "पूर्वानुमान (माध्य)" : "forecast median"}</span><span><i class="box" style="background:var(--accent);opacity:.25"></i>${A.lang === "hi" ? "चुनी गाड़ी की 80% विंडो" : "selected train · 80% window"}</span>`;
  }

  function recs(st) {
    const box = A.$("recs");
    if (!st.recs.length) { box.innerHTML = `<div class="empty">${A.lang === "hi" ? "अभी कोई टकराव नहीं।" : "No precedence conflicts forecast in the next 45 minutes."}</div>`; return; }
    box.innerHTML = st.recs.map((r, i) => {
      const id = `${r.leader}@${r.at}`;
      const d = decisions[id];
      const fl = r.followers.map(f => `<b>${f.no}</b> ${A.esc(f.name)}`).join(" and ");
      const head = r.kind === "hold"
        ? `Loop <b>${r.leader} ${A.esc(r.leader_name)}</b> at ${A.esc(r.at_name)} for <b>${r.hold_min} min</b>`
        : `Let <b>${r.leader} ${A.esc(r.leader_name)}</b> run: don't loop it at ${A.esc(r.at_name)}`;
      const body = r.kind === "hold"
        ? `so ${fl} pass on the main line through block ${r.at}–${r.nxt}, instead of crawling behind it.`
        : `Looping it would make ${A.fmt(r.leader_load)} people wait ${r.hold_min} min to save ${fl} ${r.train_min_run} train-min.`;
      const rows = r.followers.map(f => `<tr><td>${f.no} ${A.esc(f.cls)} trails ${r.leader} (if it runs)</td><td>+${f.loss} min × ${A.fmt(f.load)}</td></tr>`).join("") +
        `<tr><td>${r.leader} held ${r.hold_min} min (if looped)</td><td>+${r.hold_min} min × ${A.fmt(r.leader_load)}</td></tr>` +
        `<tr><td class="net">Net saving by ${r.kind === "hold" ? "looping" : "letting it run"}</td><td class="net">${A.fmt(r.saving)} passenger-min</td></tr>`;
      const disagree = r.prio_rule !== r.kind;
      return `<div class="rec ${d || ""}" data-i="${i}">
        <div class="rec-kind ${r.kind}">${r.kind === "hold" ? "Hold" : "Let run"} · decide by ${A.c24(r.when)}</div>
        <h4>${head}</h4><p>${body}</p><table>${rows}</table>
        ${disagree ? `<p class="note" style="margin-top:8px">Priority rules alone would <b>${r.prio_rule === "hold" ? "loop" : "run"}</b> ${r.leader}. SAARTHI counts people, including the general-class passengers on ${r.leader_cls === "Mail/Express" || r.leader_cls === "Special" ? r.leader : "the slower train"}.</p>` : ""}
        <div class="actions">${d ? `<span class="note">${d === "accepted" ? "✓ Accepted. Logged for the audit trail." : "Dismissed. Logged with your reason."}</span>` :
          `<button class="btn primary" data-act="accepted">Accept</button><button class="btn" data-act="dismissed">Dismiss</button>`}
          <span class="note" style="margin-left:auto">basis: median paths cross in ${r.at}–${r.nxt}; headway 6 min</span></div></div>`;
    }).join("");
    box.querySelectorAll(".rec").forEach(el => {
      const r = st.recs[+el.dataset.i];
      el.addEventListener("mouseenter", () => { hoverRec = r; marey(st); });
      el.addEventListener("mouseleave", () => { hoverRec = null; marey(st); });
      el.querySelectorAll("button[data-act]").forEach(b => b.onclick = () => { decisions[`${r.leader}@${r.at}`] = b.dataset.act; recs(st); });
    });
  }

  async function drawer(st) {
    const box = A.$("drawer");
    if (A.sel == null || !st.trains.find(t => t.tid === A.sel)) {
      const cand = st.trains.filter(t => t.fc.length >= 2 && t.x > 20 && t.x < 600 && t.age < 90 && t.delay >= 15 && t.delay <= 150)
        .sort((a, b) => b.fc.length - a.fc.length || b.delay - a.delay);
      const any = st.trains.filter(t => t.fc.length && t.x > 0 && t.x < 630);
      A.sel = cand.length ? cand[0].tid : any.length ? any[0].tid : null;
      if (A.sel == null) { box.innerHTML = `<div class="empty">Select a train on the corridor.</div>`; return; }
    }
    const d = await A.api("train", { date: A.date, tid: A.sel, t: A.t });
    const live = d.live;
    if (!live) { box.innerHTML = `<div class="empty">This train has left the corridor.</div>`; return; }
    const fcs = live.fc;
    if (!drawerTarget || !fcs.find(f => f.st === drawerTarget)) drawerTarget = (fcs.find(f => ["CNB", "PRYJ", "NDLS", "ETW", "TDL", "ALJN", "GZB"].includes(f.st)) || fcs[fcs.length - 1]).st;
    const lo = Math.min(A.t, ...fcs.map(f => f.sch)) - 10, hi = Math.max(...fcs.map(f => Math.max(f.cq[6], f.eta0))) + 10;
    const rowsHtml = fcs.map(f => {
      const pos = v => `${(100 * (v - lo) / (hi - lo)).toFixed(2)}%`;
      const conf = f.pub[1] - f.pub[0] <= 30 ? "high" : f.pub[1] - f.pub[0] <= 60 ? "medium" : "low";
      return `<tr data-st="${f.st}" style="cursor:pointer${f.st === drawerTarget ? ";background:var(--accent-wash)" : ""}"><td style="width:110px"><b>${A.esc(A.sname(f.st))}</b><br><span class="muted num" style="font-size:11px">sch ${A.c24(f.sch)}</span></td>
        <td><div class="bar-track">
          <div style="position:absolute;left:${pos(f.cq[0])};width:calc(${pos(f.cq[6])} - ${pos(f.cq[0])});top:9px;height:4px;background:var(--accent);opacity:.18;border-radius:2px"></div>
          <div style="position:absolute;left:${pos(f.pub[0])};width:calc(${pos(f.pub[1])} - ${pos(f.pub[0])});top:4px;height:14px;background:var(--accent);opacity:.85;border-radius:4px"></div>
          <div title="today's ETA" style="position:absolute;left:${pos(f.eta0)};top:0;height:22px;width:2px;background:var(--ink)"></div>
          <div title="timetable" style="position:absolute;left:${pos(f.sch)};top:6px;height:10px;width:2px;background:var(--muted)"></div>
        </div></td>
        <td class="num" style="width:120px;text-align:right"><b>${A.c24(f.pub[0])}–${A.c24(f.pub[1])}</b><br><span class="muted" style="font-size:11px">today: ${A.c24(f.eta0)}</span></td><td style="width:84px">${A.confChip(conf)}</td></tr>`;
    }).join("");
    const RS = {
      route: v => v < 0 ? ["Route gives time back", "timetable padding this train really uses here (learned, not assumed)"] : ["This stretch costs time", "what this train usually loses here (learned from 21 days)"],
      trend: v => v > 0 ? ["Losing time lately", "delay grew over its last reports"] : ["Making up time lately", "delay shrank over its last reports"],
      silence: () => ["No recent report", "overdue at its next station, so the range widens"],
      late_recovers: v => v < 0 ? ["Late trains recover", "moderately late trains use padding to catch up"] : ["Very late trains lose priority", "trains this late get looped for others and slip further"],
      time_of_day: v => v > 0 ? ["Busy hour", "traffic pattern for this hour"] : ["Quiet hour", "traffic pattern for this hour"],
      train_type: () => ["Train type", "priority and speed class"], other: () => ["Other", ""] };
    const tf = fcs.find(f => f.st === drawerTarget);
    const why = (tf.reasons || []).map(([k, v]) => `<div class="reason"><span><b>${RS[k] ? RS[k](v)[0] : k}</b><br><span class="muted" style="font-size:11.5px">${RS[k] ? RS[k](v)[1] : ""}</span></span><span class="mins" style="color:${v > 0 ? "var(--crit-ink)" : "var(--good-ink)"}">${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(0)} min</span></div>`).join("") || `<div class="muted" style="font-size:12.5px;padding:6px 0">Carries its current delay forward; nothing on this stretch moves it much.</div>`;
    box.innerHTML = `<div class="drawer">
      <div>
        <div class="th"><span class="no">${live.no}</span><span class="nm">${A.esc(A.lang === "hi" ? live.name_hi : live.name)}</span>${A.chip(live.delay)}<span class="muted">${A.esc(d.trip.origin)} → ${A.esc(d.trip.dest)} · ${A.esc(live.cls)} · ~${A.fmt(live.load)} passengers</span></div>
        <div class="muted" style="margin:4px 0 12px;font-size:12.5px">Last report <b>${A.esc(live.last)}</b> at ${A.c24(live.last_t)} (${live.age} min ago)${live.overdue > 0 ? ` · <b style="color:var(--crit-ink)">overdue at ${A.esc(live.next)} by ${live.overdue} min</b>` : ""}. Bars: <b>published 80% window</b>, faint line = 90% range, black tick = today's single-number ETA, grey tick = timetable.</div>
        <table style="width:100%;border-collapse:collapse">${rowsHtml}</table>
      </div>
      <div>
        <h3 style="margin:0 0 4px">Why ${A.esc(A.sname(drawerTarget))} ${A.c24(tf.pub[0])}–${A.c24(tf.pub[1])}?</h3>
        <div class="sub" style="margin-bottom:4px">Model attributions (SHAP) for the median, grouped into causes a person can check.</div>
        ${why}
        <div class="reason" style="border-top:1px solid var(--grid)"><span><b>Network context</b><br><span class="muted" style="font-size:11.5px">${d.ahead ? `train ahead ${d.ahead.no}: ${d.ahead.gap} km, ${d.ahead.delay} min late` : "no train within 80 km ahead"}${live.rain >= 1 ? ` · rain on path ${live.rain} mm/3h` : ""}</span></span></div>
        <h3 style="margin:16px 0 2px">Promise history · ${A.esc(A.sname(drawerTarget))}</h3>
        <div class="sub" style="margin-bottom:4px">What each system told a waiting family, every 5 minutes so far.</div>
        <div id="promise"></div><div class="legend" id="promiseLegend"></div>
      </div></div>`;
    box.querySelectorAll("tr[data-st]").forEach(tr => tr.onclick = () => { drawerTarget = tr.dataset.st; drawer(st); });
    promise(d.hist[drawerTarget], tf);
  }

  function promise(h, tf) {
    const box = A.$("promise");
    if (!h || !h.raw.length) { box.innerHTML = `<div class="empty">No history yet.</div>`; return; }
    const W = Math.max(300, box.clientWidth || 420), H = 190, L = 44, R = 10, T = 8, B = 22;
    const ts = h.raw.map(r => r[0]);
    const t0 = ts[0], t1 = Math.max(A.t, t0 + 30);
    const vals = h.raw.flatMap(r => [r[1], r[3], r[4]]).concat(h.pub.flatMap(p => [p[1], p[2]])).concat(h.actual ? [h.actual] : []);
    const v0 = Math.min(...vals) - 5, v1 = Math.max(...vals) + 5;
    const X = A.lin(t0, t1, L, W - R), Y = A.lin(v0, v1, H - B, T);
    box.innerHTML = "";
    const g = A.svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, box);
    const ax = A.svg("g", { class: "ax" }, g);
    const step = (v1 - v0) > 120 ? 60 : 30;
    for (let v = Math.ceil(v0 / step) * step; v <= v1; v += step) { A.svg("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "gridl" }, ax); A.text(ax, L - 5, Y(v) + 3, A.c24(v), { "text-anchor": "end" }); }
    for (let v = Math.ceil(t0 / 60) * 60; v <= t1; v += 60) A.text(ax, X(v), H - 6, A.c24(v), { "text-anchor": "middle" });
    // raw 80% band
    const band = h.raw.map(r => `${X(r[0])},${Y(r[1])}`).concat(h.raw.slice().reverse().map(r => `${X(r[0])},${Y(r[3])}`));
    A.svg("polygon", { points: band.join(" "), fill: "var(--accent)", opacity: 0.1 }, g);
    // today's ETA
    A.svg("polyline", { points: h.raw.map(r => `${X(r[0])},${Y(r[4])}`).join(" "), fill: "none", stroke: "var(--up)", "stroke-width": 2 }, g);
    // published (step)
    const pubs = h.pub;
    for (let i = 0; i < pubs.length; i++) {
      const a = pubs[i][0], b = i + 1 < pubs.length ? pubs[i + 1][0] : t1;
      A.svg("rect", { x: X(a), y: Y(pubs[i][2]), width: Math.max(1, X(b) - X(a)), height: Math.max(1, Y(pubs[i][1]) - Y(pubs[i][2])), fill: "none", stroke: "var(--accent)", "stroke-width": 2, rx: 2 }, g);
    }
    if (h.actual) { A.svg("line", { x1: L, x2: W - R, y1: Y(h.actual), y2: Y(h.actual), stroke: "var(--good)", "stroke-width": 1.5 }, g); A.text(g, W - R - 2, Y(h.actual) - 4, `actual ${A.c24(h.actual)}`, { "text-anchor": "end", "font-size": 10.5, fill: "var(--good-ink)" }); }
    const changes0 = h.raw.reduce((n, r, i) => n + (i && Math.abs(r[4] - h.raw[i - 1][4]) >= 3 ? 1 : 0), 0);
    const revs = pubs.filter(p => ["earlier", "later", "expired"].includes(p[3])).length;
    const hit = A.svg("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent" }, g);
    const cross = A.svg("line", { y1: T, y2: H - B, stroke: "var(--ink-2)", "stroke-width": 1, opacity: 0 }, g);
    hit.addEventListener("pointermove", e => {
      const r = g.getBoundingClientRect(), tt = X.inv(e.clientX - r.left);
      const k = h.raw.reduce((b, x, i) => Math.abs(x[0] - tt) < Math.abs(h.raw[b][0] - tt) ? i : b, 0), row = h.raw[k];
      const p = pubs.filter(p => p[0] <= row[0]).pop();
      cross.setAttribute("x1", X(row[0])); cross.setAttribute("x2", X(row[0])); cross.setAttribute("opacity", 1);
      A.tip(e, `<b>At ${A.c24(row[0])}</b><div class="row"><span><span class="key" style="background:var(--accent)"></span>SAARTHI said</span><b>${p ? A.c24(p[1]) + "–" + A.c24(p[2]) : "—"}</b></div><div class="row"><span><span class="key" style="background:var(--up)"></span>Today's ETA said</span><b>${A.c24(row[4])}</b></div><div class="row"><span><span class="key" style="background:var(--accent);opacity:.3"></span>raw model 80%</span><span>${A.c24(row[1])}–${A.c24(row[3])}</span></div>`);
    });
    hit.addEventListener("pointerleave", () => { cross.setAttribute("opacity", 0); A.tip(null); });
    A.$("promiseLegend").innerHTML = `<span><i class="box" style="border:2px solid var(--accent);background:none"></i>SAARTHI published (${revs} revision${revs === 1 ? "" : "s"})</span><span><i style="background:var(--up)"></i>today's ETA (${changes0} changes)</span><span><i class="box" style="background:var(--accent);opacity:.25"></i>raw model 80%</span>${h.actual ? `<span><i style="background:var(--good)"></i>actual</span>` : ""}`;
  }

  function select(tid) { A.sel = tid; render(A.st); }

  async function render(st) {
    tiles(st); strip(st); marey(st); recs(st); await drawer(st);
  }
  function init() {
    document.querySelectorAll("#mareyDir button").forEach(b => b.onclick = () => {
      document.querySelectorAll("#mareyDir button").forEach(x => x.classList.toggle("on", x === b)); mareyDir = +b.dataset.dir; marey(A.st);
    });
    addEventListener("resize", () => { if (A.view === "control" && A.st) { strip(A.st); marey(A.st); } });
  }
  return { render, init };
})();
