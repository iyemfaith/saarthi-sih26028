"""Stage 6 - EXPORT for the web: replayed days as compact JSON bundles.

data/processed/replay/<date>.pkl  ->  data/processed/web/<date>.json  (+ days.json manifest)

The JSON bundles are what both the local server and the in-browser (Pyodide) demo
read, so the repo ships plain data instead of pickles.

Run:  py -m saarthi.export
"""
import json
import pickle

from .config import PROC, TEST_DAYS

OUT = PROC / "web"


def compact(o):
    if isinstance(o, dict):
        return {str(k): compact(v) for k, v in o.items() if k != "path"}   # 'path' only feeds the hold planner
    if isinstance(o, (list, tuple)):
        return [compact(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        o = o.item()
    if isinstance(o, float):
        return round(o, 1)
    return o


def main():
    OUT.mkdir(exist_ok=True)
    manifest = {}
    for d in TEST_DAYS:
        p = PROC / "replay" / f"{d}.pkl"
        if not p.exists():
            continue
        res = compact(pickle.load(open(p, "rb")))
        res.pop("vol", None)                                   # evaluation-only, summarised in evidence.json
        path = OUT / f"{d}.json"
        json.dump(res, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        from .service import Day
        D = Day(json.load(open(path, encoding="utf-8")))
        manifest[d] = dict(day0=D.day0, n_trips=len(D.trips), suggest=D.suggest)
        print(f"  {d}: {path.stat().st_size / 1e6:.1f} MB")
    json.dump(manifest, open(OUT / "days.json", "w"), indent=1)
    print(f"wrote {len(manifest)} day bundles + days.json to {OUT}")


if __name__ == "__main__":
    main()
