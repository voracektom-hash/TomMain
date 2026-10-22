from dataclasses import replace
from datetime import datetime, timezone

import pytest

from conftest import load_fixture
from hlidac import db, medians
from hlidac.locations import gps_candidates, resolve_name, UnknownLocation
from hlidac.rules import Rule, check_detail, check_listing, load_rules, save_rule
from hlidac.sreality.parser import parse_detail, parse_search
from hlidac.text import find_keyword

NOW = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def praha(conn):
    _, listings = parse_search(load_fixture("search_praha.json"))
    db.upsert_listings(conn, listings, NOW, from_sweep=True)
    medians.compute(conn, NOW)
    return {l.id: l for l in listings}


@pytest.fixture
def flat(praha):
    return praha[1725177932]  # 3+1, 91 m², 15.95 M, Praha 2 Nové Město


@pytest.fixture
def detail():
    return parse_detail(load_fixture("detail_1725177932.json"))  # 2. NP, osobní


def rule(**kw):
    base = dict(name="t", location_type="quarter", location="Praha 2")
    base.update(kw)
    return Rule(**base)


# --- search-data criteria -----------------------------------------------------------------

def test_location_types(conn, flat):
    assert check_listing(conn, rule(), flat) is None
    assert check_listing(conn, rule(location_type="citypart", location="Nové Město"), flat) is None
    assert check_listing(conn, rule(location_type="city", location="Praha"), flat) is None
    assert check_listing(conn, rule(location="Praha 5"), flat) == "jiná lokalita"


@pytest.mark.parametrize("kw, passes", [
    ({"max_price": 16_000_000}, True),
    ({"max_price": 15_000_000}, False),
    ({"max_price_m2": 180_000}, True),
    ({"max_price_m2": 170_000}, False),
    ({"min_area": 90, "max_area": 95}, True),
    ({"min_area": 92}, False),
    ({"max_area": 80}, False),
    ({"dispositions": ["3+1", "3+kk"]}, True),
    ({"dispositions": ["2+kk"]}, False),
])
def test_search_criteria(conn, flat, kw, passes):
    assert (check_listing(conn, rule(**kw), flat) is None) is passes


def test_price_on_request_fails_price_rules(conn, flat):
    no_price = replace(flat, price_czk=None, price_m2=None)
    assert check_listing(conn, rule(), no_price) is None
    assert check_listing(conn, rule(max_price=20_000_000), no_price) == "cena na dotaz"


def test_below_median(conn, praha, flat):
    med = conn.execute("SELECT median_m2 FROM medians WHERE scope='city' AND location='Praha' "
                       "AND disposition=''").fetchone()[0]
    cheap = replace(flat, price_m2=int(med * 0.85), price_czk=1)
    r = rule(location_type="city", location="Praha", min_below_median=10)
    assert check_listing(conn, r, cheap) is None
    assert "pod mediánem" in check_listing(conn, r, replace(cheap, price_m2=int(med * 0.95)))


def test_below_median_without_data_fails(conn):
    _, listings = parse_search(load_fixture("search_praha.json"))
    db.upsert_listings(conn, listings[:1], NOW)  # one listing, no medians computed
    r = rule(min_below_median=5)
    assert check_listing(conn, r, listings[0]) == "medián není k dispozici"


# --- detail criteria ----------------------------------------------------------------------

@pytest.mark.parametrize("kw, passes", [
    ({"ownerships": ["osobní"]}, True),
    ({"ownerships": ["družstevní"]}, False),
    ({"no_ground_floor": True}, True),       # 2. NP
    ({"min_floor": 2}, True),
    ({"min_floor": 3}, False),
    ({"exclude_keywords": ["metro"]}, False),  # description mentions "metra"
    ({"exclude_keywords": ["dražba"]}, True),
])
def test_detail_criteria(flat, detail, kw, passes):
    assert (check_detail(rule(**kw), flat, detail) is None) is passes


