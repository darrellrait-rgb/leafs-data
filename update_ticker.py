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
        ("raptors_news", raptors_news),
        ("jays_news", jays_news),
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
