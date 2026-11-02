import numpy as np
import pyvsmc as smc
import pandas as pd

class SMCEngine:
    """
    محرك SMC/ICT: يحدد اتجاه السوق (BOS/CHOCH)، ثم يبحث عن منطقة دخول
    من Order Block أو FVG متوافقة مع الاتجاه.
    """

    def analyze(self, df: pd.DataFrame) -> dict:
        high = df["high"].values.astype(float)
        low = df["low"].values.astype(float)
        close = df["close"].values.astype(float)
        open_ = df["open"].values.astype(float)

        structure = smc.detect_structure(high, low, close, window_size=5, break_mode="close")
        obs = smc.detect_order_blocks(open_, high, low, close, lookback=10, zone_mode="body",
                                      compute_mitigation=True)
        fvg = smc.detect_fvg(high, low, close=close, compute_mitigation=True)

        direction = "neutral"
        if structure.trend is not None and len(structure.trend) > 0:
            last_trend = structure.trend[-1] if isinstance(structure.trend, (list, np.ndarray)) else structure.trend
            if last_trend == 1 or last_trend == "bullish":
                direction = "bullish"
            elif last_trend == -1 or last_trend == "bearish":
                direction = "bearish"

        price = close[-1]
        entry = stop_loss = take_profit = None
        reason = "لا توجد منطقة دخول واضحة حالياً"

        if direction == "bullish":
            # ابحث عن آخر Order Block صاعد غير مُخفف
            for i in range(len(obs.bullish_ob) - 1, -1, -1):
                if obs.bullish_ob[i] and not (obs.mitigated[i] if hasattr(obs, "mitigated") else False):
                    entry = (obs.top[i] + obs.bottom[i]) / 2
                    stop_loss = obs.bottom[i] - (obs.top[i] - obs.bottom[i]) * 0.5
                    risk = entry - stop_loss
                    if risk > 0:
                        take_profit = entry + risk * 2.0  # R:R = 1:2
                        reason = "Order Block صاعد غير مُخفف"
                        break
            if entry is None:
                # بديل: FVG صاعد
                for i in range(len(fvg.bullish) - 1, -1, -1):
                    if fvg.bullish[i] and not (fvg.mitigated_50[i] if hasattr(fvg, "mitigated_50") else False):
                        entry = (fvg.top[i] + fvg.bottom[i]) / 2
                        stop_loss = fvg.bottom[i] - (fvg.top[i] - fvg.bottom[i]) * 0.5
                        risk = entry - stop_loss
                        if risk > 0:
                            take_profit = entry + risk * 2.0
                            reason = "Fair Value Gap صاعد غير مُخفف"
                            break

        elif direction == "bearish":
            for i in range(len(obs.bearish_ob) - 1, -1, -1):
                if obs.bearish_ob[i] and not (obs.mitigated[i] if hasattr(obs, "mitigated") else False):
                    entry = (obs.top[i] + obs.bottom[i]) / 2
                    stop_loss = obs.top[i] + (obs.top[i] - obs.bottom[i]) * 0.5
                    risk = stop_loss - entry
                    if risk > 0:
                        take_profit = entry - risk * 2.0
                        reason = "Order Block هابط غير مُخفف"
                        break
            if entry is None:
                for i in range(len(fvg.bearish) - 1, -1, -1):
                    if fvg.bearish[i] and not (fvg.mitigated_50[i] if hasattr(fvg, "mitigated_50") else False):
                        entry = (fvg.top[i] + fvg.bottom[i]) / 2
                        stop_loss = fvg.top[i] + (fvg.top[i] - fvg.bottom[i]) * 0.5
                        risk = stop_loss - entry
                        if risk > 0:
                            take_profit = entry - risk * 2.0
                            reason = "Fair Value Gap هابط غير مُخفف"
                            break

        return {
            "strategy": "SMC/ICT",
            "direction": direction,
            "entry": round(float(entry), 4) if entry is not None else None,
            "stop_loss": round(float(stop_loss), 4) if stop_loss is not None else None,
            "take_profit": round(float(take_profit), 4) if take_profit is not None else None,
            "reason": reason,
            "confidence": self._confidence(direction, entry, structure),
        }

    def _confidence(self, direction, entry, structure):
        if direction == "neutral" or entry is None:
            return 0.3
        # ثقة أولية بناءً على وضوح الهيكل (يمكن تطويرها لاحقاً)
        return 0.7
