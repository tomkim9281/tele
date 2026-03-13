"""
Telegram Webhook Handler — MyInvestmentMarkets (MIM_AI_Agent_bot)
Handles:
  - /start → Welcome photo + text + 2 inline buttons
  - Callback: join_forum → redirect to official group
  - Callback: consult_ai → enter AI chat mode
  - Fallback: any non-command text/photo → delete + warning + re-show buttons
Deployed as Vercel Serverless Function
"""

import json
import os
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}"

# MIM Official Telegram community folder / group URL
FORUM_URL = "https://t.me/addlist/XJLBb0XjbX5mMGU1"

# Welcome photo — MIM Global logo (file_id after first send, or URL)
# We use a public URL for the logo image (set WELCOME_IMAGE_URL env var or use default)
WELCOME_IMAGE_URL = os.environ.get(
    "WELCOME_IMAGE_URL",
    "https://tele-five-tau.vercel.app/mim-logo.png"
)

# ── Welcome content ──────────────────────────────────────────────────────────
WELCOME_TEXT = (
    "Greetings from My Investment Markets, your premier global CFD exchange. 🌐\n\n"
    "Experience the ultimate trading ecosystem directly within Telegram. "
    "Through this hub, you have instant access to:\n\n"
    "📢 Official Announcements\n"
    "📊 Live Market Quotes &amp; Charts\n"
    "🗞️ Real-Time Financial News\n"
    "📝 Institutional Daily Briefings\n"
    "🎓 Premium Trading Education\n"
    "📅 Global Economic Calendar\n\n"
    "Furthermore, our Real-Time AI Agent is at your service 24/7. "
    "You can consult with the AI at any time for tailored market insights and instant support.\n\n"
    "Please select an option below to begin your journey. 👇"
)

MAIN_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "🌐 Join Official Forum",   "url": FORUM_URL}],
        [{"text": "🤖 Consult with AI Agent", "callback_data": "consult_ai"}],
    ]
}

FALLBACK_TEXT = (
    "⚠️ <b>Automated System Notice</b>\n\n"
    "This is an automated terminal. Text inputs are not supported.\n"
    "Please use the interactive buttons below to navigate and access our services. 👇"
)

AI_INTRO_TEXT = (
    "🤖 <b>MIM AI Agent</b>\n\n"
    "Hello! I'm your personal MIM AI Agent. 👋\n\n"
    "How can I assist you today? Feel free to ask me anything about:\n"
    "• Market analysis &amp; insights\n"
    "• Trading strategies &amp; tips\n"
    "• Account &amp; platform support\n"
    "• Economic events &amp; news\n\n"
    "Type your question below and I'll respond right away. 💬"
)

# Track users in AI chat mode (in-memory; resets on cold start)
# For production persistence, use a DB. This is sufficient for serverless warm instances.
ai_mode_users: set = set()

# ── Telegram API helpers ─────────────────────────────────────────────────────
def tg_request(method, payload):
    url  = f"{BASE_URL}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"TG error [{method}]: {e}")
        return {}

def send_photo(chat_id, photo_url, caption, reply_markup=None):
    payload = {
        "chat_id":    chat_id,
        "photo":      photo_url,
        "caption":    caption,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_request("sendPhoto", payload)

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {
        "chat_id":                  chat_id,
        "text":                     text,
        "parse_mode":               parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_request("sendMessage", payload)

def delete_message(chat_id, message_id):
    tg_request("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

def answer_callback(callback_id, text=None, show_alert=False):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"]       = text
        payload["show_alert"] = show_alert
    tg_request("answerCallbackQuery", payload)

# ── /start handler ───────────────────────────────────────────────────────────
def handle_start(chat_id, user_id):
    # Remove from AI mode if previously in it
    ai_mode_users.discard(user_id)
    # Send photo + caption + buttons
    result = send_photo(chat_id, WELCOME_IMAGE_URL, WELCOME_TEXT, MAIN_KEYBOARD)
    if not result.get("ok"):
        # Fallback: send text-only if photo fails
        send_message(chat_id, WELCOME_TEXT, MAIN_KEYBOARD)

# ── Callback handler ─────────────────────────────────────────────────────────
def handle_callback(callback):
    cid     = callback["id"]
    data    = callback["data"]
    msg     = callback["message"]
    chat_id = msg["chat"]["id"]
    user_id = callback["from"]["id"]

    answer_callback(cid)

    if data == "consult_ai":
        ai_mode_users.add(user_id)
        send_message(chat_id, AI_INTRO_TEXT)

    elif data == "back_main":
        ai_mode_users.discard(user_id)
        send_photo(chat_id, WELCOME_IMAGE_URL, WELCOME_TEXT, MAIN_KEYBOARD)

# ── Message handler ──────────────────────────────────────────────────────────
def handle_message(message):
    chat_id    = message["chat"]["id"]
    user_id    = message["from"]["id"]
    message_id = message["message_id"]
    text       = message.get("text", "")

    # /start command
    if text.startswith("/start"):
        handle_start(chat_id, user_id)
        return

    # If user is in AI chat mode → pass through (future: call Gemini API here)
    if user_id in ai_mode_users:
        # Placeholder echo — replace with Gemini API call as needed
        send_message(
            chat_id,
            f"🤖 <b>MIM AI Agent</b>\n\nYou said: <i>{text}</i>\n\n"
            "(AI response integration coming soon — stay tuned!)"
        )
        return

    # Fallback: delete the user's message and show warning + buttons
    delete_message(chat_id, message_id)
    send_message(chat_id, FALLBACK_TEXT, MAIN_KEYBOARD)

# ── Vercel handler ───────────────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            update = json.loads(body)
            print(f"Update: {json.dumps(update)[:200]}")

            if "message" in update:
                handle_message(update["message"])

            elif "callback_query" in update:
                handle_callback(update["callback_query"])

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        except Exception as e:
            print(f"Webhook error: {e}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"MIM AI Agent Bot Webhook Active")
