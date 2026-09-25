#!/usr/bin/env python3
"""FantaCoach v0.4 - local backend for Legarina.

Real inputs (when reachable from the user's connection):
- Weekly player and probable-lineup articles: Google News RSS search.
- Serie A fixtures: ESPN public scoreboard JSON endpoint (undocumented/community documented).

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
CACHE_TTL_NEWS = 600
CACHE_TTL_FIXTURES = 900
REQUEST_TIMEOUT = 7
MAX_WORKERS = 12

PLAYERS = [
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
    req = urllib.request.Request(url, headers={"User-Agent": "FantaCoach/0.4 local-news-reader"})
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


def build_player_news(days=7, limit=5):
    result = {p["name"]: [] for p in PLAYERS}
    errors = {}

    # Probe one player first. If DNS/network is unavailable, avoid launching 25 doomed requests.
    first = PLAYERS[0]
    name, articles, err = fetch_player_news(first, days, limit)
    result[name] = articles
    if err:
        network_markers = ("name resolution", "temporary failure", "nodename nor servname", "network is unreachable")
        if any(marker in err.lower() for marker in network_markers):
            return result, {p["name"]: err for p in PLAYERS}
        errors[name] = err

    remaining = PLAYERS[1:]
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
        "User-Agent": "FantaCoach/0.4 (+local-fantasy-football-app)",
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
        })
    return out


def build_fixtures(window_days=21):
    now = time.time()
    if FIXTURE_CACHE["payload"] and now - FIXTURE_CACHE["timestamp"] < CACHE_TTL_FIXTURES:
        return dict(FIXTURE_CACHE["payload"])

    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=window_days)
    date_range = f"{today.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
    urls = [
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/ita.1/scoreboard?dates={date_range}&limit=100",
        f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/ita.1/scoreboard?dates={date_range}&limit=100",
    ]
    last_error = None
    events = []
    for url in urls:
        try:
            events = parse_espn_events(fetch_json(url))
            if events:
                last_error = None
                break
        except Exception as exc:
            last_error = str(exc)

    # Only future/not-completed events, sorted by date.
    upcoming = []
    utc_now = datetime.now(timezone.utc)
    for ev in events:
        dt = parse_date(ev.get("date"))
        if not dt:
            continue
        if dt >= utc_now - timedelta(hours=4) and not ev.get("completed"):
            ev["date"] = dt.isoformat()
            upcoming.append(ev)
    upcoming.sort(key=lambda e: e["date"])

    next_by_club = {}
    for ev in upcoming:
        for club in (ev["home"], ev["away"]):
            if club and club not in next_by_club:
                opponent = ev["away"] if club == ev["home"] else ev["home"]
                next_by_club[club] = {
                    "eventId": ev["id"],
                    "date": ev["date"],
                    "home": ev["home"],
                    "away": ev["away"],
                    "opponent": opponent,
                    "isHome": club == ev["home"],
                    "venue": ev.get("venue", ""),
                }

    payload = {
        "events": upcoming,
        "nextByClub": next_by_club,
        "provider": "ESPN scoreboard JSON",
        "providerNote": "Endpoint pubblico non ufficialmente documentato; se non risponde, FantaCoach mantiene disponibili le news.",
        "error": last_error,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
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
    score_component = (BASE_SCORE.get(player["name"], 70) - 70) * 0.6
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

    score = BASE_SCORE.get(player["name"], 70) + aggregate_impact + availability_adjust + fixture_adjust
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
        "baseScore": BASE_SCORE.get(player["name"], 70),
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


def build_dashboard(days=7, news_limit=5, fixture_days=21):
    # News and fixtures can be fetched independently so a single provider failure does not kill the app.
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_news = pool.submit(build_player_news, days, news_limit)
        f_fix = pool.submit(build_fixtures, fixture_days)
        news, news_errors = f_news.result()
        fixtures = f_fix.result()

    next_by_club = fixtures.get("nextByClub") or {}
    player_states = {}
    for p in PLAYERS:
        player_states[p["name"]] = derive_player_state(p, news.get(p["name"], []), next_by_club.get(p["club"]))

    # Unique next fixtures for clubs in this fantasy roster, plus real articles on probable lineups.
    unique_matchups = {}
    for club in sorted({p["club"] for p in PLAYERS}):
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
        "version": "0.5-mobile",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "players": PLAYERS,
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
                news, errors = build_player_news(days, 5)
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
            self.send_json({"ok": True, "service": "FantaCoach", "version": "0.5-mobile"}, 200)
            return
        super().do_GET()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print("[FantaCoach]", fmt % args)


if __name__ == "__main__":
    os.chdir(ROOT)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"FantaCoach v0.5 Mobile attivo su http://127.0.0.1:{PORT}")
    print("Premi Ctrl+C per chiudere.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
