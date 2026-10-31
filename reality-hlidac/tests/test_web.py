import re
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import load_fixture
from hlidac import config, db, medians, rules, users
from hlidac.sreality.parser import parse_search
from hlidac.web.app import create_app


@pytest.fixture
def cfg(tmp_path: Path):
    return config.Config(db_path=tmp_path / "t.db", region_ids=(10, 11), page_limit=60,
                         user_agent="test", log_level="INFO", notify_channels=("console",))


@pytest.fixture
def passwords(cfg):
    conn = db.connect(cfg.db_path)
    now = db.utcnow()
    _, praha = parse_search(load_fixture("search_praha.json"))
    _, stc = parse_search(load_fixture("search_stredocesky.json"))
    db.upsert_listings(conn, praha + stc, now - timedelta(days=1), from_sweep=True)
    _, edge = parse_search(load_fixture("search_edge_cases.json"))
    db.upsert_listings(conn, edge, now - timedelta(hours=5))  # "new" listings
    db.record_run(conn, "poll", now - timedelta(minutes=1), now, True)
    medians.compute(conn, now)
    _, admin_pw = users.create_user(conn, "Tomas", admin=True, topic="hlidac-tomas")
    _, friend_pw = users.create_user(conn, "Petr", topic="hlidac-petr", priority=5)
    conn.close()
    return {"Tomas": admin_pw, "Petr": friend_pw}


def login(c: TestClient, name: str, password: str):
    return c.post("/login", data={"name": name, "password": password}, follow_redirects=False)


@pytest.fixture
def app(cfg, passwords):
    return create_app(cfg, start_watchdog=False)


@pytest.fixture
def client(app, passwords):
    with TestClient(app) as c:
        assert login(c, "Tomas", passwords["Tomas"]).status_code == 303
        yield c


@pytest.fixture
def friend(app, passwords):
    with TestClient(app) as c:
        assert login(c, "petr", passwords["Petr"]).status_code == 303  # name is case-insensitive
        yield c


def form(**kw):
    data = {"name": "Vinohrady", "location": "Vinohrady", "active": "1",
            "exclude_keywords": "podíl, dražba", "quiet_on": "1", "quiet_start": "22",
            "quiet_end": "7", "quiet_action": "defer"}
    data.update(kw)
    return data


# --- login ----------------------------------------------------------------------------------

