"""Paths and the corridor definition shared by every stage of the pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "Indian-Railway-Network-and-Delays"
STATIONS_GEO = ROOT / "data" / "raw" / "stations.json"
PROC = ROOT / "data" / "processed"
WEB = ROOT / "web"
PROC.mkdir(parents=True, exist_ok=True)

# Delhi -> Kanpur -> Prayagraj trunk (the busiest section in the dataset: Kanpur
# Central is served by 421 distinct trains in Sept 2024, more than any other station).
# Order is the physical order along the line. Hindi names are the official
# station-board spellings. `geo` maps renamed codes to the older code used in the
# datameet coordinate file (PRYJ was ALD until 2020).
CORRIDOR = [
    ("NDLS", "New Delhi",        "नई दिल्ली"),
    ("GZB",  "Ghaziabad",        "गाज़ियाबाद"),
    ("KRJ",  "Khurja Jn",        "खुर्जा जं."),
    ("ALJN", "Aligarh Jn",       "अलीगढ़ जं."),
    ("HRS",  "Hathras Jn",       "हाथरस जं."),
    ("TDL",  "Tundla Jn",        "टूंडला जं."),
    ("FZD",  "Firozabad",        "फ़िरोज़ाबाद"),
    ("SKB",  "Shikohabad Jn",    "शिकोहाबाद जं."),
    ("ETW",  "Etawah",           "इटावा"),
    ("BNT",  "Bharthana",        "भरथना"),
    ("PHD",  "Phaphund",         "फफूंद"),
    ("JJK",  "Jhinjhak",         "झींझक"),
    ("RURA", "Rura",             "रूरा"),
    ("CNB",  "Kanpur Central",   "कानपुर सेंट्रल"),
    ("FTP",  "Fatehpur",         "फ़तेहपुर"),
    ("KGA",  "Khaga",            "खागा"),
    ("SRO",  "Sirathu",          "सिराथू"),
    ("BRE",  "Bharwari",         "भरवारी"),
    ("PRYJ", "Prayagraj Jn",     "प्रयागराज जं."),
]
GEO_ALIAS = {"PRYJ": "ALD"}
# Fallback coordinates for codes missing from the datameet file.
GEO_FALLBACK = {"ALD": (81.8246, 25.4449)}

CODES = [c for c, _, _ in CORRIDOR]
IDX = {c: i for i, c in enumerate(CODES)}

# Chronological split by service date: no day appears in more than one split.
# Feature/ship decisions are made on VALID days; TEST days are only ever reported.
TRAIN_DAYS = [f"2024-09-{d:02d}" for d in range(1, 19)]   # 1-18 Sep: fit
VALID_DAYS = [f"2024-09-{d:02d}" for d in range(19, 22)]  # 19-21 Sep: model selection
CALIB_DAYS = [f"2024-09-{d:02d}" for d in range(22, 25)]  # 22-24 Sep: conformal calibration
TEST_DAYS = [f"2024-09-{d:02d}" for d in range(25, 31)]   # 25-30 Sep: held-out test + replay
