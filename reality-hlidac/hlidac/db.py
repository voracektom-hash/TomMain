"""SQLite storage shared by the watcher and (later) the web app.

All timestamps are stored as UTC strings "YYYY-MM-DD HH:MM:SS".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from hlidac.sreality.parser import Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id          INTEGER PRIMARY KEY,   -- Sreality hash_id
    name        TEXT NOT NULL,
    disposition TEXT,
    area_m2     REAL,
    price_czk   INTEGER,               -- NULL = price on request
    price_m2    INTEGER,
    region_id   INTEGER,
    district    TEXT,
    quarter     TEXT,                  -- Praha 1–22
    citypart    TEXT,
    city        TEXT,
    street      TEXT,
    lat         REAL,
    lon         REAL,
    premise_id  INTEGER,
    user_id     INTEGER,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    from_sweep  INTEGER NOT NULL DEFAULT 0,  -- 1 = found by the initial full sweep, not "new"
    since       TEXT,                  -- publication date from detail (phase 2)
    removed_at  TEXT                   -- set when a full sweep no longer finds it
);
CREATE INDEX IF NOT EXISTS idx_listings_gps ON listings(lat, lon);
CREATE INDEX IF NOT EXISTS idx_listings_first_seen ON listings(first_seen);
CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen);

CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  INTEGER NOT NULL REFERENCES listings(id),
    changed_at  TEXT NOT NULL,
    old_price   INTEGER NOT NULL,
    new_price   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_history_listing ON price_history(listing_id);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,     -- 'poll' or 'sweep'
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL,
    ok              INTEGER NOT NULL,
    n_results       INTEGER NOT NULL DEFAULT 0,
    n_new           INTEGER NOT NULL DEFAULT 0,
    n_price_changes INTEGER NOT NULL DEFAULT 0,
    pages           INTEGER NOT NULL DEFAULT 0,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);

CREATE TABLE IF NOT EXISTS medians (
    scope       TEXT NOT NULL,         -- 'quarter', 'citypart', 'city' or 'district'
    location    TEXT NOT NULL,
    disposition TEXT NOT NULL,         -- '' = all dispositions
    median_m2   INTEGER NOT NULL,
    n           INTEGER NOT NULL,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (scope, location, disposition)
);

CREATE TABLE IF NOT EXISTS listing_details (
    listing_id    INTEGER PRIMARY KEY REFERENCES listings(id),
    fetched_at    TEXT NOT NULL,
    since         TEXT,
    floor         INTEGER,             -- 1 = ground floor (1. NP), -1 = basement
    floors_total  INTEGER,
    ownership     TEXT,
    usable_area   REAL,
    description   TEXT,
    broker_name   TEXT,
    broker_phone  TEXT,
    broker_email  TEXT,
    agency        TEXT
);

CREATE TABLE IF NOT EXISTS rules (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL UNIQUE,
    active              INTEGER NOT NULL DEFAULT 1,
    location_type       TEXT NOT NULL,     -- 'quarter', 'citypart' or 'city'
    location            TEXT NOT NULL,
    max_price           INTEGER,
    max_price_m2        INTEGER,
    min_area            REAL,
    max_area            REAL,
    dispositions        TEXT NOT NULL DEFAULT '[]',   -- JSON list, empty = any
    ownerships          TEXT NOT NULL DEFAULT '[]',   -- JSON list, empty = any
    min_floor           INTEGER,
    no_ground_floor     INTEGER NOT NULL DEFAULT 0,
    min_below_median    REAL,              -- percent
    exclude_keywords    TEXT NOT NULL DEFAULT '[]',   -- JSON list
    quiet_start         INTEGER,           -- hour 0-23, NULL = no quiet mode
    quiet_end           INTEGER,
    quiet_action        TEXT NOT NULL DEFAULT 'defer',  -- 'defer' (send in the morning) or 'drop'
    price_drop_alert    INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,             -- 'new', 'price_drop' or 'service'
    listing_id  INTEGER REFERENCES listings(id),
    price       INTEGER,                   -- listing price at alert time (dedup of price drops)
    rule_names  TEXT NOT NULL DEFAULT '',
    channel     TEXT NOT NULL,             -- 'ntfy', 'sms', 'console'
    recipient   TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    body        TEXT NOT NULL,             -- full text actually sent
    payload     TEXT,                      -- JSON with extra fields (url, image, phone)
    status      TEXT NOT NULL,             -- 'queued', 'sent', 'failed', 'dropped'
    send_after  TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    created_at  TEXT NOT NULL,
    sent_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status, send_after);
CREATE INDEX IF NOT EXISTS idx_alerts_listing ON alerts(listing_id, kind);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # watcher and web app read/write concurrently
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


@dataclass(frozen=True)
class PriceChange:
    listing: Listing
    old_price: int
    new_price: int

    @property
    def percent(self) -> float:
        return (self.new_price - self.old_price) / self.old_price * 100


@dataclass
class UpsertResult:
    new: list[Listing]
    price_changes: list[PriceChange]
    known_count: int  # listings on the page that were already in the DB


def upsert_listings(conn: sqlite3.Connection, listings: list[Listing], now: datetime,
                    *, from_sweep: bool = False) -> UpsertResult:
    """Insert unseen listings, refresh known ones and record price changes."""
    now_s = ts(now)
    result = UpsertResult(new=[], price_changes=[], known_count=0)
    with conn:
        for l in listings:
            row = conn.execute("SELECT price_czk FROM listings WHERE id = ?", (l.id,)).fetchone()
            values = (l.name, l.disposition, l.area_m2, l.price_czk, l.price_m2, l.region_id,
                      l.district, l.quarter, l.citypart, l.city, l.street, l.lat, l.lon,
                      l.premise_id, l.user_id)
            if row is None:
                conn.execute(
                    """INSERT INTO listings (name, disposition, area_m2, price_czk, price_m2,
                       region_id, district, quarter, citypart, city, street, lat, lon,
                       premise_id, user_id, id, first_seen, last_seen, from_sweep)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (*values, l.id, now_s, now_s, int(from_sweep)))
                result.new.append(l)
                continue

            result.known_count += 1
            old = row["price_czk"]
            if old and l.price_czk and old != l.price_czk:
                conn.execute(
                    "INSERT INTO price_history (listing_id, changed_at, old_price, new_price)"
                    " VALUES (?,?,?,?)", (l.id, now_s, old, l.price_czk))
                result.price_changes.append(PriceChange(l, old, l.price_czk))
            conn.execute(
                """UPDATE listings SET name=?, disposition=?, area_m2=?, price_czk=?, price_m2=?,
                   region_id=?, district=?, quarter=?, citypart=?, city=?, street=?, lat=?,
                   lon=?, premise_id=?, user_id=?, last_seen=?, removed_at=NULL WHERE id=?""",
                (*values, now_s, l.id))
    return result


