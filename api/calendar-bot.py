"""
Economic Calendar Bot — MyInvestmentMarkets
- Weekly schedule: GitHub Actions Cron every Monday UTC 00:00 = KST 09:00
- Event alerts: GitHub Actions Cron every 5 minutes (high impact only, 1hr notice)
All times displayed in UTC.
"""

import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = -1003754818644
TOPIC_CALENDAR = 6
UTC = timezone.utc
SENT_ALERTS_FILE = "/tmp/sent_alerts.json"

# Country code → flag emoji
FLAG = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "CNY": "🇨🇳", "CAD": "🇨🇦", "AUD": "🇦🇺", "NZD": "🇳🇿",
    "CHF": "🇨🇭", "KRW": "🇰🇷",
    "United States": "🇺🇸", "Euro Zone": "🇪🇺", "United Kingdom": "🇬🇧",
    "Japan": "🇯🇵", "China": "🇨🇳", "Canada": "🇨🇦", "Australia": "🇦🇺",
    "New Zealand": "🇳🇿", "Switzerland": "🇨🇭", "South Korea": "🇰🇷",
}

def flag(country):
    return FLAG.get(country, "🌐")

def impact_dot(impact):
    return "🔴" if impact == "High" else "🟡" if impact == "Medium" else "⚪"

def tg_send(text):
    payload = {
        "chat_id": CHAT_ID, "message_thread_id": TOPIC_CALENDAR,
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

def parse_ff_xml(week="thisweek"):
    url = f"https://nfs.faireconomy.media/ff_calendar_{week}.xml"
    try:
        root = ET.fromstring(fetch_url(url))
        events = []
        for ev in root.findall("event"):
            date_str = ev.findtext("date", "")
            time_str = ev.findtext("time", "")

            # ForexFactory times are US Eastern — convert to UTC
            dt_utc = None
            try:
                if time_str and time_str not in ("All Day", ""):
                    dt_et = datetime.strptime(f"{date_str} {time_str}", "%b %d, %Y %I:%M%p")
                    # ET ≈ UTC-4 during DST (Mar-Nov), UTC-5 otherwise
                    # Mar is DST → UTC-4
                    dt_utc = dt_et + timedelta(hours=4)
                    dt_utc = dt_utc.replace(tzinfo=UTC)
            except Exception:
                pass

            events.append({
                "title":    ev.findtext("title", ""),
                "country":  ev.findtext("country", ""),
                "date":     date_str,
                "time_str": time_str,
                "time_utc": dt_utc.strftime("%H:%M") if dt_utc else time_str,
                "dt_utc":   dt_utc,
                "impact":   ev.findtext("impact", ""),
                "forecast": ev.findtext("forecast", ""),
                "previous": ev.findtext("previous", ""),
                "actual":   ev.findtext("actual", ""),
                "currency": ev.findtext("currency", ev.findtext("country", "")),
            })
        return events
    except Exception as e:
        print(f"FF XML error: {e}")
        return []

def load_sent_alerts():
    try:
        with open(SENT_ALERTS_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_sent_alerts(ids):
    try:
        with open(SENT_ALERTS_FILE, "w") as f:
            json.dump(list(ids)[-200:], f)
    except Exception:
        pass

# ── WEEKLY SCHEDULE ───────────────────────────────────────────────────────────
def send_weekly_schedule():
    now_utc = datetime.now(UTC)
    events_this = parse_ff_xml("thisweek")
    events_next = parse_ff_xml("nextweek")
    all_events = [e for e in events_this + events_next
                  if e["impact"] in ("High", "Medium")]

    if not all_events:
        print("No events to report.")
        return

    week_start = now_utc.strftime("%b %d")
    week_end   = (now_utc + timedelta(days=6)).strftime("%b %d, %Y")

    msg = (
        f"📅 <b>THIS WEEK'S KEY EVENTS</b>\n"
        f"⏱ Timezone: UTC  |  Week of {week_start} – {week_end}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    # Group by date
    from collections import defaultdict
    by_day = defaultdict(list)
    for e in all_events:
        by_day[e["date"]].append(e)

    # Sort dates
    def parse_date(d):
        try:
            return datetime.strptime(d, "%b %d, %Y")
        except Exception:
            return datetime.min

    for date_key in sorted(by_day.keys(), key=parse_date):
        day_events = sorted(by_day[date_key],
                            key=lambda x: x["time_utc"] if x["time_utc"] else "99:99")
        try:
            day_label = datetime.strptime(date_key, "%b %d, %Y").strftime("%A, %b %d")
        except Exception:
            day_label = date_key

        msg += f"\n🗓 <b>{day_label}</b>\n"
        for e in day_events:
            cur = e.get("currency", e["country"])
            dot = impact_dot(e["impact"])
            f_emoji = flag(e["country"])
            msg += f"{f_emoji} {e['time_utc']} [{cur}] {dot} {e['title']}\n"
            parts = []
            if e["forecast"]: parts.append(f"📊 Fcst: {e['forecast']}")
            if e["previous"]: parts.append(f"Prev: {e['previous']}")
            if e["actual"]:   parts.append(f"✅ Actual: {e['actual']}")
            if parts:
                msg += f"↳ {' | '.join(parts)}\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━\n⚡️ MIM Global Financial Services"

    tg_send(msg)
    print("✅ Weekly schedule sent.")

# ── EVENT ALERTS (every 5 min) ────────────────────────────────────────────────
def check_event_alerts():
    now_utc = datetime.now(UTC)
    sent_alerts = load_sent_alerts()

    events_this = parse_ff_xml("thisweek")
    events_next = parse_ff_xml("nextweek")
    all_events = events_this + events_next

    high_events = [e for e in all_events if e["impact"] == "High" and e["dt_utc"]]
    new_count = 0

    for e in high_events:
        alert_id = f"{e['date']}_{e['title']}"
        if alert_id in sent_alerts:
            continue

        minutes_until = (e["dt_utc"] - now_utc).total_seconds() / 60

        if 55 <= minutes_until <= 65:
            dot = impact_dot(e["impact"])
            f_emoji = flag(e["country"])
            cur = e.get("currency", e["country"])
            msg = (
                f"⚠️ <b>EVENT ALERT — 1 Hour Notice</b>\n\n"
                f"📌 <b>{e['title']}</b>\n"
                f"{f_emoji} {e['country']}  [{cur}]  {dot} HIGH IMPACT\n"
                f"⏰ Release: <b>{e['time_utc']} UTC</b>\n"
            )
            if e["forecast"]: msg += f"📊 Forecast: {e['forecast']}\n"
            if e["previous"]: msg += f"Prev: {e['previous']}\n"
            msg += "\n⚡ Expect elevated volatility around release.\nTrade with caution.\n\n⚡️ MIM Global Financial Services"

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
