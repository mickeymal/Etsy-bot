from datetime import datetime, timezone


_DIRECTION_EMOJI = {"LONG": "📈", "SHORT": "📉", "NEUTRAL": "➡️"}
_CONFIDENCE_BAR = ["▱▱▱▱▱", "▰▱▱▱▱", "▰▰▱▱▱", "▰▰▰▱▱", "▰▰▰▰▱", "▰▰▰▰▰"]


def _bar(confidence: float) -> str:
    idx = min(5, int(confidence / 20))
    return _CONFIDENCE_BAR[idx]


def _factor_line(name: str, score: int, detail: str) -> str:
    if score > 0:
        icon = "✅"
    elif score < 0:
        icon = "🔴"
    else:
        icon = "⬜"
    return f"{icon} {name}: {detail}"


class SignalFormatter:
    def format(
        self,
        signal: dict,
        market_data: dict,
        fear_greed: dict,
        poly_odds: dict,
    ) -> str:
        direction = signal["direction"]
        confidence = signal["confidence"]
        ticker = market_data["ticker"]
        price = ticker["price"]
        change_24h = ticker["change_pct"]
        change_15m = signal["price_change_15m"]
        rsi = signal["rsi"]
        vol_ratio = signal["vol_ratio"]
        fg_val = fear_greed["value"]
        fg_label = fear_greed["label"]
        yes_prob = poly_odds.get("yes_prob", 0.5)
        poly_title = poly_odds.get("title", "N/A")

        emoji = _DIRECTION_EMOJI[direction]
        bar = _bar(confidence)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        factor_lines = "\n".join(
            _factor_line(n, s, d) for n, s, d in signal["factors"]
        )

        if direction == "NEUTRAL":
            action = "WAIT — no clear edge this candle."
        elif direction == "LONG":
            action = f"Consider YES on Polymarket | Polymarket YES ≈ {yes_prob*100:.1f}%"
        else:
            action = f"Consider NO on Polymarket | Polymarket YES ≈ {yes_prob*100:.1f}%"

        msg = (
            f"🔔 *BTC 15-MIN SIGNAL*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{emoji} *{direction}* | Confidence: *{confidence:.1f}%* {bar}\n\n"
            f"💰 Price: *${price:,.2f}* ({change_15m:+.2f}% / 15m | {change_24h:+.2f}% / 24h)\n"
            f"📊 RSI(14): *{rsi:.1f}*\n"
            f"💧 Volume: *{vol_ratio:.1f}x* avg\n"
            f"😱 Fear & Greed: *{fg_val}* — {fg_label}\n\n"
            f"*SIGNAL FACTORS:*\n"
            f"{factor_lines}\n\n"
            f"*Polymarket Market:*\n"
            f"_{poly_title[:80]}_\n\n"
            f"⚡ *ACTION:* {action}\n\n"
            f"⏰ {now}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ _Signals only. Not financial advice. DYOR._"
        )
        return msg
