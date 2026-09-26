"""Stage 2 - MODEL THE STRUCTURE.

A time-aware view of the corridor. Given a clock time t it answers, using only
reports that had arrived by t:
  * where every train is (dead-reckoned from its last report + current delay),
  * which train is ahead of whom, how far, how late, how fast,
  * how many trains occupy the blocks ahead (inferred block occupancy),
  * how much delay the path ahead is currently costing trains (live path gain),
  * the rain along the path,
  * the topological shape of the space-time delay field (H0 persistence).

The same object builds training rows (sweeping every report in time order) and
live replay rows, so training and serving can never drift apart.
"""
import json
from bisect import bisect_right
from collections import defaultdict, deque

import numpy as np
import pandas as pd

from .config import CODES, PROC, ROOT, TRAIN_DAYS

T0 = pd.Timestamp("2024-08-31")
NC = len(CODES)
TDA_BIN, TDA_BINS = 15, 12          # space-time grid: 15-min bins over the last 3 h
LIVE_WINDOW = 180                    # minutes of traversals used for live path gain


def to_min(ts) -> np.ndarray:
    return ((pd.to_datetime(ts) - T0) / pd.Timedelta(minutes=1)).to_numpy(dtype=float)


class Trip:
    __slots__ = ("tid", "train", "date", "dir", "st", "cidx", "rkm", "sch_arr", "sch_dep", "delay",
                 "act_arr", "corr", "ckm", "corr_first", "corr_last", "rkm0", "ckm0", "speed", "cls",
                 "priority", "load", "dest", "idx_of", "anom", "pk")


