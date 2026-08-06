"""Scrape Sailarena event pages.

Sailarena has no public API; both the event presentation page and the
participant list ("Deltagarlista") are server-rendered HTML. Organizers
choose which columns the participant table shows, so parsing maps headers
dynamically instead of assuming a fixed layout. Everything here is
best-effort: whatever cannot be parsed is left empty and edited by the
admin in the UI.
"""

import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "markrounding/0.1 (+https://bibliotekarien.se)"

# Header text (lowercased, stripped) -> boat field. Checked with substring
# matching so "Respittal SRS" and "SRS-tal" both map to srs.
_HEADER_MAP = [
    ("segelnummer", "sail_number"),
    ("segelnr", "sail_number"),
    ("båtnamn", "boat_name"),
    ("båttyp", "boat_type"),
    ("båtklass", "boat_type"),
    ("klass", "boat_type"),
    ("klubb", "club"),
    ("nation", "nation"),
    ("srs", "srs"),
    ("respit", "srs"),
    ("förnamn", "_first_name"),
    ("efternamn", "_last_name"),
    ("rorsman", "skipper"),
    ("skeppare", "skipper"),
    ("namn", "skipper"),
]


def _fetch(url: str) -> str:
    resp = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.text


def _map_header(text: str) -> str | None:
    lowered = text.strip().lower()
    for needle, field in _HEADER_MAP:
        if needle in lowered:
            return field
    return None


def parse_participants(html: str) -> list[dict]:
    """Parse participant tables into boat dicts.

    Sailarena pages often contain several tables (all participants plus one
    per start group) and crew members as extra rows where only the name
    columns are filled. All mapped tables are merged; when a table has a
    sail number column, rows without one (crew rows) are skipped; duplicates
    across tables are dropped.
    """
    soup = BeautifulSoup(html, "html.parser")
    boats: list[dict] = []
    seen: set[tuple] = set()
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [
            _map_header(cell.get_text())
            for cell in rows[0].find_all(["th", "td"])
        ]
        mapped = [h for h in headers if h]
        if not mapped:
            continue
        requires_sail_number = "sail_number" in mapped
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if not any(cells):
                continue
            boat: dict = {}
            for header, value in zip(headers, cells):
                if header and value:
                    boat[header] = value
            first = boat.pop("_first_name", "")
            last = boat.pop("_last_name", "")
            if first or last:
                boat["skipper"] = " ".join(p for p in (first, last) if p)
            if requires_sail_number and not boat.get("sail_number"):
                continue  # crew row: only the name columns are filled
            if not boat:
                continue
            key = (
                boat.get("sail_number", "").upper(),
                boat.get("boat_name", "").lower(),
                boat.get("skipper", "").lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            boats.append(boat)
    return boats


_COORD_PATTERNS = [
    re.compile(r'latitude["\']?\s*[:=]\s*["\']?(-?\d{1,2}\.\d+)', re.I),
    re.compile(r'longitude["\']?\s*[:=]\s*["\']?(-?\d{1,3}\.\d+)', re.I),
]
_COORD_PAIR = re.compile(r"(\d{2}\.\d{4,})\s*,\s*(\d{1,2}\.\d{4,})")


def parse_event(html: str, url: str = "") -> dict:
    """Extract best-effort event metadata: name, organizer, coordinates and
    a link to the participant list."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {}

    heading = soup.find("h1")
    if heading and heading.get_text(strip=True):
        out["name"] = heading.get_text(" ", strip=True)
    elif soup.title:
        out["name"] = soup.title.get_text(strip=True).split("|")[0].strip()

    text = html
    lat_m = _COORD_PATTERNS[0].search(text)
    lon_m = _COORD_PATTERNS[1].search(text)
    if lat_m and lon_m:
        out["lat"], out["lon"] = float(lat_m.group(1)), float(lon_m.group(1))
    else:
        pair = _COORD_PAIR.search(text)
        if pair:
            out["lat"], out["lon"] = float(pair.group(1)), float(pair.group(2))

    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    if dates:
        out["start_date"] = min(dates)
        out["end_date"] = max(dates)

    for link in soup.find_all("a", href=True):
        if "participantlist" in link["href"].lower():
            out["participant_list_url"] = urljoin(url or "/", link["href"])
            break

    return out


def participant_list_url(event_url: str) -> str:
    base = event_url.rstrip("/")
    if base.lower().endswith("participantlist"):
        return event_url
    return base + "/ParticipantList/"


def fetch_event(url: str) -> dict:
    """Fetch a Sailarena event URL (event page or participant list) and
    return {metadata..., "boats": [...]}. Accepts either page as input."""
    html = _fetch(url)
    if url.lower().rstrip("/").endswith("participantlist"):
        return {"boats": parse_participants(html)}

    event = parse_event(html, url)
    boats = parse_participants(html)
    if not boats:
        list_url = event.get("participant_list_url") or participant_list_url(url)
        try:
            boats = parse_participants(_fetch(list_url))
        except httpx.HTTPError:
            boats = []
    event["boats"] = boats
    return event
