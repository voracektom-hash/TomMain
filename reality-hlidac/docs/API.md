# Sreality API — zjištění (Fáze 0)

Ověřeno 21. 10. 2026 živými requesty (curl + Playwright). Ukázkové odpovědi
(zkrácené, kontakty makléře anonymizované) jsou v `tests/fixtures/`.

## TL;DR

| Co | Endpoint |
|---|---|
| Seznam inzerátů | `GET https://www.sreality.cz/api/v1/estates/search` |
| Detail inzerátu | `GET https://www.sreality.cz/api/v1/estates/{hash_id}` |
| Našeptávač lokalit | `GET https://www.sreality.cz/api/v1/localities/suggest?phrase=...` |

- Čisté JSON API, **bez přihlášení, bez tokenů, bez cookies**. Stačí realistický `User-Agent`.
- Praha + Středočeský kraj jdou **jedním requestem** (`locality_region_id=10,11`).
- Detail obsahuje **jméno, telefon i e-mail makléře** a název RK. Žádný další request není potřeba.
- Starý `/api/cs/v2/estates` je mrtvý (404). Stará URL webu `/hledat/...` taky (404), nová je `/hledani/...`.

## 1. Seznam inzerátů

```
GET /api/v1/estates/search
  ?category_type_cb=1        # 1 = prodej
  &category_main_cb=1        # 1 = byty
  &locality_region_id=10,11  # 10 = Praha, 11 = Středočeský kraj; víc hodnot oddělit čárkou
  &sort=-date                # nejnovější (viz pozor níže)
  &limit=60                  # ověřeno až 200
  &offset=0                  # stránkování
  &lang=cs
```

- Víc hodnot v jednom parametru: **čárka** (`10,11`). Svislítko (`10|11`) vrací `422 Invalid arguments`.
  Opakovaný parametr (`...=10&...=11`) tiše vezme jen první hodnotu.
- Odpověď: `{pagination: {limit, offset, total}, results: [...], status_code, status_message, ...}`.
- Řazení (z JS bundlu webu): `-date`, `price_asc`, `price_desc`, `price_m2_asc`, `price_m2_desc`.
  `-price_change_time` existuje v kódu, ale API ho ignoruje (vrací stejné pořadí jako `-date`).
- Velikost: 60 inzerátů ≈ 296 kB, s `Accept-Encoding: gzip` ≈ 35 kB.

### ⚠️ `-date` = čas poslední úpravy, ne zveřejnění

Nahoře nejsou jen nové inzeráty, ale i staré, které makléř upravil nebo „topnul“.
Ověřeno na detailech:

| hash_id | since (zveřejněno) | edited (upraveno) |
|---|---|---|
| 1725177932 | 2026-10-02 | 2026-10-21 |
| 1870266444 | 2026-10-20 | 2026-10-21 |
| 1460207692 | 2026-10-21 | 2026-10-21 |
| 3313299532 | 2026-06-20 | 2026-10-21 |

Důsledky pro watcher:
1. **Nový inzerát = `hash_id`, které ještě nemáme v DB.** Proto při prvním spuštění projdeme
   celou nabídku (~8 300 bytů, 42 requestů po 200, pomalu), abychom staré inzeráty znali předem.
2. Pojistka: v detailu ověříme `since`. Pokud je starší než ~2 dny, jde o „znovuvložený“ inzerát
   a SMS pošleme jen tehdy, když to pravidlo povolí.
3. Změnu ceny chytíme zadarmo: upravený inzerát vyskočí nahoru a my porovnáme cenu s uloženou.

### Položka seznamu (zkráceno)

```json
{
  "hash_id": 1725177932,
  "advert_name": "Prodej bytu 3+1 91 m²",
  "category_sub_cb": {"name": "3+1", "value": 7},
  "price_czk": 15950000.0,
  "price_czk_m2": 175275,
  "price_summary_czk": 15950000.0,
  "locality": {
    "region_id": 10, "region": "Hlavní město Praha",
    "district": "Praha 2", "district_id": 5002,
    "quarter": "Praha 2", "quarter_id": 88,
    "city": "Praha", "citypart": "Nové Město",
    "street": "Ke Karlovu", "gps_lat": 50.0723, "gps_lon": 14.4277
  },
  "premise_id": 55953,
  "user_id": 332129
}
```

- **Plocha není samostatné pole**, parsuje se z `advert_name` (`… 91 m²`; pozor, mezera před `m²` je NBSP ` `).
- `price_czk = 0` znamená „cena na dotaz“. Takový inzerát cenovým filtrem neprojde, ale uložíme ho.
- Patro, vlastnictví a popis jsou **jen v detailu**. Filtrujeme proto ve dvou krocích:
  1. levný filtr ze seznamu (lokalita, cena, plocha, dispozice, Kč/m², medián),
  2. detail jen pro kandidáty, potom patro, vlastnictví a klíčová slova.

## 2. Detail inzerátu

```
GET /api/v1/estates/{hash_id}?lang=cs
```

