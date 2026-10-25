"""Configuration web app: rules, preview, alert history, status, medians, settings.

Run with:  python -m hlidac.web.app      (port 8000, or WEB_PORT)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import FormData

from hlidac import config, db, locations, rules, users
from hlidac.alerts import AlertEngine
from hlidac.web import auth
from hlidac.notify.base import Message
from hlidac.preview import preview
from hlidac.rules import Rule
from hlidac.rules_cli import DISPOSITIONS, OWNERSHIPS
from hlidac.schedule import TZ
from hlidac.sreality.client import SrealityClient

log = logging.getLogger("hlidac")
HERE = Path(__file__).parent
WEB_WATCHDOG_EVERY_S = 300
WEB_WATCHDOG_INTERVAL_S = 600  # watchdog fires after 2.5 × this = 25 min without a poll
TOPIC_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# --- formatting helpers for templates ------------------------------------------------------

def money(czk: int | None) -> str:
    if not czk:
        return "na dotaz"
    return f"{czk / 1_000_000:.2f} M Kč".replace(".", ",")


def thousands(n: int | float | None) -> str:
    return "–" if n is None else f"{round(n):,}".replace(",", " ")


def local(value: str | None, fmt: str = "%d. %m. %H:%M") -> str:
    if not value:
        return "–"
    return db.parse_ts(value).astimezone(TZ).strftime(fmt)


def ago(value: str | None) -> str:
    if not value:
        return "nikdy"
    seconds = (db.utcnow() - db.parse_ts(value)).total_seconds()
    if seconds < 90:
        return "před chvílí"
    if seconds < 3600:
        return f"před {round(seconds / 60)} min"
    if seconds < 86400:
        return f"před {seconds / 3600:.1f} h".replace(".", ",")
    return f"před {round(seconds / 86400)} dny"


templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters.update(money=money, thousands=thousands, local=local, ago=ago,
                             fromjson=json.loads)
templates.env.globals.update(DISPOSITIONS=DISPOSITIONS, OWNERSHIPS=OWNERSHIPS,
                             TYPE_LABELS=locations.TYPE_LABELS)


# --- app factory ---------------------------------------------------------------------------

def create_app(cfg: config.Config | None = None, *, start_watchdog: bool = True) -> FastAPI:
    cfg = cfg or config.load()
    limiter = auth.LoginLimiter()

    def get_conn() -> Iterator[sqlite3.Connection]:
        conn = db.connect(cfg.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def engine(conn: sqlite3.Connection) -> AlertEngine:
        from hlidac.watcher import build_notifiers
        return AlertEngine(conn, SrealityClient(cfg.user_agent), build_notifiers(cfg))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        stop = threading.Event()
        if start_watchdog:
            threading.Thread(target=_watchdog_loop, args=(cfg, engine, stop), daemon=True).start()
        yield
        stop.set()

    app = FastAPI(title="Reality Hlídač", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        path = request.url.path
        request.state.user = None
        if path in PUBLIC_PATHS or path.startswith("/static/"):
            return await call_next(request)
        conn = db.connect(cfg.db_path)
        try:
            user_id = auth.read_session(auth.secret_key(conn), request.cookies.get(auth.COOKIE))
            user = users.get_user(conn, user_id) if user_id else None
        finally:
            conn.close()
        if user is None:
            if request.headers.get("hx-request"):
                return Response(status_code=401, headers={"HX-Redirect": "/login"})
            return RedirectResponse("/login", status_code=303)
        request.state.user = user
        return await call_next(request)

    def render(request: Request, template: str, status_code: int = 200, **ctx) -> HTMLResponse:
        ctx.setdefault("user", request.state.user)
        return templates.TemplateResponse(request, template, ctx, status_code=status_code)

    def me(request: Request) -> users.User:
        return request.state.user

    def own_rule(conn: sqlite3.Connection, request: Request, rule_id: int) -> Rule | None:
        rule = rules.get_rule(conn, rule_id)
        return rule if rule and rule.user_id == me(request).id else None

    # --- login -----------------------------------------------------------------------------

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, conn=Depends(get_conn)):
        return render(request, "login.html", error=None, name="",
                      no_users=not users.list_users(conn))

    @app.post("/login", response_class=HTMLResponse)
    async def login(request: Request, conn=Depends(get_conn)):
        form = await request.form()
        ip = client_ip(request)
        name = (form.get("name") or "").strip()
        if limiter.blocked(ip):
            return render(request, "login.html", 429, name=name, no_users=False,
                          error="Příliš mnoho pokusů. Zkus to znovu za 15 minut.")
        user = users.authenticate(conn, name, form.get("password") or "")
        if user is None:
            limiter.fail(ip)
            return render(request, "login.html", 401, name=name, no_users=False,
                          error="Špatné jméno nebo heslo.")
        limiter.reset(ip)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(auth.COOKIE, auth.make_session(auth.secret_key(conn), user.id),
                            max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                            secure=is_https(request))
        return response

    @app.post("/logout")
    def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(auth.COOKIE)
        return response

    # --- rules -----------------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def rules_page(request: Request, conn=Depends(get_conn)):
        uid = me(request).id
        own = rules.load_rules(conn, active_only=False, user_id=uid)
        last_alert = {r["rule_names"]: r["created_at"] for r in conn.execute(
            "SELECT rule_names, MAX(created_at) AS created_at FROM alerts "
            "WHERE kind != 'service' AND user_id = ? GROUP BY rule_names", (uid,))}
        return render(request, "rules.html", page="rules", rules=own,
                      describe=describe_rule, last_alert=last_alert)

    @app.post("/rules/{rule_id}/toggle", response_class=HTMLResponse)
    def toggle(request: Request, rule_id: int, conn=Depends(get_conn)):
        rule = own_rule(conn, request, rule_id)
        if rule is None:
            return Response(status_code=404)
        rules.set_active(conn, rule_id, not rule.active, db.utcnow())
        return render(request, "_rule_card.html", rule=rules.get_rule(conn, rule_id),
                      describe=describe_rule, last_alert={})

    @app.get("/rules/new", response_class=HTMLResponse)
    def new_rule(request: Request):
        rule = Rule(name="", location_type="", location="")
        return render(request, "rule_form.html", page="rules", rule=rule, errors={},
                      is_new=True)

    @app.get("/rules/{rule_id}", response_class=HTMLResponse)
    def edit_rule(request: Request, rule_id: int, conn=Depends(get_conn)):
        rule = own_rule(conn, request, rule_id)
        if rule is None:
            return RedirectResponse("/", status_code=303)
        return render(request, "rule_form.html", page="rules", rule=rule, errors={},
                      is_new=False)

    @app.get("/rules/{rule_id}/duplicate", response_class=HTMLResponse)
    def duplicate_rule(request: Request, rule_id: int, conn=Depends(get_conn)):
        rule = own_rule(conn, request, rule_id)
        if rule is None:
            return RedirectResponse("/", status_code=303)
        copy = replace(rule, id=None, name=f"{rule.name} (kopie)")
        return render(request, "rule_form.html", page="rules", rule=copy, errors={},
                      is_new=True)

    @app.post("/rules/save")
    async def save_rule(request: Request, conn=Depends(get_conn)):
        form = await request.form()
        rule, errors = rule_from_form(conn, form)
        rule.user_id = me(request).id
        if rule.id and own_rule(conn, request, rule.id) is None:
            return RedirectResponse("/", status_code=303)
        if not errors:
            try:
                if rule.id:
                    rules.update_rule(conn, rule, db.utcnow())
                else:
                    rules.create_rule(conn, rule, db.utcnow())
            except rules.DuplicateRuleName:
                errors["name"] = "Pravidlo s tímto názvem už máš."
        if errors:
            return render(request, "rule_form.html", 422, page="rules", rule=rule,
                          errors=errors, is_new=not rule.id)
        return RedirectResponse("/", status_code=303)

    @app.post("/rules/{rule_id}/delete")
    def remove_rule(request: Request, rule_id: int, conn=Depends(get_conn)):
        if own_rule(conn, request, rule_id):
            rules.delete_rule(conn, rule_id)
        return RedirectResponse("/", status_code=303)

    @app.post("/rules/preview", response_class=HTMLResponse)
    async def rule_preview(request: Request, conn=Depends(get_conn)):
        form = await request.form()
        rule, errors = rule_from_form(conn, form, require_name=False)
        if "location" in errors:
            return render(request, "_preview.html", result=None, error=errors["location"])
        result = preview(conn, rule, db.utcnow())
        return render(request, "_preview.html", result=result, error=None,
                      shown=result.hits[:30])

    @app.get("/locations", response_class=HTMLResponse)
    def location_options(request: Request, q: str = "", location: str = "",
                         conn=Depends(get_conn)):
        # The input sends its own name ("location"); "q" is for direct use.
        return render(request, "_locations.html", items=search_locations(conn, q or location))

    # --- other pages -----------------------------------------------------------------------

    @app.get("/alerts", response_class=HTMLResponse)
    def alerts_page(request: Request, page: int = 1, conn=Depends(get_conn)):
        per_page = 40
        rows = conn.execute(
            """SELECT a.* FROM alerts a WHERE a.user_id = ?
               ORDER BY a.id DESC LIMIT ? OFFSET ?""",
            (me(request).id, per_page + 1, (page - 1) * per_page)).fetchall()
        return render(request, "alerts.html", page="alerts", rows=rows[:per_page],
                      page_no=page, has_next=len(rows) > per_page)

    @app.get("/status", response_class=HTMLResponse)
    def status_page(request: Request, conn=Depends(get_conn)):
        return render(request, "status.html", page="status", s=status_data(conn, me(request)))

    @app.get("/medians", response_class=HTMLResponse)
    def medians_page(request: Request, scope: str = "quarter", q: str = "",
                     conn=Depends(get_conn)):
        return render(request, "medians.html", page="medians", scope=scope, q=q,
                      rows=median_rows(conn, scope, q))

    # --- settings: own account + (admin) users -------------------------------------------

    def settings_ctx(conn: sqlite3.Connection, request: Request, **extra) -> dict:
        ctx = dict(page="settings", me=users.get_user(conn, me(request).id),
                   people=users.list_users(conn) if me(request).is_admin else [],
                   PRIORITIES=users.PRIORITIES, ntfy_server=cfg.ntfy_server,
                   errors={}, notice=None, new_password=None)
        ctx.update(extra)
        return ctx

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, conn=Depends(get_conn)):
        return render(request, "settings.html", **settings_ctx(conn, request))

    @app.post("/settings", response_class=HTMLResponse)
    async def settings_save(request: Request, conn=Depends(get_conn)):
        form = await request.form()
        topic = (form.get("ntfy_topic") or "").strip()
        priority = int(form.get("priority") or users.DEFAULT_PRIORITY)
        errors = {}
        if topic and not TOPIC_RE.match(topic):
            errors["ntfy_topic"] = "Jen písmena, čísla, - a _ (max. 64 znaků)."
        if priority not in users.PRIORITIES:
            errors["priority"] = "Neplatná priorita."
        if not errors:
            users.update_user(conn, me(request).id, topic=topic, priority=priority)
        return render(request, "settings.html", 422 if errors else 200,
                      **settings_ctx(conn, request, errors=errors,
                                     notice=None if errors else "Uloženo."))

    @app.post("/settings/password", response_class=HTMLResponse)
    def new_own_password(request: Request, conn=Depends(get_conn)):
        password = users.set_password(conn, me(request).id)
        return render(request, "settings.html", **settings_ctx(
            conn, request, new_password=(me(request).name, password)))

    @app.post("/settings/test", response_class=HTMLResponse)
    def settings_test(request: Request, conn=Depends(get_conn)):
        eng = engine(conn)
        targets = eng.recipients(me(request).id)
        if not targets:
            return HTMLResponse('<p class="msg err">Nemáš nastavený ntfy kanál.</p>')
        msg = Message(title="Reality Hlídač: test",
                      body="Testovací notifikace z appky. Když ji vidíš, funguje to. ✓",
                      sms="Reality Hlidac: testovaci zprava.", tags=["white_check_mark"])
        sent = eng.send_now(msg, db.utcnow(), user_id=me(request).id)
        css = "ok" if sent == len(targets) else "err"
        text = f"Odesláno {sent} z {len(targets)}."
        if sent < len(targets):
            last = conn.execute("SELECT error FROM alerts WHERE kind = 'service' AND user_id = ? "
                                "AND error IS NOT NULL ORDER BY id DESC LIMIT 1",
                                (me(request).id,)).fetchone()
            if last:
                text += f" Chyba: {last['error'][:160]}"
        return HTMLResponse(f'<p class="msg {css}">{escape(text)}</p>')

    @app.post("/users", response_class=HTMLResponse)
    async def add_user(request: Request, conn=Depends(get_conn)):
        if not me(request).is_admin:
            return Response(status_code=403)
        form = await request.form()
        try:
            user, password = users.create_user(conn, form.get("name") or "",
                                                admin=form.get("is_admin") == "1")
        except users.UserError as exc:
            return render(request, "settings.html", 422,
                          **settings_ctx(conn, request, errors={"new_user": str(exc)}))
        return render(request, "settings.html", **settings_ctx(
            conn, request, new_password=(user.name, password)))

    @app.post("/users/{user_id}/password", response_class=HTMLResponse)
    def reset_password(request: Request, user_id: int, conn=Depends(get_conn)):
        user = users.get_user(conn, user_id)
        if not me(request).is_admin or user is None:
            return Response(status_code=403)
        password = users.set_password(conn, user_id)
        return render(request, "settings.html", **settings_ctx(
            conn, request, new_password=(user.name, password)))

    @app.post("/users/{user_id}/delete", response_class=HTMLResponse)
    def remove_user(request: Request, user_id: int, conn=Depends(get_conn)):
        if not me(request).is_admin or user_id == me(request).id:
            return Response(status_code=403)
        try:
            users.delete_user(conn, user_id)
        except users.UserError as exc:
            return render(request, "settings.html", 422,
                          **settings_ctx(conn, request, errors={"new_user": str(exc)}))
        return RedirectResponse("/settings", status_code=303)

    # --- PWA + health ----------------------------------------------------------------------

    @app.get("/sw.js")
    def service_worker():
        return FileResponse(HERE / "static" / "sw.js", media_type="text/javascript")

    @app.get("/healthz")
    def health(conn=Depends(get_conn)):
        conn.execute("SELECT 1")
        return {"ok": True}

    return app


PUBLIC_PATHS = {"/login", "/healthz", "/sw.js"}


def client_ip(request: Request) -> str:
    # Behind Caddy the real client is the last X-Forwarded-For entry (Caddy appends it).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "?"


def is_https(request: Request) -> bool:
    return (request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").lower() == "https")


def escape(text: str) -> str:
    from markupsafe import escape as _escape
    return str(_escape(text))


# --- form parsing --------------------------------------------------------------------------

def _num(form: FormData, key: str, errors: dict, *, scale: float = 1,
         integer: bool = True) -> float | int | None:
    raw = (form.get(key) or "").strip().replace(" ", "").replace(",", ".")
    if not raw:
        return None
    try:
        value = float(raw) * scale
    except ValueError:
        errors[key] = "Zadej číslo."
        return None
    if value < 0:
        errors[key] = "Nesmí být záporné."
        return None
    return round(value) if integer else value


def rule_from_form(conn: sqlite3.Connection, form: FormData, *,
                   require_name: bool = True) -> tuple[Rule, dict[str, str]]:
    errors: dict[str, str] = {}
    name = (form.get("name") or "").strip()
    if require_name and not name:
        errors["name"] = "Pravidlo potřebuje název."
    loc_text = (form.get("location") or "").strip()
    loc_type, loc = "", loc_text
    if not loc_text:
        errors["location"] = "Vyber lokalitu."
    else:
        try:
            loc_type, loc = locations.resolve_name(conn, loc_text)
        except locations.UnknownLocation as exc:
            hint = f" Myslel jsi: {', '.join(exc.suggestions)}?" if exc.suggestions else ""
            errors["location"] = f"Neznámá lokalita „{loc_text}“.{hint}"

    keywords = [k.strip() for k in (form.get("exclude_keywords") or "").split(",") if k.strip()]
    quiet_on = form.get("quiet_on") == "1"
    quiet_start = _num(form, "quiet_start", errors) if quiet_on else None
    quiet_end = _num(form, "quiet_end", errors) if quiet_on else None
    if quiet_on and (quiet_start is None or quiet_end is None
                     or not (0 <= quiet_start <= 23 and 0 <= quiet_end <= 23)):
        errors["quiet"] = "Tichý režim potřebuje hodinu od a do (0–23)."
    min_area = _num(form, "min_area", errors, integer=False)
    max_area = _num(form, "max_area", errors, integer=False)
    if min_area and max_area and min_area > max_area:
        errors["max_area"] = "Plocha do musí být větší než od."

    rule = Rule(
        id=int(form["id"]) if (form.get("id") or "").isdigit() else None,
        name=name or "náhled",
        active=form.get("active") == "1",
        location_type=loc_type,
        location=loc,
        max_price=_num(form, "max_price_m", errors, scale=1_000_000),
        max_price_m2=_num(form, "max_price_m2_k", errors, scale=1000),
        min_area=min_area,
        max_area=max_area,
        dispositions=[d for d in form.getlist("dispositions") if d in DISPOSITIONS],
        ownerships=[o for o in form.getlist("ownerships") if o in OWNERSHIPS],
        min_floor=_num(form, "min_floor", errors),
        no_ground_floor=form.get("no_ground_floor") == "1",
        min_below_median=_num(form, "min_below_median", errors, integer=False),
        exclude_keywords=keywords,
        quiet_start=quiet_start,
        quiet_end=quiet_end,
        quiet_action="drop" if form.get("quiet_action") == "drop" else "defer",
        price_drop_alert=form.get("price_drop_alert") == "1",
    )
    return rule, errors


# --- page data -----------------------------------------------------------------------------

def describe_rule(r: Rule) -> list[str]:
    bits = []
    if r.dispositions:
        bits.append(", ".join(r.dispositions))
    if r.min_area or r.max_area:
        lo = f"{r.min_area:g}" if r.min_area else "0"
        hi = f"{r.max_area:g}" if r.max_area else "∞"
        bits.append(f"{lo}–{hi} m²")
    if r.max_price:
        bits.append(f"do {money(r.max_price)}")
    if r.max_price_m2:
        bits.append(f"do {thousands(r.max_price_m2)} Kč/m²")
    if r.min_below_median:
        bits.append(f"≥ {r.min_below_median:g} % pod mediánem")
    if r.ownerships:
        bits.append(", ".join(r.ownerships))
    if r.no_ground_floor:
        bits.append("bez přízemí")
    if r.min_floor:
        bits.append(f"od {r.min_floor}. NP")
    if r.quiet_start is not None:
        action = "ráno" if r.quiet_action == "defer" else "zahodit"
        bits.append(f"ticho {r.quiet_start}–{r.quiet_end} h ({action})")
    if r.price_drop_alert:
        bits.append("+ slevy")
    return bits


def search_locations(conn: sqlite3.Connection, q: str, limit: int = 12) -> list[tuple[str, str, int]]:
    from hlidac.text import normalize
    wanted = normalize(q.strip())
    items = locations.known_locations(conn)
    if wanted:
        items = [i for i in items if wanted in normalize(i[1])]
        items.sort(key=lambda i: (not normalize(i[1]).startswith(wanted), -i[2]))
    else:
        items.sort(key=lambda i: -i[2])
    seen, out = set(), []
    for loc_type, name, n in items:
        if name not in seen:
            seen.add(name)
            out.append((loc_type, name, n))
    return out[:limit]


def status_data(conn: sqlite3.Connection, user: users.User) -> dict:
    """Watcher health is shared; alert and rule counts are the user's own."""
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
    midnight = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    day_ago = db.ts(db.utcnow() - timedelta(hours=24))
    today = db.ts(midnight)
    last_ok = q("SELECT MAX(started_at) FROM runs WHERE kind = 'poll' AND ok = 1")
    healthy = bool(last_ok) and db.utcnow() - db.parse_ts(last_ok) < timedelta(minutes=25)
    return dict(
        last_ok=last_ok,
        healthy=healthy,
        polls_today=q("SELECT COUNT(*) FROM runs WHERE kind = 'poll' AND ok = 1 AND started_at >= ?", today),
        new_today=q("SELECT COUNT(*) FROM listings WHERE from_sweep = 0 AND first_seen >= ?", today),
        drops_today=q("SELECT COUNT(*) FROM price_history WHERE changed_at >= ? AND new_price < old_price", today),
        alerts_today=q("SELECT COUNT(*) FROM alerts WHERE status = 'sent' AND kind != 'service' "
                       "AND created_at >= ? AND user_id = ?", today, user.id),
        alerts_failed=q("SELECT COUNT(*) FROM alerts WHERE status = 'failed' AND created_at >= ? "
                        "AND user_id = ?", day_ago, user.id),
        alerts_waiting=q("SELECT COUNT(*) FROM alerts WHERE status = 'queued' AND user_id = ?",
                         user.id),
        errors=conn.execute("SELECT started_at, error FROM runs WHERE ok = 0 AND started_at >= ? "
                            "ORDER BY id DESC LIMIT 10", (day_ago,)).fetchall(),
        listings=q("SELECT COUNT(*) FROM listings WHERE removed_at IS NULL"),
        rules_active=q("SELECT COUNT(*) FROM rules WHERE active = 1 AND user_id = ?", user.id),
        watchdog_alarm=db.get_meta(conn, "watchdog_alarm") == "1",
        sweep_done=db.get_meta(conn, "sweep_done"),
    )


