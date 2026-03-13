#!/usr/bin/env python3
"""
High-Frequency Breaking News Bot (Zero Signup & Free Pipeline)
Checks multiple reliable RSS feeds every 5 minutes (via GitHub Actions).
Strictly checks 'pubDate' to ensure only recent news (< 60 mins) is posted.
No webhooks required. English only.
"""

import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import hashlib
import time
from email.utils import parsedate_to_datetime

BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_KEY  = os.environ.get("GEMINI_API_KEY", "")
CPANIC_KEY  = os.environ.get("CRYPTOPANIC_API_KEY", "")
CHAT_ID     = -1003754818644
TOPIC_NEWS  = 3  # "re" thread

KST = timezone(timedelta(hours=9))
SENT_IDS_FILE = "/tmp/sent_news_ids.json"
# Only send news published in the last 30 minutes per run (dedup via sent_ids cache)
MAX_AGE_MINUTES = 30

# Dedicated market/FX/financial feeds: post ALL articles (no keyword filter)
MARKET_RSS_SOURCES = [
    ("FXStreet",       "https://www.fxstreet.com/rss"),
    ("ForexLive",      "https://www.forexlive.com/feed/news"),
    ("Cointelegraph",  "https://cointelegraph.com/rss"),
    ("Seeking Alpha",  "https://seekingalpha.com/market_currents.xml"),  # Real-time!
    ("Nasdaq News",    "https://www.nasdaq.com/feed/rssoutbound?category=Markets"),
]

