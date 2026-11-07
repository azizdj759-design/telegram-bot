"""
Zero Reversal Engine v48.1  (app.py)
- 12 استراتيجيات مستقلة + تصويت مرجّح + وقف هيكلي لكل استراتيجية
- فلاتر: نظام السوق ADX، اتجاه 1H، التقلب، ساعات السيولة، تكلفة السبريد
- رأس مال صغير: حجم الصفقة حسب المخاطرة والهامش وأصغر عقد، حدود يومية، حساب ورقي
- إدارة الصفقة: SL/TP، تعادل عند +1R، وقف متحرك بعد +1.5R
- باك تست بنفس منطق الحي مع السبريد والعمولة ورصيد تراكمي
- بوت تليغرام: /start /stop /status /trades

التوكن من متغير بيئة TELEGRAM_TOKEN (لا تكتبه في الكود).
"""
import asyncio
import html
import json
import logging
import math
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import ccxt.async_support as ccxt_async
import httpx
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

try:
    from tvDatafeed import Interval, TvDatafeed
    TV_AVAILABLE = True
except ImportError:
    TV_AVAILABLE = False

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("engine")

# ============================== الإعدادات ==============================
def _f(name: str, default) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default) -> int:
    return int(os.environ.get(name, default))


def _b(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8741070555:AAGf6ys8UH8TZwlQpy_vWff9YONZ9BDmOok")  # متغير البيئة له الأولوية إن وُجد
# معرّفات ثابتة تصلها الإشارات دائماً (تحميك من ضياع المشتركين عند إعادة تشغيل Render)
ADMIN_CHAT_IDS = {int(v) for v in os.environ.get("ADMIN_CHAT_IDS", "").replace(" ", "").split(",")
                  if v.lstrip("-").isdigit()}
SUBSCRIBERS_FILE = os.environ.get("SUBSCRIBERS_FILE", "subscribers.json")
ACCOUNT_FILE = os.environ.get("ACCOUNT_FILE", "account.json")

# --- المحرك ---
POLL_SECONDS = _i("POLL_SECONDS", 30)
FETCH_INTERVAL = _i("FETCH_INTERVAL", 60)
MIN_BARS = 150
BAR_MINUTES = 15
MIN_SCORE = _f("MIN_SCORE", 1.6)             # أقل مجموع نقاط للإشارة
MIN_STRATEGIES = _i("MIN_STRATEGIES", 2)     # أقل عدد استراتيجيات متفقة
ATR_SL_MULT = _f("ATR_SL_MULT", 1.5)         # وقف احتياطي إذا لم تعطِ الاستراتيجيات وقفاً هيكلياً
RISK_REWARD = _f("RISK_REWARD", 2.0)
COOLDOWN_BARS = _i("COOLDOWN_BARS", 4)
MAX_COST_RATIO = _f("MAX_COST_RATIO", 0.20)  # تُرفض الصفقة إذا السبريد+العمولة > 20% من مسافة الوقف
DISABLED_STRATEGIES = {s.strip() for s in os.environ.get("DISABLED_STRATEGIES", "").split(",") if s.strip()}

# --- رأس المال الصغير وإدارة المخاطر ---
ACCOUNT_BALANCE = _f("ACCOUNT_BALANCE", 100)      # بالدولار
RISK_PCT = _f("RISK_PCT", 1.0)                    # المخاطرة المستهدفة لكل صفقة %
MAX_RISK_PCT = _f("MAX_RISK_PCT", 2.0)            # سقف المخاطرة إذا كان أصغر عقد أكبر من المستهدف
MAX_TOTAL_RISK_PCT = _f("MAX_TOTAL_RISK_PCT", 3.0)  # مجموع مخاطرة الصفقات المفتوحة
LEVERAGE = _f("LEVERAGE", 100)                    # رافعة وسيط الفوركس/المعادن
MAX_MARGIN_PCT = _f("MAX_MARGIN_PCT", 40)         # أقصى هامش مستخدم من الرصيد %
MAX_OPEN_TRADES = _i("MAX_OPEN_TRADES", 2)
DAILY_LOSS_LIMIT_PCT = _f("DAILY_LOSS_LIMIT_PCT", 3.0)
MAX_CONSEC_LOSSES = _i("MAX_CONSEC_LOSSES", 3)
ALLOW_SPOT_SHORT = _b("ALLOW_SPOT_SHORT", "0")    # البيع على كريبتو السبوت غير ممكن افتراضياً


@dataclass(frozen=True)
class SymbolSpec:
    kind: str                      # crypto | metal | energy | forex
    pip: float                     # حجم النقطة لحساب الأرباح
    decimals: int
    units_per_lot: float           # عدد الوحدات في 1.00 لوت (للكريبتو: 1 عملة)
    min_lot: float                 # أصغر حجم (لوت أو عملة)
    lot_step: float
    spread_pips: float             # السبريد المعتاد بالنقاط
    group: str                     # مجموعة الارتباط: صفقة واحدة مفتوحة لكل مجموعة
    quote: str = "usd"             # عملة التسعير: usd | jpy | cad
    spot: bool = False             # سبوت (بلا رافعة ولا بيع مكشوف)
    fee_pct: float = 0.0           # عمولة لكل جهة (كسر عشري)
    tv: Optional[tuple] = None
    yf: Optional[str] = None


SYMBOLS = {
    "BTCUSDT": SymbolSpec("crypto", 1.0, 2, 1, 0.0001, 0.0001, 2, "crypto", spot=True, fee_pct=0.001),
    "ETHUSDT": SymbolSpec("crypto", 0.1, 2, 1, 0.001, 0.001, 2, "crypto", spot=True, fee_pct=0.001),
    "XAUUSD": SymbolSpec("metal", 0.1, 2, 100, 0.01, 0.01, 2.5, "metals", tv=("OANDA", "XAUUSD"), yf="GC=F"),
    "XAGUSD": SymbolSpec("metal", 0.01, 3, 5000, 0.01, 0.01, 3, "metals", tv=("OANDA", "XAGUSD"), yf="SI=F"),
    "USOIL": SymbolSpec("energy", 0.01, 2, 1000, 0.01, 0.01, 3, "oil", tv=("TVC", "USOIL"), yf="CL=F"),
    "EURUSD": SymbolSpec("forex", 0.0001, 5, 100000, 0.01, 0.01, 0.8, "usd_short", tv=("FX_IDC", "EURUSD"), yf="EURUSD=X"),
    "GBPUSD": SymbolSpec("forex", 0.0001, 5, 100000, 0.01, 0.01, 1.2, "usd_short", tv=("FX_IDC", "GBPUSD"), yf="GBPUSD=X"),
    "AUDUSD": SymbolSpec("forex", 0.0001, 5, 100000, 0.01, 0.01, 1.2, "usd_short", tv=("FX_IDC", "AUDUSD"), yf="AUDUSD=X"),
    "USDJPY": SymbolSpec("forex", 0.01, 3, 100000, 0.01, 0.01, 1.0, "usd_long", quote="jpy", tv=("FX_IDC", "USDJPY"), yf="JPY=X"),
    "USDCAD": SymbolSpec("forex", 0.0001, 5, 100000, 0.01, 0.01, 1.5, "usd_long", quote="cad", tv=("FX_IDC", "USDCAD"), yf="CAD=X"),
}


def is_market_open(kind: str, now: Optional[datetime] = None) -> bool:
    """الكريبتو 24/7. الباقي مغلق من الجمعة 22:00 إلى الأحد 22:00 UTC."""
    if kind == "crypto":
        return True
    now = now or datetime.now(timezone.utc)
    wd, hr = now.weekday(), now.hour
    if wd == 5 or (wd == 4 and hr >= 22) or (wd == 6 and hr < 22):
        return False
    return True


def in_liquid_hours(kind: str, ts: datetime) -> bool:
    """تجنب فترة التبديل اليومي (21:00-23:59 UTC) حيث يتسع السبريد في الفوركس والمعادن."""
    return kind == "crypto" or ts.hour < 21


# ============================== المؤشرات ==============================
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up, dn = d.clip(lower=0), -d.clip(upper=0)
    au = up.ewm(alpha=1 / n, adjust=False).mean()
    ad = dn.ewm(alpha=1 / n, adjust=False).mean()
    r = 100 - 100 / (1 + au / ad.replace(0, np.nan))
    r[ad == 0] = 100.0
    return r.fillna(50.0)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14):
    up = df["High"].diff()
    dn = -df["Low"].diff()
    plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    a = atr(df, n)
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False).mean() / a
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, mdi


