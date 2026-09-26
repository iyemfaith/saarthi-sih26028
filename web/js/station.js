/* Station master view: arrivals on a shared clock, simulated platform plan with conflicts, PA scripts. */
App.views.station = (() => {
  const A = App;
  let code = "CNB";

  function init() {
    const sel = A.$("stnSel");
    sel.innerHTML = A.meta.stations.map(s => `<option value="${s.code}">${s.name} (${s.code})</option>`).join("");
    sel.value = code;
    sel.onchange = () => { code = sel.value; render(A.st); };
  }

  async function render() {
    const d = await A.api("station", { date: A.date, code, t: A.t });
    const arr = d.arrivals;
    const up = arr.filter(a => a.state !== "arrived");
    const next3 = up.filter(a => a.lo <= A.t + 180);
    A.$("stnTiles").innerHTML = [
      [A.lang === "hi" ? "अगले 3 घंटे में आगमन" : "Arrivals, next 3 h", next3.length, `${up.length} in 6 h`],
      [A.lang === "hi" ? "15+ मिनट देर" : "Running 15+ min late", next3.filter(a => a.delay >= 15).length, "of the next 3 h"],
      [A.lang === "hi" ? "प्लेटफॉर्म टकराव" : "Platform clashes predicted", d.conflicts.length, "before they happen"],
      [A.lang === "hi" ? "स्थिर, अब घोषित करें" : "Stable: announce now", d.announcements.filter(a => a.stable).length, `${d.announcements.length} late trains to announce`],
      [A.lang === "hi" ? "प्लेटफॉर्म" : "Platforms", d.platforms, d.halt ? "small halt: SMS/IVR first" : "planned (simulated)"],
    ].map(([l, v, s]) => `<div class="card tile"><div class="label">${l}</div><div class="value">${v}</div><div class="delta">${s}</div></div>`).join("");

    // arrivals table with a shared axis
    const lo = A.t - 30, hi = A.t + 360, pos = v => Math.max(0, Math.min(100, 100 * (v - lo) / (hi - lo)));
    const axis = [];
    for (let h = Math.ceil(lo / 60) * 60; h <= hi; h += 60) axis.push(`<span style="position:absolute;left:${pos(h)}%;transform:translateX(-50%);font-size:10px" class="muted num">${A.c24(h)}</span>`);
    const rows = arr.map(a => {
      const bar = a.state === "arrived"
        ? `<div style="position:absolute;left:${pos(a.act)}%;top:5px;width:10px;height:10px;border-radius:50%;background:var(--good);transform:translateX(-5px)" title="arrived"></div>`
        : `<div style="position:absolute;left:${pos(a.lo)}%;width:${Math.max(0.8, pos(a.hi) - pos(a.lo))}%;top:4px;height:12px;border-radius:4px;background:${a.state === "live" ? "var(--accent)" : "var(--axis)"};opacity:${a.state === "live" ? .85 : .7}"></div>` +
          (a.eta0 ? `<div title="today's ETA" style="position:absolute;left:${pos(a.eta0)}%;top:0;height:20px;width:2px;background:var(--ink)"></div>` : "") +
          `<div title="timetable" style="position:absolute;left:${pos(a.sch)}%;top:6px;height:8px;width:2px;background:var(--muted)"></div>`;
      const stateLbl = { arrived: `<span class="chip s-good"><span class="dot"></span>Arrived ${A.c24(a.act)}</span>`, live: A.chip(a.delay),
        typical: `<span class="chip"><span class="dot" style="background:var(--axis)"></span>No live report yet · typical</span>`, scheduled: `<span class="chip">Scheduled</span>` }[a.state];
      const why = a.why && a.why.length ? `<span class="muted" style="font-size:12px">${A.esc((A.lang === "hi" ? a.why_hi : a.why)[0])}</span>` :
        a.state === "typical" ? `<span class="muted" style="font-size:12px">From its last ${a.n_hist} runs; live window once it's within ~3 stops</span>` : "";
      return `<tr><td class="tno">${a.no}</td><td class="tname">${A.esc(A.lang === "hi" ? a.name_hi : a.name)}<small>${a.starts ? "<b>starts here</b> · " : ""}${A.esc(a.origin)} → ${A.esc(a.dest)}</small></td>
        <td class="num">${A.c24(a.sch)}</td><td class="num"><b>${a.state === "arrived" ? A.c24(a.act) : A.c24(a.lo) + "–" + A.c24(a.hi)}</b></td>
        <td style="min-width:260px"><div style="position:relative;height:20px">${bar}</div></td>
        <td>${a.state === "arrived" ? "" : A.confChip(a.conf)}</td><td class="num"><b>${a.pf || "–"}</b></td><td>${stateLbl}<br>${why}</td></tr>`;
    }).join("");
    A.$("arrTable").innerHTML = `<table class="arr"><thead><tr><th>Train</th><th>Name</th><th>Sched</th><th>Window</th><th><div style="position:relative;height:14px">${axis.join("")}</div></th><th>Confidence</th><th>PF</th><th>Status · why</th></tr></thead><tbody>${rows || `<tr><td colspan="8" class="empty">No arrivals in the next 6 hours.</td></tr>`}</tbody></table>`;
    A.$("arrLegend").innerHTML = `<span><i class="box" style="background:var(--accent)"></i>published window</span><span><i class="box" style="background:var(--axis)"></i>typical (not started)</span><span><i style="background:var(--ink);width:2px;height:12px"></i>today's ETA</span><span><i style="background:var(--muted);width:2px;height:10px"></i>timetable</span>`;

    gantt(d, up);
    A.$("conflicts").innerHTML = d.conflicts.map(c => `<div class="conflict"><b>PF ${c.pf}:</b> ${c.a} ${A.esc(c.a_name)} and ${c.b} ${A.esc(c.b_name)} both likely ${A.c24(c.overlap_from)}–${A.c24(c.overlap_to)}. ${c.move_to ? `Suggest moving <b>${c.b}</b> to <b>PF ${c.move_to}</b> (free then).` : "No free platform: plan a hold at the previous station."}</div>`).join("") ||
      `<div class="muted" style="font-size:12.5px;margin-top:8px">No platform clashes predicted in the next 4 hours.</div>`;
    A.$("anns").innerHTML = d.announcements.map(a => `<div class="ann ${a.stable ? "stable" : ""}"><div class="tag" style="color:${a.stable ? "var(--good-ink)" : "var(--muted)"}">${a.stable ? "✓ STABLE · ANNOUNCE NOW" : "WAIT · WINDOW STILL MOVING"} · ${a.no}</div><div class="hi" style="margin-top:4px">${A.esc(a.hi)}</div><div class="muted" style="margin-top:4px">${A.esc(a.en)}</div></div>`).join("") ||
      `<div class="empty">No late trains to announce right now.</div>`;
  }

  function gantt(d, up) {
    const box = A.$("gantt");
    const W = Math.max(500, box.clientWidth || 800), npf = d.platforms, rowH = 26, L = 44, R = 10, T = 18;
    const H = T + npf * rowH + 8, t0 = A.t, t1 = A.t + 240;
    const X = A.lin(t0, t1, L, W - R);
    box.innerHTML = "";
    const g = A.svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, box);
    const ax = A.svg("g", { class: "ax" }, g);
    for (let h = Math.ceil(t0 / 60) * 60; h <= t1; h += 60) { A.svg("line", { x1: X(h), x2: X(h), y1: T - 4, y2: H - 6, class: "gridl" }, ax); A.text(ax, X(h), 11, A.c24(h), { "text-anchor": "middle" }); }
    for (let p = 1; p <= npf; p++) A.text(ax, L - 8, T + (p - 1) * rowH + 17, `PF ${p}`, { "text-anchor": "end" });
    const clash = new Set(d.conflicts.flatMap(c => [c.a, c.b]));
    for (const a of up) {
      if (!a.pf || a.lo > t1) continue;
      const dwell = Math.max(2, a.sch_dep - a.sch);
      const x0 = X(Math.max(t0, a.lo)), x1 = X(Math.min(t1, a.hi + dwell));
      if (x1 <= L) continue;
      const y = T + (a.pf - 1) * rowH + 3;
      const r = A.svg("rect", { x: x0, y, width: Math.max(4, x1 - x0), height: rowH - 8, rx: 4, fill: a.state === "live" ? "var(--accent)" : "var(--axis)", opacity: a.state === "live" ? 0.85 : 0.6, stroke: clash.has(a.no) ? "var(--critical)" : "var(--surface)", "stroke-width": 2 }, g);
      if (x1 - x0 > 44) A.text(g, x0 + 5, y + 13, String(a.no), { "font-size": 11, fill: a.state === "live" ? "#fff" : "var(--ink)", "font-weight": 650 });
      A.bindTip(r, () => `<b>${a.no} ${A.esc(a.name)}</b><br>PF ${a.pf} · ${A.c24(a.lo)}–${A.c24(a.hi + dwell)}<br>${A.chip(a.delay)}`);
    }
  }
  return { init, render };
})();
