"""Feature rows: one per (train, last report, clock time, downstream corridor halt).

Feature groups are nested so the ablation is honest:
  OWN      - the train's own delay history, schedule and learned route recovery
  NETWORK  - train ahead, block occupancy, live path gain, target congestion, rain,
             reporting reliability
  TOPO     - H0 persistence of the space-time delay field
"""
import math
import random

import numpy as np
import pandas as pd

from .config import CALIB_DAYS, CODES, PROC, TEST_DAYS, TRAIN_DAYS, VALID_DAYS
from .network import Corridor, StateSweep

OWN = ["delay", "trend", "trend2", "dmax", "d_origin", "age", "overdue", "hod_s", "hod_c", "dow",
       "priority", "speed", "dir", "h_sch", "km_rem", "n_halts", "hist_train", "hist_n", "pair_med",
       "pair_q90", "tt_slack", "is_terminal", "tgt", "src_in_corr"]
NETWORK = ["ahead_gap_km", "ahead_delay", "ahead_trend", "ahead_anom", "ahead_slower", "ahead_prio",
           "n_ahead_30", "n_ahead_80", "n_between", "live_gain", "live_anom", "live_n", "own_anom", "corr_mean_delay", "tgt_cong", "rain_now",
           "rain_path3", "rain_path_max", "rel_score", "rel_implausible"]
TOPO = ["tda_total", "tda_n10", "tda_max", "tda_ahead_max", "tda_ahead_km"]
CATEGORICAL = ["tgt"]


