import aiohttp
import logging
from config import Config

logger = logging.getLogger(__name__)
_API = "https://api.telegram.org"


async def send_signal(message: str) -> bool:
    url = f"{_API}/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": Config.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
            data = await r.json()
            if not data.get("ok"):
                logger.error(f"Telegram send failed: {data}")
                return False
            logger.info("Signal delivered to Telegram.")
            return True


async def send_error(error: str) -> None:
    url = f"{_API}/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": Config.TELEGRAM_CHAT_ID,
        "text": f"⚠️ Bot error:\n{error}",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                await r.json()
    except Exception:
        pass
