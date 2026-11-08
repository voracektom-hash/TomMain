"""Rolling 90-day median of asking price per m², per location (and disposition)."""

from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from hlidac.db import ts

WINDOW_DAYS = 90
MIN_SAMPLES = 5               # per location
MIN_SAMPLES_DISPOSITION = 10  # per location + disposition
MIN_PRICE_M2 = 10_000         # below this it is a share, auction or typo, not a real price

PRAHA_REGION_ID = 10


def compute(conn: sqlite3.Connection, now: datetime) -> int:
    """Recompute the medians table. Returns the number of rows written."""
    rows = conn.execute(
        """SELECT region_id, quarter, citypart, city, district, disposition, price_m2 FROM listings
           WHERE last_seen >= ? AND price_m2 >= ?""",
        (ts(now - timedelta(days=WINDOW_DAYS)), MIN_PRICE_M2)).fetchall()

    groups: dict[tuple[str, str], list[tuple[str | None, int]]] = defaultdict(list)
    for r in rows:
        keys = [("city", r["city"]), ("citypart", r["citypart"])]
        if r["region_id"] == PRAHA_REGION_ID:
            keys.append(("quarter", r["quarter"]))
        else:  # okres – fallback for small villages
            keys.append(("district", r["district"]))
        for scope, location in keys:
            if location:
                groups[(scope, location)].append((r["disposition"], r["price_m2"]))

    out = []
    for (scope, location), items in groups.items():
        prices = [p for _, p in items]
        if len(prices) >= MIN_SAMPLES:
            out.append((scope, location, "", round(statistics.median(prices)), len(prices)))
        by_disp: dict[str, list[int]] = defaultdict(list)
        for disp, price in items:
            if disp:
                by_disp[disp].append(price)
        for disp, disp_prices in by_disp.items():
            if len(disp_prices) >= MIN_SAMPLES_DISPOSITION:
                out.append((scope, location, disp, round(statistics.median(disp_prices)),
                            len(disp_prices)))

    with conn:
        conn.execute("DELETE FROM medians")
        conn.executemany(
            "INSERT INTO medians (scope, location, disposition, median_m2, n, computed_at)"
            " VALUES (?,?,?,?,?,?)", [(*row, ts(now)) for row in out])
    return len(out)


def lookup(conn: sqlite3.Connection, candidates: list[tuple[str, str | None]],
           disposition: str | None) -> tuple[int, str] | None:
    """Find the most specific median: first candidate location wins; within it, a
    disposition-level median beats the all-dispositions one. Returns (median, label)."""
    for scope, location in candidates:
        if not location:
            continue
        rows = {r["disposition"]: r["median_m2"] for r in conn.execute(
            "SELECT disposition, median_m2 FROM medians WHERE scope = ? AND location = ?",
            (scope, location))}
        if disposition and disposition in rows:
            return rows[disposition], f"{location} {disposition}"
        if "" in rows:
            return rows[""], location
    return None
