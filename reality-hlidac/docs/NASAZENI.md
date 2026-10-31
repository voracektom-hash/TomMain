# Nasazení Reality Hlídače – krok za krokem

Návod pro úplného začátečníka. U každého kroku je napsáno, **v jaké aplikaci** ho děláš.
Celkem asi 45 minut, většinu času se čeká.

| Krok | Kde | Čas | Cena |
|---|---|---|---|
| 0. Vyzkoušet appku v prohlížeči (nepovinné) | GitHub Codespaces | 10 min | zdarma |
| 1. Server | Oracle Cloud (web) | 15 min | zdarma natrvalo |
| 2. Otevřít porty | Oracle Cloud (web) | 3 min | – |
| 3. Připojit se na server | Terminál na Macu | 2 min | – |
| 4. Instalace | Terminál (na serveru) | 10 min | – |
| 5. iPhone | Safari + aplikace ntfy | 5 min | zdarma |

Kdyby Oracle nešel (registrace, „Out of capacity“), použij **Hetzner** – návod je na konci
(asi 4,5 € měsíčně, jinak stejný postup).

---

## 0. Vyzkoušet appku bez serveru (GitHub Codespaces, nepovinné)

Dočasný počítač v prohlížeči, zdarma 60 hodin měsíčně. Hodí se na proklikání appky.
Po 30 minutách nečinnosti se uspí, takže **na nepřetržité hlídání není**.

1. **Prohlížeč (Safari/Chrome na laptopu):** otevři
   https://github.com/voracektom-hash/TomMain/tree/claude/eager-thompson-a4ggql
   a přihlas se na GitHub.
2. Zelené tlačítko **Code** → záložka **Codespaces** → **Create codespace on claude/eager-…**
3. Počkej 2–3 minuty, než se vše nainstaluje (dole běží terminál).
4. **Terminál dole v Codespaces** – napiš a potvrď Enterem:
   ```bash
   cd reality-hlidac
   .venv/bin/python -m hlidac.users add Tomas --admin     # vypíše heslo
   make dev                                                # spustí hlídač i appku
   ```
5. Vpravo dole vyskočí **Open in Browser** (nebo záložka **Ports** → 8000 → ikona glóbu).
6. Přihlas se jménem `Tomas` a heslem z kroku 4. Prvních ~5 minut se načítá nabídka Prahy,
   pak zkus **Pravidla → + Nové** a sleduj **Náhled** dole.
7. Konec: v terminálu `Ctrl+C`. Codespace smažeš na https://github.com/codespaces.

---

## 1. Server zdarma: Oracle Cloud „Always Free“

**Aplikace: prohlížeč na laptopu.**

1. Otevři https://signup.cloud.oracle.com a založ účet.
   - **Home Region:** vyber **Germany Central (Frankfurt)** – blízko Prahy. Později nejde změnit.
   - Platební karta slouží jen k ověření; dokud nepřepneš na placený účet, nic se neúčtuje.
2. Po přihlášení: menu ☰ vlevo nahoře → **Compute** → **Instances** → **Create instance**.
3. Vyplň:
   - **Name:** `hlidac`
   - **Image and shape → Edit:**
     - **Image:** *Change image* → **Canonical Ubuntu** → verze **24.04** → *Select image*.
     - **Shape:** *Change shape* → **Ampere** → **VM.Standard.A1.Flex**, 1 OCPU, 6 GB paměti
       (u tvaru musí být štítek *Always Free-eligible*).
   - **Networking:** nech výchozí, zkontroluj **Assign a public IPv4 address = Yes**.
   - **Add SSH keys:** **Generate a key pair for me** → klikni **Save private key**
     (stáhne se soubor `ssh-key-….key` do Stažených souborů – **neztrať ho**, je to klíč od serveru).
4. **Create.** Za 1–2 minuty bude stav **Running**. Na stránce instance si opiš
   **Public IP address** (např. `141.147.12.34`).

> **„Out of capacity“?** Zdarma servery Ampere bývají ve Frankfurtu občas rozebrané.
> Zkus jinou *Availability domain* (AD-2, AD-3), nebo to zkus za pár hodin.
> Případně tvar **VM.Standard.E2.1.Micro** (také Always Free, slabší, ale stačí).

