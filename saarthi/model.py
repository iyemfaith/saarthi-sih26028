"""Stage 3 - PUBLISH THE HONEST RANGE.

Quantile LightGBM on the delay change still to come, then split-conformal
calibration (CQR, per horizon bucket) so an "80% window" really contains the
actual arrival ~80% of the time on days the model never saw.

Ablation ladder:
  B0  carry-forward       today's practice: ETA = schedule + current delay
  B1  timetable-credited  assumes every minute of timetable recovery time is delivered
  B2  carry-forward + historical spread (a calibrated but naive range)
  M1  own-train GBM
  M2  + network (train ahead, occupancy, live path anomaly, weather, reliability)
  M3  + topology (H0 persistence of the space-time delay-anomaly field)
Each layer ships only if it beats the layer below on the VALIDATION days
(19-21 Sep). TEST days (25-30 Sep) are only reported, never used to choose.

Run:  py -m saarthi.model
"""
import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from .config import PROC
from .features import CATEGORICAL, NETWORK, OWN, TOPO

MODELS = PROC / "models"
MODELS.mkdir(exist_ok=True)
ALPHAS = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
BUCKETS = [0, 60, 180, 360, 1e9]
BUCKET_NAMES = ["< 1 h", "1-3 h", "3-6 h", "> 6 h"]
PARAMS = dict(objective="quantile", learning_rate=0.05, num_leaves=63, min_data_in_leaf=60,
              feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, verbose=-1,
              num_threads=0)
SHIP_GAIN, SHIP_DAYS = 0.01, 2        # >=1% pinball gain and better on >=2 of 3 validation days


def bucket(h):
    return np.clip(np.searchsorted(BUCKETS, h, side="right") - 1, 0, len(BUCKET_NAMES) - 1)


def fit_quantiles(tr, feats, alphas, rounds=450):
    X, y = tr[feats], tr.y - tr.base
    cat = [c for c in CATEGORICAL if c in feats]
    return {a: lgb.train({**PARAMS, "alpha": a}, lgb.Dataset(X, y, categorical_feature=cat, free_raw_data=False),
                         num_boost_round=rounds) for a in alphas}


def predict(models, df, feats):
    """Absolute delay quantiles (minutes), monotone across alpha, floored at 0."""
    P = np.column_stack([df.base.to_numpy() + models[a].predict(df[feats]) for a in sorted(models)])
    return np.maximum(np.sort(P, axis=1), 0.0)


def conformal(lo, hi, y, b, level):
    """CQR offset per horizon bucket: widen [lo, hi] until `level` coverage on calib."""
    off = {}
    for k in range(len(BUCKET_NAMES)):
        m = b == k
        n = int(m.sum())
        if n < 30:
            off[k] = 0.0
            continue
        s = np.maximum(lo[m] - y[m], y[m] - hi[m])
        off[k] = float(np.quantile(s, min(1.0, np.ceil((n + 1) * level) / n)))
    return off


def pinball(y, P, alphas):
    return float(np.mean([np.mean(np.maximum(a * (y - P[:, i]), (a - 1) * (y - P[:, i]))) for i, a in enumerate(alphas)]))


def cover(y, lo, hi):
    return dict(coverage=float(np.mean((y >= lo) & (y <= hi))), width=float(np.mean(hi - lo)))


