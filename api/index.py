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
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker)}?interval=1d&range=30d")
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
    seen, ohlc = set(), []
    for i, ts in enumerate(timestamps):
        try:
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None in (o, h, l, c): continue
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            if dt in seen: continue
            seen.add(dt)
            ohlc.append({"time": dt, "open": round(o,6), "high": round(h,6),
                         "low": round(l,6), "close": round(c,6)})
        except Exception:
            pass

    return {"price": price, "change_pct": pct, "high": high, "low": low, "ohlc": ohlc}

# ── Embedded HTML ─────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>MIM Live Quotes</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0f1117;--card:#1a1d26;--border:rgba(255,255,255,.07);--up:#00d4aa;--dn:#ff4757;--text:#e8e8f0;--muted:#6b6f8a;--accent:#00d4aa}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;overflow-x:hidden;min-height:100dvh}
header{display:flex;align-items:center;justify-content:space-between;padding:14px 16px 10px;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--bg);z-index:99}
header .logo{display:flex;align-items:center;gap:8px}
header .dot{width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,#00d4aa,#0066ff);display:flex;align-items:center;justify-content:center;font-size:14px}
header h1{font-size:16px;font-weight:700;letter-spacing:-.3px}
header p{font-size:10px;color:var(--muted)}
#closeBtn{background:none;border:none;color:var(--muted);font-size:18px;cursor:pointer;padding:4px}
#tabs{display:flex;overflow-x:auto;border-bottom:1px solid var(--border);padding:0 8px;scrollbar-width:none}
#tabs::-webkit-scrollbar{display:none}
#tabs button{flex-shrink:0;background:none;border:none;cursor:pointer;padding:12px 14px;font-size:13px;font-weight:500;color:var(--muted);border-bottom:2px solid transparent;transition:color .2s,border-color .2s}
#tabs button.active{color:var(--accent);border-bottom-color:var(--accent)}
#symbols{display:flex;flex-wrap:wrap;gap:8px;padding:12px 16px}
#symbols button{flex:1 1 calc(33% - 8px);min-width:80px;max-width:160px;padding:8px 4px;background:var(--card);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:12px;font-weight:500;cursor:pointer;transition:all .15s}
#symbols button.active{background:var(--accent);color:#000;border-color:var(--accent)}
#price-card{margin:0 16px 12px;padding:16px;background:var(--card);border:1px solid var(--border);border-radius:16px;display:none}
#price-card .row1{display:flex;justify-content:space-between;align-items:flex-start}
#price-card .sym{font-size:18px;font-weight:700}
#price-card .prc{font-size:22px;font-weight:700;text-align:right}
#price-card .chg{font-size:12px;font-weight:600;margin-top:2px}
#price-card .hl{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:12px;padding-top:10px;border-top:1px solid var(--border)}
#price-card .hl span{color:var(--text)}
.up{color:var(--up)}.dn{color:var(--dn)}
#chart-card{margin:0 16px 24px;background:var(--card);border:1px solid var(--border);border-radius:16px;overflow:hidden;display:none}
#chart-img{width:100%;display:block;border-radius:12px 12px 0 0}
#chart-loading{padding:60px 0;text-align:center;color:var(--muted);font-size:13px}
#chart-footer{text-align:center;font-size:10px;color:var(--muted);padding:6px 0}
#loading{display:none;text-align:center;padding:40px;color:var(--muted);font-size:13px}
.spinner{width:28px;height:28px;margin:0 auto 10px;border:3px solid rgba(255,255,255,.1);border-left-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#error-msg{display:none;text-align:center;padding:20px;color:var(--dn);font-size:13px}
</style>
</head>
<body>
<header>
  <div class="logo"><div class="dot">📊</div><div><h1>MIM Live Quotes</h1><p>MyInvestmentMarkets</p></div></div>
  <button id="closeBtn" onclick="Telegram.WebApp.close()">✕</button>
</header>
<div id="tabs"></div>
<div id="symbols"></div>
<div id="loading"><div class="spinner"></div>불러오는 중...</div>
<div id="error-msg"></div>
<div id="price-card">
  <div class="row1"><div class="sym" id="d-sym">--</div><div><div class="prc" id="d-price">--</div><div class="chg" id="d-chg">--</div></div></div>
  <div class="hl"><div>High &nbsp;<span id="d-high">--</span></div><div>Low &nbsp;<span id="d-low">--</span></div></div>
</div>
<div id="chart-card">
  <div id="chart-loading"><div class="spinner"></div>차트 생성 중...</div>
  <img id="chart-img" src="" alt="Candlestick Chart" style="display:none" />
  <div id="chart-footer">30D Candlestick | MyInvestmentMarkets (MIM)</div>
</div>
<script>
const tg=window.Telegram&&window.Telegram.WebApp;
if(tg){tg.expand();tg.ready();}
const CATS={
  stocks:     {label:"주식",    syms:["AAPL","AMZN","GOOG","MSFT","NFLX","TSLA","AMD","GOOGL","NVDA","META"]},
  indices:    {label:"지수",    syms:["EURO 50","US 30","HK 50","JP 225","UK 100","US 100","US 500"]},
  crypto:     {label:"암호화폐",syms:["BTC/USD","ETH/USD","XRP/USD","DOGE/USD","SOL/USD"]},
  forex:      {label:"외환",    syms:["AUD/CAD","AUD/CHF","AUD/JPY","AUD/NZD","AUD/USD","CAD/JPY","CHF/JPY","EUR/AUD","EUR/CHF","EUR/GBP","EUR/JPY","EUR/USD","GBP/AUD","GBP/JPY","GBP/USD","GBP/CAD","GBP/NZD","NZD/JPY","NZD/USD","USD/CAD","USD/CHF","USD/HKD","USD/JPY","USD/SGD","USD/CNH","USD/THB"]},
  commodities:{label:"원자재",  syms:["Silver","Gold","WTI Crude","Brent Crude","Natural Gas"]}
};
let curCat="indices",curSym="US 100";

function fmt(sym,v){
  if(v==null||isNaN(v))return'--';
  let d=2;
  if(v<0.01)d=6;else if(v<1)d=5;else if(v<10)d=4;else if(v>1000)d=2;
  if(sym.includes('JPY')||sym==='Silver')d=3;
  return Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
}

async function buildChartImg(ohlc, sym) {
  const imgEl = document.getElementById('chart-img');
  const loadEl = document.getElementById('chart-loading');
  imgEl.style.display = 'none';
  loadEl.style.display = 'block';

  // Convert OHLC to QuickChart candlestick format (x = ms timestamp)
  const data = ohlc.map(c => ({
    x: new Date(c.time).getTime(),
    o: c.open, h: c.high, l: c.low, c: c.close
  }));

  const chartCfg = {
    type: 'candlestick',
    data: {
      datasets: [{
        label: sym,
        data: data,
        color: {up:'rgba(0,212,170,1)', down:'rgba(255,71,87,1)', unchanged:'rgba(136,136,136,1)'},
        borderColor: {up:'rgba(0,212,170,1)', down:'rgba(255,71,87,1)', unchanged:'rgba(136,136,136,1)'}
      }]
    },
    options: {
      legend: {display: false},
      scales: {
        x: {type:'time', time:{unit:'day'}, ticks:{color:'#888',maxTicksLimit:6}, grid:{color:'rgba(255,255,255,0.04)'}},
        y: {ticks:{color:'#888'}, grid:{color:'rgba(255,255,255,0.04)'}}
      },
      plugins: {
        title: {display:true, text:'MIM — '+sym+' 30D Candlestick', color:'#666', font:{size:11}}
      }
    }
  };

  try {
    const resp = await fetch('https://quickchart.io/chart/create', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({width:500, height:260, backgroundColor:'#1a1d26', chart: chartCfg})
    });
    const json = await resp.json();
    if (json.url) {
      imgEl.onload = () => { loadEl.style.display='none'; imgEl.style.display='block'; };
      imgEl.onerror = () => { loadEl.textContent='차트를 불러올 수 없습니다.'; };
      imgEl.src = json.url;
    } else {
      loadEl.textContent = '차트 생성 실패';
    }
  } catch(e) {
    loadEl.textContent = '차트 오류: '+e.message;
  }
}

async function loadQuote(cat,sym){
  document.getElementById('loading').style.display='block';
  document.getElementById('error-msg').style.display='none';
  document.getElementById('price-card').style.display='none';
  document.getElementById('chart-card').style.display='none';
  try{
    const res=await fetch('/api/quote?cat='+encodeURIComponent(cat)+'&sym='+encodeURIComponent(sym));
    const d=await res.json();
    if(d.error)throw new Error(d.error);
    document.getElementById('d-sym').textContent=sym;
    document.getElementById('d-price').textContent=fmt(sym,d.price);
    const pct=Number(d.change_pct||0);
    const chgEl=document.getElementById('d-chg');
    chgEl.textContent=(pct>=0?'+':'')+pct.toFixed(2)+'% '+(pct>=0?'▲':'▼');
    chgEl.className='chg '+(pct>=0?'up':'dn');
    document.getElementById('d-high').textContent=fmt(sym,d.high);
    document.getElementById('d-low').textContent=fmt(sym,d.low);
    document.getElementById('price-card').style.display='block';
    if(d.ohlc&&d.ohlc.length>1){
      document.getElementById('chart-card').style.display='block';
      buildChartImg(d.ohlc, sym);  // async, shows spinner while loading
    }
    if(tg&&tg.HapticFeedback)tg.HapticFeedback.impactOccurred('light');
  }catch(err){
    const e=document.getElementById('error-msg');
    e.textContent='⚠️ '+sym+' 데이터 오류: '+err.message;
    e.style.display='block';
  }finally{
    document.getElementById('loading').style.display='none';
  }
}
function renderTabs(){
  const el=document.getElementById('tabs');el.innerHTML='';
  Object.keys(CATS).forEach(key=>{
    const btn=document.createElement('button');
    btn.textContent=CATS[key].label;
    if(key===curCat)btn.className='active';
    btn.onclick=()=>{curCat=key;curSym=CATS[key].syms[0];renderTabs();renderSymbols();loadQuote(curCat,curSym);};
    el.appendChild(btn);
  });
}
function renderSymbols(){
  const el=document.getElementById('symbols');el.innerHTML='';
  CATS[curCat].syms.forEach(sym=>{
    const btn=document.createElement('button');
    btn.textContent=sym;
    if(sym===curSym)btn.className='active';
    btn.onclick=()=>{curSym=sym;renderSymbols();loadQuote(curCat,sym);};
    el.appendChild(btn);
  });
}
renderTabs();renderSymbols();loadQuote(curCat,curSym);
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
