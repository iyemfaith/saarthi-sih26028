/* Passenger tab: the real phone app (iframe), the SMS on a feature phone, the 139 call, the message log. */
App.views.passenger = (() => {
  const A = App;
  const P = { code: "PRYJ", tid: null, role: "board", travel: 30, lang: "en", smsLang: "hing", ivrLang: "hi" };
  let frameReady = false, trainsAt = [];

  function chips(id, key, cb) {
    document.querySelectorAll(`#${id} button`).forEach(b => b.onclick = () => {
      document.querySelectorAll(`#${id} button`).forEach(x => x.classList.toggle("on", x === b));
      P[key] = b.dataset.v || b.dataset.role; if (key === "travel") P.travel = +P.travel; cb && cb();
    });
  }

  function init() {
    const s = A.$("pStn");
    s.innerHTML = A.meta.stations.map(x => `<option value="${x.code}">${x.name} (${x.code})</option>`).join("");
    s.value = P.code;
    s.onchange = () => { P.code = s.value; P.tid = null; render(); };
    A.$("pTrain").onchange = () => { P.tid = +A.$("pTrain").value; update(); };
    chips("pRole", "role", update); chips("pTravel", "travel", update); chips("pLang", "lang", update);
    chips("smsLang", "smsLang", update); chips("ivrLang", "ivrLang", update);
  }

  async function render() {
    const st = await A.api("station", { date: A.date, code: P.code, t: A.t });
    trainsAt = st.arrivals.filter(a => a.state !== "arrived");
    const sel = A.$("pTrain");
    sel.innerHTML = trainsAt.map(a => `<option value="${a.tid}">${a.no} · ${A.esc(a.name)} · ${A.c24(a.lo)}${a.state === "live" ? "" : " (typical)"}</option>`).join("") || `<option value="">No trains in the next 6 h</option>`;
    if (!P.tid || !trainsAt.find(a => a.tid === P.tid)) {
      const pick = trainsAt.find(a => a.state === "live" && !a.starts && a.lo - A.t > 50 && a.delay >= 15 && a.hi - a.lo <= 60) ||
        trainsAt.find(a => a.state === "live" && a.lo - A.t > 40) || trainsAt.find(a => a.state === "live") || trainsAt[0];
      P.tid = pick ? pick.tid : null;
    }
    sel.value = P.tid || "";
    await update();
  }

  async function update() {
    if (!P.tid) return;
    const params = { date: A.date, t: A.t, tid: P.tid, code: P.code, role: P.role, travel: P.travel, lang: P.lang };
    const fr = A.$("phoneFrame");
    if (!frameReady) { fr.src = `p.html?embed=1&${new URLSearchParams(params)}`; frameReady = true; }
    else fr.contentWindow.postMessage({ type: "saarthi", p: params }, "*");
    const [d, log] = await Promise.all([A.api("passenger", params), A.api("messages", params)]);
    insight(d);
    sms(d); ivr(d); msgLog(log, d);
  }

  function insight(d) {
    const p = P.role === "board" ? "5th" : "20th";
    A.$("pInsight").innerHTML = `<b>Same forecast, different advice.</b> ${P.role === "board"
      ? "Boarding: missing the train costs far more than waiting, so SAARTHI plans on the <b>earliest plausible</b> arrival (calibrated 5th percentile) plus a platform buffer."
      : "Receiving: arriving a little after the train is a mild cost, but a two-hour wait at night is not, so SAARTHI plans on the 20th percentile."}
      ${d.dec ? `<br><br>Leave-by <b>${A.c24(d.leave_by)}</b> = ${p} percentile of arrival − ${P.travel} min travel − ${d.dec.buffer} min to reach the platform. Expected wait at the station ≈ <b>${Math.round(d.dec.wait_med)} min</b> (up to ${Math.round(d.dec.wait_hi)}).` : ""}`;
  }

  function sms(d) {
    const scr = A.$("fscreen"), meta = A.$("smsMeta");
    if (!d.sms) { scr.innerHTML = `<div class="hdr"><span>Messages</span><span>${A.c24(A.t)}</span></div>Train has arrived.`; meta.innerHTML = ""; return; }
    const m = d.sms.texts[P.smsLang];
    scr.innerHTML = `<div class="hdr"><span class="from">${A.esc(d.sms.header)}</span><span>${A.c24(A.t)}</span></div><div class="${P.smsLang === "hi" ? "hi" : ""}">${A.esc(m.text)}</div>`;
    const warn = m.segments > 1 ? `<span style="color:var(--crit-ink);font-weight:650">${m.segments} segments: ${m.segments}× the cost, and older handsets may show boxes</span>` : `<span style="color:var(--good-ink);font-weight:650">1 segment: cheapest, works on every phone</span>`;
    meta.innerHTML = `<table>
      <tr><td>Sender header</td><td class="mono">${A.esc(d.sms.header)} <span class="muted">(-G = government)</span></td></tr>
      <tr><td>Encoding</td><td>${m.encoding} · ${m.units} chars / ${m.per_segment} per segment</td></tr>
      <tr><td>Billed as</td><td>${warn}</td></tr>
      <tr><td>DLT template ID</td><td class="mono">${d.sms.template_id}</td></tr>
      <tr><td>Registered template</td><td class="mono" style="font-size:11px">${A.esc(d.sms.template)}</td></tr>
      <tr><td>Principal entity</td><td class="mono">${d.sms.pe_id}</td></tr>
      <tr><td>Other scripts</td><td>${Object.entries(d.sms.texts).map(([k, v]) => `${{ en: "English", hi: "Devanagari", hing: "Hinglish" }[k]}: ${v.segments} seg`).join(" · ")}</td></tr></table>
      <div class="muted" style="margin-top:8px;font-size:11.5px">IDs are placeholders until DLT registration. Every commercial SMS in India must match a registered template.</div>`;
  }

  function speak(text, lang) {
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text), want = lang === "en" ? "en-IN" : "hi-IN";
      const v = speechSynthesis.getVoices().find(v => v.lang === want) || speechSynthesis.getVoices().find(v => v.lang.startsWith(want.slice(0, 2)));
      if (v) u.voice = v; u.lang = want; u.rate = 0.92; speechSynthesis.speak(u);
    } catch (e) { }
  }

  function ivr(d) {
    const box = A.$("ivr");
    if (!d.ivr) { box.innerHTML = `<div class="empty">Train has arrived.</div>`; return; }
    const x = d.ivr[P.ivrLang];
    box.innerHTML = x.flow.map((f, i) => f.who === "ivr"
      ? `<div class="ivr-line"><span class="who">139</span><span class="${P.ivrLang === "hi" ? "hi" : ""}">${A.esc(f.say)} <button class="play" data-i="${i}">▶ play</button></span></div>`
      : `<div class="ivr-line"><span class="who">CALLER</span><span>presses <span class="key">${A.esc(f.key)}</span></span></div>`).join("") +
      `<div class="ivr-line" style="background:var(--accent-wash);border-radius:10px;padding:8px 10px;margin-top:8px"><span class="who">WAKE-UP</span><span class="${P.ivrLang === "hi" ? "hi" : ""}"><b>Outbound call, 45 min before leave-by:</b> ${A.esc(x.wake)} <button class="play" data-w="1">▶ play</button></span></div>`;
    box.querySelectorAll(".play").forEach(b => b.onclick = () => speak(b.dataset.w ? x.wake : x.flow[+b.dataset.i].say, P.ivrLang));
  }

  function msgLog(log, d) {
    A.$("logStat").innerHTML = `SAARTHI sent <b>${log.log.length}</b> SMS so far · a notify-on-every-ETA-change service would have sent <b>${log.naive_count}</b>` +
      (log.actual ? `<br>Actual arrival <b>${A.c24(log.actual)}</b>` : "");
    A.$("msgLog").innerHTML = log.log.slice().reverse().map(m => {
      const tx = m.texts[P.smsLang];
      return `<div class="msg"><div class="when">${A.c24(m.t)} · ${m.kind.toUpperCase()} <span class="muted" style="font-weight:400">· ${tx.segments} seg · ${tx.encoding}</span></div><div class="why">${A.esc(m.why)}</div><div class="body ${P.smsLang === "hi" ? "hi" : ""}">${A.esc(tx.text)}</div></div>`;
    }).join("") || `<div class="empty">No messages yet: the window is published once the train is within about 3 stops.</div>`;
  }

  return { init, render };
})();
