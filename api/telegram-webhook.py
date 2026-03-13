"""
Telegram Webhook Handler — MyInvestmentMarkets
Handles: Market Quotes inline keyboard (real-time price + chart)
Deployed as Vercel Serverless Function
"""

import json
import os
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

CHAT_ID = -1003733637841
TOPIC_QUOTES = 47  # 시세

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

# ── Telegram API helpers ────────────────────────────────────────────────────
def tg_request(method, payload):
    url = f"{BASE_URL}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"TG error: {e}")
        return {}

def send_message(chat_id, thread_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "message_thread_id": thread_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_request("sendMessage", payload)

def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_request("editMessageText", payload)

def answer_callback(callback_id):
    tg_request("answerCallbackQuery", {"callback_query_id": callback_id})

# ── Price fetchers ──────────────────────────────────────────────────────────
def _fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())

def get_price_yf(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=2d"
    data = _fetch_url(url)
    result = data["chart"]["result"][0]
    meta = result["meta"]
    price = meta.get("regularMarketPrice", 0)
    prev  = meta.get("chartPreviousClose", meta.get("previousClose", price))
    change_pct = ((price - prev) / prev * 100) if prev else 0
    high  = meta.get("regularMarketDayHigh", price)
    low   = meta.get("regularMarketDayLow", price)
    return price, change_pct, high, low

def get_price_binance(symbol):
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
    data = _fetch_url(url)
    price = float(data["lastPrice"])
    change_pct = float(data["priceChangePercent"])
    high  = float(data["highPrice"])
    low   = float(data["lowPrice"])
    return price, change_pct, high, low

def get_sparkline_url(symbol, source):
    """Generate QuickChart sparkline image URL using recent close prices"""
    try:
        if source == "yf":
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1h&range=1d"
            data = _fetch_url(url)
            closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if c is not None]
        else:
            url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=24"
            data = _fetch_url(url)
            closes = [float(k[4]) for k in data]

        if not closes:
            return None

        chart_data = json.dumps({"type":"line","data":{"labels":list(range(len(closes))),"datasets":[{"data":closes,"borderColor":"#00d4aa","borderWidth":2,"pointRadius":0,"fill":False}]},"options":{"legend":{"display":False},"scales":{"xAxes":[{"display":False}],"yAxes":[{"display":False}]}}})
        encoded = urllib.parse.quote(chart_data)
        return f"https://quickchart.io/chart?w=400&h=120&c={encoded}"
    except Exception as e:
        print(f"Sparkline error: {e}")
        return None

# ── Keyboard builders ───────────────────────────────────────────────────────
def build_category_keyboard():
    buttons = []
    row = []
    for cat_key, cat in CATEGORIES.items():
        row.append({"text": cat["label"], "callback_data": f"cat:{cat_key}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return {"inline_keyboard": buttons}

def build_symbol_keyboard(cat_key):
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

def build_price_keyboard(cat_key, sym_name):
    return {"inline_keyboard": [
        [{"text": "🔄 Refresh", "callback_data": f"sym:{cat_key}:{sym_name}"},
         {"text": "← Back", "callback_data": f"cat:{cat_key}"}]
    ]}

# ── Price message builder ───────────────────────────────────────────────────
def build_price_text(sym_name, cat_key):
    sym_tuple = CATEGORIES[cat_key]["symbols"][sym_name]
    ticker, source = sym_tuple

    try:
        if source == "yf":
            price, change_pct, high, low = get_price_yf(ticker)
        else:
            price, change_pct, high, low = get_price_binance(ticker)
    except Exception as e:
        return f"⚠️ Could not fetch price for <b>{sym_name}</b>.\nError: {e}", None

    arrow = "🔺" if change_pct >= 0 else "🔻"
    sign  = "+" if change_pct >= 0 else ""

    sparkline_url = get_sparkline_url(ticker, source)

    # Format price with appropriate decimal places
    decimals = 5 if "JPY" not in sym_name and ("/" in sym_name and "USD" in sym_name and sym_name != "BTC/USD") else 2
    if sym_name in ("US100", "US500", "US30", "DE40", "JP225") or "Oil" in sym_name or "NatGas" in sym_name:
        decimals = 2

    price_str = f"{price:,.{decimals}f}"
    high_str  = f"{high:,.{decimals}f}"
    low_str   = f"{low:,.{decimals}f}"

    text = (
        f"📊 <b>{sym_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Price:  <b>${price_str}</b>\n"
        f"Change: <b>{sign}{change_pct:.2f}%</b> {arrow}\n"
        f"High:   {high_str}\n"
        f"Low:    {low_str}\n"
    )
    if sparkline_url:
        text += f"\n<a href='{sparkline_url}'>📈 24h Chart</a>\n"
    text += "\nMyInvestmentMarkets"

    return text, build_price_keyboard(cat_key, sym_name)

# ── Main keyboard message ───────────────────────────────────────────────────
MAIN_TEXT = (
    "⚡️ <b>MIM Live Market Terminal</b>\n\n"
    "Access institutional-grade market data instantly.\n\n"
    "Tap the button below to launch your interactive terminal and track real-time quotes, "
    "30-day candlestick charts, and live trends directly within Telegram.\n\n"
    "<i>🌐 Equities · Indices · Crypto · Forex · Commodities</i>"
)

# ── Callback handler ────────────────────────────────────────────────────────
def handle_callback(callback):
    cid   = callback["id"]
    data  = callback["data"]
    msg   = callback["message"]
    chat  = msg["chat"]["id"]
    mid   = msg["message_id"]
    thread = msg.get("message_thread_id")

    answer_callback(cid)

    if data.startswith("cat:"):
        cat_key = data.split(":")[1]
        cat = CATEGORIES[cat_key]
        text = f"📊 <b>{cat['label']}</b>\nSelect a symbol:"
        edit_message(chat, mid, text, build_symbol_keyboard(cat_key))

    elif data == "back:categories":
        edit_message(chat, mid, MAIN_TEXT, build_category_keyboard())

    elif data.startswith("sym:"):
        _, cat_key, sym_name = data.split(":", 2)
        text, keyboard = build_price_text(sym_name, cat_key)
        edit_message(chat, mid, text, keyboard)

# ── Vercel handler ──────────────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            update = json.loads(body)

            if "callback_query" in update:
                handle_callback(update["callback_query"])

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            print(f"Webhook error: {e}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"MyInvestmentMarkets Bot Webhook Active")
