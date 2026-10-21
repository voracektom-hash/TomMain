import copy
import random
from datetime import datetime, timedelta, timezone

import pytest

from conftest import load_fixture
from hlidac import config, db, medians, schedule
from hlidac.sreality.client import RateLimited
from hlidac.sreality.parser import parse_search
from hlidac.watcher import Watcher

CFG = config.Config(db_path=":memory:", region_ids=(10, 11), page_limit=60,
                    user_agent="test", log_level="INFO")
# 2026-10-21 12:00 Prague time (a Wednesday).
NOON = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)


def page(items, total=None):
    data = copy.deepcopy(load_fixture("search_praha.json"))
    data["results"] = items
    data["pagination"]["total"] = len(items) if total is None else total
    return data


def items(n=None):
    return copy.deepcopy(load_fixture("search_praha.json"))["results"][:n]


class FakeClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def search(self, region_ids, offset, limit):
        self.calls.append((offset, limit))
        result = self.pages.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class Clock:
    def __init__(self, start):
        self.t = start

    def __call__(self):
        return self.t


def make(conn, pages, now=NOON):
    clock = Clock(now)
    w = Watcher(conn, FakeClient(pages), CFG, now=clock, sleep=lambda s: None,
                rng=random.Random(1))
    return w, clock


def test_initial_sweep_does_not_report_existing_listings(conn):
    all_items = items()
    w, _ = make(conn, [page(all_items), page(all_items)])
    w.step()
    assert conn.execute("SELECT COUNT(*) FROM listings WHERE from_sweep = 1").fetchone()[0] == 22
    last_poll = conn.execute("SELECT n_new FROM runs WHERE kind='poll'").fetchone()
    assert last_poll["n_new"] == 0


def test_new_listing_and_price_change(conn):
    all_items = items()
    w, clock = make(conn, [page(all_items)])
    w.sweep(initial=True)

    fresh = copy.deepcopy(all_items[0])
    fresh["hash_id"] = 999
    cheaper = copy.deepcopy(all_items[1])
    cheaper["price_czk"] = cheaper["price_czk"] - 1_000_000
    w.client.pages = [page([fresh, cheaper] + all_items[2:])]
    clock.t += timedelta(minutes=1)
    result = w.poll_once()

    assert [l.id for l in result.new] == [999]
    assert len(result.price_changes) == 1
    ch = result.price_changes[0]
    assert ch.old_price - ch.new_price == 1_000_000
    assert ch.percent < 0
    assert conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == 1


def test_catch_up_reads_next_page_when_nothing_known(conn):
    all_items = items()
    w, _ = make(conn, [page(all_items[:2])])
    w.sweep(initial=True)
    unknown = copy.deepcopy(all_items[2:12])
    w.client.pages = [page(unknown, total=100), page(all_items[:2] + all_items[12:], total=100)]
    result = w.poll_once()
    assert result.pages == 2
    assert w.client.calls[-1] == (60, 60)


def test_zero_results_is_an_error_and_backs_off(conn):
    w, _ = make(conn, [page(items(3)), page([], total=0)])
    w.sweep(initial=True)
    delay = w.step()
    assert w.failures == 1
    assert conn.execute("SELECT ok FROM runs ORDER BY id DESC").fetchone()["ok"] == 0
    assert delay >= 50


def test_rate_limit_slows_down(conn):
    w, _ = make(conn, [page(items(3)), RateLimited("HTTP 429")])
    w.sweep(initial=True)
    delay = w.step()
    assert w.slowdown_until is not None
    assert delay >= 50 * 5


def test_weekly_sweep_marks_removed(conn):
    all_items = items()
    w, clock = make(conn, [page(all_items)])
    w.sweep(initial=True)
    clock.t = datetime(2026, 10, 29, 1, 0, tzinfo=timezone.utc)  # 03:00 Prague, 8 days later
    assert w.sweep_due()
    w.client.pages = [page(all_items[1:])]
    w.sweep(initial=False)
    removed = conn.execute("SELECT id FROM listings WHERE removed_at IS NOT NULL").fetchall()
    assert [r["id"] for r in removed] == [all_items[0]["hash_id"]]


@pytest.mark.parametrize("utc_hour, expected", [
    (10, 60),   # 12:00 Prague
    (20, 180),  # 22:00
    (0, 600),   # 02:00
    (4, 180),   # 06:00
    (5, 60),    # 07:00
])
def test_default_schedule(utc_hour, expected):
    now = datetime(2026, 10, 21, utc_hour, 0, tzinfo=timezone.utc)
    assert schedule.base_interval(now, None) == expected


def test_learned_schedule(conn):
    start = NOON - timedelta(days=20)
    db.record_run(conn, "poll", start, start, True)
    # Plenty of new listings at 12:00 on weekdays, none at 13:00.
    day = start
    n = 0
    while day < NOON:
        local_noon = day.astimezone(schedule.TZ).replace(hour=12, minute=5)
        if local_noon.weekday() < 5:
            for _ in range(5):
                n += 1
                conn.execute(
                    "INSERT INTO listings (id, name, first_seen, last_seen) VALUES (?,?,?,?)",
                    (n, "x", db.ts(local_noon), db.ts(local_noon)))
        day += timedelta(days=1)
    rates = schedule.learn_rates(conn, NOON)
    assert rates is not None
    assert rates[(False, 12)] >= 4
    assert schedule.base_interval(NOON, rates) == 60
    assert schedule.base_interval(NOON + timedelta(hours=1), rates) == 600


def test_learned_schedule_needs_14_days(conn):
    db.record_run(conn, "poll", NOON - timedelta(days=3), NOON, True)
    assert schedule.learn_rates(conn, NOON) is None


def test_jitter_bounds():
    rng = random.Random(0)
    values = [schedule.with_jitter(60, rng) for _ in range(200)]
    assert min(values) >= 50 and max(values) <= 70


def test_medians(conn):
    _, praha = parse_search(load_fixture("search_praha.json"))
    db.upsert_listings(conn, praha, NOON, from_sweep=True)
    n = medians.compute(conn, NOON)
    assert n > 0
    row = conn.execute("SELECT median_m2, n FROM medians WHERE scope='city' AND location='Praha'"
                       " AND disposition=''").fetchone()
    assert row["n"] == 21  # 22 listings, one with price on request
    assert 100_000 < row["median_m2"] < 300_000
