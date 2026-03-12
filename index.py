"""
MyInvestmentMarkets Bot — WSGI entry point

Per-user session architecture:
  - Pinned message (id:36) click → sends NEW per-user session message
  - All subsequent interactions edit THAT message (same message_id = true isolation)
  - Uses editMessageMedia to switch between text↔photo in-place (no delete+resend)

Charts:
  - OHLC candlestick via QuickChart.io /chart/create (short URL)
  - MIM watermark in chart title
  - CoinGecko for crypto (Binance blocked on Vercel US)
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

PINNED_MSG_ID = 36  # The shared pinned keyboard in Market Quotes room

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
            "BTC/USD": ("bitcoin",  "cg"),
            "ETH/USD": ("ethereum", "cg"),
            "XRP/USD": ("ripple",   "cg"),
            "SOL/USD": ("solana",   "cg"),
        }
    },
    "commodities": {
        "label": "🥇 Commodities",
        "symbols": {
            "Gold":    ("GC=F",  "yf"),
            "Silver":  ("SI=F",  "yf"),
            "WTI Oil": ("CL=F",  "yf"),
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
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"TG [{method}] error: {e}")
        return {}

def answer_cb(cid):
    tg("answerCallbackQuery", {"callback_query_id": cid})

def send_text(chat, thread, text, keyboard=None):
    p = {"chat_id": chat, "text": text,
         "parse_mode": "HTML", "disable_web_page_preview": True}
    if thread:
        p["message_thread_id"] = thread
    if keyboard:
        p["reply_markup"] = keyboard
    return tg("sendMessage", p)

def edit_text(chat, mid, text, keyboard=None):
    """Edit an existing TEXT message."""
    p = {"chat_id": chat, "message_id": mid,
         "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if keyboard:
        p["reply_markup"] = keyboard
    return tg("editMessageText", p)

def edit_to_photo(chat, mid, photo_url, caption, keyboard=None):
    """Convert any message type to photo in-place (same message_id!)."""
    p = {
        "chat_id": chat, "message_id": mid,
        "media": {
            "type": "photo",
            "media": photo_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
    }
    if keyboard:
        p["reply_markup"] = keyboard
    return tg("editMessageMedia", p)

def edit_caption(chat, mid, caption, keyboard=None):
    """Edit caption of a photo message."""
    p = {"chat_id": chat, "message_id": mid,
         "caption": caption, "parse_mode": "HTML"}
    if keyboard:
        p["reply_markup"] = keyboard
    return tg("editMessageCaption", p)

def delete_msg(chat, mid):
    tg("deleteMessage", {"chat_id": chat, "message_id": mid})

# ── Price fetchers ──────────────────────────────────────────────────────────
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def get_yf_ticker(symbol):
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
    timestamps = result["timestamps"]
    q = result["indicators"]["quote"][0]
    ohlc = []
    for i, ts in enumerate(timestamps):
        o = q["open"][i]
        h = q["high"][i]
        l = q["low"][i]
        c = q["close"][i]
        if None not in (o, h, l, c):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            ohlc.append({"x": dt, "o": round(o,4), "h": round(h,4),
                         "l": round(l,4), "c": round(c,4)})
    return ohlc[-25:]

def get_cg_ticker(cg_id):
    url = (f"https://api.coingecko.com/api/v3/simple/price"
           f"?ids={cg_id}&vs_currencies=usd"
           f"&include_24hr_change=true&include_24hr_vol=true"
           f"&include_high_24h=true&include_low_24h=true")
    d = fetch(url)[cg_id]
    return d["usd"], d.get("usd_24h_change", 0), d.get("usd_24h_high", d["usd"]), d.get("usd_24h_low", d["usd"])

def get_cg_ohlc(cg_id, days=30):
    url = (f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc"
           f"?vs_currency=usd&days={days}")
    raw = fetch(url)  # [[ts_ms, o, h, l, c], ...]
    ohlc = []
    for row in raw[-25:]:
        ts_ms, o, h, l, c = row
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        ohlc.append({"x": dt, "o": round(o,4), "h": round(h,4),
                     "l": round(l,4), "c": round(c,4)})
    return ohlc

# ── QuickChart candlestick ──────────────────────────────────────────────────
def make_candle_chart_url(sym_name, ohlc_data):
    """Create a short QuickChart URL using their /chart/create endpoint."""
    if not ohlc_data:
        return None

    chart_cfg = {
        "type": "candlestick",
        "data": {
            "datasets": [{
                "label": sym_name,
                "data": ohlc_data,
                "color": {
                    "up": "rgba(0,212,170,1)",
                    "down": "rgba(255,71,87,1)",
                    "unchanged": "rgba(150,150,150,1)"
                },
                "borderColor": {
                    "up": "rgba(0,212,170,1)",
                    "down": "rgba(255,71,87,1)",
                    "unchanged": "rgba(150,150,150,1)"
                }
            }]
        },
        "options": {
            "title": {
                "display": True,
                "text": f"{sym_name} — 30D | MyInvestmentMarkets",
                "fontColor": "#dddddd",
                "fontSize": 13
            },
            "legend": {"display": False},
            "scales": {
                "xAxes": [{"ticks": {"fontColor": "#aaa"},
                           "gridLines": {"color": "rgba(255,255,255,0.05)"}}],
                "yAxes": [{"ticks": {"fontColor": "#aaa"},
                           "gridLines": {"color": "rgba(255,255,255,0.08)"}}]
            }
        }
    }

    # Use QuickChart's /chart/create to get a short URL (avoids URL length limits)
    payload = json.dumps({"chart": chart_cfg, "backgroundColor": "#1a1a2e",
                          "width": 700, "height": 300}).encode()
    req = urllib.request.Request(
        "https://quickchart.io/chart/create",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
            return result.get("url")
    except Exception as e:
        print(f"QuickChart error: {e}")
        return None

# ── Price helpers ───────────────────────────────────────────────────────────
def smart_dec(sym_name, price):
    if any(x in sym_name for x in ["US100","US500","US30","DE40","JP225"]):
        return 2
    if "JPY" in sym_name or sym_name in ("WTI Oil","NatGas","Silver"):
        return 3
    if "/" in sym_name:
        if price > 100:   return 2
        elif price > 1:   return 4
        else:             return 6
    return 2

def build_price_data(sym_name, cat_key):
    ticker, source = CATEGORIES[cat_key]["symbols"][sym_name]
    try:
        if source == "yf":
            price, pct, high, low = get_yf_ticker(ticker)
            ohlc = get_yf_ohlc(ticker)
        else:
            price, pct, high, low = get_cg_ticker(ticker)
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
        chart_url = make_candle_chart_url(sym_name, ohlc)
        return caption, chart_url, True
    except Exception as e:
        return f"⚠️ <b>{sym_name}</b> error: {e}", None, False

# ── Keyboards ───────────────────────────────────────────────────────────────
MAIN_TEXT = (
    "📊 <b>MyInvestmentMarkets — Live Prices</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Select a category:"
)

def category_kb():
    rows = []
    row = []
    for key, cat in CATEGORIES.items():
        row.append({"text": cat["label"], "callback_data": f"cat:{key}"})
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([{"text": "✕ Close", "callback_data": "close"}])
    return {"inline_keyboard": rows}

def symbol_kb(cat_key):
    cat = CATEGORIES[cat_key]
    rows = []
    row = []
    for sym in cat["symbols"]:
        row.append({"text": sym, "callback_data": f"sym:{cat_key}:{sym}"})
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([{"text": "← Back", "callback_data": "back:categories"},
                 {"text": "✕ Close", "callback_data": "close"}])
    return {"inline_keyboard": rows}

def price_kb(cat_key, sym_name):
    return {"inline_keyboard": [[
        {"text": "🔄 Refresh",  "callback_data": f"sym:{cat_key}:{sym_name}"},
        {"text": "← Back",     "callback_data": f"cat:{cat_key}"},
        {"text": "✕ Close",    "callback_data": "close"}
    ]]}

# ── Callback handler ────────────────────────────────────────────────────────
def handle_callback(cb):
    cid    = cb["id"]
    data   = cb["data"]
    msg    = cb["message"]
    chat   = msg["chat"]["id"]
    mid    = msg["message_id"]
    thread = msg.get("message_thread_id")

    # Is this a photo message? (has "photo" key in message object)
    is_photo = bool(msg.get("photo") or msg.get("animation"))

    # Is user clicking the shared pinned portal message?
    is_pinned = (mid == PINNED_MSG_ID)

    answer_cb(cid)

    # ── Category menu ──────────────────────────────────────────────────────
    if data.startswith("cat:"):
        cat_key = data[4:]
        text = f"📊 <b>{CATEGORIES[cat_key]['label']}</b>\nSelect a symbol:"
        kb   = symbol_kb(cat_key)

        if is_pinned:
            # Create a fresh per-user session message
            send_text(chat, thread, text, kb)
        elif is_photo:
            # Currently showing a chart photo → use editMessageCaption
            edit_caption(chat, mid, text, kb)
        else:
            edit_text(chat, mid, text, kb)

    # ── Back to category select ────────────────────────────────────────────
    elif data == "back:categories":
        if not is_pinned:
            if is_photo:
                edit_caption(chat, mid, MAIN_TEXT, category_kb())
            else:
                edit_text(chat, mid, MAIN_TEXT, category_kb())

    # ── Symbol price + chart ────────────────────────────────────────────────
    elif data.startswith("sym:"):
        _, cat_key, sym_name = data.split(":", 2)
        caption, chart_url, ok = build_price_data(sym_name, cat_key)
        kb = price_kb(cat_key, sym_name)

        if is_pinned:
            # New per-user session — send fresh message
            if chart_url and ok:
                send_text(chat, thread,
                          "⏳ Loading chart...", None)
                # Note: we can't easily send photo on first click from pinned
                # So send text with chart link preview
                new_msg = send_text(chat, thread, caption, kb)
            else:
                send_text(chat, thread, caption, kb)
        else:
            if chart_url and ok:
                # Convert message to photo in-place (editMessageMedia)
                # Same message_id = only this user can interact with it!
                edit_to_photo(chat, mid, chart_url, caption, kb)
            else:
                if is_photo:
                    edit_caption(chat, mid, caption, kb)
                else:
                    edit_text(chat, mid, caption, kb)

    # ── Close ─────────────────────────────────────────────────────────────
    elif data == "close":
        if not is_pinned:
            delete_msg(chat, mid)

# ── WSGI app ────────────────────────────────────────────────────────────────
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
