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
            "EURO 50": "^STOXX50E",
            "US 30": "^DJI",
            "HK 50": "^HSI",
            "JP 225": "^N225",
            "UK 100": "^FTSE",
            "US 100": "^NDX",
            "US 500": "^GSPC"
        }
    },
    "crypto": {
        "label": "암호화폐",
        "symbols": {
            "BTC/USD": "BTC-USD",
            "ETH/USD": "ETH-USD",
            "XRP/USD": "XRP-USD",
            "DOGE/USD": "DOGE-USD",
            "SOL/USD": "SOL-USD"
        }
    },
    "forex": {
        "label": "외환",
        "symbols": {
            "AUD/CAD": "AUDCAD=X", "AUD/CHF": "AUDCHF=X", "AUD/JPY": "AUDJPY=X", "AUD/NZD": "AUDNZD=X", "AUD/USD": "AUDUSD=X",
            "CAD/JPY": "CADJPY=X", "CHF/JPY": "CHFJPY=X",
            "EUR/AUD": "EURAUD=X", "EUR/CHF": "EURCHF=X", "EUR/GBP": "EURGBP=X", "EUR/JPY": "EURJPY=X", "EUR/USD": "EURUSD=X",
            "GBP/AUD": "GBPAUD=X", "GBP/JPY": "GBPJPY=X", "GBP/USD": "GBPUSD=X", "GBP/CAD": "GBPCAD=X", "GBP/NZD": "GBPNZD=X",
            "NZD/JPY": "NZDJPY=X", "NZD/USD": "NZDUSD=X",
            "USD/CAD": "USDCAD=X", "USD/CHF": "USDCHF=X", "USD/HKD": "USDHKD=X", "USD/JPY": "USDJPY=X", "USD/SGD": "USDSGD=X", "USD/CNH": "USDCNH=X", "USD/THB": "USDTHB=X"
        }
    },
    "commodities": {
        "label": "원자재",
        "symbols": {
            "Silver": "SI=F",
            "Gold": "GC=F",
            "WTI Crude": "CL=F",
            "Brent Crude": "BZ=F",
            "Natural Gas": "NG=F"
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
            {"text": "📊 실시간 시세 및 캔들 차트 열기", "url": app_url}
        ]]
    }
    p = {
        "chat_id": chat_id,
        "text": "📊 <b>MyInvestmentMarkets — Live Prices</b>\n\n아래 버튼을 눌러 시세표와 차트를 엽니다. (알림 없이 본인 단말기에만 뜨는 프라이빗 팝업창입니다)",
        "parse_mode": "HTML",
        "reply_markup": kb
    }
    if thread_id:
        p["message_thread_id"] = thread_id
    tg("sendMessage", p)


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


# ── API Endpoint ────────────────────────────────────────────────────────────
def handle_api_quote(environ):
    try:
        qs = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))
        cat = qs.get("cat", [""])[0]
        sym = qs.get("sym", [""])[0]
        
        if cat not in CATEGORIES or sym not in CATEGORIES[cat]["symbols"]:
            return {"error": "Invalid symbol"}
            
        ticker = CATEGORIES[cat]["symbols"][sym]
        
        # We unified everything to Yahoo Finance
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
