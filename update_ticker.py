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

    # Only news headlines are built here now. Scores, schedule and standings
    # for all three teams are fetched directly by the ESP32 itself (NHL/MLB
    # aren't blocked from GitHub's servers the way NBA.com/ESPN are, but
    # there's no reason to route them through a 5-minute batch job when the
    # device can just ask for them itself every minute). News stays here
    # because it needs TSN/CP24 sitemap XML parsing, not a good fit for a
    # microcontroller, and it isn't time-sensitive the way scores are.
    for key, fn in (("news", news),
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
