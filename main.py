"""
BTC 15-Min Polymarket Signal Bot
==================================
Scans 24/7. Only sends a signal when confidence is high enough.
20-min cooldown after each signal. Responds to /start in Telegram.

Deployment modes (auto-detected):
  - Railway: webhook mode via RAILWAY_PUBLIC_DOMAIN — no polling, no 409 ever
  - Local:   polling mode (run only one instance)

Setup:
  1. cp .env.example .env  →  fill in TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  2. pip install -r requirements.txt
  3. python main.py
"""

import asyncio
import logging
import os
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application, CommandHandler

from config import Config
from data.binance import BinanceDataFetcher
from data.fear_greed import FearGreedFetcher
from data.polymarket import PolymarketFetcher
from signals.calculator import SignalCalculator
from signals.formatter import SignalFormatter
from delivery.telegram import handle_start, send_signal, send_error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Railway sets RAILWAY_PUBLIC_DOMAIN automatically on every deployment.
# If it's present we use webhook mode; otherwise polling (local dev).
RAILWAY_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
PORT = int(os.getenv("PORT", "8080"))

_last_signal_at: float = 0.0
_SIGNAL_COOLDOWN = 20 * 60   # 20 minutes between signals


async def scan_and_signal(bot) -> None:
    """Fetch data, score it, send a Telegram signal only when strong enough."""
    global _last_signal_at

    elapsed = time.monotonic() - _last_signal_at
    if _last_signal_at and elapsed < _SIGNAL_COOLDOWN:
        logger.debug(f"Cooldown — {int((_SIGNAL_COOLDOWN - elapsed) / 60)}min remaining.")
        return

    try:
        binance = BinanceDataFetcher()
        market_data, funding_rate = await asyncio.gather(
            binance.get_market_data(),
            binance.get_funding_rate(),
        )
        fear_greed  = await FearGreedFetcher().get_index()
        poly_market = await PolymarketFetcher().get_active_15m_market() or {
            "yes_prob": 0.5, "title": "", "url": "https://polymarket.com",
            "condition_id": "", "volume": 0, "end_date": "",
        }

        signal = SignalCalculator().calculate(market_data, funding_rate, fear_greed, poly_market)
        long_c, short_c = signal["long_confidence"], signal["short_confidence"]
        logger.info(f"Scan — LONG {long_c:.0f}% / SHORT {short_c:.0f}% (threshold {Config.SIGNAL_THRESHOLD}%)")

        if max(long_c, short_c) < Config.SIGNAL_THRESHOLD:
            return

        _last_signal_at = time.monotonic()
        message = SignalFormatter().format(signal, market_data, fear_greed, poly_market)
        await send_signal(bot, message)
        logger.info(f"Signal sent — {signal['direction']} {signal['confidence']:.0f}%")

    except Exception as exc:
        logger.error(f"Scan failed: {exc}", exc_info=True)
        try:
            await send_error(bot, str(exc))
        except Exception:
            pass


async def post_init(application: Application) -> None:
    """Runs once after the bot is ready — starts the scheduler and fires a first scan."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(scan_and_signal, "interval", minutes=2, args=[application.bot])
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    mode = "webhook" if RAILWAY_DOMAIN else "polling"
    logger.info(f"Bot live [{mode}] — scanning every 2 min, threshold ≥ {Config.SIGNAL_THRESHOLD}%.")
    await scan_and_signal(application.bot)


async def post_shutdown(application: Application) -> None:
    """Runs on shutdown — stops the scheduler cleanly."""
    scheduler = application.bot_data.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown()


def main() -> None:
    Config.validate()

    app = (
        Application.builder()
        .token(Config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", handle_start))

    if RAILWAY_DOMAIN:
        # ── Webhook mode (Railway) ──────────────────────────────────────────
        # Telegram pushes updates to our HTTPS URL. No getUpdates polling at all.
        # This completely eliminates 409 Conflict errors during rolling restarts.
        webhook_url = f"https://{RAILWAY_DOMAIN}/webhook"
        logger.info(f"Starting in webhook mode → {webhook_url} (internal port {PORT})")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=webhook_url,
            drop_pending_updates=True,
        )
    else:
        # ── Polling mode (local) ────────────────────────────────────────────
        logger.info("Starting in polling mode (local — ensure only one instance runs).")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
