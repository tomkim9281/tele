"""
Daily Market Briefing Bot — MIM Global Financial Services
Supports 3 session modes: us, eu, asia
Triggered by GitHub Actions Cron at each market close time.
Uses GEMINI_API_KEY2 for daily briefing narrative.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY2", "")   # dedicated briefing key
CHAT_ID    = -1003754818644
TOPIC_BRIEFING = 5
UTC = timezone.utc

def tg_send(text):
    payload = {
        "chat_id": CHAT_ID, "message_thread_id": TOPIC_BRIEFING,
        "text": text, "parse_mode": "HTML", "disable_web_page_preview": True
    }
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()

def get_yf_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=2d"
    data = json.loads(fetch_url(url))
    meta = data["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice", 0)
    prev  = meta.get("chartPreviousClose", meta.get("previousClose", price))
    change = ((price - prev) / prev * 100) if prev else 0
    return price, prev, change

def fetch_prices(symbol_map):
    prices = {}
    for name, (ticker, dec) in symbol_map.items():
        try:
            p, pv, c = get_yf_price(ticker)
            prices[name] = (p, c, dec)
        except Exception as e:
            print(f"Failed {name}: {e}")
            prices[name] = (0, 0, dec)
    return prices

def fmt(v, d=2):
    return f"{v:,.{d}f}"

def pct_badge(c):
    """Return colored percentage badge"""
    sign = "+" if c >= 0 else ""
    box  = "🟩" if c >= 0 else "🟥"
    return f"{box} {sign}{c:.2f}%"

def yield_arrow(c):
    return "▲" if c >= 0 else "▼"

def gemini_narrative(system, user):
    if not GEMINI_KEY:
        return None
    try:
        payload = json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.65, "maxOutputTokens": 800}
        }).encode()
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}",
            data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.loads(r.read())
        return res["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"Gemini error: {e}")
        return None

# ══════════════════════════════════════════════════════════════════════════════
# SESSION: US
# ══════════════════════════════════════════════════════════════════════════════
def run_us():
    now_utc  = datetime.now(UTC)
    date_str = now_utc.strftime("Mar %d, %Y")  # e.g. Mar 13, 2026

    syms = {
        "S&P 500":    ("^GSPC",  2),
        "Nasdaq 100": ("^NDX",   2),
        "Dow Jones":  ("^DJI",   2),
        "Russell 2000":("^RUT",  2),
        "2Y Yield":   ("^IRX",   3),
        "10Y Yield":  ("^TNX",   3),
        "DXY":        ("DX-Y.NYB",3),
        "Gold":       ("GC=F",   2),
        "WTI Crude":  ("CL=F",   2),
        "NatGas":     ("NG=F",   3),
    }
    P = fetch_prices(syms)

    def p(name): return P[name][0]
    def c(name): return P[name][1]
    def d(name): return P[name][2]

    # Build data string for Gemini
    data_str = (
        f"S&P 500: {fmt(p('S&P 500'))} ({c('S&P 500'):+.2f}%)\n"
        f"Nasdaq 100: {fmt(p('Nasdaq 100'))} ({c('Nasdaq 100'):+.2f}%)\n"
        f"Dow Jones: {fmt(p('Dow Jones'))} ({c('Dow Jones'):+.2f}%)\n"
        f"Russell 2000: {fmt(p('Russell 2000'))} ({c('Russell 2000'):+.2f}%)\n"
        f"2Y Yield: {fmt(p('2Y Yield'),3)}% ({c('2Y Yield'):+.3f}p)\n"
        f"10Y Yield: {fmt(p('10Y Yield'),3)}% ({c('10Y Yield'):+.3f}p)\n"
        f"DXY: {fmt(p('DXY'),3)} ({c('DXY'):+.2f}%)\n"
        f"Gold: {fmt(p('Gold'))} ({c('Gold'):+.2f}%)\n"
        f"WTI Crude: {fmt(p('WTI Crude'))} ({c('WTI Crude'):+.2f}%)\n"
        f"NatGas: {fmt(p('NatGas'),3)} ({c('NatGas'):+.2f}%)\n"
    )

    sys_prompt = (
        "You are a senior macro analyst with 15 years of experience on Wall Street. "
        "Write an institutional-grade market close briefing for a global CFD brokerage. "
        "Voice: Bloomberg/Reuters editorial standard. No hype. "
        "Structure: 6 paragraphs — theme / oil-rates-dollar chain / equity detail / "
        "economic data impact / quote attribution / tomorrow's risk factors. "
        "No emojis inside narrative. No AI self-reference."
    )
    narrative = gemini_narrative(
        sys_prompt,
        f"Write US market close briefing for {date_str}:\n\n{data_str}"
    )
    if not narrative:
        narrative = f"US equity markets closed with broad-based losses. The S&P 500 fell {c('S&P 500'):.2f}% to {fmt(p('S&P 500'))}."

    # Yield formatting (show as bps change)
    y2c  = c("2Y Yield");  y10c = c("10Y Yield")
    y2bps  = int(round(y2c  * 100 / p("2Y Yield")))  if p("2Y Yield")  else 0
    y10bps = int(round(y10c * 100 / p("10Y Yield"))) if p("10Y Yield") else 0

    msg = (
        f"🔔 <b>[MIM DAILY BRIEFING] US Market Close</b>\n\n"
        f"🗓 {date_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"📝 <b>Market Overview</b>\n"
        f"{narrative}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"📊 <b>US EQUITIES</b>\n"
        f"🇺🇸 S&amp;P 500:      {fmt(p('S&P 500'))}  ({pct_badge(c('S&P 500'))})\n"
        f"🇺🇸 Nasdaq 100:   {fmt(p('Nasdaq 100'))}  ({pct_badge(c('Nasdaq 100'))})\n"
        f"🇺🇸 Dow Jones:    {fmt(p('Dow Jones'))}  ({pct_badge(c('Dow Jones'))})\n"
        f"🇺🇸 Russell 2000: {fmt(p('Russell 2000'))}  ({pct_badge(c('Russell 2000'))})\n\n"

        f"📈 <b>FIXED INCOME (Yields)</b>\n"
        f"🇺🇸 02Y Yield: {fmt(p('2Y Yield'),3)}%  ({yield_arrow(y2c)} {abs(y2bps):+d}bps)\n"
        f"🇺🇸 10Y Yield: {fmt(p('10Y Yield'),3)}%  ({yield_arrow(y10c)} {abs(y10bps):+d}bps)\n\n"

        f"🛢️ <b>FX &amp; COMMODITIES</b>\n"
        f"💵 DXY (Dollar):  {fmt(p('DXY'),3)}  ({pct_badge(c('DXY'))})\n"
        f"🥇 Gold:           {fmt(p('Gold'))}  ({pct_badge(c('Gold'))})\n"
        f"🛢️ WTI Crude:     {fmt(p('WTI Crude'))}  ({pct_badge(c('WTI Crude'))})\n"
        f"⛽ NatGas:         {fmt(p('NatGas'),3)}  ({pct_badge(c('NatGas'))})\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡️ MIM Global Financial Services"
    )

    tg_send(msg)
    print("✅ US briefing sent.")

# ══════════════════════════════════════════════════════════════════════════════
# SESSION: EUROPE
# ══════════════════════════════════════════════════════════════════════════════
def run_eu():
    now_utc  = datetime.now(UTC)
    date_str = now_utc.strftime("Mar %d, %Y")

    syms = {
        "Euro Stoxx 50": ("^STOXX50E", 2),
        "DAX 40":        ("^GDAXI",    2),
        "FTSE 100":      ("^FTSE",     2),
        "CAC 40":        ("^FCHI",     2),
        "EUR/USD":       ("EURUSD=X",  4),
        "GBP/USD":       ("GBPUSD=X",  4),
        "Brent":         ("BZ=F",      2),
        "Gold":          ("GC=F",      2),
    }
    P = fetch_prices(syms)

    def p(name): return P[name][0]
    def c(name): return P[name][1]

    data_str = "\n".join([
        f"Euro Stoxx 50: {fmt(p('Euro Stoxx 50'))} ({c('Euro Stoxx 50'):+.2f}%)",
        f"DAX 40: {fmt(p('DAX 40'))} ({c('DAX 40'):+.2f}%)",
        f"FTSE 100: {fmt(p('FTSE 100'))} ({c('FTSE 100'):+.2f}%)",
        f"CAC 40: {fmt(p('CAC 40'))} ({c('CAC 40'):+.2f}%)",
        f"EUR/USD: {fmt(p('EUR/USD'),4)} ({c('EUR/USD'):+.2f}%)",
        f"GBP/USD: {fmt(p('GBP/USD'),4)} ({c('GBP/USD'):+.2f}%)",
        f"Brent: {fmt(p('Brent'))} ({c('Brent'):+.2f}%)",
        f"Gold: {fmt(p('Gold'))} ({c('Gold'):+.2f}%)",
    ])

    sys_prompt = (
        "You are a senior European macro strategist at a global investment bank. "
        "Write an institutional-grade European market close briefing. "
        "Voice: Bloomberg/Reuters editorial standard. No hype. No emojis. No AI self-reference. "
        "Structure: 4 paragraphs — session theme / sector rotation & index drivers / "
        "euro-sterling-rates dynamics / US session outlook. Use exact figures."
    )
    narrative = gemini_narrative(
        sys_prompt,
        f"Write European market close briefing for {date_str}:\n\n{data_str}"
    )
    if not narrative:
        narrative = f"European equities closed with the Euro Stoxx 50 at {fmt(p('Euro Stoxx 50'))} ({c('Euro Stoxx 50'):+.2f}%)."

    msg = (
        f"🔔 <b>[MIM DAILY BRIEFING] European Market Close</b>\n\n"
        f"🗓 {date_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"📝 <b>Market Overview</b>\n"
        f"{narrative}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"📊 <b>EU EQUITIES</b>\n"
        f"🇪🇺 Euro Stoxx 50: {fmt(p('Euro Stoxx 50'))}  ({pct_badge(c('Euro Stoxx 50'))})\n"
        f"🇩🇪 DAX 40:         {fmt(p('DAX 40'))}  ({pct_badge(c('DAX 40'))})\n"
        f"🇬🇧 FTSE 100:       {fmt(p('FTSE 100'))}  ({pct_badge(c('FTSE 100'))})\n"
        f"🇫🇷 CAC 40:         {fmt(p('CAC 40'))}  ({pct_badge(c('CAC 40'))})\n\n"

        f"💱 <b>FX</b>\n"
        f"🇪🇺 EUR/USD: {fmt(p('EUR/USD'),4)}  ({pct_badge(c('EUR/USD'))})\n"
        f"🇬🇧 GBP/USD: {fmt(p('GBP/USD'),4)}  ({pct_badge(c('GBP/USD'))})\n\n"

        f"🛢️ <b>COMMODITIES</b>\n"
        f"🛢️ Brent: {fmt(p('Brent'))}  ({pct_badge(c('Brent'))})\n"
        f"🥇 Gold:  {fmt(p('Gold'))}  ({pct_badge(c('Gold'))})\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡️ MIM Global Financial Services"
    )

    tg_send(msg)
    print("✅ EU briefing sent.")

# ══════════════════════════════════════════════════════════════════════════════
# SESSION: ASIA
# ══════════════════════════════════════════════════════════════════════════════
def run_asia():
    now_utc  = datetime.now(UTC)
    date_str = now_utc.strftime("Mar %d, %Y")

    syms = {
        "Nikkei 225": ("^N225",      2),
        "Hang Seng":  ("^HSI",       2),
        "KOSPI":      ("^KS11",      2),
        "Shanghai":   ("000001.SS",  2),
        "USD/JPY":    ("JPY=X",      3),
        "USD/KRW":    ("KRW=X",      2),
        "Gold":       ("GC=F",       2),
    }
    P = fetch_prices(syms)

    def p(name): return P[name][0]
    def c(name): return P[name][1]

    data_str = "\n".join([
        f"Nikkei 225: {fmt(p('Nikkei 225'))} ({c('Nikkei 225'):+.2f}%)",
        f"Hang Seng: {fmt(p('Hang Seng'))} ({c('Hang Seng'):+.2f}%)",
        f"KOSPI: {fmt(p('KOSPI'))} ({c('KOSPI'):+.2f}%)",
        f"Shanghai: {fmt(p('Shanghai'))} ({c('Shanghai'):+.2f}%)",
        f"USD/JPY: {fmt(p('USD/JPY'),3)} ({c('USD/JPY'):+.2f}%)",
        f"USD/KRW: {fmt(p('USD/KRW'),2)} ({c('USD/KRW'):+.2f}%)",
        f"Gold: {fmt(p('Gold'))} ({c('Gold'):+.2f}%)",
    ])

    sys_prompt = (
        "You are a senior Asia-Pacific macro analyst at a global prime brokerage. "
        "Write an institutional-grade Asia market close briefing. "
        "Voice: Bloomberg/Reuters editorial standard. No hype. No emojis. No AI self-reference. "
        "Structure: 4 paragraphs — session theme / Japan-Nikkei / China-HK / Korea-KOSPI & outlook. "
        "Use exact figures."
    )
    narrative = gemini_narrative(
        sys_prompt,
        f"Write Asia market close briefing for {date_str}:\n\n{data_str}"
    )
    if not narrative:
        narrative = f"Asian equities closed with the Nikkei 225 at {fmt(p('Nikkei 225'))} ({c('Nikkei 225'):+.2f}%)."

    msg = (
        f"🔔 <b>[MIM DAILY BRIEFING] Asian Market Close</b>\n\n"
        f"🗓 {date_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"📝 <b>Market Overview</b>\n"
        f"{narrative}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"📊 <b>ASIA EQUITIES</b>\n"
        f"🇯🇵 Nikkei 225: {fmt(p('Nikkei 225'))}  ({pct_badge(c('Nikkei 225'))})\n"
        f"🇭🇰 Hang Seng:  {fmt(p('Hang Seng'))}  ({pct_badge(c('Hang Seng'))})\n"
        f"🇰🇷 KOSPI:       {fmt(p('KOSPI'))}  ({pct_badge(c('KOSPI'))})\n"
        f"🇨🇳 Shanghai:    {fmt(p('Shanghai'))}  ({pct_badge(c('Shanghai'))})\n\n"

        f"💱 <b>FX</b>\n"
        f"💴 USD/JPY: {fmt(p('USD/JPY'),3)}  ({pct_badge(c('USD/JPY'))})\n"
        f"🇰🇷 USD/KRW: {fmt(p('USD/KRW'),2)}  ({pct_badge(c('USD/KRW'))})\n\n"

        f"🥇 <b>COMMODITIES</b>\n"
        f"🥇 Gold: {fmt(p('Gold'))}  ({pct_badge(c('Gold'))})\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡️ MIM Global Financial Services"
    )

    tg_send(msg)
    print("✅ Asia briefing sent.")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "us"
    print(f"Running {mode} briefing...")
    if mode == "us":
        run_us()
    elif mode == "eu":
        run_eu()
    elif mode == "asia":
        run_asia()
    else:
        print(f"Unknown mode: {mode}. Use: us, eu, asia")
