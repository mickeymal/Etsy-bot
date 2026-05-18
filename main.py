"""
BTC 15-Min Polymarket Signal Bot
==================================
Scans 24/7. Only sends a signal when confidence is high enough.
Never spams — 20-minute cooldown between signals.
Responds to /start in Telegram.

Setup:
  1. cp .env.example .env  →  fill in TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  2. pip install -r requirements.txt
  3. python main.py
"""

import asyncio
import logging
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

_last_signal_at: float = 0.0
_SIGNAL_COOLDOWN = 20 * 60   # 20 minutes between signals


async def scan_and_signal(bot) -> None:
    """Fetch market data, score it, and send a signal only when it's good enough."""
    global _last_signal_at

    # Respect cooldown — don't spam
    elapsed = time.monotonic() - _last_signal_at
    if _last_signal_at and elapsed < _SIGNAL_COOLDOWN:
        remaining = int((_SIGNAL_COOLDOWN - elapsed) / 60)
        logger.debug(f"Cooldown active — {remaining}min until next possible signal.")
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

        long_c  = signal["long_confidence"]
        short_c = signal["short_confidence"]
        logger.info(f"Scan — LONG {long_c:.0f}% / SHORT {short_c:.0f}% (threshold {Config.SIGNAL_THRESHOLD}%)")

        # Only send if one direction is clearly dominant
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


async def _clear_webhook(token: str) -> None:
    """Delete any active webhook so polling works without 409 conflicts."""
    import aiohttp
    url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json={"drop_pending_updates": True}) as r:
            data = await r.json()
            if data.get("ok"):
                logger.info("Webhook cleared — polling mode active.")
            else:
                logger.warning(f"deleteWebhook response: {data}")


async def main() -> None:
    Config.validate()

    await _clear_webhook(Config.TELEGRAM_BOT_TOKEN)

    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_start))

    # Retry loop — handles 409 Conflict (duplicate instance) on startup.
    # If another instance is still shutting down, wait and retry.
    for attempt in range(1, 6):
        try:
            async with app:
                await app.start()
                await app.updater.start_polling(drop_pending_updates=True)

                scheduler = AsyncIOScheduler(timezone="UTC")
                scheduler.add_job(scan_and_signal, "interval", minutes=2, args=[app.bot])
                scheduler.start()

                logger.info(
                    f"Bot live — scanning every 2 min, signalling when confidence ≥ {Config.SIGNAL_THRESHOLD}%. "
                    "Send /start in Telegram."
                )

                await scan_and_signal(app.bot)

                try:
                    await asyncio.Event().wait()
                except (KeyboardInterrupt, SystemExit):
                    pass
                finally:
                    scheduler.shutdown()
                    await app.updater.stop()
                    await app.stop()
            break  # clean exit

        except Exception as exc:
            if "409" in str(exc) or "Conflict" in str(exc):
                wait = attempt * 5
                logger.warning(
                    f"Conflict: another instance is still running (attempt {attempt}/5). "
                    f"Waiting {wait}s before retry… "
                    "Make sure only ONE instance is deployed."
                )
                await asyncio.sleep(wait)
            else:
                raise


if __name__ == "__main__":
    asyncio.run(main())
