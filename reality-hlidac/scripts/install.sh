#!/usr/bin/env bash
# Reality Hlídač – one-command install on a fresh Ubuntu server (Oracle Cloud Free, Hetzner…).
#
#   sudo ./scripts/install.sh
#
# Safe to run again: keeps your .env, data and accounts; only rebuilds and restarts.
set -euo pipefail
cd "$(dirname "$0")/.."

say()  { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓ %s\033[0m\n' "$*"; }
warn() { printf '  \033[33m! %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Spusť přes sudo: sudo ./scripts/install.sh"; exit 1; }

say "1/7 Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true
ok "$(docker --version)"

say "2/7 Firewall na serveru (porty 80 a 443)"
# Oracle's Ubuntu images block everything except SSH with iptables rules.
if iptables -S INPUT 2>/dev/null | grep -q -- "-j REJECT"; then
  for port in 80 443; do
    iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
      || iptables -I INPUT 1 -p tcp --dport "$port" -j ACCEPT
  done
  if command -v netfilter-persistent >/dev/null 2>&1; then netfilter-persistent save >/dev/null 2>&1; fi
  ok "iptables: povoleno 80 a 443"
fi
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null && ok "ufw: povoleno 80 a 443"
fi
ok "hotovo (u Oracle navíc musí být porty otevřené v Security List, viz návod)"

say "3/7 Nastavení (.env)"
IP=$(curl -fsS -4 https://api.ipify.org || curl -fsS -4 https://ifconfig.me)
SITE="hlidac.${IP//./-}.sslip.io"
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s/^REGION_IDS=.*/REGION_IDS=10/" .env
  sed -i "s/^NOTIFY_CHANNELS=.*/NOTIFY_CHANNELS=ntfy/" .env
  sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
  sed -i "s/^SITE_ADDRESS=.*/SITE_ADDRESS=$SITE/" .env
  chmod 600 .env
  ok "vytvořen .env (adresa $SITE)"
else
  SITE=$(grep -E '^SITE_ADDRESS=' .env | cut -d= -f2-)
  ok "ponechán stávající .env (adresa $SITE)"
fi
mkdir -p data && chown 1000:1000 data

say "4/7 Sestavení a spuštění (první build trvá pár minut)"
docker compose up -d --build
for _ in $(seq 1 60); do
  docker compose exec -T web python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)" \
    >/dev/null 2>&1 && break
  sleep 2
done
ok "běží: $(docker compose ps --format '{{.Service}}' | tr '\n' ' ')"

say "5/7 Kontrola Sreality ze serveru"
if docker compose exec -T web python -c "
import json, urllib.request
r = urllib.request.Request('https://www.sreality.cz/api/v1/estates/search?category_type_cb=1&category_main_cb=1&locality_region_id=10&limit=1',
                           headers={'User-Agent': 'Mozilla/5.0'})
d = json.load(urllib.request.urlopen(r, timeout=15)); assert d['pagination']['total'] > 0
" >/dev/null 2>&1; then
  ok "Sreality odpovídá – IP serveru není blokovaná"
else
  warn "Sreality ze serveru neodpovídá. Podívej se na: docker compose logs watcher"
fi

say "6/7 Účet správce"
if docker compose exec -T web python -m hlidac.users list | grep -q .; then
  ok "účty už existují: $(docker compose exec -T web python -m hlidac.users list | cut -d' ' -f2 | tr '\n' ' ')"
else
  read -r -p "  Tvoje jméno pro přihlášení [Tomas]: " NAME </dev/tty || NAME=""
  docker compose exec -T web python -m hlidac.users add "${NAME:-Tomas}" --admin
fi

say "7/7 Automatické bezpečnostní aktualizace Ubuntu"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades >/dev/null 2>&1 \
  && ok "zapnuto" || warn "nepodařilo se, nevadí"

printf '\nČekám na HTTPS certifikát'
for _ in $(seq 1 30); do
  curl -fsS -o /dev/null "https://$SITE/healthz" 2>/dev/null && { printf ' ✓\n'; break; }
  printf '.'; sleep 3
done

cat <<EOF

════════════════════════════════════════════════════════════
  Reality Hlídač běží:   https://$SITE

  1. Otevři adresu v Safari na iPhonu a přihlas se (heslo výš).
  2. Sdílet → Přidat na plochu.
  3. Nastavení v appce → návod na ntfy notifikace.

  Prvních ~5 minut watcher načítá celou nabídku Prahy.
  Logy:        docker compose logs -f watcher
  Aktualizace: sudo ./scripts/update.sh
════════════════════════════════════════════════════════════
EOF
if ! curl -fsS -o /dev/null "https://$SITE/healthz" 2>/dev/null; then
  warn "HTTPS zatím neodpovídá. Nejčastěji nejsou otevřené porty 80/443 u poskytovatele"
  warn "(Oracle: Security List, Hetzner: Firewall). Pak stačí: docker compose restart caddy"
fi
