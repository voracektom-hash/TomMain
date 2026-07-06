# Výkazy práce — interní timesheet aplikace

Interní webová aplikace, která nahrazuje měsíční excelovou docházku. Zaměstnanci
vyplňují měsíční výkaz v kalendáři — každému pracovnímu dni přiřadí číslo
projektu (nebo dovolenou / nemoc), výkaz odešlou ke schválení a administrátor
jej schválí nebo vrátí. Výkaz lze kdykoli exportovat do XLSX.

## Technologie

- **Next.js** (App Router, TypeScript) + **Tailwind CSS** + shadcn/ui komponenty
- **Supabase** — Auth, Postgres, Row Level Security
- **ExcelJS** — export do XLSX
- **Vitest** — unit testy doménové logiky (datumy, svátky, validace)

## Funkce

| Role | Funkce |
| --- | --- |
| Zaměstnanec | přihlášení, dashboard se stavem aktuálního měsíce a chybějícími dny, měsíční kalendář (víkendy a české státní svátky se předvyplní automaticky), přiřazení projektu po dnech, hromadné vyplnění vybraných dnů, kopie minulého měsíce, odeslání měsíce ke schválení, export XLSX |
| Admin | přehled výkazů všech zaměstnanců, detail výkazu se souhrnem po projektech, schválení / vrácení s důvodem, správa projektů (vytvoření, úprava, deaktivace), export XLSX |

Stavový workflow výkazu: `draft → submitted → approved`, případně
`submitted → returned → submitted` (vrácený výkaz lze opravit a znovu odeslat).
Odeslaný ani schválený výkaz nelze editovat — vynuceno v UI, v server actions
i na úrovni RLS.

Všechny důležité akce (založení/odeslání/schválení/vrácení výkazu, změny
projektů, úpravy dnů) se zapisují do tabulky `audit_logs`.

## Struktura projektu

```
supabase/
  migrations/            SQL migrace (schéma + RLS politiky)
  seed.sql               demo data (projekty + admin/zaměstnanec)
src/
  lib/                   doménová logika oddělená od UI
    dates.ts             typované helpery pro měsíce/dny, české formátování
    holidays.ts          české státní svátky vč. Velikonoc
    validation.ts        validace měsíce, povolené stavové přechody
    supabase/            klienti (browser/server/middleware) + dotazy
  app/
    actions/             server actions (timesheety, admin, projekty, auth)
    login/               přihlášení
    (app)/dashboard      přehled zaměstnance
    (app)/timesheets/[year]/[month]   měsíční kalendář
    (app)/projects       správa projektů
    (app)/admin/timesheets(/[id])     schvalování
    api/export/[monthId] XLSX export
  components/            UI komponenty (shadcn/ui + kalendář, dialogy)
```

## Lokální spuštění

Předpoklady: Node.js 20+, [Supabase CLI](https://supabase.com/docs/guides/cli),
Docker (pro lokální Supabase).

```bash
# 1. Závislosti
npm install

# 2. Lokální Supabase (aplikuje migrace i seed.sql)
supabase start
supabase db reset

# 3. Konfigurace prostředí
cp .env.example .env.local
# doplňte hodnoty, které vypsal `supabase start` / `supabase status`:
#   NEXT_PUBLIC_SUPABASE_URL      (API URL, typicky http://127.0.0.1:54321)
#   NEXT_PUBLIC_SUPABASE_ANON_KEY (anon key)

# 4. Vývojový server
npm run dev
```

Aplikace poběží na <http://localhost:3000>.

### Demo účty (ze seed.sql)

| Role | E-mail | Heslo |
| --- | --- | --- |
| Admin | `admin@example.com` | `password123` |
| Zaměstnanec | `zamestnanec@example.com` | `password123` |

> Seed vkládá uživatele přímo do `auth.users` a je určen **pouze pro lokální
> vývoj**. V produkci zakládejte uživatele přes Supabase Auth (Dashboard →
> Authentication); profil se vytvoří automaticky triggerem, roli `admin`
> nastavíte v tabulce `profiles`.

## Konfigurace Supabase (produkce / hosted projekt)

1. Vytvořte projekt na [supabase.com](https://supabase.com).
2. Aplikujte migrace: `supabase link --project-ref <ref>` a `supabase db push`.
3. V **Project Settings → API** zkopírujte *Project URL* a *anon public key*
   a nastavte je jako proměnné prostředí (lokálně `.env.local`, na Vercelu
   v Project Settings → Environment Variables):

   ```
   NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>
   ```

Aplikace používá výhradně anon key + RLS (žádný service-role key), takže
oprávnění vynucuje databáze i pro případ chyby v aplikační vrstvě.

## Příkazy

```bash
npm run dev     # vývojový server
npm run build   # produkční build
npm run lint    # ESLint
npm test        # unit testy (Vitest)
```

## Akceptační scénáře

- Zaměstnanec si založí výkaz aktuálního měsíce (víkendy/svátky se předvyplní).
- Každému pracovnímu dni přiřadí projekt — jednotlivě v dialogu, hromadně
  („Vybrat nevyplněné“ → projekt → „Vyplnit vybrané dny“), nebo tlačítkem
  „Zkopírovat minulý měsíc“.
- Nevyplněné pracovní dny jsou v kalendáři zvýrazněné a měsíc nelze odeslat,
  dokud nejsou doplněné.
- Po odeslání je výkaz pro zaměstnance jen ke čtení.
- Admin výkaz schválí, nebo vrátí s důvodem; vrácený výkaz jde upravit a
  znovu odeslat.
- Admin i zaměstnanec mohou stáhnout XLSX export výkazu.

## Mimo rozsah MVP

Fakturace, ERP integrace a pokročilý reporting záměrně nejsou součástí.
