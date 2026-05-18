"""
Multi-factor BTC signal calculator.

Score range: -85 to +85.
long_confidence + short_confidence always = 100%.
TP/SL derived from ATR (Average True Range) of recent candles.
"""

import logging

logger = logging.getLogger(__name__)

_MAX_SCORE = 85


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[-period - 1 + i] - closes[-period - 2 + i]
        (gains if diff >= 0 else losses).append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _macd(closes: list[float]) -> tuple[float, float]:
    if len(closes) < 35:
        return 0.0, 0.0
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [m - e for m, e in zip(ema12, ema26)]
    return macd_line[-1], _ema(macd_line, 9)[-1]


def _atr(klines: list[dict], period: int = 14) -> float:
    """Average True Range — measures recent volatility per candle."""
    if len(klines) < period + 1:
        # Fallback: use the range of the last candle
        c = klines[-1]
        return max(c["high"] - c["low"], 50.0)
    true_ranges = []
    for i in range(-period, 0):
        c = klines[i]
        prev_close = klines[i - 1]["close"]
        tr = max(c["high"] - c["low"],
                 abs(c["high"] - prev_close),
                 abs(c["low"] - prev_close))
        true_ranges.append(tr)
    return sum(true_ranges) / len(true_ranges)


def _avg_volume(klines: list[dict], lookback: int = 20) -> float:
    vols = [c["volume"] for c in klines[-lookback - 1:-1]]
    return sum(vols) / len(vols) if vols else 1.0


