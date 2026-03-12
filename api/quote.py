"""
Vercel serverless function: GET /api/quote?cat=...&sym=...
Returns JSON: price, change_pct, high, low, ohlc[]
All data from Yahoo Finance (reliable, correct date ordering for charts).
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# ── Symbol map: display_name → yahoo_ticker ─────────────────────────────────
CATEGORIES = {
    "stocks": {
        "AAPL": "AAPL", "AMZN": "AMZN", "GOOG": "GOOG", "MSFT": "MSFT",
        "NFLX": "NFLX", "TSLA": "TSLA", "AMD": "AMD", "GOOGL": "GOOGL",
        "NVDA": "NVDA", "META": "META"
    },
    "indices": {
        "EURO 50": "^STOXX50E",
        "US 30":   "^DJI",
        "HK 50":   "^HSI",
        "JP 225":  "^N225",
        "UK 100":  "^FTSE",
        "US 100":  "^NDX",
        "US 500":  "^GSPC"
    },
    "crypto": {
        "BTC/USD":  "BTC-USD",
        "ETH/USD":  "ETH-USD",
        "XRP/USD":  "XRP-USD",
        "DOGE/USD": "DOGE-USD",
        "SOL/USD":  "SOL-USD"
    },
    "forex": {
        "AUD/CAD": "AUDCAD=X", "AUD/CHF": "AUDCHF=X", "AUD/JPY": "AUDJPY=X",
        "AUD/NZD": "AUDNZD=X", "AUD/USD": "AUDUSD=X", "CAD/JPY": "CADJPY=X",
        "CHF/JPY": "CHFJPY=X", "EUR/AUD": "EURAUD=X", "EUR/CHF": "EURCHF=X",
        "EUR/GBP": "EURGBP=X", "EUR/JPY": "EURJPY=X", "EUR/USD": "EURUSD=X",
        "GBP/AUD": "GBPAUD=X", "GBP/JPY": "GBPJPY=X", "GBP/USD": "GBPUSD=X",
        "GBP/CAD": "GBPCAD=X", "GBP/NZD": "GBPNZD=X", "NZD/JPY": "NZDJPY=X",
        "NZD/USD": "NZDUSD=X", "USD/CAD": "USDCAD=X", "USD/CHF": "USDCHF=X",
        "USD/HKD": "USDHKD=X", "USD/JPY": "USDJPY=X", "USD/SGD": "USDSGD=X",
        "USD/CNH": "USDCNH=X", "USD/THB": "USDTHB=X"
    },
    "commodities": {
        "Silver":       "SI=F",
        "Gold":         "GC=F",
        "WTI Crude":    "CL=F",
        "Brent Crude":  "BZ=F",
        "Natural Gas":  "NG=F"
    }
}


def fetch_yf(ticker):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker)}?interval=1d&range=30d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get_data(ticker):
    resp   = fetch_yf(ticker)
    result = resp["chart"]["result"][0]
    meta   = result["meta"]

    price = meta.get("regularMarketPrice", 0)
    prev  = meta.get("chartPreviousClose", meta.get("previousClose", price))
    pct   = ((price - prev) / prev * 100) if prev else 0
    high  = meta.get("regularMarketDayHigh", price)
    low   = meta.get("regularMarketDayLow",  price)

    timestamps = result.get("timestamp") or result.get("timestamps", [])
    q = result["indicators"]["quote"][0]

    seen_dates = set()
    ohlc = []
    for i, ts in enumerate(timestamps):
        try:
            o = q["open"][i];  h = q["high"][i]
            l = q["low"][i];   c = q["close"][i]
            if None in (o, h, l, c):
                continue
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            if dt in seen_dates:        # deduplicate dates (chart requires unique ascending)
                continue
            seen_dates.add(dt)
            ohlc.append({"time": dt,
                         "open": round(o, 6), "high": round(h, 6),
                         "low":  round(l, 6), "close": round(c, 6)})
        except Exception:
            pass

    return {"price": price, "change_pct": pct, "high": high, "low": low, "ohlc": ohlc}


def handler(request):
    """Vercel serverless handler (http.server style)."""
    try:
        params = dict(urllib.parse.parse_qs(request.query))
        cat = params.get("cat", [""])[0]
        sym = params.get("sym", [""])[0]

        if cat not in CATEGORIES or sym not in CATEGORIES[cat]:
            return {"statusCode": 400,
                    "body": json.dumps({"error": f"Unknown: cat={cat} sym={sym}"}),
                    "headers": {"Content-Type": "application/json",
                                "Access-Control-Allow-Origin": "*"}}

        ticker = CATEGORIES[cat][sym]
        data   = get_data(ticker)
        data["symbol"] = sym

        return {"statusCode": 200,
                "body": json.dumps(data),
                "headers": {"Content-Type": "application/json",
                            "Access-Control-Allow-Origin": "*"}}

    except Exception as e:
        return {"statusCode": 500,
                "body": json.dumps({"error": str(e)}),
                "headers": {"Content-Type": "application/json",
                            "Access-Control-Allow-Origin": "*"}}
