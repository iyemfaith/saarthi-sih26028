/* SAARTHI passenger app: one decision, in your language, readable in five seconds. */
(() => {
  const q = new URLSearchParams(location.search);
  const P = { date: q.get("date"), t: +q.get("t") || null, tid: q.get("tid"), code: q.get("code"), role: q.get("role") || "board",
    travel: +(q.get("travel") || 30), lang: q.get("lang") || "en", embed: q.get("embed") === "1", detail: false };
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let meta = null, last = null;

  const S = {
    en: { wait: ["Wait. Leave home at {leave}", "That's {mins} from now."], wait_r: ["Wait. Leave for the station at {leave}", "That's {mins} from now."],
      get_ready: ["Get ready. Leave at {leave}", "In {mins}."], leave_now: ["Leave now", "Reach {station} by {reach}."],
      rest: ["Rest. You leave at {leave}", "We'll call you at {wake} to wake you."], too_late: ["You may miss this train", "It will likely leave before you reach. Call 139 for the next train."],
      arrived: ["Arrived at {act}", "This train has reached {station}."], at: "Train at {station}", odds: "8 in 10 times it arrives inside this window",
      listen: "Listen", sms: "SMS me", call: "Call me", why: "Why this time?", more: "More details ▾", less: "Fewer details ▴",
      promise: "<b>This time won't keep jumping.</b> We tell you only if it moves 10+ minutes.", ahead: "Stations ahead",
      sure: "<b>How sure are we?</b> We tested SAARTHI on a week of real trains it had never seen. Windows like this one held the real arrival 8 times out of 10. When we are less sure, the window gets wider. We don't hide it.",
      typical: "Live window starts about 3 stations before you. Until then this is its usual time over its last {n} runs.",
      conf: { high: "Very likely", medium: "Likely", low: "Rough guess" }, st: "Your station", tr: "Your train", iam: "I am", b: "Boarding", r: "Receiving someone",
      reach: "Time to reach the station", go: "Show me", change: "Change", subscribed: "Done. You'll get one SMS now, and another only if the window moves 10+ minutes. (Prototype: nothing is sent.)",
      calling: "Done. We'll call you at {wake}. (Prototype: no call is placed.)", foot: "Prototype · real running data, replayed", h: "h", m: "min",
      sched: "timetable", now: "now", leaveLbl: "leave" },
    hi: { wait: ["अभी रुकें। {leave} पर घर से निकलें", "यानी अब से {mins} बाद।"], wait_r: ["अभी रुकें। {leave} पर स्टेशन के लिए निकलें", "यानी अब से {mins} बाद।"],
      get_ready: ["तैयार हो जाएँ। {leave} पर निकलें", "{mins} में।"], leave_now: ["अभी निकलें", "{reach} तक {station} पहुँचें।"],
      rest: ["आराम करें। {leave} पर निकलना है", "हम आपको {wake} पर कॉल करके जगा देंगे।"], too_late: ["यह गाड़ी छूट सकती है", "आपके पहुँचने से पहले निकल सकती है। अगली गाड़ी के लिए 139 पर कॉल करें।"],
      arrived: ["{act} पर पहुँच गई", "यह गाड़ी {station} पहुँच चुकी है।"], at: "{station} पर गाड़ी", odds: "10 में से 8 बार गाड़ी इसी समय के बीच आती है",
      listen: "सुनें", sms: "SMS पाएँ", call: "कॉल करें", why: "यह समय क्यों?", more: "और जानकारी ▾", less: "कम जानकारी ▴",
      promise: "<b>यह समय बार-बार नहीं बदलेगा।</b> 10+ मिनट का बदलाव होने पर ही बताएँगे।", ahead: "आगे के स्टेशन",
      sure: "<b>हमें कितना भरोसा है?</b> हमने सारथी को असली गाड़ियों के एक पूरे हफ़्ते पर परखा, जो उसने पहले कभी नहीं देखा था। ऐसी समय-सीमा 10 में से 8 बार सही निकली। जब भरोसा कम होता है, तो समय-सीमा चौड़ी हो जाती है। हम इसे छिपाते नहीं।",
      typical: "लाइव समय आपसे लगभग 3 स्टेशन पहले शुरू होगा। तब तक यह पिछले {n} बार का आम समय है।",
      conf: { high: "पूरी संभावना", medium: "संभावना", low: "मोटा अनुमान" }, st: "आपका स्टेशन", tr: "आपकी गाड़ी", iam: "मैं", b: "गाड़ी में चढ़ना है", r: "किसी को लेने जाना है",
      reach: "स्टेशन पहुँचने में समय", go: "दिखाएँ", change: "बदलें", subscribed: "हो गया। अभी एक SMS आएगा, फिर तभी जब समय 10+ मिनट बदले। (प्रोटोटाइप: कोई SMS नहीं भेजा गया।)",
      calling: "हो गया। हम आपको {wake} पर कॉल करेंगे। (प्रोटोटाइप: कोई कॉल नहीं होगी।)", foot: "प्रोटोटाइप · असली रनिंग डेटा का रीप्ले", h: "घंटा", m: "मिनट",
      sched: "समय-सारणी", now: "अभी", leaveLbl: "निकलें" },
    hing: { wait: ["Abhi ruken. {leave} par ghar se niklen", "Yaani ab se {mins} baad."], wait_r: ["Abhi ruken. {leave} par station ke liye niklen", "Yaani ab se {mins} baad."],
      get_ready: ["Taiyaar ho jaayen. {leave} par niklen", "{mins} me."], leave_now: ["Abhi niklen", "{reach} tak {station} pahunchen."],
      rest: ["Aaram karen. {leave} par niklna hai", "Hum aapko {wake} par call karke jaga denge."], too_late: ["Yeh gaadi chhoot sakti hai", "Aapke pahunchne se pehle nikal sakti hai. Agli gaadi ke liye 139 par call karen."],
      arrived: ["{act} par pahunch gayi", "Yeh gaadi {station} pahunch chuki hai."], at: "{station} par gaadi", odds: "10 me se 8 baar gaadi isi samay ke beech aati hai",
      listen: "Suniye", sms: "SMS paayen", call: "Call karen", why: "Yeh samay kyon?", more: "Aur jaankari ▾", less: "Kam jaankari ▴",
      promise: "<b>Yeh samay baar-baar nahi badlega.</b> 10+ min badlaav par hi batayenge.", ahead: "Aage ke station",
      sure: "<b>Kitna bharosa?</b> Humne SAARTHI ko asli gaadiyon ke ek hafte par parkha jo usne pehle nahi dekha tha. Aisi samay-seema 10 me se 8 baar sahi nikli.",
      typical: "Live samay aapse lagbhag 3 station pehle shuru hoga. Tab tak yeh pichhle {n} baar ka aam samay hai.",
      conf: { high: "Poori sambhavna", medium: "Sambhavna", low: "Mota andaaza" }, st: "Aapka station", tr: "Aapki gaadi", iam: "Main", b: "Gaadi me chadhna hai", r: "Kisi ko lene jaana hai",
      reach: "Station pahunchne me samay", go: "Dikhaayen", change: "Badlen", subscribed: "Ho gaya. Abhi ek SMS aayega, phir tabhi jab samay 10+ min badle. (Prototype: koi SMS nahi bheja gaya.)",
      calling: "Ho gaya. Hum aapko {wake} par call karenge. (Prototype.)", foot: "Prototype · asli running data ka replay", h: "ghanta", m: "min",
      sched: "time-table", now: "abhi", leaveLbl: "niklen" },
  };
  const L = () => S[P.lang];
  const fill = (s, o) => s.replace(/\{(\w+)\}/g, (_, k) => o[k] ?? "");
  const hm = t => { const m = ((Math.round(t) % 1440) + 1440) % 1440; return [Math.floor(m / 60), m % 60]; };
  function clock(t, lang = P.lang) {
    const [h, m] = hm(t), h12 = h % 12 || 12, mm = String(m).padStart(2, "0");
    if (lang === "en") return `${h12}:${mm} ${h < 12 ? "AM" : "PM"}`;
    const k = h >= 4 && h < 12 ? 0 : h >= 12 && h < 16 ? 1 : h >= 16 && h < 20 ? 2 : 3;
    return `${(lang === "hi" ? ["सुबह", "दोपहर", "शाम", "रात"] : ["subah", "dopahar", "shaam", "raat"])[k]} ${h12}:${mm}`;
  }
  function mins(m) { m = Math.max(0, Math.round(m)); const h = Math.floor(m / 60), r = m % 60; return h ? `${h} ${L().h} ${r} ${L().m}` : `${r} ${L().m}`; }
  function toast(s) { const t = $("toast"); t.textContent = s; t.style.display = "block"; clearTimeout(toast.h); toast.h = setTimeout(() => t.style.display = "none", 4200); }
  // inside the dashboard's phone frame, share the dashboard's backend (no second Python runtime)
  const backend = (() => { try { return (window.parent !== window && window.parent.SaarthiBackend) || window.SaarthiBackend; } catch (e) { return window.SaarthiBackend; } })();
  const api = (p, o) => backend.call(p, o);

  function setLangButtons() { document.querySelectorAll("#lang button").forEach(b => b.classList.toggle("on", b.dataset.v === P.lang)); document.documentElement.lang = P.lang === "hi" ? "hi" : "en"; }
  document.querySelectorAll("#lang button").forEach(b => b.onclick = () => { P.lang = b.dataset.v; setLangButtons(); render(); });
  $("size").onclick = () => document.body.classList.toggle("big");

  function timeline(d) {
    const t0 = P.t, t1 = Math.max(d.hi + 25, t0 + 60), W = 340, H = 64, X = v => 12 + (W - 24) * (v - t0) / (t1 - t0);
    const lv = d.leave_by, parts = [];
    parts.push(`<line x1="12" x2="${W - 12}" y1="30" y2="30" stroke="#e3e2db" stroke-width="6" stroke-linecap="round"/>`);
    if (d.state !== "arrived") parts.push(`<rect x="${X(Math.max(t0, d.lo))}" y="22" width="${Math.max(6, X(d.hi) - X(Math.max(t0, d.lo)))}" height="16" rx="6" fill="#1f63b8" opacity=".85"/>`);
    parts.push(`<line x1="${X(d.sch)}" x2="${X(d.sch)}" y1="18" y2="42" stroke="#7d7b74" stroke-width="2"/>`);
    parts.push(`<circle cx="${X(t0)}" cy="30" r="7" fill="#0b0b0b" stroke="#fff" stroke-width="2"/><text x="${X(t0)}" y="58" font-size="12" text-anchor="start" fill="#46453f">${L().now} ${clock(t0)}</text>`);
    if (lv && lv > t0 && lv < t1) parts.push(`<path d="M${X(lv)} 8 v22" stroke="#0b0b0b" stroke-width="2"/><path d="M${X(lv)} 8 h12 l-3 4 l3 4 h-12z" fill="#0b0b0b"/><text x="${X(lv) + 15}" y="16" font-size="11.5" fill="#0b0b0b" font-weight="700">${L().leaveLbl} ${clock(lv)}</text>`);
    if (d.state !== "arrived" && X(d.hi) - X(t0) > 190) parts.push(`<text x="${Math.min(W - 12, X(d.hi))}" y="58" font-size="12" text-anchor="end" fill="#1f63b8" font-weight="700">${winText(d)}</text>`);
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="timeline">${parts.join("")}</svg>`;
  }

  function speakText(d) {
    const l = L(), dec = decText(d);
    return `${d.no}, ${P.lang === "hi" ? d.name_hi : d.name}. ${dec[0]}. ${dec[1]} ${fill(l.at, { station: stName(d) })}: ${d.clock[P.lang].window}. ${d.state === "arrived" ? "" : l.odds}.`;
  }
  const stName = d => P.lang === "hi" ? d.station.hi : d.station.en;
  function winText(d) {   // "रात 12:20 – 12:45", "12:20 – 12:45 AM": say the day-part once
    const c = d.clock[P.lang], lo = c.lo.split(" "), hi = c.hi.split(" ");
    if (P.lang === "en") return lo[1] === hi[1] ? `${lo[0]} – ${c.hi}` : `${c.lo} – ${c.hi}`;
    return lo[0] === hi[0] ? `${c.lo} – ${hi.slice(1).join(" ")}` : `${c.lo} – ${c.hi}`;
  }
  function decText(d) {
    const l = L(), key = d.state === "wait" && P.role === "receive" ? "wait_r" : d.state;
    const o = { leave: d.leave_by ? clock(d.leave_by) : "", mins: d.leave_by ? mins(d.leave_by - P.t) : "", station: stName(d),
      reach: d.leave_by ? clock(Math.max(d.leave_by, P.t) + P.travel) : "", wake: d.leave_by ? clock(d.leave_by - 45) : "", act: clock(d.lo) };
    const s = l[key] || l.wait;
    return [fill(s[0], o), fill(s[1], o)];
  }
  const ICON = { wait: "⏳", get_ready: "🎒", leave_now: "🚶", rest: "🌙", too_late: "⚠️", arrived: "✅" };

  async function render() {
    setLangButtons();
    if (!P.tid || !P.code) return setup();
    let d;
    try { d = await api("passenger", { date: P.date, t: P.t, tid: P.tid, code: P.code, role: P.role, travel: P.travel }); } catch (e) { $("app").innerHTML = `<div class="card">Could not load.</div>`; return; }
    last = d;
    const l = L(), dec = decText(d), nconf = { high: 3, medium: 2, low: 1 }[d.conf] || 1;
    const why = (d.why[P.lang] || []).map(w => `<li>${esc(w)}</li>`).join("");
    const journey = (d.journey || []).map(j => `<div class="jr"><span>${esc(P.lang === "hi" ? j.name.hi : j.name.en)}</span><b>${clock(j.pub[0])} – ${clock(j.pub[1])}</b></div>`).join("");
    $("app").innerHTML = `
      <div class="card">
        <div class="tr"><span class="no">${d.no}</span><span class="nm">${esc(P.lang === "hi" ? d.name_hi : d.name)}</span></div>
        <div class="to">${P.role === "board" ? "🧳" : "🤝"} ${esc(stName(d))} · ${esc(P.lang === "hi" ? d.origin[1] : d.origin[0])} → ${esc(P.lang === "hi" ? d.dest[1] : d.dest[0])}
          ${P.embed ? "" : ` · <button class="change" id="chg">${l.change}</button>`}</div>
        <div class="dec st-${d.state}" role="status" aria-live="polite"><div class="ic" aria-hidden="true">${ICON[d.state] || "⏳"}</div><div><div class="big">${esc(dec[0])}</div><div class="small">${esc(dec[1])}</div></div></div>
        ${d.state === "arrived" ? "" : `<div class="win"><div class="lab">${esc(fill(l.at, { station: stName(d) }))}</div>
          <div class="w">${esc(winText(d))}</div>
          <div class="odds"><span class="dots">${[1, 2, 3].map(i => `<i class="${i <= nconf ? "" : "o"}"></i>`).join("")}</span><b>${l.conf[d.conf]}</b> · ${l.odds}</div></div>`}
        <div class="line">${timeline(d)}</div>
        ${d.typical ? `<div class="to" style="margin-top:6px">ℹ️ ${esc(fill(l.typical, { n: d.n_hist || "" }))}</div>` : ""}
        <div class="acts"><button id="bListen"><span>🔊</span>${l.listen}</button><button id="bSms"><span>📩</span>${l.sms}</button><button id="bCall"><span>📞</span>${l.call}</button></div>
      </div>
      ${why ? `<div class="card"><h2>${l.why}</h2><ul class="why">${why}</ul></div>` : ""}
      <div class="card promise"><div style="font-size:24px">🤝</div><div>${l.promise}</div></div>
      <div class="card"><button class="tog" id="bMore" style="padding-top:0">${P.detail ? l.less : l.more}</button>
        ${P.detail ? `<div style="margin-top:10px">${journey ? `<h2>${l.ahead}</h2>${journey}` : ""}<p style="font-size:.92em;color:var(--ink2);margin:14px 0 0">${l.sure}</p></div>` : ""}</div>
      <div class="foot">${l.foot}${P.date ? ` · ${new Date(P.date + "T00:00:00Z").toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" })} 2024 ${clock(P.t)}` : ""}</div>`;
    $("bListen").onclick = () => {
      try {
        speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(speakText(d));
        const want = P.lang === "en" ? "en-IN" : "hi-IN";
        const v = speechSynthesis.getVoices().find(v => v.lang === want) || speechSynthesis.getVoices().find(v => v.lang.startsWith(want.slice(0, 2)));
        if (v) u.voice = v; u.lang = want; u.rate = 0.92;
        speechSynthesis.speak(u);
      } catch (e) { toast("Voice not available on this device."); }
    };
    $("bSms").onclick = () => toast(l.subscribed);
    $("bCall").onclick = () => toast(fill(l.calling, { wake: d.leave_by ? clock(d.leave_by - 45) : "" }));
    $("bMore").onclick = () => { P.detail = !P.detail; render(); };
    const c = $("chg"); if (c) c.onclick = () => { P.tid = null; setup(); };
  }

  async function setup() {
    const l = L();
    if (!meta) meta = await api("meta", {});
    if (!P.date) P.date = meta.default_day;
    if (!P.t) { const now = new Date(); P.t = meta.days_info[P.date].day0 + now.getHours() * 60 + now.getMinutes(); }
    const code = P.code || "CNB";
    const st = await api("station", { date: P.date, code, t: P.t });
    const opts = st.arrivals.filter(a => a.state !== "arrived").map(a => `<option value="${a.tid}">${a.no} · ${esc(P.lang === "hi" ? a.name_hi : a.name)} · ${clock(a.lo)}</option>`).join("");
    $("app").innerHTML = `<div class="card setup">
      <label>${l.st}</label><select id="sSt">${meta.stations.map(s => `<option value="${s.code}" ${s.code === code ? "selected" : ""}>${esc(P.lang === "hi" ? s.hi : s.name)}</option>`).join("")}</select>
      <label>${l.tr}</label><select id="sTr">${opts}</select>
      <label>${l.iam}</label><div class="choice"><button data-r="board" class="${P.role === "board" ? "on" : ""}">🧳<br>${l.b}</button><button data-r="receive" class="${P.role === "receive" ? "on" : ""}">🤝<br>${l.r}</button></div>
      <label>${l.reach}</label><div class="chips">${[10, 20, 30, 45, 60, 90].map(v => `<button data-v="${v}" class="${v === P.travel ? "on" : ""}">${v} ${L().m}</button>`).join("")}</div>
      <button class="go" id="sGo">${l.go}</button></div>`;
    $("sSt").onchange = e => { P.code = e.target.value; setup(); };
    document.querySelectorAll(".choice button").forEach(b => b.onclick = () => { P.role = b.dataset.r; document.querySelectorAll(".choice button").forEach(x => x.classList.toggle("on", x === b)); });
    document.querySelectorAll(".chips button").forEach(b => b.onclick = () => { P.travel = +b.dataset.v; document.querySelectorAll(".chips button").forEach(x => x.classList.toggle("on", x === b)); });
    $("sGo").onclick = () => { P.code = $("sSt").value; P.tid = $("sTr").value; if (P.tid) render(); };
  }

  addEventListener("message", e => {
    const m = e.data; if (!m || m.type !== "saarthi") return;
    Object.assign(P, m.p); render();
  });
  if (!P.embed) setInterval(() => { if (P.t) { P.t += 1; if (P.tid) render(); } }, 60000);   // standalone: the clock runs
  if (P.embed) document.body.classList.add("embed");
  setLangButtons();
  render();
})();
