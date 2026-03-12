"""
MyInvestmentMarkets Bot — WSGI entry point
Handles Telegram webhook callbacks for Market Quotes inline keyboard.
Routes:
  POST /api/telegram-webhook  -> Telegram callback handler
  GET  /                      -> Status page
"""

import json
import os
import urllib.request
import urllib.parse

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

CHAT_ID = -1003754818644
TOPIC_QUOTES = 4

# ── Instrument definitions ──────────────────────────────────────────────────
CATEGORIES = {
    "indices": {
        "label": "📈 Indices",
        "symbols": {
            "US100": ("^NDX", "yf"),
            "US500": ("^GSPC", "yf"),
            "US30":  ("^DJI", "yf"),
            "DE40":  ("^GDAXI", "yf"),
            "JP225": ("^N225", "yf"),
        }
    },
    "forex": {
        "label": "💱 Forex",
        "symbols": {
            "EUR/USD": ("EURUSD=X", "yf"),
            "GBP/USD": ("GBPUSD=X", "yf"),
            "USD/JPY": ("JPY=X", "yf"),
            "AUD/USD": ("AUDUSD=X", "yf"),
            "USD/CAD": ("CAD=X", "yf"),
        }
    },
    "crypto": {
        "label": "₿ Crypto",
        "symbols": {
            "BTC/USD": ("BTCUSDT", "binance"),
            "ETH/USD": ("ETHUSDT", "binance"),
            "XRP/USD": ("XRPUSDT", "binance"),
            "SOL/USD": ("SOLUSDT", "binance"),
        }
    },
    "commodities": {
        "label": "🥇 Commodities",
        "symbols": {
            "Gold":    ("GC=F", "yf"),
            "Silver":  ("SI=F", "yf"),
            "WTI Oil": ("CL=F", "yf"),
            "NatGas":  ("NG=F", "yf"),
        }
    }
}

# ── Telegram helpers ────────────────────────────────────────────────────────
def tg_request(method, payload):
    url = f"{BASE_URL}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"TG error [{method}]: {e}")
        return {}

def answer_callback(cid):
    tg_request("answerCallbackQuery", {"callback_query_id": cid})

def edit_message(chat_id, message_id, text, keyboard=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if keyboard:
        payload["reply_markup"] = keyboard
    tg_request("editMessageText", payload)

# ── Price fetchers ──────────────────────────────────────────────────────────
def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())

def get_price_yf(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=2d"
    data = fetch_url(url)
    meta = data["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice", 0)
    prev  = meta.get("chartPreviousClose", meta.get("previousClose", price))
    change_pct = ((price - prev) / prev * 100) if prev else 0
    high  = meta.get("regularMarketDayHigh", price)
    low   = meta.get("regularMarketDayLow", price)
    return price, change_pct, high, low

def get_price_binance(symbol):
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
    data = fetch_url(url)
    price = float(data["lastPrice"])
    change_pct = float(data["priceChangePercent"])
    high  = float(data["highPrice"])
    low   = float(data["lowPrice"])
    return price, change_pct, high, low

# ── Keyboards ───────────────────────────────────────────────────────────────
def category_keyboard():
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

def symbol_keyboard(cat_key):
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
    buttons.append([{"text": "← Back", "callback_data": "back:categories"}])
    return {"inline_keyboard": buttons}

def price_keyboard(cat_key, sym_name):
    return {"inline_keyboard": [[
        {"text": "🔄 Refresh", "callback_data": f"sym:{cat_key}:{sym_name}"},
        {"text": "← Back", "callback_data": f"cat:{cat_key}"}
    ]]}

# ── Price message ───────────────────────────────────────────────────────────
MAIN_TEXT = (
    "📊 <b>MyInvestmentMarkets — Live Prices</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Select a category to view live prices and charts:"
)

def build_price_text(sym_name, cat_key):
    ticker, source = CATEGORIES[cat_key]["symbols"][sym_name]
    try:
        if source == "yf":
            price, change_pct, high, low = get_price_yf(ticker)
        else:
            price, change_pct, high, low = get_price_binance(ticker)
    except Exception as e:
        return f"⚠️ Could not fetch price for <b>{sym_name}</b>.\nError: {e}"

    arrow = "🔺" if change_pct >= 0 else "🔻"
    sign  = "+" if change_pct >= 0 else ""

    # Smart decimal places
    if any(x in sym_name for x in ["US100", "US500", "US30", "DE40", "JP225"]):
        dec = 2
    elif "JPY" in sym_name:
        dec = 3
    elif "/" in sym_name:
        dec = 5
    else:
        dec = 2

    return (
        f"📊 <b>{sym_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Price:  <b>{price:,.{dec}f}</b>\n"
        f"Change: <b>{sign}{change_pct:.2f}%</b> {arrow}\n"
        f"High:   {high:,.{dec}f}\n"
        f"Low:    {low:,.{dec}f}\n\n"
        f"MyInvestmentMarkets"
    )

# ── Callback handler ────────────────────────────────────────────────────────
def handle_callback(cb):
    cid    = cb["id"]
    data   = cb["data"]
    msg    = cb["message"]
    chat   = msg["chat"]["id"]
    mid    = msg["message_id"]

    answer_callback(cid)

    if data.startswith("cat:"):
        cat_key = data[4:]
        edit_message(chat, mid,
                     f"📊 <b>{CATEGORIES[cat_key]['label']}</b>\nSelect a symbol:",
                     symbol_keyboard(cat_key))

    elif data == "back:categories":
        edit_message(chat, mid, MAIN_TEXT, category_keyboard())

    elif data.startswith("sym:"):
        _, cat_key, sym_name = data.split(":", 2)
        text = build_price_text(sym_name, cat_key)
        edit_message(chat, mid, text, price_keyboard(cat_key, sym_name))

# ── WSGI app ────────────────────────────────────────────────────────────────
def app(environ, start_response):
    path   = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    # ── POST /api/telegram-webhook ─────────────────────────────────────────
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

    # ── GET / ──────────────────────────────────────────────────────────────
    body = b"<h1>MyInvestmentMarkets Bot API</h1><p>Webhook active.</p>"
    start_response("200 OK", [("Content-Type", "text/html"),
                               ("Content-Length", str(len(body)))])
    return [body]
