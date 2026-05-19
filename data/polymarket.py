import time
import aiohttp
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
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
            info = self._window_info(window_ts)
            info["url"] = f"https://polymarket.com/event/{slug}"

            return {
                "condition_id": m.get("conditionId") or m.get("id") or slug,
                "yes_prob":     round(yes_prob, 4),
                "title":        m.get("question") or m.get("title", "BTC Up/Down 15-Min"),
                "volume":       float(m.get("volume", 0) or 0),
                **info,
            }
        except Exception as e:
            logger.warning(f"Failed to parse market: {e}")
            return None

    def _window_info(self, window_ts: int) -> dict:
        """Build window time labels from a Unix timestamp — no API needed."""
        dt       = datetime.fromtimestamp(window_ts, tz=_ET)
        start_dt = datetime.fromtimestamp(window_ts - _INTERVAL, tz=_ET)
        res_time   = dt.strftime("%-I:%M %p ET")
        start_time = start_dt.strftime("%-I:%M %p ET")
        slug = f"{_SLUG_PREFIX}-{window_ts}"
        return {
            "resolution_ts":   window_ts,
            "resolution_time": res_time,
            "start_time":      start_time,
            "window_label":    f"{start_time} → {res_time}",
            "url":             f"https://polymarket.com/event/{slug}",
        }

    def _empty(self) -> dict:
        """Fallback when API is unavailable — still shows correct window from clock."""
        now_ts     = int(time.time())
        window_ts  = (now_ts // _INTERVAL) * _INTERVAL
        base = self._window_info(window_ts)
        base.update({"yes_prob": 0.5, "title": "", "condition_id": "", "volume": 0})
        return base
