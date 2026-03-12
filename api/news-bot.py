"""
CryptoPanic News Bot — MyInvestmentMarkets
Checks CryptoPanic API for hot crypto news and posts to News topic.
Triggered by GitHub Actions Cron every 5 minutes.

NOTE: ForexLive / Reuters RSS is handled in real-time by Superfeedr webhook
      at /api/news-webhook (Vercel serverless). This script handles crypto only.
"""

import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta
import hashlib

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
CRYPTOPANIC_KEY = os.environ.get("CRYPTOPANIC_API_KEY", "")
CHAT_ID = -1003754818644
TOPIC_NEWS = 3  # re

KST = timezone(timedelta(hours=9))
SENT_IDS_FILE = "/tmp/sent_news_ids.json"

HIGH_IMPACT_KEYWORDS = [
    "fed", "federal reserve", "fomc", "rate hike", "rate cut", "interest rate",
    "cpi", "inflation", "nfp", "jobs", "gdp", "recession",
    "war", "crisis", "sanctions", "oil", "opec",
    "bitcoin", "crypto", "sec", "etf approval",
    "trump", "powell", "yellen",
    "bank failure", "default", "debt ceiling",
    "emergency", "breaking", "urgent", "alert"
]


def load_sent_ids():
    try:
        with open(SENT_IDS_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_sent_ids(ids):
    try:
        # Keep only last 500 IDs to prevent file bloat
        id_list = list(ids)[-500:]
        with open(SENT_IDS_FILE, "w") as f:
            json.dump(id_list, f)
    except Exception:
        pass

def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read()

def is_high_impact(title, description=""):
    text = (title + " " + description).lower()
    return any(kw in text for kw in HIGH_IMPACT_KEYWORDS)

def make_id(title, link):
    return hashlib.md5(f"{title}{link}".encode()).hexdigest()[:16]

def gemini_one_line(title, description):
    try:
        prompt = f"""Summarize this financial news in exactly ONE sentence (max 20 words). 
Be direct and factual. Include the key impact on markets if clear.
Title: {title}
Details: {description[:300] if description else 'N/A'}"""

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 60}
        }
        data = json.dumps(payload).encode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read())
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return ""

def tg_send(text):
    payload = {
        "chat_id": CHAT_ID,
        "message_thread_id": TOPIC_NEWS,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def fetch_rss_items():
    items = []
    for source_name, url in RSS_SOURCES:
        try:
            raw = fetch_url(url)
            root = ET.fromstring(raw)
            for item in root.findall(".//item")[:10]:
                title = item.findtext("title", "").strip()
                link  = item.findtext("link", "").strip()
                desc  = item.findtext("description", "").strip()
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

def fetch_cryptopanic():
    items = []
    if not CRYPTOPANIC_KEY:
        return items
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_KEY}&filter=hot&public=true"
        raw = fetch_url(url)
        data = json.loads(raw)
        for post in data.get("results", [])[:10]:
            title = post.get("title", "")
            link  = post.get("url", "")
            items.append({
                "id": make_id(title, link),
                "source": "CryptoPanic",
                "title": title,
                "link": link,
                "description": ""
            })
    except Exception as e:
        print(f"CryptoPanic error: {e}")
    return items

def run():
    sent_ids = load_sent_ids()
    # ForexLive / Reuters → handled by Superfeedr webhook (api/news-webhook.py)
    # This cron job handles CryptoPanic only
    all_items = fetch_cryptopanic()
    new_count = 0


    for item in all_items:
        if item["id"] in sent_ids:
            continue
        if not is_high_impact(item["title"], item["description"]):
            continue

        # Gemini 1-line summary
        summary = gemini_one_line(item["title"], item["description"])

        now_str = datetime.now(KST).strftime("%H:%M KST")

        text = (
            f"🔴 <b>BREAKING — Markets</b>\n\n"
            f"<b>{item['title']}</b>\n"
        )
        if summary:
            text += f"📌 {summary}\n"
        text += (
            f"\n🕐 {now_str}  |  📰 {item['source']}"
            f"\n📎 <a href='{item['link']}'>Read More</a>"
        )

        try:
            tg_send(text)
            sent_ids.add(item["id"])
            new_count += 1
            print(f"✅ Sent: {item['title'][:60]}")
            # Small delay to avoid flooding
            import time
            time.sleep(2)
        except Exception as e:
            print(f"Send error: {e}")

    save_sent_ids(sent_ids)
    print(f"✅ News check complete. {new_count} new articles sent.")

if __name__ == "__main__":
    run()
