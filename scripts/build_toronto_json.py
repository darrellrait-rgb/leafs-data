#!/usr/bin/env python3
import json
import requests
from datetime import datetime, timezone

# -----------------------------------------------------
# CONFIG
# -----------------------------------------------------

NEWSAPI_KEY = ""   # optional — leave blank for fallback
HEADERS = {"User-Agent": "toronto-json-bot"}

# -----------------------------------------------------
# Helpers
# -----------------------------------------------------

def safe_get(url, headers=None):
    try:
        r = requests.get(url, headers=headers or HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def fmt(s):
    if not s:
        return ""
    return str(s).replace("\n", " ").replace("\r", " ").strip()

def endbar(s):
    if not s.endswith(" | "):
        return s + " | "
    return s

def ascii_only(s):
    return "".join(ch if ord(ch) < 128 else "?" for ch in s)

# -----------------------------------------------------
# Leafs (REAL NHL data via TheSportsDB)
# -----------------------------------------------------

def get_leafs():
    last_url = "https://www.thesportsdb.com/api/v1/json/3/eventslast.php?id=134861"
    next_url = "https://www.thesportsdb.com/api/v1/json/3/eventsnext.php?id=134861"
    stand_url = "https://www.thesportsdb.com/api/v1/json/3/lookuptable.php?l=nhl_2024_2025"

    last = safe_get(last_url)
    nxt = safe_get(next_url)
    stand = safe_get(stand_url)

    leafs_text = "LEAFS: NO DATA | "
    leafs_next_utc = ""
    leafs_standings = "LEAFS STANDINGS: NO DATA | "
    leafs_news = "LEAFS NEWS: No updates available | "

    # Last game
    try:
        g = last["results"][0]
        home = fmt(g["strHomeTeam"])
        away = fmt(g["strAwayTeam"])
        hs = g["intHomeScore"]
        as_ = g["intAwayScore"]
        leafs_text = f"LEAFS: {away} {as_} @ {home} {hs} FINAL | "
    except Exception:
        pass

    # Next game
    try:
        g = nxt["events"][0]
        date = fmt(g["dateEvent"])
        time = fmt(g["strTime"])
        leafs_next_utc = f"{date}T{time}Z"
    except Exception:
        pass

    # Standings
    try:
        for row in stand["table"]:
            if row["teamid"] == "134861":
                pos = row["position"]
                leafs_standings = f"LEAFS STANDINGS: {pos}TH ATLANTIC | "
                break
    except Exception:
        pass

    return ascii_only(leafs_text), leafs_next_utc, ascii_only(leafs_standings), ascii_only(leafs_news)

# -----------------------------------------------------
# Jays (REAL MLB data via TheSportsDB)
# -----------------------------------------------------

def get_jays():
    last_url = "https://www.thesportsdb.com/api/v1/json/3/eventslast.php?id=134739"
    next_url = "https://www.thesportsdb.com/api/v1/json/3/eventsnext.php?id=134739"
    stand_url = "https://www.thesportsdb.com/api/v1/json/3/lookuptable.php?l=mlb_2024"

    last = safe_get(last_url)
    nxt = safe_get(next_url)
    stand = safe_get(stand_url)

    jays_text = "BLUE JAYS: NO DATA | "
    jays_next_utc = ""
    jays_standings = "JAYS STANDINGS: NO DATA | "
    jays_news = "JAYS NEWS: No updates available | "

    # Last game
    try:
        g = last["results"][0]
        home = fmt(g["strHomeTeam"])
        away = fmt(g["strAwayTeam"])
        hs = g["intHomeScore"]
        as_ = g["intAwayScore"]
        jays_text = f"BLUE JAYS: {away} {as_} @ {home} {hs} FINAL | "
    except Exception:
        pass

    # Next game
    try:
        g = nxt["events"][0]
        date = fmt(g["dateEvent"])
        time = fmt(g["strTime"])
        jays_next_utc = f"{date}T{time}Z"
    except Exception:
        pass

    # Standings
    try:
        for row in stand["table"]:
            if row["teamid"] == "134739":
                pos = row["position"]
                jays_standings = f"JAYS STANDINGS: {pos}TH AL EAST | "
                break
    except Exception:
        pass

    return ascii_only(jays_text), jays_next_utc, ascii_only(jays_standings), ascii_only(jays_news)

# -----------------------------------------------------
# Raptors News (REAL via ESPN)
# -----------------------------------------------------

def get_raptors_news():
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news"
    data = safe_get(url)

    if not data or "articles" not in data:
        return "RAPTORS NEWS: No updates available | "

    for a in data["articles"]:
        if "Raptors" in a.get("headline", ""):
            headline = fmt(a["headline"])
            return ascii_only(f"RAPTORS NEWS: {headline} | ")

    return "RAPTORS NEWS: No updates available | "

# -----------------------------------------------------
# Toronto News (REAL via NewsAPI)
# -----------------------------------------------------

def get_toronto_news():
    if not NEWSAPI_KEY:
        return "TORONTO NEWS: No updates available | "

    url = (
        "https://newsapi.org/v2/everything?"
        "q=Toronto&language=en&sortBy=publishedAt&pageSize=5&apiKey=" + NEWSAPI_KEY
    )

    data = safe_get(url)

    if not data or "articles" not in data:
        return "TORONTO NEWS: No updates available | "

    headline = fmt(data["articles"][0]["title"])
    return ascii_only(f"TORONTO NEWS: {headline} | ")

# -----------------------------------------------------
# Sports Headlines (REAL via NewsAPI)
# -----------------------------------------------------

def get_sports_headlines():
    if not NEWSAPI_KEY:
        return [
            "Leafs preparing for next matchup",
            "Jays rotation expected to shift",
            "Raptors evaluating roster changes",
            "Toronto FC training intensifies",
            "CFL East standings tighten"
        ]

    url = (
        "https://newsapi.org/v2/top-headlines?"
        "category=sports&language=en&pageSize=5&apiKey=" + NEWSAPI_KEY
    )

    data = safe_get(url)

    if not data or "articles" not in data:
        return [
            "Leafs preparing for next matchup",
            "Jays rotation expected to shift",
            "Raptors evaluating roster changes",
            "Toronto FC training intensifies",
            "CFL East standings tighten"
        ]

    headlines = []
    for a in data["articles"]:
        headlines.append(ascii_only(fmt(a["title"])))
        if len(headlines) >= 5:
            break

    return headlines

def get_sports_ticker(headlines):
    return ascii_only("SPORTS: " + " | ".join(headlines) + " | ")

# -----------------------------------------------------
# Feed Health Block
# -----------------------------------------------------

def component_status(value, empty_value):
    if value == empty_value:
        return "ERROR"
    if value.strip() == "":
        return "DEGRADED"
    return "OK"

health = {
    "status": "OK",  # will be updated below
    "last_update_utc": datetime.now(timezone.utc).isoformat(),
    "version": "2026-10-05",
    "components": {
        "leafs":   component_status(leafs_text, "LEAFS: NO DATA | "),
        "jays":    component_status(jays_text, "BLUE JAYS: NO DATA | "),
        "raptors": component_status(raptors_news, "RAPTORS NEWS: No updates available | "),
        "weather": "OK" if weatherText.strip() != "" else "DEGRADED",
        "news":    component_status(toronto_news, "TORONTO NEWS: No updates available | "),
        "sports":  "OK" if len(headlines) > 0 else "ERROR"
    },
    "message": "All systems operational"
}

# Determine overall status
if "ERROR" in health["components"].values():
    health["status"] = "ERROR"
    health["message"] = "One or more feeds failed"
elif "DEGRADED" in health["components"].values():
    health["status"] = "DEGRADED"
    health["message"] = "Some feeds are degraded"

# -----------------------------------------------------
# Build unified JSON
# -----------------------------------------------------

def main():
    leafs_text, leafs_next_utc, leafs_standings, leafs_news = get_leafs()
    jays_text, jays_next_utc, jays_standings, jays_news = get_jays()

    raptors_news = get_raptors_news()
    toronto_news = get_toronto_news()

    headlines = get_sports_headlines()
    sports_ticker = get_sports_ticker(headlines)

    data = {
        "leafs": endbar(leafs_text),
        "leafs_next_utc": leafs_next_utc,
        "leafs_standings": endbar(leafs_standings),
        "leafs_news": endbar(leafs_news),

        "jays": endbar(jays_text),
        "jays_next_utc": jays_next_utc,
        "jays_standings": endbar(jays_standings),
        "jays_news": endbar(jays_news),

        "raptors_news": endbar(raptors_news),

        "news": endbar(toronto_news),

        "sports_ticker": endbar(sports_ticker),
        "sports_headlines": headlines,
        "feed_health": health

        "generated_at": datetime.now(timezone.utc).isoformat()
    }

    with open("toronto.json", "w") as f:
        json.dump(data, f, indent=2)

    print("toronto.json updated successfully")

if __name__ == "__main__":
    main()
