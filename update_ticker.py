import html
import json
import os
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
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
NEWS_TOP_HEADLINE_COUNT = 2      # "top headlines only" for the general Toronto segment
TEAM_HEADLINE_COUNT = 2
NEWS_HEADLINE_MAX_LEN = 70

# Each team searches its own league feed first, then falls back to CBC's
# general sports feed and the Toronto regional feed - the NBA/MLB league
# feeds specifically turned out to be too thin on their own to reliably
# turn up a Raptors or Jays headline.
GENERAL_SPORTS_FEED = "https://www.cbc.ca/webfeed/rss/rss-sports"
LEAFS_NEWS_FEEDS    = ["https://www.cbc.ca/webfeed/rss/rss-sports-nhl",
                       GENERAL_SPORTS_FEED, NEWS_FEED]
RAPTORS_NEWS_FEEDS  = ["https://www.cbc.ca/webfeed/rss/rss-sports-nba",
                       GENERAL_SPORTS_FEED, NEWS_FEED]
JAYS_NEWS_FEEDS     = ["https://www.cbc.ca/webfeed/rss/rss-sports-mlb",
                       GENERAL_SPORTS_FEED, NEWS_FEED]

# TSN publishes a Google-News sitemap for each day's articles (dozens of
# items, much higher volume than CBC's team feeds) instead of RSS. It's
# tried first for team news; CBC above is the fallback if TSN is unreachable
# or has nothing for a team that day.
TSN_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
          "news": "http://www.google.com/schemas/sitemap-news/0.9"}

# CP24 runs the same Bell Media / Arc Publishing platform as TSN, so it has
# the identical dated sitemap format - but CP24 is a general Toronto news
# channel, so only the small slice of its sitemap under a /sport path counts.
# Sportsnet has no current headline feed I could find (their old scores.json
# has reportedly broken and changed URL repeatedly since 2017, and it's
# scores, not headlines, anyway) - left out rather than built on that.
SPORTS_HEADLINES_COUNT = 5
TSN_SITEMAP_BASE  = "https://www.tsn.ca/arc/outboundfeeds/sitemap-news"
CP24_SITEMAP_BASE = "https://www.cp24.com/arc/outboundfeeds/sitemap-news"
LEAFS_KEYWORDS     = ["leafs", "maple leafs"]
RAPTORS_KEYWORDS   = ["raptors"]
JAYS_KEYWORDS      = ["blue jays", "jays"]


ERRORS = []   # fetch failures, written to debug.json
NEWS_STATS = []  # per-feed item/match counts, written to debug.json separately


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


def local_dt(iso_utc):
    return datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(TZ)


def when(iso_utc):
    d = local_dt(iso_utc)
    t = d.strftime("%I:%M%p").lstrip("0")
    if d.date() == datetime.now(TZ).date():
        return f"TODAY {t}"
    return f"{d.strftime('%m/%d')} {t}"


# ---------------------------------------------------------------- NHL
def nhl_score(g, side):
    return g.get(side, {}).get("score", "-")


def leafs():
    base = "https://api-web.nhle.com/v1/club-schedule-season/TOR/"
    sched = get(base + "now")
    if not sched:
        return "LEAFS: NO DATA | ", ""
    games = sched.get("games", [])

    live = next((g for g in games if g.get("gameState") in ("LIVE", "CRIT")), None)
    if live:
        box = get(f"https://api-web.nhle.com/v1/gamecenter/{live['id']}/boxscore") or {}
        a = box.get("awayTeam", live["awayTeam"])
        h = box.get("homeTeam", live["homeTeam"])
        per = box.get("periodDescriptor", {}).get("number")
        clk = box.get("clock", {}).get("timeRemaining")
        detail = " ".join(x for x in (f"P{per}" if per else "", clk or "") if x) or "LIVE"
        return (f"LEAFS LIVE: {a.get('abbrev','AWAY')} {a.get('score', 0)} @ "
                f"{h.get('abbrev','HOME')} {h.get('score', 0)} ({detail}) | "), ""

    def done(g):
        return g.get("gameState") in ("OFF", "FINAL")

    last = None
    nxt = None
    for g in games:
        if done(g):
            last = g
        else:
            nxt = g
            break

    # Offseason / season rollover: look at the neighbouring seasons
    if nxt is None and sched.get("currentSeason"):
        start = int(str(sched["currentSeason"])[:4]) + 1
        nxt_sched = get(f"{base}{start}{start + 1}")
        if nxt_sched and nxt_sched.get("games"):
            nxt = nxt_sched["games"][0]
    if last is None and sched.get("previousSeason"):
        prev = get(f"{base}{sched['previousSeason']}")
        if prev:
            for g in prev.get("games", []):
                if done(g):
                    last = g

    out = "LEAFS "
    next_utc = ""
    if nxt:
        tag = " (PRE)" if nxt.get("gameType") == 1 else ""
        out += (f"NEXT{tag}: {nxt['awayTeam'].get('abbrev','')} @ "
                f"{nxt['homeTeam'].get('abbrev','')} {when(nxt['startTimeUTC'])} | ")
        next_utc = nxt.get("startTimeUTC", "")
    else:
        out += "NEXT: NONE | "
    if last:
        tag = " (PRE)" if last.get("gameType") == 1 else ""
        out += (f"LAST{tag}: {last['awayTeam'].get('abbrev','')} {nhl_score(last,'awayTeam')} @ "
                f"{last['homeTeam'].get('abbrev','')} {nhl_score(last,'homeTeam')} | ")
    else:
        out += "LAST: NONE | "
    return out, next_utc


