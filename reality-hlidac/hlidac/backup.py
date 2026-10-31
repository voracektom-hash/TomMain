"""Daily consistent backup of the SQLite database, kept for 7 days.

  python -m hlidac.backup          # run forever, back up every day at BACKUP_AT (03:30)
  python -m hlidac.backup --now    # one backup right now

Backups land next to the database in backups/hlidac-YYYY-MM-DD.db.gz.
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from hlidac import config
from hlidac.schedule import TZ

log = logging.getLogger("hlidac")


def backup_now(db_path: Path, keep_days: int = 7, today: datetime | None = None) -> Path | None:
    if not db_path.exists():
        log.warning("Databáze %s zatím neexistuje, záloha přeskočena", db_path)
        return None
    folder = db_path.parent / "backups"
    folder.mkdir(exist_ok=True)
    today = today or datetime.now(TZ)
    raw = folder / f"hlidac-{today:%Y-%m-%d}.db"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(raw)
    try:
        src.backup(dst)  # consistent even while the watcher writes
    finally:
        dst.close()
        src.close()
    packed = raw.with_suffix(".db.gz")
    with raw.open("rb") as f_in, gzip.open(packed, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    raw.unlink()
    oldest = (today - timedelta(days=keep_days - 1)).strftime("%Y-%m-%d")
    for old in folder.glob("hlidac-*.db.gz"):
        if old.name[len("hlidac-"):len("hlidac-") + 10] < oldest:
            old.unlink()
    log.info("Záloha hotová: %s (%d záloh)", packed.name, len(list(folder.glob("*.db.gz"))))
    return packed


def seconds_until(at: str, now: datetime) -> float:
    hour, minute = (int(x) for x in at.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main() -> None:
    cfg = config.load()
    config.setup_logging(cfg.log_level)
    keep = int(os.environ.get("BACKUP_KEEP_DAYS", "7"))
    if "--now" in sys.argv:
        backup_now(cfg.db_path, keep)
        return
    at = os.environ.get("BACKUP_AT", "03:30")
    log.info("Zálohy: každý den v %s, uchovávám %d dní", at, keep)
    while True:
        time.sleep(seconds_until(at, datetime.now(TZ)))
        try:
            backup_now(cfg.db_path, keep)
        except Exception:  # keep running; tomorrow is another try
            log.exception("Záloha selhala")


if __name__ == "__main__":
    main()
