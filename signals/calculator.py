"""
Multi-factor BTC signal calculator.

Score: -100 (max short) to +100 (max long).
long_confidence + short_confidence always = 100%.
TP/SL derived from ATR of recent candles.
"""

import logging

logger = logging.getLogger(__name__)

_MAX_SCORE = 95   # sum of all max-weight factors


# ── Technical helpers ─────────────────────────────────────────────────────────

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
    if len(klines) < period + 1:
        return max(klines[-1]["high"] - klines[-1]["low"], 50.0)
    trs = []
    for i in range(-period, 0):
        c = klines[i]
        p = klines[i - 1]["close"]
        trs.append(max(c["high"] - c["low"], abs(c["high"] - p), abs(c["low"] - p)))
    return sum(trs) / len(trs)


def _avg_volume(klines: list[dict], lookback: int = 20) -> float:
    vols = [c["volume"] for c in klines[-lookback - 1:-1]]
    return sum(vols) / len(vols) if vols else 1.0


# ── Calculator ────────────────────────────────────────────────────────────────

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

        closes       = [c["close"] for c in klines]
        current_vol  = klines[-1]["volume"]
        avg_vol      = _avg_volume(klines)
        vol_ratio    = current_vol / avg_vol if avg_vol else 1.0
        price_change = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 else 0.0

        rsi           = _rsi(closes)
        macd_val, macd_sig = _macd(closes)
        atr           = _atr(klines)
        entry_price   = closes[-1]

        score   = 0
        factors = []

        # ── 1. Price momentum (weight 20) ── most important for 15-min trade ──
        if price_change > 0.5:
            s = 20;  factors.append(("Strong bullish momentum", s, f"{price_change:+.2f}%"))
        elif price_change > 0.2:
            s = 12;  factors.append(("Bullish momentum", s, f"{price_change:+.2f}%"))
        elif price_change > 0.05:
            s = 5;   factors.append(("Slight bullish momentum", s, f"{price_change:+.2f}%"))
        elif price_change < -0.5:
            s = -20; factors.append(("Strong bearish momentum", s, f"{price_change:+.2f}%"))
        elif price_change < -0.2:
            s = -12; factors.append(("Bearish momentum", s, f"{price_change:+.2f}%"))
        elif price_change < -0.05:
            s = -5;  factors.append(("Slight bearish momentum", s, f"{price_change:+.2f}%"))
        else:
            s = 0;   factors.append(("No momentum", 0, f"{price_change:+.2f}%"))
        score += s

        # ── 2. RSI (weight 20) ──────────────────────────────────────────────
        if rsi < 30:
            s = 20;  factors.append(("RSI extreme oversold", s, f"{rsi:.0f}"))
        elif rsi < 40:
            s = 12;  factors.append(("RSI oversold", s, f"{rsi:.0f}"))
        elif rsi < 45:
            s = 5;   factors.append(("RSI near oversold", s, f"{rsi:.0f}"))
        elif rsi > 70:
            s = -20; factors.append(("RSI extreme overbought", s, f"{rsi:.0f}"))
        elif rsi > 60:
            s = -12; factors.append(("RSI overbought", s, f"{rsi:.0f}"))
        elif rsi > 55:
            s = -5;  factors.append(("RSI near overbought", s, f"{rsi:.0f}"))
        else:
            s = 0;   factors.append(("RSI neutral", 0, f"{rsi:.0f}"))
        score += s

        # ── 3. MACD (weight 15) ─────────────────────────────────────────────
        if macd_val > macd_sig:
            s = 15 if macd_val > 0 else 8
            factors.append(("MACD bullish cross", s, f"{macd_val:.1f}"))
        else:
            s = -15 if macd_val < 0 else -8
            factors.append(("MACD bearish cross", s, f"{macd_val:.1f}"))
        score += s

        # ── 4. Funding rate (weight 20) ─────────────────────────────────────
        if funding_rate < -0.0005:
            s = 20;  factors.append(("Shorts paying — squeeze risk", s, f"{funding_rate*100:.4f}%"))
        elif funding_rate < -0.0001:
            s = 10;  factors.append(("Slight short bias in futures", s, f"{funding_rate*100:.4f}%"))
        elif funding_rate > 0.0005:
            s = -20; factors.append(("Longs paying — liquidation risk", s, f"{funding_rate*100:.4f}%"))
        elif funding_rate > 0.0001:
            s = -10; factors.append(("Slight long bias in futures", s, f"{funding_rate*100:.4f}%"))
        else:
            s = 0;   factors.append(("Funding neutral", 0, f"{funding_rate*100:.4f}%"))
        score += s

        # ── 5. Fear & Greed (weight 10 — macro context, lower weight) ───────
        fg = fear_greed["value"]
        if fg <= 25:
            s = 10;  factors.append(("Extreme fear — contrarian buy", s, str(fg)))
        elif fg <= 40:
            s = 5;   factors.append(("Fear — mild bullish bias", s, str(fg)))
        elif fg >= 75:
            s = -10; factors.append(("Extreme greed — contrarian sell", s, str(fg)))
        elif fg >= 60:
            s = -5;  factors.append(("Greed — mild bearish bias", s, str(fg)))
        else:
            s = 0;   factors.append(("Sentiment neutral", 0, str(fg)))
        score += s

        # ── 6. Order book (weight 10) ────────────────────────────────────────
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

        # ── Volume amplifier (boosts signal, not scored independently) ───────
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

        # TP / SL  (2:1 risk/reward based on ATR)
        if direction == "SHORT":
            tp_price = entry_price - 1.5 * atr
            sl_price = entry_price + 0.75 * atr
        else:
            tp_price = entry_price + 1.5 * atr
            sl_price = entry_price - 0.75 * atr

        tp_pct = (tp_price - entry_price) / entry_price * 100
        sl_pct = (sl_price - entry_price) / entry_price * 100

        # Top 3 reasons in signal direction
        signed = [(n, s, d) for n, s, d in factors if s != 0]
        signed.sort(key=lambda x: x[1] if score >= 0 else -x[1], reverse=True)
        top_reasons = [f"{n} ({d})" for n, s, d in signed[:3] if abs(s) >= 5]

        return {
            "score":            score,
            "direction":        direction,
            "confidence":       confidence,
            "long_confidence":  long_confidence,
            "short_confidence": short_confidence,
            "rsi":              rsi,
            "macd":             macd_val,
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
