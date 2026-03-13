"""
MyInvestmentMarkets – Vercel WSGI entrypoint
Routes:
  GET /               → MIM Live Quotes web app HTML
  GET /api/quote      → JSON price + OHLC data (Yahoo Finance)
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# ── Symbol map ───────────────────────────────────────────────────────────────
CATEGORIES = {
    "stocks": {
        "AAPL": "AAPL", "AMZN": "AMZN", "GOOG": "GOOG", "MSFT": "MSFT",
        "NFLX": "NFLX", "TSLA": "TSLA", "AMD": "AMD", "GOOGL": "GOOGL",
        "NVDA": "NVDA", "META": "META"
    },
    "indices": {
        "EURO 50": "^STOXX50E", "US 30":  "^DJI",   "HK 50":  "^HSI",
        "JP 225":  "^N225",     "UK 100": "^FTSE",  "US 100": "^NDX",
        "US 500":  "^GSPC"
    },
    "crypto": {
        "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "XRP/USD":  "XRP-USD",
        "DOGE/USD": "DOGE-USD", "SOL/USD": "SOL-USD"
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
        "Silver": "SI=F", "Gold": "GC=F", "WTI Crude": "CL=F",
        "Brent Crude": "BZ=F", "Natural Gas": "NG=F"
    }
}

# ── Yahoo Finance helper ─────────────────────────────────────────────────────
def get_data(ticker):
    # 30-minute intraday bars for today
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker)}?interval=30m&range=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        resp = json.loads(r.read())

    result = resp["chart"]["result"][0]
    meta   = result["meta"]
    price  = meta.get("regularMarketPrice", 0)
    prev   = meta.get("chartPreviousClose", meta.get("previousClose", price))
    pct    = ((price - prev) / prev * 100) if prev else 0
    high   = meta.get("regularMarketDayHigh", price)
    low    = meta.get("regularMarketDayLow",  price)

    timestamps = result.get("timestamp") or result.get("timestamps", [])
    q = result["indicators"]["quote"][0]
    
    # Store unique timestamps in a dict to deduplicate, keeping the latest value
    unique_bars = {}
    for i, ts in enumerate(timestamps):
        try:
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None in (o, h, l, c): continue
            
            # Use Unix timestamps (seconds) for lightweight-charts intraday
            unique_bars[int(ts)] = {
                "time": int(ts), "open": round(o,6), "high": round(h,6),
                "low": round(l,6), "close": round(c,6)
            }
        except Exception:
            pass

    # Sort by time ascending
    ohlc = [unique_bars[t] for t in sorted(unique_bars.keys())]

    return {"price": price, "change_pct": pct, "high": high, "low": low, "ohlc": ohlc}

# ── Embedded HTML ─────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>MIM Live Terminal</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
:root{
  --bg:#0a0c12;--s1:#111420;--s2:#141824;
  --border:rgba(255,255,255,0.06);--border2:rgba(255,255,255,0.10);
  --up:#22d3b0;--dn:#f04b5a;
  --accent:#22d3b0;
  --text:#e4e6f0;--sub:#8b91a8;--muted:#58607c;
  --r:10px;
}
html,body{
  background:var(--bg);color:var(--text);
  font-family:'Inter',-apple-system,sans-serif;
  -webkit-font-smoothing:antialiased;
  overflow-x:hidden;min-height:100dvh;
}

/* ── HEADER ── */
header{
  display:flex;align-items:center;justify-content:space-between;
  padding:14px 16px 12px;
  border-bottom:1px solid var(--border);
  background:var(--bg);
  position:sticky;top:0;z-index:100;
}
.hd-left{display:flex;align-items:center;gap:10px;}
.hd-icon{
  width:32px;height:32px;border-radius:9px;flex-shrink:0;
  background:linear-gradient(135deg,#22d3b0 0%,#0055ff 100%);
  display:flex;align-items:center;justify-content:center;font-size:16px;
  box-shadow:0 0 16px rgba(34,211,176,0.25);
}
.hd-title{font-size:15px;font-weight:700;letter-spacing:-.3px;}
.hd-sub{font-size:10px;color:var(--muted);margin-top:1px;letter-spacing:.3px;font-weight:400;}
.live-pill{
  display:flex;align-items:center;gap:5px;
  background:rgba(34,211,176,0.10);
  border:1px solid rgba(34,211,176,0.20);
  border-radius:20px;padding:4px 10px;
  font-size:10px;font-weight:600;color:var(--accent);letter-spacing:.5px;
}
.live-dot{
  width:6px;height:6px;border-radius:50%;background:var(--accent);
  animation:blink 1.8s ease-in-out infinite;
}
@keyframes blink{0%,100%{opacity:1;transform:scale(1);}50%{opacity:.4;transform:scale(.8);}}

/* ── TABS ── */
#tabs{
  display:flex;overflow-x:auto;scrollbar-width:none;
  border-bottom:1px solid var(--border);
  padding:6px 12px 0;gap:2px;
}
#tabs::-webkit-scrollbar{display:none;}
#tabs button{
  flex-shrink:0;background:none;border:none;cursor:pointer;
  padding:9px 14px 10px;font-size:13px;font-weight:500;
  color:var(--muted);border-bottom:2px solid transparent;
  font-family:inherit;letter-spacing:.1px;
  transition:color .18s,border-color .18s;
}
#tabs button.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:600;}

/* ── SYMBOL GRID ── */
.grid-label{
  padding:10px 16px 4px;
  font-size:10px;font-weight:500;letter-spacing:.8px;
  color:var(--muted);text-transform:uppercase;
}
#symbols{
  display:grid;grid-template-columns:repeat(3,1fr);
  gap:7px;padding:8px 14px 10px;
}
#symbols.wide{grid-template-columns:repeat(4,1fr);gap:5px;padding:8px 10px 10px;}
#symbols button{
  padding:10px 6px;
  background:var(--s2);
  border:1px solid var(--border);
  border-radius:var(--r);
  color:var(--sub);
  font-size:11.5px;font-weight:600;
  font-family:inherit;cursor:pointer;
  transition:all .15s;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  letter-spacing:.1px;
}
#symbols.wide button{font-size:10.5px;padding:8px 4px;}
#symbols button:active{transform:scale(.96);}
#symbols button.active{
  background:rgba(34,211,176,0.12);
  color:var(--accent);
  border-color:rgba(34,211,176,0.35);
  font-weight:700;
}

/* ── PRICE CARD ── */
#price-card{
  margin:2px 14px 10px;
  padding:18px 16px 14px;
  background:var(--s2);
  border:1px solid var(--border2);
  border-radius:16px;
  display:none;
}
.pc-top{
  display:flex;justify-content:space-between;align-items:flex-start;
  margin-bottom:2px;
}
.pc-sym{font-size:17px;font-weight:700;letter-spacing:-.4px;}
.pc-price{font-size:26px;font-weight:700;letter-spacing:-.8px;line-height:1;}
.pc-right{text-align:right;}
.pc-chg{
  display:flex;align-items:center;justify-content:flex-end;gap:3px;
  font-size:12.5px;font-weight:600;margin-top:4px;
}
.pc-chg.up{color:var(--up);}
.pc-chg.dn{color:var(--dn);}
.pc-hl{
  display:flex;justify-content:space-between;
  border-top:1px solid var(--border);
  margin-top:12px;padding-top:10px;
}
.hl-block{display:flex;gap:4px;font-size:11px;color:var(--muted);}
.hl-val{font-weight:600;color:var(--sub);}

/* ── CHART CARD ── */
#chart-card{
  margin:0 14px 22px;
  background:var(--s2);
  border:1px solid var(--border);
  border-radius:16px;
  overflow:hidden;
  display:none;
}
.cc-header{
  display:flex;justify-content:space-between;align-items:center;
  padding:10px 14px 0;
}
.cc-title{font-size:11px;font-weight:600;color:var(--sub);letter-spacing:.3px;}
.cc-badges{display:flex;gap:5px;}
.cc-badge{
  font-size:10px;font-weight:600;letter-spacing:.3px;
  background:rgba(255,255,255,0.04);
  border:1px solid var(--border);
  border-radius:6px;padding:2px 7px;
  color:var(--muted);
}
.cc-badge.today{background:rgba(34,211,176,0.08);border-color:rgba(34,211,176,0.2);color:var(--accent);}
#chart-container{width:100%;height:260px;margin-top:6px;}
.cc-footer{
  text-align:center;font-size:9.5px;color:var(--muted);
  padding:6px 0 8px;letter-spacing:.3px;
}

/* ── LOADING / ERROR ── */
#loading{
  display:none;flex-direction:column;align-items:center;
  padding:44px 20px;color:var(--muted);font-size:12px;gap:12px;
}
.spinner{
  width:24px;height:24px;
  border:2.5px solid rgba(255,255,255,0.08);
  border-left-color:var(--accent);
  border-radius:50%;animation:spin .75s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg);}}
#error-msg{
  display:none;text-align:center;padding:24px 20px;
  color:var(--dn);font-size:12.5px;line-height:1.5;
}
</style>
</head>
<body>

<header>
  <div class="hd-left">
    <div class="hd-icon">📈</div>
    <div>
      <div class="hd-title">MIM Live Terminal</div>
      <div class="hd-sub">MIM Global Financial Services</div>
    </div>
  </div>
  <div class="live-pill"><div class="live-dot"></div>LIVE</div>
</header>

<div id="tabs"></div>
<div class="grid-label">SELECT INSTRUMENT</div>
<div id="symbols"></div>

<div id="loading"><div class="spinner"></div>Loading market data...</div>
<div id="error-msg"></div>

<div id="price-card">
  <div class="pc-top">
    <div class="pc-sym" id="d-sym">--</div>
    <div class="pc-right">
      <div class="pc-price" id="d-price">--</div>
      <div class="pc-chg" id="d-chg">--</div>
    </div>
  </div>
  <div class="pc-hl">
    <div class="hl-block">High <div class="hl-val" id="d-high">--</div></div>
    <div class="hl-block">Low <div class="hl-val" id="d-low">--</div></div>
  </div>
</div>

<div id="chart-card">
  <div class="cc-header">
    <div class="cc-title" id="chart-title">--</div>
    <div class="cc-badges">
      <div class="cc-badge today">TODAY</div>
      <div class="cc-badge">30 MIN</div>
    </div>
  </div>
  <div id="chart-container"></div>
  <div class="cc-footer">Intraday 30min Candlestick · MIM Global Financial Services</div>
</div>

<script>
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) { tg.expand(); tg.ready(); }

const CATS = {
  indices:     { label:'Indices',     syms:['EURO 50','US 30','HK 50','JP 225','UK 100','US 100','US 500'] },
  stocks:      { label:'Stocks',      syms:['AAPL','AMZN','GOOG','MSFT','NFLX','TSLA','AMD','NVDA','META'] },
  crypto:      { label:'Crypto',      syms:['BTC/USD','ETH/USD','XRP/USD','DOGE/USD','SOL/USD'] },
  forex:       { label:'Forex',       syms:['EUR/USD','GBP/USD','USD/JPY','AUD/USD','USD/CAD','USD/CHF','EUR/JPY','GBP/JPY','EUR/GBP','NZD/USD','USD/CNH','EUR/AUD','GBP/AUD','AUD/JPY','CHF/JPY','CAD/JPY','EUR/CHF','GBP/CAD','GBP/NZD','AUD/CAD','AUD/CHF','AUD/NZD','NZD/JPY','USD/HKD','USD/SGD','USD/THB'] },
  commodities: { label:'Commodities', syms:['Gold','Silver','WTI Crude','Brent Crude','Natural Gas'] },
};

let curCat='indices', curSym='US 100', chartObj=null, cSeries=null;

function initChart() {
  if (chartObj) return;
  const el = document.getElementById('chart-container');
  chartObj = LightweightCharts.createChart(el, {
    width: el.clientWidth,
    height: 260,
    layout: {
      background: { type:'solid', color:'transparent' },
      textColor:'#58607c',
      fontSize: 11,
    },
    grid: {
      vertLines: { color:'rgba(255,255,255,0.03)' },
      horzLines: { color:'rgba(255,255,255,0.04)' },
    },
    timeScale: {
      borderColor:'rgba(255,255,255,0.06)',
      timeVisible:true,
      secondsVisible:false,
      ticksVisible:false,
      fixLeftEdge:true,
      fixRightEdge:true,
    },
    rightPriceScale: {
      borderColor:'rgba(255,255,255,0.06)',
      scaleMargins:{ top:0.12, bottom:0.12 },
      autoScale:true,
    },
    crosshair: {
      vertLine:{ color:'rgba(255,255,255,0.15)', labelBackgroundColor:'#1a1d26' },
      horzLine:{ color:'rgba(255,255,255,0.15)', labelBackgroundColor:'#1a1d26' },
    },
    handleScroll:true,
    handleScale:true,
  });
  
  cSeries = chartObj.addCandlestickSeries({
    upColor:'#22d3b0', downColor:'#f04b5a',
    borderVisible:false,
    wickUpColor:'#22d3b0', wickDownColor:'#f04b5a',
  });
  
  window.addEventListener('resize', () => chartObj.applyOptions({ width: el.clientWidth }));
}

function fmt(sym, v) {
  if (v == null || isNaN(v)) return '--';
  let d = 2;
  if (v < 0.01) d = 6;
  else if (v < 1) d = 5;
  else if (v < 10) d = 4;
  if (sym && (sym.includes('JPY') || sym==='Silver')) d = 3;
  return Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
}

async function loadQuote(cat, sym) {
  const $load = document.getElementById('loading');
  const $err  = document.getElementById('error-msg');
  const $pc   = document.getElementById('price-card');
  const $cc   = document.getElementById('chart-card');

  $load.style.display='flex';
  $err.style.display='none';
  $pc.style.display='none';
  $cc.style.display='none';

  try {
    const res = await fetch(`/api/quote?cat=${encodeURIComponent(cat)}&sym=${encodeURIComponent(sym)}`);
    const d   = await res.json();
    if (d.error) throw new Error(d.error);

    document.getElementById('d-sym').textContent   = sym;
    document.getElementById('d-price').textContent = fmt(sym, d.price);
    const pct = Number(d.change_pct || 0);
    const chgEl = document.getElementById('d-chg');
    chgEl.innerHTML = (pct >= 0 ? '▲' : '▼') + ' ' + Math.abs(pct).toFixed(2) + '%';
    chgEl.className = 'pc-chg ' + (pct >= 0 ? 'up' : 'dn');
    document.getElementById('d-high').textContent = fmt(sym, d.high);
    document.getElementById('d-low').textContent  = fmt(sym, d.low);
    $pc.style.display='block';

    if (d.ohlc && d.ohlc.length > 1) {
      $cc.style.display='block';
      initChart();
      cSeries.setData(d.ohlc);
      chartObj.timeScale().fitContent();
      document.getElementById('chart-title').textContent = sym + ' · Today';
    }

    if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
  } catch(e) {
    $err.textContent = '⚠ Unable to load data for ' + sym + '. Please try again.';
    $err.style.display='block';
  } finally {
    $load.style.display='none';
  }
}

function renderTabs() {
  const el = document.getElementById('tabs');
  el.innerHTML='';
  Object.keys(CATS).forEach(key => {
    const btn=document.createElement('button');
    btn.textContent=CATS[key].label;
    if (key===curCat) btn.className='active';
    btn.onclick=()=>{ curCat=key; curSym=CATS[key].syms[0]; renderTabs(); renderSymbols(); loadQuote(curCat,curSym); };
    el.appendChild(btn);
  });
}

function renderSymbols() {
  const el=document.getElementById('symbols');
  el.innerHTML='';
  el.className=curCat==='forex'?'wide':'';
  CATS[curCat].syms.forEach(sym => {
    const btn=document.createElement('button');
    btn.textContent=sym;
    if (sym===curSym) btn.className='active';
    btn.onclick=()=>{ curSym=sym; renderSymbols(); loadQuote(curCat,curSym); };
    el.appendChild(btn);
  });
}

renderTabs();
renderSymbols();
loadQuote(curCat, curSym);
</script>
</body>
</html>"""

