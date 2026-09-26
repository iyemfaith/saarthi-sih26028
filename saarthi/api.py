"""SAARTHI prototype server.

Serves the dashboard (web/) and a JSON API over replayed held-out days. Every
endpoint takes the replay clock `t` (minutes since 2024-08-31 00:00) and only
reveals what was knowable at t: real arrivals appear once the clock passes them.

Run:  py -m uvicorn saarthi.api:app --port 8026
"""
import json
import math
import pickle
from bisect import bisect_right
from collections import defaultdict

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import messages as M
from .config import CODES, PROC, WEB
from .decide import passenger as decide_passenger
from .names import CITY

app = FastAPI(title="SAARTHI prototype", docs_url="/api/docs")
STATIONS = json.load(open(PROC / "corridor.json", encoding="utf-8"))
SIDX = {s["code"]: i for i, s in enumerate(STATIONS)}
REPORT = json.load(open(PROC / "report.json"))
EVID = json.load(open(PROC / "evidence.json")) if (PROC / "evidence.json").exists() else {}
PLATFORMS = {"NDLS": 16, "GZB": 6, "KRJ": 3, "ALJN": 4, "HRS": 3, "TDL": 5, "FZD": 3, "SKB": 3, "ETW": 4, "BNT": 2,
             "PHD": 3, "JJK": 2, "RURA": 2, "CNB": 10, "FTP": 3, "KGA": 2, "SRO": 2, "BRE": 2, "PRYJ": 10}
HALTS = {"KRJ", "HRS", "FZD", "BNT", "PHD", "JJK", "RURA", "KGA", "SRO", "BRE"}   # small stations, few/no boards


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating,)):
        return None if math.isnan(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, float) and math.isnan(o):
        return None
    return o


def J(o):
    return JSONResponse(clean(o))


