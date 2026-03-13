"""
Trading Education Bot — MyInvestmentMarkets
Generates professional chart + educational commentary using:
- yfinance (OHLCV data)
- pandas-ta (technical indicators)
- mplfinance (chart image)
- Gemini API (educational narrative)
Triggered by GitHub Actions: Mon/Wed/Fri KST 10:00
"""

import json
import os
import io
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
CHAT_ID = -1003754818644
TOPIC_EDUCATION = 7  # tra
KST = timezone(timedelta(hours=9))

# ── Strategy rotation ──────────────────────────────────────────────────────
STRATEGIES = [
    {
        "name": "RSI & Momentum",
        "symbol": "^NDX",
        "display": "Nasdaq 100 (US100)",
        "indicators": ["RSI", "EMA20", "EMA50"],
        "description": "Understanding momentum shifts using the Relative Strength Index (RSI)"
    },
    {
        "name": "MACD Trend Following",
        "symbol": "^GSPC",
        "display": "S&P 500 (US500)",
        "indicators": ["MACD", "EMA50"],
        "description": "Identifying trend direction and strength using MACD histograms and crossovers"
    },
    {
        "name": "Bollinger Bands Volatility",
        "symbol": "GC=F",
        "display": "Gold (XAUUSD)",
        "indicators": ["BB", "Volume"],
        "description": "Analyzing market volatility and potential mean-reverting conditions"
    },
    {
        "name": "Moving Average Alignment",
        "symbol": "CL=F",
        "display": "WTI Crude Oil",
        "indicators": ["EMA20", "EMA50", "EMA200"],
        "description": "Using multiple EMAs to assess long-term and short-term trend confirmation"
    },
    {
        "name": "Stochastic Oscillators",
        "symbol": "EURUSD=X",
        "display": "EUR/USD",
        "indicators": ["Stochastic", "RSI"],
        "description": "Identifying overbought/oversold extreme zones in ranging markets"
    },
    {
        "name": "Price Action & Volume",
        "symbol": "^DJI",
        "display": "Dow Jones (US30)",
        "indicators": ["ATR", "Volume", "EMA20"],
        "description": "Analyzing current price action context against trading volume and volatility"
    },
    {
        "name": "Dual Momentum",
        "symbol": "BTC-USD",
        "display": "Bitcoin (BTC/USD)",
        "indicators": ["RSI", "MACD"],
        "description": "Combining RSI and MACD to build confluence in momentum analysis"
    },
    {
        "name": "Trend Reversal Zones",
        "symbol": "^N225",
        "display": "Nikkei 225 (JP225)",
        "indicators": ["BB", "RSI"],
        "description": "Spotting potential exhaustion using Bollinger Band extremes and RSI conditions"
    },
    {
        "name": "ATR Volatility Sizing",
        "symbol": "GBPUSD=X",
        "display": "GBP/USD",
        "indicators": ["ATR", "EMA50"],
        "description": "Using Average True Range (ATR) to understand daily volatility boundaries"
    },
    {
        "name": "The 200-Day Baseline",
        "symbol": "AAPL",
        "display": "Apple (AAPL)",
        "indicators": ["EMA50", "EMA200", "Volume"],
        "description": "Assessing the macro trend environment relative to the critical 200 EMA"
    }
]

def get_daily_index(pool_size):
    """Returns a rotating index based on the day of the year."""
    day_num = datetime.now(KST).timetuple().tm_yday
    return day_num % pool_size

def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()

