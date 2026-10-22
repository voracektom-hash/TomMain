"""From new listings to delivered notifications.

Flow per poll:
  1. match new listings and price drops against active rules (search data first)
  2. download the detail only for candidates, finish the check
  3. queue one alert per channel+recipient (respecting quiet mode)
  4. send everything that is due; failed sends are retried
Plus the watchdog that reports when the watcher itself is in trouble.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from hlidac import db
from hlidac.notify.base import Message, Notifier, NotifyError
from hlidac.notify.format import listing_message, service_message
from hlidac.schedule import TZ
from hlidac.rules import Rule, below_median, check_detail, check_listing, load_rules
from hlidac.sreality.client import SrealityClient, SrealityError
from hlidac.sreality.parser import Listing, ListingDetail, ParseError, parse_detail

log = logging.getLogger("hlidac")

MAX_ATTEMPTS = 5
DETAIL_CACHE = timedelta(hours=12)
WATCHDOG_MIN_SILENCE = timedelta(minutes=10)
WATCHDOG_REPEAT = timedelta(hours=1)


@dataclass
class Channel:
    notifier: Notifier
    recipients: list[str]


class AlertEngine:
    def __init__(self, conn: sqlite3.Connection, client: SrealityClient,
                 channels: list[Channel]):
        self.conn = conn
        self.client = client
        self.channels = channels

    # --- matching -------------------------------------------------------------------------

    def process(self, new: list[Listing], price_changes: list[db.PriceChange],
                now: datetime) -> int:
        """Match listings against rules and queue alerts. Returns the number of alerts."""
        rules = load_rules(self.conn)
        if not rules:
            return 0
        queued = 0
        for l in new:
            if self._already_alerted(l.id, "new"):
                continue
            matched = self._match(rules, l, drops_only=False)
            if matched:
                queued += self._queue(l, matched, now, drop=None)
        for ch in price_changes:
            if ch.new_price >= ch.old_price or self._already_alerted(ch.listing.id, "price_drop",
                                                                     ch.new_price):
                continue
            matched = self._match(rules, ch.listing, drops_only=True)
            if matched:
                queued += self._queue(ch.listing, matched, now,
                                      drop=(ch.old_price, ch.new_price))
        return queued

    def _match(self, rules: list[Rule], l: Listing, *, drops_only: bool
               ) -> list[tuple[Rule, ListingDetail | None]]:
        candidates = []
        for rule in rules:
            if drops_only and not rule.price_drop_alert:
                continue
            reason = check_listing(self.conn, rule, l)
            if reason is None:
                candidates.append(rule)
            else:
                log.debug("Pravidlo „%s“ × %d: %s", rule.name, l.id, reason)
        if not candidates:
            return []
        detail = self.detail(l.id)
        matched = []
        for rule in candidates:
            reason = check_detail(rule, l, detail)
            if reason is None:
                matched.append((rule, detail))
            else:
                log.info("Pravidlo „%s“ odmítlo %d po detailu: %s", rule.name, l.id, reason)
        return matched

    def detail(self, listing_id: int) -> ListingDetail | None:
        """Detail from cache or Sreality. None if unavailable (rule check then decides)."""
        row = self.conn.execute("SELECT * FROM listing_details WHERE listing_id = ?",
                                (listing_id,)).fetchone()
        if row and db.utcnow() - db.parse_ts(row["fetched_at"]) < DETAIL_CACHE:
            return ListingDetail(
                id=listing_id, since=row["since"], edited=None, floor=row["floor"],
                floors_total=row["floors_total"], ownership=row["ownership"],
                usable_area=row["usable_area"], description=row["description"] or "",
                broker_name=row["broker_name"], broker_phone=row["broker_phone"],
                broker_email=row["broker_email"], agency=row["agency"])
        try:
            data = self.client.detail(listing_id)
            if data is None:
                log.warning("Detail %d už neexistuje", listing_id)
                return None
            d = parse_detail(data)
        except (SrealityError, ParseError) as exc:
            log.warning("Detail %d se nepodařilo stáhnout: %s", listing_id, exc)
            return None
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO listing_details (listing_id, fetched_at, since, floor,
                   floors_total, ownership, usable_area, description, broker_name,
                   broker_phone, broker_email, agency) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (listing_id, db.ts(db.utcnow()), d.since, d.floor, d.floors_total, d.ownership,
                 d.usable_area, d.description, d.broker_name, d.broker_phone, d.broker_email,
                 d.agency))
            self.conn.execute("UPDATE listings SET since = ? WHERE id = ?", (d.since, listing_id))
        return d

    def _already_alerted(self, listing_id: int, kind: str, price: int | None = None) -> bool:
        sql = "SELECT 1 FROM alerts WHERE listing_id = ? AND kind = ?"
        args: tuple = (listing_id, kind)
        if price is not None:
            sql += " AND price = ?"
            args += (price,)
        return self.conn.execute(sql, args).fetchone() is not None

    # --- queueing -------------------------------------------------------------------------

    def _queue(self, l: Listing, matched: list[tuple[Rule, ListingDetail | None]],
               now: datetime, drop: tuple[int, int] | None) -> int:
        rules = [r for r, _ in matched]
        detail = matched[0][1]
        below = below_median(self.conn, rules[0], l)
        message = listing_message(l, detail, below, [r.name for r in rules], drop)
        status, send_after = quiet_decision(rules, now)
        kind = "price_drop" if drop else "new"
        n = self._insert(kind, l.id, l.price_czk, rules, message, status, send_after, now)
        what = "Sleva" if drop else "Shoda"
        when = {"queued": "odesílám" if send_after <= now else
                f"tichý režim, odešlu {send_after.astimezone(TZ).strftime('%H:%M')}",
                "dropped": "tichý režim, zahazuji"}[status]
        log.info("%s: %s → %s", what, message.title, when)
        return n

    def _insert(self, kind: str, listing_id: int | None, price: int | None, rules: list[Rule],
                m: Message, status: str, send_after: datetime, now: datetime) -> int:
        payload = json.dumps({"url": m.url, "image_url": m.image_url, "phone": m.phone,
                              "priority": m.priority, "tags": m.tags, "sms": m.sms},
                             ensure_ascii=False)
        n = 0
        with self.conn:
            for channel in self.channels:
                for recipient in channel.recipients:
                    body = m.sms if channel.notifier.channel == "sms" else m.body
                    self.conn.execute(
                        """INSERT INTO alerts (kind, listing_id, price, rule_names, channel,
                           recipient, title, body, payload, status, send_after, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (kind, listing_id, price, ", ".join(r.name for r in rules),
                         channel.notifier.channel, recipient, m.title, body, payload, status,
                         db.ts(send_after), db.ts(now)))
                    n += 1
        return n

    # --- sending --------------------------------------------------------------------------

    def dispatch(self, now: datetime) -> int:
        """Send all due alerts. Returns how many were sent."""
        by_channel = {c.notifier.channel: c.notifier for c in self.channels}
        rows = self.conn.execute(
            "SELECT * FROM alerts WHERE status = 'queued' AND send_after <= ? ORDER BY id",
            (db.ts(now),)).fetchall()
        sent = 0
        for row in rows:
            notifier = by_channel.get(row["channel"])
            if notifier is None:
                continue  # channel was disabled meanwhile; keep it queued
            p = json.loads(row["payload"] or "{}")
            message = Message(title=row["title"], body=row["body"], sms=p.get("sms") or row["body"],
                              url=p.get("url"), image_url=p.get("image_url"),
                              phone=p.get("phone"), priority=p.get("priority", 3),
                              tags=p.get("tags", []))
            try:
                notifier.send(row["recipient"], message)
            except NotifyError as exc:
                attempts = row["attempts"] + 1
                status = "failed" if attempts >= MAX_ATTEMPTS else "queued"
                retry = now + timedelta(minutes=2 ** attempts)
                with self.conn:
                    self.conn.execute(
                        "UPDATE alerts SET attempts = ?, status = ?, error = ?, send_after = ? "
                        "WHERE id = ?", (attempts, status, str(exc), db.ts(retry), row["id"]))
                log.warning("Odeslání %s → %s selhalo (%d/%d): %s", row["channel"],
                            row["recipient"], attempts, MAX_ATTEMPTS, exc)
                continue
            with self.conn:
                self.conn.execute(
                    "UPDATE alerts SET status = 'sent', sent_at = ?, attempts = attempts + 1, "
                    "error = NULL WHERE id = ?", (db.ts(now), row["id"]))
            sent += 1
        return sent

    # --- watchdog -------------------------------------------------------------------------

    def watchdog(self, now: datetime, error: Exception | None, expected_interval_s: float) -> None:
        """Service alert when polling fails for too long or the API looks broken.
        At most one alarm per hour, plus one "all good again" message after recovery."""
        last_ok = self.conn.execute(
            "SELECT MAX(started_at) FROM runs WHERE kind = 'poll' AND ok = 1").fetchone()[0]
        alarm_on = db.get_meta(self.conn, "watchdog_alarm") == "1"
        if error is None and last_ok and alarm_on:
            db.set_meta(self.conn, "watchdog_alarm", "0")
            self._service("Hlídač zase funguje, kontroly probíhají normálně.", now)
            return

        problem = None
        if isinstance(error, ParseError):
            problem = f"Sreality vrací nečekaná data (možná změna API): {error}"
        else:
            limit = max(WATCHDOG_MIN_SILENCE, timedelta(seconds=2.5 * expected_interval_s))
            since = db.parse_ts(last_ok) if last_ok else None
            if since is None or now - since > limit:
                minutes = int((now - since).total_seconds() // 60) if since else None
                ago = f"{minutes} min" if minutes is not None else "nikdy"
                problem = f"Žádná úspěšná kontrola Sreality ({ago})."
                if error:
                    problem += f" Poslední chyba: {error}"
        if problem is None:
            return
        last_sent = db.get_meta(self.conn, "watchdog_sent_at")
        if last_sent and now - db.parse_ts(last_sent) < WATCHDOG_REPEAT:
            return
        log.error("Watchdog: %s", problem)
        db.set_meta(self.conn, "watchdog_sent_at", db.ts(now))
        db.set_meta(self.conn, "watchdog_alarm", "1")
        self._service(problem, now)

    def _service(self, text: str, now: datetime) -> None:
        self.send_now(service_message(text), now)

    def send_now(self, message: Message, now: datetime) -> int:
        """Service/test message to every channel, ignoring quiet mode. Returns sent count."""
        self._insert("service", None, None, [], message, "queued", now, now)
        return self.dispatch(now)


def quiet_decision(rules: list[Rule], now: datetime) -> tuple[str, datetime]:
    """('queued', when) or ('dropped', now). Any non-quiet rule means send right away."""
    if any(not r.is_quiet(now) for r in rules):
        return "queued", now
    deferring = [r for r in rules if r.quiet_action == "defer"]
    if not deferring:
        return "dropped", now
    return "queued", min(r.quiet_ends_at(now) for r in deferring)
