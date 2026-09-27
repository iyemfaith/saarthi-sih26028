"""Replays a held-out day exactly as the live system would have seen it.

Every 5 minutes: ingest the reports that had arrived, rebuild each active train's
features, predict calibrated quantiles, publish a *damped* window, compute the
controller's hold/let-run options and the carry-forward ETA that today's systems
would have shown. Truth (the real arrival) is stored alongside but only revealed
by the API once the clock passes it.

Run:  py -m saarthi.replay            (all test days)
      py -m saarthi.replay 2024-09-27
"""
import json
import math
import pickle
import sys
from collections import defaultdict

import lightgbm as lgb
import numpy as np
import pandas as pd

from .config import CALIB_DAYS, PROC, RAW, TEST_DAYS, TRAIN_DAYS, VALID_DAYS
from .decide import holds
from .features import trip_rows
from .names import display
from .network import T0, Corridor, StateSweep

STEP = 5
MODELS = PROC / "models"
OUT = PROC / "replay"
OUT.mkdir(exist_ok=True)
META = json.load(open(MODELS / "meta.json"))
ALPHAS = META["alphas"]
# calibrated quantile levels published to clients (the conformal offsets widen the tails)
from .decide import ALPHAS_CAL  # noqa: E402
MAXV = 130.0   # km/h: nothing on this corridor is faster, so arrival can't be sooner than this allows

# Human reasons: which model features speak to which cause.
GROUPS = {
    "trend": ["trend", "trend2"],
    "silence": ["overdue", "age"],
    "route": ["hist_train", "hist_n", "pair_med", "pair_q90", "tt_slack", "is_terminal", "tgt", "h_sch",
              "km_rem", "n_halts", "src_in_corr"],
    "late_recovers": ["delay", "dmax", "d_origin"],
    "time_of_day": ["hod_s", "hod_c", "dow"],
    "train_type": ["priority", "speed", "dir"],
    "network": ["ahead_gap_km", "ahead_delay", "ahead_trend", "ahead_anom", "ahead_slower", "ahead_prio",
                "n_ahead_30", "n_ahead_80", "n_between", "live_gain", "live_anom", "live_n", "own_anom",
                "corr_mean_delay", "tgt_cong", "rel_score", "rel_implausible"],
    "weather": ["rain_now", "rain_path3", "rain_path_max"],
    "topology": ["tda_total", "tda_n10", "tda_max", "tda_ahead_max", "tda_ahead_km"],
}
F2G = {f: g for g, fs in GROUPS.items() for f in fs}


def f5(x):
    return 5 * math.floor(x / 5)


def c5(x):
    return 5 * math.ceil(x / 5)


class Publisher:
    """Damped publishing. The raw window moves every few minutes; people should not.
      * earlier by >5 min  -> publish at once (someone might miss the train)
      * later              -> only if the median has left the window by 10+ min, or
                              the window is 15+ min old and has drifted 10+ min
      * narrower, nested   -> refine (good news never breaks a promise)
      * expired            -> the window's end has passed without the train: publish
    Windows snap to 5 minutes so they read like a promise, not a calculation."""

    def __init__(self):
        self.s = {}

    def step(self, key, t, lo, hi, med):
        lo, hi = max(f5(lo), c5(t)), max(c5(hi), c5(t) + 5)
        st = self.s.get(key)
        if st is None:
            self.s[key] = st = dict(lo=lo, hi=hi, t=t, n_rev=0, n_ref=0, hist=[(t, lo, hi, "first")])
            return st
        kind = None
        if lo < st["lo"] - 5:
            kind = "earlier"
        elif st["hi"] < t:
            kind = "expired"
        elif med > st["hi"] + 10 or (lo - st["lo"] >= 10 and hi - st["hi"] >= 10 and t - st["t"] >= 15):
            kind = "later"
        elif lo >= st["lo"] and hi <= st["hi"] and (hi - lo) <= 0.7 * (st["hi"] - st["lo"]) and t - st["t"] >= 10:
            kind = "narrower"
        if kind:
            st.update(lo=lo, hi=hi, t=t)
            st["n_ref" if kind == "narrower" else "n_rev"] += 1
            st["hist"].append((t, lo, hi, kind))
        return st