def fetch_website_strategies():
    """Fetches articles from the MIM education feed and maps them to strategy format."""
    try:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            import subprocess
            import sys
            subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4"])
            from bs4 import BeautifulSoup
            
        url = "https://www.myinvestmentmarkets.com/support/education-feed/en"
        html = fetch_url(url)
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.find_all("article")
        
        web_strats = []
        for art in articles:
            title_tag = art.find("h2") or art.find("h1") or art.find("h3")
            if not title_tag: continue
            title = title_tag.get_text(strip=True)
            
            # Simple text extraction
            paragraphs = [p.get_text(strip=True) for p in art.find_all("p")]
            desc = " ".join(paragraphs)[:400] + "..." if paragraphs else title
            
            # Dynamic mapping heuristics
            t_low = title.lower()
            
            symbol = "^DJI" # Default
            if "fed" in t_low or "election" in t_low or "interest" in t_low: symbol = "^GSPC"
            elif "software" in t_low or "ai" in t_low or "tech" in t_low: symbol = "^NDX"
            elif "fx" in t_low or "correlation" in t_low: symbol = "EURUSD=X"
            elif "gold" in t_low or "silver" in t_low: symbol = "GC=F"
            
            indicators = ["EMA20", "RSI"] # Default
            if "volume" in t_low or "profile" in t_low or "flow" in t_low: indicators = ["Volume", "EMA20"]
            elif "volatility" in t_low or "atr" in t_low or "squeeze" in t_low: indicators = ["BB", "ATR"]
            elif "trend" in t_low or "macd" in t_low or "ema" in t_low: indicators = ["MACD", "EMA50"]
            elif "momentum" in t_low or "stochastic" in t_low: indicators = ["RSI", "Stochastic"]
            
            web_strats.append({
                "name": title,
                "symbol": symbol,
                "display": symbol, # fallback, will be overwritten in UI map later if needed
                "indicators": indicators,
                "description": desc
            })
        return web_strats
    except Exception as e:
        print(f"Error fetching web strategies: {e}")
        return []

def get_ohlcv(symbol, period="90d"):
    import urllib.parse
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range={period}"
    data = json.loads(fetch_url(url))
    result = data["chart"]["result"][0]
    timestamps = result["timestamps"]
    quotes = result["indicators"]["quote"][0]
    opens   = quotes["open"]
    highs   = quotes["high"]
    lows    = quotes["low"]
    closes  = quotes["close"]
    volumes = quotes["volume"]
    return timestamps, opens, highs, lows, closes, volumes

