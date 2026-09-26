"""Stage 1 - PERCEIVE.

Turns the RSTGCN Indian Railway Network dataset (Sept 2024 running records) into
absolute-timestamped station reports for every train that runs on the
Delhi-Kanpur-Prayagraj trunk, plus corridor geometry and train metadata.

Run:  py -m saarthi.prepare
"""
import json
import re

import numpy as np
import pandas as pd

from .config import CODES, CORRIDOR, GEO_ALIAS, GEO_FALLBACK, IDX, PROC, RAW, STATIONS_GEO


def _mins(t: pd.Series) -> np.ndarray:
    """'09:55 PM' -> minutes after midnight."""
    s = t.str.extract(r"^(\d\d):(\d\d) ([AP])M$")
    h = s[0].astype(int) % 12 + np.where(s[2] == "P", 12, 0)
    return (h * 60 + s[1].astype(int)).to_numpy()


def schedule_offsets(routes: pd.DataFrame) -> pd.DataFrame:
    """Minutes from journey-date midnight for each scheduled arrival/departure,
    rolling over midnight whenever the clock goes backwards along the route."""
    routes = routes.sort_values(["trainNumber", "stnSerialNumber"]).copy()
    arr, dep = _mins(routes.arrivalTime), _mins(routes.departureTime)
    train = routes.trainNumber.to_numpy()
    arr_off = np.empty(len(routes), dtype=np.int64)
    dep_off = np.empty(len(routes), dtype=np.int64)
    day, last, prev = 0, -1, None
    for i in range(len(routes)):
        if train[i] != prev:
            day, last, prev = 0, -1, train[i]
        a = arr[i] + day * 1440
        if a < last:
            day += 1
            a += 1440
        d = dep[i] + day * 1440
        if d < a:
            day += 1
            d += 1440
        arr_off[i], dep_off[i], last = a, d, d
    routes["arr_off"], routes["dep_off"] = arr_off, dep_off
    return routes


def train_class(num: int, name: str) -> str:
    n = name.lower()
    for key, cls in [("vande", "Vande Bharat"), ("rajdhani", "Rajdhani"), ("jan shatabdi", "Jan Shatabdi"),
                     ("shatabdi", "Shatabdi"), ("duronto", "Duronto"), ("tejas", "Tejas"),
                     ("humsafar", "Humsafar"), ("garib", "Garib Rath"), ("amrit bharat", "Amrit Bharat"),
                     ("antyodaya", "Antyodaya"), ("sampark", "Sampark Kranti")]:
        if key in n:
            return cls
    s = f"{num:05d}"
    if s[0] == "0":
        return "Special"
    if s[0] in "56":
        return "Passenger/MEMU"
    if s[:2] in ("12", "22", "20"):
        return "Superfast"
    return "Mail/Express"


# Control-office precedence (higher runs first) and an assumed passenger load per
# rake. Loads are planning assumptions, not measured - general-class coaches make
# ordinary Mail/Express trains the most crowded on this corridor.
PRIORITY = {"Rajdhani": 6, "Vande Bharat": 6, "Shatabdi": 6, "Duronto": 5, "Tejas": 5,
            "Humsafar": 4, "Jan Shatabdi": 4, "Sampark Kranti": 4, "Garib Rath": 4, "Superfast": 4,
            "Amrit Bharat": 3, "Antyodaya": 3, "Mail/Express": 3, "Special": 2, "Passenger/MEMU": 1}
LOAD = {"Rajdhani": 1100, "Vande Bharat": 1130, "Shatabdi": 1000, "Duronto": 1150, "Tejas": 1000,
        "Humsafar": 1300, "Jan Shatabdi": 1500, "Sampark Kranti": 1800, "Garib Rath": 1600,
        "Superfast": 1800, "Amrit Bharat": 2000, "Antyodaya": 2200, "Mail/Express": 1900,
        "Special": 1600, "Passenger/MEMU": 1500}


def corridor_km(routes: pd.DataFrame) -> dict:
    """Least-squares station chainage from every train's route distances, anchored
    at New Delhi = 0. Each train contributes (km_j - km_i = observed distance)."""
    rows, rhs = [], []
    for _, g in routes[routes.station_code.isin(CODES)].groupby("trainNumber"):
        g = g.sort_values("stnSerialNumber")
        c, d = g.station_code.tolist(), g.distance.astype(float).tolist()
        for k in range(len(c) - 1):
            i, j = IDX[c[k]], IDX[c[k + 1]]
            if i == j:
                continue
            row = np.zeros(len(CODES))
            row[i], row[j] = -1, 1
            rows.append(row)
            rhs.append((d[k + 1] - d[k]) * np.sign(j - i))
    A, b = np.array(rows), np.array(rhs)
    A = np.vstack([A, np.eye(len(CODES))[0] * 100])
    b = np.append(b, 0)
    km = np.linalg.lstsq(A, b, rcond=None)[0]
    return {c: round(float(k), 1) for c, k in zip(CODES, km)}


def phantom_zeros(df: pd.DataFrame) -> np.ndarray:
    """Missing station records arrive in the source as 'actual = scheduled, delay 0'
    (e.g. 509 min late at Kanpur, then '0 min late' at New Delhi). Flag a zero as a
    placeholder when the recovery it implies is physically impossible: more than
    30% of the scheduled running time since the last trusted report, plus 10 min."""
    tr, dt, d = df.train.to_numpy(), df.date.to_numpy(), df.delay.to_numpy()
    sa, sd = df.sch_arr.to_numpy(), df.sch_dep.to_numpy()
    flag = np.zeros(len(df), bool)
    pv = 0
    for i in range(len(df)):
        if i == 0 or tr[i] != tr[i - 1] or dt[i] != dt[i - 1]:
            pv = i
            continue
        if d[i] == 0 and d[pv] >= 20:
            run = (sa[i] - sd[pv]) / np.timedelta64(1, "m")
            if d[pv] > 0.3 * max(run, 0) + 10:
                flag[i] = True
                continue
        pv = i
    return flag


