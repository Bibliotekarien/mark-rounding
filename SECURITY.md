# Säkerhet

## Rapportera en sårbarhet

Mejla **[security@bibliotekarien.se](mailto:security@bibliotekarien.se)** i
stället för att öppna ett publikt ärende. Svenska eller engelska går bra.

Ta gärna med:

- vad du hittat och var (endpoint, fil, version eller commit),
- hur det återskapas,
- vad en angripare skulle kunna göra med det.

Använd inte andras data, och gör inga överbelastningstester mot den publika
tjänsten. Samma kontaktadress finns i `/.well-known/security.txt` på våra
tjänster (RFC 9116).

## Versioner som stöds

Bara senaste commit på `main` — det är den som driftsätts.

## Vad som kontrolleras automatiskt

Varje pull request och varje commit på `main` kör, utöver testerna
(`.github/workflows/tests.yml`):

- en skanning efter hemligheter i **hela** git-historiken (gitleaks),
- en skanning av `uv.lock` och `frontend/package-lock.json` efter kända
  sårbarheter (osv-scanner),
- och på `main` en SBOM (CycloneDX) över beroendena, sparad som artefakt.

Se `.github/workflows/security-checks.yml`. Dependabot föreslår
uppdateringar av beroendena veckovis.

*English: report vulnerabilities to security@bibliotekarien.se, not in a
public issue.*
