"""The watcher: polls Sreality for new flat listings and stores everything in SQLite.

Run with:  python -m hlidac.watcher
"""

from __future__ import annotations

import logging
import random
import signal
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from hlidac import config, db, medians, schedule
from hlidac.alerts import AlertEngine, Channel
from hlidac.notify.console import ConsoleNotifier
from hlidac.notify.ntfy import NtfyNotifier
from hlidac.rules import load_rules
from hlidac.sreality.client import RateLimited, SrealityClient, SrealityError
from hlidac.sreality.parser import Listing, ParseError, parse_search

log = logging.getLogger("hlidac")

MAX_PAGES_PER_POLL = 40       # catch-up limit after downtime (40 × 60 = 2 400 listings)
CAUGHT_UP_OVERLAP = 3         # this many listings from the previous poll = nothing newer left
SWEEP_PAGE_LIMIT = 200
SWEEP_PAUSE_S = 10            # be gentle: one sweep request every 10 s
SWEEP_EVERY = timedelta(days=7)
SWEEP_HOURS = range(2, 5)     # weekly sweep runs at night (local time)
MEDIANS_EVERY = timedelta(hours=1)
SLOWDOWN_FACTOR = 5
SLOWDOWN_FOR = timedelta(minutes=30)
MAX_BACKOFF_S = 900


class StructureError(ParseError):
    """The API answered, but the data makes no sense (e.g. zero listings)."""


@dataclass
class PollResult:
    n_results: int
    new: list[Listing]
    price_changes: list[db.PriceChange]
    pages: int


def fmt_price(czk: int | None) -> str:
    if not czk:
        return "cena na dotaz"
    return f"{czk / 1_000_000:.2f} M Kč".replace(".", ",")


def fmt_location(l: Listing) -> str:
    if l.region_id == 10:  # Praha: "Praha 5 Smíchov"
        parts = [l.quarter or "Praha ?", l.citypart]
    else:                  # elsewhere: "Beroun Beroun-Město", "Černošice"
        parts = [l.city, l.citypart]
    return " ".join(dict.fromkeys(p for p in parts if p)) or "?"


def describe(l: Listing) -> str:
    area = f"{l.area_m2:g} m²" if l.area_m2 else "? m²"
    per_m2 = f" ({l.price_m2:,} Kč/m²)".replace(",", " ") if l.price_m2 else ""
    seller = " | soukromý" if l.is_private else ""
    return (f"{l.disposition or '?'} {area} | {fmt_location(l)} | "
            f"{fmt_price(l.price_czk)}{per_m2}{seller} | {l.url}")


