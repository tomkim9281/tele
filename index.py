"""
MyInvestmentMarkets Bot — WSGI entry point
Market Quotes inline keyboard with:
- Per-user sessions (each user gets their own message, not shared editing)
- CoinGecko for crypto prices (Binance blocked on Vercel US servers)
- QuickChart.io chart images with MIM watermark sent via sendPhoto
- Close button to clean up user session messages
"""

import json
import os
import urllib.request
import urllib.parse

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# The pinned keyboard message ID in Market Quotes room
# When this message is clicked → send NEW per-user message instead of editing
PINNED_MSG_ID = 36

# ── Instrument definitions ──────────────────────────────────────────────────
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

# CoinGecko ID → display name for chart labels
CG_ID_MAP = {
    "bitcoin":  "BTC/USD",
    "ethereum": "ETH/USD",
    "ripple":   "XRP/USD",
    "solana":   "SOL/USD",
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

def answer_cb(cid, text=None):
    payload = {"callback_query_id": cid}
    if text:
        payload["text"] = text
    tg("answerCallbackQuery", payload)

def edit_text(chat, mid, text, keyboard=None):
    p = {"chat_id": chat, "message_id": mid,
         "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if keyboard:
        p["reply_markup"] = keyboard
    tg("editMessageText", p)

def send_text(chat, thread, text, keyboard=None):
    p = {"chat_id": chat, "message_thread_id": thread,
         "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if keyboard:
        p["reply_markup"] = keyboard
    return tg("sendMessage", p)

def send_photo(chat, thread, photo_url, caption, keyboard=None):
    p = {"chat_id": chat, "message_thread_id": thread,
         "photo": photo_url, "caption": caption,
         "parse_mode": "HTML"}
    if keyboard:
        p["reply_markup"] = keyboard
    return tg("sendPhoto", p)

def edit_photo(chat, mid, photo_url, caption, keyboard=None):
    """Edit a message by replacing it with a new photo (delete + send)"""
    tg("deleteMessage", {"chat_id": chat, "message_id": mid})
    # After delete, mid is gone — send new photo (caller handles new mid)
    return send_photo(chat, None, photo_url, caption, keyboard)

def delete_msg(chat, mid):
    tg("deleteMessage", {"chat_id": chat, "message_id": mid})

# ── Price fetchers ──────────────────────────────────────────────────────────
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def get_yf(symbol):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?interval=1d&range=2d")
    data = fetch(url)
    meta = data["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice", 0)
    prev  = meta.get("chartPreviousClose", meta.get("previousClose", price))
    pct   = ((price - prev) / prev * 100) if prev else 0
    high  = meta.get("regularMarketDayHigh", price)
    low   = meta.get("regularMarketDayLow",  price)
    return price, pct, high, low

def get_cg(cg_id):
    """CoinGecko free API — reliable, no key, works on Vercel US servers"""
    url = (f"https://api.coingecko.com/api/v3/simple/price"
           f"?ids={cg_id}&vs_currencies=usd"
           f"&include_24hr_change=true&include_24hr_vol=true"
           f"&include_high_24h=true&include_low_24h=true")
    data = fetch(url)
    d = data[cg_id]
    price = d["usd"]
    pct   = d.get("usd_24h_change", 0)
    high  = d.get("usd_24h_high",  price)
    low   = d.get("usd_24h_low",   price)
    return price, pct, high, low

def get_yf_closes(symbol, points=30):
    """Fetch last N daily close prices for sparkline"""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?interval=1d&range=60d")
    try:
        data = fetch(url)
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        return closes[-points:]
    except Exception:
        return []

def get_cg_closes(cg_id, points=30):
    """CoinGecko market_chart — 30 day daily closes"""
    url = (f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
           f"?vs_currency=usd&days=30&interval=daily")
    try:
        data = fetch(url)
        prices = data["prices"]  # [[timestamp, price], ...]
        closes = [p[1] for p in prices]
        return closes[-points:]
    except Exception:
        return []

# ── QuickChart URL builder (with MIM watermark as chart title) ──────────────
def make_chart_url(sym_name, closes, color="#00d4aa"):
    if not closes or len(closes) < 2:
        return None
    labels = list(range(len(closes)))
    chart_cfg = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": closes,
                "borderColor": color,
                "backgroundColor": color.replace(")", ",0.15)").replace("rgb", "rgba") if "rgb" in color else f"{color}26",
                "borderWidth": 2,
                "pointRadius": 0,
                "fill": True,
                "tension": 0.3
            }]
        },
        "options": {
            "legend": {"display": False},
            "title": {
                "display": True,
                "text": f"{sym_name}  |  MyInvestmentMarkets",
                "fontColor": "#cccccc",
                "fontSize": 13
            },
            "scales": {
                "xAxes": [{"display": False}],
                "yAxes": [{"display": True,
                           "ticks": {"fontColor": "#aaaaaa"},
                           "gridLines": {"color": "rgba(255,255,255,0.05)"}}]
            },
            "layout": {"padding": {"left": 10, "right": 10, "top": 5, "bottom": 5}}
        }
    }
    encoded = urllib.parse.quote(json.dumps(chart_cfg))
    return f"https://quickchart.io/chart?w=700&h=280&bkg=%231a1a2e&c={encoded}"

