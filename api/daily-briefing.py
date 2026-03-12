"""
Daily Market Briefing Bot — MyInvestmentMarkets
Triggered by GitHub Actions Cron: Every weekday at KST 06:00 (UTC 21:00)
"""

import json
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
CHAT_ID = -1003754818644
TOPIC_BRIEFING = 5  # da

KST = timezone(timedelta(hours=9))

def tg_send(text):
    payload = {
        "chat_id": CHAT_ID,
        "message_thread_id": TOPIC_BRIEFING,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def fetch_url(url, headers=None):
    h = {"User-Agent": "Mozilla/5.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
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

def fmt_change(val):
    return f"+{val:.2f}%" if val >= 0 else f"{val:.2f}%"

def dir_arrow(val):
    return "▲" if val >= 0 else "▼"

def get_forexfactory_events(week="thisweek"):
    url = f"https://nfs.faireconomy.media/ff_calendar_{week}.xml"
    try:
        raw = fetch_url(url)
        root = ET.fromstring(raw)
        events = []
        today = datetime.now(KST).strftime("%b %d, %Y")
        tomorrow_dt = datetime.now(KST) + timedelta(days=1)
        tomorrow = tomorrow_dt.strftime("%b %d, %Y")

        for ev in root.findall("event"):
            title   = ev.findtext("title", "")
            country = ev.findtext("country", "")
            date    = ev.findtext("date", "")
            time_   = ev.findtext("time", "")
            impact  = ev.findtext("impact", "")
            fcst    = ev.findtext("forecast", "")
            prev    = ev.findtext("previous", "")
            actual  = ev.findtext("actual", "")
            events.append({
                "title": title, "country": country, "date": date,
                "time": time_, "impact": impact,
                "forecast": fcst, "previous": prev, "actual": actual
            })
        return events, today, tomorrow
    except Exception as e:
        print(f"ForexFactory error: {e}")
        return [], "", ""

def get_news_headlines():
    try:
        raw = fetch_url("https://feeds.reuters.com/reuters/businessNews")
        root = ET.fromstring(raw)
        items = root.findall(".//item")[:5]
        return [item.findtext("title", "") for item in items]
    except Exception:
        return []

def gemini_narrative(market_data, indicators_text, headlines):
    system_prompt = """You are a senior macro analyst with 15 years of experience on Wall Street.
Write an institutional-grade market close briefing for a global CFD brokerage.
Voice: Bloomberg/Reuters editorial standard. Professional and concise.
Structure: 4-5 paragraphs — today's theme / oil-rates-dollar-equity chain / economic data impact / tomorrow's risk factors.
No emojis inside narrative. No AI self-reference. Use exact figures provided."""

    user_prompt = f"""Write today's US market close briefing using this data:

=== MARKET DATA ===
{market_data}

=== TODAY'S KEY ECONOMIC RELEASES ===
{indicators_text}

=== TOP NEWS HEADLINES ===
{chr(10).join(f'- {h}' for h in headlines)}

Write professional English narrative. 4-5 paragraphs. Include specific figures."""

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800}
    }
    data = json.dumps(payload).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
    return result["candidates"][0]["content"]["parts"][0]["text"]

