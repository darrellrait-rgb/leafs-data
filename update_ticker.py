import html
import json
import os
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; leafs-ticker/1.0)"}
OUT_FILE = "leafs.json"
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}
NEWS_FEED = "https://www.cbc.ca/webfeed/rss/rss-canada-toronto"
NEWS_TOP_HEADLINE_COUNT = 2      
TEAM_HEADLINE_COUNT = 2
NEWS_HEADLINE_MAX_LEN = 70

GENERAL_SPORTS_FEED = "https://www.cbc.ca/webfeed/rss/rss-sports"
LEAFS_NEWS_FEEDS    = ["https://www.cbc.ca/webfeed/rss/rss-sports-nhl", GENERAL_SPORTS_FEED, NEWS_FEED]
RAPTORS_NEWS_FEEDS  = ["https://www.cbc.ca/webfeed/rss/rss-sports-nba", GENERAL_SPORTS_FEED, NEWS_FEED]
JAYS_NEWS_FEEDS     = ["https://www.cbc.ca/webfeed/rss/rss-sports-mlb", GENERAL_SPORTS_FEED, NEWS_FEED]

TSN_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
          "news": "http://www.google.com/schemas/sitemap-news/0.9"}

SPORTS_HEADLINES_COUNT = 5
TSN_SITEMAP_BASE  = "https://www.tsn.ca/arc/outboundfeeds/sitemap-news"
CP24_SITEMAP_BASE = "https://www.cp24.com/arc/outboundfeeds/sitemap-news"
LEAFS_KEYWORDS     = ["leafs", "maple leafs"]
RAPTORS_KEYWORDS   = ["raptors", "raps"]
JAYS_KEYWORDS      = ["blue jays", "jays"]
BILLS_KEYWORDS     = ["bills", "buffalo bills"]

ERRORS = []    
NEWS_STATS = []  

def get(url, headers=None):
    try:
        req = urllib.request.Request(url, headers=headers or HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"FETCH FAILED: {url}\n  {e}", file=sys.stderr)
        ERRORS.append(f"{url.split('?')[0][8:90]} -> {str(e)[:80]}")
        return None

