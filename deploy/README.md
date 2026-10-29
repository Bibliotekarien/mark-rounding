# Driftsättning på bibliotekarien-vps

Service-användare `markrounding` med **UID 1504** (nästa lediga efter
gribranker 1503). Containern kör som samma uid. Användaren äger ingenting
på värden och sitter **inte** i docker-gruppen; arbetskopian är root-ägd och
deploy.sh kör git och docker som root. Varför: se "Root-ägd arbetskopia"
nedan.

## 1. Engångs-setup på servern

```bash
# Service-användare: bara för att uid 1504 ska ha ett namn på värden.
sudo useradd --system --uid 1504 --home-dir /opt/markrounding --shell /usr/sbin/nologin markrounding

sudo mkdir -p /opt/markrounding    # root-ägd, 755
sudo git clone https://github.com/Bibliotekarien/mark-rounding.git /opt/markrounding/app
sudo chmod -R go-w /opt/markrounding/app

# Secrets
cd /opt/markrounding/app
sudo install -m 600 .env.template .env
# Fyll i MARKROUNDING_SECRET (python3 -c "import secrets; print(secrets.token_hex(64))")
# och MARKROUNDING_ADMIN_PASSWORD_HASH (uv run markrounding hash-password)
sudoedit .env

# SELinux: en kopia som klonats under en hemkatalog och flyttats hit får
# etiketten user_home_t, och då får systemd inte köra backup.sh.
sudo restorecon -R /opt/markrounding/app

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

Din vardagsanvändare på servern behöver inte (och bör inte ha) generell
sudo — ge den i stället rätt att köra exakt deploy-skriptet som root.
Engångs på servern:

```bash
sudo tee /etc/sudoers.d/markrounding-deploy <<'EOF'
<användarnamn> ALL=(root) NOPASSWD: /opt/markrounding/app/scripts/deploy.sh
EOF
sudo chmod 440 /etc/sudoers.d/markrounding-deploy
sudo visudo -c   # validera innan du loggar ut
```

Regeln anger kommandot utan argumentlista och täcker därför även
`--check` och `--logs`. Den är bara säker för att skriptet är root-ägt:
kunde någon annan skriva i `/opt/markrounding/app` skulle regeln ge dem
root utan lösenord. deploy.sh vägrar därför köra om arbetskopian inte är
root-ägd. Den som kontrollerar main på GitHub kontrollerar fortfarande
servern, eftersom deployen kör det som ligger på main.

## Root-ägd arbetskopia

Tidigare ägde `markrounding` arbetskopian och satt i docker-gruppen, och
deploy.sh körde git och compose som den användaren. Två vägar till root
följde av det:

- **docker-gruppen är root.** Den som kan prata med docker-socketen kan
  starta en container som monterar `/`. Containern kör som uid 1504, så ett
  utbrott ur containern hade landat precis hos en användare med den rätten.
- **root körde filer som markrounding kunde skriva:** deploy.sh (via sudo),
  backup.sh (via `markrounding-backup.timer`, som kör som root) och
  compose-filen.
- **markrounding ägde `/opt/markrounding`** och kunde därmed byta ut hela
  arbetskopian (`mv app x; mkdir app`), skript och allt. deploy.sh kontrollerar
  därför också katalogen ovanför.

Nu är arbetskopian root-ägd, git och compose körs som root, och
`markrounding` är bara ett namn på uid 1504. Det här är piloten för
SECURITY_REVIEW.md Risk 1 i bibliotekarien-platform; övriga appar följer
efter.

**Flytta en befintlig server** (en gång; den nya deploy.sh vägrar köra
innan). Ordningen spelar roll: först ägarbytet, sedan hämtas den nya koden
som root, sedan tas gruppen bort.

```bash
sudo chown root:root /opt/markrounding    # inte -R: bara katalogen själv
sudo chmod 755 /opt/markrounding
sudo chown -R root:root /opt/markrounding/app
sudo git -C /opt/markrounding/app pull --ff-only
sudo chmod -R go-w /opt/markrounding/app
sudo chmod 600 /opt/markrounding/app/.env
sudo restorecon -R /opt/markrounding/app
sudo gpasswd -d markrounding docker
sudo cp /opt/markrounding/app/deploy/markrounding.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Kontrollera sedan:

```bash
id markrounding                                # ingen docker i grupperna
sudo /opt/markrounding/app/scripts/deploy.sh   # går igenom ägarkontrollen
sudo systemctl start markrounding-backup.service
sudo journalctl -u markrounding-backup.service -n 5 --no-pager
```

Från din arbetsstation (kräver ssh-alias till servern; default-värd
`bibliotekarien-vps`, överstyr med `DEPLOY_HOST=`):

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
