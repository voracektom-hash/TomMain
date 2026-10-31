from dataclasses import replace

import pytest

from conftest import load_fixture
from hlidac.notify.format import (SMS_MAX_LEN, agency_short, broker_short, listing_message,
                                  phone_short, sms_segments, sms_text)
from hlidac.notify.ntfy import NtfyNotifier
from hlidac.sreality.parser import parse_detail, parse_search


@pytest.fixture
def flat():
    _, listings = parse_search(load_fixture("search_praha.json"))
    return listings[0]  # 3+1 91 m² Praha 2 Nové Město, 15.95 M, 175 275 Kč/m²


@pytest.fixture
def detail():
    return parse_detail(load_fixture("detail_1725177932.json"))


def test_sms_format(flat, detail):
    text = sms_text(flat, detail, below=12.3)
    assert text == ("P2-Nove Mesto 3+1 91m2 2.NP OV15.95M (175k/m2, -12% med) "
                    "J.Novak Bydleni a Real 777123456 "
                    "https://sreality.cz/detail/prodej/byt/2+kk/x/1725177932")
    assert text.isascii()
    assert sms_segments(text) <= 2


def test_sms_above_median_and_price_drop(flat, detail):
    text = sms_text(flat, detail, below=-4, drop_pct=-8.2)
    assert text.startswith("SLEVA -8% P2-Nove Mesto")
    assert "+4% med" in text


def test_sms_without_detail_private(flat):
    private = replace(flat, premise_id=None, price_czk=None, price_m2=None)
    text = sms_text(private, None, below=None)
    assert "cena?" in text and "soukromy" in text


def test_sms_too_long_drops_contact_first(flat, detail):
    long_place = replace(flat, citypart="X" * 200)
    text = sms_text(long_place, replace(detail, broker_name="Jan " + "Y" * 80), below=1)
    assert len(text) <= SMS_MAX_LEN
    assert text.endswith("/1725177932")


def test_stredocesky_location(detail):
    _, listings = parse_search(load_fixture("search_stredocesky.json"))
    assert sms_text(listings[0], detail, None).startswith("Mlada Boleslav-Mlada Boleslav II 2+kk")


@pytest.mark.parametrize("name, short", [
    ("Bc. Jana Kuželíková", "J.Kuzelikova"),
    ("Ing. arch. Petr Novák, MBA", "P.Novak"),
    ("Mgr. Šárka Dvořáková Ph.D.", "S.Dvorakova"),
    ("Novák", "Novak"),
    ("Matoušková Veronika", "V.Matouskova"),
    (None, None),
])
def test_broker_short(name, short):
    assert broker_short(name) == short


@pytest.mark.parametrize("name, short", [
    ("Bydlení a Reality s.r.o.", "Bydleni a Real"),
    ("RE/MAX Alfa", "RE/MAX Alfa"),
    ("M&M reality holding a.s.", "M&M reality ho"),
])
def test_agency_short(name, short):
    assert agency_short(name) == short


@pytest.mark.parametrize("phone, short", [
    ("+420724037592", "724037592"), ("724 037 592", "724037592"), (None, None)])
def test_phone_short(phone, short):
    assert phone_short(phone) == short


def test_segments():
    assert sms_segments("a" * 160) == 1
    assert sms_segments("a" * 161) == 2
    assert sms_segments("a" * 306) == 2
    assert sms_segments("a" * 307) == 3


def test_push_message(flat, detail):
    m = listing_message(flat, detail, (12.3, "Praha 2 3+1"), ["Centrum"])
    assert m.title == "3+1 91 m² · P2 Nové Město"
    assert "15,95 M Kč · 175 275 Kč/m² · 12 % pod mediánem (Praha 2 3+1)" in m.body
    assert "2. NP z 7 · osobní · vloženo 2. 10." in m.body
    assert "Pravidlo: Centrum" in m.body
    assert m.url.endswith("/1725177932")
    assert m.image_url.startswith("https://d18-a.sdn.cz/")
    assert m.phone == "+420777123456"


def test_push_price_drop_title(flat, detail):
    m = listing_message(flat, detail, None, ["x"], drop=(17_000_000, 15_950_000))
    assert m.title.startswith("SLEVA -6 % · ")
    assert "17,00 M Kč → 15,95 M Kč" in m.body


def test_ntfy_payload(flat, detail):
    m = listing_message(flat, detail, None, ["x"])
    p = NtfyNotifier().payload("moje-tema", m)
    assert p["topic"] == "moje-tema"
    assert p["click"] == m.url
    assert p["attach"] == m.image_url
    assert {"action": "view", "label": "Zavolat", "url": "tel:+420777123456"} in p["actions"]
