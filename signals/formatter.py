from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def _bar(pct: float, width: int = 5) -> str:
    filled = round(pct / 100 * width)
    return "▰" * filled + "▱" * (width - filled)


class SignalFormatter:
    def format_exit(
        self,
        signal: dict,
        market_data: dict,
        fear_greed: dict,
        poly_market: dict,
        open_position: str,
        entry_price: float,
    ) -> str:
        current_price = signal["entry_price"]
        pnl_pct = (current_price - entry_price) / entry_price * 100
        if open_position == "SHORT":
            pnl_pct = -pnl_pct

        now          = datetime.now(_ET).strftime("%-I:%M %p ET")
        window_label = poly_market.get("window_label", "")
        market_url   = poly_market.get("url", "https://polymarket.com")
        fg_val       = fear_greed["value"]
        fg_label     = fear_greed["label"]
        rsi          = signal["rsi"]
        vol_ratio    = signal["vol_ratio"]
        window_line  = f"🕐 <b>Window: {window_label}</b>\n" if window_label else ""

        reasons       = signal.get("top_reasons", [])
        reasons_text  = ""
        if reasons:
            bullet_lines = "\n".join(f"• {r}" for r in reasons)
            reasons_text = f"\n<b>Why exit now:</b>\n{bullet_lines}\n"

        pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"

        msg = (
            f"🔔 <b>EXIT SIGNAL — BTC 15-MIN</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{window_line}"
            f"<b>Close your {open_position} position</b>\n"
            f"💰 <b>Entry was:</b> ${entry_price:,.2f}\n"
            f"📍 <b>Current price:</b> ${current_price:,.2f}\n"
            f"{pnl_emoji} <b>Est. P&L: {pnl_pct:+.2f}%</b>\n"
            f"{reasons_text}"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 {market_url}\n\n"
            f"📊 RSI: <b>{rsi:.0f}</b> | Vol: <b>{vol_ratio:.1f}x</b> | F&G: <b>{fg_val}</b> {fg_label}\n"
            f"⏰ Exit signal at: {now}\n"
            f"⚠️ <i>You place the trade. Not financial advice.</i>"
        )
        return msg

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
        market_url    = poly_market.get("url", "https://polymarket.com")
        window_label  = poly_market.get("window_label", "")
        reasons       = signal.get("top_reasons", [])
        now           = datetime.now(_ET).strftime("%-I:%M %p ET")

        if direction == "LONG":
            action_line = "📈 <b>Action: BUY YES</b> (BTC going UP)"
        else:
            action_line = "📉 <b>Action: BUY NO</b> (BTC going DOWN)"

        bar = _bar(confidence)

        reasons_text = ""
        if reasons:
            bullet_lines = "\n".join(f"• {r}" for r in reasons)
            reasons_text = f"\n<b>Why:</b>\n{bullet_lines}\n"

        window_line = f"🕐 <b>Window: {window_label}</b>\n" if window_label else ""

        msg = (
            f"🚨 <b>SIGNAL ALERT — BTC 15-MIN</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{window_line}"
            f"{action_line}\n"
            f"<b>Confidence: {confidence:.0f}%</b> {bar}\n\n"
            f"💰 <b>Entry:</b> ${entry:,.2f}\n"
            f"🎯 <b>Rec. Take Profit:</b> ${tp:,.2f} ({tp_pct:+.2f}%)\n"
            f"🛑 <b>Rec. Stop Loss:</b> ${sl:,.2f} ({sl_pct:+.2f}%)\n"
            f"{reasons_text}"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 {market_url}\n\n"
            f"📊 RSI: <b>{rsi:.0f}</b> | Vol: <b>{vol_ratio:.1f}x</b> | F&G: <b>{fg_val}</b> {fg_label}\n"
            f"⏰ Signal at: {now}\n"
            f"⚠️ <i>You place the trade. Not financial advice.</i>"
        )
        return msg