def build_chart_and_indicators(strategy):
    """Generate chart using mplfinance and compute indicators via pandas-ta"""
    import pandas as pd
    import pandas_ta as ta
    import mplfinance as mpf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    symbol = strategy["symbol"]
    timestamps, opens, highs, lows, closes, volumes = get_ohlcv(symbol)

    from datetime import date
    dates = [datetime.utcfromtimestamp(ts).date() for ts in timestamps]

    df = pd.DataFrame({
        "Open": opens, "High": highs, "Low": lows,
        "Close": closes, "Volume": volumes
    }, index=pd.DatetimeIndex(dates))
    df.dropna(inplace=True)
    df = df.tail(60)  # Last 60 candles

    strat_name = strategy["name"]
    indicators = strategy["indicators"]
    result = {}

    # Add plots list for mplfinance addplot
    addplots = []
    panel = 1

    # ── RSI ────────────────────────────────────────────────────────────────
    if "RSI" in indicators:
        df["RSI"] = ta.rsi(df["Close"], length=14)
        result["RSI(14)"] = f"{df['RSI'].iloc[-1]:.1f}"
        rsi_plot = mpf.make_addplot(df["RSI"], panel=panel, color="#f39c12",
                                     ylabel="RSI", secondary_y=False)
        addplots.append(rsi_plot)
        panel += 1

    # ── MACD ───────────────────────────────────────────────────────────────
    if "MACD" in indicators:
        macd_df = ta.macd(df["Close"])
        if macd_df is not None and not macd_df.empty:
            df["MACD"] = macd_df.iloc[:, 0]
            df["MACDs"] = macd_df.iloc[:, 1]
            result["MACD"] = f"{df['MACD'].iloc[-1]:.2f}"
            macd_plot = mpf.make_addplot(df["MACD"], panel=panel, color="#3498db",
                                          ylabel="MACD", secondary_y=False)
            sig_plot  = mpf.make_addplot(df["MACDs"], panel=panel, color="#e74c3c",
                                          secondary_y=False)
            addplots.extend([macd_plot, sig_plot])
            panel += 1

    # ── Bollinger Bands ────────────────────────────────────────────────────
    if "BB" in indicators:
        bb_df = ta.bbands(df["Close"], length=20)
        if bb_df is not None and not bb_df.empty:
            df["BB_U"] = bb_df.iloc[:, 0]
            df["BB_L"] = bb_df.iloc[:, 2]
            result["BB Upper"] = f"{df['BB_U'].iloc[-1]:,.2f}"
            result["BB Lower"] = f"{df['BB_L'].iloc[-1]:,.2f}"
            bb_upper = mpf.make_addplot(df["BB_U"], panel=0, color="#9b59b6", linestyle="--")
            bb_lower = mpf.make_addplot(df["BB_L"], panel=0, color="#9b59b6", linestyle="--")
            addplots.extend([bb_upper, bb_lower])

    # ── EMAs ───────────────────────────────────────────────────────────────
    for ema in ["EMA20", "EMA50", "EMA200"]:
        if ema in indicators:
            length = int(ema.replace("EMA", ""))
            col = f"EMA{length}"
            df[col] = ta.ema(df["Close"], length=length)
            result[f"EMA({length})"] = f"{df[col].iloc[-1]:,.2f}"
            colors = {"EMA20": "#27ae60", "EMA50": "#f39c12", "EMA200": "#e74c3c"}
            ema_plot = mpf.make_addplot(df[col], panel=0, color=colors.get(ema, "#aaa"))
            addplots.append(ema_plot)

    # ── Stochastic ─────────────────────────────────────────────────────────
    if "Stochastic" in indicators:
        stoch_df = ta.stoch(df["High"], df["Low"], df["Close"])
        if stoch_df is not None and not stoch_df.empty:
            df["STOCHk"] = stoch_df.iloc[:, 0]
            result["Stoch %K"] = f"{df['STOCHk'].iloc[-1]:.1f}"
            stoch_plot = mpf.make_addplot(df["STOCHk"], panel=panel, color="#1abc9c",
                                           ylabel="Stoch", secondary_y=False)
            addplots.append(stoch_plot)
            panel += 1

    # ── Generate chart image ───────────────────────────────────────────────
    mc = mpf.make_marketcolors(
        up="#00d4aa", down="#ff4757",
        edge="inherit", wick="inherit",
        volume="in"
    )
    style = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle="--", gridcolor="#333",
        facecolor="#1a1a2e", figcolor="#1a1a2e",
        rc={"axes.labelcolor": "white", "xtick.color": "white", "ytick.color": "white"}
    )

    buf = io.BytesIO()
    fig_kwargs = {
        "type": "candle",
        "style": style,
        "title": f"\nMyInvestmentMarkets — {strategy['display']}",
        "ylabel": "Price",
        "volume": True,
        "addplot": addplots if addplots else None,
        "figsize": (12, 8),
        "returnfig": True,
    }
    if not addplots:
        fig_kwargs.pop("addplot")

    fig, axes = mpf.plot(df, **fig_kwargs)

    # Watermark
    fig.text(0.5, 0.01, "MyInvestmentMarkets | Not Financial Advice",
             ha="center", color="#555", fontsize=9)

    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                facecolor="#1a1a2e")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue(), result, df

def gemini_education(strategy, indicator_values, recent_close):
    prompt = f"""You are a professional CFD trading educator at MyInvestmentMarkets.
Write an educational lesson about: {strategy['name']} using {strategy['display']} as a live example.

Current indicator values (LIVE DATA):
{chr(10).join(f'- {k}: {v}' for k, v in indicator_values.items())}
Recent closing price: {recent_close:.4f}

Write exactly 3 concise paragraphs:
1. Explain the core concept of {strategy['name']} and how it generally works.
2. Objectively state what the LIVE DATA values (above) indicate right now. ONLY state facts based on the numbers provided.
3. Detail how a trader applies this knowledge to manage risk or plan trades.

CRITICAL RULES:
- IMPORTANT: DO NOT hallucinate specific chart patterns (e.g. divergence, squeeze, crossover, engulfing candle) unless the numerical values perfectly prove it.
- Never give direct financial advice or buy/sell signals.
- End the output with a single bold sentence starting with "💡 Key Takeaway:"
- Keep it under 250 words total."""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 350}
    }
    data = json.dumps(payload).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()

