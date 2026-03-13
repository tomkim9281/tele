"""
Daily Market Briefing Bot — MyInvestmentMarkets
Supports 3 session modes: us, eu, asia
Triggered by GitHub Actions Cron at each market close time.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
CHAT_ID = -1003754818644
TOPIC_BRIEFING = 5
KST = timezone(timedelta(hours=9))

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

def fc(val): return f"+{val:.2f}%" if val >= 0 else f"{val:.2f}%"
def ar(val): return "▲" if val >= 0 else "▼"
def fmt(v, d=2): return f"{v:,.{d}f}"

def gemini(system, user):
    if not GEMINI_KEY:
        return None
    try:
        payload = json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.65, "maxOutputTokens": 750}
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

def fetch_prices(symbol_map):
    prices = {}
    for name, (ticker, dec) in symbol_map.items():
        try:
            p, pv, c = get_yf_price(ticker)
            prices[name] = (p, pv, c, dec)
        except Exception as e:
            print(f"Failed {name}: {e}")
            prices[name] = (0, 0, 0, dec)
    return prices

def pline(prices, name):
    p, pv, c, d = prices[name]
    return f"{name}: {fmt(pv,d)} → {fmt(p,d)} ({fc(c)})"

def get_forexfactory_events(week="thisweek"):
    url = f"https://nfs.faireconomy.media/ff_calendar_{week}.xml"
    try:
        root = ET.fromstring(fetch_url(url))
        events = []
        today = datetime.now(KST).strftime("%b %d, %Y")
        tomorrow = (datetime.now(KST) + timedelta(days=1)).strftime("%b %d, %Y")
        for ev in root.findall("event"):
            events.append({
                "title": ev.findtext("title", ""), "country": ev.findtext("country", ""),
                "date": ev.findtext("date", ""), "time": ev.findtext("time", ""),
                "impact": ev.findtext("impact", ""), "forecast": ev.findtext("forecast", ""),
                "previous": ev.findtext("previous", ""), "actual": ev.findtext("actual", "")
            })
        return events, today, tomorrow
    except Exception as e:
        print(f"ForexFactory error: {e}")
        return [], "", ""

# ══════════════════════════════════════════════════════════════════════════════
# SESSION: US
# ══════════════════════════════════════════════════════════════════════════════
def run_us():
    date_str = datetime.now(KST).strftime("%b %d, %Y")
    syms = {
        "S&P 500": ("^GSPC",2), "Nasdaq 100": ("^NDX",2),
        "Dow Jones": ("^DJI",2), "Russell 2K": ("^RUT",2),
        "2Y Yield": ("^IRX",3), "10Y Yield": ("^TNX",3),
        "DXY": ("DX-Y.NYB",3), "Gold": ("GC=F",2),
        "WTI": ("CL=F",2), "NatGas": ("NG=F",3),
    }
    P = fetch_prices(syms)

    mkt = "\n".join([
        "[US EQUITIES]", pline(P,"S&P 500"), pline(P,"Nasdaq 100"),
        pline(P,"Dow Jones"), pline(P,"Russell 2K"),
        "\n[FIXED INCOME]", pline(P,"2Y Yield"), pline(P,"10Y Yield"),
        "\n[FX & COMMODITIES]", pline(P,"DXY"), pline(P,"Gold"),
        pline(P,"WTI"), pline(P,"NatGas"),
    ])

    sys_prompt = (
        "You are a senior macro analyst with 15 years on Wall Street. "
        "Write an institutional-grade US market close briefing. "
        "Voice: Bloomberg/Reuters standard. No emojis. No AI self-reference. "
        "Structure: 6 paragraphs — session theme / equity detail / fixed income / "
        "dollar-energy-commodities / economic data impact / tomorrow's risk factors. "
        "Use exact figures provided."
    )
    narrative = gemini(sys_prompt, f"Write US market close briefing for {date_str}:\n\n{mkt}")
    if not narrative:
        narrative = f"US equity markets closed with mixed performance. The S&P 500 moved {fc(P['S&P 500'][2])} to {fmt(P['S&P 500'][0])}."

    # ForexFactory
    events, today, tomorrow = get_forexfactory_events("thisweek")
    next_ev, _, _ = get_forexfactory_events("nextweek")
    today_ev = [e for e in events+next_ev if e["date"]==today and e["impact"] in ("High","Medium") and e["actual"]]
    tmrw_ev  = [e for e in events+next_ev if e["date"]==tomorrow and e["impact"] in ("High","Medium")]

    def star(i): return "★★★" if i=="High" else "★★"
    ind_text = ""
    for e in today_ev[:6]:
        ind_text += f"{e['time']} {e['title']} {star(e['impact'])}  {e['actual']}"
        if e["forecast"]:
            ind_text += f" (Fcst: {e['forecast']}"
            if e["previous"]: ind_text += f" | Prev: {e['previous']}"
            ind_text += ")"
        ind_text += "\n"

    tmrw_text = ""
    for e in tmrw_ev[:6]:
        tmrw_text += f"{e['time']} {e['country']} {e['title']} {star(e['impact'])}"
        if e["forecast"]:
            tmrw_text += f"\n  Fcst: {e['forecast']}"
            if e["previous"]: tmrw_text += f" | Prev: {e['previous']}"
        tmrw_text += "\n"
    if not tmrw_text: tmrw_text = "No major events scheduled."

    sp,_,spc,_=P["S&P 500"]; nd,_,ndc,_=P["Nasdaq 100"]
    dj,_,djc,_=P["Dow Jones"]; ru,_,ruc,_=P["Russell 2K"]
    y2,y2p,y2c,_=P["2Y Yield"]; y10,y10p,y10c,_=P["10Y Yield"]
    dxy,dxyp,dxyc,_=P["DXY"]; gld,gldp,gldc,_=P["Gold"]
    wti,wtip,wtic,_=P["WTI"]; ng,ngp,ngc,_=P["NatGas"]

    msg = f"""━━━━━━━━━━━━━━━━━━━━
