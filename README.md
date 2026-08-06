# Mark-rounding

Följ en kappsegling (och därmed en regatta) live: en representant för
tävlingskommittén rapporterar vilken båt som rundat vilket märke, och alla
andra kan se hur racet utvecklas i realtid.

## Så fungerar det

- **Admin** loggar in, definierar en regatta (namn, plats med koordinater,
  datum, bana som ordnad lista av märken, antal race) och hämtar
  deltagarlistan från Sailarena genom att klistra in evenemangets URL
  (Sailarena saknar API — deltagartabellen skrapas från den publika
  HTML-sidan med dynamisk kolumnmappning). Listan kan redigeras fritt.
- Admin skickar en **hemlig rapporterings-URL** till kommittén. Ingen
  inloggning krävs — länken i sig ger rätt att rapportera just den regattan.
- **Kommittérepresentanten** väljer race och märke och klickar på
  segelnummer vartefter båtarna passerar. Det går att bläddra fritt mellan
  märken (olika båtar har kommit olika långt), ångra felklick, byta
  race-status samt lägga till/avaktivera båtar som tillkommit eller utgått.
- **Startproceduren** (RRS 26) sköts från samma vy: armera en nedräkning
  med valfri förberedelseflagga (P/I/Z/U/svart), skjut upp (AP), bekräfta
  startsignalen, gör allmän återkallelse — och markera tjuvstarter (OCS)
  och straff (UFD/BFD/ZFP/DNS/DNF/RET/DSQ) genom att trycka på båtarna.
  Alla åtgärder loggas automatiskt i ett **protokoll** per race, där
  startfartyget också kan skriva fritextanteckningar.
- **Publiken** ser en startsida med kommande regattor på karta, och en
  regattasida där man följer aktuellt race: ställning, rundningsordning
  per märke med tidsgap till ledaren, och ett utvecklingsdiagram som visar
  hur avstånden ökar och minskar märke för märke. Man bläddrar fritt
  mellan tidigare och kommande race. Varje pågående
  och avslutat race har en väderruta med rådande och prognostiserat väder
  (Open-Meteo).

## Arkitektur

Samma mönster som gribranker: ett Python-paket i repo-roten med FastAPI
som äger `/api`-prefixet och serverar den byggda Vue-SPA:n ur
`frontend/dist` — en enda container i produktion. Lagring i SQLite
(rå `sqlite3`, WAL, idempotent schema, inga migrations).

```
markrounding/        app-paketet
  api/               FastAPI: app-factory + public/report/admin-routrar
  db.py              SQLite-schema och hjälpfunktioner
  auth.py            admin-lösenord (PBKDF2) + JWT + rate limit
  sailarena.py       skrapning av Sailarenas evenemangs-/deltagarsidor
  weather.py         Open-Meteo med 10-minuterscache
frontend/            Vue 3 + Vite + vue-router + MapLibre GL
tests/               pytest
scripts/             deploy.sh, backup.sh
deploy/              systemd-units + driftsättningschecklista
```

## Lokal utveckling

```bash
uv sync                                  # backend-beroenden
uv run markrounding serve --reload       # API på http://127.0.0.1:8000

cd frontend
npm install
npm run dev                              # SPA på http://127.0.0.1:5173 (proxar /api)
```

Utan `MARKROUNDING_ADMIN_PASSWORD_HASH` är admin-lösenordet `admin`
(endast i utvecklingsläge — produktion vägrar starta utan satta secrets).

## Test

```bash
uv run pytest
uv run ruff check
```

## Produktion

Se `deploy/README.md`. Kort: multi-stage-Dockerfile (Node bygger SPA:n,
Python-imagen serverar allt), `docker-compose.prod.yml` standalone utan
host-portar bakom plattformens edge-Caddy, service-användare `markrounding`
(UID 1504), named volume `markrounding-data` för SQLite-filen. Anubis
PoW-gatar HTML-trafiken (`/api/*` går förbi), och Matomo-analytics sker
server-side via Tracking HTTP API — cookie-fritt, DNT-respekterande,
ingen tracker-JS i klienten.
