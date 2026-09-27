"""Stage 4 - MAKE THE DECISION.

Passenger: the same forecast gives different advice to different people,
because the cost of being wrong is asymmetric.
  * boarding  - missing the train is catastrophic -> plan on the calibrated 5th
                percentile of arrival (be early 19 times out of 20)
  * receiving - arriving a little after the train is a mild cost, a two-hour wait
                at 2 a.m. is not -> plan on the 20th percentile

Controller: hold / let-run. When two same-direction forecast paths cross inside a
block section (the follower would catch the leader where nobody can overtake),
compare letting the leader run (followers crawl behind it) with looping the
leader at the last station before the conflict so the followers pass.
Costs are passenger-minutes, not train-minutes.
"""
import math

HEADWAY = 6          # min between successive trains on the same line (planning assumption)
MAX_HOLD = 15        # a controller will not loop a train longer than this for a precedence
MIN_SAVING = 8000    # passenger-minutes; below this the recommendation is noise
MAX_LOSS = 30        # cap on one follower's loss per block (schedule padding inflates slow run-times)
BUFFER_BIG, BUFFER_SMALL = 15, 8   # minutes to ticket/platform at a junction vs a halt
ALPHAS_CAL = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]   # levels of the published calibrated quantiles
BIG = {"NDLS", "GZB", "ALJN", "TDL", "ETW", "CNB", "PRYJ"}


def quantile_at(qs, alphas, p):
    """Linear interpolation of the published quantile curve."""
    if p <= alphas[0]:
        return qs[0]
    for (a0, q0), (a1, q1) in zip(zip(alphas, qs), zip(alphas[1:], qs[1:])):
        if p <= a1:
            return q0 + (q1 - q0) * (p - a0) / (a1 - a0)
    return qs[-1]


def passenger(fc, now, role="board", travel=30, station=""):
    """fc: forecast dict with calibrated 'cq' (clock-minute quantiles at ALPHAS_CAL).
    Returns the decision and the numbers behind it."""
    buf = BUFFER_BIG if station in BIG else BUFFER_SMALL
    p = 0.05 if role == "board" else 0.20
    target = quantile_at(fc["cq"], ALPHAS_CAL, p)
    leave_by = 5 * math.floor((target - travel - buf) / 5)
    med = quantile_at(fc["cq"], ALPHAS_CAL, 0.5)
    hi = quantile_at(fc["cq"], ALPHAS_CAL, 0.9)
    wait_med = max(0.0, med - (leave_by + travel + buf)) + buf
    wait_hi = max(0.0, hi - (leave_by + travel + buf)) + buf
    mins = leave_by - now
    night = (now % 1440) >= 22 * 60 or (now % 1440) < 5 * 60
    if fc.get("arrived"):
        state = "arrived"
    elif now + travel > med + (fc.get("dwell", 2) if role == "board" else 30):
        state = "too_late"
    elif mins <= 0:
        state = "leave_now"
    elif mins <= 15:
        state = "get_ready"
    elif night and mins > 60:
        state = "rest"
    else:
        state = "wait"
    return dict(state=state, leave_by=leave_by, mins_to_leave=mins, wait_med=wait_med, wait_hi=wait_hi,
                buffer=buf, basis_p=p, wake_call=leave_by - 45 if state == "rest" else None)


def holds(trains, t, stations):
    """For each leader L and each block section (a -> b) ahead of it, collect the
    followers whose median forecast path crosses L's inside that section. Compare
    letting L run (every follower crawls behind it) with looping L at `a` until
    the last of them has passed. Returns recommendations, biggest saving first."""
    kms = [s["km"] for s in stations]
    recs = []
    for d in (1, -1):
        tl = [x for x in trains if x["dir"] == d and x["path"]]
        for L in tl:
            pl = L["path"]
            ahead = sorted([c for c in pl if d * (kms[c] - L["x"]) > 0], key=lambda c: d * kms[c])
            for a, b in zip(ahead, ahead[1:]):
                # L's forecast departure from a, then its *scheduled* running time a->b:
                # conflicts are about running physics, not about delay the model expects
                la = pl[a][1]
                lb = la + (pl[b][2] - pl[a][3])
                if not (t + 3 < la <= t + 45):
                    continue
                fs = []
                for F in tl:
                    if F is L or not (0 < d * (L["x"] - F["x"]) <= 60):
                        continue
                    pf = F["path"]
                    if a in pf and b in pf:
                        fa = pf[a][1]
                        fb = fa + (pf[b][2] - pf[a][3])
                        if fa > la and fb < lb + 2:
                            fs.append((F, fa, fb, max(0.0, lb + HEADWAY - fb)))
                if not fs:
                    continue
                fs.sort(key=lambda z: z[1])
                # cascade: each follower also keeps headway behind the one before it
                run_losses, prev = [], lb
                for F, fa, fb, _ in fs:
                    arr = max(fb, prev + HEADWAY)
                    run_losses.append(min(arr - fb, MAX_LOSS))   # slow trains' schedules carry padding
                    prev = arr
                hold = max(0.0, fs[-1][1] + HEADWAY - la)
                if hold > MAX_HOLD or sum(run_losses) < 5:
                    break
                cost_run = sum(l * F["load"] for l, (F, *_ ) in zip(run_losses, fs))
                cost_hold = hold * L["load"]
                recs.append(dict(
                    kind="hold" if cost_hold < cost_run else "run",
                    leader=L["no"], leader_name=L["name"], leader_cls=L["cls"], leader_load=L["load"],
                    leader_delay=round(L["delay"]), leader_speed=round(L["speed"]),
                    followers=[dict(no=F["no"], name=F["name"], cls=F["cls"], load=F["load"], delay=round(F["delay"]),
                                    loss=round(lo), speed=round(F["speed"]), gap_km=round(abs(L["x"] - F["x"]), 1))
                               for lo, (F, *_ ) in zip(run_losses, fs)],
                    at=stations[a]["code"], at_name=stations[a]["name"], nxt=stations[b]["code"],
                    nxt_name=stations[b]["name"], when=la, hold_min=round(hold),
                    train_min_run=round(sum(run_losses)), cost_run=round(cost_run), cost_hold=round(cost_hold),
                    saving=round(abs(cost_run - cost_hold)),
                    prio_rule="hold" if max(F["priority"] for F, *_ in fs) > L["priority"] else "run"))
                break
    recs = [r for r in recs if r["saving"] >= MIN_SAVING]
    recs.sort(key=lambda r: -r["saving"])
    return recs[:4]
