# Reality Hlídač — plán projektu

## Fáze

| Fáze | Výstup | Stav |
|---|---|---|
| 0 — Zjištění API | `docs/API.md`, uložené ukázkové odpovědi v `tests/fixtures/` | ⛔ blokováno (síť) |
| 1 — Watcher | poller 60 s ±10 s, SQLite, deduplikace, historie cen, mediány 90 dní | čeká |
| 2 — Pravidla + SMS | filtr pravidel, SMSbrána.cz + console provider, tichý režim, watchdog | čeká |
| 3 — Appka | FastAPI + Jinja2 + HTMX, PWA, 6 obrazovek + mediány | čeká |
| 4 — Nasazení | Docker Compose, Tailscale, zálohy, `docs/NASAZENI.md` | čeká |

## Architektura

Dva procesy, jedna SQLite databáze (WAL mód):

```
[watcher]  --každých 60 s-->  Sreality API
    |  zapisuje inzeráty, alerty, heartbeat
    v
[SQLite: data/hlidac.db]
    ^  čte/zapisuje pravidla a nastavení
    |
[web (FastAPI)]  <--Tailscale--  iPhone / laptop
```

Pravidla čte watcher z DB při každém běhu → změna platí bez restartu.

## Struktura adresářů

```
reality-hlidac/
├── README.md                 # česky: co to je, spuštění, přidání pravidla
├── Makefile                  # make dev / make test
├── pyproject.toml            # závislosti (httpx, fastapi, jinja2, pytest)
├── .env.example              # SMS klíče, telefony, nastavení – s komentáři
├── docker-compose.yml        # watcher + web + backup, restart: unless-stopped
├── Dockerfile
├── docs/
│   ├── PLAN.md
│   ├── API.md                # Fáze 0
│   └── NASAZENI.md           # Fáze 4
├── hlidac/
│   ├── config.py             # načtení .env
│   ├── db.py                 # SQLite schéma + migrace
│   ├── sreality/
│   │   ├── client.py         # HTTP, User-Agent, backoff, 429/403
│   │   └── parser.py         # JSON → Listing (jediné místo závislé na API)
│   ├── locations.py          # číselník lokalit (Praha 1–22, části, obce)
│   ├── medians.py            # rolling medián Kč/m² (90 dní)
│   ├── rules.py              # vyhodnocení pravidel
│   ├── sms/
│   │   ├── base.py           # abstrakce providera
│   │   ├── smsbrana.py
│   │   ├── console.py
│   │   └── format.py         # ASCII, ≤160 znaků
│   ├── watcher.py            # hlavní smyčka + watchdog
│   └── web/
│       ├── app.py            # FastAPI routy
│       ├── templates/        # Jinja2 + HTMX
│       └── static/           # CSS, manifest.json, ikony, service worker
├── scripts/
│   └── backup.sh             # denní záloha, 7 dní retence
└── tests/
    ├── fixtures/             # uložené JSON odpovědi Sreality
    ├── test_parser.py
    ├── test_rules.py
    └── test_sms_format.py
```
