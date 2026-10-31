import pytest

from conftest import load_fixture
from hlidac.sreality.parser import ParseError, parse_area, parse_detail, parse_search


def test_search_praha():
    total, listings = parse_search(load_fixture("search_praha.json"))
    assert total == 6045
    assert len(listings) == 22
    first = listings[0]
    assert first.id == 1725177932
    assert first.disposition == "3+1"
    assert first.area_m2 == 91
    assert first.price_czk == 15_950_000
    assert first.price_m2 == 175_275
    assert first.region_id == 10
    assert first.quarter == "Praha 2"
    assert first.citypart == "Nové Město"
    assert first.city == "Praha"
    assert not first.is_private
    assert first.url == "https://www.sreality.cz/detail/prodej/byt/2+kk/x/1725177932"


def test_search_praha_quarter_differs_from_old_district():
    _, listings = parse_search(load_fixture("search_praha.json"))
    chodov = next(l for l in listings if l.citypart == "Chodov")
    assert chodov.district == "Praha 4"
    assert chodov.quarter == "Praha 11"


def test_search_stredocesky_uses_city():
    total, listings = parse_search(load_fixture("search_stredocesky.json"))
    assert total == 2225
    assert all(l.region_id == 11 for l in listings)
    assert all(l.quarter is None for l in listings)
    assert listings[0].city == "Mladá Boleslav"


def test_missing_quarter_is_none():
    _, listings = parse_search(load_fixture("search_edge_cases.json"))
    vinohrady = listings[0]
    assert vinohrady.citypart == "Vinohrady"
    assert vinohrady.quarter is None  # quarter_id == -1


def test_private_seller_price_on_request():
    _, listings = parse_search(load_fixture("search_edge_cases.json"))
    private = listings[1]
    assert private.is_private
    assert private.price_czk is None
    assert private.price_m2 is None
    assert private.area_m2 == 82


@pytest.mark.parametrize("name, area", [
    ("Prodej bytu 2+kk 54 m²", 54),
    ("Prodej bytu 3+kk 151 m²", 151),
    ("Prodej bytu 1+kk 27,5 m²", 27.5),
    ("Prodej bytu atypický", None),
])
def test_parse_area(name, area):
    assert parse_area(name) == area


def test_detail():
    d = parse_detail(load_fixture("detail_1725177932.json"))
    assert d.id == 1725177932
    assert d.since == "2026-10-02"
    assert d.floor == 2
    assert d.floors_total == 7
    assert d.ownership == "Osobní"
    assert d.broker_name == "Ing. Jan Novák"
    assert d.broker_phone == "+420777123456"
    assert d.agency == "Bydlení a Reality s.r.o."
    assert "metra" in d.description


def test_detail_not_found_raises():
    with pytest.raises(ParseError):
        parse_detail(load_fixture("detail_not_found.json"))


@pytest.mark.parametrize("payload", [
    {"status_code": 422, "status_message": "Invalid arguments"},
    {"status_code": 200, "results": "nope", "pagination": {"total": 1}},
    {"status_code": 200, "results": [{"hash_id": 1}], "pagination": {"total": 1}},
    [],
])
def test_broken_search_raises(payload):
    with pytest.raises(ParseError):
        parse_search(payload)


def test_placeholder_price_is_price_on_request():
    data = load_fixture("search_edge_cases.json")
    data["results"][1]["price_czk"] = 1.0
    _, listings = parse_search(data)
    assert listings[1].price_czk is None
    assert listings[1].price_m2 is None