---

## 2. Otevřít porty 80 a 443 (Oracle)

**Aplikace: prohlížeč (Oracle Cloud).** Bez tohoto kroku nepůjde HTTPS.

1. Na stránce instance klikni v části *Primary VNIC* na odkaz **Subnet** (např. `subnet-2026…`).
2. Záložka **Security** (u starší verze vlevo **Security Lists**) → **Default Security List for vcn-…**
3. **Add Ingress Rules** a přidej dvě pravidla:

   | Source CIDR | IP Protocol | Destination Port Range |
   |---|---|---|
   | `0.0.0.0/0` | TCP | `80` |
   | `0.0.0.0/0` | TCP | `443` |

4. **Add Ingress Rules** (uložit). Port 22 pro SSH už tam je.

---

## 3. Připojit se na server

**Aplikace: Terminál na Macu** (Spotlight ⌘+mezerník → napiš „Terminál“).

```bash
chmod 600 ~/Downloads/ssh-key-*.key
```
↑ Zamkne klíč, aby ho mohl číst jen tvůj účet (jinak ho SSH odmítne použít).

```bash
ssh -i ~/Downloads/ssh-key-*.key ubuntu@141.147.12.34
```
↑ Připojí tě na server. Místo `141.147.12.34` napiš svou Public IP.
Na otázku *„Are you sure you want to continue connecting?“* napiš `yes`.
Když vidíš `ubuntu@hlidac:~$`, jsi na serveru – všechny další příkazy píšeš sem.

---

## 4. Instalace (na serveru)

**Aplikace: Terminál, připojený na server.**

```bash
sudo apt-get update && sudo apt-get install -y git
```
↑ Nainstaluje git, kterým si stáhneš program.

```bash
git clone -b claude/eager-thompson-a4ggql https://github.com/voracektom-hash/TomMain.git
```
↑ Stáhne Reality Hlídač z GitHubu do složky `TomMain`.

```bash
cd TomMain/reality-hlidac
```
↑ Přepne do složky s programem.

```bash
sudo ./scripts/install.sh
```
↑ Udělá zbytek: nainstaluje Docker, otevře firewall, vytvoří nastavení, spustí hlídač,
appku, HTTPS a zálohy, ověří spojení se Sreality a založí tvůj účet.

Skript se zeptá na **jméno pro přihlášení** a nakonec vypíše:
- **adresu**, např. `https://hlidac.141-147-12-34.sslip.io`
- **heslo** – opiš si ho (nebo ho rovnou ulož do Klíčenky).

---

## 5. iPhone

**Aplikace: Safari.**
1. Otevři adresu z instalace, přihlas se.
2. **Sdílet** (čtvereček se šipkou) → **Přidat na plochu** → *Přidat*. Na ploše máš ikonu Hlídač.

**Aplikace: App Store → ntfy** (zdarma). Nainstaluj a povol notifikace.

**Aplikace: Hlídač (z plochy) → Nastavení.** Je tam tvůj osobní ntfy kanál a návod:
1. **ntfy:** klepni na **+**, zadej kanál, server nech výchozí.
2. **Nastavení iPhonu → Oznámení → ntfy:** zapni **Časově citlivá oznámení**
   (pro prioritu „nejvyšší“).
3. **Nastavení iPhonu → Soustředění** (Spánek, Nerušit…) → povol časově citlivá oznámení.
4. **Hlídač → Nastavení → Poslat testovací notifikaci** – měla by přijít do pár sekund.

Pak **Pravidla → + Nové**, nastav lokalitu a kritéria, **Náhled** ukáže, kolik bytů
by pravidlo chytilo. Uložit. Hotovo – nové byty ti budou chodit na telefon.

### Kamarád
**Hlídač → Nastavení → Uživatelé → Přidat.** Appka vygeneruje heslo. Pošli mu adresu
a heslo; on udělá krok 5 na svém iPhonu (ntfy kanál najde ve svém Nastavení).

---

## Údržba

Vždy nejdřív **Terminál na Macu** → `ssh -i ~/Downloads/ssh-key-*.key ubuntu@<IP>` →
`cd TomMain/reality-hlidac`.