def leafs_standings():
    """One line: division rank + record + points, e.g. 'LEAFS 3RD ATLANTIC 10-5-2 21PTS | '"""
    data = get("https://api-web.nhle.com/v1/standings/now")
    if not data:
        return ""
    rows = data.get("standings", [])
    tor = next((r for r in rows if r.get("teamAbbrev", {}).get("default") == "TOR"), None)
    if not tor:
        return ""
    div = tor.get("divisionAbbrev", "")
    div_name = {"A": "ATLANTIC", "M": "METRO", "C": "CENTRAL", "P": "PACIFIC"}.get(div, div)
    same_div = [r for r in rows if r.get("divisionAbbrev") == div]
    same_div.sort(key=lambda r: (-(r.get("points", 0)), -(r.get("wins", 0))))
    rank = next((i + 1 for i, r in enumerate(same_div)
                 if r.get("teamAbbrev", {}).get("default") == "TOR"), 0)
    ord_suffix = "TH" if 11 <= rank % 100 <= 13 else {1: "ST", 2: "ND", 3: "RD"}.get(rank % 10, "TH")
    w, l, otl = tor.get("wins", 0), tor.get("losses", 0), tor.get("otLosses", 0)
    pts = tor.get("points", 0)
    return f"LEAFS {rank}{ord_suffix} {div_name} {w}-{l}-{otl} {pts}PTS | "


# ---------------------------------------------------------------- MLB
def jays():
    today = datetime.now(TZ).date()
    start = (today - timedelta(days=3)).isoformat()
    end = (today + timedelta(days=10)).isoformat()
    data = get("https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=141"
               f"&startDate={start}&endDate={end}&hydrate=team,linescore")
    if not data:
        return "BLUE JAYS: NO DATA | ", ""

    games = [g for d in data.get("dates", []) for g in d.get("games", [])]
    games.sort(key=lambda g: g.get("gameDate", ""))
    if not games:
        return "BLUE JAYS: NO GAMES | ", ""

    def state(g):
        return g.get("status", {}).get("abstractGameState", "")

    def postponed(g):
        return g.get("status", {}).get("detailedState", "") in ("Postponed", "Cancelled")

    def abbr(g, side):
        return g["teams"][side].get("team", {}).get("abbreviation", side.upper())

    def runs(g, side):
        return g["teams"][side].get("score", 0)

    live = next((g for g in games if state(g) == "Live"), None)
    if live:
        ls = live.get("linescore", {})
        half = str(ls.get("inningState", "")).upper()
        inn = ls.get("currentInning", "")
        detail = f"{half} {inn}".strip() or "LIVE"
        return (f"BLUE JAYS LIVE: {abbr(live,'away')} {runs(live,'away')} @ "
                f"{abbr(live,'home')} {runs(live,'home')} ({detail}) | "), ""

    upcoming = [g for g in games if state(g) == "Preview" and not postponed(g)]
    finals = [g for g in games if state(g) == "Final"]

    out = "BLUE JAYS "
    next_utc = ""
    if upcoming:
        g = upcoming[0]
        out += f"NEXT: {abbr(g,'away')} @ {abbr(g,'home')} {when(g['gameDate'])} | "
        next_utc = g.get("gameDate", "")
    else:
        out += "NEXT: NONE | "
    if finals:
        g = finals[-1]
        out += (f"LAST: {abbr(g,'away')} {runs(g,'away')} @ "
                f"{abbr(g,'home')} {runs(g,'home')} | ")
    else:
        out += "LAST: NONE | "
    return out, next_utc


