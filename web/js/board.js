/* Station board: LED train indication board (Hindi/English alternating) + small-halt poster & missed-call SMS. */
App.views.board = (() => {
  const A = App;
  let code = "PRYJ", mode = "saarthi", phase = 0, data = null, timer = null;

  function init() {
    const s = A.$("bStn");
    s.innerHTML = A.meta.stations.map(x => `<option value="${x.code}">${x.name} (${x.code})${A.meta.halts.includes(x.code) ? " · halt" : ""}</option>`).join("");
    s.value = code;
    s.onchange = () => { code = s.value; render(); };
    document.querySelectorAll("#bMode button").forEach(b => b.onclick = () => {
      document.querySelectorAll("#bMode button").forEach(x => x.classList.toggle("on", x === b)); mode = b.dataset.v; draw();
    });
    timer = setInterval(() => { if (A.view === "board") { phase = 1 - phase; draw(); } }, 6000);
  }

  function draw() {
    if (!data) return;
    const hi = phase === 1, d = data;
    const H = hi
      ? ["गाड़ी सं.", "गाड़ी का नाम", "कहाँ से", mode === "saarthi" ? "अपेक्षित समय" : "अपेक्षित", "प्ले.", "स्थिति"]
      : ["TRAIN NO", "TRAIN NAME", "FROM", mode === "saarthi" ? "EXPECTED" : "EXP.TIME", "PF", mode === "saarthi" ? "STATUS" : "LATE BY"];
    const rows = d.rows.slice(0, 8).map(r => {
      const late = r.delay >= 15, arrived = r.state === "arrived";
      let when, status, cls;
      if (mode === "saarthi") {
        when = arrived ? r.win : r.win;
        status = arrived ? (hi ? "आ गई" : "ARRIVED") : r.state === "typical" ? (hi ? "अनुमानित" : "TYPICAL") : late ? (hi ? r.late_hi : r.late_en) : (hi ? "समय पर" : "ON TIME");
        cls = arrived || !late ? "g" : "r";
      } else {
        when = arrived ? r.win : r.old;
        const dl = Math.max(0, r.delay), h = Math.floor(dl / 60), m = dl % 60;
        status = arrived ? (hi ? "आ गई" : "ARRIVED") : dl < 5 ? (hi ? "समय पर" : "RIGHT TIME") : `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
        cls = arrived || dl < 5 ? "g" : "r";
      }
      return `<tr><td>${r.no}</td><td class="${hi ? "hi" : ""}">${A.esc(hi ? r.name_hi : r.name.toUpperCase())}</td><td class="small ${hi ? "hi" : ""}">${A.esc(hi ? r.origin_hi : r.origin.toUpperCase())}</td>
        <td>${A.esc(when)}</td><td>${r.pf || "-"}</td><td class="${cls} small ${hi ? "hi" : ""}">${A.esc(status)}</td></tr>`;
    }).join("");
    const lead = d.rows.find(r => r.state === "live" && r.delay >= 15);
    const tick = lead ? (hi
      ? `गाड़ी संख्या ${lead.no} ${lead.name_hi} के ${lead.win.replace("-", " से ")} के बीच प्लेटफॉर्म ${lead.pf || "-"} पर आने की संभावना है। यह समय तभी बदलेगा जब 10 मिनट से ज़्यादा का बदलाव हो। पूछताछ: 139`
      : `TRAIN NO ${lead.no} ${lead.name.toUpperCase()} IS EXPECTED BETWEEN ${lead.win.replace("-", " AND ")} ON PF ${lead.pf || "-"}. THIS WINDOW CHANGES ONLY IF IT MOVES MORE THAN 10 MIN. ENQUIRY 139`)
      : (hi ? "सभी गाड़ियाँ समय पर। यात्रा शुभ हो। पूछताछ: 139" : "ALL TRAINS RUNNING TO WINDOW. HAPPY JOURNEY. ENQUIRY 139");
    const todayTick = lead ? (hi ? `गाड़ी संख्या ${lead.no} ${lead.late_hi} से चल रही है।` : `TRAIN NO ${lead.no} IS RUNNING LATE BY ${lead.delay} MIN.`) : "";
    A.$("led").innerHTML = `<div class="led-title"><span class="${hi ? "hi" : ""}">${hi ? A.esc(d.name.hi) + " · आगमन" : A.esc(d.name.en.toUpperCase()) + " · ARRIVALS"}</span><span>${d.clock}</span></div>
      <table><thead><tr>${H.map(h => `<th class="${hi ? "hi" : ""}">${h}</th>`).join("")}</tr></thead><tbody>${rows || `<tr><td colspan="6">${hi ? "कोई आगमन नहीं" : "NO ARRIVALS"}</td></tr>`}</tbody></table>
      <div class="ticker"><span class="${hi ? "hi" : ""}">${A.esc(mode === "saarthi" ? tick : todayTick)}</span></div>`;
    A.$("boardFoot").textContent = mode === "saarthi" ? "Window = SAARTHI's published 80% window, snapped to 5 min" : "Today: one expected time, restated as delay grows";
  }

  async function render() {
    data = await A.api("board", { date: A.date, code, t: A.t });
    draw();
    const halt = A.meta.halts.includes(code) ? code : "KGA";
    const h = await A.api("halt", { date: A.date, code: halt, t: A.t });
    A.$("poster").innerHTML = `<div class="poster">
      <div style="font-size:14px;font-weight:700">${A.esc(h.name.hi)} · ${A.esc(h.name.en)}</div>
      <h2>रेलगाड़ी कब आएगी?</h2><div style="font-size:15px">When will my train come?</div>
      <div style="margin-top:10px;font-weight:700">इस नंबर पर मिस्ड कॉल दें · Give a missed call</div>
      <div class="big">${h.missed_call}</div>
      <div class="steps"><div><div class="ico">📞</div>मिस्ड कॉल दें<br><b>मुफ़्त · free</b></div><div><div class="ico">📩</div>SMS में अगली 3 गाड़ियाँ<br><b>next 3 trains</b></div><div><div class="ico">🚶</div>सही समय पर निकलें<br><b>leave on time</b></div></div>
      <div style="margin-top:12px;font-size:13px">या <b>139</b> पर कॉल करें, अपनी भाषा में सुनें · Or call <b>139</b> to hear it in your language</div></div>`;
    A.$("haltSub").textContent = `${h.name.en}, ${A.c24(A.t)}: the next ${h.trains.length} trains, as one SMS.`;
    A.$("haltSms").innerHTML = Object.entries(h.sms).map(([k, v]) => `<div style="margin-top:10px"><div style="font-size:12px;font-weight:650">${{ en: "English", hing: "Hinglish (Roman Hindi)", hi: "हिंदी (Devanagari)" }[k]} · <span class="${v.segments > 1 ? "" : ""}" style="color:${v.segments > 1 ? "var(--crit-ink)" : "var(--good-ink)"}">${v.encoding}, ${v.units} chars → ${v.segments} segment${v.segments > 1 ? "s" : ""}</span></div><div class="msg"><div class="body ${k === "hi" ? "hi" : ""}">${A.esc(v.text)}</div></div></div>`).join("") +
      `<div class="muted" style="font-size:11.5px;margin-top:10px">Missed-call number is illustrative. Replies go through the same DLT-registered templates as every other SAARTHI SMS.</div>`;
  }
  return { init, render };
})();
