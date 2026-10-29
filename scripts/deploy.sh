#!/bin/bash
# Deploy för mark-rounding på bibliotekarien-vps.
#
# Kör som root (eller via sudo). git och docker körs som root, och
# arbetskopian ska vara root-ägd och bara skrivbar för root.
# Flöde: ägarkontroll → git fetch → merge --ff-only → docker compose build
# → up -d → status.
#
# Varför root och inte service-användaren: root kör filer ur arbetskopian
# (det här skriptet, backup.sh via timern, compose-filen). Ägde markrounding
# dem kunde den användaren skriva kod som root sedan körde. Containern kör
# som uid 1504, samma som markrounding, så ett utbrott ur containern hade
# gett just den användaren. Därför ska markrounding inte heller sitta i
# docker-gruppen: den gruppen är root i praktiken (SECURITY_REVIEW.md
# Risk 1 i bibliotekarien-platform).
#
# Flaggor:
#   --check / --dry-run   Hämta och validera, men rör inte arbetskopian
#   --logs                Visa senaste loggraderna från web-containern
#   -h / --help           Visa denna hjälptext
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/markrounding/app}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
CHECK_ONLY=0
LOGS_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --check|--dry-run) CHECK_ONLY=1 ;;
    --logs) LOGS_ONLY=1 ;;
    -h|--help) sed -n '2,/^set -e/p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "Okänd flagga: $arg" >&2; exit 2 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Detta skript måste köras som root (eller via sudo)." >&2
  exit 1
fi

# Vägra köra om någon annan än root kan skriva i arbetskopian. Annars kör
# root kod som en mindre privilegierad användare har kunnat ändra.
# Symlänkar har alltid 777 och hoppas över; det som räknas är målet.
# `|| true`: när head slutar läsa får find SIGPIPE, och med pipefail hade
# skriptet då dött tyst här i stället för att säga vad som är fel.
osakra=$(find "$APP_DIR" ! -type l \( ! -user root -o -perm /022 \) -print | head -5 || true)
if [[ -n "$osakra" ]]; then
  echo "Arbetskopian $APP_DIR är inte root-ägd och skrivskyddad för andra, t.ex.:" >&2
  echo "$osakra" >&2
  echo "Rätta enligt deploy/README.md, \"Root-ägd arbetskopia\":" >&2
  echo "  chown -R root:root $APP_DIR && chmod -R go-w $APP_DIR" >&2
  exit 1
fi

if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "VARNING: $APP_DIR/.env saknas — compose kommer vägra starta utan secrets." >&2
fi

cd "$APP_DIR"
compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# --logs: bara läsa, ingen deploy. Ligger i det här skriptet så att en
# enda sudoers-regel (utan argumentlista) täcker alla make-målen.
if [[ $LOGS_ONLY -eq 1 ]]; then
  compose logs --tail 50 web
  exit 0
fi

# Fetch och merge är skilda åt så att --check inte rör arbetskopian: en
# dry-run som drar in ny kod lämnar disken före de körande containrarna.
echo "==> Hämtar senaste koden (utan att röra arbetskopian)"
git fetch --quiet
git --no-pager log --format='    %h  %an  %s' 'HEAD..@{u}'

if [[ $CHECK_ONLY -eq 1 ]]; then
  echo "==> Dry-run: validerar compose-konfigurationen (nuvarande checkout)"
  compose config >/dev/null && echo 'compose config OK'
  exit 0
fi

echo "==> Uppdaterar arbetskopian (fast-forward)"
git merge --ff-only '@{u}'

echo "==> Bygger lokala images"
compose build

echo "==> Startar om stacken"
compose up -d

compose ps
compose logs --tail 15 web
echo "==> Klart."
