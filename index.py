"""
MyInvestmentMarkets Bot — WSGI entry point
Architecture: Telegram Web App (WebView)
- GET / : Serves the Web App HTML
- GET /api/quote : Returns JSON price + OHLC for frontend chart
- POST /api/telegram-webhook : Handles /start to send the Web App button
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── Data Definitions ────────────────────────────────────────────────────────
CATEGORIES = {
    "stocks": {
        "label": "주식",
        "symbols": {
            "AAPL": "AAPL", "AMZN": "AMZN", "GOOG": "GOOG", "MSFT": "MSFT", 
            "NFLX": "NFLX", "TSLA": "TSLA", "AMD": "AMD", "GOOGL": "GOOGL", 
            "NVDA": "NVDA", "META": "META"
        }
    },
    "indices": {
        "label": "지수",
        "symbols": {
            "EURO50.c": "^STOXX50E",
            "US30.c": "^DJI",
            "HK50.c": "^HSI",
            "JP225.c": "^N225",
            "UK100.c": "^FTSE",
            "US100.c": "^NDX",
            "US500.c": "^GSPC"
        }
    },
    "crypto": {
        "label": "암호화폐",
        "symbols": {
            "BTCUSD.nx": "bitcoin",
            "ETHUSD.nx": "ethereum",
            "XRPUSD.nx": "ripple",
            "DOGEUSD.nx": "dogecoin",
            "SOLUSD.nx": "solana"
        }
    },
    "forex": {
        "label": "외환",
        "symbols": {
            "AUDCAD": "AUDCAD=X", "AUDCHF": "AUDCHF=X", "AUDJPY": "AUDJPY=X", "AUDNZD": "AUDNZD=X", "AUDUSD": "AUDUSD=X",
            "CADJPY": "CADJPY=X", "CHFJPY": "CHFJPY=X",
            "EURAUD": "EURAUD=X", "EURCHF": "EURCHF=X", "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X", "EURUSD": "EURUSD=X",
            "GBPAUD": "GBPAUD=X", "GBPJPY": "GBPJPY=X", "GBPUSD": "GBPUSD=X", "GBPCAD": "GBPCAD=X", "GBPNZD": "GBPNZD=X",
            "NZDJPY": "NZDJPY=X", "NZDUSD": "NZDUSD=X",
            "USDCAD": "USDCAD=X", "USDCHF": "USDCHF=X", "USDHKD": "USDHKD=X", "USDJPY": "USDJPY=X", "USDSGD": "USDSGD=X", "USDCNH": "USDCNH=X", "USDTHB": "USDTHB=X"
        }
    },
    "commodities": {
        "label": "원자재",
        "symbols": {
            "XAGUSD": "SI=F",
            "XAUUSD": "GC=F",
            "USOIL.c": "CL=F",
            "UKOIL.c": "BZ=F",
            "XNGUSD": "NG=F"
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
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except:
        return {}

def send_webapp_message(chat_id, thread_id):
    """Sends the message with the Web App button"""
    app_url = "https://tel1-three.vercel.app/"
    kb = {
        "inline_keyboard": [[
            {"text": "📊 실시간 시세 및 캔들 차트 열기", "web_app": {"url": app_url}}
        ]]
    }
    p = {
        "chat_id": chat_id,
        "text": "📊 <b>MyInvestmentMarkets — Live Prices</b>\n\n아래 버튼을 눌러 시세표와 차트를 엽니다. (알림 없이 본인만 조작 가능한 독립 웹앱 화면이 열립니다.)",
        "parse_mode": "HTML",
        "reply_markup": kb
    }
    if thread_id:
        p["message_thread_id"] = thread_id
    tg("sendMessage", p)

def edit_webapp_message(chat_id, msg_id):
    """Updates the pinned message to have the Web App button"""
    app_url = "https://tel1-three.vercel.app/"
    kb = {
        "inline_keyboard": [[
            {"text": "📊 실시간 시세 및 캔들 차트 열기", "web_app": {"url": app_url}}
        ]]
    }
    p = {
        "chat_id": chat_id,
        "message_id": msg_id,
        "text": "📊 <b>MyInvestmentMarkets — Live Prices</b>\n\n아래 버튼을 눌러 시세표와 차트를 엽니다. (알림 없이 본인만 조작 가능한 독립 웹앱 화면이 열립니다.)",
        "parse_mode": "HTML",
        "reply_markup": kb
    }
    tg("editMessageText", p)

# ── Price Fetchers ──────────────────────────────────────────────────────────
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def get_yf_data(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?interval=1d&range=30d"
    result = fetch(url)["chart"]["result"][0]
    
    meta = result["meta"]
    price = meta.get("regularMarketPrice", 0)
    prev  = meta.get("chartPreviousClose", meta.get("previousClose", price))
    pct   = ((price - prev) / prev * 100) if prev else 0
    high  = meta.get("regularMarketDayHigh", price)
    low   = meta.get("regularMarketDayLow", price)
    
    timestamps = result.get("timestamp") or result.get("timestamps", [])
    q = result["indicators"]["quote"][0]
    ohlc = []
    
    for i, ts in enumerate(timestamps):
        try:
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None not in (o, h, l, c):
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                ohlc.append({"time": dt, "open": round(o,5), "high": round(h,5), "low": round(l,5), "close": round(c,5)})
        except Exception:
            pass
            
    return {"price": price, "change_pct": pct, "high": high, "low": low, "ohlc": ohlc}

def get_cg_data(cg_id):
    url_p = (f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}"
             f"&vs_currencies=usd&include_24hr_change=true"
             f"&include_high_24h=true&include_low_24h=true")
    d = fetch(url_p)[cg_id]
    price = d["usd"]
    pct   = d.get("usd_24h_change", 0)
    high  = d.get("usd_24h_high", price)
    low   = d.get("usd_24h_low", price)
    
    url_c = f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc?vs_currency=usd&days=30"
    raw = fetch(url_c)
    ohlc = []
    for row in raw:
        ts_ms, o, h, l, c = row
        dt = datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc).strftime("%Y-%m-%d")
        ohlc.append({"time": dt, "open": round(o,5), "high": round(h,5), "low": round(l,5), "close": round(c,5)})
        
    return {"price": price, "change_pct": pct, "high": high, "low": low, "ohlc": ohlc}

# ── API Endpoint ────────────────────────────────────────────────────────────
def handle_api_quote(environ):
    try:
        qs = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))
        cat = qs.get("cat", [""])[0]
        sym = qs.get("sym", [""])[0]
        
        if cat not in CATEGORIES or sym not in CATEGORIES[cat]["symbols"]:
            return {"error": "Invalid symbol"}
            
        ticker = CATEGORIES[cat]["symbols"][sym]
        
        if cat == "crypto":
            data = get_cg_data(ticker)
        else:
            data = get_yf_data(ticker)
            
        data["symbol"] = sym
        return data
    except Exception as e:
        print(f"API Error: {e}")
        return {"error": str(e)}

# ── WSGI Router ─────────────────────────────────────────────────────────────
def app(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    # 1. Telegram Webhook (handle initialization via command)
    if method == "POST" and "/telegram-webhook" in path:
        try:
            length = int(environ.get("CONTENT_LENGTH", 0) or 0)
            body = environ["wsgi.input"].read(length)
            update = json.loads(body)
            # Just ignore incoming callback_queries from old pinned message
            # Or handle /webapp command
            msg = update.get("message", {})
            if msg.get("text", "").startswith("/webapp"):
                send_webapp_message(msg["chat"]["id"], msg.get("message_thread_id"))
        except Exception as e:
            print(f"Webhook error: {e}")
            
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"OK"]
        
    # 2. API Quote Endpoint (used by frontend)
    if path.startswith("/api/quote"):
        start_response("200 OK", [
            ("Content-Type", "application/json"),
            ("Access-Control-Allow-Origin", "*")
        ])
        return [json.dumps(handle_api_quote(environ)).encode()]
        
    # 3. Web App Static HTML (GET /)
    try:
        with open("webapp.html", "r", encoding="utf-8") as f:
            html = f.read()
    except:
        html = "<h1>webapp.html not found</h1>"
        
    start_response("200 OK", [("Content-Type", "text/html")])
    return [html.encode("utf-8")]
