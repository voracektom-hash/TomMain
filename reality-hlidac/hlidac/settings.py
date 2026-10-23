"""User-editable settings stored in the database; .env values are the defaults.

The watcher reloads them on every check, so a change in the web app applies right away.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from hlidac import config, db

PREFIX = "setting:"
CHANNELS = ("ntfy", "sms", "console")


@dataclass(frozen=True)
class Settings:
    channels: tuple[str, ...]
    ntfy_topics: tuple[str, ...]
    sms_recipients: tuple[str, ...]


def load(conn: sqlite3.Connection, cfg: config.Config) -> Settings:
    def get(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
        raw = db.get_meta(conn, PREFIX + key)
        return tuple(json.loads(raw)) if raw is not None else default

    return Settings(
        channels=get("channels", cfg.notify_channels),
        ntfy_topics=get("ntfy_topics", cfg.ntfy_topics),
        sms_recipients=get("sms_recipients", cfg.sms_recipients),
    )


def save(conn: sqlite3.Connection, s: Settings) -> None:
    for key, value in (("channels", s.channels), ("ntfy_topics", s.ntfy_topics),
                       ("sms_recipients", s.sms_recipients)):
        db.set_meta(conn, PREFIX + key, json.dumps(list(value), ensure_ascii=False))
