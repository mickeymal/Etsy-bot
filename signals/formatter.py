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
        poly_market: dict,
    ) -> str:
        direction  = signal["direction"]
        confidence = signal["confidence"]
        entry      = signal["entry_price"]
        tp         = signal["tp_price"]
        sl         = signal["sl_price"]
        tp_pct     = signal["tp_pct"]
        sl_pct     = signal["sl_pct"]
        rsi        = signal["rsi"]
        vol_ratio  = signal["vol_ratio"]
        fg_val     = fear_greed["value"]
        fg_label   = fear_greed["label"]
        market_url = poly_market.get("url", "https://polymarket.com")
        market_ttl = poly_market.get("title", "")
        reasons    = signal.get("top_reasons", [])
        now        = datetime.now(timezone.utc).strftime("%H:%M UTC")

        if direction == "LONG":
            action_line = "📈 *Action: BUY YES* \\(BTC going UP\\)"
        else:
            action_line = "📉 *Action: BUY NO* \\(BTC going DOWN\\)"

        bar = _bar(confidence)

        reasons_text = ""
        if reasons:
            bullet_lines = "\n".join(f"• {r}" for r in reasons)
            reasons_text = f"\n*Why:*\n{bullet_lines}\n"

        market_line = ""
        if market_ttl:
            market_line = f"\n📋 _{market_ttl[:80]}_"

        msg = (
            f"🚨 *SIGNAL ALERT — BTC 15\\-MIN*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{action_line}\n"
            f"*Confidence: {confidence:.0f}%* {bar}\n\n"
            f"💰 *Entry:* ${entry:,.2f}\n"
            f"🎯 *Rec\\. Take Profit:* ${tp:,.2f} \\({tp_pct:+.2f}%\\)\n"
            f"🛑 *Rec\\. Stop Loss:* ${sl:,.2f} \\({sl_pct:+.2f}%\\)\n"
            f"{reasons_text}"
            f"━━━━━━━━━━━━━━━━━━━"
            f"{market_line}\n"
            f"🔗 {market_url}\n\n"
            f"📊 RSI: *{rsi:.0f}* \\| Vol: *{vol_ratio:.1f}x* \\| F&G: *{fg_val}* {fg_label}\n"
            f"⏰ {now}\n"
            f"⚠️ _You place the trade\\. Not financial advice\\._"
        )
        return msg
