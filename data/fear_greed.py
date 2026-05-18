import aiohttp
import logging
from config import Config

logger = logging.getLogger(__name__)


class FearGreedFetcher:
    """Fetches the Crypto Fear & Greed Index from alternative.me — no key needed."""

    async def get_index(self) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(Config.FEAR_GREED_URL, timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                data = await r.json()

        entry = data["data"][0]
        value = int(entry["value"])

        if value <= 25:
            label = "Extreme Fear"
        elif value <= 45:
            label = "Fear"
        elif value <= 55:
            label = "Neutral"
        elif value <= 75:
            label = "Greed"
        else:
            label = "Extreme Greed"

        return {"value": value, "label": label}
