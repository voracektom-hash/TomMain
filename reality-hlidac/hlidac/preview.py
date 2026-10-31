"""'How many listings would this rule have caught?' – used by the web app and the CLI.

Floor, ownership and description keywords are only known for listings whose detail we
downloaded. Listings without a detail that pass everything else count as "maybe".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from hlidac import db
from hlidac.alerts import cached_detail
from hlidac.rules import Rule, check_detail, check_listing
from hlidac.sreality.parser import Listing
from hlidac.text import find_keyword


@dataclass
class Hit:
    listing: Listing
    first_seen: str
    sure: bool


@dataclass
class PreviewResult:
    days: int
    new_total: int            # new listings in the window (all, not only matching)
    hits: list[Hit] = field(default_factory=list)
    rejected_by_detail: int = 0
    offer_total: int = 0      # current offer size
    offer_hits: int = 0       # current offer matching search-data criteria

    @property
    def sure(self) -> int:
        return sum(h.sure for h in self.hits)

    @property
    def maybe(self) -> int:
        return len(self.hits) - self.sure


def preview(conn: sqlite3.Connection, rule: Rule, now: datetime, days: int = 7,
            with_offer: bool = True) -> PreviewResult:
    since = db.ts(now - timedelta(days=days))
    rows = conn.execute("SELECT * FROM listings WHERE from_sweep = 0 AND first_seen >= ? "
                        "ORDER BY first_seen DESC", (since,)).fetchall()
    result = PreviewResult(days=days, new_total=len(rows))
    for row in rows:
        l = db.listing_from_row(row)
        if check_listing(conn, rule, l) is not None:
            continue
        if find_keyword(l.name, rule.exclude_keywords):
            continue
        detail = cached_detail(conn, l.id)
        if detail is not None:
            if check_detail(rule, l, detail) is None:
                result.hits.append(Hit(l, row["first_seen"], sure=True))
            else:
                result.rejected_by_detail += 1
        else:
            result.hits.append(Hit(l, row["first_seen"], sure=not rule.needs_detail))
    if with_offer:
        offer = conn.execute("SELECT * FROM listings WHERE removed_at IS NULL").fetchall()
        result.offer_total = len(offer)
        result.offer_hits = sum(
            1 for r in offer if check_listing(conn, rule, db.listing_from_row(r)) is None)
    return result