def test_ground_floor(flat, detail):
    ground = replace(detail, floor=1)
    assert check_detail(rule(no_ground_floor=True), flat, ground) == "podlaží 1"
    assert check_detail(rule(no_ground_floor=True), flat, replace(detail, floor=-1)) is not None


def test_unknown_detail_values_pass(flat, detail):
    unknown = replace(detail, floor=None, ownership=None)
    assert check_detail(rule(min_floor=5, ownerships=["družstevní"]), flat, unknown) is None


# --- keywords -----------------------------------------------------------------------------

@pytest.mark.parametrize("text, found", [
    ("Prodej spoluvlastnického podílu 1/2", "podíl"),
    ("Byt v dražbě, nejnižší podání", "dražba"),
    ("Dražební vyhláška", "dražba"),
    ("Byt je pronajatý, nájemník platí včas", "nájemník"),
    ("Byt s nájemníkem", "nájemník"),
    ("Měsíční nájemné družstvu 3 500 Kč", None),   # must NOT match nájemník
    ("REZERVOVÁNO", "rezervováno"),
    ("Byt je rezervovaný", "rezervováno"),
    ("Krásný slunný byt po rekonstrukci", None),
])
def test_keywords(text, found):
    assert find_keyword(text, ["podíl", "dražba", "nájemník", "rezervováno"]) == found


# --- quiet mode ---------------------------------------------------------------------------

@pytest.mark.parametrize("utc_hour, quiet", [(19, False), (20, True), (2, True), (5, False)])
def test_quiet_over_midnight(utc_hour, quiet):
    # 22–7 Prague = 20–5 UTC in summer time (October 21 is still CEST).
    now = datetime(2026, 10, 21, utc_hour, 30, tzinfo=timezone.utc)
    assert rule(quiet_start=22, quiet_end=7).is_quiet(now) is quiet


def test_quiet_ends_next_morning():
    now = datetime(2026, 10, 21, 21, 0, tzinfo=timezone.utc)  # 23:00 Prague
    end = rule(quiet_start=22, quiet_end=7).quiet_ends_at(now)
    assert end.isoformat().startswith("2026-10-22T07:00")


def test_no_quiet_mode():
    assert not rule(quiet_start=None, quiet_end=None).is_quiet(NOW)


# --- storage and locations ----------------------------------------------------------------

def test_save_and_load_roundtrip(conn):
    r = rule(dispositions=["2+kk"], ownerships=["osobní"], price_drop_alert=True)
    save_rule(conn, r, NOW)
    save_rule(conn, replace(r, max_price=5_000_000), NOW)  # same name = update
    loaded = load_rules(conn)
    assert len(loaded) == 1
    assert loaded[0].max_price == 5_000_000
    assert loaded[0].dispositions == ["2+kk"]
    assert loaded[0].price_drop_alert is True


def test_resolve_location_names(conn, praha):
    assert resolve_name(conn, "praha 2") == ("quarter", "Praha 2")
    assert resolve_name(conn, "Smichov") == ("citypart", "Smíchov")
    assert resolve_name(conn, "PRAHA") == ("city", "Praha")
    with pytest.raises(UnknownLocation) as exc:
        resolve_name(conn, "Vinohr")
    assert "Vinohrady" in exc.value.suggestions


def test_gps_fills_missing_quarter(conn, praha, flat):
    # A listing a few metres from flat (Praha 2) but without quarter/citypart.
    lost = replace(flat, id=1, quarter=None, citypart=None, lat=flat.lat + 0.0003)
    assert gps_candidates(conn, lost, "quarter") == {"Praha 2"}
    assert check_listing(conn, rule(), lost) is None
    assert check_listing(conn, rule(location="Praha 9"), lost) == "jiná lokalita"


def test_gps_without_neighbours(conn, praha, flat):
    far = replace(flat, id=1, quarter=None, lat=49.0, lon=13.0)
    assert gps_candidates(conn, far, "quarter") == set()
