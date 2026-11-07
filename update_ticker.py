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
BILLS_NEWS_FEEDS    = ["https://www.cbc.ca/webfeed/rss/rss-sports-nfl", GENERAL_SPORTS_FEED]

TSN_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
          "news": "http://www.google.com/schemas/sitemap-news/0.9"}

CP24_SITEMAP_BASE = "https://www.cp24.com/arc/outboundfeeds/sitemap-news"
LEAFS_KEYWORDS     = ["Toronto Maple Leafs", "leafs", "maple leafs"]
RAPTORS_KEYWORDS   = ["Toronto Raptors", "raptors", "raps"]
JAYS_KEYWORDS      = ["Toronto Blue Jays", "blue jays", "jays"]
BILLS_KEYWORDS     = ["bills", "buffalo bills"]


def get_xml(url, headers=None):
    try:
        req = urllib.request.Request(url, headers=headers or BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            return ET.fromstring(r.read())
    except Exception as e:
        print(f"FETCH FAILED: {url}\n  {e}", file=sys.stderr)
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
        feeds = {"LEAFS": LEAFS_NEWS_FEEDS, "RAPTORS": RAPTORS_NEWS_FEEDS, "JAYS": JAYS_NEWS_FEEDS, "BILLS": BILLS_NEWS_FEEDS}
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
def bills_news(): return team_headlines(BILLS_KEYWORDS, TEAM_HEADLINE_COUNT, "BILLS NEWS: ")


_ASCII_SWAPS = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u2026": "...", "\u00a0": " ", "\u2022": "-",
}


def clean(s):
    for bad, good in _ASCII_SWAPS.items(): s = s.replace(bad, good)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


BILLS_SCHEDULE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/buf/schedule"


def _espn_score(competitor):
    sc = competitor.get("score")
    if isinstance(sc, dict):
        sc = sc.get("displayValue", sc.get("value"))
    try:
        return int(float(sc))
    except (TypeError, ValueError):
        return 0


def _espn_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def bills_events():
    """Buffalo's regular-season and playoff events from ESPN (empty list on failure)."""
    events = []
    for season_type in (2, 3):
        try:
            events += _espn_json(f"{BILLS_SCHEDULE_URL}?seasontype={season_type}").get("events", [])
        except Exception as e:
            print(f"bills schedule (seasontype={season_type}) failed: {e!r}", file=sys.stderr)
    return events


def bills_game(events):
    """The one game the device should poll for a live score: the game in progress,
    otherwise the next one that hasn't finished. Returns {} when there isn't one
    (offseason), so the device stops polling."""
    best = None
    for e in sorted(events, key=lambda e: e.get("date", "")):
        try:
            comp = e["competitions"][0]
            status = comp["status"]["type"]
            if status.get("state") == "post" or status.get("completed"):
                continue
            comps = comp["competitors"]
            home = next(c for c in comps if c.get("homeAway") == "home")
            away = next(c for c in comps if c.get("homeAway") == "away")
            start = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            game = {
                "id": str(e["id"]),
                "start": int(start.timestamp()),
                "home": home["team"]["abbreviation"], "homeId": str(home["team"]["id"]),
                "away": away["team"]["abbreviation"], "awayId": str(away["team"]["id"]),
            }
        except Exception as ex:
            print(f"bills_game: skipped an event: {ex!r}", file=sys.stderr)
            continue
        if status.get("state") == "in":
            return game
        if best is None:
            best = game
    return best or {}


def bills_schedule(events=None):
    """Text for the Bills ticker segment, same shape the sketch used to build
    itself: 'BILLS LAST: BAL @ BUF 20-27 | NEXT: BAL @ BUF 11/01 1:00PM | '.
    Regular season plus playoffs (seasontype 2 and 3). Returns "" if ESPN gave
    nothing, so main() keeps the previous value."""
    if events is None:
        events = bills_events()
    if not events:
        return ""

    def parse(e):
        comp = e["competitions"][0]
        status = comp["status"]["type"]
        comps = comp["competitors"]
        home = next(c for c in comps if c.get("homeAway") == "home")
        away = next(c for c in comps if c.get("homeAway") == "away")
        when = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(TZ)
        return {
            "when": when,
            "state": status.get("state", ""),
            "completed": bool(status.get("completed")),
            "detail": status.get("shortDetail", "LIVE"),
            "h": home["team"]["abbreviation"], "a": away["team"]["abbreviation"],
            "hs": _espn_score(home), "as": _espn_score(away),
        }

    games = []
    for e in events:
        try:
            games.append(parse(e))
        except Exception as ex:
            print(f"bills: skipped an event: {ex!r}", file=sys.stderr)
    games.sort(key=lambda g: g["when"])

    last = nxt = ""
    for g in games:
        line = f"{g['a']} {g['as']} @ {g['h']} {g['hs']}"
        if g["state"] == "in":
            nxt = f"LIVE: {line} ({g['detail']}) | "
            break
        if g["completed"] or g["state"] == "post":
            last = f"LAST: {line} | "
        elif not nxt:
            t = g["when"]
            h12 = t.hour % 12 or 12
            nxt = (f"NEXT: {g['a']} @ {g['h']} {t:%m/%d} "
                   f"{h12}:{t.minute:02d}{'PM' if t.hour >= 12 else 'AM'} | ")
    if not nxt and not last:
        return ""
    return "BILLS " + last + (nxt or "NEXT: NONE | ")


def main():
    old = {}
    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE) as f: old = json.load(f)
        except Exception: old = {}

    result = {}
    bills_ev = bills_events()      # fetched once, used for both the text and the live-game hand-off
    tasks = (
        ("news", news),
        ("leafs_news", leafs_news),
        ("raptors_news", raptors_news),
        ("jays_news", jays_news),
        ("bills_news", bills_news),
        ("bills_schedule", lambda: bills_schedule(bills_ev)),
    )

    for key, fn in tasks:
        try: text = clean(fn())
        except Exception as e:
            print(f"{key} failed: {e!r}", file=sys.stderr)
            text = ""
        if not text and isinstance(old.get(key), str): text = old[key]
        result[key] = text
        print(f"{key}: {text}")

    # Which game the device should poll for live scores. If ESPN gave nothing at all,
    # keep the old value; if it answered but there's no upcoming game, {} turns polling off.
    if bills_ev:
        result["bills_game"] = bills_game(bills_ev)
    elif isinstance(old.get("bills_game"), dict):
        result["bills_game"] = old["bills_game"]
    print(f"bills_game: {result.get('bills_game')}")

    with open(OUT_FILE, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