class Watcher:
    def __init__(self, conn: sqlite3.Connection, client: SrealityClient, cfg: config.Config,
                 *, now: Callable[[], datetime] = db.utcnow,
                 sleep: Callable[[float], None] = time.sleep,
                 rng: random.Random | None = None, alerts: AlertEngine | None = None):
        self.conn = conn
        self.alerts = alerts
        self.prev_ids: set[int] | None = None
        self.client = client
        self.cfg = cfg
        self.now = now
        self.sleep = sleep
        self.rng = rng or random.Random()
        self.failures = 0
        self.slowdown_until: datetime | None = None
        self.medians_at: datetime | None = None
        self.rates: schedule.Rates | None = None
        self.rates_at: datetime | None = None
        self.expected_interval: float = schedule.FAST_S

    # --- one poll -------------------------------------------------------------------------

    def poll_once(self) -> PollResult:
        """Fetch the newest listings. The list is sorted by *edit* time, so we read pages
        until we meet listings seen in the previous poll – everything above them is newer."""
        started = self.now()
        result = PollResult(0, [], [], 0)
        sweep_done = db.get_meta(self.conn, "sweep_done") is not None
        prev = self._previous_ids()
        seen: set[int] = set()
        try:
            for page in range(MAX_PAGES_PER_POLL):
                if page:
                    if page == 1:
                        log.info("Dohánění: na první stránce nejsou inzeráty z minulé kontroly, "
                                 "čtu další stránky…")
                    self.sleep(SWEEP_PAUSE_S)
                data = self.client.search(self.cfg.region_ids, page * self.cfg.page_limit,
                                          self.cfg.page_limit)
                total, listings = parse_search(data)
                if not listings:
                    raise StructureError(f"API vrátilo 0 inzerátů (total={total})")
                up = db.upsert_listings(self.conn, listings, self.now())
                result.pages += 1
                result.n_results += len(listings)
                result.new += up.new
                result.price_changes += up.price_changes
                ids = {l.id for l in listings}
                seen |= ids
                caught_up = len(ids & prev) >= min(CAUGHT_UP_OVERLAP, len(prev))
                if caught_up or not sweep_done or (page + 1) * self.cfg.page_limit >= total:
                    break
            else:
                log.warning("Ani po %d stránkách jsem nedohnal minulou kontrolu – "
                            "část nových inzerátů mohla uniknout", MAX_PAGES_PER_POLL)
        except Exception as exc:
            db.record_run(self.conn, "poll", started, self.now(), False, pages=result.pages,
                          error=f"{type(exc).__name__}: {exc}")
            raise
        self.prev_ids = seen
        db.record_run(self.conn, "poll", started, self.now(), True,
                      n_results=result.n_results, n_new=len(result.new),
                      n_price_changes=len(result.price_changes), pages=result.pages)
        return result

    def _previous_ids(self) -> set[int]:
        """IDs seen in the last successful run (from memory, or from the DB after a restart)."""
        if self.prev_ids is not None:
            return self.prev_ids
        row = self.conn.execute(
            "SELECT MAX(started_at) FROM runs WHERE ok = 1").fetchone()
        if not row or not row[0]:
            return set()
        return {r[0] for r in self.conn.execute(
            "SELECT id FROM listings WHERE last_seen >= ?", (row[0],))}

    # --- full sweep -----------------------------------------------------------------------

    def sweep(self, *, initial: bool) -> None:
        """Walk the whole offer. Initial: learn existing listings. Weekly: detect removals."""
        started = self.now()
        label = "První naplnění" if initial else "Týdenní kontrola celé nabídky"
        log.info("%s: začínám (cca %d s mezi requesty)…", label, SWEEP_PAUSE_S)
        offset, total, pages, n_new = 0, None, 0, 0
        try:
            while total is None or offset < total:
                data = self.client.search(self.cfg.region_ids, offset, SWEEP_PAGE_LIMIT)
                total, listings = parse_search(data)
                if not listings:
                    break
                up = db.upsert_listings(self.conn, listings, self.now(), from_sweep=initial)
                n_new += len(up.new)
                pages += 1
                offset += SWEEP_PAGE_LIMIT
                log.info("%s: %d / %d", label, min(offset, total), total)
                if offset < total:
                    self.sleep(SWEEP_PAUSE_S)
        except Exception as exc:
            db.record_run(self.conn, "sweep", started, self.now(), False, pages=pages,
                          error=f"{type(exc).__name__}: {exc}")
            raise
        removed = 0 if initial else db.mark_removed(self.conn, started, self.now())
        db.record_run(self.conn, "sweep", started, self.now(), True, n_results=total or 0,
                      n_new=n_new, pages=pages)
        db.set_meta(self.conn, "sweep_done", db.ts(self.now()))
        self.prev_ids = None  # next poll compares against what the sweep saw
        log.info("%s: hotovo – %d inzerátů, %d nově uložených, %d staženo z nabídky",
                 label, total or 0, n_new, removed)

    def sweep_due(self) -> bool:
        last = db.get_meta(self.conn, "sweep_done")
        if last is None:
            return True
        now = self.now()
        local_hour = now.astimezone(schedule.TZ).hour
        return now - db.parse_ts(last) >= SWEEP_EVERY and local_hour in SWEEP_HOURS

    # --- main loop ------------------------------------------------------------------------

    def next_delay(self) -> float:
        now = self.now()
        if self.rates_at is None or now - self.rates_at >= MEDIANS_EVERY:
            self.rates = schedule.learn_rates(self.conn, now)
            self.rates_at = now
        base = schedule.base_interval(now, self.rates)
        rules = load_rules(self.conn)
        if rules and all(r.is_quiet(now) for r in rules):
            base = max(base, schedule.SLOW_S)  # nothing would be sent now anyway
        self.expected_interval = base
        delay = schedule.with_jitter(base, self.rng)
        if self.slowdown_until and now < self.slowdown_until:
            delay *= SLOWDOWN_FACTOR
        if self.failures:
            delay = max(delay, min(60 * 2 ** (self.failures - 1), MAX_BACKOFF_S))
        return delay

    def maybe_compute_medians(self) -> None:
        now = self.now()
        if self.medians_at is None or now - self.medians_at >= MEDIANS_EVERY:
            n = medians.compute(self.conn, now)
            self.medians_at = now
            log.debug("Mediány přepočítány (%d řádků)", n)

    def step(self) -> float:
        """One iteration of the loop. Returns how long to sleep before the next one."""
        error: Exception | None = None
        try:
            if self.sweep_due():
                first = db.get_meta(self.conn, "sweep_done") is None
                self.sweep(initial=first)
            result = self.poll_once()
            self.failures = 0
            for l in result.new:
                log.info("Nový: %s", describe(l))
            for ch in result.price_changes:
                log.info("Změna ceny: %s → %s (%s %%) | %s", fmt_price(ch.old_price),
                         fmt_price(ch.new_price), f"{ch.percent:+.1f}".replace(".", ","),
                         describe(ch.listing))
            self.maybe_compute_medians()
            if self.alerts:
                self.alerts.process(result.new, result.price_changes, self.now())
        except RateLimited as exc:
            error = exc
            self.failures += 1
            self.slowdown_until = self.now() + SLOWDOWN_FOR
            log.warning("Sreality nás brzdí (%s) – zpomaluji %d× na %d min",
                        exc, SLOWDOWN_FACTOR, SLOWDOWN_FOR.seconds // 60)
        except ParseError as exc:
            error = exc
            self.failures += 1
            log.error("Odpověď Sreality má nečekaný tvar – možná změna API: %s", exc)
        except SrealityError as exc:
            error = exc
            self.failures += 1
            log.warning("Chyba spojení se Sreality (%d. v řadě): %s", self.failures, exc)

        delay = self.next_delay()
        if self.alerts:
            self.alerts.dispatch(self.now())
            self.alerts.watchdog(self.now(), error, self.expected_interval)
        log.debug("Další kontrola za %.0f s", delay)
        return delay

    def run_forever(self) -> None:
        log.info("Watcher startuje: regiony %s, %d inzerátů na kontrolu, DB %s",
                 ",".join(map(str, self.cfg.region_ids)), self.cfg.page_limit, self.cfg.db_path)
        hour_start, polls, new = self.now(), 0, 0
        while True:
            before = self.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            delay = self.step()
            polls += 1
            new += self.conn.execute(
                "SELECT COALESCE(SUM(n_new), 0) FROM runs WHERE id > ? AND kind = 'poll'",
                (before,)).fetchone()[0]
            if self.now() - hour_start >= timedelta(hours=1):
                log.info("Za poslední hodinu: %d kontrol, %d nových inzerátů", polls, new)
                hour_start, polls, new = self.now(), 0, 0
            self.sleep(delay)


def build_channels(cfg: config.Config) -> list[Channel]:
    channels = []
    for name in cfg.notify_channels:
        if name == "ntfy":
            if not cfg.ntfy_topics:
                log.warning("Kanál ntfy je zapnutý, ale chybí NTFY_TOPICS – vynechávám")
                continue
            channels.append(Channel(NtfyNotifier(cfg.ntfy_server, cfg.ntfy_token),
                                    list(cfg.ntfy_topics)))
        elif name == "sms":
            if cfg.sms_provider != "console":
                log.warning("SMS provider „%s“ zatím není implementovaný – používám console",
                            cfg.sms_provider)
            channels.append(Channel(ConsoleNotifier("sms"), list(cfg.sms_recipients) or ["test"]))
        elif name == "console":
            channels.append(Channel(ConsoleNotifier(), ["log"]))
        else:
            log.warning("Neznámý kanál „%s“ – vynechávám", name)
    return channels


def main() -> None:
    cfg = config.load()
    config.setup_logging(cfg.log_level)
    # Docker stops containers with SIGTERM – exit cleanly instead of being killed.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    conn = db.connect(cfg.db_path)
    client = SrealityClient(cfg.user_agent)
    channels = build_channels(cfg)
    log.info("Kanály: %s", ", ".join(f"{c.notifier.channel} ({len(c.recipients)} příjemců)"
                                       for c in channels) or "žádné")
    watcher = Watcher(conn, client, cfg, alerts=AlertEngine(conn, client, channels))
    try:
        watcher.run_forever()
    except (KeyboardInterrupt, SystemExit):
        log.info("Watcher končí.")


if __name__ == "__main__":
    main()
