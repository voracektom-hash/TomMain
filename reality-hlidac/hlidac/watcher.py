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
from hlidac.sreality.client import RateLimited, SrealityClient, SrealityError
from hlidac.sreality.parser import Listing, ParseError, parse_search

log = logging.getLogger("hlidac")

MAX_PAGES_PER_POLL = 5        # catch-up limit when a page has no known listing
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
                 rng: random.Random | None = None):
        self.conn = conn
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

    # --- one poll -------------------------------------------------------------------------

    def poll_once(self) -> PollResult:
        started = self.now()
        result = PollResult(0, [], [], 0)
        sweep_done = db.get_meta(self.conn, "sweep_done") is not None
        try:
            for page in range(MAX_PAGES_PER_POLL):
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
                # Some listing on this page was already known -> we have caught up.
                if up.known_count or not sweep_done:
                    break
            else:
                log.warning("Ani po %d stránkách žádný známý inzerát – část nových mohla uniknout",
                            MAX_PAGES_PER_POLL)
        except Exception as exc:
            db.record_run(self.conn, "poll", started, self.now(), False, pages=result.pages,
                          error=f"{type(exc).__name__}: {exc}")
            raise
        db.record_run(self.conn, "poll", started, self.now(), True,
                      n_results=result.n_results, n_new=len(result.new),
                      n_price_changes=len(result.price_changes), pages=result.pages)
        return result

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
        delay = schedule.with_jitter(schedule.base_interval(now, self.rates), self.rng)
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
        try:
            if self.sweep_due():
                first = db.get_meta(self.conn, "sweep_done") is None
                self.sweep(initial=first)
            result = self.poll_once()
            self.failures = 0
            for l in result.new:
                log.info("Nový: %s", describe(l))
            for ch in result.price_changes:
                log.info("Změna ceny: %s → %s (%+.1f %%) | %s", fmt_price(ch.old_price),
                         fmt_price(ch.new_price), ch.percent, describe(ch.listing))
            self.maybe_compute_medians()
        except RateLimited as exc:
            self.failures += 1
            self.slowdown_until = self.now() + SLOWDOWN_FOR
            log.warning("Sreality nás brzdí (%s) – zpomaluji %d× na %d min",
                        exc, SLOWDOWN_FACTOR, SLOWDOWN_FOR.seconds // 60)
        except ParseError as exc:
            self.failures += 1
            log.error("Odpověď Sreality má nečekaný tvar – možná změna API: %s", exc)
        except SrealityError as exc:
            self.failures += 1
            log.warning("Chyba spojení se Sreality (%d. v řadě): %s", self.failures, exc)

        delay = self.next_delay()
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


def main() -> None:
    cfg = config.load()
    config.setup_logging(cfg.log_level)
    # Docker stops containers with SIGTERM – exit cleanly instead of being killed.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    conn = db.connect(cfg.db_path)
    watcher = Watcher(conn, SrealityClient(cfg.user_agent), cfg)
    try:
        watcher.run_forever()
    except (KeyboardInterrupt, SystemExit):
        log.info("Watcher končí.")


if __name__ == "__main__":
    main()
