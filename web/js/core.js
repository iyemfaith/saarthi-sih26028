/* SAARTHI dashboard core: replay clock, API, i18n, status encoding, SVG helpers. No dependencies. */
const T0 = Date.UTC(2024, 7, 31); // 2024-08-31 00:00 (minutes in the API are counted from here, IST wall clock)

const I18N = {
  en: {},
  hi: {
    tagline: "समय नहीं, फ़ैसला।", t_control: "कंट्रोल रूम", t_control_s: "सेक्शन कंट्रोलर", t_station: "स्टेशन",
    t_station_s: "स्टेशन मास्टर · प्लेटफॉर्म", t_pass: "यात्री", t_pass_s: "ऐप · SMS · 139 कॉल", t_board: "स्टेशन बोर्ड",
    t_board_s: "प्लेटफॉर्म पर क्या दिखता है", t_proof: "प्रमाण", t_proof_s: "क्या यह काम करता है?",
    corr_title: "लाइव कॉरिडोर · नई दिल्ली → प्रयागराज जं.", marey_title: "समय–दूरी चार्ट (कंट्रोल चार्ट)",
    recs_title: "रोकें या चलने दें?", station: "स्टेशन", arr_title: "आगमन · अगले 6 घंटे", pf_title: "प्लेटफॉर्म योजना · अगले 4 घंटे",
    ann_title: "उद्घोषणाएँ", p_setup: "यात्री बनकर देखें", p_train: "गाड़ी", p_role: "मैं", p_board: "गाड़ी में चढ़ना है",
    p_receive: "किसी को लेने जाना है", p_travel: "स्टेशन पहुँचने में समय", p_lang: "भाषा", sms_title: "₹1,200 के फ़ीचर फ़ोन पर SMS",
    ivr_title: "139 पर कॉल · सबके लिए आवाज़", log_title: "आज इस यात्री को मिले सभी संदेश", halt_title: "बिना बोर्ड वाला हॉल्ट: दीवार पोस्टर",
    halt_sms: "मिस्ड कॉल पर जवाबी SMS",
  },
};

