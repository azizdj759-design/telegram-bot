import numpy as np
import pyvsmc as smc
import pandas as pd

class SMCEngine:
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
            last_trend = structure.trend[-1]
            if last_trend == 1: direction = "bullish"
            elif last_trend == -1: direction = "bearish"

        price = close[-1]
        entry = stop_loss = take_profit = None
        reason = "لا توجد منطقة دخول واضحة حالياً"

        if direction == "bullish":
            for i in range(len(obs.bullish_ob) - 1, -1, -1):
                if obs.bullish_ob[i] and not (obs.mitigated[i] if hasattr(obs, "mitigated") else False):
                    entry = (obs.ob_high[i] + obs.ob_low[i]) / 2
                    stop_loss = obs.ob_low[i] - (obs.ob_high[i] - obs.ob_low[i]) * 0.5
                    risk = entry - stop_loss
                    if risk > 0:
                        take_profit = entry + risk * 2.0
                        reason = "Order Block صاعد غير مُخفف"
                        break
            if entry is None:
                for i in range(len(fvg.bullish) - 1, -1, -1):
                    if fvg.bullish[i] and not (fvg.mitigated_50[i] if hasattr(fvg, "mitigated_50") else False):
                        entry = (fvg.bullish_upper[i] + fvg.bullish_lower[i]) / 2
                        stop_loss = fvg.bullish_lower[i] - (fvg.bullish_upper[i] - fvg.bullish_lower[i]) * 0.5
                        risk = entry - stop_loss
                        if risk > 0:
                            take_profit = entry + risk * 2.0
                            reason = "Fair Value Gap صاعد غير مُخفف"
                            break

        elif direction == "bearish":
            for i in range(len(obs.bearish_ob) - 1, -1, -1):
                if obs.bearish_ob[i] and not (obs.mitigated[i] if hasattr(obs, "mitigated") else False):
                    entry = (obs.ob_high[i] + obs.ob_low[i]) / 2
                    stop_loss = obs.ob_high[i] + (obs.ob_high[i] - obs.ob_low[i]) * 0.5
                    risk = stop_loss - entry
                    if risk > 0:
                        take_profit = entry - risk * 2.0
                        reason = "Order Block هابط غير مُخفف"
                        break
            if entry is None:
                for i in range(len(fvg.bearish) - 1, -1, -1):
                    if fvg.bearish[i] and not (fvg.mitigated_50[i] if hasattr(fvg, "mitigated_50") else False):
                        entry = (fvg.bearish_upper[i] + fvg.bearish_lower[i]) / 2
                        stop_loss = fvg.bearish_upper[i] + (fvg.bearish_upper[i] - fvg.bearish_lower[i]) * 0.5
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
            "confidence": 0.8 if direction != "neutral" and entry is not None else 0.3,
        }
