# Mark-rounding — konventioner

Följ kappseglingar live: tävlingskommittén rapporterar märkesrundningar via
en hemlig URL, publiken följer race och regattor. Läs `README.md`
(arkitektur, lokal setup) och `deploy/README.md` (produktion) vid behov.

## Kommandon

- `uv sync` — installera beroenden
- `uv run pytest` — kör tester
- `uv run markrounding serve --reload` — dev-server (API + ev. byggd SPA)
- `uv run markrounding init-db | hash-password` — CLI
- `cd frontend && npm run dev` — Vite-dev-server (proxar `/api` till :8000)

## Regler

- **Språk**: domändokumentation och UI-strängar på svenska; kod, kommentarer
  och commit-meddelanden på engelska. Användarvända felmeddelanden från
  API:t på svenska.
- **Tid**: alla tidsstämplar ISO-8601 UTC (`...Z`). Rendering i lokal tid
  sker i frontend.
- **Lagring**: rå `sqlite3` (stdlib), WAL, inga migrations — schemat är
  idempotent (`CREATE TABLE IF NOT EXISTS`) och appliceras vid varje start.
  Additiva schemaändringar görs som idempotenta `ALTER TABLE`-steg.
- **Auth**: en enda admin (PBKDF2-hash i env + JWT). Kommittérapportering
  auktoriseras enbart av regattans hemliga token — inga endpoints under
  `/api/report/{token}/` får läcka data för andra regattor.
- **Sailarena har inget API** — deltagarlistor skrapas från publik HTML med
  dynamisk kolumnmappning (`sailarena.py`). Arrangörer väljer kolumner
  själva, så parsern måste tåla varierande tabellstrukturer, flera tabeller
  per sida (startgrupper) och besättningsrader utan segelnummer. Skrapa
  skonsamt och tåla fel.
- **Väder**: Open-Meteo, cachas 10 min per koordinat i processen. m/s,
  grader (från), WMO-koder.
- **Matomo är server-side** (`matomo.py`, Tracking HTTP API från
  middleware) — ingen JS-tracker i klienten. Fire-and-forget, respekterar
  DNT/Sec-GPC, maskerar rapport-tokens, trackar endast dokumentladdningar.
  Av i dev (kräver `MARKROUNDING_MATOMO_URL` + `_SITE_ID`).
- **Anubis** PoW-gatar HTML-trafik i prod; `/api/*` går förbi — tokens och
  rate limits i backend är därför load-bearing.
- **Banor**: en regatta har ett bibliotek av namngivna banor (`courses`),
  märken hör till en bana och varje race pekar på sin bana (`course_id`,
  låst när racet startat). Banbyte per race loggas i protokollet. En bana
  med rapporterade rundningar kan inte tas bort. Avkortad bana (flagga S,
  RRS 32) = `POST .../shorten`: sätter `shortened=1` + avslutar racet —
  rundningarna vid senaste märket är målgången.
- **Rundningar**: append + delete (ångra), aldrig update. UNIQUE
  (race, märke, båt) — dubbelklick ger 409 som UI:t hanterar tyst via
  refresh. Rapporteringsvyn spärrar båtknapparna på ett märke när ett
  senare märke redan har rundningar — kommittén väljer uttryckligen
  efterregistrering eller hoppar till märket där registreringen
  naturligt fortsätter.
- **Tidsvisning**: `regattas.show_times` (default på) styr om
  rundningstider publiceras. Av: publika API:t strippar `ts`,
  `gap_seconds` och `last_ts` server-side (ordningen behålls) och
  utvecklingsgrafen visar placering per märke i stället för tid efter
  ledaren. Kommittéendpoints skickar alltid tider.
- **Startprocedur** (RRS 26): `planned_start` + `prep_flag`
  (P/I/Z/U/BLACK) på race; nedräkningen renderas i frontend från
  `planned_start` (servern är tidsauktoritet). Allmän återkallelse nollar
  start men behåller båtkoder (svart flagg överlever omstart, RRS 30.4 —
  kommittén rensar manuellt). Båtkoder i `race_boat_status` (OCS/UFD/BFD/
  ZFP/DNS/DNF/RET/DSQ, en per båt och race); ZFP behåller placering i
  leaderboard, övriga sorteras sist.
- **Protokoll**: alla kommittéåtgärder loggas automatiskt i `race_log`
  (+ fritextanteckningar). Append-only — protokollet redigeras aldrig.
  Enda undantaget är admins nollställning av ett race
  (`POST /api/admin/regattas/{id}/races/{n}/reset`): den raderar racets
  rundningar, båtkoder, startdata och protokoll och lämnar en enda
  `race_reset`-rad. Medvetet inte åtkomlig via kommitténs rapport-token.

## Struktur

`markrounding/` app-paketet · `api/` FastAPI (factory i `app.py`, routrar
`public`/`report`/`admin`) · `frontend/` Vue 3 + Vite + vue-router +
MapLibre · `tests/` pytest · `scripts/` deploy/backup · `deploy/`
systemd-units + driftchecklista

## Before you finish

`uv run pytest` + `uv run ruff check` + (vid frontend-ändringar)
`cd frontend && npm run lint && npm run build`.