def build_prior(C):
    """Unconditional window per (train, station) from days before the test week:
    what we can promise before the train has even started."""
    days = set(TRAIN_DAYS + VALID_DAYS + CALIB_DAYS)
    acc = defaultdict(list)
    for tr in C.trips:
        if tr.date in days:
            for j in tr.corr:
                acc[(tr.train, tr.st[j])].append(tr.delay[j])
    return {k: (len(v), *np.quantile(v, [0.1, 0.5, 0.9]).tolist()) for k, v in acc.items() if len(v) >= 4}


def run_day(C, models, date, prior, names):
    feats = META["features"]
    day0 = (pd.Timestamp(date) - T0) / pd.Timedelta(minutes=1)
    S = StateSweep(C)
    S.advance(day0 - 1)
    pub = Publisher()
    off = {lv: {int(k): v for k, v in o.items()} for lv, o in META["conformal"].items()}
    buckets = META["buckets"]
    steps, b0_hist = [], defaultdict(list)
    for t in np.arange(day0, day0 + 1440 + STEP, STEP):
        S.advance(t)
        act = S.active(t)
        rows, owners = [], []
        for tr, r, x in act:
            rr = trip_rows(C, S, tr, r, t, act, want_topo=True)
            rows += rr
        trains = []
        if rows:
            df = pd.DataFrame(rows)
            P = np.column_stack([df.base.to_numpy() + models[a].predict(df[feats]) for a in ALPHAS])
            P = np.maximum(np.sort(P, axis=1), 0.0)
            contrib = models[0.5].predict(df[feats], pred_contrib=True)[:, :-1]
            b = np.clip(np.searchsorted(buckets, df.h_sch.to_numpy(), side="right") - 1, 0, len(buckets) - 2)
            o50 = np.array([off["50"][k] for k in b]); o80 = np.array([off["80"][k] for k in b])
            o90 = np.array([off["90"][k] for k in b])
            CQ = np.column_stack([P[:, 0] - o90, P[:, 1] - o80, P[:, 2] - o50, P[:, 3], P[:, 4] + o50,
                                  P[:, 5] + o80, P[:, 6] + o90])
            CQ = np.maximum(CQ, 0.0)
            by_tid = defaultdict(list)
            for i, row in enumerate(rows):
                by_tid[row["tid"]].append(i)
            pos = {tr.tid: (r, x) for tr, r, x in act}
            for tid, idx in by_tid.items():
                tr = C.trips[tid]
                r, x = pos[tid]
                fcs, path = [], {}
                for i in idx:
                    row = rows[i]
                    j = row["j"]
                    sch = tr.sch_arr[j]
                    dwell = tr.sch_dep[j] - tr.sch_arr[j]
                    floor = t + abs(C.km[tr.cidx[j]] - x) / MAXV * 60
                    cq = np.maximum(sch + CQ[i], floor)
                    cq = np.maximum.accumulate(cq)
                    g = defaultdict(float)
                    for f, v in zip(feats, contrib[i]):
                        g[F2G.get(f, "other")] += v
                    reasons = sorted(((k, round(v, 1)) for k, v in g.items() if abs(v) >= 1.5), key=lambda z: -abs(z[1]))[:3]
                    st = pub.step((tid, j), t, cq[1], cq[5], cq[3])
                    eta0 = sch + row["base"]
                    b0_hist[(tid, j)].append((t, round(eta0)))
                    code = tr.st[j]
                    fcs.append(dict(st=code, ci=int(tr.cidx[j]), sch=float(sch), dwell=float(dwell),
                                    cq=[round(float(v), 1) for v in cq], pub=[float(st["lo"]), float(st["hi"])],
                                    n_rev=st["n_rev"], n_ref=st["n_ref"], eta0=float(round(eta0)), reasons=[(k, float(v)) for k, v in reasons],
                                    actual=float(tr.act_arr[j]), term=bool(j == len(tr.st) - 1)))
                    path[int(tr.cidx[j])] = (float(cq[3]), float(cq[3] + dwell), float(sch), float(sch + dwell))
                # passing (non-halt) corridor stations: interpolate forecast and schedule by km
                sx = tr.sch_arr[r] if tr.cidx[r] < 0 else tr.sch_dep[r]
                pts = sorted([(C.km[c], v[0], v[1], v[2], v[3]) for c, v in path.items()] +
                             [(x, t, t, t - rows[idx[0]]["base"], t - rows[idx[0]]["base"])], key=lambda z: tr.dir * z[0])
                for c in range(len(C.km)):
                    if c in path:
                        continue
                    k = C.km[c]
                    for p0, p1 in zip(pts, pts[1:]):
                        if tr.dir * (k - p0[0]) > 0 and tr.dir * (p1[0] - k) > 0:
                            f = (k - p0[0]) / (p1[0] - p0[0])
                            tt = p0[2] + (p1[1] - p0[2]) * f
                            ss = p0[4] + (p1[3] - p0[4]) * f
                            path[c] = (tt, tt, ss, ss)
                            break
                en, hi = names[tr.train]
                rw = rows[idx[0]]
                ahead = C.trips[rw["ahead_tid"]] if rw["ahead_tid"] >= 0 else None
                trains.append(dict(tid=tid, no=tr.train, name=en, name_hi=hi, cls=tr.cls, dir=tr.dir,
                                   priority=tr.priority, load=tr.load, speed=float(tr.speed), x=round(float(x), 1),
                                   delay=round(float(rw["base"]), 1), last=tr.st[r], last_t=float(tr.act_arr[r]),
                                   last_in_corr=bool(tr.cidx[r] >= 0), age=round(float(rw["age"])),
                                   overdue=round(float(rw["overdue"])), next=tr.st[r + 1] if r + 1 < len(tr.st) else None,
                                   ahead=ahead.train if ahead else None, ahead_gap=round(float(rw["ahead_gap_km"]), 1),
                                   ahead_delay=round(float(rw["ahead_delay"])) if ahead else None,
                                   live_anom=round(float(rw["live_anom"]), 1), rain=round(float(rw["rain_path_max"]), 1),
                                   fc=fcs, path={int(k): v for k, v in path.items()}))
        recs = holds(trains, t, C.stations)
        # topology snapshot for the corridor strip (both directions)
        hot = []
        for d in (1, -1):
            _, pairs = S.tda(d, t)
            for bb, dd, ci in pairs:
                if bb - dd >= 10:
                    hot.append(dict(dir=d, ci=int(ci), pers=round(float(bb - dd), 1)))
        rain = [round(C.rain_at(c, t), 1) for c in range(len(C.km))]
        steps.append(dict(t=float(t), trains=trains, recs=recs, hot=hot, rain=rain))
        if len(steps) % 48 == 0:
            print(f"  {date} {int((t - day0) // 60):02d}:00  trains {len(trains)}  recs {len(recs)}")
    # volatility accounting: carry-forward ETA vs published window, final 3 h before arrival
    vol = []
    for key, st in pub.s.items():
        tid, j = key
        tr = C.trips[tid]
        act = tr.act_arr[j]
        if not (day0 <= act < day0 + 1440):
            continue
        h0 = [(tt, e) for tt, e in b0_hist[key] if act - 180 <= tt < act]
        if len(h0) < 6:
            continue
        b0_changes = sum(1 for (_, a), (_, b) in zip(h0, h0[1:]) if abs(b - a) >= 3)
        b0_slips = sum(1 for (_, a), (_, b) in zip(h0, h0[1:]) if b - a >= 5)
        ph = [h for h in st["hist"] if act - 180 <= h[0] < act]
        pubs = [h for h in st["hist"] if h[0] < act]
        last = pubs[-1] if pubs else None
        at60 = [h for h in st["hist"] if h[0] <= act - 60]
        vol.append(dict(tid=tid, train=tr.train, st=tr.st[j], b0_changes=b0_changes, b0_slips=b0_slips,
                        pub_rev=sum(1 for h in ph if h[3] in ("earlier", "later", "expired")),
                        pub_ref=sum(1 for h in ph if h[3] == "narrower"),
                        kept_last=bool(last and last[1] <= act <= last[2]),
                        kept_60=bool(at60 and at60[-1][1] <= act <= at60[-1][2]),
                        b0_err_60=abs(act - [e for tt, e in b0_hist[key] if tt <= act - 60][-1])
                        if any(tt <= act - 60 for tt, _ in b0_hist[key]) else None))
    return dict(date=date, day0=float(day0), step=STEP, steps=steps, vol=vol,
                pub_hist={f"{k[0]}:{k[1]}": v["hist"] for k, v in pub.s.items()})