# ── WSGI app ──────────────────────────────────────────────────────────────────
def app(environ, start_response):
    path   = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    # ── /api/quote ─────────────────────────────────────────────────────────
    if path.startswith("/api/quote") or path.startswith("/api/index/api/quote"):
        try:
            qs     = environ.get("QUERY_STRING", "")
            params = urllib.parse.parse_qs(qs)
            cat    = params.get("cat", [""])[0]
            sym    = params.get("sym", [""])[0]

            if cat not in CATEGORIES or sym not in CATEGORIES[cat]:
                body = json.dumps({"error": f"Unknown cat={cat!r} sym={sym!r}"}).encode()
                status = "400 Bad Request"
            else:
                data = get_data(CATEGORIES[cat][sym])
                data["symbol"] = sym
                body   = json.dumps(data).encode()
                status = "200 OK"
        except Exception as e:
            body   = json.dumps({"error": str(e)}).encode()
            status = "500 Internal Server Error"

        start_response(status, [
            ("Content-Type",  "application/json"),
            ("Access-Control-Allow-Origin", "*"),
            ("Content-Length", str(len(body))),
        ])
        return [body]

    # ── / → serve HTML app ─────────────────────────────────────────────────
    body = HTML.encode("utf-8")
    start_response("200 OK", [
        ("Content-Type",   "text/html; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ])
    return [body]