# ── Decimal precision ───────────────────────────────────────────────────────
def smart_dec(sym_name, price):
    if any(x in sym_name for x in ["US100","US500","US30","DE40","JP225"]):
        return 2
    if "JPY" in sym_name or "Oil" in sym_name or "NatGas" in sym_name:
        return 3
    if "/" in sym_name and "USD" in sym_name:
        # Crypto or Forex
        if price > 100:
            return 2
        elif price > 1:
            return 4
        else:
            return 6
    return 2

# ── Keyboards ───────────────────────────────────────────────────────────────
def category_kb():
    buttons = []
    row = []
    for key, cat in CATEGORIES.items():
        row.append({"text": cat["label"], "callback_data": f"cat:{key}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return {"inline_keyboard": buttons}

def symbol_kb(cat_key):
    cat = CATEGORIES[cat_key]
    buttons = []
    row = []
    for sym in cat["symbols"]:
        row.append({"text": sym, "callback_data": f"sym:{cat_key}:{sym}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        {"text": "← Back", "callback_data": "back:categories"},
        {"text": "✕ Close", "callback_data": "close"}
    ])
    return {"inline_keyboard": buttons}

def price_kb(cat_key, sym_name):
    return {"inline_keyboard": [[
        {"text": "🔄 Refresh",  "callback_data": f"sym:{cat_key}:{sym_name}"},
        {"text": "← Back",     "callback_data": f"cat:{cat_key}"},
        {"text": "✕ Close",   "callback_data": "close"}
    ]]}

# ── Price + chart builder ───────────────────────────────────────────────────
MAIN_TEXT = (
    "📊 <b>MyInvestmentMarkets — Live Prices</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Select a category to view live prices and charts:"
)

def get_price_and_chart(sym_name, cat_key):
    ticker, source = CATEGORIES[cat_key]["symbols"][sym_name]

    try:
        if source == "yf":
            price, pct, high, low = get_yf(ticker)
            closes = get_yf_closes(ticker)
            color = "#00d4aa" if pct >= 0 else "#ff4757"
        else:  # cg
            price, pct, high, low = get_cg(ticker)
            closes = get_cg_closes(ticker)
            color = "#f7931a"  # Bitcoin orange for crypto

        dec = smart_dec(sym_name, price)
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

        chart_url = make_chart_url(sym_name, closes, color)
        return caption, chart_url

    except Exception as e:
        return f"⚠️ <b>{sym_name}</b> — fetch error: {e}", None

# ── Callback handler ────────────────────────────────────────────────────────
def handle_callback(cb):
    cid     = cb["id"]
    data    = cb["data"]
    msg     = cb["message"]
    chat    = msg["chat"]["id"]
    mid     = msg["message_id"]
    thread  = msg.get("message_thread_id")
    is_pinned = (mid == PINNED_MSG_ID)

    answer_cb(cid)

    # ── Category selection ─────────────────────────────────────────────────
    if data.startswith("cat:"):
        cat_key = data[4:]
        text = f"📊 <b>{CATEGORIES[cat_key]['label']}</b>\nSelect a symbol:"
        kb   = symbol_kb(cat_key)
        if is_pinned:
            send_text(chat, thread, text, kb)
        else:
            edit_text(chat, mid, text, kb)

    # ── Back to categories ─────────────────────────────────────────────────
    elif data == "back:categories":
        if not is_pinned:
            edit_text(chat, mid, MAIN_TEXT + "\n\n<i>MyInvestmentMarkets</i>",
                      category_kb())

    # ── Symbol price + chart ────────────────────────────────────────────────
    elif data.startswith("sym:"):
        _, cat_key, sym_name = data.split(":", 2)
        caption, chart_url = get_price_and_chart(sym_name, cat_key)
        kb = price_kb(cat_key, sym_name)

        if chart_url:
            # Delete current text message and send photo instead
            if not is_pinned:
                delete_msg(chat, mid)
            send_photo(chat, thread or (msg.get("message_thread_id") if is_pinned else thread),
                       chart_url, caption, kb)
        else:
            if is_pinned:
                send_text(chat, thread, caption, kb)
            else:
                edit_text(chat, mid, caption, kb)

    # ── Close (delete user session message) ────────────────────────────────
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
