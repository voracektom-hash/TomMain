# Reality Hlídač

Hlídá nové inzeráty bytů na prodej na Sreality.cz (Praha + Středočeský kraj) a do ~60 s
od zveřejnění pošle SMS, když byt splní tvoje kritéria.

**Stav:** Fáze 1 (watcher) je hotová. SMS a pravidla přijdou ve Fázi 2, webová appka
ve Fázi 3 a nasazení na VPS ve Fázi 4. Plán je v [`docs/PLAN.md`](docs/PLAN.md),
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
make dev      # první spuštění vytvoří .venv a .env a spustí watcher
```

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

## Jak přidat pravidlo

Pravidla přijdou ve Fázi 2 a jejich úprava ve webové appce ve Fázi 3.