def trip_rows(C: Corridor, S: StateSweep, tr, r: int, t: float, act, want_topo=True):
    """Rows for every corridor halt still ahead of trip `tr`, as known at time t."""
    targets = tr.corr[tr.corr > r]
    if not len(targets):
        return []
    d = tr.delay
    delay = d[r]
    nxt = r + 1
    overdue = max(0.0, t - (tr.sch_arr[nxt] + delay)) if nxt < len(d) else 0.0
    base = delay + overdue
    mod = t % 1440
    x = C.position(tr, r, t)
    if x is None:
        x = tr.ckm[r] if tr.cidx[r] >= 0 else tr.ckm0
    ci_now = int(np.argmin(np.abs(C.km - x)))

    # --- network state around this train ---
    ahead = []
    same = []
    for m, rm, xm in act:
        if m.tid == tr.tid or m.dir != tr.dir:
            continue
        same.append(m.delay[rm])
        gap = tr.dir * (xm - x)
        if 0.5 < gap <= 80 and tr.dir * (m.ckm[m.corr_last] - x) > 0:
            ahead.append((gap, m, rm))
    ahead.sort(key=lambda a: a[0])
    if ahead:
        g, m, rm = ahead[0]
        a_gap, a_delay = g, m.delay[rm]
        a_trend = m.delay[rm] - m.delay[rm - 1] if rm > 0 else 0.0
        a_anom = float(np.nansum(m.anom[max(1, rm - 1):rm + 1]))
        a_slower, a_prio = tr.speed - m.speed, m.priority - tr.priority
        a_tid = m.tid
    else:
        a_gap, a_delay, a_trend, a_anom, a_slower, a_prio, a_tid = 120.0, 0.0, 0.0, 0.0, 0.0, 0, -1
    own_anom = float(np.nansum(tr.anom[max(1, r - 1):r + 1]))
    n30 = sum(1 for a in ahead if a[0] <= 30)
    n80 = len(ahead)
    corr_mean = float(np.mean(same)) if same else 0.0
    rel = C.rel.get(tr.st[r], {"score": 1.0, "implausible": 0.0})

    if want_topo:
        _, pairs = S.tda(tr.dir, t)
        pers = [(b - dd, ci) for b, dd, ci in pairs]
        tda_total = sum(p for p, _ in pers if p >= 2)
        tda_n10 = sum(1 for p, _ in pers if p >= 10)
        tda_max = max([p for p, _ in pers], default=0.0)

    rows = []
    for j in targets:
        cj = int(tr.cidx[j])
        kmj = C.km[cj]
        lo, hi = sorted((x, kmj))
        h_sch = tr.sch_arr[j] - tr.sch_dep[r]
        hist, hn = C.train_hist(tr.train, tr.st[r], tr.st[j], tr.date)
        p05 = C.run_p05.get((tr.train, tr.st[r], tr.st[j]))
        est_arr = tr.sch_arr[j] + base
        cong = 0
        for m, rm, xm in act:
            if m.tid == tr.tid:
                continue
            k = m.idx_of.get(tr.st[j])
            if k is not None and k > rm and abs(m.sch_arr[k] + m.delay[rm] - est_arr) <= 15:
                cong += 1
        path = [c for c in range(len(CODES)) if lo - 1 <= C.km[c] <= hi + 1]
        lg, la, ln = S.live_gain(tr.dir, x, kmj, t)
        row = dict(
            tid=tr.tid, train=tr.train, date=tr.date, r=r, j=int(j), t=t, base=base, y=d[j],
            delay=delay, trend=delay - d[r - 1] if r > 0 else 0.0, trend2=delay - d[r - 2] if r > 1 else 0.0,
            dmax=float(d[:r + 1].max()), d_origin=d[0], age=t - tr.act_arr[r], overdue=overdue,
            hod_s=math.sin(2 * math.pi * mod / 1440), hod_c=math.cos(2 * math.pi * mod / 1440),
            dow=int((5 + t // 1440) % 7), priority=tr.priority, speed=tr.speed, dir=tr.dir,
            h_sch=h_sch, km_rem=abs(tr.rkm[j] - tr.rkm[r]), n_halts=int(j - r - 1),
            hist_train=hist, hist_n=hn, pair_med=C.pair_med.get((tr.dir, tr.st[r], tr.st[j]), np.nan),
            pair_q90=C.pair_q90.get((tr.dir, tr.st[r], tr.st[j]), np.nan),
            tt_slack=h_sch - p05 if p05 is not None else np.nan, is_terminal=int(j == len(d) - 1),
            tgt=cj, src_in_corr=int(tr.cidx[r] >= 0),
            ahead_tid=a_tid, x=x, own_anom=own_anom, live_anom=la, ahead_anom=a_anom,
            ahead_gap_km=a_gap, ahead_delay=a_delay, ahead_trend=a_trend, ahead_slower=a_slower,
            ahead_prio=a_prio, n_ahead_30=n30, n_ahead_80=n80,
            n_between=sum(1 for a in ahead if a[0] <= abs(kmj - x)),
            live_gain=lg, live_n=ln, corr_mean_delay=corr_mean, tgt_cong=cong,
            rain_now=C.rain_at(ci_now, t), rain_path3=float(np.mean([C.rain_at(c, t, True) for c in path])) if path else 0.0,
            rain_path_max=float(max([C.rain_at(c, t, True) for c in path], default=0.0)),
            rel_score=rel["score"], rel_implausible=rel["implausible"],
        )
        if want_topo:
            ahead_p = [p for p, ci in pers if lo - 1 <= C.km[ci] <= hi + 1]
            strong = [abs(C.km[ci] - x) for p, ci in pers if p >= 10 and lo - 1 <= C.km[ci] <= hi + 1]
            row.update(tda_total=tda_total, tda_n10=tda_n10, tda_max=tda_max,
                       tda_ahead_max=max(ahead_p, default=0.0), tda_ahead_km=min(strong, default=700.0))
        rows.append(row)
    return rows


def build_training(seed=7):
    """Sweep the whole month in report order. Each report yields a sample at the
    moment it lands (age 0) and one 'silent' sample part-way to the next report,
    so the model learns what an overdue train means."""
    random.seed(seed)
    C = Corridor()
    samples = []
    for tr in C.trips:
        lo = max(0, tr.corr_first - 3)
        for r in range(lo, tr.corr_last):
            t0 = tr.act_arr[r]
            samples.append((t0, tr.tid, r))
            gap = tr.act_arr[r + 1] - t0
            if gap >= 10:
                samples.append((t0 + random.uniform(0.2, 0.95) * gap, tr.tid, r))
    samples.sort()
    S = StateSweep(C)
    rows = []
    for k, (t, tid, r) in enumerate(samples):
        S.advance(t)
        act = S.active(t)
        rows += trip_rows(C, S, C.trips[tid], r, t, act)
        if k % 10000 == 0:
            print(f"  {k:,}/{len(samples):,} samples, {len(rows):,} rows")
    df = pd.DataFrame(rows)
    split = {**{d: "train" for d in TRAIN_DAYS}, **{d: "valid" for d in VALID_DAYS},
             **{d: "calib" for d in CALIB_DAYS}, **{d: "test" for d in TEST_DAYS}}
    df["split"] = df.date.map(split).fillna("none")
    df = df[df.split != "none"]
    df.to_pickle(PROC / "rows.pkl")
    print(df.split.value_counts())
    return df


if __name__ == "__main__":
    build_training()
