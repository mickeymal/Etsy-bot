import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    # Minimum confidence % before a signal is sent.
    # 65 = only strong signals. Lower = more frequent but noisier.
    SIGNAL_THRESHOLD = float(os.getenv("SIGNAL_THRESHOLD", "65"))

    FEAR_GREED_URL = "https://api.alternative.me/fng/"
    POLYMARKET_GAMMA_URL = "https://gamma-api.polymarket.com"

    SYMBOL = "BTCUSDT"
    INTERVAL = "15m"
    KLINE_LIMIT = 60          # candles to load for RSI/MACD
    INTERVAL_MINUTES = 15

    @classmethod
    def validate(cls):
        missing = [k for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
                   if not getattr(cls, k)]
        if missing:
            raise EnvironmentError(
                f"Missing required env vars: {', '.join(missing)}\n"
                "Copy .env.example to .env and fill in your values."
            )