def supertrend(df: pd.DataFrame, n: int = 10, mult: float = 3.0):
    a = atr(df, n).to_numpy()
    hl2 = ((df["High"] + df["Low"]) / 2).to_numpy()
    c = df["Close"].to_numpy()
    ub, lb = hl2 + mult * a, hl2 - mult * a
    fub, flb = ub.copy(), lb.copy()
    d = np.ones(len(df))
    for i in range(1, len(df)):
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1]) else flb[i - 1]
        if d[i - 1] == 1 and c[i] < flb[i]:
            d[i] = -1
        elif d[i - 1] == -1 and c[i] > fub[i]:
            d[i] = 1
        else:
            d[i] = d[i - 1]
    line = np.where(d == 1, flb, fub)
    return pd.Series(d, index=df.index), pd.Series(line, index=df.index)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    c, h, l = x["Close"], x["High"], x["Low"]
    x["ema20"], x["ema50"], x["ema200"] = ema(c, 20), ema(c, 50), ema(c, 200)
    x["rsi"] = rsi(c)
    macd_line = ema(c, 12) - ema(c, 26)
    x["macd"] = macd_line
    x["macd_sig"] = ema(macd_line, 9)
    x["macd_hist"] = x["macd"] - x["macd_sig"]
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std(ddof=0)
    x["bb_mid"], x["bb_up"], x["bb_lo"] = mid, mid + 2 * sd, mid - 2 * sd
    x["bb_bw"] = (x["bb_up"] - x["bb_lo"]) / mid
    x["sqz"] = x["bb_bw"] <= x["bb_bw"].rolling(100, min_periods=50).quantile(0.2)
    x["atr"] = atr(x)
    x["adx"], x["pdi"], x["mdi"] = adx(x)
    x["st_dir"], x["st_line"] = supertrend(x)
    ll, hh = l.rolling(14).min(), h.rolling(14).max()
    k = 100 * (c - ll) / (hh - ll).replace(0, np.nan)
    x["stoch_k"] = k.rolling(3).mean()
    x["stoch_d"] = x["stoch_k"].rolling(3).mean()
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    x["tenkan"], x["kijun"] = tenkan, kijun
    x["span_a"] = ((tenkan + kijun) / 2).shift(26)
    x["span_b"] = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    x["don_hi"] = h.rolling(20).max().shift(1)
    x["don_lo"] = l.rolling(20).min().shift(1)
    x["vol_ma"] = x["Volume"].rolling(20).mean()
    x["atr_med"] = x["atr"].rolling(50, min_periods=20).median()
    return x


def swing_levels(x: pd.DataFrame, w: int = 5, lookback: int = 120):
    h, l, n = x["High"].to_numpy(), x["Low"].to_numpy(), len(x)
    sup, res = [], []
    for i in range(max(w, n - lookback), n - w):
        if h[i] == h[i - w:i + w + 1].max():
            res.append(h[i])
        if l[i] == l[i - w:i + w + 1].min():
            sup.append(l[i])
    return sup, res


def candle_pattern(a, p):
    """يعيد (+1/-1/0, اسم النمط) لآخر شمعة."""
    rng = a.High - a.Low
    if rng <= 0:
        return 0, ""
    body = abs(a.Close - a.Open)
    upper = a.High - max(a.Open, a.Close)
    lower = min(a.Open, a.Close) - a.Low
    if p.Close < p.Open and a.Close > a.Open and a.Close >= p.Open and a.Open <= p.Close:
        return 1, "ابتلاع صاعد"
    if p.Close > p.Open and a.Close < a.Open and a.Close <= p.Open and a.Open >= p.Close:
        return -1, "ابتلاع هابط"
    if lower >= 2 * body and lower >= 0.55 * rng and upper <= 0.3 * rng:
        return 1, "مطرقة / Pin Bar صاعد"
    if upper >= 2 * body and upper >= 0.55 * rng and lower <= 0.3 * rng:
        return -1, "نجمة الرماية"
    return 0, ""


