import os
import time
import logging
import threading
import requests
from flask import Flask

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("az-line-bot")

API_KEY = os.environ["ODDS_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

MIN_ODDS = float(os.environ.get("MIN_ODDS", "1.46"))
BOOKMAKER = os.environ.get("BOOKMAKER", "onexbet")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "180"))
TARGET_POINT = float(os.environ.get("TARGET_POINT", "0.5"))

ODDS_URL = (
    "https://api.the-odds-api.com/v4/sports/soccer/odds/"
    f"?apiKey={API_KEY}&regions=eu&markets=totals&oddsFormat=decimal"
)

notified_matches = set()

KEEPALIVE_PORT = int(os.environ.get("PORT", "8080"))

app = Flask(__name__)


@app.route("/")
def home():
    return "AZ Line Alive"


def run_keepalive() -> None:
    app.run(host="0.0.0.0", port=KEEPALIVE_PORT, debug=False, use_reloader=False)


def keep_alive() -> None:
    t = threading.Thread(target=run_keepalive, daemon=True)
    t.start()


def send_msg(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=15)
        if r.status_code != 200:
            log.error("Telegram error %s: %s", r.status_code, r.text)
    except Exception as e:
        log.error("Telegram send failed: %s", e)


def check_live_odds() -> None:
    try:
        response = requests.get(ODDS_URL, timeout=20)
        if response.status_code != 200:
            log.error("Odds API error %s: %s", response.status_code, response.text[:200])
            return

        data = response.json()
        log.info("Fetched %d games", len(data))

        for game in data:
            home = game.get("home_team", "")
            away = game.get("away_team", "")
            match_id = f"{home} - {away}"

            for bookie in game.get("bookmakers", []):
                if bookie.get("key") != BOOKMAKER:
                    continue
                for market in bookie.get("markets", []):
                    if market.get("key") != "totals":
                        continue
                    for outcome in market.get("outcomes", []):
                        if (
                            outcome.get("name") == "Over"
                            and outcome.get("point") == TARGET_POINT
                        ):
                            price = outcome.get("price")
                            if (
                                price is not None
                                and price >= MIN_ODDS
                                and match_id not in notified_matches
                            ):
                                msg = (
                                    f"🔔 СИГНАЛ: {match_id}\n"
                                    f"Кэф на ТБ {TARGET_POINT}: {price}!\n"
                                    "Пора страховать."
                                )
                                send_msg(msg)
                                notified_matches.add(match_id)
                                log.info("Signal sent: %s @ %s", match_id, price)
    except Exception as e:
        log.error("check_live_odds error: %s", e)


def main() -> None:
    log.info(
        "AZ Line Bot started. bookmaker=%s min_odds=%s point=%s interval=%ss",
        BOOKMAKER, MIN_ODDS, TARGET_POINT, POLL_INTERVAL,
    )
    keep_alive()
    log.info("Keep-alive server listening on port %s", KEEPALIVE_PORT)
    send_msg("✅ Бот AZ Line запущен!")

    while True:
        log.info("Polling odds...")
        check_live_odds()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
