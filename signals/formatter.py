from datetime import datetime, timezone


def _bar(pct: float, width: int = 5) -> str:
    filled = round(pct / 100 * width)
    return "▰" * filled + "▱" * (width - filled)


def _short_end_date(end_date: str) -> str:
    if not end_date:
        return ""
    try:
        # ISO format: 2025-05-18T14:15:00Z
        dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return dt.strftime("%H:%M UTC")
    except Exception:
        return end_date[:16]


class SignalFormatter:
    def format(
        self,
        signal: dict,
        market_data: dict,
        fear_greed: dict,
        poly_market: dict,
    ) -> str:
        long_conf  = signal["long_confidence"]
        short_conf = signal["short_confidence"]
        ticker     = market_data["ticker"]
        price      = ticker["price"]
        change_15m = signal["price_change_15m"]
        change_24h = ticker["change_pct"]
        rsi        = signal["rsi"]
        vol_ratio  = signal["vol_ratio"]
        fg_val     = fear_greed["value"]
        fg_label   = fear_greed["label"]
        market_url = poly_market.get("url", "https://polymarket.com")
        title      = poly_market.get("title", "BTC 15-Min Market")
        closes_at  = _short_end_date(poly_market.get("end_date", ""))
        now        = datetime.now(timezone.utc).strftime("%H:%M UTC")

        closes_line = f"⏳ Closes: *{closes_at}*\n" if closes_at else ""

        msg = (
            f"🔔 *BTC 15-MIN MARKET OPEN*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"_{title}_\n\n"
            f"📈 Signal: *LONG* \\(Buy YES\\)\n"
            f"Confidence: *{long_conf:.0f}%* {_bar(long_conf)}\n\n"
            f"📉 Signal: *SHORT* \\(Buy NO\\)\n"
            f"Confidence: *{short_conf:.0f}%* {_bar(short_conf)}\n\n"
            f"🔗 {market_url}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 BTC: *${price:,.2f}* ({change_15m:+.2f}% / 15m | {change_24h:+.2f}% / 24h)\n"
            f"📊 RSI: *{rsi:.1f}* | Vol: *{vol_ratio:.1f}x* avg\n"
            f"😱 Fear & Greed: *{fg_val}* — {fg_label}\n"
            f"{closes_line}"
            f"⏰ Signal at: *{now}*\n"
            f"⚠️ _You place the trade\\. Not financial advice\\._"
        )
        return msg