def htf_direction(df: pd.DataFrame) -> int:
    """اتجاه الإطار الأعلى (1H) من EMA20/EMA50."""
    try:
        h = df.resample("1h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
        if len(h) < 55:
            return 0
        e20, e50, c = ema(h["Close"], 20).iloc[-1], ema(h["Close"], 50).iloc[-1], h["Close"].iloc[-1]
        if c > e50 and e20 > e50:
            return 1
        if c < e50 and e20 < e50:
            return -1
    except Exception:
        log.exception("htf_direction failed")
    return 0


# ============================== الاستراتيجيات ==============================
@dataclass
class Signal:
    name: str
    side: int                      # +1 شراء / -1 بيع
    strength: float                # 0..1
    reason: str
    sl: Optional[float] = None     # سعر الوقف الهيكلي المقترح (نقطة إبطال الفكرة)


def _sig(name, side, strength, reason, sl=None):
    sl = float(sl) if sl is not None and sl == sl else None
    return Signal(name, side, round(min(float(strength), 1.0), 2), reason, sl)


def _vol_ok(a) -> bool:
    return a.vol_ma > 0 and a.Volume > 1.2 * a.vol_ma


def pivots(arr: np.ndarray, w: int, kind: str, start: int, end: int) -> list:
    """فهارس القمم (H) أو القيعان (L) المؤكدة: الأعلى/الأدنى ضمن ±w شمعة."""
    out = []
    for i in range(max(w, start), min(end, len(arr) - w)):
        seg = arr[i - w:i + w + 1]
        if (kind == "H" and arr[i] == seg.max()) or (kind == "L" and arr[i] == seg.min()):
            out.append(i)
    return out


def strat_ema_pullback(x):
    a, p = x.iloc[-1], x.iloc[-2]
    pat, pname = candle_pattern(a, p)
    if a.ema20 > a.ema50 > a.ema200 and a.ema50 > x["ema50"].iloc[-6] and a.Low <= a.ema20 < a.Close \
            and a.Close > a.Open and 40 <= a.rsi <= 65:
        return _sig("ema_pullback", 1, 0.6 + (0.2 if pat == 1 else 0),
                    f"ارتداد من EMA20 داخل اتجاه صاعد (RSI {a.rsi:.0f})" + (f" + {pname}" if pat == 1 else ""),
                    sl=min(a.Low, p.Low))
    if a.ema20 < a.ema50 < a.ema200 and a.ema50 < x["ema50"].iloc[-6] and a.Close < a.ema20 <= a.High \
            and a.Close < a.Open and 35 <= a.rsi <= 60:
        return _sig("ema_pullback", -1, 0.6 + (0.2 if pat == -1 else 0),
                    f"ارتداد من EMA20 داخل اتجاه هابط (RSI {a.rsi:.0f})" + (f" + {pname}" if pat == -1 else ""),
                    sl=max(a.High, p.High))
    return None


def strat_macd_cross(x):
    a, p = x.iloc[-1], x.iloc[-2]
    if p.macd_hist <= 0 < a.macd_hist and a.Close > a.ema50:
        return _sig("macd_cross", 1, 0.55 + (0.2 if a.macd < 0 else 0), "تقاطع MACD صاعد فوق EMA50",
                    sl=x["Low"].iloc[-10:].min())
    if p.macd_hist >= 0 > a.macd_hist and a.Close < a.ema50:
        return _sig("macd_cross", -1, 0.55 + (0.2 if a.macd > 0 else 0), "تقاطع MACD هابط تحت EMA50",
                    sl=x["High"].iloc[-10:].max())
    return None


def strat_rsi_bollinger(x):
    a, p = x.iloc[-1], x.iloc[-2]
    if p.Close < p.bb_lo and a.Close > a.bb_lo and a.Close > a.Open and min(p.rsi, a.rsi) < 35:
        return _sig("rsi_bollinger", 1, 0.7 + (0.15 if a.rsi > p.rsi else 0),
                    f"عودة فوق البولنجر السفلي مع RSI {min(p.rsi, a.rsi):.0f}", sl=min(a.Low, p.Low))
    if p.Close > p.bb_up and a.Close < a.bb_up and a.Close < a.Open and max(p.rsi, a.rsi) > 65:
        return _sig("rsi_bollinger", -1, 0.7 + (0.15 if a.rsi < p.rsi else 0),
                    f"عودة تحت البولنجر العلوي مع RSI {max(p.rsi, a.rsi):.0f}", sl=max(a.High, p.High))
    return None


def strat_squeeze_breakout(x):
    a = x.iloc[-1]
    if not x["sqz"].iloc[-7:-1].any():
        return None
    if a.Close > a.bb_up and a.Close > a.Open:
        return _sig("squeeze_breakout", 1, 0.65 + (0.2 if _vol_ok(a) else 0),
                    "اختراق صاعد بعد انضغاط البولنجر", sl=a.bb_mid)
    if a.Close < a.bb_lo and a.Close < a.Open:
        return _sig("squeeze_breakout", -1, 0.65 + (0.2 if _vol_ok(a) else 0),
                    "اختراق هابط بعد انضغاط البولنجر", sl=a.bb_mid)
    return None


def strat_supertrend_adx(x):
    a = x.iloc[-1]
    recent = x["st_dir"].iloc[-4:-1]
    bonus = min(0.3, max(0.0, (a.adx - 20) / 50)) if a.adx == a.adx else 0
    if a.st_dir == 1 and (recent == -1).any() and a.adx > 20 and a.pdi > a.mdi:
        return _sig("supertrend_adx", 1, 0.6 + bonus, f"انقلاب Supertrend صاعد (ADX {a.adx:.0f})", sl=a.st_line)
    if a.st_dir == -1 and (recent == 1).any() and a.adx > 20 and a.mdi > a.pdi:
        return _sig("supertrend_adx", -1, 0.6 + bonus, f"انقلاب Supertrend هابط (ADX {a.adx:.0f})", sl=a.st_line)
    return None


def strat_stochastic(x):
    a, p = x.iloc[-1], x.iloc[-2]
    if p.stoch_k <= p.stoch_d and a.stoch_k > a.stoch_d and x["stoch_k"].iloc[-4:-1].min() < 25:
        return _sig("stochastic", 1, 0.55 + (0.15 if a.Close > a.Open else 0),
                    "تقاطع ستوكاستيك صاعد من تشبع بيع", sl=x["Low"].iloc[-6:].min())
    if p.stoch_k >= p.stoch_d and a.stoch_k < a.stoch_d and x["stoch_k"].iloc[-4:-1].max() > 75:
        return _sig("stochastic", -1, 0.55 + (0.15 if a.Close < a.Open else 0),
                    "تقاطع ستوكاستيك هابط من تشبع شراء", sl=x["High"].iloc[-6:].max())
    return None


def strat_donchian(x):
    a = x.iloc[-1]
    if a.Close > a.don_hi and a.adx > 20 and a.Close > a.Open:
        return _sig("donchian", 1, 0.6 + (0.2 if _vol_ok(a) else 0), "اختراق أعلى 20 شمعة",
                    sl=x["Low"].iloc[-10:].min())
    if a.Close < a.don_lo and a.adx > 20 and a.Close < a.Open:
        return _sig("donchian", -1, 0.6 + (0.2 if _vol_ok(a) else 0), "كسر أدنى 20 شمعة",
                    sl=x["High"].iloc[-10:].max())
    return None


def strat_ichimoku(x):
    a, p, p2 = x.iloc[-1], x.iloc[-2], x.iloc[-3]
    top, bot = np.maximum(a.span_a, a.span_b), np.minimum(a.span_a, a.span_b)
    if a.Close > top and a.tenkan > a.kijun and (p.tenkan <= p.kijun or p2.tenkan <= p2.kijun) and a.span_a > a.span_b:
        return _sig("ichimoku", 1, 0.75, "إيشيموكو: فوق السحابة + تقاطع Tenkan/Kijun صاعد", sl=a.kijun)
    if a.Close < bot and a.tenkan < a.kijun and (p.tenkan >= p.kijun or p2.tenkan >= p2.kijun) and a.span_a < a.span_b:
        return _sig("ichimoku", -1, 0.75, "إيشيموكو: تحت السحابة + تقاطع Tenkan/Kijun هابط", sl=a.kijun)
    return None


def strat_sr_candle(x):
    a, p = x.iloc[-1], x.iloc[-2]
    pat, pname = candle_pattern(a, p)
    if pat == 0 or not a.atr > 0:
        return None
    sup, res = swing_levels(x)
    if pat == 1 and any(abs(a.Low - s) <= 0.5 * a.atr for s in sup):
        return _sig("sr_candle", 1, 0.75, f"{pname} عند دعم", sl=a.Low)
    if pat == -1 and any(abs(a.High - r) <= 0.5 * a.atr for r in res):
        return _sig("sr_candle", -1, 0.75, f"{pname} عند مقاومة", sl=a.High)
    return None


def strat_fib_pullback(x):
    """تصحيح فيبوناتشي إلى المنطقة الذهبية 50%-61.8% بعد موجة دافعة، ضمن اتجاه EMA50/EMA200."""
    n = len(x)
    a, p = x.iloc[-1], x.iloc[-2]
    if not a.atr > 0:
        return None
    h, l = x["High"].to_numpy(), x["Low"].to_numpy()
    ph, pl = pivots(h, 5, "H", n - 150, n), pivots(l, 5, "L", n - 150, n)
    pat, pname = candle_pattern(a, p)
    tol = 0.1 * a.atr
    if a.ema50 > a.ema200 and ph:
        ih = ph[-1]
        lows = [i for i in pl if i < ih]
        if lows and n - 1 - ih <= 60:
            H, L = h[ih], l[lows[-1]]
            leg = H - L
            z_hi, z_lo, inv = H - 0.5 * leg, H - 0.618 * leg, H - 0.786 * leg
            if leg >= 2 * a.atr and h[ih + 1:].max() <= H and l[ih:].min() >= inv - tol \
                    and a.Low <= z_hi + tol and a.Close >= z_lo - tol and a.Close > a.Open and a.Close < H:
                ratio = (H - a.Low) / leg * 100
                return _sig("fib_pullback", 1, 0.7 + (0.1 if pat == 1 else 0),
                            f"تصحيح فيبو {ratio:.0f}% من موجة صاعدة" + (f" + {pname}" if pat == 1 else ""), sl=inv)
    if a.ema50 < a.ema200 and pl:
        il = pl[-1]
        highs = [i for i in ph if i < il]
        if highs and n - 1 - il <= 60:
            H, L = h[highs[-1]], l[il]
            leg = H - L
            z_lo, z_hi, inv = L + 0.5 * leg, L + 0.618 * leg, L + 0.786 * leg
            if leg >= 2 * a.atr and l[il + 1:].min() >= L and h[il:].max() <= inv + tol \
                    and a.High >= z_lo - tol and a.Close <= z_hi + tol and a.Close < a.Open and a.Close > L:
                ratio = (a.High - L) / leg * 100
                return _sig("fib_pullback", -1, 0.7 + (0.1 if pat == -1 else 0),
                            f"تصحيح فيبو {ratio:.0f}% من موجة هابطة" + (f" + {pname}" if pat == -1 else ""), sl=inv)
    return None


def strat_rsi_divergence(x):
    """دايفرجنس عادي بين السعر وRSI على قمتين/قاعين مؤكدين، مع شمعة تأكيد."""
    n = len(x)
    a, p = x.iloc[-1], x.iloc[-2]
    h, l, r = x["High"].to_numpy(), x["Low"].to_numpy(), x["rsi"].to_numpy()
    pl, ph = pivots(l, 3, "L", n - 80, n), pivots(h, 3, "H", n - 80, n)
    if len(pl) >= 2:
        i1, i2 = pl[-2], pl[-1]
        if n - 1 - i2 <= 8 and i2 - i1 >= 5 and l[i2] < l[i1] and r[i2] > r[i1] + 2 and r[i1] < 40 \
                and l[i2:].min() >= l[i2] and a.Close > a.Open and a.rsi > p.rsi:
            return _sig("rsi_divergence", 1, 0.7 + (0.1 if r[i1] < 30 else 0),
                        f"دايفرجنس صاعد: قاع أدنى في السعر وRSI أعلى ({r[i1]:.0f}→{r[i2]:.0f})", sl=l[i2])
    if len(ph) >= 2:
        i1, i2 = ph[-2], ph[-1]
        if n - 1 - i2 <= 8 and i2 - i1 >= 5 and h[i2] > h[i1] and r[i2] < r[i1] - 2 and r[i1] > 60 \
                and h[i2:].max() <= h[i2] and a.Close < a.Open and a.rsi < p.rsi:
            return _sig("rsi_divergence", -1, 0.7 + (0.1 if r[i1] > 70 else 0),
                        f"دايفرجنس هابط: قمة أعلى في السعر وRSI أدنى ({r[i1]:.0f}→{r[i2]:.0f})", sl=h[i2])
    return None


def strat_session_breakout(x):
    """اختراق نطاق الجلسة الآسيوية (00:00-07:00 UTC) خلال لندن (07:00-11:00). لا يعمل على الكريبتو."""
    if x.attrs.get("kind") == "crypto":
        return None
    a = x.iloc[-1]
    ts = x.index[-1]
    if not 7 <= ts.hour < 11 or not a.atr > 0:
        return None
    day = ts.normalize()
    asia = x[(x.index >= day) & (x.index < day + pd.Timedelta(hours=7))]
    if len(asia) < 20:
        return None
    hi, lo = asia["High"].max(), asia["Low"].min()
    if not 2 * a.atr <= hi - lo <= 10 * a.atr:
        return None
    after = x[(x.index >= day + pd.Timedelta(hours=7)) & (x.index < ts)]
    bonus = 0.1 if a.adx > 20 else 0
    mid = (hi + lo) / 2
    if a.Close > hi and a.Close > a.Open and not (after["Close"] > hi).any():
        return _sig("session_breakout", 1, 0.7 + bonus, "أول إغلاق فوق نطاق آسيا خلال لندن", sl=mid)
    if a.Close < lo and a.Close < a.Open and not (after["Close"] < lo).any():
        return _sig("session_breakout", -1, 0.7 + bonus, "أول إغلاق تحت نطاق آسيا خلال لندن", sl=mid)
    return None


# (الاسم، الدالة، الوزن، النوع)
STRATEGIES: list[tuple[str, Callable, float, str]] = [
    ("ema_pullback", strat_ema_pullback, 1.2, "trend"),
    ("fib_pullback", strat_fib_pullback, 1.1, "trend"),
    ("supertrend_adx", strat_supertrend_adx, 1.0, "trend"),
    ("ichimoku", strat_ichimoku, 1.0, "trend"),
    ("donchian", strat_donchian, 0.9, "trend"),
    ("macd_cross", strat_macd_cross, 0.8, "trend"),
    ("squeeze_breakout", strat_squeeze_breakout, 1.0, "neutral"),
    ("session_breakout", strat_session_breakout, 0.9, "neutral"),
    ("rsi_bollinger", strat_rsi_bollinger, 1.0, "reversal"),
    ("sr_candle", strat_sr_candle, 1.1, "reversal"),
    ("rsi_divergence", strat_rsi_divergence, 1.0, "reversal"),
    ("stochastic", strat_stochastic, 0.7, "reversal"),
]

STRATEGY_INFO = {
    "ema_pullback": {
        "title": "ارتداد المتوسطات داخل اتجاه قائم", "regime": "اتجاه",
        "entry": ["شراء: EMA20 > EMA50 > EMA200 وميل EMA50 صاعد (مقارنة بقيمته قبل 5 شموع)",
                  "الشمعة لمست EMA20 (Low ≤ EMA20) وأغلقت فوقها بشمعة صاعدة",
                  "RSI بين 40 و65 (بيع: ترتيب معاكس وRSI بين 35 و60)",
                  "القوة 0.6، و+0.2 إذا ظهر ابتلاع أو مطرقة (للبيع: ابتلاع هابط أو نجمة)"],
        "stop": "أسفل أدنى الشمعتين الأخيرتين (للبيع: أعلى قمة)"},
    "fib_pullback": {
        "title": "تصحيح فيبوناتشي إلى المنطقة الذهبية", "regime": "اتجاه",
        "entry": ["اتجاه: EMA50 > EMA200 للشراء (العكس للبيع)",
                  "آخر موجة دافعة بين قاع وقمة مؤكدين (±5 شموع) حجمها ≥ 2 ATR وعمرها ≤ 60 شمعة",
                  "السعر عاد إلى منطقة 50%-61.8% (هامش 0.1 ATR) ولم يكسر مستوى 78.6%",
                  "شمعة صاعدة تغلق داخل المنطقة أو فوقها وتحت القمة؛ القوة 0.7 (+0.1 مع نمط شمعة)"],
        "stop": "عند مستوى 78.6% من الموجة"},
    "supertrend_adx": {
        "title": "انقلاب Supertrend مع قوة ADX", "regime": "اتجاه",
        "entry": ["Supertrend (10، 3.0) انقلب لأعلى خلال آخر 3 شموع وهو الآن صاعد",
                  "ADX > 20 و+DI > -DI (للبيع العكس)",
                  "القوة 0.6 + حتى 0.3 حسب ارتفاع ADX فوق 20"],
        "stop": "خط Supertrend"},
    "ichimoku": {
        "title": "إيشيموكو (سحابة + تقاطع)", "regime": "اتجاه",
        "entry": ["الإغلاق فوق السحابة (أعلى Span A/B) وSpan A > Span B",
                  "Tenkan > Kijun بعد تقاطع صاعد خلال آخر شمعتين",
                  "للبيع: كل شيء معكوس؛ القوة 0.75"],
        "stop": "خط Kijun"},
    "donchian": {
        "title": "اختراق قناة دونشيان 20", "regime": "اتجاه",
        "entry": ["الإغلاق فوق أعلى 20 شمعة سابقة (أو تحت أدنى 20 للبيع) بشمعة بنفس الاتجاه",
                  "ADX > 20؛ القوة 0.6 (+0.2 إذا الحجم > 1.2× متوسطه ويتوفر الحجم)"],
        "stop": "أدنى 10 شموع (للبيع أعلى 10)"},
    "macd_cross": {
        "title": "تقاطع هيستوغرام MACD", "regime": "اتجاه",
        "entry": ["الهيستوغرام ينتقل من ≤0 إلى >0 والإغلاق فوق EMA50 (للبيع العكس)",
                  "القوة 0.55 (+0.2 إذا حدث التقاطع تحت خط الصفر للشراء أو فوقه للبيع)"],
        "stop": "أدنى 10 شموع (للبيع أعلى 10)"},
    "squeeze_breakout": {
        "title": "اختراق بعد انضغاط البولنجر", "regime": "أي نظام",
        "entry": ["عرض البولنجر كان ≤ المئين 20 (آخر 100 شمعة) خلال آخر 6 شموع",
                  "إغلاق خارج الحزمة العلوية بشمعة صاعدة (أو السفلية بشمعة هابطة)",
                  "القوة 0.65 (+0.2 مع حجم مرتفع)"],
        "stop": "الخط الأوسط للبولنجر"},
    "session_breakout": {
        "title": "اختراق نطاق آسيا في جلسة لندن", "regime": "أي نظام (غير الكريبتو)",
        "entry": ["النطاق = أعلى/أدنى 00:00-07:00 UTC بعرض بين 2 و10 ATR (20 شمعة على الأقل)",
                  "بين 07:00 و11:00 UTC: أول إغلاق خارج النطاق بشمعة بنفس الاتجاه ولم يسبقه إغلاق خارجه",
                  "القوة 0.7 (+0.1 إذا ADX > 20)"],
        "stop": "منتصف نطاق آسيا"},
    "rsi_bollinger": {
        "title": "انعكاس البولنجر مع RSI", "regime": "عرضي",
        "entry": ["الشمعة السابقة أغلقت تحت الحزمة السفلية والحالية عادت فوقها بشمعة صاعدة",
                  "RSI < 35 في إحدى الشمعتين (للبيع: فوق الحزمة العلوية وRSI > 65)",
                  "القوة 0.7 (+0.15 إذا RSI يتحسن)"],
        "stop": "أدنى الشمعتين (للبيع أعلى قمة)"},
    "sr_candle": {
        "title": "شمعة انعكاسية عند دعم/مقاومة", "regime": "عرضي",
        "entry": ["نمط: ابتلاع أو مطرقة (شراء) / ابتلاع هابط أو نجمة رماية (بيع)",
                  "الدعم/المقاومة من قمم وقيعان مؤكدة آخر 120 شمعة، والمسافة ≤ 0.5 ATR",
                  "القوة 0.75"],
        "stop": "أدنى الشمعة (للبيع أعلاها)"},
    "rsi_divergence": {
        "title": "دايفرجنس RSI", "regime": "عرضي/نهاية اتجاه",
        "entry": ["قاعان مؤكدان (±3) بينهما ≥ 5 شموع: قاع السعر أدنى وقاع RSI أعلى بأكثر من 2 نقطة",
                  "RSI عند القاع الأول < 40 والقاع الثاني حدث خلال آخر 8 شموع ولم يُكسر",
                  "شمعة صاعدة وRSI يرتفع (للبيع العكس مع RSI > 60)؛ القوة 0.7 (+0.1 إذا RSI < 30 أو > 70)"],
        "stop": "قاع/قمة الدايفرجنس الثاني"},
    "stochastic": {
        "title": "تقاطع ستوكاستيك من التشبع", "regime": "عرضي",
        "entry": ["%K يعبر %D لأعلى بعد أن كان تحت 25 خلال آخر 3 شموع (للبيع: فوق 75)",
                  "القوة 0.55 (+0.15 إذا الشمعة بنفس الاتجاه)"],
        "stop": "أدنى 6 شموع (للبيع أعلى 6)"},
}


def regime_multiplier(regime: str, kind: str) -> float:
    if kind == "neutral" or regime == "mixed":
        return 1.0
    if regime == "trend":
        return 1.0 if kind == "trend" else 0.6
    return 1.0 if kind == "reversal" else 0.6   # range


def _wait(note: str, **extra) -> dict:
    return {"decision": "WAIT", "side": 0, "note": note, **extra}


def analyze(df: pd.DataFrame, spec: SymbolSpec) -> dict:
    """تحليل على شموع مغلقة فقط: فلاتر → استراتيجيات → تصويت مرجّح → وقف هيكلي → فحص التكلفة."""
    if len(df) < MIN_BARS:
        return _wait("بيانات غير كافية")
    x = compute_indicators(df)
    x.attrs["kind"] = spec.kind
    a = x.iloc[-1]
    if not a.atr > 0:
        return _wait("ATR غير صالح")
    vr = float(a.atr / a.atr_med) if a.atr_med > 0 else 1.0
    base = {"bar": str(df.index[-1]), "atr": float(a.atr), "vol_ratio": round(vr, 2)}
    if not in_liquid_hours(spec.kind, df.index[-1].to_pydatetime()):
        return _wait("خارج ساعات السيولة (توسع السبريد)", **base)
    if vr > 3:
        return _wait("تقلب مفرط (احتمال خبر) — انتظار الهدوء", **base)
    if vr < 0.4:
        return _wait("سوق هادئ جداً", **base)

    adx_v = float(a.adx)
    regime = "trend" if adx_v >= 25 else "range" if adx_v <= 18 else "mixed"
    htf = htf_direction(df)

    scores, counts, found = {1: 0.0, -1: 0.0}, {1: 0, -1: 0}, []
    signals = []
    for name, fn, weight, kind in STRATEGIES:
        if name in DISABLED_STRATEGIES:
            continue
        try:
            s = fn(x)
        except Exception:
            log.exception("strategy %s failed", name)
            continue
        if s is None:
            continue
        val = s.strength * weight * regime_multiplier(regime, kind)
        scores[s.side] += val
        counts[s.side] += 1
        found.append(s)
        signals.append({**asdict(s), "points": round(val, 2)})

    side = 1 if scores[1] >= scores[-1] else -1
    win, lose = scores[side], scores[-side]
    if htf == -side:
        win *= 0.75     # عقوبة للتداول ضد اتجاه الساعة

    res = {**base, "decision": "WAIT", "side": 0, "score": round(win, 2),
           "long_score": round(scores[1], 2), "short_score": round(scores[-1], 2),
           "regime": regime, "adx": round(adx_v, 1), "rsi": round(float(a.rsi), 1), "htf": htf,
           "signals": signals}
    if not (win >= MIN_SCORE and counts[side] >= MIN_STRATEGIES and win >= 2 * lose):
        return res

    # وقف هيكلي: وسيط مسافات الوقف المقترحة (+0.1 ATR) محصور بين 1 و2.5 ATR
    entry, atr_v = float(a.Close), float(a.atr)
    hints = [(entry - s.sl) * side + 0.1 * atr_v for s in found if s.side == side and s.sl is not None
             and (entry - s.sl) * side > 0]
    if hints:
        sl_dist, src = float(np.clip(np.median(hints), 1.0 * atr_v, 2.5 * atr_v)), "structure"
    else:
        sl_dist, src = ATR_SL_MULT * atr_v, "atr"
    cost = trade_cost(spec, entry)
    res.update({"sl_dist": sl_dist, "sl_source": src, "cost": cost})
    if cost > MAX_COST_RATIO * sl_dist:
        res["note"] = "التكلفة (سبريد/عمولة) مرتفعة نسبةً للوقف"
        return res
    res.update({"decision": "BUY" if side == 1 else "SELL", "side": side})
    return res


# ============================== إدارة الصفقات ورأس المال ==============================
def quote_to_usd(spec: SymbolSpec, price: float) -> float:
    """تحويل الربح المسعّر بعملة الاقتباس إلى دولار (USDJPY وUSDCAD يُقسمان على السعر)."""
    return 1.0 / price if spec.quote in ("jpy", "cad") else 1.0


def trade_cost(spec: SymbolSpec, price: float) -> float:
    """تكلفة الدورة الكاملة بوحدة السعر: السبريد + عمولة الدخول والخروج."""
    return spec.spread_pips * spec.pip + 2 * spec.fee_pct * price


def size_position(spec: SymbolSpec, balance: float, price: float, sl_dist: float,
                  risk_pct: Optional[float] = None) -> dict:
    """حجم الصفقة لرأس مال صغير: حسب المخاطرة، ثم سقف الهامش، ثم احترام أصغر عقد."""
    risk_pct = risk_pct or RISK_PCT
    q = quote_to_usd(spec, price)
    loss_per_lot = sl_dist * spec.units_per_lot * q            # خسارة 1.00 لوت عند ضرب الوقف (دولار)
    if loss_per_lot <= 0 or balance <= 0:
        return {"ok": False, "reason": "بيانات غير صالحة لحساب الحجم"}
    lev = 1.0 if spec.spot else LEVERAGE
    margin_per_lot = spec.units_per_lot * price * q / lev
    lots_risk = balance * risk_pct / 100 / loss_per_lot
    lots_margin = balance * MAX_MARGIN_PCT / 100 / margin_per_lot
    lots = math.floor(min(lots_risk, lots_margin) / spec.lot_step + 1e-9) * spec.lot_step
    if lots < spec.min_lot:
        if lots_margin < spec.min_lot:
            need = spec.min_lot * margin_per_lot / (MAX_MARGIN_PCT / 100)
            return {"ok": False, "reason": f"الهامش لا يكفي لأصغر عقد (يلزم رصيد ≈ ${need:.0f})"}
        min_risk = spec.min_lot * loss_per_lot
        if min_risk > balance * MAX_RISK_PCT / 100:
            return {"ok": False, "reason": f"أصغر عقد يخاطر بـ ${min_risk:.2f} ({min_risk / balance * 100:.1f}% > {MAX_RISK_PCT:g}%)"}
        lots = spec.min_lot
    lots = round(lots, 8)
    risk_usd = lots * loss_per_lot
    return {"ok": True, "lots": lots, "risk_usd": round(risk_usd, 2),
            "risk_pct": round(risk_usd / balance * 100, 2),
            "margin_usd": round(lots * margin_per_lot, 2),
            "notional_usd": round(lots * spec.units_per_lot * price * q, 2)}


@dataclass
class Trade:
    symbol: str
    side: int
    entry: float
    sl: float
    tp: float
    risk: float                 # بعد الوقف الأولي (وحدة السعر)
    opened_at: str
    strategies: list = field(default_factory=list)
    score: float = 0.0
    status: str = "OPEN"        # OPEN | CLOSED
    result: Optional[str] = None
    exit_price: Optional[float] = None
    closed_at: Optional[str] = None
    max_r: float = 0.0
    pnl_r: float = 0.0
    pnl_pips: float = 0.0
    pnl_usd: float = 0.0
    checked_until: Optional[str] = None
    cost: float = 0.0           # سبريد + عمولات بوحدة السعر
    lots: float = 0.0
    usd_factor: float = 0.0     # دولار لكل 1.0 وحدة سعر لهذا الحجم
    risk_usd: float = 0.0
    margin_usd: float = 0.0
    sl_source: str = "atr"

    @classmethod
    def open(cls, symbol, side, entry, sl_dist, rr, strategies, score, opened_at,
             cost=0.0, lots=0.0, usd_factor=0.0, risk_usd=0.0, margin_usd=0.0, sl_source="atr"):
        return cls(symbol=symbol, side=side, entry=entry, sl=entry - side * sl_dist,
                   tp=entry + side * sl_dist * rr, risk=sl_dist, opened_at=opened_at,
                   strategies=strategies, score=score, cost=cost, lots=lots, usd_factor=usd_factor,
                   risk_usd=risk_usd, margin_usd=margin_usd, sl_source=sl_source)

    def _close(self, price: float, label: Optional[str], pip: float, when: str):
        self.status, self.exit_price, self.closed_at = "CLOSED", price, when
        move = (price - self.entry) * self.side - self.cost       # صافي بعد التكلفة
        self.pnl_r = round(move / self.risk, 2)
        self.pnl_pips = round(move / pip, 1)
        self.pnl_usd = round(move * self.usd_factor, 2)
        self.result = label or ("SL" if self.pnl_r < -0.1 else "BE" if abs(self.pnl_r) <= 0.1 else "TRAIL")

    def step(self, high: float, low: float, pip: float, when: str) -> bool:
        """يطبق شمعة (أو سعراً لحظياً high=low). SL قبل TP عند التعارض. يعيد True إذا أُغلقت."""
        if self.status != "OPEN":
            return False
        s = self.side
        hit_sl = low <= self.sl if s == 1 else high >= self.sl
        hit_tp = high >= self.tp if s == 1 else low <= self.tp
        if hit_sl:
            self._close(self.sl, None, pip, when)
            return True
        if hit_tp:
            self._close(self.tp, "TP", pip, when)
            return True
        best = high if s == 1 else low
        self.max_r = max(self.max_r, (best - self.entry) * s / self.risk)
        lock = None
        if self.max_r >= 1.5:
            lock = self.max_r - 1.0        # وقف متحرك: مسافة 1R من أفضل سعر
        elif self.max_r >= 1.0:
            lock = 0.0                     # تعادل
        if lock is not None:
            new_sl = self.entry + s * lock * self.risk
            self.sl = max(self.sl, new_sl) if s == 1 else min(self.sl, new_sl)
        return False


class Account:
    """حساب ورقي يتتبع الرصيد لو نفّذت كل الإشارات، مع حدود يومية لحماية رأس المال الصغير."""

    def __init__(self, start: float, path: str):
        self.path, self.start, self.balance = path, start, start
        self.day, self.day_start, self.consec = self._today(), start, 0
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if abs(float(d["start"]) - start) < 1e-9:       # تغيير ACCOUNT_BALANCE يصفّر الحساب
                self.balance, self.day = float(d["balance"]), d["day"]
                self.day_start, self.consec = float(d["day_start"]), int(d["consec"])
        except (FileNotFoundError, ValueError, KeyError):
            pass

    @staticmethod
    def _today() -> str:
        return datetime.utcnow().strftime("%Y-%m-%d")

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f)
        except OSError:
            log.exception("cannot save account")

    def _roll(self):
        if self._today() != self.day:
            self.day, self.day_start, self.consec = self._today(), self.balance, 0
            self._save()

    def can_trade(self):
        self._roll()
        if self.balance <= 0:
            return False, "الرصيد صفر"
        if self.day_start - self.balance >= DAILY_LOSS_LIMIT_PCT / 100 * self.day_start:
            return False, "بلغت حد الخسارة اليومي"
        if self.consec >= MAX_CONSEC_LOSSES:
            return False, "توقف مؤقت بعد خسائر متتالية"
        return True, ""

    def record(self, pnl_usd: float):
        self._roll()
        self.balance = round(self.balance + pnl_usd, 2)
        if pnl_usd < 0:
            self.consec += 1
        elif pnl_usd > 0:
            self.consec = 0
        self._save()

    def to_dict(self) -> dict:
        return {"start": self.start, "balance": self.balance, "day": self.day,
                "day_start": self.day_start, "consec": self.consec}