def tg_send_photo(photo_bytes, caption):
    import multipart
    # Use Telegram sendPhoto with multipart/form-data
    boundary = "----TelegramBotBoundary"
    body = b""
    # chat_id
    body += f"------TelegramBotBoundary\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n".encode()
    # message_thread_id
    body += f"------TelegramBotBoundary\r\nContent-Disposition: form-data; name=\"message_thread_id\"\r\n\r\n{TOPIC_EDUCATION}\r\n".encode()
    # parse_mode
    body += b"------TelegramBotBoundary\r\nContent-Disposition: form-data; name=\"parse_mode\"\r\n\r\nHTML\r\n"
    # caption
    cap_encoded = caption.encode("utf-8")
    body += b"------TelegramBotBoundary\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n" + cap_encoded + b"\r\n"
    # photo
    body += b"------TelegramBotBoundary\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"chart.png\"\r\nContent-Type: image/png\r\n\r\n"
    body += photo_bytes + b"\r\n"
    body += b"------TelegramBotBoundary--\r\n"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=----TelegramBotBoundary"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def run():
    web_strategies = fetch_website_strategies()
    master_pool = STRATEGIES + web_strategies
    if not master_pool:
        print("No strategies found.")
        return

    idx = get_daily_index(len(master_pool))
    strategy = master_pool[idx]
    
    # Improve display names dynamically
    sym_map = {
        "^NDX": "Nasdaq 100", "^GSPC": "S&P 500", "GC=F": "Gold", 
        "CL=F": "WTI Crude", "EURUSD=X": "EUR/USD", "^DJI": "Dow Jones",
        "BTC-USD": "Bitcoin", "^N225": "Nikkei 225", "GBPUSD=X": "GBP/USD", "AAPL": "Apple"
    }
    if strategy["display"] == strategy["symbol"]:
        strategy["display"] = sym_map.get(strategy["symbol"], strategy["symbol"])
    
    print(f"📚 Strategy: {strategy['name']} — {strategy['display']}")

    # Build chart + compute indicators
    chart_bytes, indicator_values, df = build_chart_and_indicators(strategy)
    recent_close = df["Close"].iloc[-1]

    # Generate Gemini commentary
    print("🧠 Requesting AI commentary...")
    try:
        commentary = gemini_education(strategy, indicator_values, df.iloc[-1]['Close'])
    except Exception as e:
        print(f"Gemini API failed: {e}")
        commentary = strategy.get("description", "Education commentary is unavailable at this moment.")
    
    if not commentary:
        commentary = strategy.get("description", "Education commentary is unavailable.")
    else:
        # Prevent Telegram HTML parse errors by escaping rogue tags
        commentary = commentary.replace("<", "&lt;").replace(">", "&gt;")

    # HTML escaping helper
    def safe(txt):
        return str(txt).replace("<", "&lt;").replace(">", "&gt;")

    safe_name = safe(strategy['name'])[:50]
    safe_desc = safe(strategy.get('description', ''))
    safe_display = safe(strategy['display'])

    indicators_text = "\n".join(f"{k}: {v}" for k, v in indicator_values.items())
    now_str = datetime.now(KST).strftime("%b %d, %Y")

    header = f"🎓 <b>TRADING EDUCATION — {safe_name}</b>\n━━━━━━━━━━━━━━━━━━━━\n📌 <b>"
    mid = f"</b>\n\n"
    footer = (
        f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Values ({safe_display})</b>\n"
        f"{indicators_text}\n\n"
        f"MIM | {now_str}"
    )

    static_len = len(header) + len(mid) + len(footer)
    budget = 1010 - static_len

    # Allocate max 150 chars to description
    if len(safe_desc) > 150:
        safe_desc = safe_desc[:147] + "..."

    # Allocate the rest to commentary
    com_budget = budget - len(safe_desc)
    if len(commentary) > com_budget:
        commentary = commentary[:com_budget-3] + "..."

    caption = header + safe_desc + mid + commentary + footer

    tg_send_photo(chart_bytes, caption)
    print(f"✅ Education post sent: {strategy['name']}")

if __name__ == "__main__":
    run()