class SignalCalculator:
    def calculate(
        self,
        market_data: dict,
        funding_rate: float,
        fear_greed: dict,
        poly_odds: dict,
    ) -> dict:
        klines   = market_data["klines"]
        ticker   = market_data["ticker"]
        ob_ratio = market_data["ob_ratio"]

        closes        = [c["close"] for c in klines]
        current_vol   = klines[-1]["volume"]
        avg_vol       = _avg_volume(klines)
        vol_ratio     = current_vol / avg_vol if avg_vol else 1.0
        price_change  = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 else 0.0

        rsi          = _rsi(closes)
        macd_val, macd_sig = _macd(closes)
        atr          = _atr(klines)
        entry_price  = closes[-1]

        score   = 0
        factors = []

        # --- RSI (weight 20) ---
        if rsi < 30:
            s = 20; factors.append(("RSI extreme oversold", s, f"{rsi:.0f}"))
        elif rsi < 40:
            s = 12; factors.append(("RSI oversold", s, f"{rsi:.0f}"))
        elif rsi < 48:
            s = 5;  factors.append(("RSI near oversold", s, f"{rsi:.0f}"))
        elif rsi > 70:
            s = -20; factors.append(("RSI extreme overbought", s, f"{rsi:.0f}"))
        elif rsi > 60:
            s = -12; factors.append(("RSI overbought", s, f"{rsi:.0f}"))
        elif rsi > 52:
            s = -5;  factors.append(("RSI near overbought", s, f"{rsi:.0f}"))
        else:
            s = 0;   factors.append(("RSI neutral", 0, f"{rsi:.0f}"))
        score += s

        # --- MACD (weight 15) ---
        if macd_val > macd_sig:
            s = 15 if macd_val > 0 else 8
            factors.append(("MACD bullish cross", s, f"{macd_val:.1f}"))
        else:
            s = -15 if macd_val < 0 else -8
            factors.append(("MACD bearish cross", s, f"{macd_val:.1f}"))
        score += s

        # --- Funding rate (weight 20) ---
        if funding_rate < -0.0005:
            s = 20;  factors.append(("Shorts paying (squeeze risk)", s, f"{funding_rate*100:.4f}%"))
        elif funding_rate < -0.0001:
            s = 10;  factors.append(("Slight short bias", s, f"{funding_rate*100:.4f}%"))
        elif funding_rate > 0.0005:
            s = -20; factors.append(("Longs paying (liquidation risk)", s, f"{funding_rate*100:.4f}%"))
        elif funding_rate > 0.0001:
            s = -10; factors.append(("Slight long bias", s, f"{funding_rate*100:.4f}%"))
        else:
            s = 0;   factors.append(("Funding neutral", 0, f"{funding_rate*100:.4f}%"))
        score += s

        # --- Fear & Greed (weight 15) ---
        fg = fear_greed["value"]
        if fg <= 25:
            s = 15;  factors.append(("Extreme fear (contrarian buy)", s, str(fg)))
        elif fg <= 40:
            s = 8;   factors.append(("Market fear", s, str(fg)))
        elif fg >= 75:
            s = -15; factors.append(("Extreme greed (contrarian sell)", s, str(fg)))
        elif fg >= 60:
            s = -8;  factors.append(("Market greed", s, str(fg)))
        else:
            s = 0;   factors.append(("Sentiment neutral", 0, str(fg)))
        score += s

        # --- Order book (weight 10) ---
        if ob_ratio > 1.3:
            s = 10;  factors.append(("Heavy bid pressure", s, f"{ob_ratio:.2f}x"))
        elif ob_ratio > 1.1:
            s = 5;   factors.append(("Slight bid pressure", s, f"{ob_ratio:.2f}x"))
        elif ob_ratio < 0.7:
            s = -10; factors.append(("Heavy ask pressure", s, f"{ob_ratio:.2f}x"))
        elif ob_ratio < 0.9:
            s = -5;  factors.append(("Slight ask pressure", s, f"{ob_ratio:.2f}x"))
        else:
            s = 0;   factors.append(("Order book balanced", 0, f"{ob_ratio:.2f}x"))
        score += s

        # --- Polymarket odds (weight 5) ---
        yes_prob = poly_odds.get("yes_prob", 0.5)
        if yes_prob > 0.65:
            s = 5;  factors.append(("Polymarket YES favored", s, f"{yes_prob*100:.0f}%"))
        elif yes_prob < 0.35:
            s = -5; factors.append(("Polymarket NO favored", s, f"{yes_prob*100:.0f}%"))
        else:
            s = 0;  factors.append(("Polymarket even odds", 0, f"{yes_prob*100:.0f}%"))
        score += s

        # --- Volume amplifier ---
        if vol_ratio >= 1.5:
            score = int(score * 1.15)
            factors.append(("Volume spike", 0, f"{vol_ratio:.1f}x avg"))

        # Clamp
        score = max(-_MAX_SCORE, min(_MAX_SCORE, score))

        # Confidence (complementary, sums to 100%)
        long_confidence  = round((score + _MAX_SCORE) / (2 * _MAX_SCORE) * 100, 1)
        short_confidence = round(100 - long_confidence, 1)
        direction        = "LONG" if score > 0 else ("SHORT" if score < 0 else "NEUTRAL")
        confidence       = long_confidence if score >= 0 else short_confidence

        # TP / SL based on ATR
        # LONG:  TP = +1.5×ATR,  SL = -0.75×ATR   (2:1 risk/reward)
        # SHORT: TP = -1.5×ATR,  SL = +0.75×ATR
        if direction == "SHORT":
            tp_price = entry_price - 1.5 * atr
            sl_price = entry_price + 0.75 * atr
        else:
            tp_price = entry_price + 1.5 * atr
            sl_price = entry_price - 0.75 * atr

        tp_pct = (tp_price - entry_price) / entry_price * 100
        sl_pct = (sl_price - entry_price) / entry_price * 100

        # Top reasons (strongest factors in the dominant direction)
        signed_factors = [(n, s, d) for n, s, d in factors if s != 0]
        signed_factors.sort(key=lambda x: x[1] if score >= 0 else -x[1], reverse=True)
        top_reasons = [f"{n} ({d})" for n, s, d in signed_factors[:3] if abs(s) >= 5]

        return {
            "score":            score,
            "direction":        direction,
            "confidence":       confidence,
            "long_confidence":  long_confidence,
            "short_confidence": short_confidence,
            "rsi":              rsi,
            "macd":             macd_val,
            "macd_signal":      macd_sig,
            "price_change_15m": price_change,
            "vol_ratio":        vol_ratio,
            "entry_price":      entry_price,
            "tp_price":         tp_price,
            "sl_price":         sl_price,
            "tp_pct":           tp_pct,
            "sl_pct":           sl_pct,
            "atr":              atr,
            "top_reasons":      top_reasons,
            "factors":          factors,
        }