def day_static(C, date, prior, names):
    """Everything about the day that does not depend on the clock: trips that touch
    the day, their full corridor reports (truth, revealed by time on the client)."""
    day0 = (pd.Timestamp(date) - T0) / pd.Timedelta(minutes=1)
    trips = []
    for tr in C.trips:
        if not tr.corr.size:
            continue
        t_in, t_out = tr.sch_arr[tr.corr_first], tr.act_arr[tr.corr_last]
        if t_out < day0 - 120 or t_in > day0 + 1440 + 60:
            continue
        en, hi = names[tr.train]
        m = C.meta.loc[tr.train]
        trips.append(dict(
            tid=tr.tid, no=tr.train, name=en, name_hi=hi, cls=tr.cls, dir=tr.dir, load=tr.load,
            origin=m.origin_name, dest=m.dest_name, date=tr.date,
            stops=[dict(st=tr.st[j], ci=int(tr.cidx[j]), sch_arr=float(tr.sch_arr[j]), sch_dep=float(tr.sch_dep[j]),
                        act=float(tr.act_arr[j]), delay=float(tr.delay[j]),
                        prior=prior.get((tr.train, tr.st[j]))) for j in tr.corr]))
    return trips


def main(days):
    C = Corridor()
    models = {a: lgb.Booster(model_file=str(MODELS / f"q{int(round(a * 100)):02d}.txt")) for a in ALPHAS}
    prior = build_prior(C)
    edges = pd.read_csv(PROC / "irn_edges.csv")
    codes = set(edges["from"]) | set(edges["to"])
    names = {int(t): display(t, r["name"], r.origin_name, r.dest_name, codes) for t, r in C.meta.iterrows()}
    json.dump({str(k): v for k, v in names.items()}, open(PROC / "names.json", "w", encoding="utf-8"), ensure_ascii=False)
    for d in days:
        print(f"replaying {d}")
        res = run_day(C, models, d, prior, names)
        res["trips"] = day_static(C, d, prior, names)
        pickle.dump(res, open(OUT / f"{d}.pkl", "wb"))
        v = pd.DataFrame(res["vol"])
        if len(v):
            print(f"  {len(v)} arrivals: carry-forward changes/arrival {v.b0_changes.mean():.2f} "
                  f"(slips {v.b0_slips.mean():.2f})  published revisions {v.pub_rev.mean():.2f}  "
                  f"kept(last) {v.kept_last.mean():.2%}  kept(T-60) {v.kept_60.mean():.2%}")


if __name__ == "__main__":
    main(sys.argv[1:] or TEST_DAYS)
