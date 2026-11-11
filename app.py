"""
Zero Reversal Engine v49.0 - وضع 4 ساعات (app.py)
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
BAR_FETCH = _i("BAR_FETCH", 600)                 # عدد الشموع المحمّلة (للعرض والتحليل)
CORE_CONFIRM = _i("CORE_CONFIRM", 2)             # أقل عدد استراتيجيات أساسية (ICT/SMC/إليوت/فني) تؤكد الاتجاه
SETUP_COUNTS = _b("SETUP_COUNTS", "1")           # 1: الإعداد المؤكد (قبل وصول السعر للمنطقة) يُحسب تأكيداً؛ 0: الإشارات المكتملة فقط
CORE_MIN_SIGNALS = _i("CORE_MIN_SIGNALS", 1)     # أقل عدد إشارات أساسية مكتملة (⚡) ضمن التأكيد، والباقي يمكن أن يكون إعداداً (◔)
SETUP_BONUS = _f("SETUP_BONUS", 0.35)            # نقاط إضافية لكل استراتيجية أساسية في وضع الإعداد
MIN_SL_ATR = _f("MIN_SL_ATR", 1.0)               # أصغر وقف (× ATR)
MAX_SL_ATR = _f("MAX_SL_ATR", 3.5)               # أكبر وقف (× ATR)
TIMEFRAME = os.environ.get("TIMEFRAME", "4h").strip().lower()      # 4h (الموصى به بعد الاختبار) | 1h | 15m
TF_MINUTES = {"15m": 15, "1h": 60, "4h": 240}.get(TIMEFRAME, 240)
BAR_MINUTES = TF_MINUTES
HTF_RULE = {"15m": "1h", "1h": "4h", "4h": "1D"}.get(TIMEFRAME, "1D")       # الإطار الأعلى لفلتر الاتجاه
HTF_MIN_BARS = {"15m": 220, "1h": 220, "4h": 340}.get(TIMEFRAME, 340)      # أقل شموع لحساب اتجاه الإطار الأعلى
MIN_SCORE = _f("MIN_SCORE", 1.0)             # أقل مجموع نقاط للإشارة
STRICT_SCORE = _f("STRICT_SCORE", 1.3)       # تحت هذا الحد تُقبل الإشارة فقط إذا وافق اتجاه 1H
MIN_STRATEGIES = _i("MIN_STRATEGIES", 1)     # أقل عدد استراتيجيات متفقة
HTF_HARD = _b("HTF_HARD", "1")               # إلزام اتفاق اتجاه الإطار الأعلى (يومي على 4H)
MIN_ADX = _f("MIN_ADX", 0)                  # أقل قوة اتجاه ADX
ATR_SL_MULT = _f("ATR_SL_MULT", 1.5)         # وقف احتياطي إذا لم تعطِ الاستراتيجيات وقفاً هيكلياً
RISK_REWARD = _f("RISK_REWARD", 3.0)
COOLDOWN_BARS = _i("COOLDOWN_BARS", 4)
MAX_COST_RATIO = _f("MAX_COST_RATIO", 0.35)  # السبريد+العمولة يجب ألا تتجاوز هذه النسبة من الوقف (يُوسَّع الوقف تلقائياً إن أمكن)
DISABLED_STRATEGIES = {s.strip() for s in os.environ.get("DISABLED_STRATEGIES", "").split(",") if s.strip()}

# --- رأس المال الصغير وإدارة المخاطر ---
ACCOUNT_BALANCE = _f("ACCOUNT_BALANCE", 10000)      # بالدولار
RISK_PCT = _f("RISK_PCT", 1.0)                    # المخاطرة المستهدفة لكل صفقة %
MAX_RISK_PCT = _f("MAX_RISK_PCT", 2.0)            # سقف المخاطرة إذا كان أصغر عقد أكبر من المستهدف
MAX_TOTAL_RISK_PCT = _f("MAX_TOTAL_RISK_PCT", 3.0)  # مجموع مخاطرة الصفقات المفتوحة
LEVERAGE = _f("LEVERAGE", 100)                    # رافعة وسيط الفوركس/المعادن
MAX_MARGIN_PCT = _f("MAX_MARGIN_PCT", 40)         # أقصى هامش مستخدم من الرصيد %
MAX_OPEN_TRADES = _i("MAX_OPEN_TRADES", 2)
DAILY_LOSS_LIMIT_PCT = _f("DAILY_LOSS_LIMIT_PCT", 3.0)
MAX_CONSEC_LOSSES = _i("MAX_CONSEC_LOSSES", 3)
ALLOW_SPOT_SHORT = _b("ALLOW_SPOT_SHORT", "1")    # إشارات البيع على الكريبتو (نفّذها عبر عقود/فيوتشرز)؛ ضعه 0 لو تتداول سبوت فقط
CRYPTO_FEE_PCT = _f("CRYPTO_FEE_PCT", 0.0005)     # عمولة كل جهة للكريبتو (0.0005 = 0.05%)


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
    "BTCUSDT": SymbolSpec("crypto", 1.0, 2, 1, 0.0001, 0.0001, 2, "crypto", spot=True, fee_pct=CRYPTO_FEE_PCT),
    "ETHUSDT": SymbolSpec("crypto", 0.1, 2, 1, 0.001, 0.001, 2, "crypto", spot=True, fee_pct=CRYPTO_FEE_PCT),
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
        h = df.resample(HTF_RULE).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
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
    zone: Optional[tuple] = None   # منطقة الدخول (أعلى، أدنى)


def _sig(name, side, strength, reason, sl=None, zone=None):
    sl = float(sl) if sl is not None and sl == sl else None
    zone = (float(max(zone)), float(min(zone))) if zone else None
    return Signal(name, side, round(min(float(strength), 1.0), 2), reason, sl, zone)


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


# ============================== الاستراتيجيات الأساسية الأربع (نسخة مصحّحة) ==============================
# كل استراتيجية تُكتب مرة للشراء وتُعكس للبيع بقلب الأسعار (side=-1)، فتبقى القواعد متناظرة تماماً.
def _ov():
    return {"zones": [], "lines": [], "points": []}


def _tm(x, i):
    return int(x.index[int(i)].timestamp())


def _px(v) -> str:
    return f"{float(v):.6g}"


def _zn(x, i0, p1, p2, label, side):
    return {"top": float(max(p1, p2)), "bottom": float(min(p1, p2)), "t0": _tm(x, i0), "label": label, "side": side}


def _ln(x, i0, price, label):
    return {"price": float(price), "t0": _tm(x, i0), "label": label}


def _pt(x, i, price, label):
    return {"time": _tm(x, i), "price": float(price), "label": label}


def _chk(lst):
    return [{"ok": bool(o), "text": t} for o, t in lst]


class _ScanCache(dict):
    """pandas ينسخ x.attrs (deepcopy) عند كل x["High"] / x.iloc[-1]؛ هذا الكاش يُرجع نفسه بدل النسخ
    حتى لا يتكرر نسخ النتائج مئات المرات في كل تحليل (وفي الباك تست)."""
    def __deepcopy__(self, memo):
        return self

    def __copy__(self):
        return self


def _memo(x, key, fn):
    cache = x.attrs.get("scans")
    if cache is None:
        cache = x.attrs["scans"] = _ScanCache()
    ck = (key, len(x), x.index[-1])        # المفتاح يشمل طول البيانات وآخر شمعة: لا تسرّب بين شرائح مختلفة
    if ck not in cache:
        if len(cache) > 64:
            cache.clear()
        cache[ck] = fn(x)
    return cache[ck]


def _arrays(x, side):
    """للشراء الأسعار كما هي. للبيع تُقلب (High=-Low ...) لنطبّق منطق الشراء نفسه."""
    if side == 1:
        return x["High"].to_numpy(), x["Low"].to_numpy(), x["Close"].to_numpy(), x["Open"].to_numpy()
    return -x["Low"].to_numpy(), -x["High"].to_numpy(), -x["Close"].to_numpy(), -x["Open"].to_numpy()


def _zigzag(hh, ll, w, lookback):
    n = len(hh)
    ph, pl = pivots(hh, w, "H", n - lookback, n), pivots(ll, w, "L", n - lookback, n)
    pts = sorted([(i, hh[i], "H") for i in ph] + [(i, ll[i], "L") for i in pl], key=lambda t: t[0])
    out = []
    for p in pts:
        if out and out[-1][2] == p[2]:
            if (p[2] == "H" and p[1] > out[-1][1]) or (p[2] == "L" and p[1] < out[-1][1]):
                out[-1] = p
        else:
            out.append(p)
    return out


# ---------------------------------------------------------------- ICT
def _ict_dir(x, side, in_kz):
    n = len(x)
    hh, ll, cc, oo = _arrays(x, side)
    atr_ = float(x["atr"].iloc[-1])
    P = lambda v: float(v) * side
    ov, chk = _ov(), []
    pl = pivots(ll, 3, "L", n - 90, n - 4)
    ph = pivots(hh, 3, "H", n - 90, n)
    s = q = None
    for si in range(n - 3, max(n - 16, 10), -1):          # أحدث سحب سيولة أولاً
        for qi in reversed(pl):
            # الذيل يخترق القاع بمقدار ملموس (≥ 0.1 ATR) والإغلاق يعود فوقه
            if qi < si - 3 and ll[si] < ll[qi] - 0.1 * atr_ and cc[si] > ll[qi]:
                s, q = si, qi
                break
        if s is not None:
            break
    if s is not None and ll[s:].min() < ll[s]:             # قاع السحب انكسر لاحقاً: الإعداد باطل
        s = q = None
    chk.append((s is not None, "سحب سيولة: كسر قاع سابق ثم إغلاق فوقه" if side == 1 else "سحب سيولة: كسر قمة سابقة ثم إغلاق تحتها"))
    jj = fvg = None
    zt = zb = None
    disp = fresh = disc = inz = legok = False
    if s is not None:
        ov["lines"].append(_ln(x, q, P(ll[q]), "سيولة سُحبت"))
        ov["points"].append(_pt(x, s, P(ll[s]), "Sweep"))
        prev = [i for i in ph if i < s]
        if prev:
            lvl = hh[prev[-1]]
            ov["lines"].append(_ln(x, prev[-1], P(lvl), "MSS"))
            # الكسر يجب أن يحدث قبل شمعة التأكيد الحالية
            jj = next((j for j in range(s + 1, n - 1) if cc[j] > lvl), None)
    chk.append((jj is not None, "كسر هيكل السوق (MSS) بعد السحب"))
    if jj is not None:
        disp = any(cc[k] - oo[k] >= 0.8 * atr_ for k in range(s, jj + 1))
        hi_, lo_ = hh[s:n - 1].max(), ll[s]               # قمة الموجة بدون شمعة التأكيد الحالية
        leg = hi_ - lo_
        legok = leg >= 1.5 * atr_
        zt, zb = hi_ - 0.62 * leg, hi_ - 0.79 * leg
        for k in range(max(s, 1), min(jj, n - 2) + 1):
            if ll[k + 1] > hh[k - 1]:
                fvg = (hh[k - 1], ll[k + 1], k - 1)
        fresh = n - 1 - jj <= 40
        disc = cc[-1] <= (hh[-100:].max() + ll[-100:].min()) / 2
        inz = ll[-1] <= zt and cc[-1] >= zb and cc[-1] > oo[-1]
        ov["zones"].append(_zn(x, jj, P(zt), P(zb), "OTE 62–79%", side))
        if fvg:
            ov["zones"].append(_zn(x, fvg[2], P(fvg[0]), P(fvg[1]), "FVG", side))
    chk += [(disp, "اندفاع (Displacement) بشمعة ≥ 0.8 ATR"),
            (legok and fresh, "موجة الاندفاع كافية الحجم وحديثة"),
            (disc, "السعر في منطقة الخصم (Discount)" if side == 1 else "السعر في منطقة العلاوة (Premium)"),
            (inz, "السعر داخل منطقة OTE بشمعة تأكيد"),
            (in_kz, "داخل نافذة التداول (Kill Zone: لندن/نيويورك)")]
    trigger = bool(s is not None and jj is not None and disp and legok and fresh and disc and inz and in_kz)
    ok2 = s is not None and jj is not None
    if trigger:
        txt = "سحب سيولة + MSS + عودة إلى OTE داخل نافذة التداول"
    elif s is None:
        txt = ""
    elif jj is None:
        txt = "تم سحب السيولة؛ بانتظار كسر الهيكل MSS"
    elif not (legok and fresh):
        txt = "MSS تحقق لكن موجة الاندفاع ضعيفة أو قديمة"
    elif not inz:
        txt = f"MSS مؤكد؛ منطقة OTE بين {_px(min(P(zt), P(zb)))} و{_px(max(P(zt), P(zb)))} — بانتظار عودة السعر"
    elif not in_kz:
        txt = "السعر في OTE لكن خارج نافذة التداول"
    else:
        txt = "السعر في OTE لكن ليس في منطقة الخصم/العلاوة الصحيحة"
    return {"side": side, "stage": sum(bool(o) for o, _ in chk), "trigger": trigger, "ok2": ok2, "overlay": ov,
            "checks": chk, "sl": P(ll[s]) if s is not None else None,
            "zone": (P(zt), P(zb)) if zt is not None else None,
            "fvg_overlap": bool(fvg and zt is not None and fvg[0] < zt and fvg[1] > zb), "text": txt}


def _scan_ict(x):
    kind, ts = x.attrs.get("kind"), x.index[-1]
    in_kz = kind == "crypto" or 7 <= ts.hour < 11 or 12 <= ts.hour < 16
    rs = [_ict_dir(x, sd, in_kz) for sd in (1, -1)]
    best = max(rs, key=lambda d: (d["trigger"], d["stage"]))
    sig = None
    if best["trigger"]:
        sig = _sig("ict", best["side"], 0.8 + (0.1 if best["fvg_overlap"] else 0),
                   "ICT: سحب سيولة + MSS + عودة إلى OTE" + (" مع FVG" if best["fvg_overlap"] else ""),
                   sl=best["sl"], zone=best["zone"])
    return {"bias": best["side"] if best["ok2"] else 0, "text": best["text"] or "لا إعداد ICT: لا سحب سيولة حديث",
            "signal": sig, "overlay": best["overlay"] if best["stage"] >= 1 else _ov(), "checks": _chk(best["checks"]),
            "sl": best["sl"], "zone": best["zone"]}


# ---------------------------------------------------------------- SMC
def _smc_dir(x, side):
    n = len(x)
    hh, ll, cc, oo = _arrays(x, side)
    a = x.iloc[-1]
    atr_ = float(a.atr)
    P = lambda v: float(v) * side
    ov = _ov()
    ph = pivots(hh, 4, "H", n - 130, n - 3)
    ih = j = None
    for cand in reversed(ph):                              # أحدث قمة انكسرت خلال آخر 60 شمعة
        jb = next((t for t in range(cand + 1, n) if cc[t] > hh[cand]), None)
        if jb is not None and n - 1 - jb <= 60:
            ih, j = cand, jb
            break
    choch = bool(ih is not None and (a.ema50 - a.ema200) * side <= 0)
    name = "CHoCH" if choch else "BOS"
    ob = None
    ztop = zbot = None
    disp = unmit = disc = ret = fvg = first = sizeok = False
    if ih is not None:
        k = ih + int(np.argmin(ll[ih:j + 1]))
        ov["lines"].append(_ln(x, ih, P(hh[ih]), name))
        ov["points"].append(_pt(x, j, P(cc[j]), name))
        ob = next((m for m in range(k, max(k - 6, 0), -1) if cc[m] < oo[m]), None)
        if ob is not None:
            ztop, zbot = hh[ob], ll[ob]
            sizeok = 0.2 * atr_ <= ztop - zbot <= 3 * atr_
            disp = (hh[k:j + 1].max() - ll[k]) >= 2.0 * atr_
            unmit = bool((cc[j:] > zbot).all())
            fvg = any(ll[t + 1] > hh[t - 1] for t in range(max(k + 1, 1), j))
            disc = cc[-1] <= (hh[-100:].max() + ll[-100:].min()) / 2
            first = bool(j + 1 >= n - 1 or ll[j + 1:n - 1].min() > ztop)
            ret = j < n - 1 and ll[-1] <= ztop and cc[-1] > zbot and cc[-1] > oo[-1] and n - 1 - ob <= 90
            ov["zones"].append(_zn(x, ob, P(ztop), P(zbot), "Order Block", side))
    word = "صاعد" if side == 1 else "هابط"
    chk = [(ih is not None, f"كسر هيكل {word}: إغلاق {'فوق قمة' if side == 1 else 'تحت قاع'} سابق (BOS/CHoCH)"),
           (ob is not None, "كتلة أوامر (OB): آخر شمعة معاكسة قبل الاندفاع"),
           (disp and sizeok, "اندفاع قوي (≥ 2 ATR) وحجم الكتلة مناسب"),
           (unmit, "الكتلة لم تُستهلك (لا إغلاق خلفها)"),
           (disc, "السعر في منطقة الخصم" if side == 1 else "السعر في منطقة العلاوة"),
           (ret, "عودة السعر إلى الكتلة بشمعة تأكيد")]
    trigger = bool(ih is not None and ob is not None and sizeok and disp and unmit and disc and ret)
    if trigger:
        txt = f"{name} {word} + ارتداد من Order Block" + (" (أول لمسة)" if first else "")
    elif ih is None:
        txt = ""
    elif ob is None:
        txt = "كُسر الهيكل لكن لا توجد كتلة أوامر واضحة"
    elif not (disp and sizeok):
        txt = "الاندفاع ضعيف أو حجم الكتلة غير مناسب"
    elif not unmit:
        txt = "كتلة الأوامر استُهلكت (أُغلق السعر خلفها)"
    elif not ret:
        txt = f"OB {word} بين {_px(min(P(ztop), P(zbot)))} و{_px(max(P(ztop), P(zbot)))} — بانتظار عودة السعر إليه"
    else:
        txt = "السعر في الكتلة لكن ليس في منطقة الخصم/العلاوة الصحيحة"
    return {"side": side, "stage": sum(bool(o) for o, _ in chk), "trigger": trigger, "ok2": ih is not None and ob is not None,
            "overlay": ov, "checks": chk, "sl": P(zbot) if zbot is not None else None,
            "zone": (P(ztop), P(zbot)) if ztop is not None else None, "first": first, "fvg": bool(fvg), "name": name, "text": txt}


def _scan_smc(x):
    rs = [_smc_dir(x, sd) for sd in (1, -1)]
    best = max(rs, key=lambda d: (d["trigger"], d["stage"]))
    sig = None
    if best["trigger"]:
        sig = _sig("smc", best["side"], 0.75 + (0.1 if best["first"] else 0) + (0.05 if best["fvg"] else 0),
                   f"SMC: {best['name']} + ارتداد من Order Block" + (" (أول لمسة)" if best["first"] else ""),
                   sl=best["sl"], zone=best["zone"])
    return {"bias": best["side"] if best["ok2"] else 0, "text": best["text"] or "لا كسر هيكل حديث (BOS/CHoCH)",
            "signal": sig, "overlay": best["overlay"] if best["stage"] >= 1 else _ov(), "checks": _chk(best["checks"]),
            "sl": best["sl"], "zone": best["zone"]}


# ---------------------------------------------------------------- موجات إليوت
def _ell_dir(x, side):
    n = len(x)
    hh, ll, cc, oo = _arrays(x, side)
    a = x.iloc[-1]
    atr_ = float(a.atr)
    P = lambda v: float(v) * side
    zz = _zigzag(hh, ll, 4, 300)
    types = lambda m: [p[2] for p in zz[-m:]]
    pat = None
    if len(zz) >= 5 and types(5) == ["L", "H", "L", "H", "L"]:        # شكل الموجة 5 (محاور 0..4)
        p0, p1, p2, p3, p4 = zz[-5:]
        w1, w3 = p1[1] - p0[1], p3[1] - p2[1]
        r4 = (p3[1] - p4[1]) / w3 if w3 > 0 else 9
        if w1 >= 2 * atr_ and p2[1] > p0[1] and p4[1] > p1[1] and w3 >= w1 and 0.236 <= r4 <= 0.5:
            pat = ("w5", zz[-5:], r4)
    if pat is None and len(zz) >= 3 and types(3) == ["L", "H", "L"]:   # شكل الموجة 3 (محاور 0..2)
        p0, p1, p2 = zz[-3:]
        w1 = p1[1] - p0[1]
        r2 = (p1[1] - p2[1]) / w1 if w1 > 0 else 9
        if w1 >= 2 * atr_ and p2[1] > p0[1] and 0.382 <= r2 <= 0.786:
            pat = ("w3", zz[-3:], r2)
    ov = _ov()
    chk = [(pat is not None, "عدّ صالح: موجات 1-2 (أو 1-4) تحقق قواعد إليوت الثلاث")]
    trigger = False
    sl = tgt = r = None
    label = kind_ = ""
    word = "صاعدة" if side == 1 else "هابطة"
    if pat:
        kind_, pts, r = pat
        li, lp = pts[-1][0], pts[-1][1]
        w1 = pts[1][1] - pts[0][1]
        if kind_ == "w3":
            tgt, lim, label = lp + 1.618 * w1, pts[1][1] + 1.0 * atr_, "الموجة 3"
        else:
            tgt, lim, label = lp + w1, pts[3][1], "الموجة 5"
        recent = n - 1 - li <= 30
        no_ll = ll[li:].min() >= lp
        turn = cc[-1] > oo[-1] and (a.Close - a.ema20) * side > 0
        mom = (a.macd_hist - x["macd_hist"].iloc[-2]) * side > 0
        within = cc[-1] <= lim
        trigger = bool(recent and no_ll and turn and mom and within)
        chk += [(recent and no_ll, "آخر محور حديث (≤ 30 شمعة) ولم يُكسر"),
                (turn, "شمعة تأكيد واتجاه السعر مع EMA20"),
                (mom, "زخم MACD يتحسن باتجاه الموجة"),
                (within, "السعر لم يتجاوز نهاية الموجة السابقة")]
        for idx, p in enumerate(pts):
            ov["points"].append(_pt(x, p[0], P(p[1]), str(idx)))
        sl = P(lp)
        ov["lines"].append(_ln(x, li, P(tgt), f"هدف {label}"))
        ov["lines"].append(_ln(x, li, P(lp), "إبطال العدّ"))
    if trigger:
        txt = f"انطلاق {label} {word} بعد تصحيح {r * 100:.0f}% — هدف تقريبي {_px(P(tgt))}"
    elif pat:
        txt = f"عدّ محتمل: موجات {'1-2' if kind_ == 'w3' else '1-4'} {word} (تصحيح {r * 100:.0f}%)؛ بانتظار انطلاق {label}"
    else:
        txt = ""
    strength = 0.65 if pat and pat[0] == "w5" else 0.75 + (0.1 if pat and 0.5 <= pat[2] <= 0.618 else 0)
    return {"side": side, "stage": sum(bool(o) for o, _ in chk), "trigger": trigger, "ok2": pat is not None,
            "overlay": ov, "checks": chk, "sl": sl, "text": txt, "strength": strength, "txt_sig": txt,
            "tgt": (P(tgt) if tgt is not None else None)}


def _scan_elliott(x):
    rs = [_ell_dir(x, sd) for sd in (1, -1)]
    best = max(rs, key=lambda d: (d["trigger"], d["ok2"], d["stage"]))
    sig = _sig("elliott", best["side"], best["strength"], "إليوت: " + best["txt_sig"], sl=best["sl"]) if best["trigger"] else None
    return {"bias": best["side"] if best["ok2"] else 0,
            "text": best["text"] or "لا عدّ إليوت صالح حالياً: آخر المحاور لا تحقق قواعد الموجة 1-2",
            "signal": sig, "overlay": best["overlay"], "checks": _chk(best["checks"]),
            "sl": best["sl"], "tgt": best.get("tgt")}


# ---------------------------------------------------------------- التحليل الفني الكلاسيكي
def _tech_dir(x, side):
    n = len(x)
    hh, ll, cc, oo = _arrays(x, side)
    a, p = x.iloc[-1], x.iloc[-2]
    atr_ = float(a.atr)
    P = lambda v: float(v) * side
    trend = bool((a.ema20 - a.ema50) * side > 0 and (a.Close - a.ema50) * side > 0
                 and (a.ema50 - x["ema50"].iloc[-6]) * side > 0)
    mom = bool(a.macd_hist * side > 0 and 0 < (a.rsi - 50) * side <= 22)
    stren = bool(a.adx >= 20 and (a.pdi - a.mdi) * side > 0)
    pat, pname = candle_pattern(a, p)
    sup, res = swing_levels(x)
    lvls = sup if side == 1 else res
    edge = a.Low if side == 1 else a.High
    near = abs(edge - a.ema20) <= 0.6 * atr_ or any(abs(edge - s) <= 0.5 * atr_ for s in lvls)
    trig_a = bool(pat == side and near)
    ov = _ov()
    ph = pivots(hh, 4, "H", n - 60, n - 3)
    retest, lvl = False, None
    for cand in reversed(ph):                              # كسر ثم إعادة اختبار
        b = next((t for t in range(cand + 1, n - 1) if cc[t] > hh[cand]), None)
        if b is not None and n - 1 - b <= 15:
            lvl = hh[cand]
            retest = bool(ll[-1] <= lvl + 0.5 * atr_ and cc[-1] > lvl and cc[-1] > oo[-1])
            ov["lines"].append(_ln(x, cand, P(lvl), "مستوى الكسر/إعادة الاختبار"))
            break
    near_lv = [v for v in lvls if (v - a.Close) * side <= 0]
    if near_lv:
        v = max(near_lv) if side == 1 else min(near_lv)
        ov["lines"].append(_ln(x, max(0, n - 120), v, "دعم" if side == 1 else "مقاومة"))
    trig = trig_a or retest
    word = "صاعد" if side == 1 else "هابط"
    chk = [(trend, f"الاتجاه {word}: EMA20/EMA50 والسعر وميل EMA50"),
           (mom, "الزخم: MACD وRSI بين 50 و72 باتجاه الصفقة" if side == 1 else "الزخم: MACD وRSI بين 28 و50 باتجاه الصفقة"),
           (stren, "قوة الاتجاه: ADX ≥ 20 وDI باتجاه الصفقة"),
           (trig, "محفز الدخول: شمعة انعكاسية عند دعم/متوسط أو كسر + إعادة اختبار")]
    ok = bool(trend and mom and stren and trig)
    sl = (x["Low"].iloc[-8:].min() if side == 1 else x["High"].iloc[-8:].max())
    strength = 0.7 + (0.1 if (trig_a and retest) else 0) + (0.1 if a.adx >= 25 else 0)
    short = ["الاتجاه", "الزخم", "قوة ADX", "المحفز"]
    txt = "؛ ".join(f"{'✓' if o else '✗'} {nm}" for (o, _), nm in zip(chk, short)) + f" ({word})"
    return {"side": side, "stage": sum(bool(o) for o, _ in chk), "trigger": ok, "trend": trend, "overlay": ov,
            "checks": chk, "sl": float(sl), "strength": strength, "text": txt,
            "pname": pname if trig_a else "كسر وإعادة اختبار"}


def _scan_tech(x):
    rs = [_tech_dir(x, sd) for sd in (1, -1)]
    # عند تساوي المراحل نفضّل الاتجاه الذي يوافق الترند (بدل تفضيل الشراء دائماً)
    best = max(rs, key=lambda d: (d["trigger"], d["stage"], d["trend"]))
    sig = _sig("technical", best["side"], best["strength"],
               f"التحليل الفني: اتجاه + زخم + قوة + محفز ({best['pname']})", sl=best["sl"]) if best["trigger"] else None
    return {"bias": best["side"] if best["stage"] >= 3 else 0, "text": best["text"], "signal": sig,
            "overlay": best["overlay"], "checks": _chk(best["checks"]), "sl": best["sl"]}


def _mk_scan(name, fn):
    return lambda x: _memo(x, name, fn)


# كل مسح يُحسب مرة واحدة لكل شمعة ثم يُعاد استخدامه (إشارات + آراء + رسومات)
SCANS = {"ict": _mk_scan("ict", _scan_ict), "smc": _mk_scan("smc", _scan_smc),
         "elliott": _mk_scan("elliott", _scan_elliott), "technical": _mk_scan("technical", _scan_tech)}
strat_ict = lambda x: SCANS["ict"](x)["signal"]
strat_smc = lambda x: SCANS["smc"](x)["signal"]
strat_elliott = lambda x: SCANS["elliott"](x)["signal"]
strat_technical = lambda x: SCANS["technical"](x)["signal"]


# ------------------ رسومات الاستراتيجيات الداعمة (تظهر عند الضغط عليها) ------------------
def _ov_sr(x):
    a, n, ov = x.iloc[-1], len(x), _ov()
    sup, res = swing_levels(x)
    below, above = [s for s in sup if s <= a.Close], [r for r in res if r >= a.Close]
    if below:
        ov["lines"].append(_ln(x, max(0, n - 120), max(below), "أقرب دعم"))
    if above:
        ov["lines"].append(_ln(x, max(0, n - 120), min(above), "أقرب مقاومة"))
    return ov


def _ov_donchian(x):
    a, n, ov = x.iloc[-1], len(x), _ov()
    ov["lines"] += [_ln(x, max(0, n - 40), a.don_hi, "أعلى 20"), _ln(x, max(0, n - 40), a.don_lo, "أدنى 20")]
    return ov


def _ov_session(x):
    ov = _ov()
    if x.attrs.get("kind") == "crypto":
        return ov
    ts = x.index[-1]
    day = ts.normalize()
    mask = (x.index >= day) & (x.index < day + pd.Timedelta(hours=7))
    asia = x[mask]
    if len(asia) >= 20:
        i0 = int(np.argmax(mask))
        ov["zones"].append(_zn(x, i0, asia["High"].max(), asia["Low"].min(), "نطاق آسيا", 0))
    return ov


def _ov_fib(x):
    n, a, ov = len(x), x.iloc[-1], _ov()
    h, l = x["High"].to_numpy(), x["Low"].to_numpy()
    ph, pl = pivots(h, 5, "H", n - 150, n), pivots(l, 5, "L", n - 150, n)
    if a.ema50 > a.ema200 and ph:
        lows = [i for i in pl if i < ph[-1]]
        if lows:
            H, L = h[ph[-1]], l[lows[-1]]
            ov["zones"].append(_zn(x, ph[-1], H - 0.5 * (H - L), H - 0.618 * (H - L), "المنطقة الذهبية", 1))
            ov["lines"].append(_ln(x, ph[-1], H - 0.786 * (H - L), "إبطال 78.6%"))
    elif a.ema50 < a.ema200 and pl:
        highs = [i for i in ph if i < pl[-1]]
        if highs:
            H, L = h[highs[-1]], l[pl[-1]]
            ov["zones"].append(_zn(x, pl[-1], L + 0.5 * (H - L), L + 0.618 * (H - L), "المنطقة الذهبية", -1))
            ov["lines"].append(_ln(x, pl[-1], L + 0.786 * (H - L), "إبطال 78.6%"))
    return ov


OVERLAY_FNS = {"sr_candle": _ov_sr, "donchian": _ov_donchian, "session_breakout": _ov_session, "fib_pullback": _ov_fib}


# (الاسم، الدالة، الوزن، النوع)
STRATEGIES: list[tuple[str, Callable, float, str]] = [
    ("ict", strat_ict, 1.8, "core"),
    ("smc", strat_smc, 1.8, "core"),
    ("elliott", strat_elliott, 1.4, "core"),
    ("technical", strat_technical, 1.5, "core"),
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
    if kind in ("neutral", "core") or regime == "mixed":
        return 1.0
    if regime == "trend":
        return 1.0 if kind == "trend" else 0.6
    return 1.0 if kind == "reversal" else 0.6   # range


# ------------------ رأي كل استراتيجية في السوق (حتى بدون إشارة) ------------------
def _v_ema_pullback(x):
    a = x.iloc[-1]
    if a.ema20 > a.ema50 > a.ema200:
        b, t = 1, "اتجاه صاعد (EMA20>50>200)"
    elif a.ema20 < a.ema50 < a.ema200:
        b, t = -1, "اتجاه هابط (EMA20<50<200)"
    else:
        return 0, "المتوسطات متشابكة: لا اتجاه واضح"
    d = (a.Close - a.ema20) / a.atr if a.atr > 0 else 0
    return b, f"{t}. السعر {abs(d):.1f} ATR {'فوق' if d >= 0 else 'تحت'} EMA20، RSI {a.rsi:.0f}. ينتظر ارتداداً إلى EMA20"


def _v_fib_pullback(x):
    n, a = len(x), x.iloc[-1]
    h, l = x["High"].to_numpy(), x["Low"].to_numpy()
    ph, pl = pivots(h, 5, "H", n - 150, n), pivots(l, 5, "L", n - 150, n)
    if a.ema50 > a.ema200:
        lows = [i for i in pl if ph and i < ph[-1]]
        if ph and lows and h[ph[-1]] > l[lows[-1]]:
            H, L = h[ph[-1]], l[lows[-1]]
            r = (H - a.Close) / (H - L) * 100
            if r > 100:
                return 0, "المتوسطات صاعدة لكن السعر كسر بداية آخر موجة: الاتجاه الصاعد مهدد"
            if r < 0:
                return 1, "اتجاه صاعد؛ السعر فوق قمة آخر موجة (لا تصحيح بعد)"
            return 1, f"اتجاه صاعد؛ التصحيح الحالي {r:.0f}% من آخر موجة (المنطقة المستهدفة 50-62%)"
        return 1, "اتجاه صاعد بلا موجة دافعة واضحة"
    if a.ema50 < a.ema200:
        highs = [i for i in ph if pl and i < pl[-1]]
        if pl and highs and h[highs[-1]] > l[pl[-1]]:
            H, L = h[highs[-1]], l[pl[-1]]
            r = (a.Close - L) / (H - L) * 100
            if r > 100:
                return 0, "المتوسطات هابطة لكن السعر كسر بداية آخر موجة: الاتجاه الهابط مهدد"
            if r < 0:
                return -1, "اتجاه هابط؛ السعر تحت قاع آخر موجة (لا تصحيح بعد)"
            return -1, f"اتجاه هابط؛ التصحيح الحالي {r:.0f}% من آخر موجة (المنطقة المستهدفة 50-62%)"
        return -1, "اتجاه هابط بلا موجة دافعة واضحة"
    return 0, "لا اتجاه مؤكد (EMA50≈EMA200)"


def _v_supertrend(x):
    a = x.iloc[-1]
    b = int(a.st_dir)
    q = "قوي" if a.adx >= 25 else "متوسط" if a.adx >= 20 else "ضعيف"
    return b, f"Supertrend {'صاعد' if b == 1 else 'هابط'}، قوة الاتجاه ADX {a.adx:.0f} ({q})"


def _v_ichimoku(x):
    a = x.iloc[-1]
    top, bot = np.maximum(a.span_a, a.span_b), np.minimum(a.span_a, a.span_b)
    tk = "Tenkan فوق Kijun" if a.tenkan > a.kijun else "Tenkan تحت Kijun"
    if a.Close > top:
        return 1, f"السعر فوق السحابة؛ {tk}"
    if a.Close < bot:
        return -1, f"السعر تحت السحابة؛ {tk}"
    return 0, f"السعر داخل السحابة (لا اتجاه)؛ {tk}"


def _v_donchian(x):
    a = x.iloc[-1]
    if not a.don_hi > a.don_lo:
        return 0, "بيانات غير كافية"
    pos = (a.Close - a.don_lo) / (a.don_hi - a.don_lo)
    if pos > 1:
        return 1, "السعر فوق أعلى 20 شمعة"
    if pos < 0:
        return -1, "السعر تحت أدنى 20 شمعة"
    return 0, f"داخل قناة 20 شمعة عند {pos * 100:.0f}% (0=القاع، 100=القمة)؛ لا اختراق"


def _v_macd(x):
    a, p = x.iloc[-1], x.iloc[-2]
    b = 1 if a.macd_hist > 0 else -1 if a.macd_hist < 0 else 0
    return b, (f"الهيستوغرام {'موجب' if b == 1 else 'سالب'} و{'يتزايد' if a.macd_hist > p.macd_hist else 'يتناقص'}؛ "
               f"MACD {'فوق' if a.macd > 0 else 'تحت'} الصفر")


def _v_squeeze(x):
    a = x.iloc[-1]
    pct = (x["bb_bw"].iloc[-100:] <= a.bb_bw).mean() * 100
    st = "انضغاط (استعداد لحركة)" if pct <= 20 else "اتساع" if pct >= 80 else "طبيعي"
    return 0, f"عرض البولنجر عند المئين {pct:.0f}% — {st}"


def _v_session(x):
    if x.attrs.get("kind") == "crypto":
        return 0, "غير مفعّلة للكريبتو"
    a, ts = x.iloc[-1], x.index[-1]
    day = ts.normalize()
    asia = x[(x.index >= day) & (x.index < day + pd.Timedelta(hours=7))]
    if ts.hour < 7 or len(asia) < 20:
        return 0, "نطاق آسيا قيد التكوين"
    hi, lo = asia["High"].max(), asia["Low"].min()
    win = "" if 7 <= ts.hour < 11 else " (خارج نافذة لندن)"
    if a.Close > hi:
        return 1, "السعر فوق نطاق آسيا" + win
    if a.Close < lo:
        return -1, "السعر تحت نطاق آسيا" + win
    return 0, "السعر داخل نطاق آسيا" + win


def _v_rsi_bb(x):
    a = x.iloc[-1]
    pos = (a.Close - a.bb_lo) / (a.bb_up - a.bb_lo) * 100 if a.bb_up > a.bb_lo else 50
    if a.rsi < 35:
        return 1, f"تشبع بيع محتمل: RSI {a.rsi:.0f}، السعر عند {pos:.0f}% من نطاق البولنجر"
    if a.rsi > 65:
        return -1, f"تشبع شراء محتمل: RSI {a.rsi:.0f}، السعر عند {pos:.0f}% من نطاق البولنجر"
    return 0, f"RSI {a.rsi:.0f} محايد، السعر عند {pos:.0f}% من نطاق البولنجر"


def _v_sr(x):
    a = x.iloc[-1]
    sup, res = swing_levels(x)
    below, above = [s for s in sup if s <= a.Close], [r for r in res if r >= a.Close]
    parts = []
    if below and a.atr > 0:
        parts.append(f"أقرب دعم على بعد {(a.Close - max(below)) / a.atr:.1f} ATR")
    if above and a.atr > 0:
        parts.append(f"أقرب مقاومة على بعد {(min(above) - a.Close) / a.atr:.1f} ATR")
    return 0, "، ".join(parts) or "لا مستويات واضحة"


def _v_divergence(x):
    return 0, "لا يوجد دايفرجنس مكتمل حالياً"


def _v_stoch(x):
    a = x.iloc[-1]
    b = 1 if a.stoch_k < 20 else -1 if a.stoch_k > 80 else 0
    z = "تشبع بيع" if b == 1 else "تشبع شراء" if b == -1 else "منطقة وسطى"
    return b, f"%K={a.stoch_k:.0f} / %D={a.stoch_d:.0f} — {z}"


VIEWS = {"ema_pullback": _v_ema_pullback, "fib_pullback": _v_fib_pullback, "supertrend_adx": _v_supertrend,
         "ichimoku": _v_ichimoku, "donchian": _v_donchian, "macd_cross": _v_macd, "squeeze_breakout": _v_squeeze,
         "session_breakout": _v_session, "rsi_bollinger": _v_rsi_bb, "sr_candle": _v_sr,
         "rsi_divergence": _v_divergence, "stochastic": _v_stoch}

for _k, _fn in SCANS.items():
    VIEWS[_k] = (lambda fn: (lambda x: (fn(x)["bias"], fn(x)["text"])))(_fn)


STRATEGY_INFO.update({
    "ict": {
        "title": "ICT — سحب السيولة + MSS + OTE", "regime": "أساسية (أي نظام)",
        "entry": ["سحب سيولة: شمعة (آخر 15) كسرت قاع سابق مؤكد (بمقدار ≥ 0.1 ATR) وأغلقت فوقه (للبيع: قمة وأغلقت تحتها)",
                  "MSS: إغلاق لاحق فوق آخر قمة مؤكدة قبل السحب (قبل شمعة التأكيد)، مع شمعة اندفاع جسمها ≥ 0.8 ATR",
                  "موجة الاندفاع ≥ 1.5 ATR وعمرها ≤ 40 شمعة، ولم يُكسر قاع السحب",
                  "السعر في منطقة الخصم (النصف الأسفل لنطاق آخر 100 شمعة) للشراء، والعلاوة للبيع",
                  "شمعة تأكيد داخل OTE (61.8%-79% من الموجة) ويُرسم FVG إن وُجد",
                  "داخل Kill Zone: لندن 07-11 ونيويورك 12-16 UTC (الكريبتو بلا قيد)",
                  "القوة 0.8 (+0.1 إذا تقاطع FVG مع OTE)"],
        "stop": "أسفل قاع السحب (للبيع أعلى قمته)"},
    "smc": {
        "title": "SMC — كسر الهيكل + Order Block", "regime": "أساسية (أي نظام)",
        "entry": ["BOS/CHoCH: إغلاق فوق أحدث قمة مؤكدة خلال آخر 60 شمعة (CHoCH إذا عكس اتجاه EMA50/EMA200)",
                  "Order Block: آخر شمعة هابطة قبل الاندفاع (حجمها بين 0.2 و3 ATR)",
                  "اندفاع ≥ 2 ATR من قاع الحركة إلى الكسر",
                  "الكتلة لم تُستهلك: لا إغلاق خلفها منذ الكسر",
                  "السعر في الخصم (أو العلاوة للبيع) ويرتد من الكتلة بشمعة تأكيد",
                  "القوة 0.75 (+0.1 أول لمسة، +0.05 مع FVG)"],
        "stop": "أسفل الـ Order Block (للبيع أعلاه)"},
    "elliott": {
        "title": "موجات إليوت — بداية الموجة 3 / 5", "regime": "أساسية (أي نظام)",
        "entry": ["محاور ZigZag (±4 شموع) على آخر 300 شمعة",
                  "الموجة 3: محاور L-H-L؛ الموجة 1 ≥ 2 ATR، الموجة 2 لا تكسر البداية وتصحح بين 38.2% و78.6%",
                  "الموجة 5: محاور L-H-L-H-L؛ الموجة 4 لا تتداخل مع الموجة 1، الموجة 3 ≥ الموجة 1، وتصحيح 4 بين 23.6% و50%",
                  "المحور الأخير حديث (≤ 30 شمعة) ولم يُكسر، وشمعة تأكيد فوق EMA20 وزخم MACD يتحسن",
                  "القوة 0.75 للموجة 3 (+0.1 عند تصحيح 50-61.8%) و0.65 للموجة 5"],
        "stop": "أسفل محور بداية الموجة (إبطال العدّ). الهدف: 161.8% من الموجة 1 (أو مساواة الموجة 1 للموجة 5)"},
    "technical": {
        "title": "التحليل الفني الكلاسيكي — اتجاه + زخم + قوة + محفز", "regime": "أساسية (أي نظام)",
        "entry": ["الاتجاه: EMA20 > EMA50 والسعر فوق EMA50 وميل EMA50 صاعد (للبيع العكس)",
                  "الزخم: هيستوغرام MACD موجب وRSI بين 50 و72 (للبيع 28-50)",
                  "القوة: ADX ≥ 20 و+DI > -DI",
                  "المحفز: شمعة انعكاسية (ابتلاع/مطرقة) عند EMA20 أو دعم، أو كسر مقاومة ثم إعادة اختبارها",
                  "القوة 0.7 (+0.1 عند اجتماع المحفزين، +0.1 إذا ADX ≥ 25)"],
        "stop": "أدنى 8 شموع (للبيع أعلى 8)"},
})


# ---------- رسومات الاستراتيجيات على الشارت ----------
OVERLAYS = {}
for _k, _fn in SCANS.items():
    OVERLAYS[_k] = (lambda fn: (lambda x: fn(x)["overlay"]))(_fn)
for _k, _fn in OVERLAY_FNS.items():
    OVERLAYS[_k] = _fn


def compute_overlays(x) -> dict:
    out = {}
    for name, _, _, _ in STRATEGIES:
        fn = OVERLAYS.get(name)
        try:
            out[name] = fn(x) if fn else _ov()
        except Exception:
            log.exception("overlay %s failed", name)
            out[name] = _ov()
    return out


def main_zone(e, ov):
    return None


def build_views(x, found, regime):
    fired = {s.name: s for s in found}
    out = []
    for name, _, weight, kind in STRATEGIES:
        if name in DISABLED_STRATEGIES:
            continue
        overlay, checks = None, []
        try:
            if name in SCANS:
                sc = _memo(x, name, SCANS[name])
                bias, text, overlay, checks = sc["bias"], sc["text"], sc["overlay"], sc["checks"]
            else:
                bias, text = VIEWS[name](x)
                if name in OVERLAY_FNS:
                    overlay = OVERLAY_FNS[name](x)
        except Exception:
            log.exception("view %s failed", name)
            bias, text = 0, "تعذر الحساب"
        s = fired.get(name)
        if s:
            bias, text = s.side, s.reason
        out.append({"name": name, "title": STRATEGY_INFO[name]["title"], "bias": int(bias), "signal": bool(s),
                    "text": text, "kind": kind, "core": name in SCANS, "weight": weight,
                    "regime_fit": regime_multiplier(regime, kind), "overlay": overlay, "checks": checks})
    return out


def _wait(note: str, **extra) -> dict:
    return {"decision": "WAIT", "side": 0, "note": note, **extra}


def analyze(df: pd.DataFrame, spec: SymbolSpec, views: bool = True) -> dict:
    """تحليل على شموع مغلقة فقط: استراتيجيات → آراء → تصويت مرجّح → فلاتر → وقف هيكلي → فحص التكلفة."""
    if len(df) < MIN_BARS:
        return _wait("بيانات غير كافية")
    x = compute_indicators(df)
    x.attrs["kind"] = spec.kind
    a = x.iloc[-1]
    if not a.atr > 0:
        return _wait("ATR غير صالح")
    vr = float(a.atr / a.atr_med) if a.atr_med > 0 else 1.0
    adx_v = float(a.adx)
    regime = "trend" if adx_v >= 25 else "range" if adx_v <= 18 else "mixed"
    htf = htf_direction(df)

    scores, counts, found, signals = {1: 0.0, -1: 0.0}, {1: 0, -1: 0}, [], []
    gp: dict = {}
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
        gp.setdefault((name, s.side), []).append(val)
        found.append(s)
        signals.append({**asdict(s), "points": round(val, 2)})

    for (_g, sd), vals in gp.items():
        vals.sort(reverse=True)
        scores[sd] += vals[0] + 0.3 * sum(vals[1:])
        counts[sd] += 1

    # --- تأكيد الاستراتيجيات الأساسية: إشارة مكتملة (signal) أو إعداد مؤكد بانتظار المنطقة (setup)
    core = {1: [], -1: []}
    core_sc = {1: {}, -1: {}}
    for cname, cfn in SCANS.items():
        if cname in DISABLED_STRATEGIES:
            continue
        try:
            sc = cfn(x)
        except Exception:
            log.exception("core scan %s failed", cname)
            continue
        sg = sc.get("signal")
        sd, mode = (sg.side, "signal") if sg else (int(sc.get("bias") or 0), "setup")
        if sd in (1, -1) and (mode == "signal" or SETUP_COUNTS):
            core[sd].append({"name": cname, "mode": mode})
            core_sc[sd][cname] = sc
    eff = {sd: scores[sd] + SETUP_BONUS * sum(1 for c in core[sd] if c["mode"] == "setup") for sd in (1, -1)}

    side = 1 if eff[1] >= eff[-1] else -1
    win, lose = eff[side], eff[-side]
    if htf == -side:
        win *= 0.75     # عقوبة للتداول ضد اتجاه الساعة

    res = {"bar": str(df.index[-1]), "atr": float(a.atr), "vol_ratio": round(vr, 2),
           "decision": "WAIT", "side": 0, "score": round(win, 2),
           "long_score": round(eff[1], 2), "short_score": round(eff[-1], 2),
           "regime": regime, "adx": round(adx_v, 1), "rsi": round(float(a.rsi), 1), "htf": htf,
           "signals": signals, "core": {"needed": CORE_CONFIRM, "buy": core[1], "sell": core[-1]}}
    if views:
        vs = build_views(x, found, regime)
        res["views"] = vs
        res["bias_counts"] = {"bull": sum(v["bias"] == 1 for v in vs), "bear": sum(v["bias"] == -1 for v in vs),
                              "neutral": sum(v["bias"] == 0 for v in vs)}

    if not in_liquid_hours(spec.kind, df.index[-1].to_pydatetime()):
        res["note"] = "خارج ساعات السيولة (توسع السبريد)"
        return res
    if vr > 3:
        res["note"] = "تقلب مفرط (احتمال خبر) — انتظار الهدوء"
        return res
    if vr < 0.4:
        res["note"] = "سوق هادئ جداً"
        return res
    if not (win >= MIN_SCORE and counts[side] >= MIN_STRATEGIES and win >= 2 * lose):
        return res
    if win < STRICT_SCORE and htf != side:
        res["note"] = "إشارة حدّية: تحتاج توافق اتجاه الساعة (1H)"
        return res
    if HTF_HARD and htf != side:
        res["note"] = "اتجاه الإطار الأعلى لا يوافق الإشارة" + (" (غير متاح: بيانات قليلة)" if htf == 0 else "")
        return res
    if adx_v < MIN_ADX:
        res["note"] = f"ADX {adx_v:.0f} أقل من {MIN_ADX:g}"
        return res
    n_core, n_opp = len(core[side]), len(core[-side])
    n_sig = sum(1 for c in core[side] if c["mode"] == "signal")
    if n_core < CORE_CONFIRM or n_core <= n_opp:
        res["note"] = (f"تأكيد الاستراتيجيات الأساسية غير كافٍ: {n_core} من {CORE_CONFIRM} مطلوبة"
                       + (f" (والمعاكسة {n_opp})" if n_opp else ""))
        return res
    if n_sig < CORE_MIN_SIGNALS:
        res["note"] = f"التأكيد الأساسي إعدادات فقط ({n_core}) — بانتظار إشارة مكتملة من إحداها"
        return res

    # ---- الوقف: نقطة إبطال الفكرة للاستراتيجيات الأساسية المؤكِّدة (الوسيط)، خلف آخر قمة/قاع قريب، + هامش (سبريد/ATR)
    entry, atr_v = float(a.Close), float(a.atr)
    buf = max(0.15 * atr_v, spec.spread_pips * spec.pip)
    hints = []
    for sc in core_sc[side].values():
        slp = sc.get("sl")
        if slp is not None and slp == slp and (entry - slp) * side > 0:
            hints.append((entry - slp) * side + buf)
    if not hints:
        hints = [(entry - s.sl) * side + buf for s in found
                 if s.side == side and s.sl is not None and (entry - s.sl) * side > 0]
    lo_c, hi_c = MIN_SL_ATR * atr_v, MAX_SL_ATR * atr_v
    if hints:
        raw, src = float(np.median(hints)), "structure"
    else:
        raw, src = ATR_SL_MULT * atr_v, "atr"
    rc = x.iloc[-6:]
    adverse = (entry - float(rc["Low"].min())) if side == 1 else (float(rc["High"].max()) - entry)
    sl_dist = float(np.clip(max(raw, adverse + buf), lo_c, hi_c))
    res["sl_capped"] = bool(raw > hi_c)

    # ---- التكلفة: إن كانت كبيرة نسبةً للوقف نوسّع الوقف (الحجم ينقص تلقائياً والمخاطرة ثابتة) وإلا نرفض
    cost = trade_cost(spec, entry)
    need = cost / MAX_COST_RATIO if MAX_COST_RATIO > 0 else 0.0
    if sl_dist < need:
        if need <= hi_c:
            sl_dist, src = need, src + "+cost"
        else:
            res.update({"sl_dist": sl_dist, "sl_source": src, "cost": cost})
            res["note"] = f"التكلفة (سبريد/عمولة) مرتفعة نسبةً للوقف: تحتاج وقفاً ≥ {need:.{spec.decimals}f}"
            return res
    res.update({"sl_dist": sl_dist, "sl_source": src, "cost": cost})

    # ---- الأهداف: هدف واحد عندما RR<1 (إعداد النسبة العالية) • وإلا TP1=1R (تعادل) • TP2=الهدف الرئيسي • TP3=امتداد • + هدف إليوت
    rr = RISK_REWARD
    tp_dist = rr * sl_dist
    targets = [{"label": "TP", "r": round(rr, 2)}] if rr <= 1 else [
        {"label": "TP1", "r": 1.0}, {"label": "TP", "r": round(rr, 2)}]
    ell = core_sc[side].get("elliott")
    if rr >= 1 and ell and ell.get("tgt") is not None:
        er = (float(ell["tgt"]) - entry) * side / sl_dist
        if er >= 1.2:
            res["elliott_target"] = {"price": float(ell["tgt"]), "r": round(er, 2)}
            targets.append({"label": "إليوت", "r": round(er, 2)})
    targets.sort(key=lambda t: t["r"])
    for t in targets:
        t["price"] = entry + side * sl_dist * t["r"]
    res["targets"] = targets
    res["sl_price"] = entry - side * sl_dist
    res["tp_price"] = entry + side * tp_dist
    res["rr_net"] = round((tp_dist - cost) / (sl_dist + cost), 2)
    try:
        sup, rsl = swing_levels(x)
        lv = [v for v in (sup if side == -1 else rsl) if (v - entry) * side > 0.3 * atr_v]
        if lv:
            nv = min(lv, key=lambda v: abs(v - entry))
            if abs(nv - entry) < tp_dist:
                res["obstacle"] = {"price": float(nv), "r": round(abs(nv - entry) / sl_dist, 2)}
    except Exception:
        pass

    zs = [s.zone for s in found if s.side == side and s.zone]
    if not zs:
        zs = [sc["zone"] for sc in core_sc[side].values() if sc.get("zone")]
    if zs:
        ez = {"top": zs[0][0], "bottom": zs[0][1]}
    else:
        ez = {"top": entry + 0.15 * atr_v, "bottom": entry - 0.15 * atr_v}
    res["entry_zone"] = {**ez, "side": side}
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
    targets: list = field(default_factory=list)

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
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

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


def to_tf(df: pd.DataFrame) -> pd.DataFrame:
    """تجميع شموع الساعة إلى الإطار المطلوب (4H) على شبكة UTC (0،4،8،...) كما في الاختبار."""
    if TIMEFRAME == "15m" or df is None or df.empty:
        return df
    o = df.resample(f"{max(1, TF_MINUTES // 60)}h").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    return o.dropna(subset=["Open", "High", "Low", "Close"])


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
        raw = []
        if bars > 300:
            try:   # تجميع صفحات (best-effort)
                ms = BAR_MINUTES * 60 * 1000
                since = int(time.time() * 1000) - bars * ms
                for _ in range(bars // 100 + 4):
                    chunk = await self.okx.fetch_ohlcv(sym, TIMEFRAME, since=since, limit=100)
                    if not chunk:
                        break
                    raw += chunk
                    since = chunk[-1][0] + ms
                    if since > time.time() * 1000:
                        break
            except Exception:
                log.warning("okx paging failed, falling back to 300 bars")
                raw = []
        if len(raw) < min(bars, 300):
            raw = await self.okx.fetch_ohlcv(sym, TIMEFRAME, limit=min(bars, 300))
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
                src = Interval.in_15_minute if TIMEFRAME == "15m" else Interval.in_1_hour
                nb = bars if TIMEFRAME == "15m" else min(5000, bars * max(1, TF_MINUTES // 60) + 8)
                return self.tv.get_hist(symbol=spec.tv[1], exchange=spec.tv[0], interval=src, n_bars=nb)
            hist = await asyncio.to_thread(work)
        if hist is None or hist.empty:
            return None
        hist = hist.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
        df = to_tf(clean_ohlc(hist)).tail(bars)
        return df if len(df) >= 100 else None

    async def _yf(self, spec, bars):
        def work():
            if TIMEFRAME == "15m":
                return yf.download(spec.yf, period="30d" if bars > 800 else "10d", interval="15m",
                                   progress=False, auto_adjust=False)
            return yf.download(spec.yf, period="400d", interval="1h", progress=False, auto_adjust=False)
        d = await asyncio.to_thread(work)
        if d is None or d.empty:
            return None
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        if d.index.tz is not None:
            d.index = d.index.tz_convert("UTC").tz_localize(None)
        df = to_tf(clean_ohlc(d)).tail(bars)
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
                        await self.send(chat, "✅ تم الاشتراك في الإشارات.\n/stop إلغاء • /status الحالة • /trades الصفقات • /views BTCUSDT آراء الاستراتيجيات")
                    elif cmd == "/stop":
                        self.subs.discard(chat)
                        self._save()
                        await self.send(chat, "تم إلغاء الاشتراك.")
                    elif cmd in ("/status", "/trades", "/views"):
                        await self.send(chat, status_fn(text))
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
        self.stats = {"analyses": 0, "signals": 0, "opened": 0, "skipped": {}}
        self._chart = None
        self.ov_cache = None

    def _skip(self, a: dict, reason: str):
        a["skipped"] = reason
        self.stats["skipped"][reason] = self.stats["skipped"].get(reason, 0) + 1

    @property
    def price(self) -> Optional[float]:
        return float(self.df["Close"].iloc[-1]) if self.df is not None else None

    async def refresh(self, provider: DataProvider):
        if time.time() - self.last_fetch < FETCH_INTERVAL:
            return
        self.last_fetch = time.time()
        df, src = await provider.fetch(self.symbol, self.spec, BAR_FETCH)
        if df is None:
            self.data_ok, self.note = False, "فشل جلب البيانات الحقيقية"
            return
        self.df, self.source = df, src
        self.data_ok, self.note = True, "OK"
        if HTF_HARD and len(df) < HTF_MIN_BARS:
            self.data_ok, self.note = False, f"بيانات قليلة ({len(df)}) لاتجاه الإطار الأعلى؛ يلزم {HTF_MIN_BARS}+"
        if self.spec.kind == "crypto":    # فحص حداثة البيانات (UTC معروف للكريبتو)
            age = datetime.utcnow() - df.index[-1].to_pydatetime()
            if age > timedelta(minutes=BAR_MINUTES * 3):
                self.data_ok, self.note = False, "بيانات قديمة"

    async def chart_df(self, provider: "DataProvider"):
        """تاريخ أطول للعرض فقط (حتى 1000 شمعة) مع كاش 3 دقائق؛ التحليل يبقى على بيانات المحرك."""
        c = self._chart
        if c and time.time() - c[0] < 180:
            return c[1]
        df, _ = await provider.fetch(self.symbol, self.spec, 1000)
        if df is not None and len(df) > len(self.df):
            self._chart = (time.time(), df)
            return df
        self._chart = (time.time(), self.df)
        return self.df

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
        self.stats["analyses"] += 1
        if a["decision"] in ("BUY", "SELL"):
            self.stats["signals"] += 1
        if a["decision"] not in ("BUY", "SELL") or self.trade is not None:
            return
        if self.cooldown_until is not None and bar <= self.cooldown_until:
            self._skip(a, "فترة انتظار بعد صفقة سابقة")
            return
        side = a["side"]
        if self.spec.spot and side == -1 and not ALLOW_SPOT_SHORT:
            self._skip(a, "البيع المكشوف غير متاح على كريبتو السبوت")
            return
        ok, why = portfolio_can_open(self)
        if not ok:
            self._skip(a, why)
            return
        sz = size_position(self.spec, account.balance, price, a["sl_dist"])
        if not sz["ok"]:
            self._skip(a, sz["reason"])
            return
        open_risk = sum(e.trade.risk_usd for e in engines.values() if e.trade)
        if open_risk + sz["risk_usd"] > account.balance * MAX_TOTAL_RISK_PCT / 100:
            self._skip(a, "مجموع المخاطرة المفتوحة سيتجاوز الحد")
            return
        t = Trade.open(self.symbol, side, price, a["sl_dist"], RISK_REWARD,
                       [s["name"] for s in a["signals"] if s["side"] == side], a["score"],
                       datetime.utcnow().isoformat(timespec="seconds"), cost=a["cost"], lots=sz["lots"],
                       usd_factor=sz["lots"] * self.spec.units_per_lot * quote_to_usd(self.spec, price),
                       risk_usd=sz["risk_usd"], margin_usd=sz["margin_usd"], sl_source=a["sl_source"])
        t.checked_until = str(self.df.index[-1])
        t.targets = [dict(x) for x in a.get("targets", [])]
        self.trade = t
        self.stats["opened"] += 1
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
        src = {"structure": "هيكلي", "atr": "ATR"}.get(t.sl_source.split("+")[0], "ATR") + (" + توسعة للتكلفة" if "+cost" in t.sl_source else "")
        nm = {"ict": "ICT", "smc": "SMC", "elliott": "إليوت", "technical": "فني"}
        key = "buy" if t.side == 1 else "sell"
        core = " • ".join(f"{nm.get(c['name'], c['name'])}{'⚡' if c['mode'] == 'signal' else '◔'}" for c in a["core"][key])
        z = a.get("entry_zone")
        ez = f"منطقة الدخول: <code>{fmt(z['bottom'], sp)} – {fmt(z['top'], sp)}</code>\n" if z else ""
        tps = "\n".join(f"🎯 {x['label']}: <code>{fmt(x['price'], sp)}</code> ({x['r']:g}R)"
                        + (" — حرّك الوقف للتعادل" if x["label"] == "TP1" else "") for x in a.get("targets", []))
        ob = a.get("obstacle")
        obs = f"\n⚠️ مستوى قريب قبل الهدف: <code>{fmt(ob['price'], sp)}</code> ({ob['r']}R)" if ob else ""
        foot = "" if RISK_REWARD < 1 else "\n\n<i>عند +1R حرّك الوقف للدخول، وبعد +1.5R تابع الوقف المتحرك.</i>"
        return (f"{icon} <b>{word} {self.symbol}</b>\n"
                f"الدخول: <code>{fmt(t.entry, sp)}</code>\n{ez}"
                f"⛔ الوقف: <code>{fmt(t.sl, sp)}</code> ({src}، مسافة {fmt(t.risk, sp)})\n{tps}{obs}\n"
                f"صافي R:R بعد التكلفة: <b>{a.get('rr_net', '—')}</b>\n"
                f"الحجم: <b>{size_label(self.symbol, sp, t.lots)}</b> | المخاطرة: ${t.risk_usd} "
                f"({t.risk_usd / account.balance * 100:.1f}%) | الهامش: ${t.margin_usd}\n"
                f"النقاط: {a['score']} | السوق: {a['regime']} (ADX {a['adx']}) | 1H: {htf}\n"
                f"🧩 تأكيد أساسي: {core}\n\n{reasons}{foot}")

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
        res = analyze(df.iloc[max(0, i + 1 - 500):i + 1], spec, views=False)
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
ENABLED_SYMBOLS = [x.strip().upper() for x in os.environ.get("SYMBOLS_ENABLED", "XAUUSD,BTCUSDT").split(",") if x.strip()]
engines: dict[str, MarketEngine] = {s: MarketEngine(s, sp) for s, sp in SYMBOLS.items() if s in ENABLED_SYMBOLS}
telegram = Telegram(TELEGRAM_TOKEN, SUBSCRIBERS_FILE)
account = Account(ACCOUNT_BALANCE, ACCOUNT_FILE)


class State:
    provider: Optional[DataProvider] = None
    http: Optional[httpx.AsyncClient] = None


state = State()


async def notify(msg: str):
    await telegram.broadcast(msg)


def status_text(text: str) -> str:
    parts = text.split()
    cmd = parts[0].lower().split("@")[0]
    if cmd == "/views":
        sym = parts[1].upper() if len(parts) > 1 else "BTCUSDT"
        sym = {"WTIUSD": "USOIL"}.get(sym, sym)
        e = engines.get(sym)
        if not e or not e.analysis or not e.analysis.get("views"):
            return f"لا يوجد تحليل لـ {sym} بعد (السوق مغلق أو بانتظار إغلاق شمعة).\nالرموز: " + ", ".join(engines)
        a = e.analysis
        icon = {1: "🟢", -1: "🔴", 0: "⚪"}
        lines = [f"📊 <b>{sym}</b> | القرار: <b>{a['decision']}</b> | النقاط {a['score']} | {a['regime']} (ADX {a['adx']})"]
        for v in a["views"]:
            lines.append(f"{icon[v['bias']]} <b>{html.escape(v['title'])}</b>{' ⚡' if v['signal'] else ''}\n   {html.escape(v['text'])}")
        if a.get("note"):
            lines.append(f"⚠️ {a['note']}")
        return "\n".join(lines)
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


app = FastAPI(title="Zero Reversal Engine", version="49.0", lifespan=lifespan)


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


def why_no_trade(e: MarketEngine) -> dict:
    a = e.analysis or {}
    reasons = []
    if e.df is None or not e.data_ok:
        reasons.append(f"لا توجد بيانات صالحة: {e.note}")
    if not is_market_open(e.spec.kind):
        reasons.append("السوق مغلق (يفتح الأحد 22:00 UTC)")
    if e.analysis is None and e.data_ok and is_market_open(e.spec.kind):
        reasons.append("لم يُجرَ أي تحليل بعد (بانتظار إغلاق شمعة)")
    if a.get("note"):
        reasons.append(a["note"])
    if a and a.get("decision") == "WAIT" and not a.get("note"):
        sig = a.get("signals", [])
        side = 1 if a.get("long_score", 0) >= a.get("short_score", 0) else -1
        n_side = sum(1 for s in sig if s["side"] == side)
        win, lose = max(a.get("long_score", 0), a.get("short_score", 0)), min(a.get("long_score", 0), a.get("short_score", 0))
        if not sig:
            reasons.append("لم تُصدر أي استراتيجية إشارة في آخر شمعة")
        elif a.get("score", 0) < MIN_SCORE:
            reasons.append(f"النقاط {a.get('score')} أقل من الحد {MIN_SCORE} (شراء {a.get('long_score')} / بيع {a.get('short_score')})")
        elif n_side < MIN_STRATEGIES:
            reasons.append(f"استراتيجية واحدة فقط تتفق (المطلوب {MIN_STRATEGIES})")
        elif win < 2 * lose:
            reasons.append("تعارض بين استراتيجيات الشراء والبيع")
    if a.get("skipped"):
        reasons.append("إشارة لم تُنفَّذ: " + a["skipped"])
    if e.trade:
        reasons.append("توجد صفقة مفتوحة بالفعل على هذا الرمز")
    return {"symbol": e.symbol, "source": e.source, "data_ok": e.data_ok, "market_open": is_market_open(e.spec.kind),
            "last_analyzed_bar": a.get("bar"), "decision": a.get("decision"), "score": a.get("score"),
            "regime": a.get("regime"), "reasons": reasons or ["لا سبب ظاهر"], "stats": e.stats}


@app.get("/api/why")
async def api_why():
    recipients = len(telegram.subs | ADMIN_CHAT_IDS)
    return {"telegram_enabled": telegram.enabled, "telegram_recipients": recipients,
            "telegram_hint": None if recipients else "لا يوجد مستلم: أرسل /start للبوت أو اضبط ADMIN_CHAT_IDS",
            "thresholds": {"min_score": MIN_SCORE, "min_strategies": MIN_STRATEGIES, "core_confirm": CORE_CONFIRM, "core_min_signals": CORE_MIN_SIGNALS,
                           "setup_counts": SETUP_COUNTS, "max_cost_ratio": MAX_COST_RATIO},
            "symbols": [why_no_trade(e) for e in engines.values()]}


@app.get("/api/strategies")
async def api_strategies():
    return {
        "params": {"min_score": MIN_SCORE, "strict_score": STRICT_SCORE, "min_strategies": MIN_STRATEGIES, "risk_reward": RISK_REWARD,
                   "atr_sl_mult_fallback": ATR_SL_MULT, "max_cost_ratio": MAX_COST_RATIO, "core_confirm": CORE_CONFIRM,
                   "setup_counts": SETUP_COUNTS, "min_sl_atr": MIN_SL_ATR, "max_sl_atr": MAX_SL_ATR,
                   "htf_hard": HTF_HARD, "min_adx": MIN_ADX},
        "filters": ["نظام السوق ADX: ≥25 اتجاه، ≤18 عرضي", "اتجاه 1H (EMA20/50): عقوبة 25% عند المعاكسة",
                    f"إلزام اتفاق اتجاه 1H: {'نعم' if HTF_HARD else 'لا'} • أقل ADX للدخول: {MIN_ADX:g}",
                    "تقلب ATR/وسيطه: رفض فوق 3× أو تحت 0.4×", "تجنب 21:00-24:00 UTC لغير الكريبتو",
                    f"السبريد+العمولة ≤ {MAX_COST_RATIO * 100:.0f}% من الوقف (يُوسَّع الوقف تلقائياً حتى {MAX_SL_ATR:g} ATR وإلا رُفضت)",
                    f"الدخول يتطلب تأكيد {CORE_CONFIRM} استراتيجيات أساسية أو أكثر (⚡ إشارة مكتملة / ◔ إعداد مؤكد)", "صفقة واحدة لكل مجموعة مرتبطة"],
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


def chart_extras(e: "MarketEngine") -> dict:
    closed = e.df.iloc[:-1]
    bar = closed.index[-1]
    if e.ov_cache and e.ov_cache[0] == bar:
        return e.ov_cache[1]
    x = compute_indicators(closed)
    x.attrs["kind"] = e.spec.kind
    ov = compute_overlays(x)
    e.ov_cache = (bar, ov)
    return ov


@app.get("/api/candles/{symbol}")
async def api_candles(symbol: str, limit: int = Query(400, ge=50, le=1000)):
    e = engines.get(symbol.upper())
    if not e or e.df is None:
        raise HTTPException(404, "لا توجد بيانات لهذا الرمز بعد")
    df = e.df if limit <= len(e.df) else await e.chart_df(state.provider)
    x = compute_indicators(df).tail(limit)
    ts = [int(t.timestamp()) for t in x.index]

    def line(col):
        return [{"time": t, "value": float(v)} for t, v in zip(ts, x[col]) if v == v]

    candles = [{"time": t, "open": float(r.Open), "high": float(r.High), "low": float(r.Low), "close": float(r.Close)}
               for t, (_, r) in zip(ts, x.iterrows())]
    try:
        ov = chart_extras(e)
    except Exception:
        log.exception("chart_extras failed")
        ov = {}
    a = e.analysis or {}
    plan, tr = None, e.trade
    if tr:
        tl = [{"label": t["label"], "r": t["r"], "price": tr.entry + tr.side * tr.risk * t["r"]} for t in (tr.targets or [])]
        plan = {"kind": "open", "side": tr.side, "entry": tr.entry, "sl": tr.sl, "tp": tr.tp, "targets": tl, "rr_net": None}
    elif a.get("decision") in ("BUY", "SELL") and a.get("sl_dist") and e.price:
        s = a["side"]
        tl = [{"label": t["label"], "r": t["r"], "price": e.price + s * a["sl_dist"] * t["r"]} for t in a.get("targets", [])]
        plan = {"kind": "signal", "side": s, "entry": e.price, "sl": e.price - s * a["sl_dist"],
                "tp": e.price + s * a["sl_dist"] * RISK_REWARD, "targets": tl, "rr_net": a.get("rr_net")}
    info = {n: {"title": i.get("title", n), "entry": i.get("entry", []), "stop": i.get("stop", "")}
            for n, i in STRATEGY_INFO.items()}
    return {"symbol": e.symbol, "decimals": e.spec.decimals, "candles": candles,
            "ema20": line("ema20"), "ema50": line("ema50"), "ema200": line("ema200"),
            "trade": {"side": tr.side, "entry": tr.entry, "sl": tr.sl, "tp": tr.tp, "opened_at": tr.opened_at} if tr else None,
            "plan": plan, "main_zone": main_zone(e, ov) if ov else None, "overlays": ov, "info": info}


CHART_PAGE = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__SYM__ — Zero Reversal</title>
<style>:root{color-scheme:light dark;--bg:#fff;--fg:#1a1a1a;--mut:#6b7280;--bd:#e5e7eb;--card:#f3f4f6;--acc:#6366f1}
@media(prefers-color-scheme:dark){:root{--bg:#0f1117;--fg:#e8e8ea;--mut:#9aa0aa;--bd:#262a33;--card:#181b23}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}
header{display:flex;gap:10px;align-items:center;padding:10px 12px;flex-wrap:wrap}a{color:inherit}.m{color:var(--mut)}
.logo{font-weight:800;background:linear-gradient(90deg,#6366f1,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent}
#box{height:56vh;min-height:320px;direction:ltr;position:relative;touch-action:none;user-select:none;-webkit-user-select:none}
canvas{display:block;touch-action:none;cursor:grab}canvas:active{cursor:grabbing}
.lg{padding:2px 12px 6px;font-size:12px;display:flex;gap:12px;flex-wrap:wrap}.lg i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-inline-end:4px}
.bt{display:flex;gap:8px;padding:0 12px 6px;flex-wrap:wrap}.bt button{background:var(--card);color:var(--fg);border:1px solid var(--bd);border-radius:8px;padding:6px 12px;font-size:14px}
.bt button.on{border-color:var(--acc);outline:1px solid var(--acc)}
.tip{padding:0 12px 8px;font-size:12px;color:var(--mut)}
#v{padding:0 12px 12px}.sum,.sel{background:var(--card);border-radius:12px;padding:10px;margin-bottom:10px;line-height:1.7}
.sel{border:1px solid var(--acc)}.sel ul{margin:6px 0 0;padding-inline-start:18px}.sel li{margin:2px 0;list-style:none;margin-inline-start:-18px}
h4{margin:14px 0 4px;color:var(--acc)}.r{border-bottom:1px solid var(--bd);padding:9px 6px;cursor:pointer;border-radius:8px}
.r.on{background:var(--card);outline:1px solid var(--acc)}.tag{background:#16a34a;color:#fff;border-radius:6px;padding:1px 6px;font-size:12px}
.hint{font-size:12px;color:var(--mut);margin:4px 0}
footer{text-align:center;padding:18px 0 28px;color:var(--mut);font-size:13px}footer b{background:linear-gradient(90deg,#6366f1,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent}</style></head><body>
<header><a href="/">← الرئيسية</a><span class="logo">Zero Reversal</span><b>__SYM__</b><span id="i" class="m"></span></header>
<div id="box"><canvas id="cv"></canvas></div>
<div class="lg m"><span><i style="background:#3b82f6"></i>EMA20</span><span><i style="background:#f59e0b"></i>EMA50</span><span><i style="background:#a855f7"></i>EMA200</span></div>
<div class="bt"><button onclick="zoom(0.7)">＋</button><button onclick="zoom(1/0.7)">－</button>
<button onclick="setN(100)">100</button><button onclick="setN(200)">200</button><button onclick="setN(400)">400</button><button onclick="setN(600)">600</button>
<button onclick="goLive()">⏭ الآن</button><button onclick="resetView()">↺ ضبط</button><button onclick="pick(null)">إلغاء التحديد</button></div>
<div class="tip">اسحب لتحريك الشارت (يمين/يسار/أعلى/أسفل) • إصبعان للتكبير • اسحب محور السعر لتكبير الارتفاع • نقرتان لإعادة الضبط</div>
<div id="v"></div>
<footer>Developed by <b>aziz</b></footer>
<script>
const SYM='__SYM__';let DATA=null,AN=null,MO=true,N=200,OFF=0,YO=0,YS=1,PPP=1,SEL=null,raf=0;
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const selView=()=>AN&&AN.views&&SEL?AN.views.find(v=>v.name===SEL):null;
const sched=()=>{if(!raf)raf=requestAnimationFrame(()=>{raf=0;draw()})};
function draw(){
 const d=DATA;if(!d||!d.candles.length)return;
 const A=d.candles,tot=A.length;
 N=Math.max(20,Math.min(Math.round(N),tot));OFF=Math.max(0,Math.min(OFF,tot-N));
 const cv=document.getElementById('cv'),box=document.getElementById('box'),dpr=window.devicePixelRatio||1;
 const W=box.clientWidth,H=box.clientHeight;
 cv.width=W*dpr;cv.height=H*dpr;cv.style.width=W+'px';cv.style.height=H+'px';
 const g=cv.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,W,H);
 const fg=css('--fg'),mut=css('--mut'),bd=css('--bd'),bg=css('--bg');
 const end=tot-Math.round(OFF),C=A.slice(end-N,end),padR=66,padB=20,padT=8,pw=W-padR,ph=H-padB-padT;
 let hi=-Infinity,lo=Infinity;C.forEach(c=>{hi=Math.max(hi,c.high);lo=Math.min(lo,c.low)});
 const PL=d.plan;
 if(PL&&OFF<5){[PL.entry,PL.sl,PL.tp].forEach(v=>{if(v!=null){hi=Math.max(hi,v);lo=Math.min(lo,v)}})}
 const pad=(hi-lo)*0.06||1;hi+=pad;lo-=pad;
 const mid=(hi+lo)/2,half=(hi-lo)/2*YS;hi=mid+half+YO;lo=mid-half+YO;PPP=(hi-lo)/ph;
 const y=v=>padT+(hi-v)/(hi-lo)*ph,step=pw/C.length,x=i=>step*(i+0.5);
 const xt=t=>{if(t>C[C.length-1].time)return null;const i=C.findIndex(c=>c.time>=t);return i<0?null:x(i)};
 const clipY=v=>Math.max(padT,Math.min(padT+ph,y(v)));
 g.font='11px system-ui';
 for(let k=0;k<=5;k++){const v=lo+(hi-lo)*k/5,yy=y(v);g.strokeStyle=bd;g.lineWidth=1;g.beginPath();g.moveTo(0,yy);g.lineTo(pw,yy);g.stroke();
  g.fillStyle=mut;g.textAlign='left';g.textBaseline='middle';g.fillText(v.toFixed(d.decimals),pw+4,yy);}
 g.textAlign='center';g.textBaseline='alphabetic';
 for(let k=0;k<4;k++){const i=Math.floor((C.length-1)*(k+0.5)/4);g.fillStyle=mut;
  g.fillText(new Date(C[i].time*1000).toISOString().slice(5,16).replace('T',' '),x(i),H-5);}
 const zc=s=>s==1?'22,163,74':s==-1?'220,38,38':'99,102,241';
 const box2=(t0,top,bot,s,label,a)=>{const xx=xt(t0);if(xx===null)return;const x0=Math.max(0,xx-step/2),y1=clipY(top),y2=clipY(bot);if(Math.abs(y2-y1)<1)return;
  g.fillStyle='rgba('+zc(s)+','+a+')';g.fillRect(x0,y1,pw-x0,y2-y1);g.strokeStyle='rgba('+zc(s)+',0.9)';g.lineWidth=1;g.strokeRect(x0,y1,pw-x0,y2-y1);
  if(label){g.fillStyle='rgb('+zc(s)+')';g.textAlign='left';g.textBaseline='top';g.fillText(label,x0+4,Math.min(y1,y2)+3)}};
 const ov=selView()&&selView().overlay;
 const tps=PL?(PL.targets&&PL.targets.length?PL.targets:[{label:'TP',price:PL.tp}]):[];
 if(AN&&AN.entry_zone&&!PL){const L0=C[Math.max(0,C.length-30)].time;box2(L0,AN.entry_zone.top,AN.entry_zone.bottom,AN.entry_zone.side,'منطقة الدخول',0.22)}
 if(PL){const t0=d.trade?Date.parse(d.trade.opened_at+'Z')/1000:C[Math.max(0,C.length-30)].time;
  const far=tps.reduce((m,t)=>Math.abs(t.price-PL.entry)>Math.abs(m.price-PL.entry)?t:m,tps[0]);
  box2(t0,far.price,PL.entry,1,'',0.08);box2(t0,PL.entry,PL.sl,-1,'',0.10)}
 if(ov)(ov.zones||[]).forEach(z=>box2(z.t0,z.top,z.bottom,z.side,z.label,0.16));
 const lineOf=(arr,col,w)=>{const m=new Map(arr.map(p=>[p.time,p.value]));g.strokeStyle=col;g.lineWidth=w;g.beginPath();let st=false;
  C.forEach((c,i)=>{const v=m.get(c.time);if(v===undefined){st=false;return}if(!st){g.moveTo(x(i),y(v));st=true}else g.lineTo(x(i),y(v))});g.stroke()};
 lineOf(d.ema200,'#a855f7',1.6);lineOf(d.ema50,'#f59e0b',1.2);lineOf(d.ema20,'#3b82f6',1.2);
 const bw=Math.max(1,step*0.65);
 C.forEach((c,i)=>{const col=c.close>=c.open?'#16a34a':'#dc2626';g.strokeStyle=col;g.fillStyle=col;g.lineWidth=1;
  g.beginPath();g.moveTo(x(i),y(c.high));g.lineTo(x(i),y(c.low));g.stroke();
  g.fillRect(x(i)-bw/2,y(Math.max(c.open,c.close)),bw,Math.max(1,Math.abs(y(c.open)-y(c.close))))});
 if(ov){(ov.lines||[]).forEach(l=>{if(l.price>hi||l.price<lo)return;const xx=xt(l.t0);if(xx===null)return;const x0=Math.max(0,xx);g.strokeStyle='#f59e0b';g.lineWidth=1.4;g.setLineDash([5,4]);
   g.beginPath();g.moveTo(x0,y(l.price));g.lineTo(pw,y(l.price));g.stroke();g.setLineDash([]);
   g.fillStyle='#f59e0b';g.textAlign='left';g.textBaseline='bottom';g.fillText(l.label,x0+4,y(l.price)-2)});
  (ov.points||[]).forEach(p=>{if(p.price>hi||p.price<lo||p.time<C[0].time)return;const px_=xt(p.time);if(px_===null)return;const py=y(p.price);g.fillStyle='#22d3ee';g.beginPath();g.arc(px_,py,4,0,7);g.fill();
   g.fillStyle=fg;g.textAlign='center';g.textBaseline='bottom';g.fillText(p.label,px_,py-6)})}
 if(PL){const L=[['دخول',PL.entry,'#9ca3af'],['وقف',PL.sl,'#dc2626']].concat(tps.map(t=>[t.label,t.price,'#16a34a']));
  L.forEach(([n,p,c])=>{if(p>hi||p<lo)return;
  g.strokeStyle=c;g.setLineDash([6,4]);g.lineWidth=1.5;g.beginPath();g.moveTo(0,y(p));g.lineTo(pw,y(p));g.stroke();g.setLineDash([]);
  g.fillStyle=c;g.textAlign='left';g.textBaseline='middle';g.fillText(n+' '+p.toFixed(d.decimals),4,y(p)-8)})}
 const last=A[tot-1].close;
 if(last<=hi&&last>=lo){g.fillStyle=fg;g.fillRect(pw,y(last)-8,padR,16);
  g.fillStyle=bg;g.textAlign='left';g.textBaseline='middle';g.fillText(last.toFixed(d.decimals),pw+4,y(last))}
 if(OFF>=1){g.fillStyle=mut;g.textAlign='left';g.textBaseline='top';g.fillText('◀ '+Math.round(OFF)+' شمعة عن الآن',6,padT+2)}
}
/* ---------- التحكم بالشارت: سحب + تكبير بإصبعين/عجلة + محور السعر ---------- */
function zoom(f){N=N*f;sched()}
function setN(v){N=v;sched()}
function goLive(){OFF=0;YO=0;sched()}
function resetView(){N=200;OFF=0;YO=0;YS=1;sched()}
(function(){
 const cv=document.getElementById('cv'),P=new Map();let last=null,pinch=null,axis=false,moved=0,tapT=0;
 const pos=e=>{const r=cv.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top}};
 cv.addEventListener('pointerdown',e=>{try{cv.setPointerCapture(e.pointerId)}catch(_){}
  const p=pos(e);P.set(e.pointerId,p);moved=0;
  if(P.size===1){axis=p.x>cv.clientWidth-66;last=p}
  if(P.size===2){const[a,b]=[...P.values()];pinch={d:Math.hypot(a.x-b.x,a.y-b.y),N:N}}});
 cv.addEventListener('pointermove',e=>{if(!P.has(e.pointerId))return;const p=pos(e);P.set(e.pointerId,p);
  if(P.size===2&&pinch){const[a,b]=[...P.values()];const dd=Math.max(Math.hypot(a.x-b.x,a.y-b.y),1);N=pinch.N*pinch.d/dd;sched();return}
  if(P.size===1&&last){const dx=p.x-last.x,dy=p.y-last.y;last=p;moved+=Math.abs(dx)+Math.abs(dy);
   if(axis){YS=Math.max(0.15,Math.min(8,YS*Math.exp(dy/160)))}
   else{const step=(cv.clientWidth-66)/N;OFF+=dx/step;YO+=dy*PPP}
   sched()}});
 const up=e=>{P.delete(e.pointerId);if(P.size<2)pinch=null;
  if(P.size===1)last=[...P.values()][0];
  if(P.size===0){last=null;
   if(moved<8){const t=Date.now();if(t-tapT<320){resetView();tapT=0}else tapT=t}}};
 cv.addEventListener('pointerup',up);cv.addEventListener('pointercancel',up);
 cv.addEventListener('wheel',e=>{e.preventDefault();
  if(e.shiftKey){OFF+=e.deltaY>0?-8:8}else{N=N*(e.deltaY>0?1.12:0.89)}sched()},{passive:false});
})();
const ic=b=>b==1?'🟢':b==-1?'🔴':'⚪';
const NM={ict:'ICT',smc:'SMC',elliott:'إليوت',technical:'فني'};
const cl=arr=>(arr||[]).map(c=>(NM[c.name]||c.name)+(c.mode==='signal'?'⚡':'◔')).join(' · ')||'—';
function row(v){return '<div class="r'+(v.name===SEL?' on':'')+'" data-n="'+v.name+'" onclick="pick(this.dataset.n)"><div>'+ic(v.bias)+' <b>'+v.title+'</b> '+(v.signal?'<span class="tag">إشارة</span>':'')+'</div><div class="m">'+v.text+'</div></div>'}
function views(){
 const el=document.getElementById('v'),a=AN;
 if(!a||!a.views){el.innerHTML='<div class="sum m">'+(MO?'لم يُحلَّل بعد: بانتظار إغلاق شمعة.':'السوق مغلق حالياً: لا يوجد تحليل جديد.')+'</div>';return}
 const bc=a.bias_counts||{};
 const dec={BUY:'شراء 🟢',SELL:'بيع 🔴',WAIT:'انتظار ⚪'}[a.decision]||a.decision;
 const htf={'1':'صاعد','-1':'هابط','0':'محايد'}[String(a.htf)];
 const f=v=>Number(v).toFixed(DATA.decimals),PL=DATA&&DATA.plan;
 let pl='';
 if(PL){pl='<br>📌 '+(PL.kind==='open'?'صفقة مفتوحة':'خطة الإشارة')+': دخول '+f(PL.entry)+' | ⛔ وقف '+f(PL.sl)+
   (PL.targets&&PL.targets.length?'<br>🎯 '+PL.targets.map(t=>t.label+' '+f(t.price)+' ('+t.r+'R)').join(' • '):'')+
   (PL.rr_net?'<br>صافي R:R بعد التكلفة: '+PL.rr_net:'')}
 const cr=a.core?'<br>🧩 تأكيد أساسي (المطلوب '+a.core.needed+'): 🟢 '+cl(a.core.buy)+' | 🔴 '+cl(a.core.sell)+' <span class="m">(⚡ إشارة مكتملة • ◔ إعداد مؤكد)</span>':'';
 let h='<div class="sum"><b>القرار: '+dec+'</b> | النقاط '+a.score+' (شراء '+a.long_score+' / بيع '+a.short_score+')<br>السوق: '+a.regime+' (ADX '+a.adx+') | اتجاه 1H: '+htf+'<br>آراء الاستراتيجيات: 🟢 '+bc.bull+' صاعد • 🔴 '+bc.bear+' هابط • ⚪ '+bc.neutral+' محايد'+cr+pl+
  (a.entry_zone?'<br>🎯 منطقة الدخول: '+f(a.entry_zone.bottom)+' – '+f(a.entry_zone.top):'')+
  (a.obstacle?'<br>⚠️ مستوى قريب قبل الهدف: '+f(a.obstacle.price)+' ('+a.obstacle.r+'R)':'')+
  (a.sl_capped?'<br>ℹ️ الإبطال الهيكلي أبعد من الحد الأقصى للوقف فتم تقييد الوقف':'')+
  (a.note?'<br>⚠️ '+a.note:'')+(a.skipped?'<br>⛔ لم تُنفَّذ: '+a.skipped:'')+'</div>';
 const sv=selView();
 if(sv){const emp=!sv.overlay||(!(sv.overlay.zones||[]).length&&!(sv.overlay.lines||[]).length&&!(sv.overlay.points||[]).length);
  h+='<div class="sel"><b>'+ic(sv.bias)+' '+sv.title+'</b><div class="m">'+sv.text+'</div>'+
   (sv.checks&&sv.checks.length?'<ul>'+sv.checks.map(c=>'<li>'+(c.ok?'✅':'❌')+' '+c.text+'</li>').join('')+'</ul>':'')+
   '<div class="hint">'+(emp?'لا يوجد إعداد حالي لرسمه على الشارت.':'مرسوم على الشارت أعلاه.')+'</div></div>'}
 h+='<h4>الاستراتيجيات الأساسية</h4><div class="hint">اضغط على أي استراتيجية لرؤية تحليلها على الشارت وقائمة شروطها.</div>'+a.views.filter(v=>v.core).map(row).join('');
 h+='<h4>الاستراتيجيات الداعمة</h4>'+a.views.filter(v=>!v.core).map(row).join('');
 el.innerHTML=h;
}
function pick(n){SEL=(n===null||SEL===n)?null:n;views();sched();if(SEL)window.scrollTo({top:0,behavior:'smooth'})}
async function load(){
 const inf=document.getElementById('i');
 try{
  const r=await fetch('/api/candles/'+SYM+'?limit=1000');
  if(!r.ok){inf.textContent='لا توجد بيانات بعد ('+r.status+') — تحقق من /api/status';return}
  const prevT=DATA&&DATA.candles.length?DATA.candles[DATA.candles.length-1].time:0;
  DATA=await r.json();
  if(OFF>=1&&prevT){OFF+=DATA.candles.filter(c=>c.time>prevT).length}   /* لا يقفز الشارت عند وصول شمعة جديدة */
  inf.textContent=(DATA.trade?(DATA.trade.side==1?'صفقة شراء مفتوحة':'صفقة بيع مفتوحة'):'لا توجد صفقة');
  const s=await (await fetch('/api/analyze/'+SYM)).json();AN=s.analysis;MO=s.market_open;
  views();draw();
 }catch(e){inf.textContent='خطأ: '+e}
}
addEventListener('resize',sched);load();setInterval(load,30000);
</script></body></html>"""


