from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import load_fixture
from hlidac import config, db, medians, rules
from hlidac.sreality.parser import parse_search
from hlidac.web.app import create_app


@pytest.fixture
def cfg(tmp_path: Path):
    return config.Config(db_path=tmp_path / "t.db", region_ids=(10, 11), page_limit=60,
                         user_agent="test", log_level="INFO", notify_channels=("console",))


@pytest.fixture
def client(cfg):
    conn = db.connect(cfg.db_path)
    now = db.utcnow()
    _, praha = parse_search(load_fixture("search_praha.json"))
    _, stc = parse_search(load_fixture("search_stredocesky.json"))
    db.upsert_listings(conn, praha + stc, now - timedelta(days=1), from_sweep=True)
    # three "new" listings seen by polling yesterday
    _, edge = parse_search(load_fixture("search_edge_cases.json"))
    db.upsert_listings(conn, edge, now - timedelta(hours=5))
    db.record_run(conn, "poll", now - timedelta(minutes=1), now, True)
    medians.compute(conn, now)
    conn.close()
    with TestClient(create_app(cfg, start_watchdog=False)) as c:
        yield c


def form(**kw):
    data = {"name": "Vinohrady", "location": "Vinohrady", "active": "1",
            "exclude_keywords": "podíl, dražba", "quiet_on": "1", "quiet_start": "22",
            "quiet_end": "7", "quiet_action": "defer"}
    data.update(kw)
    return data


def test_pages_render(client):
    for url in ["/", "/rules/new", "/alerts", "/status", "/medians", "/medians?scope=city",
                "/settings", "/healthz", "/static/manifest.webmanifest", "/sw.js"]:
        r = client.get(url)
        assert r.status_code == 200, url


def test_empty_rules_page_invites_first_rule(client):
    assert "Vytvořit první pravidlo" in client.get("/").text


def test_create_edit_duplicate_toggle_delete(client, cfg):
    r = client.post("/rules/save", data=form(max_price_m="12,5", max_price_m2_k="200",
                                             dispositions=["2+kk", "3+kk"]),
                    follow_redirects=False)
    assert r.status_code == 303
    conn = db.connect(cfg.db_path)
    rule = rules.load_rules(conn)[0]
    assert rule.location_type == "citypart" and rule.location == "Vinohrady"
    assert rule.max_price == 12_500_000 and rule.max_price_m2 == 200_000
    assert rule.dispositions == ["2+kk", "3+kk"]
    assert (rule.quiet_start, rule.quiet_end) == (22, 7)

    page = client.get("/").text
    assert "Vinohrady" in page and "do 12,50 M Kč" in page

    # edit: rename + drop quiet mode
    r = client.post("/rules/save", data=form(id=str(rule.id), name="Vinohrady 2", quiet_on=""),
                    follow_redirects=False)
    assert r.status_code == 303
    edited = rules.get_rule(conn, rule.id)
    assert edited.name == "Vinohrady 2" and edited.quiet_start is None

    dup = client.get(f"/rules/{rule.id}/duplicate").text
    assert "Vinohrady 2 (kopie)" in dup and 'name="id"' not in dup

    card = client.post(f"/rules/{rule.id}/toggle").text
    assert 'class="card rule off"' in card
    assert rules.get_rule(conn, rule.id).active is False

    client.post(f"/rules/{rule.id}/delete")
    assert rules.load_rules(conn, active_only=False) == []


def test_validation_errors(client):
    r = client.post("/rules/save", data=form(name="", location="Vinohr", max_area="abc"))
    assert r.status_code == 422
    assert "Pravidlo potřebuje název." in r.text
    assert "Neznámá lokalita" in r.text and "Vinohrady" in r.text
    assert "Zadej číslo." in r.text


def test_duplicate_name_rejected(client):
    client.post("/rules/save", data=form())
    r = client.post("/rules/save", data=form())
    assert r.status_code == 422
    assert "už existuje" in r.text


def test_preview(client):
    r = client.post("/rules/preview", data=form(name=""))
    assert r.status_code == 200
    # the Vinohrady edge-case listing was "new" 5 h ago and has no detail → "možná"
    assert "možná" in r.text
    assert "727322700" in r.text
    r = client.post("/rules/preview", data=form(location="xyz"))
    assert "Neznámá lokalita" in r.text


def test_location_autocomplete(client):
    r = client.get("/locations", params={"location": "smi"})
    assert '<option value="Smíchov">' in r.text
    r = client.get("/locations", params={"q": "praha 1"})
    assert 'value="Praha 1"' in r.text


def test_settings_roundtrip_and_validation(client):
    r = client.post("/settings", data={"ch_ntfy": "1", "ntfy_topics": "hlidac-abc\nhlidac-def",
                                       "sms_recipients": "+420 777 123 456"})
    assert r.status_code == 200 and "Uloženo" in r.text
    page = client.get("/settings").text
    assert "hlidac-abc\nhlidac-def" in page and "+420777123456" in page
    r = client.post("/settings", data={"ntfy_topics": "bad topic!", "sms_recipients": "abc"})
    assert r.status_code == 422
    assert "Neplatný název kanálu" in r.text and "Neplatné číslo" in r.text


def test_test_notification_console(client):
    client.post("/settings", data={"ch_console": "1"})
    r = client.post("/settings/test")
    assert "Odesláno 1 z 1." in r.text
    assert "Servis" in client.get("/alerts").text


def test_test_notification_without_channels(client):
    client.post("/settings", data={})
    assert "Žádný kanál" in client.post("/settings/test").text


def test_status_page(client):
    text = client.get("/status").text
    assert "Hlídač běží" in text


def test_medians_page(client):
    # The 22-listing fixture only has enough samples (≥ 5) for a few locations.
    text = client.get("/medians?scope=city").text
    assert "<td>Praha</td>" in text
    assert "Žádná data" not in text
    assert "Žádná data" in client.get("/medians?scope=city&q=nic-takoveho").text


def test_password(cfg, monkeypatch):
    monkeypatch.setenv("WEB_PASSWORD", "tajne")
    with TestClient(create_app(cfg, start_watchdog=False)) as c:
        assert c.get("/").status_code == 401
        assert c.get("/healthz").status_code == 200
        assert c.get("/", auth=("x", "tajne")).status_code == 200
        assert c.get("/", auth=("x", "spatne")).status_code == 401