def main():
    routes = pd.read_csv(RAW / "train_routes_Sep2024.csv", dtype={"trainNumber": int})
    routes = routes.drop_duplicates(["trainNumber", "station_code"], keep="first")
    routes = schedule_offsets(routes)

    # Trains with at least two halts on the corridor, visited monotonically.
    meta = []
    corr = routes[routes.station_code.isin(CODES)]
    for t, g in corr.groupby("trainNumber"):
        g = g.sort_values("stnSerialNumber")
        idx = [IDX[c] for c in g.station_code]
        if len(idx) < 2:
            continue
        if not (all(a < b for a, b in zip(idx, idx[1:])) or all(a > b for a, b in zip(idx, idx[1:]))):
            continue
        full = routes[routes.trainNumber == t].sort_values("stnSerialNumber")
        name = str(full.trainName.iloc[0]).strip()
        cls = train_class(t, name)
        meta.append(dict(train=int(t), name=name, cls=cls, priority=PRIORITY[cls], load=LOAD[cls],
                         dir="DN" if idx[1] > idx[0] else "UP",
                         origin=full.station_code.iloc[0], origin_name=full.station_name.iloc[0],
                         dest=full.station_code.iloc[-1], dest_name=full.station_name.iloc[-1],
                         corr_first=g.station_code.iloc[0], corr_last=g.station_code.iloc[-1],
                         n_corr_halts=len(idx)))
    meta = pd.DataFrame(meta)
    keep = set(meta.train)
    print(f"corridor trains: {len(meta)}  (DN {sum(meta.dir == 'DN')}, UP {sum(meta.dir == 'UP')})")

    df = pd.read_csv(RAW / "train_routes_delays_Sep2024.csv")
    df = df[df.train.isin(keep)]
    df = df.merge(routes[["trainNumber", "station_code", "stnSerialNumber", "distance", "arr_off", "dep_off",
                          "station_name"]],
                  left_on=["train", "station"], right_on=["trainNumber", "station_code"], how="inner")
    base = pd.to_datetime(df.date)
    df["sch_arr"] = base + pd.to_timedelta(df.arr_off, unit="min")
    df["sch_dep"] = base + pd.to_timedelta(df.dep_off, unit="min")
    df["delay"] = df.arr_delay.astype(float)
    df["act_arr"] = df.sch_arr + pd.to_timedelta(df.delay, unit="min")
    df["act_dep"] = df.sch_dep + pd.to_timedelta(df.delay, unit="min")
    df["cidx"] = df.station.map(IDX).fillna(-1).astype(int)
    df = df.rename(columns={"stnSerialNumber": "seq", "distance": "route_km"})
    df = df[["train", "date", "seq", "station", "station_name", "cidx", "route_km", "sch_arr", "sch_dep",
             "act_arr", "act_dep", "delay"]].sort_values(["train", "date", "seq"]).reset_index(drop=True)
    n_raw, trips_raw = len(df), df.groupby(["train", "date"]).ngroups
    ph = phantom_zeros(df)
    quality = dict(reports_raw=n_raw, phantom=int(ph.sum()), phantom_pct=float(100 * ph.mean()),
                   trips=trips_raw, trips_with_phantom=int(df[ph].groupby(["train", "date"]).ngroups),
                   corridor_phantom=int((ph & (df.cidx >= 0)).sum()))
    df = df[~ph].reset_index(drop=True)
    print(f"reports: {len(df):,}  trips: {df.groupby(['train', 'date']).ngroups:,}  "
          f"(removed {quality['phantom']:,} zero-filled placeholders = {quality['phantom_pct']:.2f}%)")
    json.dump(quality, open(PROC / "quality.json", "w"), indent=1)

    km = corridor_km(routes)
    geo = json.load(open(STATIONS_GEO, encoding="utf-8"))["features"]
    coords = {f["properties"]["code"]: f["geometry"]["coordinates"] for f in geo if f.get("geometry")}
    coords.update({k: list(v) for k, v in GEO_FALLBACK.items()})
    zones = json.load(open(RAW / "stations_zones_mapping.json"))
    stations = []
    for code, name, hi in CORRIDOR:
        lon, lat = coords[GEO_ALIAS.get(code, code)]
        n_tr = int(df[df.station == code].train.nunique())
        stations.append(dict(code=code, name=name, hi=hi, km=km[code], lat=lat, lon=lon,
                             zone=zones.get(code, ""), n_trains=n_tr))
    for s in stations:
        print(f"  {s['code']:5s} {s['km']:7.1f} km  {s['n_trains']:3d} trains  {s['zone']}")

    # Days each train actually ran (has records) in the month.
    ran = df.groupby("train").date.nunique().rename("days_ran")
    meta = meta.merge(ran, on="train", how="left").fillna({"days_ran": 0})

    df.to_pickle(PROC / "reports.pkl")
    meta.to_csv(PROC / "trains.csv", index=False)
    routes[routes.trainNumber.isin(keep)].to_pickle(PROC / "routes.pkl")
    json.dump(stations, open(PROC / "corridor.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    edges = pd.read_csv(RAW / "IRN_edges.csv")
    edges.to_csv(PROC / "irn_edges.csv", index=False)


if __name__ == "__main__":
    main()
