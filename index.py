"""
Minimal WSGI entrypoint for Vercel Python preset.
The actual bot logic lives in api/telegram-webhook.py
"""

def app(environ, start_response):
    path = environ.get("PATH_INFO", "/")

    if path == "/" or path == "":
        body = b"<h1>MyInvestmentMarkets Bot API</h1><p>Webhook active at /api/telegram-webhook</p>"
        status = "200 OK"
    else:
        body = b"Not Found"
        status = "404 Not Found"

    headers = [
        ("Content-Type", "text/html"),
        ("Content-Length", str(len(body)))
    ]
    start_response(status, headers)
    return [body]
