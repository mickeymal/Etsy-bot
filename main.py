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

# Active position state: None | "LONG" | "SHORT"
_active_position: str | None = None
_position_entry_price: float = 0.0

# Exit fires when the opposite confidence exceeds this threshold
_EXIT_THRESHOLD = 55


async def scan_and_signal() -> None:
    global _active_position, _position_entry_price

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
        direction = signal["direction"]
        formatter = SignalFormatter()

        logger.info(
            f"Scan [{poly_market.get('window_label','?')}] — "
            f"LONG {long_c:.0f}% / SHORT {short_c:.0f}% | "
            f"position={_active_position or 'none'}"
        )

        # ── Check for exit signal when a position is open ─────────────────────
        if _active_position == "LONG" and short_c >= _EXIT_THRESHOLD:
            msg = formatter.format_exit(
                signal, market_data, fear_greed, poly_market,
                open_position="LONG",
                entry_price=_position_entry_price,
            )
            delivered = await send_signal(msg)
            if delivered:
                logger.info(f"EXIT LONG signal sent (SHORT {short_c:.0f}% >= {_EXIT_THRESHOLD}%)")
                _active_position = None
            return

        if _active_position == "SHORT" and long_c >= _EXIT_THRESHOLD:
            msg = formatter.format_exit(
                signal, market_data, fear_greed, poly_market,
                open_position="SHORT",
                entry_price=_position_entry_price,
            )
            delivered = await send_signal(msg)
            if delivered:
                logger.info(f"EXIT SHORT signal sent (LONG {long_c:.0f}% >= {_EXIT_THRESHOLD}%)")
                _active_position = None
            return

        # ── New entry signal ───────────────────────────────────────────────────
        if max(long_c, short_c) < Config.SIGNAL_THRESHOLD:
            logger.info(
                f"Below threshold ({Config.SIGNAL_THRESHOLD}%) — "
                f"{'SIGNAL: ' + direction if max(long_c, short_c) >= Config.SIGNAL_THRESHOLD else 'no signal'}"
            )
            return

        # Don't spam same direction while already in that position
        if _active_position == direction:
            logger.info(f"Already in {direction} — skipping duplicate entry signal")
            return

        message = formatter.format(signal, market_data, fear_greed, poly_market)
        delivered = await send_signal(message)
        if delivered:
            _active_position = direction
            _position_entry_price = signal["entry_price"]
            logger.info(f"Signal sent — {direction} {signal['confidence']:.0f}% @ ${_position_entry_price:,.2f}")
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