def get_xml(url, headers=None):
    try:
        req = urllib.request.Request(url, headers=headers or BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            return ET.fromstring(r.read())
    except Exception as e:
        print(f"FETCH FAILED: {url}\n  {e}", file=sys.stderr)
        ERRORS.append(f"{url.split('?')[0][8:90]} -> {str(e)[:80]}")
        return None

def fetch_sitemap_articles(base_url):
    url = f"{base_url}/{datetime.now(TZ).date().isoformat()}/"
    root = get_xml(url)
    if root is None:
        return []
    articles = []
    for url_el in root.findall("sm:url", TSN_NS):
        title_el = url_el.find("news:news/news:title", TSN_NS)
        date_el = url_el.find("news:news/news:publication_date", TSN_NS)
        loc_el = url_el.find("sm:loc", TSN_NS)
        if title_el is None or not title_el.text:
            continue
        t = html.unescape(title_el.text).strip()
        t = re.sub(r"\s+", " ", t)
        articles.append({
            "title": t,
            "date": date_el.text if date_el is not None else "",
            "loc": loc_el.text if loc_el is not None else "",
        })
    articles.sort(key=lambda a: a["date"], reverse=True)
    return articles

def top_sports_headlines(count=SPORTS_HEADLINES_COUNT):
    tsn_articles = fetch_sitemap_articles(TSN_SITEMAP_BASE)
    for a in tsn_articles: a["source"] = "TSN"
    cp24_all = fetch_sitemap_articles(CP24_SITEMAP_BASE)
    cp24_articles = [a for a in cp24_all if "/sport" in a["loc"].lower()]
    for a in cp24_articles: a["source"] = "CP24"
    combined = tsn_articles + cp24_articles
    combined.sort(key=lambda a: a["date"], reverse=True)
    seen = set()
    result = []
    for a in combined:
        if a["title"] in seen: continue
        seen.add(a["title"])
        title = a["title"]
        if len(title) > NEWS_HEADLINE_MAX_LEN:
            title = title[:NEWS_HEADLINE_MAX_LEN - 1].rstrip() + "\u2026"
        result.append({"title": title, "source": a["source"], "url": a["loc"]})
        if len(result) >= count: break
    return result

def tsn_headline_titles(keywords, count):
    url = f"https://www.tsn.ca/arc/outboundfeeds/sitemap-news/{datetime.now(TZ).date().isoformat()}/"
    root = get_xml(url)
    if root is None: return [], 0
    titles = []
    total_items = 0
    for url_el in root.findall("sm:url", TSN_NS):
        total_items += 1
        title_el = url_el.find("news:news/news:title", TSN_NS)
        if title_el is None or not title_el.text: continue
        t = html.unescape(title_el.text).strip()
        t = re.sub(r"\s+", " ", t)
        if not any(k.lower() in t.lower() for k in keywords): continue
        if len(t) > NEWS_HEADLINE_MAX_LEN: t = t[:NEWS_HEADLINE_MAX_LEN - 1].rstrip() + "\u2026"
        titles.append(t)
        if len(titles) >= count: break
    return titles, total_items

def cbc_headline_titles(feed_urls, keywords, count, seen):
    if isinstance(feed_urls, str): feed_urls = [feed_urls]
    titles = []
    total_items = 0
    for feed_url in feed_urls:
        if len(titles) >= count: break
        root = get_xml(feed_url)
        if root is None: continue
        for item in root.findall("./channel/item"):
            total_items += 1
            t = item.findtext("title")
            if not t: continue
            t = html.unescape(t).strip()
            t = re.sub(r"\s+", " ", t)
            if keywords and not any(k.lower() in t.lower() for k in keywords): continue
            if t in seen: continue
            seen.add(t)
            if len(t) > NEWS_HEADLINE_MAX_LEN: t = t[:NEWS_HEADLINE_MAX_LEN - 1].rstrip() + "\u2026"
            titles.append(t)
            if len(titles) >= count: break
    return titles, total_items

def team_headlines(keywords, count, prefix):
    tsn_titles, _ = tsn_headline_titles(keywords, count)
    seen = set(tsn_titles)
    titles = list(tsn_titles)
    if len(titles) < count:
        feeds = {"LEAFS": LEAFS_NEWS_FEEDS, "RAPTORS": RAPTORS_NEWS_FEEDS, "JAYS": JAYS_NEWS_FEEDS}
        feed_urls = feeds.get(prefix.split()[0], [GENERAL_SPORTS_FEED, NEWS_FEED])
        cbc_titles, _ = cbc_headline_titles(feed_urls, keywords, count - len(titles), seen)
        titles += cbc_titles
    if not titles: return ""
    return prefix + " | ".join(titles) + " | "

def news():
    cp24_articles = fetch_sitemap_articles(CP24_SITEMAP_BASE)
    titles = []
    for a in cp24_articles:
        t = a["title"]
        if len(t) > NEWS_HEADLINE_MAX_LEN: t = t[:NEWS_HEADLINE_MAX_LEN - 1].rstrip() + "\u2026"
        titles.append(t)
        if len(titles) >= NEWS_TOP_HEADLINE_COUNT: break
    if len(titles) < NEWS_TOP_HEADLINE_COUNT:
        cbc_titles, _ = cbc_headline_titles(NEWS_FEED, None, NEWS_TOP_HEADLINE_COUNT - len(titles), set(titles))
        titles += cbc_titles
    if not titles: return ""
    return "NEWS: " + " | ".join(titles) + " | "

def leafs_news(): return team_headlines(LEAFS_KEYWORDS, TEAM_HEADLINE_COUNT, "LEAFS NEWS: ")
def raptors_news(): return team_headlines(RAPTORS_KEYWORDS, TEAM_HEADLINE_COUNT, "RAPTORS NEWS: ")
def jays_news(): return team_headlines(JAYS_KEYWORDS, TEAM_HEADLINE_COUNT, "JAYS NEWS: ")

def extract_score(competitor):
    score_val = competitor.get("score", "0")
    if isinstance(score_val, dict): score_val = score_val.get("value", "0")
    try: return str(int(float(score_val)))
    except (ValueError, TypeError): return "0"

# ---------------------------------------------------------------- Fixed Raptors Schedule & Live Feed
def get_raptors_data():
    raps_sched_text = "RAPTORS: NO DATA | "
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/tor/schedule"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        events = data.get("events", [])
        if not events: return raps_sched_text

        last_game = ""
        best_last_date = ""
        next_game = ""
        live_game = ""

        for e in events:
            competitions = e.get("competitions", [])
            if not competitions: continue
            comp = competitions[0]

            status_type = comp.get("status", {}).get("type", {})
            completed = status_type.get("completed", False)
            state = status_type.get("state", "")
            date_iso = e.get("date", "")

            competitors = comp.get("competitors", [])
            home_team = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away_team = next((c for c in competitors if c.get("homeAway") == "away"), {})

            h_abbr = home_team.get("team", {}).get("abbreviation", "TOR")
            a_abbr = away_team.get("team", {}).get("abbreviation", "TOR")
            h_score = extract_score(home_team)
            a_score = extract_score(away_team)

            # Robust live state check for NBA games
            if state in ["in", "live"] or status_type.get("name") == "STATUS_IN_PROGRESS":
                detail = status_type.get("shortDetail", "LIVE")
                live_game = f"RAPTORS LIVE: {a_abbr} {a_score} @ {h_abbr} {h_score} ({detail}) | "
                break
            elif completed:
                if not best_last_date or date_iso > best_last_date:
                    best_last_date = date_iso
                    last_game = f"LAST: {a_abbr} {a_score} @ {h_abbr} {h_score} (FINAL) | "
            elif not completed and not next_game:
                try:
                    dt = datetime.strptime(date_iso[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
                    date_formatted = dt.strftime("%m/%d %I:%M%p")
                except Exception:
                    date_formatted = date_iso[:10]
                next_game = f"NEXT: {a_abbr} @ {h_abbr} {date_formatted} | "

        if live_game:
            raps_sched_text = live_game
        elif next_game or last_game:
            if not next_game: next_game = "NEXT: NONE | "
            if not last_game: last_game = "LAST: NONE | "
            raps_sched_text = f"RAPTORS {next_game}{last_game}"
    except Exception as err:
        print(f"[Python] Raptors schedule fetch warning: {err}", file=sys.stderr)

    return raps_sched_text

def raptors():
    return get_raptors_data()

# ---------------------------------------------------------------- Blue Jays / MLB Playoff Fallback
def get_jays_data():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    jays_url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=141&hydrate=team"
    jays_sched_text = "JAYS: OFFSEASON | "
    try:
        req = urllib.request.Request(jays_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        dates = data.get("dates", [])
        last_game, next_game, live_game = "", "", ""
        for d in dates:
            for g in d.get("games", []):
                status = g.get("status", {}).get("abstractGameState", "")
                detailed_status = g.get("status", {}).get("detailedState", "")
                date_iso = g.get("gameDate", "")
                home = g.get("teams", {}).get("home", {})
                away = g.get("teams", {}).get("away", {})
                h_abbr = home.get("team", {}).get("abbreviation", "TOR")
                a_abbr = away.get("team", {}).get("abbreviation", "TOR")
                h_score = home.get("score", 0)
                a_score = away.get("score", 0)
                if status == "Live":
                    live_game = f"JAYS LIVE: {a_abbr} {a_score} @ {h_abbr} {h_score} ({detailed_status}) | "
                    break
                elif status == "Final":
                    last_game = f"LAST: {a_abbr} {a_score} @ {h_abbr} {h_score} (FINAL) | "
                elif status == "Preview" and not next_game:
                    try:
                        dt = datetime.strptime(date_iso[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
                        date_formatted = dt.strftime("%m/%d %I:%M%p")
                    except Exception:
                        date_formatted = date_iso[:10]
                    next_game = f"NEXT: {a_abbr} @ {h_abbr} {date_formatted} | "
        if live_game: jays_sched_text = live_game
        elif next_game or last_game:
            jays_sched_text = f"JAYS {next_game or 'NEXT: NONE | '}{last_game or 'LAST: NONE | '}"
    except Exception as err:
        print(f"[Python] Jays fetch warning: {err}", file=sys.stderr)
    return jays_sched_text

def jays(): return get_jays_data()

# ---------------------------------------------------------------- Buffalo Bills (ESPN)
_BILLS_CACHE = None

def get_bills_data():
    global _BILLS_CACHE
    if _BILLS_CACHE is not None: return _BILLS_CACHE
    bills_sched_text = "BILLS: NO DATA | "
    bills_stand_text = ""
    bills_news_text = ""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    schedule_urls = [
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/2/schedule?seasontype=2",
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/2/schedule?seasontype=1",
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
    ]
    for url in schedule_urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            events = data.get("events", [])
            if not events: continue
            last_game, best_last_date, next_game, live_game = "", "", "", ""
            for e in events:
                name = e.get("name", "")
                if "scoreboard" in url and "Bills" not in name: continue
                competitions = e.get("competitions", [])
                if not competitions: continue
                comp = competitions[0]
                status_type = comp.get("status", {}).get("type", {})
                completed = status_type.get("completed", False)
                state = status_type.get("state", "")
                date_iso = e.get("date", "")
                competitors = comp.get("competitors", [])
                home_team = next((c for c in competitors if c.get("homeAway") == "home"), {})
                away_team = next((c for c in competitors if c.get("homeAway") == "away"), {})
                h_abbr = home_team.get("team", {}).get("abbreviation", "BUF")
                a_abbr = away_team.get("team", {}).get("abbreviation", "BUF")
                h_score = extract_score(home_team)
                a_score = extract_score(away_team)
                if state == "in":
                    detail = status_type.get("shortDetail", "LIVE")
                    live_game = f"BILLS LIVE: {a_abbr} {a_score} @ {h_abbr} {h_score} ({detail}) | "
                    break
                elif completed:
                    if not best_last_date or date_iso > best_last_date:
                        best_last_date = date_iso
                        last_game = f"LAST: {a_abbr} {a_score} @ {h_abbr} {h_score} (FINAL) | "
                elif not completed and not next_game:
                    try:
                        dt = datetime.strptime(date_iso[:16], "%Y-%m-%dT%H:%M")
                        date_formatted = dt.strftime("%m/%d %I:%M%p")
                    except Exception:
                        date_formatted = date_iso[:10]
                    next_game = f"NEXT: {a_abbr} @ {h_abbr} {date_formatted} | "
            if live_game:
                bills_sched_text = live_game
                break
            elif next_game or last_game:
                bills_sched_text = f"BILLS {next_game or 'NEXT: NONE | '}{last_game or 'LAST: NONE | '}"
                break
        except Exception as err:
            print(f"[Python] Schedule fetch warning for {url}: {err}", file=sys.stderr)

    # Standings & News
    try:
        req = urllib.request.Request("https://site.api.espn.com/apis/v2/sports/football/nfl/standings", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            st_data = json.loads(resp.read().decode())
        for group in st_data.get("children", []):
            if "AFC East" in group.get("name", ""):
                rank = 1
                for team_entry in group.get("standings", {}).get("entries", []):
                    if team_entry.get("team", {}).get("abbreviation", "") == "BUF":
                        stats = {s.get("name"): s.get("value") for s in team_entry.get("stats", [])}
                        wins, losses, ties = int(stats.get("wins", 0)), int(stats.get("losses", 0)), int(stats.get("ties", 0))
                        ordinal = "ST" if rank == 1 else ("ND" if rank == 2 else ("RD" if rank == 3 else "TH"))
                        bills_stand_text = f"BILLS {rank}{ordinal} AFC EAST {wins}-{losses}{'-' + str(ties) if ties > 0 else ''} | "
                        break
                    rank += 1
    except Exception: pass

    tsn_titles, _ = tsn_headline_titles(BILLS_KEYWORDS, TEAM_HEADLINE_COUNT)
    if tsn_titles: bills_news_text = "BILLS NEWS: " + " | ".join(tsn_titles) + " | "

    _BILLS_CACHE = (bills_sched_text, (bills_stand_text + bills_news_text).strip())
    return _BILLS_CACHE

def bills(): return get_bills_data()[0]
def bills_info(): return get_bills_data()[1]

_ASCII_SWAPS = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u2026": "...", "\u00a0": " ", "\u2022": "-",
}

def clean(s):
    for bad, good in _ASCII_SWAPS.items(): s = s.replace(bad, good)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

def main():
    old = {}
    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE) as f: old = json.load(f)
        except Exception: old = {}

    result = {}
    tasks = (
        ("news", news),
        ("leafs_news", leafs_news),
        ("raptors", raptors),
        ("raptors_news", raptors_news),
        ("jays_news", jays_news),
        ("jays", jays),
        ("bills", bills),
        ("bills_info", bills_info),
    )

    for key, fn in tasks:
        try: text = clean(fn())
        except Exception as e:
            print(f"{key} failed: {e!r}", file=sys.stderr)
            text = ""
        if not text and isinstance(old.get(key), str): text = old[key]
        result[key] = text
        print(f"{key}: {text}")

    with open(OUT_FILE, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")

    try: headlines = top_sports_headlines()
    except Exception: headlines = []

    old_headlines = {}
    if os.path.exists("sports_headlines.json"):
        try:
            with open("sports_headlines.json") as f: old_headlines = json.load(f)
        except Exception: pass

    if not headlines and isinstance(old_headlines.get("headlines"), list):
        headlines = old_headlines["headlines"]

    headlines = [{**h, "title": clean(h["title"])} for h in headlines]
    ticker_text = "SPORTS: " + " | ".join(h["title"] for h in headlines) + " | " if headlines else ""

    with open("sports_headlines.json", "w") as f:
        json.dump({"generated_at": datetime.now(TZ).isoformat(), "headlines": headlines, "ticker": ticker_text}, f, indent=2)
        f.write("\n")

if __name__ == "__main__":
    main()
