"""
BTC 15-Minute Polymarket Signal Bot
====================================
Runs every 15 minutes (on :00, :15, :30, :45) and sends a BTC directional
signal to your Telegram chat.  You read the signal and place trades manually
on Polymarket.

Setup:
  1. cp .env.example .env
  2. Fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
  3. pip install -r requirements.txt
  4. python main.py
"""

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import Config
from data.binance import BinanceDataFetcher
from data.fear_greed import FearGreedFetcher
from data.polymarket import PolymarketFetcher
from signals.calculator import SignalCalculator
from signals.formatter import SignalFormatter
from delivery.telegram import TelegramDelivery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_signal_cycle() -> None:
    logger.info("Running signal cycle...")
    delivery = TelegramDelivery()

    try:
        binance = BinanceDataFetcher()
        market_data, funding_rate = await asyncio.gather(
            binance.get_market_data(),
            binance.get_funding_rate(),
        )

        fear_greed = await FearGreedFetcher().get_index()
        poly_odds = await PolymarketFetcher().get_btc_odds()

        signal = SignalCalculator().calculate(market_data, funding_rate, fear_greed, poly_odds)
        message = SignalFormatter().format(signal, market_data, fear_greed, poly_odds)

        logger.info(
            f"Signal: {signal['direction']} | Confidence: {signal['confidence']:.1f}% | Score: {signal['score']}"
        )

        # Only send if confidence exceeds threshold (default 60 %)
        if signal["confidence"] >= Config.SIGNAL_THRESHOLD or signal["direction"] == "NEUTRAL":
            await delivery.send(message)
        else:
            logger.info(f"Signal below threshold ({Config.SIGNAL_THRESHOLD}%), skipping send.")

    except Exception as exc:
        logger.error(f"Signal cycle failed: {exc}", exc_info=True)
        try:
            await delivery.send_error(str(exc))
        except Exception:
            pass


async def main() -> None:
    Config.validate()

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(run_signal_cycle, "cron", minute="0,15,30,45", misfire_grace_time=60)
    scheduler.start()

    logger.info("BTC Signal Bot started — signals fire at :00, :15, :30, :45 UTC.")
    await run_signal_cycle()  # Fire immediately on startup

    try:
        while True:
            await asyncio.sleep(30)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down.")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