📉 <b>US MARKET CLOSE — {date_str}</b>
━━━━━━━━━━━━━━━━━━━━

{narrative}

━━━━━━━━━━━━━━━━━━━━
🇺🇸 <b>US EQUITIES</b>
S&amp;P 500      {fc(spc)} → {fmt(sp)}  {ar(spc)}
Nasdaq 100   {fc(ndc)} → {fmt(nd)}  {ar(ndc)}
Dow Jones    {fc(djc)} → {fmt(dj)}  {ar(djc)}
Russell 2K   {fc(ruc)} → {fmt(ru)}  {ar(ruc)}

📊 <b>FIXED INCOME</b>
2Y Yield   {fmt(y2p,3)}% → {fmt(y2,3)}% {ar(y2c)}
10Y Yield  {fmt(y10p,3)}% → {fmt(y10,3)}% {ar(y10c)}

💵 <b>FX &amp; COMMODITIES</b>
DXY     {fmt(dxyp,3)} → {fmt(dxy,3)} {ar(dxyc)}
Gold    {fmt(gldp)} → {fmt(gld)} {ar(gldc)}
WTI     {fmt(wtip)} → {fmt(wti)} {ar(wtic)}
NatGas  {fmt(ngp,3)} → {fmt(ng,3)} {ar(ngc)}"""

    if ind_text:
        msg += f"""

📋 <b>TODAY'S DATA RELEASES</b>
{ind_text.strip()}"""

    msg += f"""

━━━━━━━━━━━━━━━━━━━━
<b>【TOMORROW — Key Events】</b>

{tmrw_text.strip()}
━━━━━━━━━━━━━━━━━━━━
MyInvestmentMarkets"""

    tg_send(msg)
    print("✅ US briefing sent.")

# ══════════════════════════════════════════════════════════════════════════════
# SESSION: EUROPE
# ══════════════════════════════════════════════════════════════════════════════
def run_eu():
    date_str = datetime.now(KST).strftime("%b %d, %Y")
    syms = {
        "Euro Stoxx 50": ("^STOXX50E",2), "DAX 40": ("^GDAXI",2),
        "FTSE 100": ("^FTSE",2), "CAC 40": ("^FCHI",2),
        "EUR/USD": ("EURUSD=X",4), "GBP/USD": ("GBPUSD=X",4),
        "Bund 10Y": ("^BUND",3),
        "Brent": ("BZ=F",2), "Gold": ("GC=F",2),
    }
    P = fetch_prices(syms)

    mkt = "\n".join([
        "[EU EQUITIES]", pline(P,"Euro Stoxx 50"), pline(P,"DAX 40"),
        pline(P,"FTSE 100"), pline(P,"CAC 40"),
        "\n[FX]", pline(P,"EUR/USD"), pline(P,"GBP/USD"),
        "\n[COMMODITIES]", pline(P,"Brent"), pline(P,"Gold"),
    ])

    sys_prompt = (
        "You are a senior European macro strategist at a global investment bank. "
        "Write an institutional-grade European market close briefing. "
        "Voice: Bloomberg/Reuters standard. No emojis. No AI self-reference. "
        "Structure: 4 paragraphs — session theme / sector rotation & index drivers / "
        "euro-sterling-rates dynamics / US session outlook. Use exact figures."
    )
    narrative = gemini(sys_prompt, f"Write European market close briefing for {date_str}:\n\n{mkt}")
    if not narrative:
        narrative = f"European equities closed the session with the Euro Stoxx 50 moving {fc(P['Euro Stoxx 50'][2])} to {fmt(P['Euro Stoxx 50'][0])}."

    sx,_,sxc,_=P["Euro Stoxx 50"]; dx,_,dxc,_=P["DAX 40"]
    ft,_,ftc,_=P["FTSE 100"]; ca,_,cac,_=P["CAC 40"]
    eu,eup,euc,_=P["EUR/USD"]; gb,gbp,gbc,_=P["GBP/USD"]
    br,brp,brc,_=P["Brent"]; gl,glp,glc,_=P["Gold"]

    msg = f"""━━━━━━━━━━━━━━━━━━━━
