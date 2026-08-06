from markrounding.sailarena import parse_event
from markrounding.sailarena import parse_participants
from markrounding.sailarena import participant_list_url

PARTICIPANT_HTML = """
<html><body>
<h1>Testregattan 2026</h1>
<table>
  <tr>
    <th>Förnamn</th><th>Efternamn</th><th>Klubb</th><th>Båttyp</th>
    <th>Båtnamn</th><th>Nationsbeteckning</th><th>Segelnummer</th>
    <th>Respittal SRS</th>
  </tr>
  <tr>
    <td>Lars Göran</td><td>Karlsson</td><td>KSSS</td><td>Omega 42</td>
    <td>Oriole</td><td>SWE</td><td>106</td><td>1,032</td>
  </tr>
  <tr>
    <td>Robert</td><td>Westerlind</td><td>Viggbyholms SS</td><td>Elan E3</td>
    <td>Relax</td><td>SWE</td><td>3031</td><td>0,961</td>
  </tr>
  <tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
</table>
</body></html>
"""


def test_parse_participants_maps_dynamic_headers():
    boats = parse_participants(PARTICIPANT_HTML)
    assert len(boats) == 2
    first = boats[0]
    assert first["sail_number"] == "106"
    assert first["boat_name"] == "Oriole"
    assert first["boat_type"] == "Omega 42"
    assert first["club"] == "KSSS"
    assert first["nation"] == "SWE"
    assert first["srs"] == "1,032"
    assert first["skipper"] == "Lars Göran Karlsson"


CREW_AND_GROUPS_HTML = """
<html><body>
<table>
  <tr><th>Förnamn</th><th>Efternamn</th><th>Klubb</th><th>Båtnamn</th><th>Segelnummer</th></tr>
  <tr><td>Lars</td><td>Karlsson</td><td>KSSS</td><td>Oriole</td><td>106</td></tr>
  <tr><td>Anders</td><td>Gille</td><td></td><td></td><td></td></tr>
  <tr><td>Kajsa</td><td>Tesch</td><td></td><td></td><td></td></tr>
  <tr><td>Robert</td><td>Westerlind</td><td>VSS</td><td>Relax</td><td>3031</td></tr>
</table>
<table>
  <tr><th>Förnamn</th><th>Efternamn</th><th>Klubb</th><th>Båtnamn</th><th>Segelnummer</th></tr>
  <tr><td>Lars</td><td>Karlsson</td><td>KSSS</td><td>Oriole</td><td>106</td></tr>
  <tr><td>Eva</td><td>Nilsson</td><td>GKSS</td><td>Vinga</td><td>77</td></tr>
</table>
</body></html>
"""


def test_parse_participants_skips_crew_rows_and_dedupes_tables():
    boats = parse_participants(CREW_AND_GROUPS_HTML)
    assert [b["sail_number"] for b in boats] == ["106", "3031", "77"]
    assert all(b.get("sail_number") for b in boats)


def test_parse_participants_no_table():
    assert parse_participants("<html><body><p>Ingen lista</p></body></html>") == []


EVENT_HTML = """
<html><head><title>Testregattan 2026 | Sailarena</title></head><body>
<h1>Testregattan 2026</h1>
<script>var map = {"latitude": 59.78221910000001, "longitude": 17.6271419};</script>
<p>2026-06-19 till 2026-06-20</p>
<a href="/sv/se/club/uss/testregattan-2026/ParticipantList/">Deltagarlista</a>
</body></html>
"""


def test_parse_event_metadata():
    event = parse_event(EVENT_HTML, "https://www.sailarena.com/sv/se/club/uss/testregattan-2026")
    assert event["name"] == "Testregattan 2026"
    assert abs(event["lat"] - 59.7822191) < 1e-6
    assert abs(event["lon"] - 17.6271419) < 1e-6
    assert event["start_date"] == "2026-06-19"
    assert event["end_date"] == "2026-06-20"
    assert event["participant_list_url"].endswith("/ParticipantList/")


def test_participant_list_url():
    assert participant_list_url("https://x.se/club/a/b") == "https://x.se/club/a/b/ParticipantList/"
    assert participant_list_url("https://x.se/club/a/b/ParticipantList") == (
        "https://x.se/club/a/b/ParticipantList"
    )
