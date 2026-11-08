import copy
from datetime import datetime, timedelta, timezone

import pytest

from conftest import load_fixture
from hlidac import db
from hlidac import users
from hlidac.alerts import AlertEngine
from hlidac.notify.base import NotifyError
from hlidac.rules import Rule, save_rule
from hlidac.sreality.parser import ParseError, parse_search

NOON = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)   # 12:00 Prague
NIGHT = datetime(2026, 10, 21, 21, 0, tzinfo=timezone.utc)  # 23:00 Prague


class FakeNotifier:
    def __init__(self, channel="ntfy", fail=0):
        self.channel = channel
        self.sent = []
        self.fail = fail

    def send(self, recipient, message):
        if self.fail:
            self.fail -= 1
            raise NotifyError("down")
        self.sent.append((recipient, message))


class FakeClient:
    def __init__(self):
        self.detail_calls = 0

    def detail(self, listing_id):
        self.detail_calls += 1
        data = copy.deepcopy(load_fixture("detail_1725177932.json"))
        data["result"]["hash_id"] = listing_id
        return data


@pytest.fixture
def listings(conn):
    _, ls = parse_search(load_fixture("search_praha.json"))
    db.upsert_listings(conn, ls, NOON, from_sweep=True)
    return ls


@pytest.fixture
def owner(conn):
    user, _ = users.create_user(conn, "Tomas", admin=True, topic="topic", priority=4)
    return user


@pytest.fixture
def setup(conn, owner):
    ntfy = FakeNotifier("ntfy")
    log = FakeNotifier("console")
    client = FakeClient()
    engine = AlertEngine(conn, client, {"ntfy": ntfy, "console": log})
    return engine, ntfy, log, client


def add_rule(conn, **kw):
    base = dict(name="Praha 2", location_type="quarter", location="Praha 2", user_id=1)
    base.update(kw)
    save_rule(conn, Rule(**base), NOON)


def test_match_queues_and_sends_to_all_channels(conn, listings, setup):
    engine, ntfy, log, client = setup
    add_rule(conn)
    praha2 = [l for l in listings if l.quarter == "Praha 2"]
    assert engine.process(praha2, [], NOON) == 2 * len(praha2)
    assert client.detail_calls == len(praha2)
    engine.dispatch(NOON)
    assert len(ntfy.sent) == len(praha2)
    assert ntfy.sent[0][0] == "topic"
    assert ntfy.sent[0][1].priority == 4          # the owner's priority
    assert log.sent[0][0] == "log:Tomas"
    row = conn.execute("SELECT status, rule_names FROM alerts LIMIT 1").fetchone()
    assert row["status"] == "sent" and row["rule_names"] == "Praha 2"


def test_no_rules_no_detail_requests(conn, listings, setup):
    engine, _, _, client = setup
    assert engine.process(listings, [], NOON) == 0
    assert client.detail_calls == 0


def test_non_matching_listing_skips_detail(conn, listings, setup):
    engine, _, _, client = setup
    add_rule(conn, location="Praha 22")
    engine.process(listings, [], NOON)
    assert client.detail_calls == sum(l.quarter == "Praha 22" for l in listings)


def test_one_alert_per_listing_even_with_two_rules(conn, listings, setup):
    engine, ntfy, _, _ = setup
    add_rule(conn, name="A")
    add_rule(conn, name="B", location_type="city", location="Praha")
    flat = listings[0]
    engine.process([flat], [], NOON)
    engine.process([flat], [], NOON)  # seen again → no duplicate
    engine.dispatch(NOON)
    assert len(ntfy.sent) == 1
    assert "Pravidlo: A, B" in ntfy.sent[0][1].body


def test_detail_criteria_reject(conn, listings, setup):
    engine, ntfy, _, _ = setup
    add_rule(conn, min_floor=5)  # fixture detail is 2. NP
    engine.process([listings[0]], [], NOON)
    engine.dispatch(NOON)
    assert ntfy.sent == []


def test_quiet_mode_defers_to_morning(conn, listings, setup):
    engine, ntfy, _, _ = setup
    add_rule(conn, quiet_start=22, quiet_end=7, quiet_action="defer")
    engine.process([listings[0]], [], NIGHT)
    engine.dispatch(NIGHT)
    assert ntfy.sent == []
    morning = datetime(2026, 10, 22, 5, 1, tzinfo=timezone.utc)  # 07:01 Prague
    engine.dispatch(morning)
    assert len(ntfy.sent) == 1


def test_quiet_mode_drop(conn, listings, setup):
    engine, ntfy, _, _ = setup
    add_rule(conn, quiet_start=22, quiet_end=7, quiet_action="drop")
    engine.process([listings[0]], [], NIGHT)
    engine.dispatch(NIGHT + timedelta(hours=12))
    assert ntfy.sent == []
    assert conn.execute("SELECT DISTINCT status FROM alerts").fetchone()[0] == "dropped"