def median_rows(conn: sqlite3.Connection, scope: str, q: str) -> list[sqlite3.Row]:
    from hlidac.text import normalize
    if scope not in ("quarter", "citypart", "city", "district"):
        scope = "quarter"
    rows = conn.execute(
        """SELECT m.location, m.median_m2, m.n,
                  (SELECT json_group_object(d.disposition, d.median_m2) FROM medians d
                   WHERE d.scope = m.scope AND d.location = m.location AND d.disposition != '')
                  AS by_disp
           FROM medians m WHERE m.scope = ? AND m.disposition = ''""", (scope,)).fetchall()
    if q:
        rows = [r for r in rows if normalize(q) in normalize(r["location"])]

    def key(r):
        m = re.match(r"^Praha (\d+)$", r["location"])
        return (0, int(m.group(1)), "") if m else (1, -r["n"], r["location"])
    return sorted(rows, key=key)


# --- background watchdog -------------------------------------------------------------------

def _watchdog_loop(cfg: config.Config, engine_factory, stop: threading.Event) -> None:
    """Second line of defence: if the watcher process dies, the web app notices."""
    while not stop.wait(WEB_WATCHDOG_EVERY_S):
        try:
            conn = db.connect(cfg.db_path)
            try:
                engine_factory(conn).watchdog(db.utcnow(), None, WEB_WATCHDOG_INTERVAL_S)
            finally:
                conn.close()
        except Exception:  # never let the thread die
            log.exception("Watchdog v appce selhal")


def main() -> None:
    import uvicorn
    cfg = config.load()
    config.setup_logging(cfg.log_level)
    port = int(os.environ.get("WEB_PORT", "8000"))
    log.info("Appka běží na http://0.0.0.0:%d", port)
    uvicorn.run("hlidac.web.app:create_app", factory=True, host="0.0.0.0", port=port,
                log_level="warning")


if __name__ == "__main__":
    main()
