from datetime import datetime, timezone


def _bar(pct: float, width: int = 5) -> str:
    filled = round(pct / 100 * width)
    return "▰" * filled + "▱" * (width - filled)


class SignalFormatter:
    def format(
        self,
        signal: dict,
        market_data: dict,
        fear_greed: dict,
        poly_odds: dict,
    ) -> str:
        long_conf = signal["long_confidence"]
        short_conf = signal["short_confidence"]
        ticker = market_data["ticker"]
        price = ticker["price"]
        change_15m = signal["price_change_15m"]
        change_24h = ticker["change_pct"]
        rsi = signal["rsi"]
        vol_ratio = signal["vol_ratio"]
        fg_val = fear_greed["value"]
        fg_label = fear_greed["label"]
        market_url = poly_odds.get("url", "https://polymarket.com")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        msg = (
            f"🔔 *BTC 15-MIN SIGNALS*\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"📈 Signal: *LONG*\n"
            f"Confidence: *{long_conf:.0f}%* {_bar(long_conf)}\n"
            f"Market: {market_url}\n\n"
            f"📉 Signal: *SHORT*\n"
            f"Confidence: *{short_conf:.0f}%* {_bar(short_conf)}\n"
            f"Market: {market_url}\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 BTC: *${price:,.2f}* ({change_15m:+.2f}% / 15m | {change_24h:+.2f}% / 24h)\n"
            f"📊 RSI: *{rsi:.1f}* | Vol: *{vol_ratio:.1f}x* avg\n"
            f"😱 Fear & Greed: *{fg_val}* — {fg_label}\n\n"
            f"⏰ {now}\n"
            f"⚠️ _Signals only. You place trades. Not financial advice._"
        )
        return msg
