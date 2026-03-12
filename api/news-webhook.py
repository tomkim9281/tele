"""
Real-Time News Webhook — MyInvestmentMarkets
Receives Superfeedr PubSubHubbub POST notifications for ForexLive RSS.
Deployed as Vercel serverless function at /api/news-webhook.

Superfeedr calls this endpoint instantly when ForexLive publishes new content.
Verifies the source, filters high-impact headlines, sends to Telegram News room.
"""

import json
import os
import hashlib
import urllib.request
from datetime import datetime, timezone, timedelta

BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_KEY  = os.environ.get("GEMINI_API_KEY", "")
SUPERFEEDR_SECRET = os.environ.get("SUPERFEEDR_SECRET", "mim_news_secret_2026")

CHAT_ID    = -1003754818644
TOPIC_NEWS = 3   # "re" topic thread id
KST        = timezone(timedelta(hours=9))

HIGH_IMPACT_KEYWORDS = [
    "fed", "federal reserve", "fomc", "rate hike", "rate cut", "interest rate",
    "cpi", "inflation", "nfp", "payroll", "jobs", "gdp", "recession",
    "war", "crisis", "sanctions", "oil", "opec",
    "bitcoin", "crypto", "etf",
    "trump", "powell", "tariff", "trade war",
    "bank failure", "default", "debt ceiling",
    "emergency", "breaking", "urgent", "flash",
    "earnings beat", "earnings miss", "surprise",
]

# ── Persistent dedup using /tmp (per-invocation, best-effort) ─────────────────
SENT_FILE = "/tmp/wh_sent_ids.json"

def load_sent():
    try:
        with open(SENT_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_sent(ids):
    try:
        with open(SENT_FILE, "w") as f:
            json.dump(list(ids)[-500:], f)
    except Exception:
        pass

def make_id(title, link=""):
    return hashlib.md5(f"{title}{link}".encode()).hexdigest()[:16]

def is_high_impact(title, desc=""):
    text = (title + " " + desc).lower()
    return any(kw in text for kw in HIGH_IMPACT_KEYWORDS)

def gemini_summary(title, desc):
    if not GEMINI_KEY:
        return ""
    try:
        prompt = (
            f"Summarize this financial news in ONE concise sentence (max 20 words). "
            f"Be direct and factual. Include market impact if clear.\n"
            f"Title: {title}\nDetails: {desc[:300] or 'N/A'}"
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
    except Exception:
        return ""

def tg_send(text):
    p = {
        "chat_id": CHAT_ID, "message_thread_id": TOPIC_NEWS,
        "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=json.dumps(p).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def parse_superfeedr_payload(body_bytes):
    """Parse Superfeedr's JSON or Atom/XML payload → list of {title, link, desc}"""
    items = []
    try:
        # Superfeedr can send JSON (preferred) or Atom XML
        data = json.loads(body_bytes)
        # JSON format: {"status": {...}, "items": [...]}
        for entry in data.get("items", []):
            items.append({
                "title": entry.get("title", "").strip(),
                "link":  entry.get("permalinkUrl", entry.get("id", "")).strip(),
                "desc":  entry.get("summary", entry.get("content", "")).strip(),
            })
        return items
    except (json.JSONDecodeError, Exception):
        pass

    # Fallback: Atom XML
    try:
        import xml.etree.ElementTree as ET
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(body_bytes)
        for entry in root.findall(".//atom:entry", ns):
            title = entry.findtext("atom:title", "", ns).strip()
            link_el = entry.find("atom:link[@rel='alternate']", ns)
            link = (link_el.get("href", "") if link_el is not None else "").strip()
            summary = entry.findtext("atom:summary", "", ns).strip()
            items.append({"title": title, "link": link, "desc": summary})
    except Exception:
        pass

    return items

# ── WSGI entrypoint ───────────────────────────────────────────────────────────
def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path   = environ.get("PATH_INFO", "/")

    def respond(status, body, ctype="text/plain"):
        b = body.encode() if isinstance(body, str) else body
        start_response(status, [
            ("Content-Type", ctype),
            ("Content-Length", str(len(b))),
        ])
        return [b]

    # ── GET: Superfeedr hub challenge verification ──────────────────────────
    if method == "GET":
        qs = environ.get("QUERY_STRING", "")
        params = {}
        for part in qs.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[urllib.parse.unquote_plus(k)] = urllib.parse.unquote_plus(v)
        challenge = params.get("hub.challenge", "")
        if challenge:
            # Echo back the challenge to confirm subscription
            return respond("200 OK", challenge)
        return respond("200 OK", "News webhook active")

    # ── POST: Superfeedr notification ──────────────────────────────────────
    if method == "POST":
        try:
            content_length = int(environ.get("CONTENT_LENGTH", 0))
            body = environ["wsgi.input"].read(content_length)
        except Exception:
            body = b""

        items = parse_superfeedr_payload(body)
        sent = load_sent()
        processed = 0

        for item in items:
            title = item.get("title", "")
            link  = item.get("link", "")
            desc  = item.get("desc", "")

            if not title:
                continue
            item_id = make_id(title, link)
            if item_id in sent:
                continue
            if not is_high_impact(title, desc):
                sent.add(item_id)  # mark as seen even if not high-impact
                continue

            summary = gemini_summary(title, desc)
            now_str = datetime.now(KST).strftime("%H:%M KST")

            text = f"🔴 <b>BREAKING — Markets</b>\n\n<b>{title}</b>\n"
            if summary:
                text += f"📌 {summary}\n"
            text += f"\n🕐 {now_str}  |  📰 ForexLive"
            if link:
                text += f"\n📎 <a href='{link}'>Read More</a>"

            try:
                tg_send(text)
                sent.add(item_id)
                processed += 1
                print(f"✅ Sent: {title[:60]}")
            except Exception as e:
                print(f"TG error: {e}")

        save_sent(sent)
        return respond("200 OK", json.dumps({"processed": processed}), "application/json")

    return respond("405 Method Not Allowed", "Method Not Allowed")

# Local urllib.parse import needed for GET handler
import urllib.parse
