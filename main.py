"""
BTC 15-Min Polymarket Signal Bot
==================================
Watches Polymarket for a new BTC 15-minute up/down market.
The moment a new one opens, analyses the data and sends you a signal.
You place the trade manually.

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

# Track the last market we signalled so we never send twice for the same market
_last_signalled_id: str = ""


async def check_for_new_market(bot) -> None:
    """Poll Polymarket for a new BTC 15-min market. Fire signal only when a new one appears."""
    global _last_signalled_id

    try:
        poly_market = await PolymarketFetcher().get_active_15m_market()
    except Exception as e:
        logger.warning(f"Polymarket poll failed: {e}")
        return

    if not poly_market:
        logger.debug("No active BTC 15-min market found yet.")
        return

    market_id = poly_market["condition_id"]

    if market_id == _last_signalled_id:
        logger.debug(f"Market {market_id[:12]}… already signalled. Waiting for next one.")
        return

    # New market found — generate and send signal
    _last_signalled_id = market_id
    logger.info(f"New BTC 15-min market: {poly_market['title'][:60]}")

    try:
        binance = BinanceDataFetcher()
        market_data, funding_rate = await asyncio.gather(
            binance.get_market_data(),
            binance.get_funding_rate(),
        )
        fear_greed = await FearGreedFetcher().get_index()

        signal  = SignalCalculator().calculate(market_data, funding_rate, fear_greed, poly_market)
        message = SignalFormatter().format(signal, market_data, fear_greed, poly_market)

        logger.info(
            f"Signal → LONG {signal['long_confidence']:.0f}% / SHORT {signal['short_confidence']:.0f}%"
        )
        await send_signal(bot, message)

    except Exception as exc:
        logger.error(f"Signal generation failed: {exc}", exc_info=True)
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
        # Check every 60 seconds — markets open every 15 min, this catches them fast
        scheduler.add_job(
            check_for_new_market,
            "interval",
            seconds=60,
            args=[app.bot],
        )
        scheduler.start()
        logger.info("Bot started — watching Polymarket for new BTC 15-min markets. Send /start in Telegram.")

        await check_for_new_market(app.bot)  # check immediately on boot

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            scheduler.shutdown()
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