Odpověď `{result: {...}, status_code, status_message}`. Neexistující inzerát vrací HTTP 404
a `{"status_code":404,"status_message":"Not found"}`.

Důležitá pole:

| Pole | Příklad | Použití |
|---|---|---|
| `since` | `"2026-10-02"` | datum zveřejnění |
| `edited` | `"2026-10-21"` | poslední úprava |
| `usable_area` | `91` | užitná plocha m² |
| `floor_area` | `103` | podlahová plocha |
| `floor_number` | `2` | patro (2 = 2. NP; ověříme na přízemí v datech) |
| `floors` | `7` | počet podlaží domu |
| `ownership` | `{"name": "Osobní", "value": 1}` | vlastnictví (družstevní = jiná hodnota) |
| `advert_description` | text | klíčová slova (podíl, dražba…) |
| `price_summary_old_czk` | `null` | původní cena při slevě |
| `user.user_name` | `"Ing. Jan Novák"` | makléř |
| `user.user_phones[].phone` | `"+420777123456"` | telefon |
| `user.user_email` | | e-mail |
| `premise.name` | `"Bydlení a Reality s.r.o."` | RK |
| `building_type`, `building_condition`, `energy_efficiency_rating_cb` | | do budoucna |

## 3. Lokality

V položce seznamu je lokalita jako text i ID. Pravidla budeme párovat **podle názvu**
(je stabilní a čitelný v UI):

| Typ lokality | Pole | Příklad |
|---|---|---|
| Praha – správní obvod (Praha 1–22) | `locality.quarter` | `"Praha 11"` (Chodov) |
| Praha – katastrální část | `locality.citypart` | `"Smíchov"`, `"Karlín"` |
| Středočeský kraj – obec | `locality.city` | `"Černošice"`, `"Beroun"` |
| Středočeský kraj – okres | `locality.district` | `"Praha-západ"` |

Pozor: `district` v Praze je starý okres (Praha 1–10), např. Chodov má `district = "Praha 4"`,
ale `quarter = "Praha 11"`. Pro „Praha 1–22“ používáme **`quarter`**.

**Našeptávač:** `GET /api/v1/localities/suggest?phrase=Smichov&lang=cs` vrací obce
(`municipality_cz`) a části (`ward_cz`) s ID a krajem. V appce ale budeme našeptávat
z vlastní DB (lokality, které jsme už viděli) a ze statického seznamu, bez dalších requestů na Sreality.

## 4. Odkaz na inzerát

- Plná URL: `https://www.sreality.cz/detail/prodej/byt/{dispozice}/{slug}/{hash_id}`
- Slug může být cokoliv a dispozice libovolná platná: `/detail/prodej/byt/2+kk/x/{id}` → 301 na správnou URL.
- Nejkratší funkční tvar: `sreality.cz/detail/prodej/byt/2+kk/x/1725177932` (~46 znaků).
- `/detail/{id}` vrací 404.

Pro SMS (limit 160 znaků) je to hodně. Řešení navrhnu ve Fázi 2 (vlastní zkracovač vs. služba).

## 5. Hlavičky, cookies, limity

- Stačí `User-Agent` (realistický Chrome) a `Accept-Encoding: gzip`. Bez cookies a tokenů.
- Server nastavuje cookie `sznlbr` (load balancer), API ji nevyžaduje.
- V hlavičkách nejsou žádné rate-limit hlavičky. Při testech (~40 requestů za 15 min) nepřišla žádná 429.
- **Prohlížeč** (ne API) dostane u `/hledani/...` a `/detail/...` redirect 302 na
  `login.seznam.cz/api/v1/autologin`. Obejde se parametrem `?noredirect=1`. Pro API to neplatí.

## 6. Server-side data (záloha)

Stránka `/hledani/prodej/byty/praha` je Next.js a v `<script id="__NEXT_DATA__">` nese
`props.pageProps.dehydratedState.queries[queryKey[0]=="estatesSearch"].state.data` se stejnými
daty v camelCase. **Nepoužíváme**, je to 10× větší a křehčí. Je to ale záložní cesta, kdyby
Sreality JSON API zavřela.

## 7. Doporučená strategie pro watcher

- **1 request / 60 s ±10 s:** `search?...&locality_region_id=10,11&sort=-date&limit=60`, gzip.
- Nové `hash_id` uložit. Známé `hash_id` se změněnou cenou zaznamenat jako změnu ceny.
- Detail jen pro kandidáty, kteří projdou levným filtrem.
- Hlídání struktury: `status_code != 200`, 0 výsledků nebo chybějící `hash_id`/`locality` → watchdog.

## 8. Rizika

- **Neoficiální API.** Může se změnit bez varování. Parser je proto izolovaný v jednom souboru a watchdog pošle servisní SMS.
- **(Spekulace) IP datacentra.** Seznam může IP z Hetzneru omezovat jinak než tuto. Ověříme hned po nasazení (Fáze 4).
