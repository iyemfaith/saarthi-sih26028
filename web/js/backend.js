/* Where the SAARTHI API runs.
 *   server  : a SAARTHI server answers /api/* (laptop: uvicorn saarthi.api:app)
 *   browser : no server (GitHub Pages) -> the same Python code (saarthi/service.py)
 *             runs in this tab via Pyodide, reading the replay day as JSON.
 * One source of truth: the browser runs the repo's Python files, not a JS port. */
window.SaarthiBackend = (() => {
  const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/";
  const ROOT = new URL("../", location.href).href;          // repo root, relative to web/
  const FILES = ["saarthi/__init__.py", "saarthi/config.py", "saarthi/names.py", "saarthi/decide.py",
    "saarthi/messages.py", "saarthi/service.py", "data/processed/corridor.json", "data/processed/report.json",
    "data/processed/evidence.json", "data/processed/web/days.json"];
  let mode = null, py = null, booting = null, queue = Promise.resolve();
  const days = new Set();

  function status(msg) {
    if (!document.body) return;
    let el = document.getElementById("saarthi-boot");
    if (!el) {
      el = document.createElement("div");
      el.id = "saarthi-boot";
      el.setAttribute("role", "status");
      el.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:9999;background:#0b0b0b;" +
        "color:#fff;padding:12px 18px;border-radius:12px;font:14px/1.4 system-ui,'Segoe UI',sans-serif;" +
        "box-shadow:0 8px 28px rgba(0,0,0,.3);max-width:92vw;text-align:center";
      document.body.appendChild(el);
    }
    el.textContent = msg || "";
    el.style.display = msg ? "block" : "none";
  }

  async function detect() {
    if (mode) return mode;
    if (location.hostname.endsWith("github.io")) return (mode = "browser");   // static hosting: no server to probe
    try {
      const r = await fetch("/api/meta", { cache: "no-store" });
      if (r.ok && (r.headers.get("content-type") || "").includes("json")) return (mode = "server");
    } catch (e) { /* no server */ }
    return (mode = "browser");
  }

  function boot() {
    if (booting) return booting;
    booting = (async () => {
      status("Starting SAARTHI in your browser: a one-time ~15 MB download…");
      await new Promise((res, rej) => {
        const s = document.createElement("script");
        s.src = PYODIDE + "pyodide.js";
        s.onload = res;
        s.onerror = () => rej(new Error("Could not load the Python runtime (Pyodide)."));
        document.head.appendChild(s);
      });
      py = await loadPyodide({ indexURL: PYODIDE });
      py.FS.mkdirTree("/app/saarthi");
      py.FS.mkdirTree("/app/data/processed/web");
      await Promise.all(FILES.map(async f => {
        const r = await fetch(ROOT + f);
        if (!r.ok) throw new Error(`missing ${f}`);
        py.FS.writeFile("/app/" + f, new Uint8Array(await r.arrayBuffer()));
      }));
      py.runPython("import sys; sys.path.insert(0, '/app'); from saarthi.service import dispatch");
      status("");
    })().catch(e => { status("Could not start the demo: " + e.message); throw e; });
    return booting;
  }

  async function ensureDay(date) {
    if (!date || days.has(date)) return;
    status(`Loading ${date}: real running records for 19 stations (~3 MB)…`);
    const r = await fetch(ROOT + `data/processed/web/${date}.json`);
    if (!r.ok) throw new Error(`day ${date}: ${r.status}`);
    py.FS.writeFile(`/app/data/processed/web/${date}.json`, new Uint8Array(await r.arrayBuffer()));
    days.add(date);
    status("");
  }

  async function call(path, params = {}) {
    if ((await detect()) === "server") {
      const q = new URLSearchParams(params).toString();
      const r = await fetch(`/api/${path}${q ? "?" + q : ""}`);
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json();
    }
    await boot();
    // Python is single-threaded: run calls one at a time, in order
    const run = queue.then(async () => {
      await ensureDay(params.date);
      return JSON.parse(py.globals.get("dispatch")(path, JSON.stringify(params)));
    });
    queue = run.catch(() => {});
    const res = await run;
    if (res && res.error) throw new Error(`${path}: ${res.status} ${res.error}`);
    return res;
  }

  return { call, detect, get mode() { return mode; } };
})();