def run():
    now_kst = datetime.now(KST)
    date_str = now_kst.strftime("%b %d, %Y")

    # ── Fetch market data ──────────────────────────────────────────────────
    symbols = {
        "S&P 500":    ("^GSPC",    2),
        "Nasdaq 100": ("^NDX",     2),
        "Dow Jones":  ("^DJI",     2),
        "Russell 2K": ("^RUT",     2),
        "2Y Yield":   ("^IRX",     3),
        "10Y Yield":  ("^TNX",     3),
        "DXY":        ("DX-Y.NYB", 3),
        "Gold":       ("GC=F",     2),
        "WTI":        ("CL=F",     2),
        "NatGas":     ("NG=F",     3),
    }

    prices = {}
    for name, (ticker, dec) in symbols.items():
        try:
            price, prev, change = get_yf_price(ticker)
            prices[name] = (price, prev, change, dec)
        except Exception as e:
            print(f"Failed {name}: {e}")
            prices[name] = (0, 0, 0, 2)

    # ── Build market data string for Gemini ───────────────────────────────
    def p(name):
        price, prev, change, dec = prices[name]
        return f"{name}: {prev:.{dec}f} → {price:.{dec}f} ({fmt_change(change)})"

    market_data_str = "\n".join([
        "[US EQUITIES]",
        p("S&P 500"), p("Nasdaq 100"), p("Dow Jones"), p("Russell 2K"),
        "\n[FIXED INCOME]",
        p("2Y Yield"), p("10Y Yield"),
        "\n[FX & COMMODITIES]",
        p("DXY"), p("Gold"), p("WTI"), p("NatGas"),
    ])

    # ── ForexFactory ─────────────────────────────────────────────────────
    events, today, tomorrow = get_forexfactory_events("thisweek")
    next_events, _, _ = get_forexfactory_events("nextweek")

    today_events = [e for e in events + next_events if e["date"] == today and e["impact"] in ("High","Medium") and e["actual"]]
    tomorrow_events = [e for e in events + next_events if e["date"] == tomorrow and e["impact"] in ("High","Medium")]

    def star(impact):
        return "★★★" if impact == "High" else "★★"

    indicators_text = ""
    for e in today_events[:6]:
        indicators_text += f"{e['time']} {e['title']} {star(e['impact'])}  {e['actual']}"
        if e["forecast"]:
            indicators_text += f" (Fcst: {e['forecast']}"
            if e["previous"]:
                indicators_text += f" | Prev: {e['previous']}"
            indicators_text += ")"
        indicators_text += "\n"

    # ── Headlines ─────────────────────────────────────────────────────────
    headlines = get_news_headlines()

    # ── Gemini narrative ──────────────────────────────────────────────────
    try:
        narrative = gemini_narrative(market_data_str, indicators_text or "No major releases today.", headlines)
    except Exception as e:
        narrative = f"Markets closed the session with mixed signals. {market_data_str[:200]}"

    # ── Tomorrow schedule ─────────────────────────────────────────────────
    tomorrow_text = ""
    if tomorrow_events:
        for e in tomorrow_events[:6]:
            tomorrow_text += f"{e['time']} {e['country']} {e['title']} {star(e['impact'])}"
            if e["forecast"]:
                tomorrow_text += f"\n  Fcst: {e['forecast']}"
                if e["previous"]:
                    tomorrow_text += f" | Prev: {e['previous']}"
            tomorrow_text += "\n"
    else:
        tomorrow_text = "No major events scheduled."

    # ── Build full message ─────────────────────────────────────────────────
    sp, _, sp_c, _ = prices["S&P 500"]
    nd, _, nd_c, _ = prices["Nasdaq 100"]
    dj, _, dj_c, _ = prices["Dow Jones"]
    rut,_, rut_c,_ = prices["Russell 2K"]
    y2, y2p, y2c,_ = prices["2Y Yield"]
    y10,y10p,y10c,_= prices["10Y Yield"]
    dxy,dxyp,dxyc,_= prices["DXY"]
    gld,gldp,gldc,_= prices["Gold"]
    wti,wtip,wtic,_= prices["WTI"]
    ng, ngp, ngc,_ = prices["NatGas"]

    msg = f"""━━━━━━━━━━━━━━━━━━━━
📉 <b>US MARKET CLOSE — {date_str}</b>
━━━━━━━━━━━━━━━━━━━━

{narrative}

━━━━━━━━━━━━━━━━━━━━
🇺🇸 <b>US EQUITIES</b>
S&P 500      {fmt_change(sp_c)} → {sp:,.2f}
Nasdaq 100   {fmt_change(nd_c)} → {nd:,.2f}
Dow Jones    {fmt_change(dj_c)} → {dj:,.2f}
Russell 2K   {fmt_change(rut_c)} → {rut:,.2f}

📊 <b>FIXED INCOME</b>
2Y Yield   {y2p:.3f}% → {y2:.3f}% {dir_arrow(y2c)}
10Y Yield  {y10p:.3f}% → {y10:.3f}% {dir_arrow(y10c)}

💵 <b>FX &amp; COMMODITIES</b>
DXY     {dxyp:.3f} → {dxy:.3f} {dir_arrow(dxyc)}
Gold    {gldp:,.2f} → {gld:,.2f} {dir_arrow(gldc)}
WTI     {wtip:.2f} → {wti:.2f} {dir_arrow(wtic)}
NatGas  {ngp:.3f} → {ng:.3f} {dir_arrow(ngc)}"""

    if indicators_text:
        msg += f"""

📋 <b>TODAY'S DATA RELEASES</b>
{indicators_text.strip()}"""

    msg += f"""

━━━━━━━━━━━━━━━━━━━━
<b>【TOMORROW — Key Events】</b>

{tomorrow_text.strip()}
━━━━━━━━━━━━━━━━━━━━
MyInvestmentMarkets"""

    tg_send(msg)
    print("✅ Daily briefing sent.")

if __name__ == "__main__":
    run()
