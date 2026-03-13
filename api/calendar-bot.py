"""
Economic Calendar Bot — MyInvestmentMarkets
- Weekly schedule: GitHub Actions Cron every Monday KST 09:00
- Event alerts: GitHub Actions Cron every 5 minutes (high impact only, 1hr notice)
"""

import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = -1003754818644
TOPIC_CALENDAR = 6  # eco
KST = timezone(timedelta(hours=9))
SENT_ALERTS_FILE = "/tmp/sent_alerts.json"

TRADINGVIEW_CALENDAR_URL = "https://www.tradingview.com/economic-calendar/"

def tg_send(text, with_calendar_button=True):
    payload = {
        "chat_id": CHAT_ID,
        "message_thread_id": TOPIC_CALENDAR,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if with_calendar_button:
        payload["reply_markup"] = json.dumps({
            "inline_keyboard": [[
                {"text": "📅 Calendar", "url": TRADINGVIEW_CALENDAR_URL}
            ]]
        })
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()

def parse_ff_xml(week="thisweek"):
    url = f"https://nfs.faireconomy.media/ff_calendar_{week}.xml"
    try:
        raw = fetch_url(url)
        root = ET.fromstring(raw)
        events = []
        for ev in root.findall("event"):
            # Parse date and time from ForexFactory
            date_str = ev.findtext("date", "")
            time_str = ev.findtext("time", "")

            # Convert time to KST (ForexFactory is US Eastern)
            # ET is UTC-5 (or UTC-4 during DST) — we add 13/14 hours for KST
            dt_kst = None
            try:
                if time_str and time_str != "All Day":
                    dt_et = datetime.strptime(f"{date_str} {time_str}", "%b %d, %Y %I:%M%p")
                    # Assume ET = UTC-4 (approximate, DST)
                    dt_utc = dt_et + timedelta(hours=4)
                    dt_kst = dt_utc + timedelta(hours=9)
            except Exception:
                pass

            events.append({
                "title":    ev.findtext("title", ""),
                "country":  ev.findtext("country", ""),
                "date":     date_str,
                "time":     time_str,
                "time_kst": dt_kst.strftime("%a %H:%M KST") if dt_kst else time_str,
                "dt_kst":   dt_kst,
                "impact":   ev.findtext("impact", ""),
                "forecast": ev.findtext("forecast", ""),
                "previous": ev.findtext("previous", ""),
                "actual":   ev.findtext("actual", ""),
            })
        return events
    except Exception as e:
        print(f"FF XML error: {e}")
        return []

def star(impact):
    return "⭐⭐⭐" if impact == "High" else "⭐⭐" if impact == "Medium" else "⭐"

def load_sent_alerts():
    try:
        with open(SENT_ALERTS_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_sent_alerts(ids):
    try:
        id_list = list(ids)[-200:]
        with open(SENT_ALERTS_FILE, "w") as f:
            json.dump(id_list, f)
    except Exception:
        pass

# ── WEEKLY SCHEDULE ────────────────────────────────────────────────────────
def send_weekly_schedule():
    now_kst = datetime.now(KST)
    events_this = parse_ff_xml("thisweek")
    events_next = parse_ff_xml("nextweek")
    all_events = events_this + events_next

    # Filter High + Medium impact
    filtered = [e for e in all_events if e["impact"] in ("High", "Medium")]

    if not filtered:
        print("No events to report.")
        return

    # Week range label
    week_start = now_kst.strftime("%b %d")
    week_end   = (now_kst + timedelta(days=6)).strftime("%b %d, %Y")

    msg = f"📅 <b>THIS WEEK'S KEY EVENTS</b>\nWeek of {week_start} – {week_end}\n\n"

    high_events = [e for e in filtered if e["impact"] == "High"]
    med_events  = [e for e in filtered if e["impact"] == "Medium"]

    if high_events:
        msg += "<b>⭐⭐⭐ HIGH IMPACT</b>\n"
        for e in high_events[:8]:
            msg += f"{e['time_kst']} — {e['country']} — <b>{e['title']}</b>\n"
            if e["forecast"] or e["previous"]:
                parts = []
                if e["forecast"]:
                    parts.append(f"Fcst: {e['forecast']}")
                if e["previous"]:
                    parts.append(f"Prev: {e['previous']}")
                msg += f"  {' | '.join(parts)}\n"
        msg += "\n"

    if med_events:
        msg += "<b>⭐⭐ MEDIUM IMPACT</b>\n"
        for e in med_events[:8]:
            msg += f"{e['time_kst']} — {e['country']} — {e['title']}\n"

    msg += "\nMyInvestmentMarkets"

    tg_send(msg)
    print("✅ Weekly schedule sent.")

# ── EVENT ALERTS (every 5 min check) ─────────────────────────────────────
def check_event_alerts():
    now_kst = datetime.now(KST)
    sent_alerts = load_sent_alerts()

    events_this = parse_ff_xml("thisweek")
    events_next = parse_ff_xml("nextweek")
    all_events = events_this + events_next

    high_events = [e for e in all_events if e["impact"] == "High" and e["dt_kst"]]
    new_count = 0

    for e in high_events:
        alert_id = f"{e['date']}_{e['title']}"
        if alert_id in sent_alerts:
            continue

        dt_kst = e["dt_kst"]
        minutes_until = (dt_kst - now_kst).total_seconds() / 60

        if 55 <= minutes_until <= 65:
            release_time = dt_kst.strftime("%H:%M KST")
            msg = (
                f"⚠️ <b>EVENT ALERT — 1 Hour Notice</b>\n\n"
                f"📌 <b>{e['title']}</b>\n"
                f"🇺🇸 {e['country']}  |  ⭐⭐⭐ HIGH IMPACT\n"
                f"⏰ Release: <b>{release_time}</b>\n"
            )
            if e["forecast"]:
                msg += f"Forecast: {e['forecast']}\n"
            if e["previous"]:
                msg += f"Previous: {e['previous']}\n"
            msg += "\n⚡ Expect elevated volatility around the release.\nTrade with caution.\n\nMyInvestmentMarkets"

            try:
                tg_send(msg)
                sent_alerts.add(alert_id)
                new_count += 1
                print(f"✅ Alert sent: {e['title']}")
            except Exception as ex:
                print(f"Alert send error: {ex}")

    save_sent_alerts(sent_alerts)
    print(f"✅ Alert check done. {new_count} alert(s) sent.")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "alert"
    if mode == "weekly":
        send_weekly_schedule()
    else:
        check_event_alerts()