# General news sites: keyword filter applied (finance/economy only)
FILTERED_RSS_SOURCES = [
    ("CNBC Markets",   "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
    ("BBC Business",   "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("Guardian Biz",   "https://www.theguardian.com/business/rss"),
    ("Yahoo Finance",  "https://finance.yahoo.com/news/rssindex"),
    ("Motley Fool",    "https://www.fool.com/feeds/index.aspx"),
]

HIGH_IMPACT_KEYWORDS = [
    # Macro / Central Banks
    "fed", "fomc", "rate", "powell", "cpi", "inflation", "nfp", "payroll",
    "jobs", "gdp", "recession", "yield", "treasury", "bond",
    # Markets general
    "market", "stock", "equit", "index", "indices", "rally", "selloff",
    "surge", "plunge", "crash", "soar", "drop", "rise", "fall", "gain", "loss",
    "nasdaq", "s&p", "dow", "russell", "nikkei", "dax", "ftse",
    # Geopolitics / Macro Risk
    "war", "crisis", "sanctions", "oil", "opec", "tariff", "trade",
    # Crypto
    "bitcoin", "crypto", "btc", "eth", "binance", "coinbase",
    # Commodities / FX
    "apple", "microsoft", "nvidia", "tesla", "amazon", "google", "meta",
    # Geopolitics / Macro / Breaking Disasters
    "military", "attack", "strike", "missile", "tanker", "explosion", 
    "emergency", "nato", "russia", "china", "ukraine", "iran", "israel"
]

def load_sent_ids():
    try:
        with open(SENT_IDS_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_sent_ids(ids):
    try:
        id_list = list(ids)[-1000:]
        with open(SENT_IDS_FILE, "w") as f:
            json.dump(id_list, f)
    except Exception:
        pass

def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read()

def is_high_impact(title, desc=""):
    text = (title + " " + desc).lower()
    return any(kw in text for kw in HIGH_IMPACT_KEYWORDS)

def make_id(title, link=""):
    return hashlib.md5(f"{title}{link}".encode()).hexdigest()[:16]

def gemini_one_line(title, desc):
    if not GEMINI_KEY:
        return ""
    try:
        prompt = (
            f"Summarize this financial news in ONE concise English sentence (max 20 words). "
            f"Be direct and factual. Include market impact if clear.\n"
            f"Headline: {title}\nDetails: {desc[:300] if desc else 'N/A'}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 60}
        }).encode()
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={GEMINI_KEY}",
            data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read())
        return res["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"Gemini error: {e}")
        return ""

def tg_send(text):
    p = {
        "chat_id": CHAT_ID, "message_thread_id": TOPIC_NEWS,
        "text": text, "parse_mode": "HTML", "disable_web_page_preview": False
    }
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=json.dumps(p).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def fetch_rss(sources, now_utc, keyword_filter=False):
    items = []
    for source_name, url in sources:
        try:
            raw = fetch_url(url)
            root = ET.fromstring(raw)
            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                link  = item.findtext("link", "").strip()
                desc  = item.findtext("description", "").strip()
                pub_d = item.findtext("pubDate", "").strip()

                if not pub_d:
                    continue

                dt = None
                try:
                    dt = parsedate_to_datetime(pub_d)
                except Exception:
                    try:
                        dt = datetime.fromisoformat(pub_d.replace("Z", "+00:00"))
                    except Exception:
                        try:
                            from dateutil.parser import parse as dp
                            dt = dp(pub_d)
                        except Exception:
                            pass

                if dt is None:
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_mins = (now_utc - dt).total_seconds() / 60
                if age_mins > MAX_AGE_MINUTES or age_mins < -5:
                    continue

                # Optional keyword filter for general news sites
                if keyword_filter:
                    text = (title + " " + desc).lower()
                    if not any(kw in text for kw in HIGH_IMPACT_KEYWORDS):
                        continue

                items.append({
                    "id": make_id(title, link),
                    "source": source_name,
                    "title": title,
                    "link": link,
                    "description": desc
                })
        except Exception as e:
            print(f"RSS error [{source_name}]: {e}")
    return items

def fetch_all():
    now_utc = datetime.now(timezone.utc)
    items = []

    # Market/FX feeds: all articles (no keyword filter)
    items += fetch_rss(MARKET_RSS_SOURCES, now_utc, keyword_filter=False)

    # General news feeds: keyword filter applied
    items += fetch_rss(FILTERED_RSS_SOURCES, now_utc, keyword_filter=True)

    # CryptoPanic
    if CPANIC_KEY:
        try:
            url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CPANIC_KEY}&filter=hot&public=true"
            data = json.loads(fetch_url(url))
            for post in data.get("results", []):
                title = post.get("title", "").strip()
                link  = post.get("url", "").strip()
                pub_d = post.get("created_at", "").strip()
                if pub_d:
                    try:
                        dt = datetime.fromisoformat(pub_d.replace("Z", "+00:00"))
                        age_mins = (now_utc - dt).total_seconds() / 60
                        if age_mins > MAX_AGE_MINUTES:
                            continue
                    except Exception:
                        pass
                items.append({
                    "id": make_id(title, link),
                    "source": "CryptoPanic",
                    "title": title, "link": link, "description": ""
                })
        except Exception as e:
            print(f"CryptoPanic error: {e}")

    return items


def run():
    print(f"Starting news fetch at {datetime.now(timezone.utc)}")
    sent_ids = load_sent_ids()
    all_items = fetch_all()
    new_count = 0

    print(f"Found {len(all_items)} recent articles (< {MAX_AGE_MINUTES} mins old).")

    for item in all_items:
        if item["id"] in sent_ids:
            continue

        summary = gemini_one_line(item["title"], item["description"])

        text = (
            f"🔴 <b>BREAKING</b>\n\n"
            f"<b>{item['title']}</b>\n"
        )
        if summary:
            text += f"\n📌 <i>{summary}</i>\n"
        text += (
            f"\n📰 {item['source']}\n"
            f"🔗 <a href='{item['link']}'>Read More</a>"
        )

        try:
            tg_send(text)
            sent_ids.add(item["id"])
            new_count += 1
            print(f"✅ Sent: {item['title'][:50]}...")
            time.sleep(2)  # Avoid rate limit
        except Exception as e:
            print(f"❌ Send error: {e}")

    save_sent_ids(sent_ids)
    print(f"Done. Sent {new_count} new breaking alerts.")

if __name__ == "__main__":
    run()
