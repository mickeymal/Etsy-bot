import time
import aiohttp
import logging
from datetime import datetime, timezone
from config import Config

logger = logging.getLogger(__name__)

_SLUG_PREFIX = "btc-updown-15m"
_INTERVAL    = 900   # 15 minutes in seconds


class PolymarketFetcher:
    """Fetches the active BTC 15-min up/down market by constructing the slug
    from the current 15-minute window timestamp — no keyword search needed."""

    async def _get(self, path: str, params: dict = None) -> list | dict:
        url = f"{Config.POLYMARKET_GAMMA_URL}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params or {}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                return await r.json()

    async def get_active_15m_market(self) -> dict | None:
        """Return the currently open BTC 15-min market, or None if not found."""
        now_ts = int(time.time())

        # Try current window, then next, then one back — covers edge cases
        # where a new market just opened or the old one just closed
        for offset in [0, 1, -1]:
            window_ts = ((now_ts // _INTERVAL) + offset) * _INTERVAL
            slug      = f"{_SLUG_PREFIX}-{window_ts}"
            market    = await self._fetch_slug(slug, window_ts)
            if market:
                logger.info(f"Polymarket market: {slug} → {market['resolution_time']}")
                return market

        logger.warning("No BTC 15-min market found for current window.")
        return None

    # Backwards-compatible alias used by SignalCalculator
    async def get_btc_odds(self) -> dict:
        return await self.get_active_15m_market() or self._empty()

    # ------------------------------------------------------------------ helpers

    async def _fetch_slug(self, slug: str, window_ts: int) -> dict | None:
        try:
            raw = await self._get("/markets", {"slug": slug, "limit": 1})
            markets = raw if isinstance(raw, list) else raw.get("markets", [])
            if markets:
                return self._parse(markets[0], window_ts)
        except Exception as e:
            logger.debug(f"Slug {slug} not found: {e}")
        return None

    def _parse(self, m: dict, window_ts: int) -> dict | None:
        try:
            yes_prob = None
            outcome_prices = m.get("outcomePrices")
            if outcome_prices and isinstance(outcome_prices, list):
                yes_prob = float(outcome_prices[0])

            if yes_prob is None:
                for tok in (m.get("tokens") or []):
                    if isinstance(tok, dict) and tok.get("outcome", "").lower() == "yes":
                        yes_prob = float(tok.get("price", 0.5))
                        break

            if yes_prob is None:
                yes_prob = 0.5

            slug = m.get("slug", f"{_SLUG_PREFIX}-{window_ts}")
            url  = f"https://polymarket.com/event/{slug}"

            # Show the resolution time so user knows which window this is for
            dt = datetime.fromtimestamp(window_ts, tz=timezone.utc)
            resolution_time = dt.strftime("%-I:%M %p UTC")   # e.g. "8:45 PM UTC"

            # Start time = 15 minutes before resolution
            start_ts = window_ts - _INTERVAL
            start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
            start_time = start_dt.strftime("%-I:%M %p UTC")

            return {
                "condition_id":    m.get("conditionId") or m.get("id") or slug,
                "yes_prob":        round(yes_prob, 4),
                "title":           m.get("question") or m.get("title", "BTC Up/Down 15-Min"),
                "volume":          float(m.get("volume", 0) or 0),
                "url":             url,
                "resolution_ts":   window_ts,
                "resolution_time": resolution_time,
                "start_time":      start_time,
                "window_label":    f"{start_time} → {resolution_time}",
            }
        except Exception as e:
            logger.warning(f"Failed to parse market: {e}")
            return None

    def _empty(self) -> dict:
        return {
            "yes_prob": 0.5, "title": "", "url": "https://polymarket.com",
            "condition_id": "", "volume": 0, "resolution_time": "",
            "start_time": "", "window_label": "",
        }
