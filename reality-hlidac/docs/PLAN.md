# Reality Hlídač — plán projektu

## Fáze

| Fáze | Výstup | Stav |
|---|---|---|
| 0 — Zjištění API | `docs/API.md`, uložené ukázkové odpovědi v `tests/fixtures/` | ✅ hotovo |
| 1 — Watcher | adaptivní poller (60 s ±10 s přes den), SQLite, historie cen, mediány 90 dní | ✅ hotovo |
| 2 — Pravidla + notifikace | filtr pravidel, ntfy push + SMS (console; SMSbrána později), tichý režim, watchdog | ✅ hotovo (bez SMSbrány) |
| 3 — Appka | FastAPI + Jinja2 + HTMX, PWA, 6 obrazovek + mediány, druhý watchdog | ✅ hotovo |
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
│   ├── alerts.py             # shoda → detail → fronta → odeslání, watchdog
│   ├── rules_cli.py          # import / výpis / náhled pravidel z příkazové řádky
│   ├── text.py               # diakritika, hledání slov ve všech tvarech
│   ├── notify/
│   │   ├── base.py           # abstrakce kanálu
│   │   ├── ntfy.py           # push notifikace
│   │   ├── console.py        # výpis do logu (i jako SMS náhrada)
│   │   └── format.py         # texty: push s diakritikou, SMS ASCII ≤ 2 segmenty
│   ├── watcher.py            # hlavní smyčka + watchdog
│   ├── preview.py            # „kolik bytů by pravidlo chytilo“
│   ├── users.py              # účty, hesla, ntfy kanál a priorita každého uživatele
│   └── web/
│       ├── app.py            # FastAPI routy, formuláře, watchdog vlákno
│       ├── auth.py           # přihlášení (podepsaná cookie), limit pokusů
│       ├── templates/        # Jinja2 + HTMX
│       └── static/           # CSS, manifest.json, ikony, service worker
├── scripts/
│   ├── dev.sh                # lokálně watcher + appka
│   ├── make_icons.py         # ikony PWA
│   └── backup.sh             # denní záloha, 7 dní retence (Fáze 4)
└── tests/
    ├── fixtures/             # uložené JSON odpovědi Sreality
    ├── test_parser.py
    ├── test_rules.py
    ├── test_alerts.py
    ├── test_watcher.py
    └── test_sms_format.py
```
