import aiohttp
import logging
from config import Config

logger = logging.getLogger(__name__)


class BinanceDataFetcher:
    """Fetches OHLCV, ticker, order-book, and funding-rate data from Binance.
    All endpoints are public — no API key required.
    """

    async def _get(self, base: str, path: str, params: dict) -> dict | list:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base}{path}", params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                return await r.json()

    async def get_klines(self) -> list[dict]:
        """Return the last N 15-minute candles as dicts with OHLCV fields."""
        raw = await self._get(
            Config.BINANCE_BASE_URL,
            "/api/v3/klines",
            {"symbol": Config.SYMBOL, "interval": Config.INTERVAL, "limit": Config.KLINE_LIMIT},
        )
        return [
            {
                "open_time": c[0],
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
            }
            for c in raw
        ]

    async def get_ticker(self) -> dict:
        """Return 24-hour ticker stats."""
        data = await self._get(
            Config.BINANCE_BASE_URL,
            "/api/v3/ticker/24hr",
            {"symbol": Config.SYMBOL},
        )
        return {
            "price": float(data["lastPrice"]),
            "change_pct": float(data["priceChangePercent"]),
            "high_24h": float(data["highPrice"]),
            "low_24h": float(data["lowPrice"]),
            "volume_24h": float(data["quoteVolume"]),
        }

    async def get_order_book_imbalance(self, depth: int = 20) -> float:
        """Return bid/ask volume ratio. >1 = more bid pressure (bullish)."""
        data = await self._get(
            Config.BINANCE_BASE_URL,
            "/api/v3/depth",
            {"symbol": Config.SYMBOL, "limit": depth},
        )
        bid_vol = sum(float(b[1]) for b in data["bids"])
        ask_vol = sum(float(a[1]) for a in data["asks"])
        if ask_vol == 0:
            return 1.0
        return bid_vol / ask_vol

    async def get_funding_rate(self) -> float:
        """Return latest perpetual futures funding rate for BTCUSDT.
        Negative = shorts paying longs (bullish pressure).
        Positive = longs paying shorts (bearish pressure).
        """
        raw = await self._get(
            Config.BINANCE_FUTURES_URL,
            "/fapi/v1/fundingRate",
            {"symbol": Config.SYMBOL, "limit": 1},
        )
        if raw:
            return float(raw[0]["fundingRate"])
        return 0.0

    async def get_market_data(self) -> dict:
        """Convenience: fetch klines + ticker + order book imbalance together."""
        import asyncio
        klines, ticker, ob_ratio = await asyncio.gather(
            self.get_klines(),
            self.get_ticker(),
            self.get_order_book_imbalance(),
        )
        return {"klines": klines, "ticker": ticker, "ob_ratio": ob_ratio}