class Corridor:
    def __init__(self):
        self.stations = json.load(open(PROC / "corridor.json", encoding="utf-8"))
        self.km = np.array([s["km"] for s in self.stations])
        rep = pd.read_pickle(PROC / "reports.pkl")
        meta = pd.read_csv(PROC / "trains.csv").set_index("train")
        self.meta = meta
        self.trips: list[Trip] = []
        for (train, date), g in rep.groupby(["train", "date"], sort=True):
            m = meta.loc[train]
            tr = Trip()
            tr.tid, tr.train, tr.date = len(self.trips), int(train), date
            tr.dir = 1 if m.dir == "DN" else -1
            tr.st = g.station.to_numpy()
            tr.cidx = g.cidx.to_numpy()
            tr.rkm = g.route_km.to_numpy(dtype=float)
            tr.sch_arr, tr.sch_dep = to_min(g.sch_arr), to_min(g.sch_dep)
            tr.delay = g.delay.to_numpy(dtype=float)
            tr.act_arr = tr.sch_arr + tr.delay
            tr.corr = np.flatnonzero(tr.cidx >= 0)
            if len(tr.corr) < 2:
                continue
            tr.ckm = np.where(tr.cidx >= 0, self.km[np.clip(tr.cidx, 0, None)], np.nan)
            tr.corr_first, tr.corr_last = tr.corr[0], tr.corr[-1]
            tr.rkm0, tr.ckm0 = tr.rkm[tr.corr_first], tr.ckm[tr.corr_first]
            span_t = tr.sch_arr[tr.corr_last] - tr.sch_dep[tr.corr_first]
            span_k = abs(tr.ckm[tr.corr_last] - tr.ckm0)
            tr.speed = 60 * span_k / max(span_t, 1)
            tr.cls, tr.priority, tr.load, tr.dest = m.cls, int(m.priority), int(m.load), m.dest
            tr.idx_of = {}
            for i, s in enumerate(tr.st):
                tr.idx_of.setdefault(s, i)
            # corridor-km of every report: exact at corridor halts, extrapolated by route
            # distance from the nearest corridor halt outside it
            tr.pk = np.empty(len(tr.st))
            for i in range(len(tr.st)):
                if tr.cidx[i] >= 0:
                    tr.pk[i] = tr.ckm[i]
                else:
                    c = tr.corr_first if i < tr.corr_first else tr.corr_last
                    tr.pk[i] = tr.ckm[c] + tr.dir * (tr.rkm[i] - tr.rkm[c])
            self.trips.append(tr)
        for i, tr in enumerate(self.trips):
            tr.tid = i
        # Global report stream in the order the control office would receive it.
        ev = [(tr.act_arr[r], tr.tid, r) for tr in self.trips for r in range(len(tr.st))]
        ev.sort()
        self.ev_t = np.array([e[0] for e in ev])
        self.ev = ev
        self._weather()
        self._reliability()
        self._runtime_stats()
        self._anomalies()

    # ---------- static context (fit on training days only) ----------
    def _weather(self):
        w = json.load(open(ROOT / "data" / "raw" / "weather_openmeteo_sep2024.json"))
        t0 = pd.Timestamp(w["NDLS"]["hourly"]["time"][0])
        self.w_t0 = (t0 - T0) / pd.Timedelta(minutes=1)
        self.rain = np.array([[v or 0.0 for v in w[c]["hourly"]["precipitation"]] for c in CODES])
        self.rain_cum3 = np.stack([pd.Series(r).rolling(3, min_periods=1).sum().to_numpy() for r in self.rain])

    def rain_at(self, ci: int, t: float, cum=False) -> float:
        h = int((t - self.w_t0) // 60) - 1        # last *completed* hour: no peeking
        arr = self.rain_cum3 if cum else self.rain
        return float(arr[ci, min(max(h, 0), arr.shape[1] - 1)])

    def _reliability(self):
        """Per-station reporting reliability from training days.
        implausible: implied run from the previous halt faster than 70% of the
        fastest *scheduled* run between the same two stations (someone logged the
        time late at one end, early at the other).
        round5: share of non-zero delays that are exact multiples of 5 minutes,
        in excess of the 20% expected by chance (hand-rounded manual entries)."""
        fastest = {}
        for tr in self.trips:
            for a, b in zip(range(len(tr.st) - 1), range(1, len(tr.st))):
                k = (tr.st[a], tr.st[b])
                run = tr.sch_arr[b] - tr.sch_dep[a]
                if run > 0:
                    fastest[k] = min(fastest.get(k, 1e9), run)
        imp, tot, r5, nz = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
        for tr in self.trips:
            if tr.date not in TRAIN_DAYS:
                continue
            for b in range(1, len(tr.st)):
                a = b - 1
                s = tr.st[b]
                run = (tr.sch_arr[b] + tr.delay[b]) - (tr.sch_dep[a] + tr.delay[a])
                f = fastest.get((tr.st[a], tr.st[b]))
                tot[s] += 1
                if f and f > 8 and run < 0.7 * f:
                    imp[s] += 1
                if tr.delay[b] > 0:
                    nz[s] += 1
                    r5[s] += tr.delay[b] % 5 == 0
        self.rel = {}
        for s in tot:
            ir = imp[s] / tot[s]
            rr = max(0.0, r5[s] / nz[s] - 0.2) if nz[s] >= 20 else 0.0
            self.rel[s] = dict(n=tot[s], implausible=ir, round5_excess=rr, score=max(0.0, 1 - 3 * ir - rr))

    def _runtime_stats(self):
        """Learned recovery: what the route actually gives back, per train and per
        station pair, from training days only (out-of-fold for training rows)."""
        by_train = defaultdict(lambda: defaultdict(list))   # (train, s, j) -> {date: delta}
        by_pair = defaultdict(list)                          # (dir, s, j) -> deltas
        runtime = defaultdict(list)                          # (train, s, j) -> actual run minutes
        for tr in self.trips:
            if tr.date not in TRAIN_DAYS:
                continue
            idx = list(range(max(0, tr.corr_first - 3), tr.corr_last))
            for r in idx:
                for j in tr.corr[tr.corr > r]:
                    d = tr.delay[j] - tr.delay[r]
                    by_train[(tr.train, tr.st[r], tr.st[j])][tr.date].append(d)
                    by_pair[(tr.dir, tr.st[r], tr.st[j])].append(d)
                    runtime[(tr.train, tr.st[r], tr.st[j])].append(tr.act_arr[j] - (tr.sch_dep[r] + tr.delay[r]))
        self.by_train = by_train
        self.pair_med = {k: float(np.median(v)) for k, v in by_pair.items() if len(v) >= 5}
        self.pair_q90 = {k: float(np.quantile(v, 0.9)) for k, v in by_pair.items() if len(v) >= 5}
        self.run_p05 = {k: float(np.quantile(v, 0.05)) for k, v in runtime.items() if len(v) >= 3}

    def _anomalies(self):
        """Delay gained between consecutive halts *minus what this train usually
        gains there* (training days, out-of-fold by date). Raw gains are dominated
        by each timetable's own padding; the anomaly isolates network conditions."""
        seg = defaultdict(lambda: defaultdict(list))
        pooled = defaultdict(list)
        for tr in self.trips:
            if tr.date not in TRAIN_DAYS:
                continue
            for r in range(1, len(tr.st)):
                g = tr.delay[r] - tr.delay[r - 1]
                seg[(tr.train, tr.st[r - 1], tr.st[r])][tr.date].append(g)
                pooled[(tr.dir, tr.st[r - 1], tr.st[r])].append(g)
        pooled = {k: float(np.median(v)) for k, v in pooled.items()}
        for tr in self.trips:
            tr.anom = np.full(len(tr.st), np.nan)
            for r in range(1, len(tr.st)):
                d = seg.get((tr.train, tr.st[r - 1], tr.st[r]), {})
                vals = [x for dd, xs in d.items() if dd != tr.date for x in xs]
                typ = float(np.median(vals)) if len(vals) >= 2 else pooled.get((tr.dir, tr.st[r - 1], tr.st[r]))
                if typ is not None:
                    tr.anom[r] = (tr.delay[r] - tr.delay[r - 1]) - typ

    def train_hist(self, train, s, j, date):
        """Median delay change for this train over s->j on *other* training days."""
        d = self.by_train.get((train, s, j))
        if not d:
            return np.nan, 0
        vals = [x for dd, xs in d.items() if dd != date for x in xs]
        return (float(np.median(vals)), len(vals)) if vals else (np.nan, 0)

    # ---------- dynamic state ----------
    def position(self, tr: Trip, r: int, t: float):
        """Dead-reckoned corridor km of trip `tr` at time t, given its last report r.
        Returns None once the train has left the corridor."""
        tau = t - tr.delay[r]                      # equivalent scheduled time
        n = len(tr.st)
        k = r
        while k + 1 < n and tr.sch_arr[k + 1] <= tau:
            k += 1
        if k >= tr.corr_last:
            return None
        if tau <= tr.sch_dep[k] or k + 1 >= n:
            return float(tr.pk[k])
        f = (tau - tr.sch_dep[k]) / max(tr.sch_arr[k + 1] - tr.sch_dep[k], 1e-6)
        return float(tr.pk[k] + min(f, 1.0) * (tr.pk[k + 1] - tr.pk[k]))


class StateSweep:
    """Replays the report stream. `advance(t)` ingests every report with time <= t;
    after that, all queries see exactly what a control office would know at t."""

    def __init__(self, C: Corridor):
        self.C = C
        self.p = 0
        self.last = {}                             # tid -> last report index (live trips only)
        self.seg = {1: [deque() for _ in range(NC - 1)], -1: [deque() for _ in range(NC - 1)]}
        self.cells = {1: deque(), -1: deque()}     # (t, cidx, gain) for the TDA field
        self._tda_cache = {}

    def advance(self, t: float):
        C = self.C
        while self.p < len(C.ev) and C.ev[self.p][0] <= t:
            te, tid, r = C.ev[self.p]
            tr = C.trips[tid]
            prev = self.last.get(tid)
            self.p += 1
            if prev is not None and r <= prev:     # out-of-order log entry: keep the newer one
                continue
            if r >= tr.corr_first - 3 or tr.cidx[r] >= 0:
                self.last[tid] = r
            if prev is not None and tr.cidx[r] >= 0:
                gain = tr.delay[r] - tr.delay[prev]
                an = float(np.nansum(tr.anom[prev + 1:r + 1]))
                self.cells[tr.dir].append((te, int(tr.cidx[r]), an))
                if tr.cidx[prev] >= 0 and tr.cidx[prev] != tr.cidx[r]:
                    a, b = sorted((int(tr.cidx[prev]), int(tr.cidx[r])))
                    span = max(C.km[b] - C.km[a], 1)
                    for s in range(a, b):
                        self.seg[tr.dir][s].append((te, gain / span, an / span))
        for tid in [k for k, r in self.last.items()
                    if r >= C.trips[k].corr_last or t - C.trips[k].act_arr[r] > 360]:
            del self.last[tid]
        for d in (1, -1):
            for q in self.seg[d]:
                while q and q[0][0] < t - LIVE_WINDOW:
                    q.popleft()
            while self.cells[d] and self.cells[d][0][0] < t - TDA_BIN * TDA_BINS:
                self.cells[d].popleft()

    def active(self, t: float):
        """(trip, last report, corridor km) for trains currently on or approaching the corridor."""
        out = []
        for tid, r in self.last.items():
            tr = self.C.trips[tid]
            x = self.C.position(tr, r, t)
            if x is not None:
                out.append((tr, r, x))
        return out

    def live_gain(self, d: int, x0: float, x1: float, t: float):
        """Delay the path x0->x1 is currently adding (minutes), from recent traversals."""
        C = self.C
        lo, hi = min(x0, x1), max(x0, x1)
        tot, anom, n = 0.0, 0.0, 0
        for s in range(NC - 1):
            a, b = C.km[s], C.km[s + 1]
            ov = min(b, hi) - max(a, lo)
            if ov <= 0:
                continue
            q = self.seg[d][s]
            if q:
                w = [np.exp(-(t - te) / 90) for te, _, _ in q]
                sw = sum(w)
                tot += ov * sum(wi * g for wi, (_, g, _) in zip(w, q)) / sw
                anom += ov * sum(wi * an for wi, (_, _, an) in zip(w, q)) / sw
                n += len(q)
        return tot, anom, n

    def tda(self, d: int, t: float):
        """H0 persistence of the space-time delay-anomaly field (superlevel filtration
        on the station x time grid graph). Components = congestion hotspots;
        persistence = how strongly a hotspot stands above its surroundings."""
        key = (d, int(t // 5))
        if key in self._tda_cache:
            return self._tda_cache[key]
        grid = np.zeros((NC, TDA_BINS))
        cnt = np.zeros((NC, TDA_BINS))
        for te, ci, g in self.cells[d]:
            b = int((t - te) // TDA_BIN)
            if 0 <= b < TDA_BINS:
                grid[ci, b] += g
                cnt[ci, b] += 1
        grid = np.where(cnt > 0, grid / np.maximum(cnt, 1), 0.0)
        pairs = persistence_h0(grid)
        if len(self._tda_cache) > 64:
            self._tda_cache.clear()
        self._tda_cache[key] = (grid, pairs)
        return grid, pairs


def persistence_h0(grid: np.ndarray):
    """0-dim superlevel persistence on a 4-connected grid via union-find.
    Returns [(birth, death, station_index)] for components born above 0."""
    H, W = grid.shape
    order = np.argsort(-grid, axis=None)
    parent = -np.ones(H * W, dtype=int)
    birth = np.zeros(H * W)
    peak = np.zeros(H * W, dtype=int)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    out = []
    for flat in order:
        v = grid.flat[flat]
        if v <= 0:
            break
        parent[flat], birth[flat], peak[flat] = flat, v, flat
        i, j = divmod(flat, W)
        for ni, nj in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)):
            if 0 <= ni < H and 0 <= nj < W:
                nb = ni * W + nj
                if parent[nb] < 0:
                    continue
                ra, rb = find(flat), find(nb)
                if ra == rb:
                    continue
                young, old = (ra, rb) if birth[ra] < birth[rb] else (rb, ra)
                out.append((birth[young], v, peak[young] // W))
                parent[young] = old
    roots = {find(f) for f in range(H * W) if parent[f] >= 0}
    out += [(birth[r], 0.0, peak[r] // W) for r in roots]
    return out
