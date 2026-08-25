# Driftsättning på bibliotekarien-vps

Följer plattformens standardmönster (jfr gribranker). Service-användare
`markrounding` med **UID 1504** (nästa lediga efter gribranker 1503).

## 1. Engångs-setup på servern

```bash
# Service-användare. --home-dir /opt/markrounding: skrivbart HOME krävs
# eftersom deploy.sh kör `docker compose build` via sudo -u -H (buildx
# skapar ~/.docker).
sudo useradd --system --uid 1504 --home-dir /opt/markrounding --shell /usr/sbin/nologin markrounding
sudo usermod -aG docker markrounding

sudo mkdir -p /opt/markrounding
sudo git clone <repo-url> /opt/markrounding/app
sudo chown -R markrounding:markrounding /opt/markrounding

# Secrets
cd /opt/markrounding/app
sudo -u markrounding cp .env.template .env
# Fyll i MARKROUNDING_SECRET (python3 -c "import secrets; print(secrets.token_hex(64))")
# och MARKROUNDING_ADMIN_PASSWORD_HASH (uv run markrounding hash-password)
sudo -u markrounding chmod 600 .env

# Första deploy
sudo /opt/markrounding/app/scripts/deploy.sh

# Autostart vid boot + nattlig backup
sudo cp deploy/markrounding.service /etc/systemd/system/
sudo cp deploy/markrounding-backup.service /etc/systemd/system/
sudo cp deploy/markrounding-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now markrounding.service markrounding-backup.timer
```

## 2. I plattform-repot (`/opt/bibliotekarien-platform`)

1. DNS: A-post för t.ex. `markrounding.bibliotekarien.se` → serverns IP.
2. `edge/docker-compose.yml`: lägg till nätet under `networks:`:

   ```yaml
   markrounding_proxy:
     external: true
   ```

   (och i caddy-servicens `networks:`-lista.)
3. `edge/Caddyfile`: nytt site-block. `/api/*` går direkt till web
   (XHR-klienter kan inte lösa Anubis PoW); all övrig trafik går genom
   Anubis:

   ```caddy
   markrounding.bibliotekarien.se {
       handle /api/* {
           reverse_proxy http://markrounding-web:8000
       }
       handle {
           reverse_proxy http://markrounding-anubis:8923 {
               header_up X-Real-Ip {remote_host}
               header_up X-Http-Version {http.request.proto}
           }
       }

       header {
           Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
           X-Content-Type-Options "nosniff"
           X-Frame-Options "DENY"
           Referrer-Policy "strict-origin-when-cross-origin"
           Content-Security-Policy "default-src 'self'; base-uri 'self'; connect-src 'self' https://tile.openstreetmap.org https://tiles.openseamap.org; font-src 'self'; frame-ancestors 'none'; img-src 'self' data: blob: https://tile.openstreetmap.org https://tiles.openseamap.org; object-src 'none'; script-src 'self' blob: 'wasm-unsafe-eval'; worker-src blob:; style-src 'self' 'unsafe-inline'; form-action 'self'"
       }

       log {
           output file /var/log/caddy/markrounding.log {
               roll_size 10mb
               roll_keep 5
           }
           format json
       }
   }
   ```

   CSP-noter: MapLibre GL kräver `worker-src blob:` och `script-src blob:`;
   `'wasm-unsafe-eval'` krävs för Anubis PoW-WASM; kartplattorna hämtas
   från OSM + OpenSeaMap (`connect-src`/`img-src`). Väderanropen går via
   backend (server-till-server mot Open-Meteo) och Matomo-trackingen är
   server-side, så ingen av dem behöver något i CSP:n.
4. **Ordning:** appstacken måste vara igång *före* edge-recreate (den skapar
   nätet som edge förväntar sig som external):
   `make -C /opt/bibliotekarien-platform edge-recreate`
5. Uppdatera `SERVER_LAYOUT.md` (stacks-, nätverks-, volym-tabellerna +
   "Senast uppdaterad").

## 3. Löpande deploy

Från din arbetsstation (kräver ssh-alias med sudo-rätt på servern;
default-värd `bibliotekarien-vps`, överstyr med `DEPLOY_HOST=`):

```bash
make deploy        # git pull + build + omstart på servern
make deploy-check  # dry-run: validera utan att applicera
make deploy-logs   # senaste 50 raderna från web-containern
```

Eller direkt på servern:

```bash
sudo /opt/markrounding/app/scripts/deploy.sh          # deploy
sudo /opt/markrounding/app/scripts/deploy.sh --check  # dry-run
```

## Matomo (server-side)

Trackingen sker från backend via Matomos Tracking HTTP API — ingen
JS-tracker i klienten. Setup:

1. Skapa en ny sajt i Matomo-admin på `bibstats.bibliotekarien.se`
   (Administration → Websites → Manage) → notera site-id.
2. Skapa en app-specifik `token_auth` (Administration → Personal →
   Security → Auth tokens) — krävs för att besökarens riktiga IP (`cip`)
   ska registreras i stället för containerns.
3. Sätt `MARKROUNDING_MATOMO_URL`, `MARKROUNDING_MATOMO_SITE_ID` och
   `MARKROUNDING_MATOMO_TOKEN` i `.env` och deploya om.

Egenskaper: cookie-fritt, respekterar DNT/Sec-GPC, hemliga rapport-tokens
maskeras (`/report/_token_`) innan URL:en skickas, endast dokumentladdningar
trackas (inte `/api`-polling eller assets). Begränsning: SPA-navigering
inom en laddad sida syns inte — bara sidladdningar.

## Anmärkningar

- Inga host-portar publiceras; edge når `markrounding-web:8000` och
  `markrounding-anubis:8923` via `markrounding_proxy`.
- `/api/*` går förbi Anubis (XHR kan inte lösa browser-PoW) — backendens
  rate limit på login är därför load-bearing, och rapporterings-endpoints
  skyddas av den hemliga tokenen.
- `ANUBIS_COOKIE_DOMAIN` i `.env` måste matcha det publika hostnamnet,
  annars accepteras inte clearance-cookien (känd tOPAC-fallgrop).
- **`$` i `.env`-värden måste escapas som `$$`** — lösenordshashen
  (`pbkdf2$260000$…`) tolkas annars av compose som variabelreferenser:
  varningen `The "…" variable is not set` betyder att hashen blev tom i
  containern. Se kommentaren i `.env.template`.
- **Skapa aldrig `markrounding_proxy` för hand** (`docker network create`).
  Compose vägrar ta över ett nät utan sina labels (`incorrect label
  com.docker.compose.network`). Rätt ordning: app-stacken skapar nätet
  (deploy.sh) → sedan `edge-recreate`. Har nätet skapats manuellt: koppla
  loss ev. containrar, `docker network rm markrounding_proxy`, deploya om.
- Named volume `markrounding-data` innehåller SQLite-filen med alla
  rundningar. Nattlig snapshot till `/opt/markrounding/backups`
  (14 dagars rotation) via `markrounding-backup.timer`.
- Restore: `gunzip` senaste snapshot, stoppa stacken, kopiera in filen i
  volymen (`docker cp` till `markrounding-web:/app/data/markrounding.sqlite`
  med stacken i stoppad web-container eller via en tillfällig container),
  starta igen.
