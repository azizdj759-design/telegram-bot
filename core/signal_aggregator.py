class SignalAggregator:
    def __init__(self, min_confluence=2):
        self.min_confluence = min_confluence

    def aggregate(self, signals: list[dict]) -> dict:
        valid = [s for s in signals if s["direction"] in ("bullish", "bearish")]
        if not valid:
            return self._no_trade("لا توجد إشارة اتجاه من أي استراتيجية")

        bullish = [s for s in valid if s["direction"] == "bullish"]
        bearish = [s for s in valid if s["direction"] == "bearish"]

        if len(bullish) >= self.min_confluence and len(bullish) > len(bearish):
            return self._combine(bullish, "bullish")
        elif len(bearish) >= self.min_confluence and len(bearish) > len(bullish):
            return self._combine(bearish, "bearish")
        else:
            return self._no_trade("الإشارات متعارضة أو غير كافية للتوافق")

    def _combine(self, signals, direction):
        entries = [s["entry"] for s in signals if s["entry"] is not None]
        stops = [s["stop_loss"] for s in signals if s["stop_loss"] is not None]
        targets = [s["take_profit"] for s in signals if s["take_profit"] is not None]

        if not entries or not stops:
            return self._no_trade("مستويات غير مكتملة من الاستراتيجيات المتفقة")

        entry = sum(entries) / len(entries)
        stop_loss = sum(stops) / len(stops)
        take_profit = sum(targets) / len(targets) if targets else None

        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry) if take_profit else 0
        rr = round(reward / risk, 2) if risk > 0 else 0

        # حساب نسبة النجاح التقريبية (Win Rate Score)
        # كلما زاد عدد الاستراتيجيات المتفقة وكانت نسبة RR جيدة، زادت النسبة
        win_rate = 50 + (len(signals) * 15) # قاعدة أساسية
        if rr >= 2: win_rate += 10
        if rr >= 3: win_rate += 5
        win_rate = min(95, win_rate) # سقف 95%

        return {
            "decision": "شراء" if direction == "bullish" else "بيع",
            "direction": direction,
            "entry": round(entry, 4),
            "stop_loss": round(stop_loss, 4),
            "take_profit": round(take_profit, 4) if take_profit else None,
            "risk_reward": rr,
            "win_rate": win_rate,
            "confluence_count": len(signals),
            "confluence_strategies": [s["strategy"] for s in signals],
            "details": signals,
        }

    def _no_trade(self, reason):
        return {"decision": "انتظار", "direction": "neutral", "reason": reason,
                "entry": None, "stop_loss": None, "take_profit": None,
                "win_rate": 0, "details": []}
