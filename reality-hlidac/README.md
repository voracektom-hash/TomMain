# Reality Hlídač

Hlídá nové inzeráty bytů na prodej na Sreality.cz (Praha + Středočeský kraj) a do ~60 s
od zveřejnění pošle push notifikaci (a později SMS), když byt splní tvoje kritéria.

**Stav:** Fáze 1 (watcher), 2 (pravidla + push notifikace přes ntfy) a 3 (webová appka)
jsou hotové. Skutečné SMS (SMSbrána.cz) se doplní později, zatím se SMS jen vypisují do
logu. Nasazení na VPS přijde ve Fázi 4. Plán je v [`docs/PLAN.md`](docs/PLAN.md),
popis Sreality API v [`docs/API.md`](docs/API.md).

## Co dělá teď

- Kontroluje nejnovější inzeráty, přes den každou minutu, v noci řidčeji (viz níže).
- Ukládá **všechny** viděné byty do SQLite (`data/hlidac.db`): cenu, plochu, dispozici,
  lokalitu a čas prvního výskytu.
- Zaznamenává změny ceny.
- Jednou za hodinu přepočítá medián Kč/m² za 90 dní pro každou lokalitu.
- Jednou týdně v noci projde celou nabídku a označí stažené inzeráty.

## Spuštění na vlastním počítači

Potřebuješ Python 3.12 nebo novější a `make`. Na Macu jsou obvykle už nainstalované.

```bash
cd reality-hlidac
make dev      # první spuštění vytvoří .venv a .env, spustí watcher i webovou appku
```

Appka běží na http://localhost:8000. Watcher a appka sdílejí jednu databázi.

Při prvním spuštění watcher asi 7 minut prochází celou nabídku (~8 300 bytů), aby věděl,
co už existuje. Teprve potom hlásí nové inzeráty. Zastavíš ho klávesami `Ctrl+C`.

Další příkazy:

```bash
make stats    # počty inzerátů, poslední kontrola, mediány Kč/m²
make test     # automatické testy
```

## Jak číst log

```
2026-10-21 14:02:11 INFO    Nový: 2+kk 54 m² | Praha 3 Žižkov | 10,19 M Kč (188 704 Kč/m²) | https://…
2026-10-21 14:09:40 INFO    Změna ceny: 10,99 M Kč → 9,99 M Kč (-9,1 %) | 3+kk 72 m² | …
2026-10-21 15:00:03 INFO    Za poslední hodinu: 60 kontrol, 14 nových inzerátů
2026-10-21 15:03:00 WARNING Sreality nás brzdí (HTTP 429) – zpomaluji 5× na 30 min
```

## Jak často kontroluje

Prvních 14 dní platí pevný rozvrh: 7–22 h každou minutu, 22–24 a 6–7 h každé 3 minuty,
0–6 h každých 10 minut. Potom se rozvrh učí z vlastní historie: v hodinách, kdy v průměru
přibývají aspoň 3 nové byty za hodinu, kontroluje každou minutu, při méně než 0,5 bytu
za hodinu jen každých 10 minut. Nic se tím neztratí, pomalejší kontrola jen o pár minut
oddálí upozornění.

## Webová appka

Mobile-first, funguje na iPhonu i v počítači. Na iPhonu ji v Safari přidáš na plochu přes
Sdílet → Přidat na plochu.

| Obrazovka | Co tam je |
|---|---|
| Pravidla | seznam, přepínač aktivní, upravit / duplikovat / smazat |
| Editor | všechna kritéria, lokalita s našeptáváním, **živý náhled** – kolik bytů za 7 dní by pravidlo chytilo |
| Historie | každá odeslaná / čekající / zahozená zpráva, komu a proč |
| Mediány | Kč/m² za 90 dní podle obvodu, části, obce a okresu |
| Stav | poslední kontrola, počty dnes, chyby |
| Nastavení | kanály, ntfy témata, SMS čísla, testovací notifikace |

Appka hlídá i samotný watcher: když 25 minut neproběhne kontrola, pošle servisní notifikaci.

## Jak přidat pravidlo

V appce: **Pravidla → + Nové**. Náhled dole ukazuje, kolik bytů by pravidlo chytilo,
takže kritéria vyladíš ještě před uložením.

Alternativně z příkazové řádky přes soubor:

```bash
cp pravidla.example.toml pravidla.toml   # vzor s vysvětlivkami u každé položky
# uprav pravidla.toml v libovolném textovém editoru
make import-rules                        # nahraje pravidla (stejný název = přepíše)
make rules                               # vypíše pravidla
make preview                             # kolik bytů by které pravidlo chytilo
```

Lokalita může být obvod („Praha 5“), městská část („Praha-Libuš“), část („Smíchov“)
nebo obec („Černošice“). Když název neexistuje, příkaz napoví podobné.
Změna platí od příští kontroly, watcher není potřeba restartovat.

## Notifikace

1. Nainstaluj si do telefonu aplikaci **ntfy** (zdarma).
2. Vymysli tajný název kanálu, třeba `python3 -c "import secrets; print('hlidac-' + secrets.token_urlsafe(12))"`.
3. V aplikaci se ke kanálu přihlas (Subscribe to topic). Stejně to může udělat i další člověk v rodině.
4. Do `.env` dej `NOTIFY_CHANNELS=ntfy` a `NTFY_TOPICS=<název kanálu>`.
5. `make test-notify` pošle testovací notifikaci.

Notifikace obsahuje fotku, cenu, Kč/m², srovnání s mediánem, podlaží, vlastnictví,
makléře a tlačítka „Inzerát“ a „Zavolat“. SMS text (bez diakritiky, max. 2 SMS) se
tvoří už teď a ukáže se v logu, odesílat se začne po napojení SMS brány.

**Watchdog:** když 10 minut (v noci déle) neproběhne úspěšná kontrola, nebo Sreality
začne vracet nečekaná data, přijde servisní notifikace (max. 1× za hodinu) a po
opravě zpráva „Hlídač zase funguje“.