def jays_standings():
    """One line: division rank + record + games back, e.g. 'JAYS 2ND AL EAST 15-10 GB 2.5 | '"""
    data = get("https://statsapi.mlb.com/api/v1/standings?leagueId=103,104"
               f"&season={datetime.now(TZ).year}&standingsTypes=regularSeason")
    if not data:
        return ""
    for rec in data.get("records", []):
        for tr in rec.get("teamRecords", []):
            if tr.get("team", {}).get("id") == 141:
                rank = int(tr.get("divisionRank", 0) or 0)
                ord_suffix = ("TH" if 11 <= rank % 100 <= 13
                              else {1: "ST", 2: "ND", 3: "RD"}.get(rank % 10, "TH"))
                w, l = tr.get("wins", 0), tr.get("losses", 0)
                gb = tr.get("gamesBack", "-")
                gb_txt = "" if gb in ("-", "0.0", None) else f" GB {gb}"

                # Bonus, best-effort: wild card standing, if the field is present
                # and the team isn't leading its division (where it's moot).
                wc_txt = ""
                wc_rank = tr.get("wildCardRank")
                wc_gb = tr.get("wildCardGamesBack")
                if rank != 1 and wc_rank and wc_gb not in (None, "-"):
                    wcr = int(wc_rank)
                    wcr_suffix = ("TH" if 11 <= wcr % 100 <= 13
                                  else {1: "ST", 2: "ND", 3: "RD"}.get(wcr % 10, "TH"))
                    wc_txt = f" WC {wcr}{wcr_suffix} {wc_gb}GB"

                return f"JAYS {rank}{ord_suffix} AL EAST {w}-{l}{gb_txt}{wc_txt} | "
    return ""


# ---------------------------------------------------------------- News (TSN sitemap + CBC RSS)
def fetch_sitemap_articles(base_url):
    """Generic reader for the Bell Media / Arc Publishing dated sitemap format
    (TSN and CP24 both use it): returns a list of
    {title, date (ISO string), loc (article URL)} dicts, newest first."""
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

    articles.sort(key=lambda a: a["date"], reverse=True)   # newest first
    return articles


def top_sports_headlines(count=SPORTS_HEADLINES_COUNT):
    """Combines TSN (a pure sports site - every article counts) with CP24's
    small sports slice (only articles whose URL path includes /sport), sorts
    by publish time, dedupes by title, and keeps the newest `count`."""
    tsn_articles = fetch_sitemap_articles(TSN_SITEMAP_BASE)
    for a in tsn_articles:
        a["source"] = "TSN"

    cp24_all = fetch_sitemap_articles(CP24_SITEMAP_BASE)
    cp24_articles = [a for a in cp24_all if "/sport" in a["loc"].lower()]
    for a in cp24_articles:
        a["source"] = "CP24"

    NEWS_STATS.append(f"[SPORTS HEADLINES] TSN: {len(tsn_articles)} items; "
                       f"CP24: {len(cp24_articles)} sports items of {len(cp24_all)} total")

    combined = tsn_articles + cp24_articles
    combined.sort(key=lambda a: a["date"], reverse=True)

    seen = set()
    result = []
    for a in combined:
        if a["title"] in seen:
            continue
        seen.add(a["title"])
        title = a["title"]
        if len(title) > NEWS_HEADLINE_MAX_LEN:
            title = title[:NEWS_HEADLINE_MAX_LEN - 1].rstrip() + "\u2026"
        result.append({"title": title, "source": a["source"], "url": a["loc"]})
        if len(result) >= count:
            break

    return result