DASHBOARD = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Zero Reversal Engine</title>
<style>:root{color-scheme:light dark;--bg:#fff;--fg:#1a1a1a;--mut:#6b7280;--bd:#e5e7eb;--g:#16a34a;--r:#dc2626}
@media(prefers-color-scheme:dark){:root{--bg:#111318;--fg:#e8e8ea;--mut:#9aa0aa;--bd:#2a2e37}}
body{margin:0;padding:12px;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}
.w{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:620px}
th,td{padding:8px;border-bottom:1px solid var(--bd);text-align:right;white-space:nowrap}th{color:var(--mut);font-weight:500}
.b{color:var(--g);font-weight:600}.s{color:var(--r);font-weight:600}.m{color:var(--mut)}#acc{margin:6px 0 12px}</style></head><body>
<h3><span style="background:linear-gradient(90deg,#6366f1,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent">Zero Reversal Engine</span></h3><div id="acc" class="m"></div><div class="w"><table><thead><tr><th>الرمز</th><th>السعر</th><th>القرار</th><th>النقاط</th>
<th>السوق</th><th>الصفقة</th><th>ملاحظة</th></tr></thead><tbody id="t"></tbody></table></div>
<footer style="text-align:center;padding:22px 0;color:var(--mut)">Developed by <b style="background:linear-gradient(90deg,#6366f1,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent">aziz</b></footer>
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


@app.get("/chart/{symbol}", response_class=HTMLResponse)
async def chart_page(symbol: str):
    sym = symbol.upper()
    if sym not in engines:
        raise HTTPException(404, "رمز غير معروف")
    return CHART_PAGE.replace("__SYM__", sym)