| Co | Příkaz | Co dělá |
|---|---|---|
| Stav | `sudo docker compose ps` | ukáže, jestli všechny 4 části běží |
| Logy hlídače | `sudo docker compose logs -f watcher` | živý výpis (nové byty, chyby); konec `Ctrl+C` |
| Logy appky | `sudo docker compose logs --tail 50 web` | posledních 50 řádků |
| Aktualizace | `sudo ./scripts/update.sh` | stáhne novou verzi a restartuje; data zůstanou |
| Restart | `sudo docker compose restart` | restartuje vše |
| Záloha hned | `sudo docker compose exec backup python -m hlidac.backup --now` | uloží zálohu teď |
| Seznam záloh | `ls data/backups` | zálohy posledních 7 dní |
| Nové heslo | `sudo docker compose exec web python -m hlidac.users passwd Tomas` | když heslo zapomeneš |
| Zastavit | `sudo docker compose down` | vypne vše (data zůstanou) |

**Stažení zálohy na Mac** (Terminál na Macu, ne na serveru):
```bash
scp -i ~/Downloads/ssh-key-*.key "ubuntu@<IP>:TomMain/reality-hlidac/data/backups/*" ~/Downloads/
```

**Obnova ze zálohy** (na serveru):
```bash
sudo docker compose stop watcher web
gunzip -c data/backups/hlidac-2026-11-05.db.gz | sudo tee data/hlidac.db > /dev/null
sudo rm -f data/hlidac.db-wal data/hlidac.db-shm
sudo docker compose start watcher web
```

Zálohy leží na stejném serveru – chrání proti chybě v datech, ne proti ztrátě serveru.
Občas si je stáhni na Mac (příkaz výš).

---

## Když něco nejde

| Příznak | Řešení |
|---|---|
| Adresa se v Safari nenačte | Porty 80/443 nejsou otevřené (krok 2). Pak na serveru `sudo docker compose restart caddy`. |
| Stav v appce červený, „Sreality neodpovídá“ | `sudo docker compose logs --tail 30 watcher`. Při HTTP 403/429 Sreality IP serveru blokuje – napiš mi. |
| Testovací notifikace nepřišla | Hlídač → Historie: u zprávy je chyba. „429 limit“ = vyčerpaný limit ntfy (250/den na server). |
| SSH: „Permission denied (publickey)“ | Špatný klíč nebo chybí `chmod 600` (krok 3). U Oracle je uživatel `ubuntu`, u Hetzneru `root`. |
| Zapomenuté heslo | Příkaz „Nové heslo“ v tabulce Údržba. |

---

## Alternativa: Hetzner (~4,5 €/měsíc)

**Aplikace: Terminál na Macu** – vytvoř si SSH klíč (jednou):
```bash
ssh-keygen -t ed25519 -f ~/.ssh/hlidac -N ""
cat ~/.ssh/hlidac.pub
```
↑ První příkaz vytvoří klíč, druhý vypíše jeho veřejnou část – celý řádek zkopíruj.

**Aplikace: prohlížeč** – https://console.hetzner.cloud:
1. Zaregistruj se, vytvoř projekt → **Add Server**.
2. **Location:** Falkenstein nebo Nuremberg · **Image:** Ubuntu 24.04 ·
   **Type:** Shared vCPU → x86 → nejmenší (CX22).
3. **SSH keys → Add SSH key** → vlož zkopírovaný řádek.
4. **Create & Buy now**, opiš si IP.

**Terminál na Macu:** `ssh -i ~/.ssh/hlidac root@<IP>` a pak krok 4 výš
(u Hetzneru jsi rovnou `root`, `sudo` ničemu nevadí). Porty Hetzner ve výchozím stavu
neblokuje.

---

## Středočeský kraj

Zatím se hlídá jen Praha. Rozšíření (na serveru):
```bash
sudo sed -i 's/^REGION_IDS=.*/REGION_IDS=10,11/' .env && sudo docker compose up -d
```
↑ Přidá Středočeský kraj (11) a restartuje. Watcher si nové byty načte sám.
