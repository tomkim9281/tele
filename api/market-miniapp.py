#!/usr/bin/env python3
"""
Market Quotes Mini App Message Sender
Sends a promo message with Launch Live Terminal button to the 마켓쿼츠 topic.
Button opens t.me/MIM_AI_Agent_bot/MIM (BotFather Mini App)
"""

import json
import os
import urllib.request

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = -1003733637841
TOPIC_ID  = 47  # 마켓쿼츠 topic

def send_market_miniapp():
    text = (
        "⚡️ <b>MIM Live Market Terminal</b>\n\n"
        "Access institutional-grade market data instantly.\n\n"
        "Tap the button below to launch your interactive terminal and track "
        "real-time quotes, intraday candlestick charts, and live trends "
        "directly within Telegram.\n\n"
        "🌐 <i>Equities · Indices · Crypto · Forex · Commodities</i>"
    )
    payload = {
        "chat_id": CHAT_ID,
        "message_thread_id": TOPIC_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [[
                {
                    "text": "📊 Launch Live Terminal",
                    "url": "https://t.me/MIM_AI_Agent_bot/MIM"
                }
            ]]
        }
    }
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        result = json.loads(r.read())

    if result.get("ok"):
        msg_id = result["result"]["message_id"]
        print(f"✅ Market Quotes mini app message sent! message_id={msg_id}")
    else:
        print(f"❌ Error: {result}")
    return result

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set!")
        exit(1)
    send_market_miniapp()
