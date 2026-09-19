"""Place names -> coordinates, distances, and a guess at how the shopper travels.

`geocode` asks the free Open-Meteo Geocoding API (no key) and caches one JSON per name under
data/context/geocode_<slug>.json. It never raises: any failure returns None.

Open-Meteo's search does not match CJK input ("札幌" returns nothing, "Sapporo" returns 札幌市 with
language=zh), so common zh-TW place names are first mapped to an English search term (ALIASES);
unknown names are tried as typed, then with a trailing 市/縣 stripped.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

API_URL = "https://geocoding-api.open-meteo.com/v1/search"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "context"

ALIASES = {
    # Taiwan
    "台北": "Taipei", "臺北": "Taipei", "新北": "New Taipei", "桃園": "Taoyuan", "新竹": "Hsinchu",
    "苗栗": "Miaoli", "台中": "Taichung", "臺中": "Taichung", "彰化": "Changhua", "南投": "Nantou",
    "雲林": "Douliu", "嘉義": "Chiayi", "台南": "Tainan", "臺南": "Tainan", "高雄": "Kaohsiung",
    "屏東": "Pingtung", "墾丁": "Hengchun", "基隆": "Keelung", "宜蘭": "Yilan", "花蓮": "Hualien",
    "台東": "Taitung", "臺東": "Taitung", "澎湖": "Magong", "金門": "Kinmen", "馬祖": "Nangan",
    # Japan / Korea
    "東京": "Tokyo", "大阪": "Osaka", "京都": "Kyoto", "奈良": "Nara", "神戶": "Kobe",
    "札幌": "Sapporo", "北海道": "Sapporo", "函館": "Hakodate", "小樽": "Otaru", "旭川": "Asahikawa",
    "名古屋": "Nagoya", "福岡": "Fukuoka", "沖繩": "Naha", "那霸": "Naha", "仙台": "Sendai",
    "橫濱": "Yokohama", "廣島": "Hiroshima", "金澤": "Kanazawa", "首爾": "Seoul", "釜山": "Busan",
    "濟州": "Jeju City",
    # rest of Asia
    "香港": "Hong Kong", "澳門": "Macau", "上海": "Shanghai", "北京": "Beijing", "廈門": "Xiamen",
    "曼谷": "Bangkok", "清邁": "Chiang Mai", "普吉": "Phuket", "新加坡": "Singapore",
    "吉隆坡": "Kuala Lumpur", "峇里島": "Denpasar", "胡志明市": "Ho Chi Minh City", "河內": "Hanoi",
    "峴港": "Da Nang", "馬尼拉": "Manila", "宿霧": "Cebu City",
    # further away
    "倫敦": "London", "巴黎": "Paris", "羅馬": "Rome", "米蘭": "Milan", "柏林": "Berlin",
    "阿姆斯特丹": "Amsterdam", "巴塞隆納": "Barcelona", "紐約": "New York", "洛杉磯": "Los Angeles",
    "舊金山": "San Francisco", "西雅圖": "Seattle", "溫哥華": "Vancouver", "雪梨": "Sydney",
    "墨爾本": "Melbourne", "奧克蘭": "Auckland",
}

TAIWAN_NAMES = {"tw", "taiwan", "台灣", "臺灣", "台湾"}


def _slug(name: str) -> str:
    s = re.sub(r"[^\w]+", "_", name.strip().lower()).strip("_")
    return s or hashlib.md5(name.encode("utf-8")).hexdigest()[:12]


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"geocode_{_slug(name)}.json"


def _queries(name: str) -> list[str]:
    n = name.strip()
    base = re.sub(r"[市縣县]$", "", n)
    out = []
    for q in (ALIASES.get(n), ALIASES.get(base), n, base):
        if q and q not in out:
            out.append(q)
    return out


def geocode(name: str, timeout: float = 3.0) -> dict | None:
    """{name, lat, lon, country, country_code, timezone} for a place name; cached; None on failure."""
    try:
        if not name or not str(name).strip():
            return None
        name = str(name).strip()
        cache = _cache_path(name)
        if cache.exists():
            try:
                d = json.loads(cache.read_text(encoding="utf-8"))
                if d.get("lat") is not None and d.get("lon") is not None:
                    return d
            except Exception:
                pass                                   # corrupt cache -> refetch
        import requests
        for q in _queries(name):
            r = requests.get(API_URL, params={"name": q, "count": 1, "language": "zh",
                                              "format": "json"}, timeout=timeout)
            r.raise_for_status()
            res = (r.json() or {}).get("results") or []
            if not res:
                continue
            hit = res[0]
            out = {"name": name, "resolved_name": hit.get("name") or q,
                   "lat": float(hit["latitude"]), "lon": float(hit["longitude"]),
                   "country": hit.get("country"), "country_code": hit.get("country_code"),
                   "timezone": hit.get("timezone"), "query": q,
                   "fetched_at": datetime.now().isoformat(timespec="seconds")}
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
            except Exception:
                pass
            return out
        return None
    except Exception:
        return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _norm_country(c) -> str | None:
    if c is None:
        return None
    s = str(c).strip().lower()
    return "tw" if s in TAIWAN_NAMES else (s or None)


def infer_transport(km: float, origin_country: str | None = None,
                    dest_country: str | None = None) -> str:
    """flight (different country or > 400 km) | hsr (80-400 km in Taiwan) | train | car |
    scooter (< 30 km in Taiwan) | mrt (< 30 km elsewhere)."""
    oc, dc = _norm_country(origin_country), _norm_country(dest_country)
    if (oc and dc and oc != dc) or km > 400:
        return "flight"
    in_tw = "tw" in (oc, dc) and (oc in (None, "tw")) and (dc in (None, "tw"))
    if km < 30:
        return "scooter" if in_tw else "mrt"
    if in_tw:
        return "hsr" if km >= 80 else "car"
    return "train"


def flight_hours(km: float) -> float:
    """Rough door-to-door-ish air time: cruise ~750 km/h plus taxi/climb."""
    return km / 750.0 + 0.5