def mark_removed(conn: sqlite3.Connection, sweep_started: datetime, now: datetime) -> int:
    """After a full sweep: listings not seen during it are gone from Sreality."""
    with conn:
        cur = conn.execute(
            "UPDATE listings SET removed_at = ? WHERE last_seen < ? AND removed_at IS NULL",
            (ts(now), ts(sweep_started)))
    return cur.rowcount


def record_run(conn: sqlite3.Connection, kind: str, started: datetime, finished: datetime,
               ok: bool, *, n_results: int = 0, n_new: int = 0, n_price_changes: int = 0,
               pages: int = 0, error: str | None = None) -> None:
    with conn:
        conn.execute(
            """INSERT INTO runs (kind, started_at, finished_at, ok, n_results, n_new,
               n_price_changes, pages, error) VALUES (?,?,?,?,?,?,?,?,?)""",
            (kind, ts(started), ts(finished), int(ok), n_results, n_new, n_price_changes,
             pages, error))


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def listing_from_row(row: sqlite3.Row) -> Listing:
    return Listing(
        id=row["id"], name=row["name"], disposition=row["disposition"], area_m2=row["area_m2"],
        price_czk=row["price_czk"], price_m2=row["price_m2"], region_id=row["region_id"],
        district=row["district"], quarter=row["quarter"], citypart=row["citypart"],
        city=row["city"], street=row["street"], lat=row["lat"], lon=row["lon"],
        premise_id=row["premise_id"], user_id=row["user_id"])
