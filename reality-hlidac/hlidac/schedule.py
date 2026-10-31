"""Adaptive polling interval: check often when new listings usually appear, rarely at night.

Missing a listing is impossible here – "new" means "an ID we have not stored yet", and the
watcher reads further pages when a page has no known listing. A slower interval only delays
the alert.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from hlidac.db import parse_ts, ts

TZ = ZoneInfo("Europe/Prague")

FAST_S = 60
MEDIUM_S = 180
SLOW_S = 600

LEARN_WINDOW_DAYS = 28
MIN_HISTORY_DAYS = 14
FAST_RATE = 3.0     # new listings per hour at or above which we poll every minute
MEDIUM_RATE = 0.5   # below this we poll every 10 minutes

# Key: (is_weekend, local hour) -> average number of new listings in that hour.
Rates = dict[tuple[bool, int], float]


def default_interval(hour: int) -> int:
    """Used during the first 14 days, before we have our own history."""
    if 7 <= hour < 22:
        return FAST_S
    if hour >= 22 or hour == 6:
        return MEDIUM_S
    return SLOW_S


def interval_from_rate(rate: float) -> int:
    if rate >= FAST_RATE:
        return FAST_S
    if rate >= MEDIUM_RATE:
        return MEDIUM_S
    return SLOW_S


def learn_rates(conn: sqlite3.Connection, now: datetime) -> Rates | None:
    """Average new listings per (weekday/weekend, hour), or None if history is too short."""
    row = conn.execute(
        "SELECT MIN(started_at) AS first FROM runs WHERE kind = 'poll' AND ok = 1").fetchone()
    if not row or not row["first"]:
        return None
    window_start = max(parse_ts(row["first"]), now - timedelta(days=LEARN_WINDOW_DAYS))
    if now - parse_ts(row["first"]) < timedelta(days=MIN_HISTORY_DAYS):
        return None

    # Count how many weekday / weekend days the window covers (full days only).
    first_day = window_start.astimezone(TZ).date() + timedelta(days=1)
    last_day = now.astimezone(TZ).date() - timedelta(days=1)
    days = {False: 0, True: 0}
    day = first_day
    while day <= last_day:
        days[day.weekday() >= 5] += 1
        day += timedelta(days=1)
    if not days[False] or not days[True]:
        return None

    counts: Rates = {(w, h): 0.0 for w in (False, True) for h in range(24)}
    rows = conn.execute(
        "SELECT first_seen FROM listings WHERE from_sweep = 0 AND first_seen >= ? AND first_seen < ?",
        (ts(datetime.combine(first_day, datetime.min.time(), TZ)),
         ts(datetime.combine(last_day + timedelta(days=1), datetime.min.time(), TZ))))
    for r in rows:
        local = parse_ts(r["first_seen"]).astimezone(TZ)
        counts[(local.weekday() >= 5, local.hour)] += 1
    return {key: n / days[key[0]] for key, n in counts.items()}


def base_interval(now: datetime, rates: Rates | None) -> int:
    local = now.astimezone(TZ)
    if rates is None:
        return default_interval(local.hour)
    return interval_from_rate(rates[(local.weekday() >= 5, local.hour)])


def with_jitter(seconds: int, rng: random.Random) -> float:
    """60 s ± 10 s; longer intervals ± 10 % – so requests never look clockwork."""
    if seconds <= FAST_S:
        return seconds + rng.uniform(-10, 10)
    return seconds * rng.uniform(0.9, 1.1)