📊 <b>EUROPE MARKET CLOSE — {date_str}</b>
━━━━━━━━━━━━━━━━━━━━

{narrative}

━━━━━━━━━━━━━━━━━━━━
🇪🇺 <b>EU EQUITIES</b>
Euro Stoxx 50  {fc(sxc)} → {fmt(sx)}  {ar(sxc)}
DAX 40         {fc(dxc)} → {fmt(dx)}  {ar(dxc)}
FTSE 100       {fc(ftc)} → {fmt(ft)}  {ar(ftc)}
CAC 40         {fc(cac)} → {fmt(ca)}  {ar(cac)}

💱 <b>FX</b>
EUR/USD  {fmt(eup,4)} → {fmt(eu,4)} {ar(euc)}
GBP/USD  {fmt(gbp,4)} → {fmt(gb,4)} {ar(gbc)}

🛢 <b>COMMODITIES</b>
Brent   {fmt(brp)} → {fmt(br)} {ar(brc)}
Gold    {fmt(glp)} → {fmt(gl)} {ar(glc)}

━━━━━━━━━━━━━━━━━━━━
MyInvestmentMarkets"""

    tg_send(msg)
    print("✅ EU briefing sent.")

# ══════════════════════════════════════════════════════════════════════════════
# SESSION: ASIA
# ══════════════════════════════════════════════════════════════════════════════
def run_asia():
    date_str = datetime.now(KST).strftime("%b %d, %Y")
    syms = {
        "Nikkei 225": ("^N225",2), "Hang Seng": ("^HSI",2),
        "KOSPI": ("^KS11",2), "Shanghai": ("000001.SS",2),
        "USD/JPY": ("JPY=X",3), "USD/KRW": ("KRW=X",2),
        "Gold": ("GC=F",2),
    }
    P = fetch_prices(syms)

    mkt = "\n".join([
        "[ASIA EQUITIES]", pline(P,"Nikkei 225"), pline(P,"Hang Seng"),
        pline(P,"KOSPI"), pline(P,"Shanghai"),
        "\n[FX]", pline(P,"USD/JPY"), pline(P,"USD/KRW"),
        "\n[COMMODITIES]", pline(P,"Gold"),
    ])

    sys_prompt = (
        "You are a senior Asia-Pacific macro analyst at a global prime brokerage. "
        "Write an institutional-grade Asia market close briefing. "
        "Voice: Bloomberg/Reuters standard. No emojis. No AI self-reference. "
        "Structure: 4 paragraphs — session theme / Japan-Nikkei / China-HK / Korea-KOSPI & outlook. "
        "Use exact figures."
    )
    narrative = gemini(sys_prompt, f"Write Asia market close briefing for {date_str}:\n\n{mkt}")
    if not narrative:
        narrative = f"Asian equities closed the session with the Nikkei 225 moving {fc(P['Nikkei 225'][2])} to {fmt(P['Nikkei 225'][0])}."

    nk,_,nkc,_=P["Nikkei 225"]; hs,_,hsc,_=P["Hang Seng"]
    ks,_,ksc,_=P["KOSPI"]; sh,_,shc,_=P["Shanghai"]
    jy,jyp,jyc,_=P["USD/JPY"]; kr,krp,krc,_=P["USD/KRW"]
    gl,glp,glc,_=P["Gold"]

    msg = f"""━━━━━━━━━━━━━━━━━━━━
📊 <b>ASIA MARKET CLOSE — {date_str}</b>
━━━━━━━━━━━━━━━━━━━━

{narrative}

━━━━━━━━━━━━━━━━━━━━
🌏 <b>ASIA EQUITIES</b>
Nikkei 225    {fc(nkc)} → {fmt(nk)}  {ar(nkc)}
Hang Seng     {fc(hsc)} → {fmt(hs)}  {ar(hsc)}
KOSPI         {fc(ksc)} → {fmt(ks)}  {ar(ksc)}
Shanghai      {fc(shc)} → {fmt(sh)}  {ar(shc)}

💱 <b>FX</b>
USD/JPY  {fmt(jyp,3)} → {fmt(jy,3)} {ar(jyc)}
USD/KRW  {fmt(krp,2)} → {fmt(kr,2)} {ar(krc)}

🥇 <b>COMMODITIES</b>
Gold     {fmt(glp)} → {fmt(gl)} {ar(glc)}

━━━━━━━━━━━━━━━━━━━━
MyInvestmentMarkets"""

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
