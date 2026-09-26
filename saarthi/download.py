"""Stage 0 - fetch the third-party inputs (not redistributed in this repo).

  * RSTGCN "Indian Railway Network and Delays" dataset (Chowdhury et al., IEEE T-ITS)
  * datameet/railways station coordinates
  * Open-Meteo ERA5 hourly weather for the 19 corridor stations, Sept 2024

Run:  py -m saarthi.download
"""
import io
import json
import zipfile

import requests

from .config import CODES, GEO_ALIAS, GEO_FALLBACK, RAW, ROOT, STATIONS_GEO

RSTGCN_ZIP = "https://github.com/KoyenaChowdhury/RSTGCN/raw/HEAD/Indian-Railway-Network-and-Delays.zip"
DATAMEET = "https://raw.githubusercontent.com/datameet/railways/master/stations.json"
METEO = "https://archive-api.open-meteo.com/v1/archive"


def main():
    raw = ROOT / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    if not RAW.exists():
        print("downloading RSTGCN dataset (~24 MB)...")
        r = requests.get(RSTGCN_ZIP, timeout=300)
        r.raise_for_status()
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(raw)
    if not STATIONS_GEO.exists():
        print("downloading datameet station coordinates...")
        r = requests.get(DATAMEET, timeout=120)
        r.raise_for_status()
        STATIONS_GEO.write_bytes(r.content)
    wpath = raw / "weather_openmeteo_sep2024.json"
    if not wpath.exists():
        print("downloading Open-Meteo hourly weather...")
        feats = json.load(open(STATIONS_GEO, encoding="utf-8"))["features"]
        coords = {f["properties"]["code"]: f["geometry"]["coordinates"] for f in feats if f.get("geometry")}
        coords.update({k: list(v) for k, v in GEO_FALLBACK.items()})
        lonlat = [coords[GEO_ALIAS.get(c, c)] for c in CODES]
        params = dict(latitude=",".join(f"{la:.4f}" for _, la in lonlat), longitude=",".join(f"{lo:.4f}" for lo, _ in lonlat),
                      start_date="2024-08-31", end_date="2024-10-02", timezone="Asia/Kolkata",
                      hourly="precipitation,weather_code,temperature_2m,wind_gusts_10m,visibility")
        r = requests.get(METEO, params=params, timeout=120)
        r.raise_for_status()
        json.dump({c: x for c, x in zip(CODES, r.json())}, open(wpath, "w"))
    print("inputs ready in", raw)


if __name__ == "__main__":
    main()
