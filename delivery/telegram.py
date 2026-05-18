import aiohttp
import logging
from config import Config

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org"


class TelegramDelivery:
    """Sends a Markdown message to a Telegram chat via the Bot API.
    No third-party library needed — plain HTTPS calls.
    """

    async def send(self, message: str) -> bool:
        url = f"{_API}/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": Config.TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
                if not data.get("ok"):
                    logger.error(f"Telegram send failed: {data}")
                    return False
                logger.info("Signal sent to Telegram.")
                return True

    async def send_error(self, error: str) -> None:
        """Send a plain-text error notification (no Markdown to avoid parse errors)."""
        url = f"{_API}/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": Config.TELEGRAM_CHAT_ID,
            "text": f"[BTC Signal Bot Error]\n{error}",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                await r.json()
