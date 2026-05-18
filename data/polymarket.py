import aiohttp
import logging
from config import Config

logger = logging.getLogger(__name__)

_BTC_KEYWORDS   = ["bitcoin", "btc"]
_15M_KEYWORDS   = ["15 min", "15-min", "15min", "15 minute", "next 15"]
_UPDOWN_KEYWORDS = ["higher", "lower", "up or down", "up/down", "above", "below"]

_SEARCH_TERMS = [
    "btc 15 minute",
    "bitcoin 15 minute",
    "btc up or down",
    "btc higher lower",
    "bitcoin higher",
]


class PolymarketFetcher:
    """Watches Polymarket for the active BTC 15-minute up/down market."""

    async def _get(self, path: str, params: dict) -> list | dict:
        url = f"{Config.POLYMARKET_GAMMA_URL}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                return await r.json()

    async def get_active_15m_market(self) -> dict | None:
        """Return the currently open BTC 15-minute market, or None if not found."""
        for term in _SEARCH_TERMS:
            try:
                raw = await self._get(
                    "/markets",
                    {"search": term, "active": "true", "closed": "false", "limit": 30},
                )
                markets = raw if isinstance(raw, list) else raw.get("markets", [])
                match = self._find_15m(markets)
                if match:
                    return match
            except Exception as e:
                logger.warning(f"Polymarket search '{term}' failed: {e}")

        return None

    # Keep backwards-compatible alias used by SignalCalculator
    async def get_btc_odds(self) -> dict:
        market = await self.get_active_15m_market()
        if market:
            return market
        return {"yes_prob": 0.5, "title": "N/A", "volume": 0, "url": "https://polymarket.com", "condition_id": ""}

    # ------------------------------------------------------------------ helpers

    def _find_15m(self, markets: list) -> dict | None:
        candidates = []
        for m in markets:
            title = (m.get("question") or m.get("title") or "").lower()
            if not any(k in title for k in _BTC_KEYWORDS):
                continue
            if not any(k in title for k in _15M_KEYWORDS):
                continue
            score = sum(1 for k in _UPDOWN_KEYWORDS if k in title)
            parsed = self._parse(m, score)
            if parsed:
                candidates.append(parsed)

        if not candidates:
            return None
        candidates.sort(key=lambda x: (x["priority"], x["volume"]), reverse=True)
        return candidates[0]

    def _parse(self, m: dict, priority: int = 0) -> dict | None:
        try:
            tokens = m.get("tokens") or []
            yes_prob = None

            outcome_prices = m.get("outcomePrices")
            if outcome_prices and isinstance(outcome_prices, list):
                yes_prob = float(outcome_prices[0])

            if yes_prob is None:
                for tok in tokens:
                    if isinstance(tok, dict) and tok.get("outcome", "").lower() == "yes":
                        yes_prob = float(tok.get("price", 0.5))
                        break

            if yes_prob is None:
                yes_prob = 0.5

            condition_id = (
                m.get("conditionId")
                or m.get("id")
                or m.get("slug")
                or ""
            )
            slug = m.get("slug") or condition_id
            url = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"

            return {
                "condition_id": str(condition_id),
                "yes_prob": round(yes_prob, 4),
                "title": m.get("question") or m.get("title", "BTC 15-Min Market"),
                "volume": float(m.get("volume", 0) or 0),
                "url": url,
                "end_date": m.get("endDate") or m.get("resolutionTime") or "",
                "priority": priority,
            }
        except Exception:
            return None
