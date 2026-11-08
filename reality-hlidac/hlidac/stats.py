"""Print a quick overview of what the watcher has collected.

Run with:  python -m hlidac.stats
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from hlidac import config, db
from hlidac.schedule import TZ


def _praha_key(name: str) -> int:
    match = re.search(r"\d+", name)
    return int(match.group()) if match else 999


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def main() -> None:
    cfg = config.load()
    conn = db.connect(cfg.db_path)
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731

    midnight = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    print("=== Reality Hlídač – stav ===")
    print(f"Inzerátů v DB:          {fmt_int(q('SELECT COUNT(*) FROM listings'))}"
          f" (aktivních {fmt_int(q('SELECT COUNT(*) FROM listings WHERE removed_at IS NULL'))})")
    print(f"Nových dnes:            "
          f"{q('SELECT COUNT(*) FROM listings WHERE from_sweep = 0 AND first_seen >= ?', db.ts(midnight))}")
    print(f"Změn ceny dnes:         "
          f"{q('SELECT COUNT(*) FROM price_history WHERE changed_at >= ?', db.ts(midnight))}")
    last_ok = q("SELECT MAX(started_at) FROM runs WHERE kind = 'poll' AND ok = 1")
    if last_ok:
        local = db.parse_ts(last_ok).astimezone(TZ).strftime("%d.%m. %H:%M:%S")
        print(f"Poslední úspěšná kontrola: {local}")
    errors = q("SELECT COUNT(*) FROM runs WHERE ok = 0 AND started_at >= ?",
               db.ts(db.utcnow() - timedelta(hours=24)))
    print(f"Chyb za 24 h:           {errors}")

    rows = conn.execute("SELECT location, median_m2, n FROM medians "
                        "WHERE scope = 'quarter' AND disposition = ''").fetchall()
    if rows:
        print("\nMedián Kč/m² (90 dní), Praha:")
        for r in sorted(rows, key=lambda r: _praha_key(r["location"])):
            print(f"  {r['location']:<10} {fmt_int(r['median_m2']):>9} Kč/m²   (n={r['n']})")

    rows = conn.execute(
        """SELECT m.location, m.median_m2, m.n FROM medians m
           WHERE m.scope = 'city' AND m.disposition = '' AND m.location != 'Praha'
           ORDER BY m.n DESC LIMIT 15""").fetchall()
    if rows:
        print("\nMedián Kč/m² (90 dní), největší obce mimo Prahu:")
        for r in rows:
            print(f"  {r['location']:<22} {fmt_int(r['median_m2']):>9} Kč/m²   (n={r['n']})")


if __name__ == "__main__":
    main()