def tsn_headline_titles(keywords, count):
    """TSN's daily Google-News sitemap - much higher volume than CBC's team
    feeds, but a different, more fragile format (namespaced XML, dated URL)."""
    url = f"https://www.tsn.ca/arc/outboundfeeds/sitemap-news/{datetime.now(TZ).date().isoformat()}/"
    root = get_xml(url)
    if root is None:
        return [], 0

    titles = []
    total_items = 0
    for url_el in root.findall("sm:url", TSN_NS):
        total_items += 1
        title_el = url_el.find("news:news/news:title", TSN_NS)
        if title_el is None or not title_el.text:
            continue
        t = html.unescape(title_el.text).strip()
        t = re.sub(r"\s+", " ", t)

        if not any(k.lower() in t.lower() for k in keywords):
            continue
        if len(t) > NEWS_HEADLINE_MAX_LEN:
            t = t[:NEWS_HEADLINE_MAX_LEN - 1].rstrip() + "\u2026"
        titles.append(t)
        if len(titles) >= count:
            break

    return titles, total_items


def cbc_headline_titles(feed_urls, keywords, count, seen):
    """Pulls up to `count` headline titles across one or more RSS feeds (tried
    in order, stopping once `count` is reached), skipping anything already in
    `seen` (so a story TSN already found isn't repeated)."""
    if isinstance(feed_urls, str):
        feed_urls = [feed_urls]

    titles = []
    total_items = 0
    for feed_url in feed_urls:
        if len(titles) >= count:
            break
        root = get_xml(feed_url)
        if root is None:
            continue

        for item in root.findall("./channel/item"):
            total_items += 1
            t = item.findtext("title")
            if not t:
                continue
            t = html.unescape(t).strip()
            t = re.sub(r"\s+", " ", t)

            if keywords and not any(k.lower() in t.lower() for k in keywords):
                continue
            if t in seen:
                continue
            seen.add(t)

            if len(t) > NEWS_HEADLINE_MAX_LEN:
                t = t[:NEWS_HEADLINE_MAX_LEN - 1].rstrip() + "\u2026"
            titles.append(t)
            if len(titles) >= count:
                break

    return titles, total_items


def team_headlines(keywords, count, prefix):
    """TSN first, CBC's feeds fill in the rest if TSN comes up short."""
    tsn_titles, tsn_items = tsn_headline_titles(keywords, count)
    seen = set(tsn_titles)

    titles = list(tsn_titles)
    cbc_items = 0
    if len(titles) < count:
        feeds = {"LEAFS": LEAFS_NEWS_FEEDS, "RAPTORS": RAPTORS_NEWS_FEEDS, "JAYS": JAYS_NEWS_FEEDS}
        feed_urls = feeds[prefix.split()[0]]
        cbc_titles, cbc_items = cbc_headline_titles(feed_urls, keywords, count - len(titles), seen)
        titles += cbc_titles

    tag = f"[{prefix.strip(': ')}]"
    NEWS_STATS.append(f"{tag} TSN: {tsn_items} items checked, {len(tsn_titles)} matched; "
                       f"CBC: {cbc_items} items checked, {len(titles) - len(tsn_titles)} matched")

    if not titles:
        return ""
    return prefix + " | ".join(titles) + " | "


def news():
    """Top Toronto headlines: CP24's general sitemap (proper timestamps, so
    tried first) topped up with CBC's Toronto feed if CP24 comes up short."""
    cp24_articles = fetch_sitemap_articles(CP24_SITEMAP_BASE)   # unfiltered - CP24 is Toronto-general already
    titles = []
    for a in cp24_articles:
        t = a["title"]
        if len(t) > NEWS_HEADLINE_MAX_LEN:
            t = t[:NEWS_HEADLINE_MAX_LEN - 1].rstrip() + "\u2026"
        titles.append(t)
        if len(titles) >= NEWS_TOP_HEADLINE_COUNT:
            break
    cp24_matched = len(titles)

    cbc_items = 0
    if len(titles) < NEWS_TOP_HEADLINE_COUNT:
        cbc_titles, cbc_items = cbc_headline_titles(
            NEWS_FEED, None, NEWS_TOP_HEADLINE_COUNT - len(titles), set(titles))
        titles += cbc_titles

    NEWS_STATS.append(f"[NEWS] CP24: {len(cp24_articles)} items checked, {cp24_matched} matched; "
                       f"CBC: {cbc_items} items checked, {len(titles) - cp24_matched} matched")

    if not titles:
        return ""
    return "NEWS: " + " | ".join(titles) + " | "