def test_login_required(app):
    with TestClient(app) as c:
        r = c.get("/", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"
        assert c.get("/healthz").status_code == 200
        assert c.get("/static/manifest.webmanifest").status_code == 200
        assert c.post("/rules/preview", headers={"HX-Request": "true"}).headers["HX-Redirect"] == "/login"


def test_wrong_password_and_lockout(app, passwords):
    with TestClient(app) as c:
        for _ in range(5):
            r = login(c, "Tomas", "spatne")
            assert r.status_code == 401 and "Špatné jméno nebo heslo" in r.text
        r = login(c, "Tomas", passwords["Tomas"])  # even the right password is blocked now
        assert r.status_code == 429


def test_session_cookie_flags(app, passwords):
    with TestClient(app) as c:
        r = login(c, "Tomas", passwords["Tomas"])
        cookie = r.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=31536000" in cookie


def test_tampered_cookie_rejected(app, passwords):
    with TestClient(app) as c:
        login(c, "Petr", passwords["Petr"])
        value = c.cookies.get("hlidac_session")
        user_id, rest = value.split(".", 1)
        c.cookies.set("hlidac_session", f"1.{rest}")  # try to become user 1 (admin)
        assert c.get("/", follow_redirects=False).status_code == 303


def test_logout(client):
    client.post("/logout")
    assert client.get("/", follow_redirects=False).status_code == 303


def test_no_users_shows_setup_hint(tmp_path):
    cfg = config.Config(db_path=tmp_path / "empty.db", region_ids=(10,), page_limit=60,
                        user_agent="t", log_level="INFO")
    with TestClient(create_app(cfg, start_watchdog=False)) as c:
        assert "python -m hlidac.users add" in c.get("/login").text


# --- pages and rules ------------------------------------------------------------------------

def test_pages_render(client):
    for url in ["/", "/rules/new", "/alerts", "/status", "/medians", "/medians?scope=city",
                "/settings", "/sw.js"]:
        r = client.get(url)
        assert r.status_code == 200, url
    assert "Tomas" in client.get("/").text


def test_create_edit_duplicate_toggle_delete(client, cfg):
    r = client.post("/rules/save", data=form(max_price_m="12,5", max_price_m2_k="200",
                                             dispositions=["2+kk", "3+kk"]),
                    follow_redirects=False)
    assert r.status_code == 303
    conn = db.connect(cfg.db_path)
    rule = rules.load_rules(conn)[0]
    assert rule.user_id == 1
    assert rule.location_type == "citypart" and rule.location == "Vinohrady"
    assert rule.max_price == 12_500_000 and rule.max_price_m2 == 200_000
    assert rule.dispositions == ["2+kk", "3+kk"]

    r = client.post("/rules/save", data=form(id=str(rule.id), name="Vinohrady 2", quiet_on=""),
                    follow_redirects=False)
    assert r.status_code == 303
    edited = rules.get_rule(conn, rule.id)
    assert edited.name == "Vinohrady 2" and edited.quiet_start is None and edited.user_id == 1

    dup = client.get(f"/rules/{rule.id}/duplicate").text
    assert "Vinohrady 2 (kopie)" in dup and 'name="id"' not in dup

    assert 'class="card rule off"' in client.post(f"/rules/{rule.id}/toggle").text
    client.post(f"/rules/{rule.id}/delete")
    assert rules.load_rules(conn, active_only=False) == []


def test_users_see_only_their_rules(client, friend, cfg):
    client.post("/rules/save", data=form(name="Tomasovo"))
    friend.post("/rules/save", data=form(name="Petrovo"))
    assert "Tomasovo" in client.get("/").text and "Petrovo" not in client.get("/").text
    assert "Petrovo" in friend.get("/").text and "Tomasovo" not in friend.get("/").text

    conn = db.connect(cfg.db_path)
    tomas_rule = next(r for r in rules.load_rules(conn) if r.name == "Tomasovo")
    # the friend cannot open, toggle, overwrite or delete someone else's rule
    assert "Tomasovo" not in friend.get(f"/rules/{tomas_rule.id}").text
    assert friend.post(f"/rules/{tomas_rule.id}/toggle").status_code == 404
    friend.post("/rules/save", data=form(id=str(tomas_rule.id), name="hacked"))
    friend.post(f"/rules/{tomas_rule.id}/delete")
    assert rules.get_rule(conn, tomas_rule.id).name == "Tomasovo"


def test_same_rule_name_allowed_for_different_users(client, friend):
    assert client.post("/rules/save", data=form(), follow_redirects=False).status_code == 303
    assert friend.post("/rules/save", data=form(), follow_redirects=False).status_code == 303
    r = client.post("/rules/save", data=form())
    assert r.status_code == 422 and "už máš" in r.text


def test_validation_errors(client):
    r = client.post("/rules/save", data=form(name="", location="Vinohr", max_area="abc"))
    assert r.status_code == 422
    assert "Pravidlo potřebuje název." in r.text
    assert "Neznámá lokalita" in r.text and "Vinohrady" in r.text
    assert "Zadej číslo." in r.text


def test_preview(client):
    r = client.post("/rules/preview", data=form(name=""))
    assert "možná" in r.text and "727322700" in r.text
    assert "Neznámá lokalita" in client.post("/rules/preview", data=form(location="xyz")).text


def test_location_autocomplete(client):
    assert '<option value="Smíchov">' in client.get("/locations", params={"location": "smi"}).text
    assert 'value="Praha 1"' in client.get("/locations", params={"q": "praha 1"}).text


def test_medians_page(client):
    text = client.get("/medians?scope=city").text
    assert "<td>Praha</td>" in text
    assert "Žádná data" in client.get("/medians?scope=city&q=nic-takoveho").text


def test_status_page(client):
    assert "Hlídač běží" in client.get("/status").text


# --- settings and accounts ------------------------------------------------------------------

def test_own_settings(friend, cfg):
    r = friend.post("/settings", data={"ntfy_topic": "petr-novy", "priority": "5"})
    assert r.status_code == 200 and "Uloženo" in r.text
    conn = db.connect(cfg.db_path)
    petr = users.get_user(conn, 2)
    assert petr.ntfy_topic == "petr-novy" and petr.priority == 5
    r = friend.post("/settings", data={"ntfy_topic": "spatny kanal!", "priority": "4"})
    assert r.status_code == 422


def test_test_notification_goes_to_me(friend, cfg):
    r = friend.post("/settings/test")
    assert "Odesláno 1 z 1." in r.text  # console channel only in tests
    conn = db.connect(cfg.db_path)
    row = conn.execute("SELECT user_id, recipient FROM alerts ORDER BY id DESC").fetchone()
    assert row["user_id"] == 2 and row["recipient"] == "log:Petr"


def test_admin_manages_users(client, cfg):
    page = client.get("/settings").text
    assert "Uživatelé" in page and "Petr" in page
    r = client.post("/users", data={"name": "Jana"})
    password = re.search(r'<p class="password">([^<]+)</p>', r.text).group(1)
    conn = db.connect(cfg.db_path)
    assert users.authenticate(conn, "Jana", password)
    assert client.post("/users", data={"name": "jana"}).status_code == 422  # duplicate
    jana = next(u for u in users.list_users(conn) if u.name == "Jana")
    client.post(f"/users/{jana.id}/delete")
    assert all(u.name != "Jana" for u in users.list_users(conn))


def test_friend_cannot_manage_users(friend):
    assert "Uživatelé" not in friend.get("/settings").text
    assert friend.post("/users", data={"name": "X"}).status_code == 403
    assert friend.post("/users/1/password").status_code == 403
    assert friend.post("/users/1/delete").status_code == 403


def test_new_own_password(friend, cfg):
    r = friend.post("/settings/password")
    password = re.search(r'<p class="password">([^<]+)</p>', r.text).group(1)
    conn = db.connect(cfg.db_path)
    assert users.authenticate(conn, "Petr", password)


def test_friend_history_is_private(client, friend, cfg):
    conn = db.connect(cfg.db_path)
    for uid, title in ((1, "Tomasuv alert"), (2, "Petruv alert")):
        conn.execute("INSERT INTO alerts (kind, user_id, channel, recipient, title, body, status,"
                     " send_after, created_at) VALUES ('new', ?, 'ntfy', 't', ?, 'b', 'sent', ?, ?)",
                     (uid, title, db.ts(db.utcnow()), db.ts(db.utcnow())))
    conn.commit()
    assert "Petruv alert" in friend.get("/alerts").text
    assert "Tomasuv alert" not in friend.get("/alerts").text
