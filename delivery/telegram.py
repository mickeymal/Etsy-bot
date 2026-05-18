import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

START_MESSAGE = (
    "🤖 *BTC Signal Bot is Active\\!*\n\n"
    "Every 15 minutes \\(at :00, :15, :30, :45 UTC\\) I'll send you:\n\n"
    "📈 *LONG confidence %* — how bullish the market looks\n"
    "📉 *SHORT confidence %* — how bearish the market looks\n"
    "🔗 *Direct Polymarket link* — tap to open the market\n\n"
    "Data I analyse:\n"
    "• RSI \\+ MACD \\(price momentum\\)\n"
    "• OKX funding rate \\(leverage positioning\\)\n"
    "• Crypto Fear & Greed Index\n"
    "• Order book imbalance\n"
    "• Polymarket odds\n\n"
    "You read the signal → you place the trade manually on Polymarket\\.\n\n"
    "⚠️ _Not financial advice\\. DYOR\\._"
)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(START_MESSAGE, parse_mode="MarkdownV2")


async def send_signal(bot, message: str) -> bool:
    from config import Config
    try:
        await bot.send_message(
            chat_id=Config.TELEGRAM_CHAT_ID,
            text=message,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        logger.info("Signal sent to Telegram.")
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


async def send_error(bot, error: str) -> None:
    from config import Config
    try:
        await bot.send_message(
            chat_id=Config.TELEGRAM_CHAT_ID,
            text=f"[BTC Signal Bot Error]\n{error}",
        )
    except Exception:
        pass
