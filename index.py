"""
MyInvestmentMarkets Bot — WSGI entry point

Session isolation:
  callback_data embeds owner user_id → only owner can control their session
  e.g. "cat_u:indices:12345678" → bot checks from.id == 12345678

Price data:
  Yahoo Finance for indices/forex/commodities
  CoinGecko for crypto (Binance blocked on Vercel US servers)

Charts:
  QuickChart.io candlestick, short URL via /chart/create
  MIM watermark in chart title
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

PINNED_MSG_ID = 36   # shared portal in Market Quotes room

CATEGORIES = {
    "indices": {
        "label": "📈 Indices",
        "symbols": {
            "US100":  ("^NDX",    "yf"),
            "US500":  ("^GSPC",   "yf"),
            "US30":   ("^DJI",    "yf"),
            "DE40":   ("^GDAXI",  "yf"),
            "JP225":  ("^N225",   "yf"),
        }
    },
    "forex": {
        "label": "💱 Forex",
        "symbols": {
            "EUR/USD": ("EURUSD=X", "yf"),
            "GBP/USD": ("GBPUSD=X", "yf"),
            "USD/JPY": ("JPY=X",    "yf"),
            "AUD/USD": ("AUDUSD=X", "yf"),
            "USD/CAD": ("CAD=X",    "yf"),
        }
    },
    "crypto": {
        "label": "₿ Crypto",
        "symbols": {
            "BTC":  ("bitcoin",  "cg"),
            "ETH":  ("ethereum", "cg"),
            "XRP":  ("ripple",   "cg"),
            "SOL":  ("solana",   "cg"),
        }
    },
    "commodities": {
        "label": "🥇 Commodities",
        "symbols": {
            "Gold":    ("GC=F",  "yf"),
            "Silver":  ("SI=F",  "yf"),
            "WTI":     ("CL=F",  "yf"),
            "NatGas":  ("NG=F",  "yf"),
        }
    }
}

# ── Telegram helpers ────────────────────────────────────────────────────────
def tg(method, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/{method}", data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"TG [{method}] error: {e}")
        return {}

def answer_cb(cid, text=None, show_alert=False):
    p = {"callback_query_id": cid}
    if text:
        p["text"] = text
        p["show_alert"] = show_alert
    tg("answerCallbackQuery", p)

def send_text(chat, thread, text, kb=None):
    p = {"chat_id": chat, "text": text,
         "parse_mode": "HTML", "disable_web_page_preview": True}
    if thread:
        p["message_thread_id"] = thread
    if kb:
        p["reply_markup"] = kb
    return tg("sendMessage", p)

def edit_text(chat, mid, text, kb=None):
    p = {"chat_id": chat, "message_id": mid,
         "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if kb:
        p["reply_markup"] = kb
    return tg("editMessageText", p)

def edit_to_photo(chat, mid, url, caption, kb=None):
    """Convert any message (text or photo) to photo in-place — same message_id!"""
    p = {
        "chat_id": chat, "message_id": mid,
        "media": {"type": "photo", "media": url,
                  "caption": caption, "parse_mode": "HTML"}
    }
    if kb:
        p["reply_markup"] = kb
    return tg("editMessageMedia", p)

def edit_caption(chat, mid, caption, kb=None):
    p = {"chat_id": chat, "message_id": mid,
         "caption": caption, "parse_mode": "HTML"}
    if kb:
        p["reply_markup"] = kb
    return tg("editMessageCaption", p)

def delete_msg(chat, mid):
    tg("deleteMessage", {"chat_id": chat, "message_id": mid})

# ── Price data ──────────────────────────────────────────────────────────────
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def get_yf_price(symbol):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?interval=1d&range=2d")
    meta = fetch(url)["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice", 0)
    prev  = meta.get("chartPreviousClose", meta.get("previousClose", price))
    pct   = ((price - prev) / prev * 100) if prev else 0
    high  = meta.get("regularMarketDayHigh", price)
    low   = meta.get("regularMarketDayLow",  price)
    return price, pct, high, low

def get_yf_ohlc(symbol, days=30):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?interval=1d&range={days}d")
    result = fetch(url)["chart"]["result"][0]
    # ← FIX: Yahoo Finance key is "timestamp" NOT "timestamps"
    timestamps = result.get("timestamp") or result.get("timestamps", [])
    q = result["indicators"]["quote"][0]
    ohlc = []
    for i, ts in enumerate(timestamps):
        try:
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None not in (o, h, l, c):
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                ohlc.append({"x": dt, "o": round(o,4), "h": round(h,4),
                             "l": round(l,4), "c": round(c,4)})
        except Exception:
            continue
    return ohlc[-25:]

def get_cg_price(cg_id):
    url = (f"https://api.coingecko.com/api/v3/simple/price"
           f"?ids={cg_id}&vs_currencies=usd"
           f"&include_24hr_change=true&include_high_24h=true&include_low_24h=true")
    d = fetch(url)[cg_id]
    return (d["usd"], d.get("usd_24h_change", 0),
            d.get("usd_24h_high", d["usd"]), d.get("usd_24h_low", d["usd"]))

def get_cg_ohlc(cg_id):
    url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc?vs_currency=usd&days=30"
    raw = fetch(url)
    ohlc = []
    for row in raw[-25:]:
        ts_ms, o, h, l, c = row
        dt = datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc).strftime("%Y-%m-%d")
        ohlc.append({"x": dt, "o": round(o,4), "h": round(h,4),
                     "l": round(l,4), "c": round(c,4)})
    return ohlc

# ── QuickChart candlestick (short URL) ─────────────────────────────────────
def make_chart_url(sym_name, ohlc):
    if not ohlc:
        return None
    cfg = {
        "type": "candlestick",
        "data": {"datasets": [{
            "label": sym_name,
            "data": ohlc,
            "color": {"up": "#00d4aa", "down": "#ff4757", "unchanged": "#888"}
        }]},
        "options": {
            "title": {"display": True,
                      "text": f"{sym_name} — 30D | MyInvestmentMarkets",
                      "fontColor": "#ddd", "fontSize": 13},
            "legend": {"display": False},
            "scales": {
                "xAxes": [{"ticks": {"fontColor": "#aaa", "maxTicksLimit": 6},
                            "gridLines": {"color": "rgba(255,255,255,0.05)"}}],
                "yAxes": [{"ticks": {"fontColor": "#aaa"},
                            "gridLines": {"color": "rgba(255,255,255,0.08)"}}]
            }
        }
    }
    body = json.dumps({"chart": cfg, "backgroundColor": "#1a1a2e",
                       "width": 700, "height": 320}).encode()
    req = urllib.request.Request(
        "https://quickchart.io/chart/create", data=body,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read()).get("url")
    except Exception as e:
        print(f"QuickChart error: {e}")
        return None

# ── Price builder ───────────────────────────────────────────────────────────
def smart_dec(sym, price):
    if any(x in sym for x in ["US100","US500","US30","DE40","JP225"]): return 2
    if "JPY" in sym: return 3
    if price > 1000: return 2
    if price > 1:    return 4
    return 6

def build_price(sym_name, cat_key):
    ticker, source = CATEGORIES[cat_key]["symbols"][sym_name]
    try:
        if source == "yf":
            price, pct, high, low = get_yf_price(ticker)
            ohlc = get_yf_ohlc(ticker)
        else:
            price, pct, high, low = get_cg_price(ticker)
            ohlc = get_cg_ohlc(ticker)

        dec   = smart_dec(sym_name, price)
        arrow = "🔺" if pct >= 0 else "🔻"
        sign  = "+" if pct >= 0 else ""
        caption = (
            f"📊 <b>{sym_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Price:  <b>{price:,.{dec}f}</b>\n"
            f"Change: <b>{sign}{pct:.2f}%</b> {arrow}\n"
            f"High:   {high:,.{dec}f}\n"
            f"Low:    {low:,.{dec}f}\n\n"
            f"<i>MyInvestmentMarkets</i>"
        )
        chart_url = make_chart_url(sym_name, ohlc)
        return caption, chart_url
    except Exception as e:
        return f"⚠️ <b>{sym_name}</b> — fetch error: {e}", None

# ── Keyboards with user_id ownership (64 byte limit safe) ──────────────────
def category_kb(uid):
    rows = []
    row = []
    for key, cat in CATEGORIES.items():
        row.append({"text": cat["label"], "callback_data": f"cat_u:{key}:{uid}"})
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([{"text": "✕ Close", "callback_data": f"close_u:{uid}"}])
    return {"inline_keyboard": rows}

def symbol_kb(cat_key, uid):
    rows = []
    row = []
    for sym in CATEGORIES[cat_key]["symbols"]:
        row.append({"text": sym, "callback_data": f"sym_u:{cat_key}:{sym}:{uid}"})
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([
        {"text": "← Back", "callback_data": f"back_u:{uid}"},
        {"text": "✕ Close", "callback_data": f"close_u:{uid}"}
    ])
    return {"inline_keyboard": rows}

def price_kb(cat_key, sym_name, uid):
    return {"inline_keyboard": [[
        {"text": "🔄 Refresh", "callback_data": f"sym_u:{cat_key}:{sym_name}:{uid}"},
        {"text": "← Back",    "callback_data": f"cat_u:{cat_key}:{uid}"},
        {"text": "✕ Close",   "callback_data": f"close_u:{uid}"}
    ]]}

# ── Portal keyboard (shared pinned message — no uid, anyone can start) ──────
def portal_kb():
    rows = []
    row = []
    for key, cat in CATEGORIES.items():
        row.append({"text": cat["label"], "callback_data": f"start:{key}"})
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    return {"inline_keyboard": rows}

MAIN_TEXT = (
    "📊 <b>MyInvestmentMarkets — Live Prices</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Select a category:"
)

# ── Callback handler ────────────────────────────────────────────────────────
def handle_callback(cb):
    cid    = cb["id"]
    data   = cb["data"]
    msg    = cb["message"]
    chat   = msg["chat"]["id"]
    mid    = msg["message_id"]
    thread = msg.get("message_thread_id")
    uid    = str(cb["from"]["id"])    # current user's Telegram ID
    is_photo = bool(msg.get("photo"))

    # ── PORTAL CLICK (shared pinned message) → start per-user session ──────
    if data.startswith("start:"):
        cat_key = data[6:]
        answer_cb(cid)
        text = f"📊 <b>{CATEGORIES[cat_key]['label']}</b>\nSelect a symbol:"
        # Send a NEW message owned by this user
        send_text(chat, thread, text, symbol_kb(cat_key, uid))
        return

    # ── OWNED ACTIONS (check uid matches) ──────────────────────────────────
    # Extract owner_uid from callback_data
    parts = data.split(":")
    action = parts[0]

    # Ownership check
    owner_uid = parts[-1]   # always the last segment for _u actions
    if owner_uid != uid:
        answer_cb(cid, "⚠️ This is not your session. Click the main buttons above to start your own.", show_alert=True)
        return

    answer_cb(cid)

    if action == "cat_u":
        cat_key = parts[1]
        text = f"📊 <b>{CATEGORIES[cat_key]['label']}</b>\nSelect a symbol:"
        if is_photo:
            edit_caption(chat, mid, text, symbol_kb(cat_key, uid))
        else:
            edit_text(chat, mid, text, symbol_kb(cat_key, uid))

    elif action == "back_u":
        if is_photo:
            edit_caption(chat, mid, MAIN_TEXT, category_kb(uid))
        else:
            edit_text(chat, mid, MAIN_TEXT, category_kb(uid))

    elif action == "sym_u":
        cat_key  = parts[1]
        sym_name = parts[2]
        caption, chart_url = build_price(sym_name, cat_key)
        kb = price_kb(cat_key, sym_name, uid)

        if chart_url:
            # Convert in-place to photo via editMessageMedia (same message_id!)
            edit_to_photo(chat, mid, chart_url, caption, kb)
        else:
            # Fallback to text if chart unavailable
            if is_photo:
                edit_caption(chat, mid, caption, kb)
            else:
                edit_text(chat, mid, caption, kb)

    elif action == "close_u":
        delete_msg(chat, mid)

# ── WSGI ───────────────────────────────────────────────────────────────────
def app(environ, start_response):
    path   = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    if method == "POST" and "/telegram-webhook" in path:
        try:
            length = int(environ.get("CONTENT_LENGTH", 0) or 0)
            body   = environ["wsgi.input"].read(length)
            update = json.loads(body)
            if "callback_query" in update:
                handle_callback(update["callback_query"])
        except Exception as e:
            print(f"Webhook error: {e}")
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"OK"]

    body = b"<h1>MyInvestmentMarkets Bot API</h1><p>Webhook active.</p>"
    start_response("200 OK", [("Content-Type", "text/html"),
                               ("Content-Length", str(len(body)))])
    return [body]