const App = {
  meta: null, date: null, day0: 0, t: 0, playing: false, speed: 60, lang: "en", view: "control",
  sel: null, st: null, stepT: null, views: {}, lastFetch: 0, busy: false,

  async api(path, params = {}) {
    const q = new URLSearchParams(params).toString();
    const r = await fetch(`/api/${path}${q ? "?" + q : ""}`);
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
  },

  // ---------- time ----------
  hm(t) { const m = Math.round(t) % 1440; const mm = (m + 1440) % 1440; return [Math.floor(mm / 60), mm % 60]; },
  c24(t) { const [h, m] = this.hm(t); return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`; },
  c12(t, lang = this.lang) {
    const [h, m] = this.hm(t); const h12 = h % 12 || 12;
    if (lang === "hi") return `${["रात", "सुबह", "दोपहर", "शाम", "रात"][h < 4 ? 0 : h < 12 ? 1 : h < 16 ? 2 : h < 20 ? 3 : 4]} ${h12}:${String(m).padStart(2, "0")}`;
    return `${h12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
  },
  dt(t) { return new Date(T0 + t * 60000); },
  dayName(t) { return this.dt(t).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }); },
  dur(m) { m = Math.round(m); if (Math.abs(m) < 60) return `${m} min`; const h = Math.floor(Math.abs(m) / 60), r = Math.abs(m) % 60; return `${m < 0 ? "-" : ""}${h}h ${String(r).padStart(2, "0")}m`; },
  fmt(n, d = 0) { return Number(n).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d }); },

  // ---------- delay status (reserved status palette; always icon + label) ----------
  status(d) {
    if (d == null) return { k: "good", label: "—", icon: "" };
    if (d < 15) return { k: "good", label: this.lang === "hi" ? "समय पर" : "On time", icon: "✓" };
    if (d < 60) return { k: "warn", label: this.lang === "hi" ? `${Math.round(d)} मि. देर` : `${Math.round(d)} min late`, icon: "!" };
    if (d < 180) return { k: "serious", label: this.lang === "hi" ? `${this.dur(d)} देर` : `${this.dur(d)} late`, icon: "!!" };
    return { k: "critical", label: this.lang === "hi" ? `${this.dur(d)} देर` : `${this.dur(d)} late`, icon: "×" };
  },
  chip(d) { const s = this.status(d); return `<span class="chip s-${s.k}"><span class="dot"></span>${s.label}</span>`; },
  confChip(c) {
    const L = { en: { high: "High confidence", medium: "Medium", low: "Low" }, hi: { high: "भरोसा ऊँचा", medium: "मध्यम", low: "कम" } }[this.lang === "hi" ? "hi" : "en"];
    const ic = { high: "●●●", medium: "●●○", low: "●○○" }[c] || "○○○";
    return `<span class="chip conf-${c}" title="Confidence"><span style="letter-spacing:-1px;font-size:9px">${ic}</span>${L[c] || c}</span>`;
  },
  scolor(d) { return d == null ? "var(--muted)" : d < 15 ? "var(--good)" : d < 60 ? "var(--warn)" : d < 180 ? "var(--serious)" : "var(--critical)"; },
  stn(code) { return this.meta.stations.find(s => s.code === code); },
  sname(code) { const s = this.stn(code); return s ? (this.lang === "hi" ? s.hi : s.name) : code; },

  // ---------- DOM + SVG ----------
  $(id) { return document.getElementById(id); },
  esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); },
  svg(tag, attrs = {}, parent) {
    const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  },
  text(parent, x, y, s, attrs = {}) { const e = this.svg("text", { x, y, ...attrs }, parent); e.textContent = s; return e; },
  lin(d0, d1, r0, r1) { const f = v => r0 + (v - d0) * (r1 - r0) / ((d1 - d0) || 1); f.inv = p => d0 + (p - r0) * (d1 - d0) / ((r1 - r0) || 1); return f; },
  tip(e, html) {
    const t = this.$("tip");
    if (!html) { t.style.display = "none"; return; }
    t.innerHTML = html; t.style.display = "block";
    const w = t.offsetWidth, h = t.offsetHeight;
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + w > innerWidth - 8) x = e.clientX - w - 14;
    if (y + h > innerHeight - 8) y = e.clientY - h - 14;
    t.style.left = x + "px"; t.style.top = y + "px";
  },
  bindTip(el, fn) {
    el.addEventListener("pointermove", e => this.tip(e, fn(e)));
    el.addEventListener("pointerleave", () => this.tip(null));
    el.setAttribute("tabindex", "0");
    el.addEventListener("focus", () => { const r = el.getBoundingClientRect(); this.tip({ clientX: r.right, clientY: r.top }, fn({})); });
    el.addEventListener("blur", () => this.tip(null));
  },

  i18n() {
    const d = I18N[this.lang] || {};
    document.querySelectorAll("[data-i18n]").forEach(e => {
      const k = e.dataset.i18n;
      if (!e.dataset.en) e.dataset.en = e.textContent;
      e.textContent = d[k] || e.dataset.en;
      e.classList.toggle("hi", this.lang === "hi" && !!d[k]);
    });
  },

  // ---------- clock ----------
  setT(t, force) {
    this.t = Math.max(this.day0, Math.min(this.day0 + 1440, t));
    this.$("clock").textContent = this.c24(this.t);
    this.$("clockDate").innerHTML = `<b>${this.dayName(this.t)}</b><br>${this.lang === "hi" ? "असली रनिंग डेटा का रीप्ले" : "replay of real running data"}`;
    this.$("scrub").value = Math.round(this.t - this.day0);
    const step = Math.floor((this.t - this.day0) / 5);
    if (force || step !== this.stepT) { this.stepT = step; this.refresh(); }
  },
  async refresh() {
    if (this.busy) { this.pending = true; return; }
    this.busy = true;
    const want = this.stepT;
    try {
      this.st = await this.api("state", { date: this.date, t: this.t });
      const v = this.views[this.view];
      if (v && v.render) await v.render(this.st);
    } catch (e) { console.error(e); }
    this.busy = false;
    // the clock may have moved while we were drawing: never leave a stale frame on screen
    if (this.pending || this.stepT !== want) { this.pending = false; this.refresh(); }
  },
  play(on) {
    this.playing = on;
    this.$("playBtn").innerHTML = on ? "❚❚ Pause" : "▶ Play";
    this.$("playBtn").classList.toggle("on", on);
  },
  loop() {
    let last = performance.now();
    const f = now => {
      const dt = (now - last) / 1000; last = now;
      if (this.playing) {
        const nt = this.t + dt * this.speed / 60;
        if (nt >= this.day0 + 1440) this.play(false);
        this.setT(nt);
      }
      requestAnimationFrame(f);
    };
    requestAnimationFrame(f);
  },

  async start() {
    this.meta = await this.api("meta");
    const ds = this.$("daySel");
    ds.innerHTML = this.meta.days.map(d => `<option value="${d}">${new Date(d + "T00:00:00Z").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })} 2024</option>`).join("");
    this.date = this.meta.default_day; ds.value = this.date;
    this.day0 = this.meta.days_info[this.date].day0;
    this.$("truthNote").innerHTML = `<b>Replay mode.</b> Real Indian Railways running records for this day (RSTGCN dataset, IIT Kharagpur, IEEE T-ITS). The model never trained on it. Forecasts use only reports that had arrived by the clock; real arrivals appear when the clock passes them.`;
    ds.onchange = () => { this.date = ds.value; this.day0 = this.meta.days_info[this.date].day0; this.sel = null; this.setT(this.meta.days_info[this.date].suggest || this.day0 + 14 * 60, true); };
    this.$("playBtn").onclick = () => this.play(!this.playing);
    this.$("scrub").oninput = e => this.setT(this.day0 + +e.target.value);
    document.querySelectorAll("#speedSeg button").forEach(b => b.onclick = () => {
      document.querySelectorAll("#speedSeg button").forEach(x => x.classList.toggle("on", x === b)); this.speed = +b.dataset.speed;
    });
    document.querySelectorAll("#langSeg button").forEach(b => b.onclick = () => {
      document.querySelectorAll("#langSeg button").forEach(x => x.classList.toggle("on", x === b)); this.lang = b.dataset.lang; this.i18n(); this.setT(this.t, true);
    });
    this.$("themeBtn").onclick = () => {
      const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      document.documentElement.dataset.theme = cur === "dark" ? "light" : "dark";
      try { localStorage.setItem("saarthi-theme", document.documentElement.dataset.theme); } catch (e) { }
      this.setT(this.t, true);
    };
    try { const th = localStorage.getItem("saarthi-theme"); if (th) document.documentElement.dataset.theme = th; } catch (e) { }
    document.querySelectorAll("#tabs .tab").forEach(b => b.onclick = () => this.show(b.dataset.view));
    document.addEventListener("keydown", e => { if (e.code === "Space" && e.target.tagName !== "INPUT" && e.target.tagName !== "SELECT") { e.preventDefault(); this.play(!this.playing); } });
    for (const v of Object.values(this.views)) if (v.init) v.init();
    const h = location.hash.slice(1); if (h && this.views[h]) this.view = h;
    this.show(this.view, true);
    this.play(false);
    this.setT(this.meta.days_info[this.date].suggest || this.day0 + 14 * 60, true);
    this.loop();
  },
  show(v, silent) {
    this.view = v;
    document.querySelectorAll("#tabs .tab").forEach(b => b.classList.toggle("on", b.dataset.view === v));
    document.querySelectorAll(".view").forEach(s => s.classList.toggle("on", s.id === "v-" + v));
    history.replaceState(null, "", "#" + v);
    if (!silent && this.st) { const x = this.views[v]; if (x && x.render) x.render(this.st); }
  },
};
