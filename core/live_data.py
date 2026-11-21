import json
import math
import re
import tempfile
import urllib.parse
import urllib.request

import pandas as pd

UA = {"User-Agent": "OptiProtein-pitch/1.0 (contact: fleektyre@gmail.com)"}  # put your real email
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Approximate centres of each corridor (keyed by LGA, lowercase). Adjust if you want tighter areas.
CORRIDOR_COORDS = {
    "surulere": (6.5010, 3.3570),
    "ikeja": (6.6018, 3.3515),
    "alimosho": (6.5896, 3.2856),
    "yaba": (6.5095, 3.3711),
    "ibadan": (7.4300, 3.9120),
    "wuse": (9.0667, 7.4700),
    "ota": (6.6867, 3.2300),
}


def _http(url, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------- OpenStreetMap: real outlet counts ----------
def osm_outlets(lat, lon, radius_m=2000):
    """Count restaurants / fast food / canteens around a point. Returns (count, per_km2)."""
    q = (
        "[out:json][timeout:90];"
        f'nwr["amenity"~"^(restaurant|fast_food|canteen|food_court)$"](around:{radius_m},{lat},{lon});'
        "out count;"
    )
    body = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for url in OVERPASS_URLS:
        try:
            raw = _http(url, data=body, timeout=120)
            data = json.loads(raw)
            if "remark" in data and "error" in data["remark"].lower():
                raise RuntimeError(data["remark"])
            total = int(data["elements"][0]["tags"]["total"])
            area_km2 = math.pi * (radius_m / 1000.0) ** 2
            return total, round(total / area_km2, 1)
        except Exception as exc:  # try next mirror
            last = exc
    raise RuntimeError(f"Overpass failed: {last}")

# ---------- NBS: beef price (zone or state level) ----------
ZONES = {
    "north central": ["benue", "kogi", "kwara", "nasarawa", "niger", "plateau", "fct"],
    "north east": ["adamawa", "bauchi", "borno", "gombe", "taraba", "yobe"],
    "north west": ["jigawa", "kaduna", "kano", "katsina", "kebbi", "sokoto", "zamfara"],
    "south east": ["abia", "anambra", "ebonyi", "enugu", "imo"],
    "south south": ["akwa ibom", "bayelsa", "cross river", "delta", "edo", "rivers"],
    "south west": ["ekiti", "lagos", "ogun", "ondo", "osun", "oyo"],
}
STATE_TO_ZONE = {s: z for z, states in ZONES.items() for s in states}


def norm_state(s):
    s = re.sub(r"[^a-z ]", "", str(s).lower()).strip()
    return {"abuja": "fct", "federal capital territory": "fct", "fct abuja": "fct"}.get(s, s)


def download(url):
    suffix = ".csv" if url.lower().split("?")[0].endswith(".csv") else (
        ".xls" if url.lower().split("?")[0].endswith(".xls") else ".xlsx")
    path = tempfile.NamedTemporaryFile(delete=False, suffix=suffix).name
    with open(path, "wb") as f:
        f.write(_http(url, timeout=120))
    return path


def _read_all(path):
    if path.lower().endswith(".csv"):
        return {"csv": pd.read_csv(path, header=None)}
    return pd.read_excel(path, sheet_name=None, header=None)


def parse_nbs_beef(path):
    """Reads an NBS Selected Food Price Watch file (item x zone layout, or item x state).
    Returns {"zones": {zone: price}, "states": {state: price}, "national": price or None}."""
    out = {"zones": {}, "states": {}, "national": None}
    for df in _read_all(path).values():
        beef_rows = [(0 if "boneless" in str(df.iat[r, 0]).lower() else 1, r)
                     for r in range(len(df)) if "beef" in str(df.iat[r, 0]).lower()]
        if not beef_rows:
            continue
        brow = sorted(beef_rows)[0][1]
        for hr in range(brow):
            for j in range(1, df.shape[1]):
                h = str(df.iat[hr, j]).strip().lower()
                price = pd.to_numeric(df.iat[brow, j], errors="coerce")
                if pd.isna(price):
                    continue
                if h in ZONES:
                    out["zones"][h] = float(price)
                elif h in STATE_TO_ZONE:
                    out["states"][norm_state(h)] = float(price)
            cols = [j for j in range(1, df.shape[1]) if str(df.iat[hr, j]).lower().startswith("average of")]
            if cols:
                p = pd.to_numeric(df.iat[brow, cols[-1]], errors="coerce")
                if pd.notna(p):
                    out["national"] = float(p)
    return out


def beef_price_for_state(parsed, state):
    """Best available price: state, then zone. Returns (price, level) or (None, None)."""
    st = norm_state(state)
    if st in parsed["states"]:
        return parsed["states"][st], "state"
    zone = STATE_TO_ZONE.get(st)
    if zone in parsed["zones"]:
        return parsed["zones"][zone], "zone"
    return None, None