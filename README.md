# SAARTHI prototype · सारथी

**Not a time. A decision.** Working prototype for SIH 2026 · PS SIH26028 *Dynamic Forecast of ETA for Coaching Trains* (Team Hoppers).

### ▶ Live demo: **https://iyemfaith.github.io/saarthi-sih26028/**

Passenger phone app on its own: https://iyemfaith.github.io/saarthi-sih26028/web/p.html · works best on a laptop for the dashboard. The first visit downloads ~15 MB (a Python runtime plus one replay day, ~3 MB compressed) and takes 10–20 s; after that it runs entirely in your browser: the same Python code as the server, via [Pyodide](https://pyodide.org). No server, no sign-in.

It replays **real Indian Railways running records** for a held-out week on the **Delhi → Kanpur → Prayagraj trunk** (19 stations, 635 km, 323 trains) exactly as a live system would have seen them. Every 5 minutes it publishes a calibrated, damped arrival window, turns it into decisions, and delivers them to five surfaces.

## Run it

Needs Python 3.11+.

```
git clone <this repo> && cd saarthi
pip install -r requirements.txt
python -m uvicorn saarthi.api:app --port 8026
```

Then open http://127.0.0.1:8026. On Windows you can double-click `start.bat` instead. The passenger phone app on its own is at http://127.0.0.1:8026/p.

The replayed days ship with the repo (as JSON in `data/processed/web/`), so the dashboard runs straight after cloning. The live demo is this same repo served by GitHub Pages: with no server present, `web/js/backend.js` runs `saarthi/service.py` in the browser instead. To rebuild everything from the raw data (downloads ~25 MB, then about 35 min): `bash run_pipeline.sh`.

## The five surfaces (one forecast, no one's view diluted for anyone else)

| Tab | Who | What it answers |
|---|---|---|
| Control room | Section controller | Where is everything? Which precedence conflicts are coming? Hold or let run, in passenger-minutes, with the reason |
| Station | Station master, platform staff | What arrives in the next 6 h, which platforms will clash, which announcements are stable enough to make now |
| Passenger | Anyone, incl. rural users | *Leave now or wait?* The real phone app (voice, Hindi, big type), the SMS on a feature phone, the 139 IVR call |
| Station board | Everyone on the platform | Realistic LED board alternating Hindi/English; today's board vs SAARTHI; the missed-call poster for halts with no board |
| Proof | Judges, CRIS | Every claim in the deck, tested on a week the model never saw, including what did **not** work |

## Data (what's real)

* **Running records**: RSTGCN *Indian Railway Network and Delays* dataset, Sept 2024 (Chowdhury, Koley, Chakraborty, Ghosh; IIT Kharagpur / IIIT Bhubaneswar; IEEE T-ITS). https://github.com/KoyenaChowdhury/RSTGCN. It's the paper cited on slide 6 of the deck.
* **Weather**: hourly rain per station, Open-Meteo ERA5 reanalysis (stand-in for the IMD feed).
* **Station coordinates**: datameet/railways. Chainage is solved from route distances (Kanpur 441 km vs the real 440).
* **Cleaned**: 4,327 records (4.2%) were zero-filled placeholders, i.e. a missing report stored as "actual = scheduled, 0 min late". They were removed as missing.
* **Inferred**: positions between halts, train ahead, block occupancy, rake pairs (odd/even convention).
* **Assumed**: platform numbers, passenger loads per class, 6-min headway, DLT IDs and the missed-call number. No SMS or call is ever sent.

Split by date: fit 1–18 Sep · model selection 19–21 · conformal calibration 22–24 · **test/replay 25–30** (never used to choose anything).

## Results (held-out 25–30 Sep)

* Error vs today's carry-forward ETA: **MAE 17.2 → 12.6 min (−27%)**.
* Timetable optimism: crediting all timetable recovery leaves forecasts **15 min too early** on average. For trains 15+ min late, the timetable allows 17–23 min of recovery into Kanpur, Aligarh and New Delhi; the route actually gives back 3–10.
* Calibration: "8 in 10" windows contain **80.7%** of real arrivals (raw quantiles 70.7%); 90% windows 91.4%.
* Stability over 3,731 real arrivals: in the final 3 hours today's ETA changed **3.1 times** per arrival (28% got 3+ slips later); SAARTHI's window changed **0.75 times** (8%). The promise held **80%** of the time an hour out.
* A boarding passenger deciding 90 min out (3,268 arrivals):

  | strategy | missed the train | median wait | 90th-pct wait |
  |---|---|---|---|
  | printed timetable | 0% | 25 min | 105 min |
  | today's ETA | **14.9%** | 14 min | 38 min |
  | SAARTHI leave-by | **2.4%** | **11 min** | 35 min |

* **Held back, as the deck promised**: the network layer (+0.4% on validation) and the topology layer (+0.8%) didn't clear the 1% bar. Public data only logs halts, so "the train ahead" is inferred, not seen. The deck's 30-second position, block and signal feeds are exactly the missing inputs. The one place it clearly helps is heavy rain on the path (−3.4% error on 2.5% of forecasts).
* **Found**: rake links matter. When a late incoming rake eats the turnaround (76 of 1,026 turnarounds), the return working runs a median **279 min** late two stops later, vs 12 min otherwise (r = 0.65).
* **Found**: 4.2% of source records are zero-filled placeholders; Tundla's logged times imply impossible runs 10.5% of the time.

## Pipeline

```
saarthi/prepare.py   PERCEIVE  raw dataset -> timestamped corridor reports, placeholder cleaning
saarthi/network.py   MODEL     dead-reckoning, train ahead, occupancy, live anomaly, H0 persistence
saarthi/features.py            one row per (train, clock time, downstream halt), leak-free sweep
saarthi/model.py     PUBLISH   quantile LightGBM + per-horizon conformal (CQR) + ablation ladder
saarthi/replay.py              5-minute replay, damped publisher, hold/let-run, today's ETA for contrast
saarthi/decide.py    DECIDE    asymmetric passenger advice; passenger-minute precedence
saarthi/messages.py            SMS (GSM-7/UCS-2, DLT templates), 139 IVR, PA announcements
saarthi/service.py             the API as plain functions; reveals truth only once the clock passes it
saarthi/api.py                 FastAPI wrapper (laptop); in the browser demo Pyodide calls service.py directly
saarthi/export.py              replayed days -> JSON bundles for server and browser
web/                           dashboard + passenger app (no external libraries, works offline)
```