def leafs_news():
    return team_headlines(LEAFS_KEYWORDS, TEAM_HEADLINE_COUNT, "LEAFS NEWS: ")


def raptors_news():
    return team_headlines(RAPTORS_KEYWORDS, TEAM_HEADLINE_COUNT, "RAPTORS NEWS: ")


def jays_news():
    return team_headlines(JAYS_KEYWORDS, TEAM_HEADLINE_COUNT, "JAYS NEWS: ")


# ---------------------------------------------------------------- main
# The LED matrix font only has plain ASCII. Swap common typographic characters
# for their ASCII look-alikes first (so "Varsho\u2019s" stays "Varsho's" instead of
# losing the apostrophe), strip accents (Montr\u00e9al -> Montreal), then drop
# whatever is left.
_ASCII_SWAPS = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u2026": "...", "\u00a0": " ", "\u2022": "-",
}


def clean(s):
    for bad, good in _ASCII_SWAPS.items():
        s = s.replace(bad, good)
    s = unicodedata.normalize("NFKD", s)
    return s.encode("ascii", "ignore").decode("ascii")


def main():
    old = {}
    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE) as f:
                old = json.load(f)
        except Exception:
            old = {}

    result = {}

    # Sources that return (ticker_text, next_game_utc)
    for key, fn in (("leafs", leafs), ("jays", jays)):
        try:
            text, next_utc = fn()
            text = clean(text)
        except Exception as e:  # never let one source break the others
            print(f"{key} failed: {e!r}", file=sys.stderr)
            text, next_utc = f"{key.upper()}: ERROR | ", ""
        if ("NO DATA" in text or "ERROR" in text) and isinstance(old.get(key), str):
            text = old[key]
            next_utc = old.get(f"{key}_next_utc", next_utc)
        result[key] = text
        result[f"{key}_next_utc"] = next_utc
        print(f"{key}: {text}  (next: {next_utc or 'none'})")

    # Plain ticker-text sources. Raptors scores/schedule aren't fetched here
    # at all - cdn.nba.com, ESPN and (without a configured BDL_KEY secret)
    # BallDontLie all fail from GitHub's servers, confirmed repeatedly. That
    # data comes entirely from the device itself instead, which fetches
    # BallDontLie and ESPN directly from your home network, not blocked the
    # same way. Keeping a guaranteed-to-fail fallback here was just wasted
    # requests and log noise every run.
    for key, fn in (("leafs_standings", leafs_standings),
                     ("jays_standings", jays_standings),
                     ("news", news),
                     ("leafs_news", leafs_news),
                     ("raptors_news", raptors_news),
                     ("jays_news", jays_news)):
        try:
            text = clean(fn())
        except Exception as e:
            print(f"{key} failed: {e!r}", file=sys.stderr)
            text = ""
        if not text and isinstance(old.get(key), str):
            text = old[key]   # keep yesterday's rather than show nothing
        result[key] = text
        print(f"{key}: {text}")

    with open(OUT_FILE, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")

    # Separate file: top 5 sports headlines combined from TSN + CP24, sorted
    # by recency. Kept apart from leafs.json since it's a different kind of
    # thing (a general sports feed, not per-team ticker text) and other
    # consumers might want it without also fetching the sports data.
    try:
        headlines = top_sports_headlines()
    except Exception as e:
        print(f"sports_headlines failed: {e!r}", file=sys.stderr)
        headlines = []

    old_headlines = {}
    if os.path.exists("sports_headlines.json"):
        try:
            with open("sports_headlines.json") as f:
                old_headlines = json.load(f)
        except Exception:
            old_headlines = {}

    if not headlines and isinstance(old_headlines.get("headlines"), list):
        headlines = old_headlines["headlines"]   # keep yesterday's rather than write an empty file

    headlines = [{**h, "title": clean(h["title"])} for h in headlines]
    ticker_text = "SPORTS: " + " | ".join(h["title"] for h in headlines) + " | " if headlines else ""

    with open("sports_headlines.json", "w") as f:
        json.dump({
            "generated_at": datetime.now(TZ).isoformat(),
            "headlines": headlines,
            "ticker": ticker_text,
        }, f, indent=2)
        f.write("\n")

    with open("debug.json", "w") as f:
        json.dump({
            "errors": [clean(e) for e in ERRORS[-8:]],
            "news_stats": [clean(e) for e in NEWS_STATS],
        }, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
