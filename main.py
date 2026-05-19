"""
BTC 15-Min Polymarket Signal Bot
==================================
Scans 24/7 using APScheduler. Sends a Telegram message via raw HTTP
when signal confidence is high enough. No polling, no webhooks, no 409.

Setup:
  1. cp .env.example .env  ->  fill in TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  2. pip install -r requirements.txt
  3. python main.py
"""

import asyncio
import logging
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import Config
from data.binance import BinanceDataFetcher
from data.fear_greed import FearGreedFetcher
from data.polymarket import PolymarketFetcher
from signals.calculator import SignalCalculator
from signals.formatter import SignalFormatter
from delivery.telegram import send_signal, send_error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_last_signal_at: float = 0.0
_SIGNAL_COOLDOWN = 20 * 60   # 20 minutes between signals


async def scan_and_signal() -> None:
    global _last_signal_at

    elapsed = time.monotonic() - _last_signal_at
    if _last_signal_at and elapsed < _SIGNAL_COOLDOWN:
        logger.info(f"Cooldown — {int((_SIGNAL_COOLDOWN - elapsed) / 60)}min remaining. Skipping scan.")
        return

    logger.info("Scanning market data...")

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

        message = SignalFormatter().format(signal, market_data, fear_greed, poly_market)
        delivered = await send_signal(message)
        if delivered:
            _last_signal_at = time.monotonic()
            logger.info(f"Signal sent — {signal['direction']} {signal['confidence']:.0f}%")
        else:
            logger.error("Signal NOT delivered — check TELEGRAM_CHAT_ID in Railway variables.")

    except Exception as exc:
        logger.error(f"Scan failed: {exc}", exc_info=True)
        await send_error(str(exc))


async def main() -> None:
    Config.validate()

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(scan_and_signal, "interval", minutes=2)
    scheduler.start()

    logger.info(
        f"Bot started — scanning every 2 min, "
        f"signalling when confidence >= {Config.SIGNAL_THRESHOLD}%. "
        f"No polling. No 409."
    )

    await scan_and_signal()   # immediate scan on startup

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
