"""
MyInvestmentMarkets Bot — WSGI entry point

ARCHITECTURE: DM-based sessions
  - Group portal message has buttons → user clicks
  - Bot sends DM to that user privately (nobody else sees it)
  - All price interaction happens in user's private chat
  - True privacy: other group members never see any price queries

SPEED: Vercel Hobby has 10s function timeout
  - Price fetch: Yahoo Finance meta (fast ~1s)
  - Chart: QuickChart direct GET URL embedded in text (no /chart/create POST)
  - Telegram link preview shows chart image automatically

CRYPTO: CoinGecko API (Binance blocked on Vercel US East servers)
"""

import json
import os
import urllib.request
import urllib.parse

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Get bot username at module load time (used for DM start link)
_BOT_USERNAME = None
def get_bot_username():
    global _BOT_USERNAME
    if _BOT_USERNAME:
        return _BOT_USERNAME
    try:
        req = urllib.request.Request(f"{BASE_URL}/getMe")
        with urllib.request.urlopen(req, timeout=5) as r:
            result = json.loads(r.read())
            _BOT_USERNAME = result["result"].get("username", "")
            return _BOT_USERNAME
    except Exception:
        return ""

CATEGORIES = {
    "indices": {
        "label": "📈 Indices",
        "symbols": {
            "US100": ("^NDX",    "yf"),
            "US500": ("^GSPC",   "yf"),
            "US30":  ("^DJI",    "yf"),
            "DE40":  ("^GDAXI",  "yf"),
            "JP225": ("^N225",   "yf"),
        }
    },
    "forex": {
        "label": "💱 Forex",
        "symbols": {
            "EURUSD": ("EURUSD=X", "yf"),
            "GBPUSD": ("GBPUSD=X", "yf"),
            "USDJPY": ("JPY=X",    "yf"),
            "AUDUSD": ("AUDUSD=X", "yf"),
            "USDCAD": ("CAD=X",    "yf"),
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
            "Gold":   ("GC=F", "yf"),
            "Silver": ("SI=F", "yf"),
            "WTI":    ("CL=F", "yf"),
            "Gas":    ("NG=F", "yf"),
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
        return {"ok": False}

def answer_cb(cid, text=None, alert=False):
    p = {"callback_query_id": cid}
    if text:
        p["text"] = text
        p["show_alert"] = alert
    tg("answerCallbackQuery", p)

def send_dm(user_id, text, kb=None):
    """Send a private message directly to user. user_id == dm chat_id in Telegram."""
    p = {"chat_id": user_id, "text": text,
         "parse_mode": "HTML", "disable_web_page_preview": False}
    if kb:
        p["reply_markup"] = kb
    return tg("sendMessage", p)

def edit_dm(user_id, msg_id, text, kb=None):
    p = {"chat_id": user_id, "message_id": msg_id,
         "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": False}
    if kb:
        p["reply_markup"] = kb
    return tg("editMessageText", p)

def delete_dm(user_id, msg_id):
    tg("deleteMessage", {"chat_id": user_id, "message_id": msg_id})

# ── Price data ──────────────────────────────────────────────────────────────
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
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

def get_cg_price(cg_id):
    url = (f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}"
           f"&vs_currencies=usd&include_24hr_change=true"
           f"&include_high_24h=true&include_low_24h=true")
    d = fetch(url)[cg_id]
    return (d["usd"], d.get("usd_24h_change", 0),
            d.get("usd_24h_high", d["usd"]), d.get("usd_24h_low", d["usd"]))

# ── QuickChart line chart (fast GET URL, no API roundtrip) ──────────────────
def make_line_chart_url(sym, ticker, source):
    """
    Fetch 30-day close prices and build a QuickChart GET URL.
    Uses line chart (fast, compact JSON) for Telegram link preview.
    MIM watermark in chart title.
    """
    try:
        if source == "yf":
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
                   f"{urllib.parse.quote(ticker)}?interval=1d&range=30d")
            result = fetch(url)["chart"]["result"][0]
            # 'timestamp' key (no trailing s) — fixed
            timestamps = result.get("timestamp") or result.get("timestamps", [])
            closes = result["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if c is not None][-20:]
        else:
            url = (f"https://api.coingecko.com/api/v3/coins/{ticker}/market_chart"
                   f"?vs_currency=usd&days=20&interval=daily")
            data = fetch(url)
            closes = [p[1] for p in data["prices"]][-20:]

        if len(closes) < 2:
            return None

        color = "#00d4aa" if closes[-1] >= closes[0] else "#ff4757"

        cfg = {
            "type": "line",
            "data": {
                "labels": list(range(len(closes))),
                "datasets": [{
                    "data": [round(c, 4) for c in closes],
                    "borderColor": color,
                    "backgroundColor": color + "22",
                    "borderWidth": 2,
                    "pointRadius": 0,
                    "fill": True,
                    "tension": 0.3
                }]
            },
            "options": {
                "title": {"display": True,
                          "text": f"{sym} — 20D | MyInvestmentMarkets",
                          "fontColor": "#ddd", "fontSize": 12},
                "legend": {"display": False},
                "scales": {
                    "xAxes": [{"display": False}],
                    "yAxes": [{"display": True,
                               "ticks": {"fontColor": "#aaa", "maxTicksLimit": 4},
                               "gridLines": {"color": "rgba(255,255,255,0.07)"}}]
                }
            }
        }
        encoded = urllib.parse.quote(json.dumps(cfg, separators=(',', ':')))
        return f"https://quickchart.io/chart?w=600&h=240&bkg=%231a1a2e&c={encoded}"
    except Exception as e:
        print(f"Chart error [{sym}]: {e}")
        return None

# ── Price text builder ──────────────────────────────────────────────────────
def smart_dec(sym, price):
    if any(x in sym for x in ["US100","US500","US30","DE40","JP225"]): return 2
    if sym in ("USDJPY",): return 3
    if price > 1000: return 2
    if price > 1:    return 4
    return 6

def build_price_text(sym_name, cat_key):
    ticker, source = CATEGORIES[cat_key]["symbols"][sym_name]
    try:
        if source == "yf":
            price, pct, high, low = get_yf_price(ticker)
        else:
            price, pct, high, low = get_cg_price(ticker)

        dec   = smart_dec(sym_name, price)
        arrow = "🔺" if pct >= 0 else "🔻"
        sign  = "+" if pct >= 0 else ""

        chart_url = make_line_chart_url(sym_name, ticker, source)

        text = (
            f"📊 <b>{sym_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Price:  <b>{price:,.{dec}f}</b>\n"
            f"Change: <b>{sign}{pct:.2f}%</b> {arrow}\n"
            f"High:   {high:,.{dec}f}\n"
            f"Low:    {low:,.{dec}f}\n"
        )
        if chart_url:
            text += f'\n<a href="{chart_url}">📈 20-Day Chart | MyInvestmentMarkets</a>\n'
        else:
            text += "\n<i>MyInvestmentMarkets</i>\n"

        return text
    except Exception as e:
        return f"⚠️ <b>{sym_name}</b> — error: {e}"

# ── Keyboards (all use uid → DM chat_id, not group chat_id) ────────────────
def category_kb(uid):
    rows = []
    row = []
    for key, cat in CATEGORIES.items():
        row.append({"text": cat["label"], "callback_data": f"c:{key}:{uid}"})
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([{"text": "✕ Close", "callback_data": f"x:{uid}"}])
    return {"inline_keyboard": rows}

def symbol_kb(cat_key, uid):
    rows = []
    row = []
    for sym in CATEGORIES[cat_key]["symbols"]:
        row.append({"text": sym, "callback_data": f"s:{cat_key}:{sym}:{uid}"})
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([
        {"text": "← Back", "callback_data": f"b:{uid}"},
        {"text": "✕ Close", "callback_data": f"x:{uid}"}
    ])
    return {"inline_keyboard": rows}

def price_kb(cat_key, sym_name, uid):
    return {"inline_keyboard": [[
        {"text": "🔄 Refresh",  "callback_data": f"s:{cat_key}:{sym_name}:{uid}"},
        {"text": "← Back",     "callback_data": f"c:{cat_key}:{uid}"},
        {"text": "✕ Close",    "callback_data": f"x:{uid}"}
    ]]}

# Portal keyboard for shared group message (no uid — anyone taps)
def portal_kb():
    return {"inline_keyboard": [
        [{"text": "📈 Indices",     "callback_data": "go:indices"},
         {"text": "💱 Forex",       "callback_data": "go:forex"}],
        [{"text": "₿ Crypto",       "callback_data": "go:crypto"},
         {"text": "🥇 Commodities", "callback_data": "go:commodities"}]
    ]}

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
    chat   = msg["chat"]["id"]       # group chat id
    mid    = msg["message_id"]
    thread = msg.get("message_thread_id")
    uid    = cb["from"]["id"]        # Telegram user id (int)
    uid_s  = str(uid)

    # ── GROUP PORTAL: open DM session ─────────────────────────────────────
    if data.startswith("go:"):
        cat_key = data[3:]
        answer_cb(cid)
        text = f"📊 <b>{CATEGORIES[cat_key]['label']}</b>\nSelect a symbol:"

        result = send_dm(uid, text, symbol_kb(cat_key, uid_s))
        if not result.get("ok"):
            # User hasn't started bot in DM
            bot_user = get_bot_username()
            answer_cb(cid,
                f"⚠️ Please start the bot first!\n👉 t.me/{bot_user}?start=1\n"
                f"Then tap the button again.",
                alert=True)
        return

    # ── DM SESSION ACTIONS (all in user's private chat) ─────────────────
    # callback_data format: "c:cat:uid", "s:cat:sym:uid", "b:uid", "x:uid"
    parts = data.split(":")
    action = parts[0]
    owner_uid = parts[-1]

    # Ownership check — only the DM owner can control their session
    if owner_uid != uid_s:
        answer_cb(cid, "⚠️ This is not your session.", alert=True)
        return

    answer_cb(cid)

    if action == "c":       # category
        cat_key = parts[1]
        edit_dm(uid, mid, f"📊 <b>{CATEGORIES[cat_key]['label']}</b>\nSelect a symbol:",
                symbol_kb(cat_key, uid_s))

    elif action == "b":     # back to category menu
        edit_dm(uid, mid, MAIN_TEXT, category_kb(uid_s))

    elif action == "s":     # symbol price
        cat_key  = parts[1]
        sym_name = parts[2]
        text = build_price_text(sym_name, cat_key)
        edit_dm(uid, mid, text, price_kb(cat_key, sym_name, uid_s))

    elif action == "x":     # close session
        delete_dm(uid, mid)

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
