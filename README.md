# MyInvestmentMarkets — Telegram Automation Bot

Automated Telegram bots for MyInvestmentMarkets CFD Exchange.

## Bots
- 📰 `api/news-bot.py` — Real-time high-impact news (every 15 min via GitHub Actions)
- 📊 `api/telegram-webhook.py` — Market Quotes inline keyboard (Vercel Webhook)
- 📉 `api/daily-briefing.py` — Daily market close briefing (weekdays KST 06:00)
- 📅 `api/calendar-bot.py` — Economic calendar + 1hr event alerts (every 5 min)
- 🎓 `api/education-bot.py` — Trading education with mplfinance charts (Mon/Wed/Fri KST 10:00)

## Deployment
- **Vercel**: Hosts the webhook for Market Quotes bot
- **GitHub Actions**: Runs all scheduled bots

## Environment Variables (set in Vercel Dashboard + GitHub Secrets)
- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`
- `CRYPTOPANIC_API_KEY`

## Topic IDs (Group Chat ID: -1003754818644)
- News: thread 3
- Market Quotes: thread 4
- Daily Briefing: thread 5
- Economic Calendar: thread 6
- Trading Education: thread 7
