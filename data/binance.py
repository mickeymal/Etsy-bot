import aiohttp
import asyncio
import logging
from config import Config

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "btc-signal-bot/1.0"}
_OKX = "https://www.okx.com/api/v5"
_SPOT = "BTC-USDT"
_PERP = "BTC-USDT-SWAP"


class BinanceDataFetcher:
    """Market data from OKX public API — no geo-restrictions, no API key required."""

    async def _get(self, path: str, params: dict = None) -> dict:
        async with aiohttp.ClientSession(headers=_HEADERS) as session:
            async with session.get(
                f"{_OKX}{path}",
                params=params or {},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                r.raise_for_status()
                return await r.json()

    async def get_klines(self) -> list[dict]:
        """Return the last ~60 15-minute candles from OKX.
        OKX format: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
        """
        data = await self._get(
            "/market/candles",
            {"instId": _SPOT, "bar": "15m", "limit": Config.KLINE_LIMIT},
        )
        candles = data.get("data", [])
        # OKX returns newest first — reverse so oldest is index 0
        candles = list(reversed(candles))
        return [
            {
                "open_time": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
            }
            for c in candles
        ]

    async def get_ticker(self) -> dict:
        """Return current price and 24h stats from OKX."""
        data = await self._get("/market/ticker", {"instId": _SPOT})
        t = data["data"][0]

        price = float(t["last"])
        open_24h = float(t["open24h"])
        change_pct = ((price - open_24h) / open_24h * 100) if open_24h else 0.0

        return {
            "price": price,
            "change_pct": round(change_pct, 2),
            "high_24h": float(t["high24h"]),
            "low_24h": float(t["low24h"]),
            "volume_24h": float(t.get("volCcy24h", t.get("vol24h", 0))),
        }

    async def get_order_book_imbalance(self, depth: int = 20) -> float:
        """Return bid/ask volume ratio from OKX order book. >1 = bullish pressure."""
        data = await self._get("/market/books", {"instId": _SPOT, "sz": depth})
        book = data["data"][0]
        # OKX format: [[price, size, liquidated_orders, num_orders], ...]
        bid_vol = sum(float(b[1]) for b in book.get("bids", []))
        ask_vol = sum(float(a[1]) for a in book.get("asks", []))
        if ask_vol == 0:
            return 1.0
        return bid_vol / ask_vol

    async def get_funding_rate(self) -> float:
        """Return latest BTC perpetual funding rate from OKX.
        Negative = shorts paying longs (bullish).
        Positive = longs paying shorts (bearish).
        """
        try:
            data = await self._get("/public/funding-rate", {"instId": _PERP})
            entries = data.get("data", [])
            if entries:
                return float(entries[0]["fundingRate"])
        except Exception as e:
            logger.warning(f"OKX funding rate fetch failed: {e}")
        return 0.0

    async def get_market_data(self) -> dict:
        """Fetch klines + ticker + order book imbalance in parallel."""
        klines, ticker, ob_ratio = await asyncio.gather(
            self.get_klines(),
            self.get_ticker(),
            self.get_order_book_imbalance(),
        )
        return {"klines": klines, "ticker": ticker, "ob_ratio": ob_ratio}
