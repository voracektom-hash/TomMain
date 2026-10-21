"""Configuration loaded from environment variables and an optional .env file."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Config:
    db_path: Path
    region_ids: tuple[int, ...]
    page_limit: int
    user_agent: str
    log_level: str


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding real env vars."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load(env_file: str | Path = ".env") -> Config:
    load_env_file(Path(env_file))
    env = os.environ
    return Config(
        db_path=Path(env.get("DB_PATH", "data/hlidac.db")),
        region_ids=tuple(int(x) for x in env.get("REGION_IDS", "10,11").split(",") if x.strip()),
        page_limit=int(env.get("PAGE_LIMIT", "60")),
        user_agent=env.get("USER_AGENT", DEFAULT_USER_AGENT),
        log_level=env.get("LOG_LEVEL", "INFO").upper(),
    )


class PragueFormatter(logging.Formatter):
    """Log timestamps in Prague time, whatever the server's timezone is."""

    def formatTime(self, record, datefmt=None):  # noqa: N802 (logging API name)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        moment = datetime.fromtimestamp(record.created, ZoneInfo("Europe/Prague"))
        return moment.strftime(datefmt or "%Y-%m-%d %H:%M:%S")


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(PragueFormatter("%(asctime)s %(levelname)-7s %(message)s"))
    logging.basicConfig(level=level, handlers=[handler])
