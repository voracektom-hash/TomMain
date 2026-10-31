# Reality Hlídač

Hlídá nové inzeráty bytů na prodej na Sreality.cz (Praha; Středočeský kraj jde zapnout v `.env`) a do ~60 s
od zveřejnění pošle push notifikaci (a později SMS), když byt splní tvoje kritéria.

**Stav:** všechny 4 fáze jsou hotové – watcher, pravidla, push notifikace přes ntfy
(zdarma), webová appka s účty pro víc lidí a nasazení na server jedním příkazem.
**Jak to rozjet na serveru zdarma: [`docs/NASAZENI.md`](docs/NASAZENI.md).**
SMS (SMSbrána.cz) se případně doplní později. Plán je v [`docs/PLAN.md`](docs/PLAN.md),
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
Před prvním přihlášením vytvoř účet správce (vypíše heslo):

```bash
.venv/bin/python -m hlidac.users add Tomas --admin
```

Při prvním spuštění watcher asi 5 minut prochází celou nabídku (~6 000 bytů v Praze), aby věděl,
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
| Nastavení | můj ntfy kanál a priorita, testovací notifikace, návod pro iPhone; správce přidává uživatele |

**Víc uživatelů:** každý má vlastní přihlášení, pravidla, historii, ntfy kanál a prioritu
notifikací (normální / vysoká / nejvyšší). Správce přidá kamaráda v Nastavení → Uživatelé,
appka vygeneruje heslo. Sreality se kontroluje jedním dotazem pro všechny.

Appka hlídá i samotný watcher: když 25 minut neproběhne kontrola, pošle servisní notifikaci.

## Jak přidat pravidlo

V appce: **Pravidla → + Nové**. Náhled dole ukazuje, kolik bytů by pravidlo chytilo,
takže kritéria vyladíš ještě před uložením.

Alternativně z příkazové řádky přes soubor:

```bash
cp pravidla.example.toml pravidla.toml   # vzor s vysvětlivkami u každé položky
# uprav pravidla.toml v libovolném textovém editoru
make import-rules                        # nahraje pravidla správci (stejný název = přepíše)
make rules                               # vypíše pravidla
make preview                             # kolik bytů by které pravidlo chytilo
```

Lokalita může být obvod („Praha 5“), městská část („Praha-Libuš“), část („Smíchov“)
nebo obec („Černošice“). Když název neexistuje, příkaz napoví podobné.
Změna platí od příští kontroly, watcher není potřeba restartovat.

## Notifikace (ntfy, zdarma)

1. Nainstaluj si do iPhonu aplikaci **ntfy** a povol jí notifikace.
2. V appce Hlídač otevři **Nastavení** – je tam tvůj osobní ntfy kanál.
3. V ntfy klepni na **+** a zadej ten kanál.
4. **Nejvyšší priorita:** Nastavení iPhonu → Oznámení → ntfy → *Časově citlivá oznámení*,
   a v režimech Soustředění povol časově citlivá oznámení. Pak notifikace projde i přes
   Soustředění/Spánek (fyzický přepínač ztišení ale nepřebije nic).
5. Tlačítkem **Poslat testovací notifikaci** ověříš, že to funguje.

Notifikace obsahuje fotku, cenu, Kč/m², srovnání s mediánem, podlaží, vlastnictví,
makléře a tlačítka „Inzerát“ a „Zavolat“. SMS text (bez diakritiky, max. 2 SMS) se
tvoří už teď a ukáže se v logu, odesílat se začne po napojení SMS brány.

**Watchdog:** když 10 minut (v noci déle) neproběhne úspěšná kontrola, nebo Sreality
začne vracet nečekaná data, přijde servisní notifikace (max. 1× za hodinu) a po
opravě zpráva „Hlídač zase funguje“.
