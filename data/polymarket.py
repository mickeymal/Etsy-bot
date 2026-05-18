import aiohttp
import logging
from config import Config

logger = logging.getLogger(__name__)

# Known stable slugs for recurring BTC Polymarket markets.
# The fetcher falls back to a keyword search when none of these are active.
_SEARCH_TERMS = ["bitcoin", "btc"]


class PolymarketFetcher:
    """Fetches active BTC market odds from Polymarket Gamma API — no key needed."""

    async def _get(self, path: str, params: dict) -> list | dict:
        url = f"{Config.POLYMARKET_GAMMA_URL}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                return await r.json()

    async def get_btc_odds(self) -> dict:
        """Return the YES probability and title of the most relevant active BTC market."""
        for term in _SEARCH_TERMS:
            try:
                markets = await self._get(
                    "/markets",
                    {"search": term, "active": "true", "closed": "false", "limit": 20},
                )
                if not isinstance(markets, list):
                    markets = markets.get("markets", [])

                best = self._pick_best(markets)
                if best:
                    return best
            except Exception as e:
                logger.warning(f"Polymarket search '{term}' failed: {e}")

        return {"yes_prob": 0.5, "title": "N/A", "volume": 0}

    def _pick_best(self, markets: list) -> dict | None:
        scored = []
        for m in markets:
            title = (m.get("question") or m.get("title") or "").lower()
            if not any(k in title for k in ("bitcoin", "btc")):
                continue

            # Prefer markets explicitly about price going up/down
            priority = 0
            for kw in ("above", "below", "higher", "reach", "hit"):
                if kw in title:
                    priority += 1

            try:
                outcomes = m.get("outcomes") or []
                tokens = m.get("tokens") or []

                yes_prob = None

                # Gamma v2 format: outcomePrices list
                outcome_prices = m.get("outcomePrices")
                if outcome_prices and isinstance(outcome_prices, list):
                    yes_prob = float(outcome_prices[0])

                # Gamma v1 format: tokens[0].price
                if yes_prob is None and tokens:
                    for tok in tokens:
                        if isinstance(tok, dict) and tok.get("outcome", "").lower() == "yes":
                            yes_prob = float(tok.get("price", 0.5))
                            break

                if yes_prob is None:
                    yes_prob = 0.5

                scored.append({
                    "priority": priority,
                    "yes_prob": round(yes_prob, 4),
                    "title": m.get("question") or m.get("title", "BTC Market"),
                    "volume": float(m.get("volume", 0) or 0),
                })
            except Exception:
                continue

        if not scored:
            return None

        # Sort by priority desc, then volume desc
        scored.sort(key=lambda x: (x["priority"], x["volume"]), reverse=True)
        return scored[0]
