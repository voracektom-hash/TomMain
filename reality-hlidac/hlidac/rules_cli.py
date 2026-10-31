"""Manage rules from the command line until the web app exists (phase 3).

  python -m hlidac.rules_cli import pravidla.toml [Jmeno]   # add / update rules (default: admin)
  python -m hlidac.rules_cli list                   # show rules
  python -m hlidac.rules_cli preview                # how many listings each rule would catch
  python -m hlidac.rules_cli test-notify            # send a test notification
"""

from __future__ import annotations

import sys
import tomllib
from hlidac import config, db, locations
from hlidac.alerts import AlertEngine
from hlidac.notify.base import Message
from hlidac.preview import preview
from hlidac.rules import Rule, load_rules, save_rule
from hlidac.sreality.client import SrealityClient

PREVIEW_DAYS = 7
PREVIEW_SHOW = 15

# Czech keys in pravidla.toml -> Rule fields
KEYS = {
    "aktivni": "active", "max_cena": "max_price", "max_cena_m2": "max_price_m2",
    "plocha_od": "min_area", "plocha_do": "max_area", "dispozice": "dispositions",
    "vlastnictvi": "ownerships", "min_podlazi": "min_floor", "bez_prizemi": "no_ground_floor",
    "min_pod_medianem": "min_below_median", "vyloucena_slova": "exclude_keywords",
    "alert_sleva": "price_drop_alert",
}
QUIET_ACTIONS = {"rano": "defer", "ráno": "defer", "zahodit": "drop"}
DISPOSITIONS = ["1+kk", "1+1", "2+kk", "2+1", "3+kk", "3+1", "4+kk", "4+1", "5+kk", "5+1",
                "6 a více", "Atypický"]
OWNERSHIPS = ["osobní", "družstevní", "státní/obecní"]
NUMBER_FIELDS = ("max_cena", "max_cena_m2", "plocha_od", "plocha_do", "min_podlazi",
                 "min_pod_medianem")
BOOL_FIELDS = ("aktivni", "bez_prizemi", "alert_sleva")


class RuleFileError(ValueError):
    pass


def rule_from_toml(conn, data: dict) -> Rule:
    name = data.get("nazev")
    if not name:
        raise RuleFileError("pravidlo nemá „nazev“")
    if "lokalita" not in data:
        raise RuleFileError(f"pravidlo „{name}“ nemá „lokalita“")
    try:
        loc_type, loc = locations.resolve_name(conn, data["lokalita"])
    except locations.UnknownLocation as exc:
        hint = f" Myslel jsi: {', '.join(exc.suggestions)}?" if exc.suggestions else ""
        raise RuleFileError(f"pravidlo „{name}“: neznámá lokalita „{exc.name}“.{hint}") from exc

    rule = Rule(name=name, location_type=loc_type, location=loc)
    unknown = set(data) - set(KEYS) - {"nazev", "lokalita", "tichy_rezim", "tichy_rezim_akce"}
    if unknown:
        raise RuleFileError(f"pravidlo „{name}“: neznámé položky {', '.join(sorted(unknown))}")
    for cz in NUMBER_FIELDS:
        if cz in data and (isinstance(data[cz], bool) or not isinstance(data[cz], (int, float))):
            raise RuleFileError(f"pravidlo „{name}“: {cz} musí být číslo")
    for cz in BOOL_FIELDS:
        if cz in data and not isinstance(data[cz], bool):
            raise RuleFileError(f"pravidlo „{name}“: {cz} musí být true nebo false")
    bad = [d for d in data.get("dispozice", []) if d not in DISPOSITIONS]
    if bad:
        raise RuleFileError(f"pravidlo „{name}“: neznámá dispozice {bad}. "
                            f"Možnosti: {', '.join(DISPOSITIONS)}")
    bad = [o for o in data.get("vlastnictvi", []) if o.lower() not in OWNERSHIPS]
    if bad:
        raise RuleFileError(f"pravidlo „{name}“: neznámé vlastnictví {bad}. "
                            f"Možnosti: {', '.join(OWNERSHIPS)}")
    for cz, field in KEYS.items():
        if cz in data:
            setattr(rule, field, data[cz])

    quiet = data.get("tichy_rezim", "22-7")
    if quiet in ("", "ne", False):
        rule.quiet_start = rule.quiet_end = None
    else:
        try:
            start, end = (int(x) for x in str(quiet).split("-"))
            assert 0 <= start <= 23 and 0 <= end <= 23
        except (ValueError, AssertionError) as exc:
            raise RuleFileError(f"pravidlo „{name}“: tichy_rezim musí být např. \"22-7\"") from exc
        rule.quiet_start, rule.quiet_end = start, end
    action = data.get("tichy_rezim_akce", "rano")
    if action not in QUIET_ACTIONS:
        raise RuleFileError(f"pravidlo „{name}“: tichy_rezim_akce musí být „rano“ nebo „zahodit“")
    rule.quiet_action = QUIET_ACTIONS[action]
    return rule


