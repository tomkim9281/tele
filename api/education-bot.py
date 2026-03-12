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
        "name": "RSI Divergence",
        "symbol": "^NDX",
        "display": "Nasdaq 100 (US100)",
        "indicators": ["RSI", "EMA20", "EMA50"],
        "description": "Using RSI divergence to spot potential reversals on US100"
    },
    {
        "name": "MACD Crossover",
        "symbol": "^GSPC",
        "display": "S&P 500 (US500)",
        "indicators": ["MACD", "EMA50"],
        "description": "Identifying trend changes using MACD crossover signals"
    },
    {
        "name": "Bollinger Band Squeeze",
        "symbol": "GC=F",
        "display": "Gold (XAUUSD)",
        "indicators": ["BB", "Volume"],
        "description": "Trading volatility breakouts using Bollinger Band Squeeze"
    },
    {
        "name": "Multi-Timeframe EMA",
        "symbol": "CL=F",
        "display": "WTI Crude Oil",
        "indicators": ["EMA20", "EMA50", "EMA200"],
        "description": "Using EMA 20/50/200 alignment for trend confirmation"
    },
    {
        "name": "Stochastic Strategy",
        "symbol": "EURUSD=X",
        "display": "EUR/USD",
        "indicators": ["Stochastic", "RSI"],
        "description": "Identifying overbought/oversold zones using Stochastics"
    },
    {
        "name": "Support & Resistance Breakout",
        "symbol": "^DJI",
        "display": "Dow Jones (US30)",
        "indicators": ["ATR", "Volume", "EMA20"],
        "description": "Trading confirmed breakouts above key resistance levels"
    },
]

def get_week_index():
    """Returns a rotating index (0-5) based on ISO week number"""
    week_num = datetime.now(KST).isocalendar()[1]
    return week_num % len(STRATEGIES)

def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()

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

Strategy being taught: {strategy['name']}
Instrument: {strategy['display']}
Current indicator values:
{chr(10).join(f'- {k}: {v}' for k, v in indicator_values.items())}
Recent closing price: {recent_close:.4f}

Write educational commentary in 3-4 paragraphs:
1. Briefly explain what {strategy['name']} is and why traders use it
2. Describe what the current chart/indicator readings suggest about {strategy['display']}
3. Explain how a trader would use this setup to plan an entry/exit

Rules:
- Plain English, explain any jargon used
- Never give direct buy/sell signals — use "signals suggest", "traders may watch for"
- End with exactly ONE sentence starting with "💡 Key Takeaway:"
- Total response max 250 words"""

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
    strategy = STRATEGIES[get_week_index()]
    print(f"📚 Strategy: {strategy['name']} — {strategy['display']}")

    # Build chart + compute indicators
    chart_bytes, indicator_values, df = build_chart_and_indicators(strategy)
    recent_close = df["Close"].iloc[-1]

    # Gemini educational commentary
    try:
        commentary = gemini_education(strategy, indicator_values, recent_close)
    except Exception as e:
        commentary = f"Today we analyze {strategy['name']} on {strategy['display']}."

    # Build caption
    indicators_text = "\n".join(f"{k}: {v}" for k, v in indicator_values.items())
    now_str = datetime.now(KST).strftime("%b %d, %Y")

    caption = (
        f"🎓 <b>TRADING EDUCATION — {strategy['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{strategy['description']}</b>\n\n"
        f"{commentary}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Current Values ({strategy['display']})</b>\n"
        f"{indicators_text}\n\n"
        f"MyInvestmentMarkets  |  {now_str}"
    )

    # Caption limit is 1024 chars for photos
    if len(caption) > 1020:
        caption = caption[:1017] + "..."

    tg_send_photo(chart_bytes, caption)
    print(f"✅ Education post sent: {strategy['name']}")

if __name__ == "__main__":
    run()
