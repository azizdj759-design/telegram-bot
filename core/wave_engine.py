import numpy as np
import pandas as pd

class WaveEngine:
    """
    محرك تحليل موجي مبسط:
    - يكتشف القمم والقيعان المتأرجحة (Swing Points) عبر ZigZag.
    - يحدد اتجاه الموجة الأخيرة (صاعدة/هابطة).
    - يقترح دخولاً عند التصحيح وهدفاً عبر امتداد فيبوناتشي.
    """

    def analyze(self, df: pd.DataFrame, zigzag_pct=0.02) -> dict:
        highs = df["high"].values
        lows = df["low"].values
        pivots = self._zigzag(highs, lows, zigzag_pct)

        if len(pivots) < 3:
            return {"strategy": "Wave (ZigZag)", "direction": "neutral",
                    "entry": None, "stop_loss": None, "take_profit": None,
                    "reason": "نقاط تأرجح غير كافية", "confidence": 0.2}

        last_pivots = pivots[-3:]
        (p1_type, p1_price), (p2_type, p2_price), (p3_type, p3_price) = last_pivots

        direction = "neutral"
        if p1_type == "low" and p3_type == "high" and p3_price > p2_price:
            direction = "bullish"
        elif p1_type == "high" and p3_type == "low" and p3_price < p2_price:
            direction = "bearish"

        entry = stop_loss = take_profit = None
        reason = "لا يوجد نمط موجي واضح"

        if direction == "bullish":
            # الدخول عند تصحيح 61.8% من الموجة الصاعدة الأخيرة
            swing_low, swing_high = p2_price, p3_price
            entry = swing_high - (swing_high - swing_low) * 0.618
            stop_loss = swing_low - (swing_high - swing_low) * 0.1
            risk = entry - stop_loss
            if risk > 0:
                take_profit = entry + risk * 1.618
                reason = "موجة صاعدة مع تصحيح فيبوناتشي 61.8%"

        elif direction == "bearish":
            swing_high, swing_low = p2_price, p3_price
            entry = swing_low + (swing_high - swing_low) * 0.618
            stop_loss = swing_high + (swing_high - swing_low) * 0.1
            risk = stop_loss - entry
            if risk > 0:
                take_profit = entry - risk * 1.618
                reason = "موجة هابطة مع تصحيح فيبوناتشي 61.8%"

        return {
            "strategy": "Wave (ZigZag)",
            "direction": direction,
            "entry": round(float(entry), 4) if entry is not None else None,
            "stop_loss": round(float(stop_loss), 4) if stop_loss is not None else None,
            "take_profit": round(float(take_profit), 4) if take_profit is not None else None,
            "reason": reason,
            "confidence": 0.6 if direction != "neutral" and entry is not None else 0.2,
        }

    def _zigzag(self, highs, lows, pct):
        pivots = []
        last_pivot_idx = 0
        last_pivot_type = None
        for i in range(2, len(highs) - 2):
            if highs[i] == max(highs[i - 2:i + 3]):
                if last_pivot_type != "high" or highs[i] > highs[last_pivot_idx]:
                    pivots.append(("high", highs[i]))
                    last_pivot_idx, last_pivot_type = i, "high"
            elif lows[i] == min(lows[i - 2:i + 3]):
                if last_pivot_type != "low" or lows[i] < lows[last_pivot_idx]:
                    pivots.append(("low", lows[i]))
                    last_pivot_idx, last_pivot_type = i, "low"
        return pivots