def cmd_import(conn, path: str, user_name: str | None = None) -> None:
    owner = _owner(conn, user_name)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    items = data.get("pravidlo", [])
    if not items:
        sys.exit("Soubor neobsahuje žádné [[pravidlo]].")
    rules = [rule_from_toml(conn, item) for item in items]  # validate all before saving
    for rule in rules:
        rule.user_id = owner.id
        save_rule(conn, rule, db.utcnow())
        print(f"✓ {rule.name}  ({locations.TYPE_LABELS[rule.location_type]}: {rule.location})")
    print(f"Uloženo pravidel: {len(rules)} pro {owner.name}. Watcher je použije při příští kontrole.")


def _owner(conn, user_name: str | None):
    from hlidac.users import admins, list_users
    people = list_users(conn)
    if not people:
        raise RuleFileError("Nejdřív vytvoř účet: python -m hlidac.users add Jmeno --admin")
    if user_name is None:
        return admins(conn)[0]
    for u in people:
        if u.name.lower() == user_name.lower():
            return u
    raise RuleFileError(f"Uživatel {user_name} neexistuje.")


def describe_rule(r: Rule) -> str:
    bits = [f"{r.location}"]
    if r.dispositions:
        bits.append("/".join(r.dispositions))
    if r.min_area or r.max_area:
        bits.append(f"{r.min_area or 0:g}–{f'{r.max_area:g}' if r.max_area else '∞'} m²")
    if r.max_price:
        bits.append(f"≤ {r.max_price / 1e6:.2f} M".replace(".", ","))
    if r.max_price_m2:
        bits.append(f"≤ {r.max_price_m2:,} Kč/m²".replace(",", " "))
    if r.min_below_median:
        bits.append(f"≥ {r.min_below_median:g} % pod mediánem")
    if r.ownerships:
        bits.append("/".join(r.ownerships))
    if r.no_ground_floor:
        bits.append("bez přízemí")
    if r.min_floor:
        bits.append(f"od {r.min_floor}. NP")
    if r.quiet_start is not None:
        bits.append(f"ticho {r.quiet_start}–{r.quiet_end} ({'ráno' if r.quiet_action == 'defer' else 'zahodit'})")
    if r.price_drop_alert:
        bits.append("+ slevy")
    return " · ".join(bits)


def cmd_list(conn) -> None:
    rules = load_rules(conn, active_only=False)
    if not rules:
        print("Žádná pravidla. Přidej je: make import-rules")
    for r in rules:
        print(f"[{'✓' if r.active else ' '}] {r.id}. {r.name}\n      {describe_rule(r)}")


def cmd_preview(conn) -> None:
    now = db.utcnow()
    for rule in load_rules(conn, active_only=False):
        p = preview(conn, rule, now, PREVIEW_DAYS)
        print(f"■ {rule.name}: {p.sure} jistě + {p.maybe} možná z {p.new_total} nových "
              f"za {p.days} dní · {p.offer_hits} z {p.offer_total} v aktuální nabídce")
        for h in p.hits[:PREVIEW_SHOW]:
            l = h.listing
            price = f"{l.price_czk / 1e6:.2f} M".replace(".", ",") if l.price_czk else "na dotaz"
            mark = "" if h.sure else " (možná)"
            print(f"    {h.first_seen[:16]}  {l.disposition} {l.area_m2:g} m²  {price}{mark}  {l.url}")
    print("\n„Možná“ = projde vším kromě patra/vlastnictví/slov v popisu, které známe až z detailu.")


def cmd_test_notify(conn, cfg) -> None:
    from hlidac.watcher import build_notifiers
    engine = AlertEngine(conn, SrealityClient(cfg.user_agent), build_notifiers(cfg))
    msg = Message(title="Reality Hlídač: test", body="Testovací notifikace. Když ji vidíš, funguje to. ✓",
                  sms="Reality Hlidac: testovaci SMS. Funguje to.", priority=3, tags=["white_check_mark"])
    now = db.utcnow()
    sent = engine.send_now(msg, now)
    print(f"Odesláno {sent} zpráv (správcům).")


def main() -> None:
    cfg = config.load()
    config.setup_logging(cfg.log_level)
    conn = db.connect(cfg.db_path)
    args = sys.argv[1:]
    try:
        if args[:1] == ["import"] and len(args) in (2, 3):
            cmd_import(conn, args[1], args[2] if len(args) == 3 else None)
        elif args == ["list"]:
            cmd_list(conn)
        elif args == ["preview"]:
            cmd_preview(conn)
        elif args == ["test-notify"]:
            cmd_test_notify(conn, cfg)
        else:
            sys.exit(__doc__)
    except RuleFileError as exc:
        sys.exit(f"Chyba: {exc}")


if __name__ == "__main__":
    main()
