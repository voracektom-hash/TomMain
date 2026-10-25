"""Alert rules: location + optional criteria. A listing alerts if ANY active rule matches.

Evaluation runs in two steps so we only download details for real candidates:
  1. check_listing() – data from the search page (free)
  2. check_detail()  – floor, ownership, keywords (needs one detail request)
Each check returns None when the rule passes, or a short Czech reason why not.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from hlidac import locations, medians
from hlidac.db import ts
from hlidac.schedule import TZ
from hlidac.sreality.parser import Listing, ListingDetail
from hlidac.text import find_keyword, normalize

DEFAULT_KEYWORDS = ["podíl", "dražba", "nájemník", "rezervováno"]
DEFAULT_QUIET = (22, 7)
GROUND_FLOOR = 1  # Sreality floor_number: 1 = 1. NP (ground floor), -1 = basement


@dataclass
class Rule:
    name: str
    location_type: str
    location: str
    id: int | None = None
    user_id: int | None = None
    active: bool = True
    max_price: int | None = None
    max_price_m2: int | None = None
    min_area: float | None = None
    max_area: float | None = None
    dispositions: list[str] = field(default_factory=list)
    ownerships: list[str] = field(default_factory=list)
    min_floor: int | None = None
    no_ground_floor: bool = False
    min_below_median: float | None = None
    exclude_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    quiet_start: int | None = DEFAULT_QUIET[0]
    quiet_end: int | None = DEFAULT_QUIET[1]
    quiet_action: str = "defer"  # 'defer' = send when quiet mode ends, 'drop' = never
    price_drop_alert: bool = False

    @property
    def needs_detail(self) -> bool:
        return bool(self.ownerships or self.min_floor is not None or self.no_ground_floor
                    or self.exclude_keywords)

    # --- quiet mode -----------------------------------------------------------------------

    def is_quiet(self, now: datetime) -> bool:
        if self.quiet_start is None or self.quiet_end is None:
            return False
        hour = now.astimezone(TZ).hour
        if self.quiet_start <= self.quiet_end:
            return self.quiet_start <= hour < self.quiet_end
        return hour >= self.quiet_start or hour < self.quiet_end  # over midnight, e.g. 22–7

    def quiet_ends_at(self, now: datetime) -> datetime:
        """Next moment the quiet window ends (only meaningful when is_quiet(now))."""
        local = now.astimezone(TZ)
        end = local.replace(hour=self.quiet_end or 0, minute=0, second=0, microsecond=0)
        if end <= local:
            end += timedelta(days=1)
        return end


# --- evaluation -------------------------------------------------------------------------

def check_listing(conn: sqlite3.Connection, rule: Rule, l: Listing) -> str | None:
    if l.id is None:
        return "chybí ID"
    if rule.location not in locations.listing_locations(conn, l, rule.location_type):
        return "jiná lokalita"
    if rule.dispositions and l.disposition not in rule.dispositions:
        return f"dispozice {l.disposition}"
    if rule.min_area is not None and (l.area_m2 is None or l.area_m2 < rule.min_area):
        return f"plocha {l.area_m2} m²"
    if rule.max_area is not None and (l.area_m2 is None or l.area_m2 > rule.max_area):
        return f"plocha {l.area_m2} m²"
    needs_price = rule.max_price or rule.max_price_m2 or rule.min_below_median
    if needs_price and not l.price_czk:
        return "cena na dotaz"
    if rule.max_price and l.price_czk > rule.max_price:
        return f"cena {l.price_czk}"
    if rule.max_price_m2 and (l.price_m2 is None or l.price_m2 > rule.max_price_m2):
        return f"Kč/m² {l.price_m2}"
    if rule.min_below_median:
        below = below_median(conn, rule, l)
        if below is None:
            return "medián není k dispozici"
        if below[0] < rule.min_below_median:
            return f"jen {below[0]:.0f} % pod mediánem"
    return None


def below_median(conn: sqlite3.Connection, rule: Rule | None, l: Listing) -> tuple[float, str] | None:
    """(percent below median, median label) – positive = cheaper than median."""
    if not l.price_m2:
        return None
    rule_type, rule_loc = (rule.location_type, rule.location) if rule else ("city", None)
    found = medians.lookup(conn, locations.median_candidates(conn, l, rule_type, rule_loc),
                           l.disposition)
    if found is None:
        return None
    median, label = found
    return (median - l.price_m2) / median * 100, label


def check_detail(rule: Rule, l: Listing, d: ListingDetail | None) -> str | None:
    """Detail-based criteria. Unknown values pass – one extra alert beats a missed flat."""
    if d is None:
        return None if not rule.needs_detail else "detail nedostupný"
    if rule.ownerships and d.ownership:
        wanted = {normalize(o)[:5] for o in rule.ownerships}  # 'osobni', 'druzs', 'statn'
        if normalize(d.ownership)[:5] not in wanted:
            return f"vlastnictví {d.ownership}"
    if d.floor is not None:
        if rule.no_ground_floor and d.floor <= GROUND_FLOOR:
            return f"podlaží {d.floor}"
        if rule.min_floor is not None and d.floor < rule.min_floor:
            return f"podlaží {d.floor}"
    keyword = find_keyword(f"{l.name}\n{d.description}", rule.exclude_keywords)
    if keyword:
        return f"obsahuje „{keyword}“"
    return None


# --- storage ----------------------------------------------------------------------------

_JSON_FIELDS = ("dispositions", "ownerships", "exclude_keywords")
_BOOL_FIELDS = ("active", "no_ground_floor", "price_drop_alert")
_COLUMNS = ("user_id", "name", "active", "location_type", "location", "max_price", "max_price_m2",
            "min_area", "max_area", "dispositions", "ownerships", "min_floor",
            "no_ground_floor", "min_below_median", "exclude_keywords", "quiet_start",
            "quiet_end", "quiet_action", "price_drop_alert")


def _from_row(row: sqlite3.Row) -> Rule:
    data = {k: row[k] for k in _COLUMNS}
    for k in _JSON_FIELDS:
        data[k] = json.loads(data[k] or "[]")
    for k in _BOOL_FIELDS:
        data[k] = bool(data[k])
    return Rule(id=row["id"], **data)


def load_rules(conn: sqlite3.Connection, *, active_only: bool = True,
               user_id: int | None = None) -> list[Rule]:
    where, args = [], []
    if active_only:
        where.append("active = 1")
    if user_id is not None:
        where.append("user_id = ?")
        args.append(user_id)
    sql = "SELECT * FROM rules" + (" WHERE " + " AND ".join(where) if where else "")
    return [_from_row(r) for r in conn.execute(sql + " ORDER BY id", args)]


def save_rule(conn: sqlite3.Connection, rule: Rule, now: datetime) -> int:
    """Insert or update (by owner + name). Returns the rule id."""
    values = []
    for k in _COLUMNS:
        v = getattr(rule, k)
        if k in _JSON_FIELDS:
            v = json.dumps(v, ensure_ascii=False)
        elif k in _BOOL_FIELDS:
            v = int(v)
        values.append(v)
    with conn:
        conn.execute(
            f"INSERT INTO rules ({', '.join(_COLUMNS)}, created_at, updated_at) "
            f"VALUES ({', '.join('?' * len(_COLUMNS))}, ?, ?) "
            f"ON CONFLICT(user_id, name) DO UPDATE SET "
            + ", ".join(f"{k} = excluded.{k}" for k in _COLUMNS if k not in ("name", "user_id"))
            + ", updated_at = excluded.updated_at",
            (*values, ts(now), ts(now)))
    return conn.execute("SELECT id FROM rules WHERE name = ? AND user_id IS ?",
                        (rule.name, rule.user_id)).fetchone()["id"]


class DuplicateRuleName(ValueError):
    pass


def get_rule(conn: sqlite3.Connection, rule_id: int) -> Rule | None:
    row = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
    return _from_row(row) if row else None


def create_rule(conn: sqlite3.Connection, rule: Rule, now: datetime) -> int:
    if conn.execute("SELECT 1 FROM rules WHERE name = ? AND user_id IS ?",
                    (rule.name, rule.user_id)).fetchone():
        raise DuplicateRuleName(rule.name)
    return save_rule(conn, rule, now)


def update_rule(conn: sqlite3.Connection, rule: Rule, now: datetime) -> None:
    """Update by id (the name may change)."""
    clash = conn.execute("SELECT 1 FROM rules WHERE name = ? AND user_id IS ? AND id != ?",
                         (rule.name, rule.user_id, rule.id)).fetchone()
    if clash:
        raise DuplicateRuleName(rule.name)
    values = []
    for k in _COLUMNS:
        v = getattr(rule, k)
        if k in _JSON_FIELDS:
            v = json.dumps(v, ensure_ascii=False)
        elif k in _BOOL_FIELDS:
            v = int(v)
        values.append(v)
    with conn:
        conn.execute(f"UPDATE rules SET {', '.join(f'{k} = ?' for k in _COLUMNS)}, "
                     "updated_at = ? WHERE id = ?", (*values, ts(now), rule.id))


def set_active(conn: sqlite3.Connection, rule_id: int, active: bool, now: datetime) -> None:
    with conn:
        conn.execute("UPDATE rules SET active = ?, updated_at = ? WHERE id = ?",
                     (int(active), ts(now), rule_id))


def delete_rule(conn: sqlite3.Connection, rule_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
