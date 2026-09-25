#!/usr/bin/env python3
"""FantaCoach v0.8 - multi-user backend.

Real inputs (when reachable from the user's connection):
- Weekly player and probable-lineup articles: Google News RSS search.
- Serie A fixtures: provider chain (ESPN -> TheSportsDB -> official Lega Serie A embedded fallback for rounds 6-12 2026/27).

Derived outputs (clearly labelled as estimates in the UI):
- availability signal, starting-index, news impact, FantaCoach score.

No third-party Python packages are required.
Run: python3 server.py
Open: http://127.0.0.1:8787
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", os.environ.get("FANTACOACH_PORT", "8787")))
ROOT = os.path.dirname(os.path.abspath(__file__))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
CACHE_TTL_NEWS = 600
CACHE_TTL_FIXTURES = 900
REQUEST_TIMEOUT = 7
MAX_WORKERS = 12

SERIE_A_LEAGUE_ID = "4332"
THESPORTSDB_KEY = os.environ.get("THESPORTSDB_KEY", "123")
OFFICIAL_SCHEDULE_SOURCE = "https://www.legaseriea.it/serie-a/news/quando-si-gioca-anticipi-e-posticipi-fino-alla-12a-giornata"


LEGACY_PLAYERS = [
    {"name": "Butez", "full": "Jean Butez", "club": "Como", "role": "POR"},
    {"name": "Martínez", "full": "Josep Martinez", "club": "Inter", "role": "POR"},
    {"name": "Stanković", "full": "Filip Stankovic", "club": "Venezia", "role": "POR"},
    {"name": "Belghali", "full": "Rafik Belghali", "club": "Torino", "role": "DIF"},
    {"name": "Bracaglia", "full": "Matteo Bracaglia", "club": "Frosinone", "role": "DIF"},
    {"name": "De Winter", "full": "Koni De Winter", "club": "Milan", "role": "DIF"},
    {"name": "Dodô", "full": "Dodo", "club": "Fiorentina", "role": "DIF"},
    {"name": "Estupiñán", "full": "Pervis Estupinan", "club": "Milan", "role": "DIF"},
    {"name": "Floriani Mussolini", "full": "Romano Floriani Mussolini", "club": "Lazio", "role": "DIF"},
    {"name": "Jiménez", "full": "Alex Jimenez", "club": "Fiorentina", "role": "DIF"},
    {"name": "Wesley", "full": "Wesley", "club": "Roma", "role": "DIF"},
    {"name": "Alajbegović", "full": "Kerim Alajbegovic", "club": "Juventus", "role": "CEN"},
    {"name": "Cissé A.", "full": "Alphadjo Cisse", "club": "Milan", "role": "CEN"},
    {"name": "Nico González", "full": "Nico Gonzalez", "club": "Juventus", "role": "CEN"},
    {"name": "Curtis Jones", "full": "Curtis Jones", "club": "Inter", "role": "CEN"},
    {"name": "Loftus-Cheek", "full": "Ruben Loftus-Cheek", "club": "Milan", "role": "CEN"},
    {"name": "Nico Paz", "full": "Nico Paz", "club": "Como", "role": "CEN"},
    {"name": "Zaccagni", "full": "Mattia Zaccagni", "club": "Lazio", "role": "CEN"},
    {"name": "Zaniolo", "full": "Nicolo Zaniolo", "club": "Udinese", "role": "CEN"},
    {"name": "Berardi", "full": "Domenico Berardi", "club": "Sassuolo", "role": "ATT"},
    {"name": "Beto", "full": "Beto", "club": "Fiorentina", "role": "ATT"},
    {"name": "Diao", "full": "Assane Diao", "club": "Como", "role": "ATT"},
    {"name": "Lautaro Martínez", "full": "Lautaro Martinez", "club": "Inter", "role": "ATT"},
    {"name": "Mateo Pellegrino", "full": "Mateo Pellegrino", "club": "Fiorentina", "role": "ATT"},
    {"name": "Woltemade", "full": "Nick Woltemade", "club": "Juventus", "role": "ATT"},
]

# The base score is the current prototype model; live signals modify it.
BASE_SCORE = {
    'Butez':74,'Martínez':82,'Stanković':69,'Belghali':66,'Bracaglia':73,
    'De Winter':78,'Dodô':64,'Estupiñán':76,'Floriani Mussolini':75,'Jiménez':68,
    'Wesley':61,'Alajbegović':72,'Cissé A.':77,'Nico González':81,'Curtis Jones':79,
    'Loftus-Cheek':74,'Nico Paz':91,'Zaccagni':88,'Zaniolo':71,'Berardi':84,
    'Beto':70,'Diao':86,'Lautaro Martínez':94,'Mateo Pellegrino':80,'Woltemade':78,
}

# Club aliases as they can appear in provider payloads.
CLUB_ALIASES = {
    "Como": ["como", "como 1907"],
    "Inter": ["inter", "internazionale", "inter milan", "inter milano"],
    "Venezia": ["venezia", "venezia fc"],
    "Torino": ["torino", "torino fc"],
    "Frosinone": ["frosinone", "frosinone calcio"],
    "Milan": ["milan", "ac milan"],
    "Fiorentina": ["fiorentina", "acf fiorentina"],
    "Lazio": ["lazio", "ss lazio", "lazio rome"],
    "Roma": ["roma", "as roma"],
    "Juventus": ["juventus", "juventus turin"],
    "Udinese": ["udinese", "udinese calcio"],
    "Sassuolo": ["sassuolo", "sassuolo calcio"],
}


SERIE_A_CLUBS = {"Atalanta","Bologna","Cagliari","Como","Fiorentina","Frosinone","Genoa","Inter","Juventus","Lazio","Lecce","Milan","Monza","Napoli","Parma","Roma","Sassuolo","Torino","Udinese","Venezia"}
CLUB_ALIASES.update({
    "Atalanta": ["atalanta", "atalanta bc"],
    "Bologna": ["bologna", "bologna fc"],
    "Cagliari": ["cagliari", "cagliari calcio"],
    "Genoa": ["genoa", "genoa cfc"],
    "Lecce": ["lecce", "us lecce"],
    "Monza": ["monza", "ac monza"],
    "Napoli": ["napoli", "ssc napoli"],
    "Parma": ["parma", "parma calcio"],
})

def normalize_role(position):
    pos = (position or "").lower()
    if any(x in pos for x in ("goalkeeper", "keeper", "portiere")):
        return "POR"
    if any(x in pos for x in ("defender", "back", "difens")):
        return "DIF"
    if any(x in pos for x in ("forward", "striker", "winger", "attacc")):
        return "ATT"
    if any(x in pos for x in ("midfield", "centroc")):
        return "CEN"
    return "CEN"

def normalize_player_input(raw):
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or raw.get("full") or "").strip()
    if not name:
        return None
    full = str(raw.get("full") or name).strip()
    club = normalize_club(str(raw.get("club") or "").strip())
    role = str(raw.get("role") or "CEN").upper().strip()
    if role not in {"POR","DIF","CEN","ATT"}:
        role = normalize_role(role)
    return {"name": name, "full": full, "club": club, "role": role, "providerId": raw.get("providerId")}

def search_players(query):
    q = (query or "").strip()
    if len(q) < 2:
        return [], "locale"
    qlow = q.lower()
    results = []
    seen = set()
    for p in LEGACY_PLAYERS:
        if qlow in p["name"].lower() or qlow in p["full"].lower():
            item = {**p, "provider": "catalogo FantaCoach", "providerId": None, "roleEstimated": False}
            results.append(item); seen.add((p["full"].lower(), p["club"]))
    provider = "catalogo FantaCoach"
    if len(q) >= 3:
        try:
            url = f"https://www.thesportsdb.com/api/v1/json/{THESPORTSDB_KEY}/searchplayers.php?p={urllib.parse.quote(q)}"
            data = fetch_json(url)
            for raw in (data or {}).get("player") or []:
                sport = (raw.get("strSport") or "").lower()
                if sport and sport != "soccer":
                    continue
                club = normalize_club(raw.get("strTeam") or "")
                if club not in SERIE_A_CLUBS:
                    continue
                full = (raw.get("strPlayer") or "").strip()
                if not full:
                    continue
                key=(full.lower(),club)
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "name": full, "full": full, "club": club,
                    "role": normalize_role(raw.get("strPosition")),
                    "providerId": raw.get("idPlayer"),
                    "provider": "TheSportsDB", "roleEstimated": True,
                    "position": raw.get("strPosition") or ""
                })
            provider = "FantaCoach + TheSportsDB"
        except Exception:
            pass
    return results[:12], provider

SUSPENDED = ["squalificat", "squalifica", "espulso e squalific", "fermo per squalifica"]
INJURED = ["lesione", "infortun", "operazione", "operato", "frattura", "indisponibile", "non convocat", "out per", "stop di"]
DOUBTFUL = ["dubbio", "differenziato", "a parte", "affaticamento", "problema muscolare", "fastidio", "contusione", "gestione", "rischio forfait"]
AVAILABLE = ["in gruppo", "recuperato", "recupera", "convocato", "disponibile", "rientra", "rientro", "ok per"]
STARTER_UP = ["titolare", "dal primo minuto", "in pole", "verso una maglia", "favorito", "confermato nell'undici"]
STARTER_DOWN = ["verso la panchina", "parte dalla panchina", "riserva", "non dovrebbe partire", "ballottaggio"]

NEWS_CACHE = {}
FIXTURE_CACHE = {"timestamp": 0.0, "payload": None}
LINEUP_NEWS_CACHE = {}


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(raw: str):
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return None


def contains_any(text, words):
    text = (text or "").lower()
    return any(word in text for word in words)


def news_impact(text: str) -> int:
    t = (text or "").lower()
    if contains_any(t, SUSPENDED):
        return -10
    if contains_any(t, INJURED):
        return -8
    if contains_any(t, DOUBTFUL):
        return -4
    if contains_any(t, STARTER_DOWN):
        return -3
    if contains_any(t, STARTER_UP):
        return 3
    if contains_any(t, AVAILABLE):
        return 3
    return 0


def google_news_rss(query: str, days=7, limit=5):
    q = f"{query} when:{days}d"
    params = urllib.parse.urlencode({"q": q, "hl": "it", "gl": "IT", "ceid": "IT:it"})
    url = f"https://news.google.com/rss/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "FantaCoach/0.6 news-reader"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    now = datetime.now(timezone.utc)
    articles, seen = [], set()
    for item in root.findall(".//item"):
        title = strip_html(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        published = parse_date(item.findtext("pubDate") or "")
        source_el = item.find("source")
        source = strip_html(source_el.text if source_el is not None else "") or "Google News"
        desc = strip_html(item.findtext("description") or "")
        if not title or not link:
            continue
        key = (title.lower(), source.lower())
        if key in seen:
            continue
        seen.add(key)
        age_hours = None
        if published:
            age_hours = max(0, (now - published).total_seconds() / 3600)
            if age_hours > days * 24 + 8:
                continue
        impact = news_impact(title + " " + desc)
        articles.append({
            "headline": title,
            "detail": "Titolo, fonte e data provengono dal feed live. Apri la fonte per il contesto completo.",
            "source": source,
            "publishedAt": published.isoformat() if published else None,
            "url": link,
            "ageHours": round(age_hours, 1) if age_hours is not None else None,
            "impact": impact,
            "tone": "up" if impact > 0 else "down" if impact < 0 else "flat",
        })
        if len(articles) >= limit:
            break
    return articles


def fetch_player_news(player, days=7, limit=5):
    cache_key = (player["name"], days, limit)
    cached = NEWS_CACHE.get(cache_key)
    if cached and time.time() - cached["timestamp"] < CACHE_TTL_NEWS:
        return player["name"], cached["articles"], None
    query = f'"{player["full"]}" "{player["club"]}" calcio'
    try:
        articles = google_news_rss(query, days=days, limit=limit)
        NEWS_CACHE[cache_key] = {"timestamp": time.time(), "articles": articles}
        return player["name"], articles, None
    except Exception as exc:
        return player["name"], [], str(exc)


def build_player_news(players, days=7, limit=5):
    players = players or LEGACY_PLAYERS
    result = {p["name"]: [] for p in players}
    errors = {}

    # Probe one player first. If DNS/network is unavailable, avoid launching 25 doomed requests.
    first = players[0]
    name, articles, err = fetch_player_news(first, days, limit)
    result[name] = articles
    if err:
        network_markers = ("name resolution", "temporary failure", "nodename nor servname", "network is unreachable")
        if any(marker in err.lower() for marker in network_markers):
            return result, {p["name"]: err for p in players}
        errors[name] = err

    remaining = players[1:]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_player_news, p, days, limit): p for p in remaining}
        for future in as_completed(futures):
            name, articles, err = future.result()
            result[name] = articles
            if err:
                errors[name] = err
    return result, errors


def normalize_club(raw: str):
    s = re.sub(r"[^a-z0-9 ]+", "", (raw or "").lower()).strip()
    for canonical, aliases in CLUB_ALIASES.items():
        for alias in aliases:
            alias_norm = re.sub(r"[^a-z0-9 ]+", "", alias.lower()).strip()
            if s == alias_norm or alias_norm in s or s in alias_norm:
                return canonical
    return raw or ""


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "FantaCoach/0.6 (+fantacoach-legarina)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_espn_events(data):
    out = []
    for ev in data.get("events", []) or []:
        comp = (ev.get("competitions") or [{}])[0]
        competitors = comp.get("competitors") or []
        home = away = None
        for c in competitors:
            team = c.get("team") or {}
            item = {
                "name": team.get("displayName") or team.get("shortDisplayName") or "",
                "abbr": team.get("abbreviation") or "",
            }
            if c.get("homeAway") == "home":
                home = item
            elif c.get("homeAway") == "away":
                away = item
        if not home or not away:
            continue
        status = ((ev.get("status") or {}).get("type") or {})
        out.append({
            "id": str(ev.get("id") or ""),
            "date": ev.get("date"),
            "home": normalize_club(home["name"]),
            "away": normalize_club(away["name"]),
            "homeProviderName": home["name"],
            "awayProviderName": away["name"],
            "status": status.get("name") or status.get("description") or "Scheduled",
            "completed": bool(status.get("completed")),
            "venue": ((comp.get("venue") or {}).get("fullName") or ""),
            "round": None,
        })
    return out


def current_season_label(ref_date=None):
    d = ref_date or datetime.now(timezone.utc).date()
    start_year = d.year if d.month >= 7 else d.year - 1
    return f"{start_year}-{start_year + 1}"


def sportsdb_timestamp(ev):
    raw = ev.get("strTimestamp") or ""
    if raw:
        dt = parse_date(raw)
        if dt:
            return dt.isoformat()
    date_part = ev.get("dateEvent") or ""
    time_part = ev.get("strTime") or ev.get("strTimeLocal") or "12:00:00"
    if date_part:
        try:
            # TheSportsDB soccer times are generally UTC in strTime.
            dt = datetime.fromisoformat(f"{date_part}T{time_part[:8]}+00:00")
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
    return None


def parse_sportsdb_events(data):
    out = []
    for ev in (data or {}).get("events", []) or []:
        home_raw = ev.get("strHomeTeam") or ""
        away_raw = ev.get("strAwayTeam") or ""
        if not home_raw or not away_raw:
            continue
        status_text = (ev.get("strStatus") or ev.get("strProgress") or "Scheduled").strip()
        completed = status_text.lower() in {"match finished", "finished", "ft", "aet", "pen"}
        out.append({
            "id": str(ev.get("idEvent") or ""),
            "date": sportsdb_timestamp(ev),
            "home": normalize_club(home_raw),
            "away": normalize_club(away_raw),
            "homeProviderName": home_raw,
            "awayProviderName": away_raw,
            "status": status_text or "Scheduled",
            "completed": completed,
            "venue": ev.get("strVenue") or "",
            "round": ev.get("intRound"),
        })
    return out


def fetch_sportsdb_next_round():
    base = f"https://www.thesportsdb.com/api/v1/json/{THESPORTSDB_KEY}"
    first = fetch_json(f"{base}/eventsnextleague.php?id={SERIE_A_LEAGUE_ID}")
    next_events = (first or {}).get("events") or []
    if not next_events:
        return []
    seed = next_events[0]
    round_no = seed.get("intRound")
    season = seed.get("strSeason") or current_season_label()
    if round_no:
        try:
            round_data = fetch_json(
                f"{base}/eventsround.php?id={SERIE_A_LEAGUE_ID}&r={urllib.parse.quote(str(round_no))}&s={urllib.parse.quote(season)}"
            )
            parsed = parse_sportsdb_events(round_data)
            if parsed:
                return parsed
        except Exception:
            pass
    return parse_sportsdb_events(first)


def official_embedded_schedule():
    """Published Serie A 2026/27 kickoffs for rounds 6-12.

    Emergency fallback only. It is intentionally date-bounded so it cannot silently
    masquerade as live data after the published range has passed.
    """
    rows = [
        # round 6
        (6,"2026-10-10T13:00:00+00:00","Genoa","Fiorentina"),(6,"2026-10-10T16:00:00+00:00","Inter","Parma"),(6,"2026-10-10T18:45:00+00:00","Napoli","Frosinone"),
        (6,"2026-10-11T10:30:00+00:00","Como","Roma"),(6,"2026-10-11T13:00:00+00:00","Lazio","Monza"),(6,"2026-10-11T13:00:00+00:00","Lecce","Bologna"),(6,"2026-10-11T16:00:00+00:00","Sassuolo","Milan"),(6,"2026-10-11T18:45:00+00:00","Cagliari","Juventus"),
        (6,"2026-10-12T16:30:00+00:00","Atalanta","Venezia"),(6,"2026-10-12T18:45:00+00:00","Torino","Udinese"),
        # round 7
        (7,"2026-10-16T18:45:00+00:00","Frosinone","Sassuolo"),(7,"2026-10-17T13:00:00+00:00","Venezia","Napoli"),(7,"2026-10-17T16:00:00+00:00","Bologna","Inter"),(7,"2026-10-17T18:45:00+00:00","Roma","Genoa"),
        (7,"2026-10-18T10:30:00+00:00","Udinese","Lecce"),(7,"2026-10-18T13:00:00+00:00","Fiorentina","Como"),(7,"2026-10-18T16:00:00+00:00","Milan","Atalanta"),(7,"2026-10-18T18:45:00+00:00","Juventus","Lazio"),(7,"2026-10-19T16:30:00+00:00","Monza","Cagliari"),(7,"2026-10-19T18:45:00+00:00","Parma","Torino"),
        # round 8
        (8,"2026-10-23T18:45:00+00:00","Torino","Monza"),(8,"2026-10-24T13:00:00+00:00","Como","Sassuolo"),(8,"2026-10-24T13:00:00+00:00","Cagliari","Bologna"),(8,"2026-10-24T16:00:00+00:00","Napoli","Roma"),(8,"2026-10-24T18:45:00+00:00","Lazio","Parma"),
        (8,"2026-10-25T10:30:00+00:00","Inter","Fiorentina"),(8,"2026-10-25T13:00:00+00:00","Atalanta","Frosinone"),(8,"2026-10-25T13:00:00+00:00","Genoa","Venezia"),(8,"2026-10-25T16:00:00+00:00","Lecce","Juventus"),(8,"2026-10-25T18:45:00+00:00","Udinese","Milan"),
        # round 9
        (9,"2026-10-27T17:30:00+00:00","Sassuolo","Lazio"),(9,"2026-10-27T19:45:00+00:00","Roma","Cagliari"),(9,"2026-10-27T19:45:00+00:00","Torino","Como"),
        (9,"2026-10-28T17:30:00+00:00","Milan","Bologna"),(9,"2026-10-28T17:30:00+00:00","Parma","Udinese"),(9,"2026-10-28T17:30:00+00:00","Venezia","Inter"),(9,"2026-10-28T19:45:00+00:00","Genoa","Juventus"),(9,"2026-10-28T19:45:00+00:00","Monza","Napoli"),(9,"2026-10-29T17:30:00+00:00","Frosinone","Lecce"),(9,"2026-10-29T19:45:00+00:00","Fiorentina","Atalanta"),
        # round 10
        (10,"2026-10-31T14:00:00+00:00","Bologna","Monza"),(10,"2026-10-31T17:00:00+00:00","Udinese","Roma"),(10,"2026-10-31T19:45:00+00:00","Milan","Inter"),
        (10,"2026-11-01T11:30:00+00:00","Como","Venezia"),(10,"2026-11-01T14:00:00+00:00","Frosinone","Torino"),(10,"2026-11-01T14:00:00+00:00","Lazio","Cagliari"),(10,"2026-11-01T17:00:00+00:00","Lecce","Genoa"),(10,"2026-11-01T19:45:00+00:00","Juventus","Napoli"),(10,"2026-11-02T17:30:00+00:00","Sassuolo","Fiorentina"),(10,"2026-11-02T19:45:00+00:00","Atalanta","Parma"),
        # round 11
        (11,"2026-11-06T19:45:00+00:00","Venezia","Udinese"),(11,"2026-11-07T14:00:00+00:00","Cagliari","Frosinone"),(11,"2026-11-07T14:00:00+00:00","Torino","Lecce"),(11,"2026-11-07T17:00:00+00:00","Parma","Bologna"),(11,"2026-11-07T19:45:00+00:00","Roma","Sassuolo"),
        (11,"2026-11-08T11:30:00+00:00","Napoli","Lazio"),(11,"2026-11-08T14:00:00+00:00","Genoa","Milan"),(11,"2026-11-08T14:00:00+00:00","Monza","Atalanta"),(11,"2026-11-08T17:00:00+00:00","Inter","Como"),(11,"2026-11-08T19:45:00+00:00","Fiorentina","Juventus"),
        # round 12
        (12,"2026-11-21T14:00:00+00:00","Como","Cagliari"),(12,"2026-11-21T14:00:00+00:00","Lazio","Lecce"),(12,"2026-11-21T17:00:00+00:00","Parma","Roma"),(12,"2026-11-21T19:45:00+00:00","Napoli","Torino"),
        (12,"2026-11-22T11:30:00+00:00","Sassuolo","Genoa"),(12,"2026-11-22T14:00:00+00:00","Milan","Frosinone"),(12,"2026-11-22T17:00:00+00:00","Bologna","Udinese"),(12,"2026-11-22T19:45:00+00:00","Atalanta","Inter"),(12,"2026-11-23T17:30:00+00:00","Monza","Fiorentina"),(12,"2026-11-23T19:45:00+00:00","Juventus","Venezia"),
    ]
    return [{
        "id": f"lega-{rnd}-{i}", "date": dt, "home": home, "away": away,
        "homeProviderName": home, "awayProviderName": away, "status": "Scheduled",
        "completed": False, "venue": "Serie A", "round": rnd,
    } for i,(rnd,dt,home,away) in enumerate(rows, 1)]


def _future_events(events, window_days):
    utc_now = datetime.now(timezone.utc)
    cutoff = utc_now + timedelta(days=window_days)
    upcoming = []
    for ev in events:
        dt = parse_date(ev.get("date"))
        if not dt:
            continue
        if dt >= utc_now - timedelta(hours=4) and dt <= cutoff and not ev.get("completed"):
            item = dict(ev)
            item["date"] = dt.isoformat()
            upcoming.append(item)
    upcoming.sort(key=lambda e: e["date"])
    return upcoming


def _fixture_payload(events, provider, provider_note, error=None, source_url=None):
    next_by_club = {}
    for ev in events:
        for club in (ev["home"], ev["away"]):
            if club and club not in next_by_club:
                opponent = ev["away"] if club == ev["home"] else ev["home"]
                next_by_club[club] = {
                    "eventId": ev["id"], "date": ev["date"], "home": ev["home"], "away": ev["away"],
                    "opponent": opponent, "isHome": club == ev["home"], "venue": ev.get("venue", ""),
                    "round": ev.get("round"),
                }
    return {
        "events": events,
        "nextByClub": next_by_club,
        "provider": provider,
        "providerNote": provider_note,
        "sourceUrl": source_url,
        "error": error,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def build_fixtures(window_days=21):
    now = time.time()
    if FIXTURE_CACHE["payload"] and now - FIXTURE_CACHE["timestamp"] < CACHE_TTL_FIXTURES:
        return dict(FIXTURE_CACHE["payload"])

    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=window_days)
    date_range = f"{today.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
    provider_errors = []

    # Provider 1: ESPN JSON (fast when available).
    espn_urls = [
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/ita.1/scoreboard?dates={date_range}&limit=100",
        f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/ita.1/scoreboard?dates={date_range}&limit=100",
    ]
    for url in espn_urls:
        try:
            upcoming = _future_events(parse_espn_events(fetch_json(url)), window_days)
            if upcoming:
                payload = _fixture_payload(upcoming, "ESPN scoreboard JSON", "Calendario live da endpoint pubblico ESPN.")
                payload["providerErrors"] = provider_errors
                FIXTURE_CACHE.update({"timestamp": now, "payload": payload})
                return dict(payload)
        except Exception as exc:
            provider_errors.append(f"ESPN: {exc}")

    # Provider 2: TheSportsDB. The next event tells us the round; eventsround then returns that matchday.
    try:
        upcoming = _future_events(fetch_sportsdb_next_round(), window_days)
        if upcoming:
            payload = _fixture_payload(
                upcoming,
                "TheSportsDB",
                "Fallback API gratuito: prossima giornata di Serie A.",
                source_url="https://www.thesportsdb.com/league/4332",
            )
            payload["providerErrors"] = provider_errors
            FIXTURE_CACHE.update({"timestamp": now, "payload": payload})
            return dict(payload)
    except Exception as exc:
        provider_errors.append(f"TheSportsDB: {exc}")

    # Provider 3: official published Lega Serie A dates for rounds 6-12 only.
    embedded = _future_events(official_embedded_schedule(), window_days)
    if embedded:
        payload = _fixture_payload(
            embedded,
            "Lega Serie A (fallback ufficiale incorporato)",
            "Date/orari pubblicati ufficialmente per le giornate 6-12. Fallback locale, non feed live.",
            error="; ".join(provider_errors) if provider_errors else None,
            source_url=OFFICIAL_SCHEDULE_SOURCE,
        )
        payload["providerErrors"] = provider_errors
        FIXTURE_CACHE.update({"timestamp": now, "payload": payload})
        return dict(payload)

    payload = _fixture_payload(
        [], "non disponibile",
        "Nessun provider calendario ha restituito partite nel periodo richiesto.",
        error="; ".join(provider_errors) if provider_errors else "Nessuna partita trovata.",
    )
    payload["providerErrors"] = provider_errors
    FIXTURE_CACHE.update({"timestamp": now, "payload": payload})
    return dict(payload)

def most_recent_signal(articles):
    signals = []
    for art in articles:
        text = (art.get("headline") or "").lower()
        kind = None
        if contains_any(text, SUSPENDED):
            kind = "suspended"
        elif contains_any(text, INJURED):
            kind = "injured"
        elif contains_any(text, DOUBTFUL):
            kind = "doubtful"
        elif contains_any(text, AVAILABLE):
            kind = "available"
        elif contains_any(text, STARTER_UP):
            kind = "starter_up"
        elif contains_any(text, STARTER_DOWN):
            kind = "starter_down"
        if kind:
            dt = parse_date(art.get("publishedAt")) or datetime(1970,1,1,tzinfo=timezone.utc)
            signals.append((dt, kind, art))
    if not signals:
        return None
    signals.sort(key=lambda x: x[0], reverse=True)
    return signals[0]


def derive_player_state(player, articles, fixture):
    signal = most_recent_signal(articles)
    state = "Nessun segnale critico"
    state_code = "unknown"
    availability_adjust = 0
    lineup_adjust = 0
    evidence = None

    if signal:
        _, kind, evidence = signal
        if kind == "suspended":
            state, state_code, availability_adjust, lineup_adjust = "Possibile squalifica da verificare", "suspended", -18, -60
        elif kind == "injured":
            state, state_code, availability_adjust, lineup_adjust = "Possibile indisponibilità da verificare", "injured", -15, -50
        elif kind == "doubtful":
            state, state_code, availability_adjust, lineup_adjust = "Dubbio / gestione", "doubtful", -7, -22
        elif kind == "available":
            state, state_code, availability_adjust, lineup_adjust = "Segnale di disponibilità", "available", 3, 10
        elif kind == "starter_up":
            state, state_code, availability_adjust, lineup_adjust = "Segnale positivo sulla titolarità", "starter_up", 2, 15
        elif kind == "starter_down":
            state, state_code, availability_adjust, lineup_adjust = "Ballottaggio / possibile panchina", "starter_down", -4, -18

    aggregate_impact = sum(int(a.get("impact") or 0) for a in articles[:3])
    aggregate_impact = max(-12, min(8, aggregate_impact))

    # An index, not a bookmaker-style probability. It is intentionally labelled as such in UI.
    base_score = int(player.get("baseScore") or BASE_SCORE.get(player["name"], 70))
    score_component = (base_score - 70) * 0.6
    lineup_index = 70 + score_component + lineup_adjust
    relevant_count = sum(1 for a in articles if int(a.get("impact") or 0) != 0)
    if relevant_count >= 2:
        confidence = "Alta"
    elif relevant_count == 1:
        confidence = "Media"
    else:
        confidence = "Bassa"
    lineup_index = int(max(5, min(95, round(lineup_index))))

    fixture_adjust = 0
    if fixture:
        fixture_adjust = 1 if fixture.get("isHome") else 0

    score = base_score + aggregate_impact + availability_adjust + fixture_adjust
    score = int(max(20, min(99, score)))

    return {
        "status": state,
        "statusCode": state_code,
        "lineupIndex": lineup_index,
        "confidence": confidence,
        "newsImpact": aggregate_impact,
        "availabilityImpact": availability_adjust,
        "fixtureImpact": fixture_adjust,
        "score": score,
        "baseScore": base_score,
        "evidence": evidence,
    }


def fetch_lineup_news(club, opponent, days=4, limit=3):
    if not club or not opponent:
        return [], None
    key = (club, opponent, days, limit)
    cached = LINEUP_NEWS_CACHE.get(key)
    if cached and time.time() - cached["timestamp"] < CACHE_TTL_NEWS:
        return cached["articles"], None
    query = f'"probabili formazioni" "{club}" "{opponent}" Serie A'
    try:
        articles = google_news_rss(query, days=days, limit=limit)
        LINEUP_NEWS_CACHE[key] = {"timestamp": time.time(), "articles": articles}
        return articles, None
    except Exception as exc:
        return [], str(exc)


def build_dashboard(players=None, days=7, news_limit=5, fixture_days=21):
    players = [normalize_player_input(p) for p in (players or LEGACY_PLAYERS)]
    players = [p for p in players if p]
    if not players:
        players = [dict(p) for p in LEGACY_PLAYERS]
    # News and fixtures can be fetched independently so a single provider failure does not kill the app.
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_news = pool.submit(build_player_news, players, days, news_limit)
        f_fix = pool.submit(build_fixtures, fixture_days)
        news, news_errors = f_news.result()
        fixtures = f_fix.result()

    next_by_club = fixtures.get("nextByClub") or {}
    player_states = {}
    for p in players:
        player_states[p["name"]] = derive_player_state(p, news.get(p["name"], []), next_by_club.get(p["club"]))

    # Unique next fixtures for clubs in this fantasy roster, plus real articles on probable lineups.
    unique_matchups = {}
    for club in sorted({p["club"] for p in players}):
        fx = next_by_club.get(club)
        if not fx:
            continue
        match_key = fx.get("eventId") or f"{fx['home']}-{fx['away']}-{fx['date']}"
        unique_matchups[match_key] = fx

    lineup_news = {}
    lineup_errors = {}
    if unique_matchups:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {}
            for match_key, fx in unique_matchups.items():
                futures[pool.submit(fetch_lineup_news, fx["home"], fx["away"], 4, 3)] = match_key
            for fut in as_completed(futures):
                key = futures[fut]
                arts, err = fut.result()
                lineup_news[key] = arts
                if err:
                    lineup_errors[key] = err

    return {
        "ok": True,
        "version": "0.8-multiuser",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "players": players,
        "news": news,
        "newsErrors": news_errors,
        "fixtures": fixtures,
        "states": player_states,
        "lineupNews": lineup_news,
        "lineupNewsErrors": lineup_errors,
        "notes": {
            "real": "Titolo, fonte, data, link degli articoli e calendario (quando il provider risponde) sono dati live.",
            "estimated": "Stato, indice titolarità, impatto e FantaCoach Score sono stime automatiche e vanno verificati aprendo le fonti.",
        },
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/config":
            self.send_json({
                "ok": True,
                "version": "0.8-multiuser",
                "cloudConfigured": bool(SUPABASE_URL and SUPABASE_ANON_KEY),
                "supabaseUrl": SUPABASE_URL,
                "supabaseAnonKey": SUPABASE_ANON_KEY,
                "legacyRoster": LEGACY_PLAYERS,
            }, 200)
            return
        if parsed.path == "/api/player-search":
            q = (qs.get("q", [""])[0] or "").strip()
            results, provider = search_players(q)
            self.send_json({"ok": True, "results": results, "provider": provider}, 200)
            return
        if parsed.path == "/api/dashboard":
            try:
                days = max(1, min(14, int(qs.get("days", ["7"])[0])))
                fixture_days = max(7, min(45, int(qs.get("fixture_days", ["21"])[0])))
                payload = build_dashboard(days=days, news_limit=5, fixture_days=fixture_days)
                self.send_json(payload, 200)
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, 500)
            return
        if parsed.path == "/api/news":
            try:
                days = max(1, min(14, int(qs.get("days", ["7"])[0])))
                news, errors = build_player_news(LEGACY_PLAYERS, days, 5)
                self.send_json({"ok": True, "players": news, "errors": errors, "provider": "Google News RSS"}, 200)
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, 502)
            return
        if parsed.path == "/api/fixtures":
            try:
                fixture_days = max(7, min(45, int(qs.get("days", ["21"])[0])))
                self.send_json({"ok": True, **build_fixtures(fixture_days)}, 200)
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, 502)
            return
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "service": "FantaCoach", "version": "0.8-multiuser"}, 200)
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/dashboard":
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length > 200000:
                    self.send_json({"ok": False, "error": "Payload troppo grande"}, 413); return
                raw = self.rfile.read(length) if length else b"{}"
                body = json.loads(raw.decode("utf-8") or "{}")
                roster = body.get("players") or []
                if not isinstance(roster, list) or len(roster) > 60:
                    self.send_json({"ok": False, "error": "Rosa non valida"}, 400); return
                days = max(1, min(14, int(body.get("days", 7))))
                fixture_days = max(7, min(45, int(body.get("fixture_days", 28))))
                payload = build_dashboard(players=roster, days=days, news_limit=5, fixture_days=fixture_days)
                self.send_json(payload, 200)
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, 500)
            return
        self.send_json({"ok": False, "error": "Endpoint non trovato"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print("[FantaCoach]", fmt % args)


if __name__ == "__main__":
    os.chdir(ROOT)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"FantaCoach v0.8 Multi-utente attivo su http://127.0.0.1:{PORT}")
    print("Premi Ctrl+C per chiudere.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