# ============================== مصادر البيانات ==============================
def clean_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    df = df[["Open", "High", "Low", "Close", "Volume"]].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    df["Volume"] = df["Volume"].fillna(0)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[(df[["Open", "High", "Low", "Close"]] > 0).all(axis=1)].copy()
    ohlc = df[["Open", "High", "Low", "Close"]]
    df["High"], df["Low"] = ohlc.max(axis=1), ohlc.min(axis=1)
    rng = df["High"] - df["Low"]
    med = rng.rolling(50, min_periods=10).median().replace(0, np.nan)
    return df[~(rng > 15 * med)]      # حذف أخطاء البيانات فقط، لا الحركات القوية


class DataProvider:
    def __init__(self):
        self.okx = ccxt_async.okx({"enableRateLimit": True})
        self.tv = None
        self.tv_lock = asyncio.Lock()

    async def close(self):
        await self.okx.close()

    async def fetch(self, symbol: str, spec: SymbolSpec, bars: int = 300):
        try:
            if spec.kind == "crypto":
                df = await self._okx(symbol, bars)
                if df is not None:
                    return df, f"OKX {symbol}"
            else:
                if TV_AVAILABLE and spec.tv:
                    df = await self._tv(spec, bars)
                    if df is not None:
                        return df, f"TradingView {spec.tv[1]}"
                if YF_AVAILABLE and spec.yf:
                    df = await self._yf(spec, bars)
                    if df is not None:
                        return df, f"Yahoo {spec.yf}"
        except Exception:
            log.exception("fetch %s failed", symbol)
        return None, "none"

    async def _okx(self, symbol, bars):
        sym = symbol.replace("USDT", "/USDT")
        if bars <= 300:
            raw = await self.okx.fetch_ohlcv(sym, "15m", limit=bars)
        else:   # تجميع صفحات للباك تست (best-effort)
            raw, ms = [], BAR_MINUTES * 60 * 1000
            since = int(time.time() * 1000) - bars * ms
            for _ in range(bars // 100 + 5):
                chunk = await self.okx.fetch_ohlcv(sym, "15m", since=since, limit=100)
                if not chunk:
                    break
                raw += chunk
                since = chunk[-1][0] + ms
                if since > time.time() * 1000:
                    break
        if not raw:
            return None
        df = pd.DataFrame(raw, columns=["time", "Open", "High", "Low", "Close", "Volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        df = clean_ohlc(df.set_index("time")).tail(bars)
        return df if len(df) >= 100 else None

    async def _tv(self, spec, bars):
        async with self.tv_lock:
            def work():
                if self.tv is None:
                    self.tv = TvDatafeed()
                return self.tv.get_hist(symbol=spec.tv[1], exchange=spec.tv[0],
                                        interval=Interval.in_15_minute, n_bars=bars)
            hist = await asyncio.to_thread(work)
        if hist is None or hist.empty:
            return None
        hist = hist.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
        df = clean_ohlc(hist).tail(bars)
        return df if len(df) >= 100 else None

    async def _yf(self, spec, bars):
        def work():
            return yf.download(spec.yf, period="30d" if bars > 800 else "10d", interval="15m",
                               progress=False, auto_adjust=False)
        d = await asyncio.to_thread(work)
        if d is None or d.empty:
            return None
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        if d.index.tz is not None:
            d.index = d.index.tz_convert("UTC").tz_localize(None)
        df = clean_ohlc(d).tail(bars)
        return df if len(df) >= 100 else None


# ============================== التليغرام ==============================
class Telegram:
    def __init__(self, token: str, path: str):
        self.token, self.path = token, path
        self.subs: set[int] = set()
        self.offset = 0
        self.client: Optional[httpx.AsyncClient] = None
        try:
            with open(path, encoding="utf-8") as f:
                self.subs = set(int(i) for i in json.load(f))
        except (FileNotFoundError, ValueError):
            pass

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(sorted(self.subs), f)
        except OSError:
            log.exception("cannot save subscribers")

    async def _api(self, method: str, **payload):
        r = await self.client.post(f"https://api.telegram.org/bot{self.token}/{method}", json=payload, timeout=40)
        return r.json()

    async def send(self, chat_id: int, text: str) -> bool:
        try:
            res = await self._api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                                  disable_web_page_preview=True)
            if not res.get("ok") and res.get("error_code") == 403:   # المستخدم حظر البوت
                self.subs.discard(chat_id)
                self._save()
            return bool(res.get("ok"))
        except Exception:
            log.exception("telegram send failed")
            return False

    async def broadcast(self, text: str) -> int:
        if not self.enabled:
            return 0
        sent = 0
        for cid in list(self.subs | ADMIN_CHAT_IDS):
            sent += await self.send(cid, text)
        return sent

    async def poll_loop(self, status_fn: Callable[[str], str]):
        while True:
            try:
                res = await self._api("getUpdates", offset=self.offset, timeout=25)
                if not res.get("ok"):
                    log.error("telegram getUpdates: %s", res)
                    await asyncio.sleep(15)
                    continue
                for u in res["result"]:
                    self.offset = u["update_id"] + 1
                    msg = u.get("message") or {}
                    text = (msg.get("text") or "").strip()
                    chat = (msg.get("chat") or {}).get("id")
                    if not text or chat is None:
                        continue
                    cmd = text.split()[0].lower().split("@")[0]
                    if cmd == "/start":
                        self.subs.add(chat)
                        self._save()
                        await self.send(chat, "✅ تم الاشتراك في الإشارات.\n/stop إلغاء • /status الحالة • /trades الصفقات")
                    elif cmd == "/stop":
                        self.subs.discard(chat)
                        self._save()
                        await self.send(chat, "تم إلغاء الاشتراك.")
                    elif cmd in ("/status", "/trades"):
                        await self.send(chat, status_fn(cmd))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("telegram poll error")
                await asyncio.sleep(10)


# ============================== المحرك ==============================
def fmt(v: float, spec: SymbolSpec) -> str:
    return f"{v:.{spec.decimals}f}"


def size_label(symbol: str, spec: SymbolSpec, lots: float) -> str:
    return f"{lots:g} {symbol.replace('USDT', '')}" if spec.kind == "crypto" else f"{lots:g} لوت"


class MarketEngine:
    def __init__(self, symbol: str, spec: SymbolSpec):
        self.symbol, self.spec = symbol, spec
        self.df: Optional[pd.DataFrame] = None
        self.source, self.data_ok, self.note = "—", False, "لم تُجلب بيانات بعد"
        self.last_fetch = 0.0
        self.trade: Optional[Trade] = None
        self.history: deque = deque(maxlen=100)
        self.analysis: Optional[dict] = None
        self.last_bar = None
        self.cooldown_until: Optional[pd.Timestamp] = None

    @property
    def price(self) -> Optional[float]:
        return float(self.df["Close"].iloc[-1]) if self.df is not None else None

    async def refresh(self, provider: DataProvider):
        if time.time() - self.last_fetch < FETCH_INTERVAL:
            return
        self.last_fetch = time.time()
        df, src = await provider.fetch(self.symbol, self.spec)
        if df is None:
            self.data_ok, self.note = False, "فشل جلب البيانات الحقيقية"
            return
        self.df, self.source = df, src
        self.data_ok, self.note = True, "OK"
        if self.spec.kind == "crypto":    # فحص حداثة البيانات (UTC معروف للكريبتو)
            age = datetime.utcnow() - df.index[-1].to_pydatetime()
            if age > timedelta(minutes=BAR_MINUTES * 3):
                self.data_ok, self.note = False, "بيانات قديمة"

    async def process(self, notify: Callable):
        if self.df is None or not self.data_ok:
            return
        closed = self.df.iloc[:-1]
        price = self.price

        if self.trade and self.trade.status == "OPEN":
            await self._manage(closed, price, notify)

        if not is_market_open(self.spec.kind):
            self.note = "السوق مغلق"
            return
        self.note = "OK"
        bar = closed.index[-1]
        if bar == self.last_bar:
            return
        self.last_bar = bar
        self.analysis = a = analyze(closed, self.spec)
        if a["decision"] not in ("BUY", "SELL") or self.trade is not None:
            return
        if self.cooldown_until is not None and bar <= self.cooldown_until:
            a["skipped"] = "فترة انتظار بعد صفقة سابقة"
            return
        side = a["side"]
        if self.spec.spot and side == -1 and not ALLOW_SPOT_SHORT:
            a["skipped"] = "البيع المكشوف غير متاح على كريبتو السبوت"
            return
        ok, why = portfolio_can_open(self)
        if not ok:
            a["skipped"] = why
            return
        sz = size_position(self.spec, account.balance, price, a["sl_dist"])
        if not sz["ok"]:
            a["skipped"] = sz["reason"]
            return
        open_risk = sum(e.trade.risk_usd for e in engines.values() if e.trade)
        if open_risk + sz["risk_usd"] > account.balance * MAX_TOTAL_RISK_PCT / 100:
            a["skipped"] = "مجموع المخاطرة المفتوحة سيتجاوز الحد"
            return
        t = Trade.open(self.symbol, side, price, a["sl_dist"], RISK_REWARD,
                       [s["name"] for s in a["signals"] if s["side"] == side], a["score"],
                       datetime.utcnow().isoformat(timespec="seconds"), cost=a["cost"], lots=sz["lots"],
                       usd_factor=sz["lots"] * self.spec.units_per_lot * quote_to_usd(self.spec, price),
                       risk_usd=sz["risk_usd"], margin_usd=sz["margin_usd"], sl_source=a["sl_source"])
        t.checked_until = str(self.df.index[-1])
        self.trade = t
        await notify(self._signal_message(t, a))

    async def _manage(self, closed: pd.DataFrame, price: float, notify):
        t, pip = self.trade, self.spec.pip
        cu = pd.Timestamp(t.checked_until)
        done = False
        for ts, row in closed[closed.index > cu].iterrows():
            t.checked_until = str(ts)
            if t.step(float(row.High), float(row.Low), pip, str(ts)):
                done = True
                break
        if not done:
            done = t.step(price, price, pip, datetime.utcnow().isoformat(timespec="seconds"))
        if done:
            self.history.append(t)
            self.trade = None
            self.cooldown_until = closed.index[-1] + timedelta(minutes=BAR_MINUTES * COOLDOWN_BARS)
            account.record(t.pnl_usd)
            await notify(self._close_message(t))

    def _signal_message(self, t: Trade, a: dict) -> str:
        sp = self.spec
        icon, word = ("🟢", "شراء") if t.side == 1 else ("🔴", "بيع")
        htf = {1: "صاعد", -1: "هابط", 0: "محايد"}[a["htf"]]
        reasons = "\n".join(f"• {html.escape(s['reason'])}" for s in a["signals"] if s["side"] == t.side)
        src = "هيكلي" if t.sl_source == "structure" else "ATR"
        return (f"{icon} <b>{word} {self.symbol}</b>\n"
                f"الدخول: <code>{fmt(t.entry, sp)}</code>\n"
                f"الوقف: <code>{fmt(t.sl, sp)}</code> ({src})\n"
                f"الهدف: <code>{fmt(t.tp, sp)}</code>  (R:R 1:{RISK_REWARD:g})\n"
                f"الحجم: <b>{size_label(self.symbol, sp, t.lots)}</b> | المخاطرة: ${t.risk_usd} "
                f"({t.risk_usd / account.balance * 100:.1f}%) | الهامش: ${t.margin_usd}\n"
                f"النقاط: {a['score']} | السوق: {a['regime']} (ADX {a['adx']}) | 1H: {htf}\n\n{reasons}\n\n"
                f"<i>عند +1R حرّك الوقف للدخول، وبعد +1.5R تابع الوقف المتحرك.</i>")

    def _close_message(self, t: Trade) -> str:
        icon = "✅" if t.pnl_r > 0.1 else "❌" if t.pnl_r < -0.1 else "➖"
        return (f"{icon} <b>إغلاق {t.symbol}</b> ({t.result})\n"
                f"السعر: <code>{fmt(t.exit_price, self.spec)}</code>\n"
                f"النتيجة: {t.pnl_r:+.2f}R ({t.pnl_pips:+.1f} نقطة) = ${t.pnl_usd:+.2f}\n"
                f"الرصيد الورقي: ${account.balance:.2f}")

    def summary(self) -> dict:
        return {
            "symbol": self.symbol, "price": self.price, "source": self.source,
            "data_ok": self.data_ok, "note": self.note,
            "market_open": is_market_open(self.spec.kind),
            "analysis": self.analysis,
            "trade": asdict(self.trade) if self.trade else None,
        }


def portfolio_can_open(e: MarketEngine):
    ok, why = account.can_trade()
    if not ok:
        return False, why
    if sum(1 for x in engines.values() if x.trade) >= MAX_OPEN_TRADES:
        return False, "بلغ عدد الصفقات المفتوحة الحد الأقصى"
    for o in engines.values():
        if o is not e and o.trade and o.spec.group == e.spec.group:
            return False, f"رمز مرتبط ({o.symbol}) مفتوح بالفعل"
    return True, ""


# ============================== باك تست ==============================
def backtest(df: pd.DataFrame, symbol: str, spec: SymbolSpec, balance: float = ACCOUNT_BALANCE) -> dict:
    """نفس منطق التحليل الحي + السبريد والعمولة + حجم الصفقة لرأس مال صغير (تراكمي)."""
    trades: list[Trade] = []
    bal, skipped_cap = balance, 0
    i, n = MIN_BARS, len(df)
    while i < n - 1:
        res = analyze(df.iloc[:i + 1], spec)
        if res["decision"] not in ("BUY", "SELL") or (spec.spot and res["side"] == -1 and not ALLOW_SPOT_SHORT):
            i += 1
            continue
        entry = float(df["Open"].iloc[i + 1])
        sz = size_position(spec, bal, entry, res["sl_dist"])
        if not sz["ok"]:
            skipped_cap += 1
            i += 1
            continue
        t = Trade.open(symbol, res["side"], entry, res["sl_dist"], RISK_REWARD,
                       [s["name"] for s in res["signals"] if s["side"] == res["side"]], res["score"],
                       str(df.index[i + 1]), cost=res["cost"], lots=sz["lots"],
                       usd_factor=sz["lots"] * spec.units_per_lot * quote_to_usd(spec, entry),
                       risk_usd=sz["risk_usd"], margin_usd=sz["margin_usd"], sl_source=res["sl_source"])
        j, closed = i + 1, False
        while j < n:
            if t.step(float(df["High"].iloc[j]), float(df["Low"].iloc[j]), spec.pip, str(df.index[j])):
                closed = True
                break
            j += 1
        if not closed:
            break
        trades.append(t)
        bal = round(bal + t.pnl_usd, 2)
        i = j + COOLDOWN_BARS
    rs = [t.pnl_r for t in trades]
    wins, losses = [r for r in rs if r > 0], [r for r in rs if r < 0]
    equity = np.cumsum(rs) if rs else np.array([0.0])
    dd = float((np.maximum.accumulate(equity) - equity).max())
    by_strategy: dict[str, list] = {}
    for t in trades:
        for s in t.strategies:
            by_strategy.setdefault(s, []).append(t.pnl_r)
    return {
        "symbol": symbol, "bars": n, "trades": len(trades), "skipped_for_capital": skipped_cap,
        "win_rate_pct": round(100 * len(wins) / len(rs), 1) if rs else 0,
        "total_r": round(float(sum(rs)), 2),
        "avg_r": round(float(np.mean(rs)), 3) if rs else 0,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses else None,
        "max_drawdown_r": round(dd, 2),
        "start_balance": balance, "final_balance": bal,
        "return_pct": round((bal / balance - 1) * 100, 1),
        "by_strategy": {k: {"trades": len(v), "total_r": round(sum(v), 2)} for k, v in by_strategy.items()},
        "note": "يشمل السبريد والعمولة، ولا يشمل الانزلاق السعري. نتائج الماضي لا تضمن المستقبل.",
        "last_trades": [asdict(t) for t in trades[-10:]],
    }


# ============================== التطبيق ==============================
engines: dict[str, MarketEngine] = {s: MarketEngine(s, sp) for s, sp in SYMBOLS.items()}
telegram = Telegram(TELEGRAM_TOKEN, SUBSCRIBERS_FILE)
account = Account(ACCOUNT_BALANCE, ACCOUNT_FILE)


class State:
    provider: Optional[DataProvider] = None
    http: Optional[httpx.AsyncClient] = None


state = State()


async def notify(msg: str):
    await telegram.broadcast(msg)


def status_text(cmd: str) -> str:
    lines = [f"💰 الرصيد الورقي: ${account.balance:.2f}"]
    for e in engines.values():
        if cmd == "/trades":
            if e.trade:
                t = e.trade
                lines.append(f"{'🟢' if t.side == 1 else '🔴'} {e.symbol} {size_label(e.symbol, e.spec, t.lots)} "
                             f"@ {fmt(t.entry, e.spec)} | SL {fmt(t.sl, e.spec)} | TP {fmt(t.tp, e.spec)}")
        else:
            p = fmt(e.price, e.spec) if e.price else "—"
            d = e.analysis["decision"] if e.analysis else "—"
            lines.append(f"{e.symbol}: {p} | {d} | {e.note}")
    return "\n".join(lines)


async def engine_loop():
    while True:
        try:
            res = await asyncio.gather(*(e.refresh(state.provider) for e in engines.values()), return_exceptions=True)
            for r in res:
                if isinstance(r, Exception):
                    log.error("refresh error: %r", r)
            for e in engines.values():
                try:
                    await e.process(notify)
                except Exception:
                    log.exception("process %s failed", e.symbol)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("engine loop error")
        await asyncio.sleep(POLL_SECONDS)


async def keepalive_loop():
    """يمنع Render المجاني من إيقاف الخدمة بعد 15 دقيقة بلا زيارات (يستخدم الرابط العام)."""
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        return
    while True:
        await asyncio.sleep(600)
        try:
            await state.http.get(url.rstrip("/") + "/health", timeout=20)
        except Exception:
            log.warning("keepalive ping failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.provider = DataProvider()
    state.http = httpx.AsyncClient()
    telegram.client = state.http
    tasks = [asyncio.create_task(engine_loop()), asyncio.create_task(keepalive_loop())]
    if telegram.enabled:
        tasks.append(asyncio.create_task(telegram.poll_loop(status_text)))
    else:
        log.warning("TELEGRAM_TOKEN غير مضبوط: التليغرام معطّل")
    yield
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await state.provider.close()
    await state.http.aclose()


app = FastAPI(title="Zero Reversal Engine", version="48.1", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True, "symbols": len(engines), "subscribers": len(telegram.subs | ADMIN_CHAT_IDS)}


@app.get("/api/status")
async def api_status():
    return [e.summary() for e in engines.values()]


@app.get("/api/analyze/{symbol}")
async def api_analyze(symbol: str):
    e = engines.get(symbol.upper())
    if not e:
        raise HTTPException(404, "رمز غير معروف")
    return e.summary()


@app.get("/api/strategies")
async def api_strategies():
    return {
        "params": {"min_score": MIN_SCORE, "min_strategies": MIN_STRATEGIES, "risk_reward": RISK_REWARD,
                   "atr_sl_mult_fallback": ATR_SL_MULT, "max_cost_ratio": MAX_COST_RATIO},
        "filters": ["نظام السوق ADX: ≥25 اتجاه، ≤18 عرضي", "اتجاه 1H (EMA20/50): عقوبة 25% عند المعاكسة",
                    "تقلب ATR/وسيطه: رفض فوق 3× أو تحت 0.4×", "تجنب 21:00-24:00 UTC لغير الكريبتو",
                    "رفض إذا السبريد+العمولة > 20% من الوقف", "صفقة واحدة لكل مجموعة مرتبطة"],
        "strategies": [{"name": n, "weight": w, "kind": k, "enabled": n not in DISABLED_STRATEGIES,
                        **STRATEGY_INFO.get(n, {})} for n, _, w, k in STRATEGIES],
    }


@app.get("/api/account")
async def api_account():
    ok, why = account.can_trade()
    return {**account.to_dict(), "can_trade": ok, "reason": why,
            "limits": {"risk_pct": RISK_PCT, "max_risk_pct": MAX_RISK_PCT, "max_total_risk_pct": MAX_TOTAL_RISK_PCT,
                       "max_open_trades": MAX_OPEN_TRADES, "daily_loss_limit_pct": DAILY_LOSS_LIMIT_PCT,
                       "max_consecutive_losses": MAX_CONSEC_LOSSES, "leverage": LEVERAGE}}


@app.get("/api/capital")
async def api_capital(balance: float = Query(ACCOUNT_BALANCE, gt=0), risk_pct: float = Query(RISK_PCT, gt=0, le=5)):
    """أي الرموز يمكن تداولها برصيدك؟ حجم الصفقة والمخاطرة والهامش لوقف بحجم 1.5 ATR الحالي."""
    out = []
    for e in engines.values():
        if e.df is None:
            out.append({"symbol": e.symbol, "ok": False, "reason": "لا توجد بيانات بعد"})
            continue
        sl_dist = float(atr(e.df).iloc[-1]) * ATR_SL_MULT
        sz = size_position(e.spec, balance, e.price, sl_dist, risk_pct)
        out.append({"symbol": e.symbol, "price": e.price, "sl_pips": round(sl_dist / e.spec.pip, 1),
                    "spread_pips": e.spec.spread_pips, **sz})
    return out


@app.get("/api/trades")
async def api_trades():
    hist = [asdict(t) for e in engines.values() for t in e.history]
    rs = [t["pnl_r"] for t in hist]
    return {
        "open": [asdict(e.trade) for e in engines.values() if e.trade],
        "closed": hist[-50:],
        "stats": {"count": len(rs), "total_r": round(sum(rs), 2), "total_usd": round(sum(t["pnl_usd"] for t in hist), 2),
                  "win_rate_pct": round(100 * sum(r > 0 for r in rs) / len(rs), 1) if rs else 0},
    }


@app.get("/api/backtest/{symbol}")
async def api_backtest(symbol: str, bars: int = Query(1000, ge=300, le=3000),
                       balance: float = Query(ACCOUNT_BALANCE, gt=0)):
    symbol = symbol.upper()
    e = engines.get(symbol)
    if not e:
        raise HTTPException(404, "رمز غير معروف")
    df, src = await state.provider.fetch(symbol, e.spec, bars)
    if df is None:
        raise HTTPException(503, "تعذر جلب بيانات حقيقية للباك تست")
    result = await asyncio.to_thread(backtest, df, symbol, e.spec, balance)
    result["source"] = src
    return result


@app.get("/test-telegram")
async def test_telegram():
    if not telegram.enabled:
        raise HTTPException(503, "TELEGRAM_TOKEN غير مضبوط")
    sent = await telegram.broadcast("🚀 <b>النظام متصل!</b>\nرسالة تجريبية.")
    return {"status": "success" if sent else "no_subscribers", "sent": sent}


@app.get("/api/candles/{symbol}")
async def api_candles(symbol: str, limit: int = Query(200, ge=50, le=300)):
    e = engines.get(symbol.upper())
    if not e or e.df is None:
        raise HTTPException(404, "لا توجد بيانات لهذا الرمز بعد")
    x = compute_indicators(e.df).tail(limit)
    ts = [int(t.timestamp()) for t in x.index]

    def line(col):
        return [{"time": t, "value": float(v)} for t, v in zip(ts, x[col]) if v == v]

    candles = [{"time": t, "open": float(r.Open), "high": float(r.High), "low": float(r.Low), "close": float(r.Close)}
               for t, (_, r) in zip(ts, x.iterrows())]
    tr = e.trade
    return {"symbol": e.symbol, "decimals": e.spec.decimals, "candles": candles,
            "ema20": line("ema20"), "ema50": line("ema50"), "ema200": line("ema200"),
            "trade": {"side": tr.side, "entry": tr.entry, "sl": tr.sl, "tp": tr.tp} if tr else None}


CHART_PAGE = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__SYM__</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/lightweight-charts/4.1.3/lightweight-charts.standalone.production.min.js"></script>
<style>:root{color-scheme:light dark;--bg:#fff;--fg:#1a1a1a;--mut:#6b7280;--bd:#e5e7eb}
@media(prefers-color-scheme:dark){:root{--bg:#111318;--fg:#e8e8ea;--mut:#9aa0aa;--bd:#2a2e37}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}
header{display:flex;gap:12px;align-items:center;padding:10px 12px}a{color:inherit}.m{color:var(--mut)}
#c{height:calc(100vh - 90px);min-height:320px}</style></head><body>
<header><a href="/">← الرئيسية</a><b>__SYM__</b><span id="i" class="m"></span></header><div id="c"></div>
<script>
const dark=matchMedia('(prefers-color-scheme: dark)').matches;
const chart=LightweightCharts.createChart(document.getElementById('c'),{
 layout:{background:{color:dark?'#111318':'#ffffff'},textColor:dark?'#e8e8ea':'#1a1a1a'},
 grid:{vertLines:{color:dark?'#1f232b':'#f1f1f1'},horzLines:{color:dark?'#1f232b':'#f1f1f1'}},
 timeScale:{timeVisible:true,secondsVisible:false},autoSize:true});
const cs=chart.addCandlestickSeries({upColor:'#16a34a',downColor:'#dc2626',borderVisible:false,wickUpColor:'#16a34a',wickDownColor:'#dc2626'});
const l20=chart.addLineSeries({color:'#3b82f6',lineWidth:1,priceLineVisible:false});
const l50=chart.addLineSeries({color:'#f59e0b',lineWidth:1,priceLineVisible:false});
const l200=chart.addLineSeries({color:'#a855f7',lineWidth:2,priceLineVisible:false});
let lines=[],first=true;
async function load(){try{
 const d=await (await fetch('/api/candles/__SYM__')).json();
 cs.applyOptions({priceFormat:{type:'price',precision:d.decimals,minMove:Math.pow(10,-d.decimals)}});
 cs.setData(d.candles);l20.setData(d.ema20);l50.setData(d.ema50);l200.setData(d.ema200);
 lines.forEach(x=>cs.removePriceLine(x));lines=[];
 if(d.trade){const t=d.trade;
  [['دخول',t.entry,'#9ca3af'],['وقف',t.sl,'#dc2626'],['هدف',t.tp,'#16a34a']].forEach(([n,p,c])=>
   lines.push(cs.createPriceLine({price:p,color:c,lineWidth:2,lineStyle:2,title:n})));}
 document.getElementById('i').textContent=(d.trade?(d.trade.side==1?'صفقة شراء مفتوحة':'صفقة بيع مفتوحة'):'لا توجد صفقة')+' | EMA 20/50/200';
 if(first){chart.timeScale().fitContent();first=false;}
}catch(e){document.getElementById('i').textContent='لا توجد بيانات بعد'}}
load();setInterval(load,30000);
</script></body></html>"""


@app.get("/chart/{symbol}", response_class=HTMLResponse)
async def chart_page(symbol: str):
    sym = symbol.upper()
    if sym not in engines:
        raise HTTPException(404, "رمز غير معروف")
    return CHART_PAGE.replace("__SYM__", sym)


DASHBOARD = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Zero Reversal Engine</title>
<style>:root{color-scheme:light dark;--bg:#fff;--fg:#1a1a1a;--mut:#6b7280;--bd:#e5e7eb;--g:#16a34a;--r:#dc2626}
@media(prefers-color-scheme:dark){:root{--bg:#111318;--fg:#e8e8ea;--mut:#9aa0aa;--bd:#2a2e37}}
body{margin:0;padding:12px;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}
.w{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:620px}
th,td{padding:8px;border-bottom:1px solid var(--bd);text-align:right;white-space:nowrap}th{color:var(--mut);font-weight:500}
.b{color:var(--g);font-weight:600}.s{color:var(--r);font-weight:600}.m{color:var(--mut)}#acc{margin:6px 0 12px}</style></head><body>
<h3>Zero Reversal Engine</h3><div id="acc" class="m"></div><div class="w"><table><thead><tr><th>الرمز</th><th>السعر</th><th>القرار</th><th>النقاط</th>
<th>السوق</th><th>الصفقة</th><th>ملاحظة</th></tr></thead><tbody id="t"></tbody></table></div>
<script>
const cls=d=>d==='BUY'?'b':d==='SELL'?'s':'m';
async function load(){try{
const ac=await (await fetch('/api/account')).json();
document.getElementById('acc').textContent='الرصيد الورقي: $'+ac.balance.toFixed(2)+' | '+(ac.can_trade?'التداول مفعّل':ac.reason);
const d=await (await fetch('/api/status')).json();
document.getElementById('t').innerHTML=d.map(e=>{const a=e.analysis||{};const t=e.trade;
const note=a.skipped||a.note||e.note;
return `<tr><td><a href="/chart/${e.symbol}">${e.symbol} 📈</a></td><td>${e.price??'—'}</td><td class="${cls(a.decision)}">${a.decision??'—'}</td>
<td>${a.score??'—'}</td><td>${a.regime??'—'}</td>
<td>${t?(t.side==1?'شراء ':'بيع ')+t.lots+' @ '+t.entry.toFixed(4):'—'}</td><td class="m">${note}</td></tr>`}).join('')}catch(e){}}
load();setInterval(load,15000);
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD
