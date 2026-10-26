"""Places on a real map: a bundled city list (GeoNames, CC BY 4.0) and road distances.

No live geocoding: `find("münch")` searches `cities.csv` (6,600 cities; how it was made:
`make_cities.py`). Road km = great-circle km x a road factor (about 1.25 in Germany).
"""

import csv
import math
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROAD_FACTOR = 1.25
ATTRIBUTION = "City list: GeoNames (geonames.org), CC BY 4.0"


@dataclass(frozen=True)
class City:
    name: str
    country: str
    lat: float
    lon: float
    population: int
    alt: tuple = ()

    @property
    def label(self):
        """Munich, DE (1.5 M): unique enough for a select box."""
        pop = self.population
        size = f"{pop / 1e6:.1f} M" if pop >= 1e6 else f"{pop / 1e3:,.0f}k"
        return f"{self.name}, {self.country} ({size})"


def _plain(text):
    """'München' -> 'munchen': search ignores case and accents."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()


@lru_cache(maxsize=1)
def cities():
    with open(Path(__file__).with_name("cities.csv"), encoding="utf-8") as f:
        return [City(r["name"], r["country"], float(r["lat"]), float(r["lon"]), int(r["population"]),
                     tuple(a for a in r["alt"].split("|") if a))
                for r in csv.DictReader(f)]


def find(query, limit=10):
    """Cities whose name (or German spelling) starts with the query, biggest first."""
    q = _plain(query.strip())
    if not q:
        return []
    starts, contains = [], []
    for c in cities():   # already sorted by population
        names = [_plain(c.name)] + [_plain(a) for a in c.alt]
        if any(n.startswith(q) for n in names):
            starts.append(c)
        elif any(q in n for n in names):
            contains.append(c)
    return (starts + contains)[:limit]


def lookup(name):
    """Best match for an exact place name ('Hamburg', 'München'), or None."""
    q = _plain(name.strip())
    for c in cities():
        if _plain(c.name) == q or any(_plain(a) == q for a in c.alt):
            return c
    return None


def great_circle_km(lat1, lon1, lat2, lon2):
    """Haversine distance on a sphere of radius 6,371 km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def road_km(a, b, factor=ROAD_FACTOR):
    """Road distance estimate between two places with lat/lon (dicts or City)."""
    get = (lambda p, k: p[k]) if isinstance(a, dict) else getattr
    return great_circle_km(get(a, "lat"), get(a, "lon"), get(b, "lat"), get(b, "lon")) * factor
