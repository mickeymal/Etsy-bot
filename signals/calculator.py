"""
Multi-factor BTC signal calculator.

Score range: -100 (max short) to +100 (max long).
Confidence = |score| / MAX_SCORE * 100 (capped at 100 %).
Direction = LONG if score > 0, SHORT if score < 0.
"""

import logging

logger = logging.getLogger(__name__)

# Total weight budget — used to normalise confidence to 0-100 %
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
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _macd(closes: list[float]) -> tuple[float, float]:
    """Return (macd_line, signal_line)."""
    if len(closes) < 35:
        return 0.0, 0.0
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [m - e for m, e in zip(ema12, ema26)]
    signal_line = _ema(macd_line, 9)
    return macd_line[-1], signal_line[-1]


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
        klines = market_data["klines"]
        ticker = market_data["ticker"]
        ob_ratio = market_data["ob_ratio"]

        closes = [c["close"] for c in klines]
        current_vol = klines[-1]["volume"]
        avg_vol = _avg_volume(klines)
        vol_ratio = current_vol / avg_vol if avg_vol else 1.0

        rsi = _rsi(closes)
        macd_val, macd_sig = _macd(closes)
        price_change_15m = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 else 0.0

        score = 0
        factors = []

        # --- RSI (weight: 20) ---
        if rsi < 30:
            s = 20
            factors.append(("RSI Extreme Oversold", s, f"RSI {rsi:.1f}"))
        elif rsi < 40:
            s = 12
            factors.append(("RSI Oversold", s, f"RSI {rsi:.1f}"))
        elif rsi < 48:
            s = 5
            factors.append(("RSI Approaching Oversold", s, f"RSI {rsi:.1f}"))
        elif rsi > 70:
            s = -20
            factors.append(("RSI Extreme Overbought", s, f"RSI {rsi:.1f}"))
        elif rsi > 60:
            s = -12
            factors.append(("RSI Overbought", s, f"RSI {rsi:.1f}"))
        elif rsi > 52:
            s = -5
            factors.append(("RSI Approaching Overbought", s, f"RSI {rsi:.1f}"))
        else:
            s = 0
            factors.append(("RSI Neutral", 0, f"RSI {rsi:.1f}"))
        score += s

        # --- MACD (weight: 15) ---
        if macd_val > macd_sig:
            s = 15 if macd_val > 0 else 8
            factors.append(("MACD Bullish Cross", s, f"{macd_val:.1f} > {macd_sig:.1f}"))
        else:
            s = -15 if macd_val < 0 else -8
            factors.append(("MACD Bearish Cross", s, f"{macd_val:.1f} < {macd_sig:.1f}"))
        score += s

        # --- Funding Rate (weight: 20) ---
        if funding_rate < -0.0005:
            s = 20
            factors.append(("Funding: Shorts Paying", s, f"{funding_rate*100:.4f}%"))
        elif funding_rate < -0.0001:
            s = 10
            factors.append(("Funding: Slight Short Bias", s, f"{funding_rate*100:.4f}%"))
        elif funding_rate > 0.0005:
            s = -20
            factors.append(("Funding: Longs Paying", s, f"{funding_rate*100:.4f}%"))
        elif funding_rate > 0.0001:
            s = -10
            factors.append(("Funding: Slight Long Bias", s, f"{funding_rate*100:.4f}%"))
        else:
            s = 0
            factors.append(("Funding: Neutral", 0, f"{funding_rate*100:.4f}%"))
        score += s

        # --- Fear & Greed (weight: 15) ---
        fg = fear_greed["value"]
        if fg <= 25:
            s = 15
            factors.append(("Fear & Greed: Extreme Fear", s, str(fg)))
        elif fg <= 40:
            s = 8
            factors.append(("Fear & Greed: Fear", s, str(fg)))
        elif fg >= 75:
            s = -15
            factors.append(("Fear & Greed: Extreme Greed", s, str(fg)))
        elif fg >= 60:
            s = -8
            factors.append(("Fear & Greed: Greed", s, str(fg)))
        else:
            s = 0
            factors.append(("Fear & Greed: Neutral", 0, str(fg)))
        score += s

        # --- Order-Book Imbalance (weight: 10) ---
        if ob_ratio > 1.3:
            s = 10
            factors.append(("Order Book: Bid Heavy", s, f"{ob_ratio:.2f}x"))
        elif ob_ratio > 1.1:
            s = 5
            factors.append(("Order Book: Slight Bid Pressure", s, f"{ob_ratio:.2f}x"))
        elif ob_ratio < 0.7:
            s = -10
            factors.append(("Order Book: Ask Heavy", s, f"{ob_ratio:.2f}x"))
        elif ob_ratio < 0.9:
            s = -5
            factors.append(("Order Book: Slight Ask Pressure", s, f"{ob_ratio:.2f}x"))
        else:
            s = 0
            factors.append(("Order Book: Balanced", 0, f"{ob_ratio:.2f}x"))
        score += s

        # --- Polymarket Odds (weight: 5) ---
        yes_prob = poly_odds.get("yes_prob", 0.5)
        if yes_prob > 0.65:
            s = 5
            factors.append(("Polymarket: YES Favored", s, f"{yes_prob*100:.1f}%"))
        elif yes_prob < 0.35:
            s = -5
            factors.append(("Polymarket: NO Favored", s, f"{yes_prob*100:.1f}%"))
        else:
            s = 0
            factors.append(("Polymarket: Even Odds", 0, f"{yes_prob*100:.1f}%"))
        score += s

        # --- Volume amplifier (not scored, used for display and mild boost) ---
        if vol_ratio >= 1.5:
            # Amplify existing signal slightly
            score = int(score * 1.15)
            factors.append(("Volume Spike", 0, f"{vol_ratio:.1f}x avg — amplified"))

        # Clamp and normalise
        score = max(-_MAX_SCORE, min(_MAX_SCORE, score))
        confidence = round(abs(score) / _MAX_SCORE * 100, 1)

        return {
            "score": score,
            "direction": "LONG" if score > 0 else ("SHORT" if score < 0 else "NEUTRAL"),
            "confidence": confidence,
            "rsi": rsi,
            "macd": macd_val,
            "macd_signal": macd_sig,
            "price_change_15m": price_change_15m,
            "vol_ratio": vol_ratio,
            "factors": factors,
        }