def main():
    df = pd.read_pickle(PROC / "rows.pkl")
    df = df[df.y.notna()].reset_index(drop=True)
    tr, va, ca, te = (df[df.split == s].reset_index(drop=True) for s in ("train", "valid", "calib", "test"))
    print(f"rows  train {len(tr):,}  valid {len(va):,}  calib {len(ca):,}  test {len(te):,}")
    yte, yva, yca = te.y.to_numpy(), va.y.to_numpy(), ca.y.to_numpy()
    bte, bca = bucket(te.h_sch.to_numpy()), bucket(ca.h_sch.to_numpy())
    report = {"rows": {"train": len(tr), "valid": len(va), "calib": len(ca), "test": len(te)},
              "trips_test": int(te.tid.nunique()), "trains_test": int(te.train.nunique()), "ladder": []}

    # ---- baselines (test) ----
    b0 = te.base.to_numpy()
    b1 = np.maximum(0, te.base - te.tt_slack.fillna(0).clip(lower=0)).to_numpy()
    res_tr, btr = (tr.y - tr.base).to_numpy(), bucket(tr.h_sch.to_numpy())
    q = {k: np.quantile(res_tr[btr == k], [0.1, 0.5, 0.9]) for k in range(len(BUCKET_NAMES))}
    b2 = np.maximum(np.array([q[k] for k in bte]) + b0[:, None], 0)
    for key, name, pred, lohi in [("B0", "Carry-forward (today's ETA)", b0, None),
                                  ("B1", "Timetable recovery fully credited", b1, None),
                                  ("B2", "Carry-forward + historical spread", b2[:, 1], (b2[:, 0], b2[:, 2]))]:
        e = dict(key=key, name=name, mae=float(np.mean(np.abs(yte - pred))), bias=float(np.mean(yte - pred)),
                 p90_abs=float(np.quantile(np.abs(yte - pred), 0.9)))
        if lohi:
            c = cover(yte, *lohi)
            e.update(cov80=c["coverage"], width80=c["width"])
        report["ladder"].append(e)
        print(f"{key}: MAE {e['mae']:.2f}  bias {e['bias']:+.2f}")

    # ---- model ladder: decide on VALID, report on TEST ----
    sets = {"M1": OWN, "M2": OWN + NETWORK, "M3": OWN + NETWORK + TOPO}
    names = {"M1": "Own-train model", "M2": "+ network (train ahead, blocks, weather)",
             "M3": "+ topology (persistent hotspots)"}
    ab = [0.1, 0.5, 0.9]
    val, preds, per_day_te = {}, {}, {}
    for key, feats in sets.items():
        mdl = fit_quantiles(tr, feats, ab)
        Pva, Pca, Pte = predict(mdl, va, feats), predict(mdl, ca, feats), predict(mdl, te, feats)
        off = conformal(Pca[:, 0], Pca[:, 2], yca, bca, 0.8)
        o = np.array([off[k] for k in bte])
        raw, cal = cover(yte, Pte[:, 0], Pte[:, 2]), cover(yte, np.maximum(Pte[:, 0] - o, 0), Pte[:, 2] + o)
        val[key] = dict(pinball=pinball(yva, Pva, ab),
                        per_day=va.assign(e=np.abs(yva - Pva[:, 1])).groupby("date").e.mean().to_dict())
        e = dict(key=key, name=names[key], mae=float(np.mean(np.abs(yte - Pte[:, 1]))),
                 bias=float(np.mean(yte - Pte[:, 1])), p90_abs=float(np.quantile(np.abs(yte - Pte[:, 1]), 0.9)),
                 pinball=pinball(yte, Pte, ab), cov80_raw=raw["coverage"], cov80=cal["coverage"],
                 width80=cal["width"], val_pinball=val[key]["pinball"])
        report["ladder"].append(e)
        preds[key] = Pte[:, 1]
        per_day_te[key] = te.assign(e=np.abs(yte - Pte[:, 1])).groupby("date").e.mean().to_dict()
        print(f"{key}: test MAE {e['mae']:.2f}  pinball {e['pinball']:.3f} (valid {val[key]['pinball']:.3f})  "
              f"cov80 raw {raw['coverage']:.3f} -> cal {cal['coverage']:.3f}  width {cal['width']:.1f}")

    def verdict(lower, upper):
        g = (val[lower]["pinball"] - val[upper]["pinball"]) / val[lower]["pinball"]
        days = sum(val[upper]["per_day"][d] < val[lower]["per_day"][d] for d in val[lower]["per_day"])
        return dict(layer=upper, over=lower, val_pinball_gain_pct=100 * g, val_days_better=int(days),
                    val_days=len(val[lower]["per_day"]), ships=bool(g >= SHIP_GAIN and days >= SHIP_DAYS),
                    test_per_day={d: {lower: per_day_te[lower][d], upper: per_day_te[upper][d]} for d in per_day_te[lower]})
    v_net = verdict("M1", "M2")
    final = "M2" if v_net["ships"] else "M1"
    v_topo = verdict(final, "M3")
    if v_topo["ships"]:
        final = "M3"
    report["verdicts"] = [v_net, v_topo]
    for v in report["verdicts"]:
        print(f"{v['layer']} over {v['over']}: valid pinball gain {v['val_pinball_gain_pct']:+.2f}%, better on "
              f"{v['val_days_better']}/{v['val_days']} days -> {'SHIPS' if v['ships'] else 'does not ship'}")
    print(f"production = {final}")
    feats = sets[final]

    # ---- production model: full quantile set (fit on train+valid), conformal on calib ----
    mdl = fit_quantiles(pd.concat([tr, va], ignore_index=True), feats, ALPHAS)
    Pca, Pte = predict(mdl, ca, feats), predict(mdl, te, feats)
    levels = {"50": (0.25, 0.75), "80": (0.1, 0.9), "90": (0.05, 0.95)}
    conf, calib = {}, []
    for lv, (a, b) in levels.items():
        ia, ib = ALPHAS.index(a), ALPHAS.index(b)
        off = conformal(Pca[:, ia], Pca[:, ib], yca, bca, int(lv) / 100)
        conf[lv] = off
        o = np.array([off[k] for k in bte])
        lo, hi = np.maximum(Pte[:, ia] - o, 0), Pte[:, ib] + o
        raw, cal = cover(yte, Pte[:, ia], Pte[:, ib]), cover(yte, lo, hi)
        by_b = [dict(bucket=nm, n=int((bte == k).sum()), **cover(yte[bte == k], lo[bte == k], hi[bte == k]),
                     mae=float(np.mean(np.abs(yte[bte == k] - Pte[bte == k, 3]))),
                     mae_b0=float(np.mean(np.abs(yte[bte == k] - b0[bte == k]))))
                for k, nm in enumerate(BUCKET_NAMES) if (bte == k).sum()]
        calib.append(dict(level=int(lv), raw=raw["coverage"], calibrated=cal["coverage"], width=cal["width"],
                          by_horizon=by_b))
        print(f"  {lv}% window: raw {raw['coverage']:.3f} -> calibrated {cal['coverage']:.3f}, width {cal['width']:.1f} min")
    report["calibration"] = calib
    report["production"] = final
    report["production_mae"] = float(np.mean(np.abs(yte - Pte[:, 3])))
    report["features"] = feats

    # ---- how early does each model see a delay coming? ----
    from .network import Corridor
    C = Corridor()
    sch_j = np.array([C.trips[i].sch_arr[j] for i, j in zip(te.tid, te.j)])
    to_go = sch_j + yte - te.t.to_numpy()           # minutes from forecast to the actual arrival
    change = yte - b0
    rows = []
    for lo_, hi_ in zip([0, 15, 30, 45, 60, 90, 120, 180], [15, 30, 45, 60, 90, 120, 180, 300]):
        m = (to_go >= lo_) & (to_go < hi_)
        if m.sum() < 50:
            continue
        r = dict(lo=lo_, hi=hi_, n=int(m.sum()), mae_b0=float(np.mean(np.abs(change[m]))),
                 **{f"mae_{k.lower()}": float(np.mean(np.abs(yte[m] - preds[k][m]))) for k in preds},
                 mae_prod=float(np.mean(np.abs(yte[m] - Pte[m, 3]))))
        big = m & (change >= 15)
        r["n_big"] = int(big.sum())
        if big.sum() >= 20:
            for k in preds:
                r[f"capture_{k.lower()}"] = float(np.median((preds[k][big] - b0[big]) / change[big]))
        rows.append(r)
    report["lead"] = rows

    imp = mdl[0.5].feature_importance("gain")
    report["importance"] = sorted([dict(feature=f, gain=float(g)) for f, g in zip(feats, imp)], key=lambda d: -d["gain"])
    for a, m in mdl.items():
        m.save_model(str(MODELS / f"q{int(round(a * 100)):02d}.txt"))
    json.dump(dict(alphas=ALPHAS, features=feats, categorical=CATEGORICAL, buckets=BUCKETS, bucket_names=BUCKET_NAMES,
                   conformal={lv: {str(k): v for k, v in o.items()} for lv, o in conf.items()}),
              open(MODELS / "meta.json", "w"), indent=1)
    json.dump(report, open(PROC / "report.json", "w"), indent=1, default=float)
    print("saved models + report.json")


if __name__ == "__main__":
    main()
