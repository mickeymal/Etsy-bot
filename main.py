"""
BTC 15-Minute Polymarket Signal Bot
=====================================
Sends BTC directional signals (LONG / SHORT confidence) to Telegram
every 15 minutes. Responds to /start with a welcome message.

Setup:
  1. cp .env.example .env  →  fill in TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  2. pip install -r requirements.txt
  3. python main.py
"""

import asyncio
import logging
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


async def run_signal_cycle(bot) -> None:
    logger.info("Running signal cycle...")
    try:
        binance = BinanceDataFetcher()
        market_data, funding_rate = await asyncio.gather(
            binance.get_market_data(),
            binance.get_funding_rate(),
        )
        fear_greed = await FearGreedFetcher().get_index()
        poly_odds  = await PolymarketFetcher().get_btc_odds()

        signal  = SignalCalculator().calculate(market_data, funding_rate, fear_greed, poly_odds)
        message = SignalFormatter().format(signal, market_data, fear_greed, poly_odds)

        logger.info(
            f"Score: {signal['score']}  "
            f"LONG: {signal['long_confidence']:.0f}%  "
            f"SHORT: {signal['short_confidence']:.0f}%"
        )
        await send_signal(bot, message)

    except Exception as exc:
        logger.error(f"Signal cycle failed: {exc}", exc_info=True)
        try:
            await send_error(bot, str(exc))
        except Exception:
            pass


async def main() -> None:
    Config.validate()

    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_start))

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            run_signal_cycle,
            "cron",
            minute="0,15,30,45",
            misfire_grace_time=60,
            args=[app.bot],
        )
        scheduler.start()
        logger.info("Bot started — signals fire at :00, :15, :30, :45 UTC. Send /start in Telegram.")

        await run_signal_cycle(app.bot)  # fire immediately on startup

        try:
            await asyncio.Event().wait()   # run forever
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            scheduler.shutdown()
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
