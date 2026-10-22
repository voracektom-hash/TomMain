"""Where is a listing? Location types, name lookup and the GPS fallback.

Location types used in rules:
  quarter  – Praha 1–22 and municipal districts like "Praha-Libuš" (Sreality 'quarter')
  citypart – cadastral parts like "Smíchov", "Karlín" (Sreality 'citypart')
  city     – municipality like "Černošice", or "Praha" for the whole city

When a Prague listing lacks its quarter or citypart, we look at the nearest listings
with a known value and take the majority (see docs/API.md, "Nepřesná lokalita").
"""

from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter

from hlidac.sreality.parser import Listing
from hlidac.text import normalize

LOCATION_TYPES = ("quarter", "citypart", "city")
TYPE_LABELS = {"quarter": "obvod / městská část", "citypart": "část obce", "city": "obec"}

GPS_NEIGHBOURS = 5
GPS_RADIUS_M = 1000
GPS_MAJORITY = 0.6
_DEG_LAT_M = 111_320  # metres per degree of latitude

QUARTER_RE = re.compile(r"^Praha[ -]")


class UnknownLocation(ValueError):
    def __init__(self, name: str, suggestions: list[str]):
        super().__init__(name)
        self.name = name
        self.suggestions = suggestions


def known_locations(conn: sqlite3.Connection) -> list[tuple[str, str, int]]:
    """All (type, name, listing count) seen in the data – used for lookup and autocomplete."""
    out = []
    for loc_type in LOCATION_TYPES:
        rows = conn.execute(
            f"SELECT {loc_type} AS name, COUNT(*) AS n FROM listings "
            f"WHERE {loc_type} IS NOT NULL GROUP BY {loc_type}").fetchall()
        out += [(loc_type, r["name"], r["n"]) for r in rows]
    return out


def resolve_name(conn: sqlite3.Connection, name: str) -> tuple[str, str]:
    """'smichov' -> ('citypart', 'Smíchov'). Raises UnknownLocation with suggestions."""
    wanted = normalize(name.strip())
    known = known_locations(conn)
    # Prefer quarter for "Praha 5"/"Praha-Libuš", otherwise city before citypart.
    order = {"quarter": 0, "city": 1, "citypart": 2}
    matches = sorted((k for k in known if normalize(k[1]) == wanted),
                     key=lambda k: (order[k[0]], -k[2]))
    if matches:
        return matches[0][0], matches[0][1]
    suggestions = sorted({k[1] for k in known if wanted in normalize(k[1])})[:8]
    raise UnknownLocation(name, suggestions)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * _DEG_LAT_M
    dx = (lon2 - lon1) * _DEG_LAT_M * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


def gps_candidates(conn: sqlite3.Connection, listing: Listing, field: str) -> set[str]:
    """Guess a missing quarter/citypart from the nearest listings that have it.

    Returns one name when the neighbours agree, several when they do not (so a rule for
    any of them matches – one extra alert beats a missed flat), or none without data.
    """
    if listing.lat is None or listing.lon is None:
        return set()
    d_lat = GPS_RADIUS_M / _DEG_LAT_M
    d_lon = d_lat / max(math.cos(math.radians(listing.lat)), 0.1)
    rows = conn.execute(
        f"SELECT {field} AS name, lat, lon FROM listings WHERE {field} IS NOT NULL "
        "AND id != ? AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
        (listing.id, listing.lat - d_lat, listing.lat + d_lat,
         listing.lon - d_lon, listing.lon + d_lon)).fetchall()
    near = sorted((_distance_m(listing.lat, listing.lon, r["lat"], r["lon"]), r["name"])
                  for r in rows)
    near = [name for dist, name in near if dist <= GPS_RADIUS_M][:GPS_NEIGHBOURS]
    if not near:
        return set()
    top, count = Counter(near).most_common(1)[0]
    if count / len(near) > GPS_MAJORITY:
        return {top}
    return set(near)


def listing_locations(conn: sqlite3.Connection, listing: Listing, loc_type: str) -> set[str]:
    """Names of the given type this listing belongs to (GPS fallback when missing)."""
    value = getattr(listing, loc_type)
    if value:
        return {value}
    if loc_type == "city":
        return set()
    return gps_candidates(conn, listing, loc_type)


def median_candidates(conn: sqlite3.Connection, listing: Listing, rule_type: str,
                      rule_location: str) -> list[tuple[str, str | None]]:
    """Where to look for a median, most specific first."""
    quarters = listing_locations(conn, listing, "quarter") if listing.region_id == 10 else set()
    return [
        (rule_type, rule_location),
        ("citypart", listing.citypart),
        ("quarter", next(iter(quarters)) if len(quarters) == 1 else None),
        ("district", listing.district if listing.region_id != 10 else None),
        ("city", listing.city),
    ]


def short_name(listing: Listing) -> str:
    """Compact ASCII-friendly location for SMS: 'P5-Smíchov', 'P-Libuš', 'Černošice'."""
    if listing.region_id == 10:
        quarter = listing.quarter or ""
        m = re.match(r"^Praha (\d+)$", quarter)
        if m:
            prefix = f"P{m.group(1)}"
        elif quarter.startswith("Praha-"):
            return "P-" + quarter[len("Praha-"):]
        else:
            prefix = "Praha"
        return f"{prefix}-{listing.citypart}" if listing.citypart else prefix
    if listing.city and listing.citypart and listing.citypart != listing.city:
        return f"{listing.city}-{listing.citypart}"
    return listing.city or listing.citypart or "?"
