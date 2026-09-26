"""Evidence for the Proof screen, plus server-ready day bundles.

  * reporting reliability per corridor station (training days)
  * optimism bias: what the timetable promises a late train can recover vs what
    the route actually gives back (test days)
  * rake link: does a late incoming rake delay the return working? (odd/even pairs
    that turn round at a corridor terminal)
  * volatility & promise-keeping of published windows vs today's carry-forward ETA

Run:  py -m saarthi.finalize
"""
import json
import pickle
from collections import defaultdict

import numpy as np
import pandas as pd

from .config import CODES, PROC, TEST_DAYS, TRAIN_DAYS
from .network import T0, Corridor

OUT = PROC / "replay"


def main():
    C = Corridor()
    ev = {}
    # --- reliability ---
    rel = []
    for s in C.stations:
        r = C.rel.get(s["code"])
        if r:
            rel.append(dict(code=s["code"], name=s["name"], n=r["n"], implausible=r["implausible"],
                            round5=r["round5_excess"], score=r["score"]))
    ev["reliability"] = sorted(rel, key=lambda d: d["score"])

    # --- optimism bias: late trains (>=15 min) arriving at big stations, test days ---
    rows = pd.read_pickle(PROC / "rows.pkl")
    te = rows[(rows.split == "test") & (rows.age == 0) & (rows.delay >= 15) & rows.tt_slack.notna()].copy()
    te["promised"] = te.tt_slack.clip(lower=0).clip(upper=te.delay)
    te["actual"] = (te.delay - te.y)
    te["tgt_code"] = te.tgt.map(dict(enumerate(CODES)))
    ob = []
    for code, g in te.groupby("tgt_code"):
        if len(g) < 40:
            continue
        ob.append(dict(code=code, name=C.stations[CODES.index(code)]["name"], n=int(len(g)),
                       promised=float(g.promised.median()), actual=float(g.actual.median()),
                       promised_mean=float(g.promised.mean()), actual_mean=float(g.actual.mean())))
    ev["optimism"] = sorted(ob, key=lambda d: CODES.index(d["code"]))

    # --- rake link: train pairs (odd/even) turning round at a corridor station ---
    by = defaultdict(dict)
    for tr in C.trips:
        by[tr.train][tr.date] = tr
    pts = []
    for tr in C.trips:
        pair = tr.train + 1 if tr.train % 2 else tr.train - 1
        if pair not in by or tr.st[0] not in CODES:
            continue
        origin = tr.st[0]
        dep = tr.sch_dep[0]
        # the most recent arrival of the pair train at this origin, before our departure
        best = None
        for d, pt in by[pair].items():
            k = pt.idx_of.get(origin)
            if k is None or k != len(pt.st) - 1:
                continue
            slack = dep - pt.sch_arr[k]
            if 30 <= slack <= 24 * 60 and (best is None or slack < best[0]):
                best = (slack, pt, k)
        if best:
            slack, pt, k = best
            late_in = pt.delay[k]
            pts.append(dict(train=tr.train, pair=pair, origin=origin, slack=float(slack), in_delay=float(late_in),
                            eaten=float(max(0.0, late_in - slack + 60)), out_delay=float(tr.delay[0]),
                            out_delay_next=float(tr.delay[min(2, len(tr.st) - 1)])))
    rk = pd.DataFrame(pts)
    if len(rk):
        tight = rk[rk.in_delay > rk.slack - 60]
        loose = rk[rk.in_delay <= rk.slack - 60]
        ev["rake"] = dict(n=len(rk), n_tight=len(tight),
                          out_delay_tight=float(tight.out_delay_next.median()) if len(tight) else None,
                          out_delay_loose=float(loose.out_delay_next.median()) if len(loose) else None,
                          corr=float(np.corrcoef(rk.in_delay, rk.out_delay_next)[0, 1]) if len(rk) > 5 else None,
                          sample=rk.sort_values("in_delay", ascending=False).head(12).to_dict("records"))

    # --- what a boarding passenger would have lived through, per strategy ---
    # Each real arrival: the passenger checks 90 min before the train actually came
    # and picks the time to be on the platform. Missed = the train had already left.
    outcomes = defaultdict(list)
    for d in TEST_DAYS:
        p = OUT / f"{d}.pkl"
        if not p.exists():
            continue
        res = pickle.load(open(p, "rb"))
        trips = {tr["tid"]: tr for tr in res["trips"]}
        steps = res["steps"]
        ts = np.array([s["t"] for s in steps])
        seen = set()
        for tr in res["trips"]:
            for s in tr["stops"]:
                act = s["act"]
                if not (res["day0"] <= act < res["day0"] + 1440) or C.trips[tr["tid"]].st[0] == s["st"]:
                    continue
                k = int(np.searchsorted(ts, act - 90, side="right") - 1)
                if k < 0:
                    continue
                x = next((x for x in steps[k]["trains"] if x["tid"] == tr["tid"]), None)
                f = x and next((f for f in x["fc"] if f["st"] == s["st"]), None)
                if not f or (tr["tid"], s["st"]) in seen:
                    continue
                seen.add((tr["tid"], s["st"]))
                dwell = max(1.0, s["sch_dep"] - s["sch_arr"])
                for name, plat in (("timetable", s["sch_arr"] - 10), ("today", f["eta0"] - 10), ("saarthi", f["cq"][0])):
                    missed = act + dwell < plat
                    outcomes[name].append((missed, 0.0 if missed else max(0.0, act - plat)))
    if outcomes:
        ev["passenger_sim"] = {k: dict(n=len(v), missed=float(np.mean([m for m, _ in v])),
                                       wait_med=float(np.median([w for m, w in v if not m])),
                                       wait_mean=float(np.mean([w for m, w in v if not m])),
                                       wait_p90=float(np.quantile([w for m, w in v if not m], 0.9)))
                               for k, v in outcomes.items()}

    # --- volatility over all replayed days ---
    vols = []
    for d in TEST_DAYS:
        p = OUT / f"{d}.pkl"
        if not p.exists():
            continue
        res = pickle.load(open(p, "rb"))
        # server needs the trip-report index j for every stop (publish history is keyed by it)
        for trip in res["trips"]:
            tr = C.trips[trip["tid"]]
            for s in trip["stops"]:
                s["j"] = int(tr.idx_of[s["st"]])
        pickle.dump(res, open(p, "wb"))
        v = pd.DataFrame(res["vol"])
        v["date"] = d
        vols.append(v)
    if vols:
        v = pd.concat(vols)
        ev["volatility"] = dict(
            n=int(len(v)), days=sorted(v.date.unique().tolist()),
            b0_changes=float(v.b0_changes.mean()), b0_slips=float(v.b0_slips.mean()),
            pub_rev=float(v.pub_rev.mean()), pub_ref=float(v.pub_ref.mean()),
            kept_last=float(v.kept_last.mean()), kept_60=float(v.kept_60.mean()),
            b0_slip_dist=v.b0_slips.value_counts().sort_index().to_dict(),
            pub_rev_dist=v.pub_rev.value_counts().sort_index().to_dict(),
            share_b0_3plus=float((v.b0_slips >= 3).mean()), share_pub_3plus=float((v.pub_rev >= 3).mean()),
            per_day={d: dict(n=int(len(g)), b0_slips=float(g.b0_slips.mean()), pub_rev=float(g.pub_rev.mean()),
                             kept_60=float(g.kept_60.mean())) for d, g in v.groupby("date")})
    # --- dataset card numbers ---
    rep = pd.read_pickle(PROC / "reports.pkl")
    q = json.load(open(PROC / "quality.json"))
    ev["dataset"] = dict(corridor_trains=int(C.meta.shape[0]), corridor_trips=len(C.trips), corridor_reports=int(len(rep)),
                         stations=len(CODES), km=float(C.km[-1]), quality=q)
    json.dump(ev, open(PROC / "evidence.json", "w"), indent=1, default=float)
    print(json.dumps({k: (v if k != "rake" else {kk: vv for kk, vv in v.items() if kk != "sample"})
                      for k, v in ev.items() if k in ("volatility", "rake", "dataset")}, indent=1, default=float)[:2500])
    for o in ev["optimism"]:
        print(f"  {o['code']:5s} n={o['n']:4d} timetable promises {o['promised']:5.1f}  route gives {o['actual']:5.1f}")


if __name__ == "__main__":
    main()