class Day:
    def __init__(self, res):
        self.res = res
        self.date, self.day0, self.step = res["date"], res["day0"], res["step"]
        self.steps = res["steps"]
        self.ts = [s["t"] for s in self.steps]
        self.by_tid = [{tr["tid"]: tr for tr in s["trains"]} for s in self.steps]
        self.trips = {tr["tid"]: tr for tr in res["trips"]}
        self.pub_hist = res["pub_hist"]
        self.plan = self._platform_plan()
        # a daytime moment with a hold/let-run decision and plenty of traffic: where the demo opens
        cand = [(len(s["recs"]) > 0, len(s["trains"]), s["t"]) for s in self.steps if 11 * 60 <= s["t"] - self.day0 <= 19 * 60]
        self.suggest = max(cand)[2] if cand else self.day0 + 14 * 60

    def at(self, t):
        i = max(0, bisect_right(self.ts, t) - 1)
        return i, self.steps[i]

    def _platform_plan(self):
        """Simulated platform plan (real platform data is not public): greedy interval
        partitioning of each station's scheduled occupancy, down trains on the low
        numbers and up trains on the high ones where possible."""
        plan = {}
        for code, npf in PLATFORMS.items():
            occ = []
            for tr in self.trips.values():
                for s in tr["stops"]:
                    if s["st"] == code:
                        occ.append((s["sch_arr"] - 5, max(s["sch_dep"], s["sch_arr"] + 2) + 5, tr["tid"], tr["dir"]))
            occ.sort()
            free = [-1e9] * npf
            half = max(1, npf // 2)
            for a, b, tid, d in occ:
                pref = list(range(half)) + list(range(half, npf)) if d == 1 else list(range(half, npf)) + list(range(half))
                k = next((p for p in pref if free[p] <= a), min(range(npf), key=lambda p: free[p]))
                free[k] = b
                plan[(code, tid)] = k + 1
        return plan


DAYS = {}
for p in sorted((PROC / "replay").glob("*.pkl")):
    d = Day(pickle.load(open(p, "rb")))
    DAYS[d.date] = d
DEFAULT_DAY = "2024-09-27" if "2024-09-27" in DAYS else (sorted(DAYS)[0] if DAYS else None)


def day(date):
    if date not in DAYS:
        raise HTTPException(404, f"day {date} not replayed")
    return DAYS[date]


def stn_names(code):
    s = STATIONS[SIDX[code]]
    return {"en": s["name"], "hi": s["hi"]}


def city(name):
    return CITY.get(name, (name, name))


# ---------------------------------------------------------------- endpoints
@app.get("/api/meta")
def meta():
    return J(dict(stations=STATIONS, days=sorted(DAYS), default_day=DEFAULT_DAY,
                  days_info={d: dict(day0=D.day0, n_trips=len(D.trips), suggest=D.suggest) for d, D in DAYS.items()},
                  halts=sorted(HALTS), platforms=PLATFORMS, production=REPORT.get("production")))


@app.get("/api/state")
def state(date: str, t: float):
    D = day(date)
    i, s = D.at(t)
    trains = []
    for tr in s["trains"]:
        if not (-15 <= tr["x"] <= STATIONS[-1]["km"] + 15):
            continue
        fc = []
        for f in tr["fc"]:
            fc.append(dict(st=f["st"], ci=f["ci"], sch=f["sch"], pub=f["pub"], cq=f["cq"], eta0=f["eta0"],
                           conf=M.confidence(f["pub"][0], f["pub"][1], tr["overdue"]), reasons=f["reasons"],
                           n_rev=f["n_rev"]))
        trains.append({k: v for k, v in tr.items() if k not in ("fc", "path")} | {"fc": fc})
    # time-distance chart: past (revealed) + forecast median with 80% band
    marey = {}
    for tr in s["trains"]:
        trip = D.trips.get(tr["tid"])
        if not trip:
            continue
        past = [(st["act"], STATIONS[st["ci"]]["km"]) for st in trip["stops"] if st["act"] <= t and st["act"] >= t - 300]
        past.append((t, tr["x"]))
        fut = [(f["cq"][3], STATIONS[f["ci"]]["km"], f["cq"][1], f["cq"][5]) for f in tr["fc"]]
        marey[tr["tid"]] = dict(past=past, fut=fut)
    delays = [tr["delay"] for tr in trains if 0 <= tr["x"] <= STATIONS[-1]["km"]]
    n_fc = sum(len(tr["fc"]) for tr in trains)
    stable = sum(1 for tr in trains for f in tr["fc"] if f["n_rev"] == 0)
    stats = dict(on_corridor=len(delays), median_delay=float(np.median(delays)) if delays else 0,
                 late60=sum(1 for d in delays if d >= 60), recs=len(s["recs"]),
                 stable_share=stable / n_fc if n_fc else 1.0, windows=n_fc)
    return J(dict(t=s["t"], step=i, trains=trains, recs=s["recs"], hot=s["hot"], rain=s["rain"], marey=marey,
                  stats=stats))


@app.get("/api/train")
def train(date: str, tid: int, t: float):
    D = day(date)
    trip = D.trips.get(tid)
    if not trip:
        raise HTTPException(404, "trip")
    i, s = D.at(t)
    live = D.by_tid[i].get(tid)
    stops = []
    for st in trip["stops"]:
        o = {k: v for k, v in st.items() if k not in ("act", "delay")}
        if st["act"] <= t:
            o.update(act=st["act"], delay=st["delay"], done=True)
        stops.append(o)
    hist = {}
    for st in trip["stops"]:
        key = f"{tid}:{st['j']}"
        raw = []
        for k in range(i + 1):
            x = D.by_tid[k].get(tid)
            if not x:
                continue
            f = next((f for f in x["fc"] if f["st"] == st["st"]), None)
            if f:
                raw.append((D.ts[k], f["cq"][1], f["cq"][3], f["cq"][5], f["eta0"]))
        pubs = [h for h in D.pub_hist.get(key, []) if h[0] <= t]
        if raw or pubs:
            hist[st["st"]] = dict(raw=raw, pub=pubs, actual=st["act"] if st["act"] <= t else None)
    ahead = None
    if live and live.get("ahead"):
        ahead = dict(no=live["ahead"], gap=live["ahead_gap"], delay=live["ahead_delay"])
    return J(dict(trip={k: v for k, v in trip.items() if k != "stops"}, stops=stops, live=live and
                  {k: v for k, v in live.items() if k != "path"}, hist=hist, ahead=ahead))


def arrivals(D, code, t, horizon=360):
    i, s = D.at(t)
    out = []
    for tr in D.trips.values():
        for st in tr["stops"]:
            if st["st"] != code:
                continue
            if not (t - 30 <= st["act"] and st["sch_arr"] <= t + horizon):
                continue
            live = D.by_tid[i].get(tr["tid"])
            f = next((f for f in live["fc"] if f["st"] == code), None) if live else None
            o = dict(tid=tr["tid"], no=tr["no"], name=tr["name"], name_hi=tr["name_hi"], cls=tr["cls"], dir=tr["dir"],
                     starts=st["j"] == 0,
                     origin=city(tr["origin"])[0], origin_hi=city(tr["origin"])[1], dest=city(tr["dest"])[0],
                     dest_hi=city(tr["dest"])[1], sch=st["sch_arr"], sch_dep=st["sch_dep"],
                     pf=D.plan.get((code, tr["tid"])))
            if st["act"] <= t:
                o.update(state="arrived", act=st["act"], delay=st["delay"], lo=st["act"], hi=st["act"])
            elif f:
                o.update(state="live", lo=max(f["pub"][0], 5 * math.ceil(t / 5)), hi=f["pub"][1], cq=f["cq"], eta0=f["eta0"], delay=live["delay"],
                         conf=M.confidence(f["pub"][0], f["pub"][1], live["overdue"]), reasons=f["reasons"],
                         n_rev=f["n_rev"], last=live["last"], age=live["age"],
                         why=M.reasons_text(f, live, stn_names(code), "en"),
                         why_hi=M.reasons_text(f, live, stn_names(code), "hi"))
            else:
                pr = st.get("prior")
                if pr:
                    lo, hi = st["sch_arr"] + pr[1], st["sch_arr"] + pr[3]
                    o.update(state="typical", lo=lo, hi=hi, delay=pr[2], n_hist=pr[0])
                else:
                    o.update(state="scheduled", lo=st["sch_arr"], hi=st["sch_arr"] + 15, delay=0)
                o["lo"], o["hi"] = 5 * math.floor(o["lo"] / 5), 5 * math.ceil(o["hi"] / 5)
                o["conf"] = "low"
            out.append(o)
    out.sort(key=lambda o: o["lo"])
    return out


@app.get("/api/station")
def station(date: str, code: str, t: float):
    D = day(date)
    arr = arrivals(D, code, t)
    # predicted platform conflicts among trains not yet arrived
    conf = []
    npf = PLATFORMS.get(code, 2)
    pending = [a for a in arr if a["state"] != "arrived" and a.get("pf")]
    for k, a in enumerate(pending):
        for b in pending[k + 1:]:
            if a["pf"] != b["pf"]:
                continue
            a_end = a["hi"] + max(2, a["sch_dep"] - a["sch"]) + 5
            if b["lo"] < a_end and a["lo"] < b["hi"] + 5:
                busy = defaultdict(list)
                for c in arr:
                    if c.get("pf") and c["state"] != "arrived":
                        busy[c["pf"]].append((c["lo"], c["hi"] + 10))
                alt = next((p for p in range(1, npf + 1) if p != b["pf"] and
                            all(e < b["lo"] or s0 > b["hi"] + 10 for s0, e in busy[p])), None)
                conf.append(dict(pf=a["pf"], a=a["no"], a_name=a["name"], b=b["no"], b_name=b["name"],
                                 overlap_from=max(a["lo"], b["lo"]), overlap_to=min(a_end, b["hi"] + 5), move_to=alt))
    ann = []
    for a in arr:
        if a["state"] == "live" and a["delay"] >= 10:
            ctx = dict(no=a["no"], name_en=a["name"], name_hi=a["name_hi"], origin_en=a["origin"], origin_hi=a["origin_hi"],
                       dest_en=a["dest"], dest_hi=a["dest_hi"], lo=a["lo"], hi=a["hi"], delay=a["delay"], pf=a["pf"])
            ann.append(dict(no=a["no"], stable=a.get("n_rev", 0) == 0 and a["conf"] != "low", **M.announcement(ctx)))
    return J(dict(code=code, name=stn_names(code), platforms=npf, halt=code in HALTS, arrivals=arr,
                  conflicts=conf[:6], announcements=ann[:6]))


def _ctx(D, tid, code, t, role, travel):
    i, s = D.at(t)
    trip = D.trips.get(tid)
    if not trip:
        raise HTTPException(404, "trip")
    stop = next((x for x in trip["stops"] if x["st"] == code), None)
    if not stop:
        raise HTTPException(404, "train does not stop there")
    live = D.by_tid[i].get(tid)
    f = next((f for f in live["fc"] if f["st"] == code), None) if live else None
    base = dict(no=trip["no"], name_en=trip["name"], name_hi=trip["name_hi"], st_en=stn_names(code)["en"],
                st_hi=stn_names(code)["hi"], role=role, sch=stop["sch_arr"], dwell=stop["sch_dep"] - stop["sch_arr"],
                origin=city(trip["origin"]), dest=city(trip["dest"]), pf=D.plan.get((code, tid)))
    if stop["act"] <= t:
        return dict(base, state="arrived", act=stop["act"], lo=stop["act"], hi=stop["act"], delay=stop["delay"],
                    leave_by=None, live=None, f=None)
    if f:
        dec = decide_passenger(dict(cq=f["cq"], dwell=base["dwell"]), t, role, travel, code)
        return dict(base, state=dec["state"], lo=max(f["pub"][0], 5 * math.ceil(t / 5)), hi=f["pub"][1], cq=f["cq"], delay=live["delay"],
                    leave_by=dec["leave_by"], dec=dec, live=live, f=f,
                    conf=M.confidence(f["pub"][0], f["pub"][1], live["overdue"]))
    pr = stop.get("prior")
    if pr:
        lo, hi, med = stop["sch_arr"] + pr[1], stop["sch_arr"] + pr[3], stop["sch_arr"] + pr[2]
    else:
        lo, hi, med = stop["sch_arr"], stop["sch_arr"] + 20, stop["sch_arr"] + 5
    cq = [lo - 5, lo, (lo + med) / 2, med, (med + hi) / 2, hi, hi + 10]
    dec = decide_passenger(dict(cq=cq, dwell=base["dwell"]), t, role, travel, code)
    return dict(base, state=dec["state"], typical=True, lo=max(5 * math.floor(lo / 5), 5 * math.ceil(t / 5)), hi=5 * math.ceil(hi / 5), cq=cq,
                delay=pr[2] if pr else 0, leave_by=dec["leave_by"], dec=dec, live=None, f=None, conf="low",
                n_hist=pr[0] if pr else 0)


@app.get("/api/passenger")
def passenger(date: str, t: float, tid: int, code: str, role: str = "board", travel: int = 30):
    D = day(date)
    c = _ctx(D, tid, code, t, role, travel)
    why = {lg: (M.reasons_text(c["f"], c["live"], stn_names(code), lg) if c.get("f") else []) for lg in ("en", "hi", "hing")}
    out = dict(no=c["no"], name=c["name_en"], name_hi=c["name_hi"], station=stn_names(code), code=code, role=role,
               travel=travel, state=c["state"], lo=c["lo"], hi=c["hi"], sch=c["sch"], delay=c["delay"],
               leave_by=c.get("leave_by"), conf=c.get("conf", "low"), cq=c.get("cq"), dec=c.get("dec"), pf=c.get("pf"),
               origin=c["origin"], dest=c["dest"], why=why, n_hist=c.get("n_hist"), typical=bool(c.get("typical")),
               clock={lg: dict(lo=M.clock(c["lo"], lg), hi=M.clock(c["hi"], lg), window=M.window(c["lo"], c["hi"], lg),
                               leave=M.clock(c["leave_by"], lg) if c.get("leave_by") else None,
                               sch=M.clock(c["sch"], lg)) for lg in ("en", "hi", "hing")})
    if c["state"] != "arrived":
        ctx = dict(no=c["no"], name_en=c["name_en"], name_hi=c["name_hi"], st_en=c["st_en"], st_hi=c["st_hi"],
                   lo=c["lo"], hi=c["hi"], delay=c["delay"], leave_by=c.get("leave_by"), role=role)
        out["sms"] = M.sms_set("window", ctx)
        out["ivr"] = {lg: M.ivr(ctx, lg) for lg in ("hi", "en")}
    if c.get("live"):
        tr = D.trips[tid]
        out["journey"] = [dict(st=f["st"], name=stn_names(f["st"]), pub=f["pub"], cq=f["cq"], sch=f["sch"])
                          for f in c["live"]["fc"]]
        out["last"] = dict(st=c["live"]["last"], age=c["live"]["age"])
    return J(out)


@app.get("/api/messages")
def message_log(date: str, t: float, tid: int, code: str, role: str = "board", travel: int = 30):
    """Every message a subscriber would have received up to t, vs how often a naive
    'notify on every ETA change' service would have pinged them."""
    D = day(date)
    trip = D.trips[tid]
    stop = next(x for x in trip["stops"] if x["st"] == code)
    key = f"{tid}:{stop['j']}"
    hist = [h for h in D.pub_hist.get(key, []) if h[0] <= t]
    log = []
    prev = None
    left = False
    ci = SIDX[code]
    stn = stn_names(code)
    for k in range(len(D.steps)):
        tk = D.ts[k]
        if tk > t:
            break
        x = D.by_tid[k].get(tid)
        if not x or tk >= stop["act"]:
            continue
        f = next((f for f in x["fc"] if f["st"] == code), None)
        if not f:
            continue
        lo, hi = f["pub"]
        dec = decide_passenger(dict(cq=f["cq"], dwell=stop["sch_dep"] - stop["sch_arr"]), tk, role, travel, code)
        ctx = dict(no=trip["no"], name_en=trip["name"], name_hi=trip["name_hi"], st_en=stn["en"], st_hi=stn["hi"],
                   lo=lo, hi=hi, delay=x["delay"], leave_by=dec["leave_by"], role=role, pf=D.plan.get((code, tid)))
        if prev is None:
            log.append(dict(t=tk, why="Subscribed: first window published", **M.sms_set("window", ctx)))
        elif (lo, hi) != prev and not (lo >= prev[0] and hi <= prev[1]):
            ctx.update(old_lo=prev[0], old_hi=prev[1])
            log.append(dict(t=tk, why="Window moved (damped publisher decided it matters)", **M.sms_set("change", ctx)))
        if dec["state"] == "leave_now" and not any(m["kind"] == "leave" for m in log):
            log.append(dict(t=tk, why="Your leave-by time has come", **M.sms_set("leave", ctx)))
        prev_stop = [s_ for s_ in trip["stops"] if s_["act"] <= tk and s_["j"] < stop["j"]]
        if prev_stop and not left and x["last"] == prev_stop[-1]["st"] and prev_stop[-1]["st"] != code and \
                abs(STATIONS[prev_stop[-1]["ci"]]["km"] - STATIONS[ci]["km"]) <= 80:
            ps = prev_stop[-1]["st"]
            ctx.update(prev_st=stn_names(ps)["en"], prev_st_hi=stn_names(ps)["hi"])
            log.append(dict(t=tk, why=f"Train left {ps}, the last stop before yours", **M.sms_set("arriving", ctx)))
            left = True
        prev = (lo, hi)
    # the naive alternative: one SMS per ETA change of 5+ minutes
    naive, last = 0, None
    for k in range(len(D.steps)):
        tk = D.ts[k]
        if tk > t or tk >= stop["act"]:
            break
        x = D.by_tid[k].get(tid)
        f = x and next((f for f in x["fc"] if f["st"] == code), None)
        if f:
            if last is None or abs(f["eta0"] - last) >= 5:
                naive += 1
                last = f["eta0"]
    return J(dict(log=log, naive_count=naive, actual=stop["act"] if stop["act"] <= t else None,
                  pub_hist=hist))


@app.get("/api/halt")
def halt(date: str, code: str, t: float):
    """The missed-call service for a halt with no display board."""
    D = day(date)
    arr = [a for a in arrivals(D, code, t, horizon=240) if a["state"] != "arrived"][:3]
    stn = stn_names(code)
    parts_en = [f"{a['no']} {M.sms_name(a['name'], 12)} {M.gsm_safe(M.window(a['lo'], a['hi'], 'en'))}" for a in arr]
    parts_hing = [f"{a['no']} {M.gsm_safe(M.window(a['lo'], a['hi'], 'hing'))}" for a in arr]
    parts_hi = [f"{a['no']} {M.window(a['lo'], a['hi'], 'hi')}" for a in arr]
    en = f"SAARTHI {stn['en'].upper()}: next trains " + "; ".join(parts_en) + ". 139"
    hing = f"SAARTHI {stn['en']}: agli gaadiyan " + "; ".join(parts_hing) + ". 139"
    hi = f"सारथी {stn['hi']}: अगली गाड़ियाँ " + "; ".join(parts_hi) + "। 139"
    return J(dict(code=code, name=stn, trains=arr, missed_call=f"0{5120 + SIDX[code]:04d}-{SIDX[code] * 7 + 100:03d}-139",
                  sms={lg: dict(text=tx, **M.sms_meta(tx)) for lg, tx in (("en", en), ("hing", hing), ("hi", hi))}))


@app.get("/api/board")
def board(date: str, code: str, t: float):
    D = day(date)
    rows = []
    for a in arrivals(D, code, t, horizon=240):
        if a["starts"] or (a["state"] == "arrived" and a["act"] < t - 10):
            continue
        rows.append(dict(no=a["no"], name=M.short_name(a["name"], 18), name_hi=a["name_hi"], state=a["state"],
                         win=f"{M.clock24(a['lo'])}-{M.clock24(a['hi'])}" if a["state"] != "arrived" else M.clock24(a["act"]),
                         old=f"{M.clock24(a.get('eta0', a['sch']))}", sch=M.clock24(a["sch"]), pf=a.get("pf"),
                         delay=round(a.get("delay", 0)), late_en=M.late_text(a.get("delay", 0), "en").upper(),
                         late_hi=M.late_text(a.get("delay", 0), "hi"), conf=a.get("conf"), lo=a["lo"], hi=a["hi"],
                         origin=a["origin"], origin_hi=a["origin_hi"], dest=a["dest"], dest_hi=a["dest_hi"]))
    return J(dict(code=code, name=stn_names(code), rows=rows[:9], clock=M.clock24(t)))


@app.get("/api/report")
def report():
    return J(dict(report=REPORT, evidence=EVID))


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/p")
def phone():
    return FileResponse(WEB / "p.html")