def test_price_drop_alert_once_per_price(conn, listings, setup):
    engine, ntfy, _, _ = setup
    add_rule(conn, price_drop_alert=True)
    flat = listings[0]
    drop = db.PriceChange(flat, 17_000_000, flat.price_czk)
    engine.process([], [drop], NOON)
    engine.process([], [drop], NOON)
    rise = db.PriceChange(flat, 15_000_000, flat.price_czk)
    engine.process([], [rise], NOON)  # price went up → no alert
    engine.dispatch(NOON)
    assert len(ntfy.sent) == 1
    assert ntfy.sent[0][1].title.startswith("SLEVA")


def test_price_drop_needs_rule_flag(conn, listings, setup):
    engine, ntfy, _, _ = setup
    add_rule(conn, price_drop_alert=False)
    engine.process([], [db.PriceChange(listings[0], 17_000_000, 15_950_000)], NOON)
    engine.dispatch(NOON)
    assert ntfy.sent == []


def test_failed_send_is_retried(conn, listings, setup):
    engine, _, _, _ = setup
    flaky = FakeNotifier("ntfy", fail=1)
    engine.notifiers = {"ntfy": flaky}
    add_rule(conn)
    engine.process([listings[0]], [], NOON)
    assert engine.dispatch(NOON) == 0
    assert engine.dispatch(NOON + timedelta(minutes=1)) == 0  # backoff 2 min
    assert engine.dispatch(NOON + timedelta(minutes=3)) == 1
    assert len(flaky.sent) == 1


# --- watchdog -----------------------------------------------------------------------------

def test_watchdog_silent_while_polling_works(conn, setup):
    engine, ntfy, _, _ = setup
    db.record_run(conn, "poll", NOON - timedelta(minutes=1), NOON, True)
    engine.watchdog(NOON, None, 60)
    assert ntfy.sent == []


def test_watchdog_alarm_once_per_hour_then_recovery(conn, setup):
    engine, ntfy, _, _ = setup
    db.record_run(conn, "poll", NOON - timedelta(minutes=30), NOON, True)
    engine.watchdog(NOON, ConnectionError("timeout"), 60)
    engine.watchdog(NOON + timedelta(minutes=20), ConnectionError("timeout"), 60)
    assert len(ntfy.sent) == 1
    assert "30 min" in ntfy.sent[0][1].body
    engine.watchdog(NOON + timedelta(minutes=61), ConnectionError("timeout"), 60)
    assert len(ntfy.sent) == 2
    db.record_run(conn, "poll", NOON + timedelta(minutes=62), NOON, True)
    engine.watchdog(NOON + timedelta(minutes=62), None, 60)
    assert "zase funguje" in ntfy.sent[-1][1].body


def test_watchdog_parse_error_is_immediate(conn, setup):
    engine, ntfy, _, _ = setup
    db.record_run(conn, "poll", NOON - timedelta(minutes=1), NOON, True)
    engine.watchdog(NOON, ParseError("results missing"), 60)
    assert "změna API" in ntfy.sent[0][1].body


def test_watchdog_tolerates_slow_night_interval(conn, setup):
    engine, ntfy, _, _ = setup
    db.record_run(conn, "poll", NOON - timedelta(minutes=12), NOON, True)
    engine.watchdog(NOON, None, 600)  # 10-min interval at night: 12 min gap is fine
    assert ntfy.sent == []


def test_watchdog_no_false_recovery_while_still_dead(conn, setup):
    engine, ntfy, _, _ = setup
    db.record_run(conn, "poll", NOON - timedelta(minutes=40), NOON, True)
    engine.watchdog(NOON, None, 600)            # web app check: 40 min > 25 min → alarm
    engine.watchdog(NOON + timedelta(minutes=5), None, 600)
    assert len(ntfy.sent) == 1
    assert "zase funguje" not in ntfy.sent[0][1].body


def test_two_users_same_flat_each_gets_own_alert(conn, listings, setup):
    engine, ntfy, _, _ = setup
    friend, _ = users.create_user(conn, "Petr", topic="petr-topic", priority=5)
    add_rule(conn, name="Moje")
    add_rule(conn, name="Petrovo", user_id=friend.id)
    engine.process([listings[0]], [], NOON)
    engine.process([listings[0]], [], NOON)  # no duplicates per user
    engine.dispatch(NOON)
    by_topic = {t: m for t, m in ntfy.sent}
    assert set(by_topic) == {"topic", "petr-topic"}
    assert "Pravidlo: Moje" in by_topic["topic"].body
    assert "Pravidlo: Petrovo" in by_topic["petr-topic"].body
    assert by_topic["petr-topic"].priority == 5   # friend wants the highest priority


def test_service_messages_go_to_admins_only(conn, setup):
    engine, ntfy, _, _ = setup
    users.create_user(conn, "Petr", topic="petr-topic")
    db.record_run(conn, "poll", NOON - timedelta(hours=1), NOON, True)
    engine.watchdog(NOON, ConnectionError("x"), 60)
    assert [t for t, _ in ntfy.sent] == ["topic"]


def test_user_without_topic_gets_nothing_on_ntfy(conn, listings, setup):
    engine, ntfy, log, _ = setup
    users.update_user(conn, 1, topic=None, priority=4)
    add_rule(conn)
    engine.process([listings[0]], [], NOON)
    engine.dispatch(NOON)
    assert ntfy.sent == [] and len(log.sent) == 1
