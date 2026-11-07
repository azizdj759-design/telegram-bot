import re
S = open("/mnt/user-data/outputs/app.py", encoding="utf-8").read()


def rep(old, new, count=1):
    global S
    assert old in S, "anchor not found: " + old[:60]
    S = S.replace(old, new, count)


# ---------------------------------------------------------------- 1) الإعدادات
rep("MIN_BARS = 150\n", """MIN_BARS = 150
BAR_FETCH = _i("BAR_FETCH", 600)                 # عدد الشموع المحمّلة (للعرض والتحليل)
REQUIRE_CORE = _b("REQUIRE_CORE", "1")           # الصفقة تتطلب موافقة استراتيجية أساسية واحدة على الأقل
""")

# ---------------------------------------------------------------- 2) جلب شموع أكثر
i0 = S.index("    async def _okx(self, symbol, bars):")
i1 = S.index("    async def _tv(self, spec, bars):")
S = S[:i0] + '''    async def _okx(self, symbol, bars):
        sym = symbol.replace("USDT", "/USDT")
        raw = []
        if bars > 300:
            try:   # تجميع صفحات (best-effort)
                ms = BAR_MINUTES * 60 * 1000
                since = int(time.time() * 1000) - bars * ms
                for _ in range(bars // 100 + 4):
                    chunk = await self.okx.fetch_ohlcv(sym, "15m", since=since, limit=100)
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
            raw = await self.okx.fetch_ohlcv(sym, "15m", limit=min(bars, 300))
        if not raw:
            return None
        df = pd.DataFrame(raw, columns=["time", "Open", "High", "Low", "Close", "Volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        df = clean_ohlc(df.set_index("time")).tail(bars)
        return df if len(df) >= 100 else None

''' + S[i1:]
rep("df, src = await provider.fetch(self.symbol, self.spec)", "df, src = await provider.fetch(self.symbol, self.spec, BAR_FETCH)")

# ---------------------------------------------------------------- 3) Signal + _sig
rep("    sl: Optional[float] = None     # سعر الوقف الهيكلي المقترح (نقطة إبطال الفكرة)\n",
    "    sl: Optional[float] = None     # سعر الوقف الهيكلي المقترح (نقطة إبطال الفكرة)\n    zone: Optional[tuple] = None   # منطقة الدخول (أعلى، أدنى)\n")
rep('''def _sig(name, side, strength, reason, sl=None):
    sl = float(sl) if sl is not None and sl == sl else None
    return Signal(name, side, round(min(float(strength), 1.0), 2), reason, sl)''',
    '''def _sig(name, side, strength, reason, sl=None, zone=None):
    sl = float(sl) if sl is not None and sl == sl else None
    zone = (float(max(zone)), float(min(zone))) if zone else None
    return Signal(name, side, round(min(float(strength), 1.0), 2), reason, sl, zone)''')

# ---------------------------------------------------------------- 4) الاستراتيجيات الأساسية الأربع
CORE = r'''
# ============================== الاستراتيجيات الأساسية الأربع ==============================
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


def _memo(x, key, fn):
    cache = x.attrs.setdefault("scans", {})
    if key not in cache:
        cache[key] = fn(x)
    return cache[key]


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
    a = x.iloc[-1]
    atr_ = float(a.atr)
    P = lambda v: float(v) * side
    ov, chk = _ov(), []
    pl = pivots(ll, 3, "L", n - 90, n - 4)
    ph = pivots(hh, 3, "H", n - 90, n)
    s = q = None
    for si in range(n - 3, max(n - 16, 10), -1):          # أحدث سحب سيولة أولاً
        for qi in reversed(pl):
            if qi < si - 3 and ll[si] < ll[qi] and cc[si] > ll[qi]:
                s, q = si, qi
                break
        if s is not None:
            break
    chk.append((s is not None, "سحب سيولة: كسر قاع سابق ثم إغلاق فوقه" if side == 1 else "سحب سيولة: كسر قمة سابقة ثم إغلاق تحتها"))
    jj = lvl = fvg = None
    zt = zb = None
    disp = fresh = disc = inz = legok = False
    if s is not None:
        ov["lines"].append(_ln(x, q, P(ll[q]), "سيولة سُحبت"))
        ov["points"].append(_pt(x, s, P(ll[s]), "Sweep"))
        prev = [i for i in ph if i < s]
        if prev:
            lvl = hh[prev[-1]]
            ov["lines"].append(_ln(x, prev[-1], P(lvl), "MSS"))
            jj = next((j for j in range(s + 1, n) if cc[j] > lvl), None)
    chk.append((jj is not None, "كسر هيكل السوق (MSS) بعد السحب"))
    if jj is not None:
        disp = any(cc[k] - oo[k] >= 0.8 * atr_ for k in range(s, jj + 1))
        hi_, lo_ = hh[s:].max(), ll[s]
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
            "signal": sig, "overlay": best["overlay"] if best["stage"] >= 1 else _ov(), "checks": _chk(best["checks"])}


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
            "signal": sig, "overlay": best["overlay"] if best["stage"] >= 1 else _ov(), "checks": _chk(best["checks"])}


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
    label = ""
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
            "overlay": ov, "checks": chk, "sl": sl, "text": txt, "strength": strength, "txt_sig": txt}


def _scan_elliott(x):
    rs = [_ell_dir(x, sd) for sd in (1, -1)]
    best = max(rs, key=lambda d: (d["trigger"], d["ok2"], d["stage"]))
    sig = _sig("elliott", best["side"], best["strength"], "إليوت: " + best["txt_sig"], sl=best["sl"]) if best["trigger"] else None
    return {"bias": best["side"] if best["ok2"] else 0,
            "text": best["text"] or "لا عدّ إليوت صالح حالياً: آخر المحاور لا تحقق قواعد الموجة 1-2",
            "signal": sig, "overlay": best["overlay"], "checks": _chk(best["checks"])}


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
    near_lv = [v for v in (sup if side == 1 else res) if (v - a.Close) * side <= 0]
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
    return {"side": side, "stage": sum(bool(o) for o, _ in chk), "trigger": ok, "overlay": ov, "checks": chk,
            "sl": float(sl), "strength": strength, "text": txt, "pname": pname if trig_a else "كسر وإعادة اختبار"}


def _scan_tech(x):
    rs = [_tech_dir(x, sd) for sd in (1, -1)]
    best = max(rs, key=lambda d: (d["trigger"], d["stage"]))
    sig = _sig("technical", best["side"], best["strength"],
               f"التحليل الفني: اتجاه + زخم + قوة + محفز ({best['pname']})", sl=best["sl"]) if best["trigger"] else None
    return {"bias": best["side"] if best["stage"] >= 3 else 0, "text": best["text"], "signal": sig,
            "overlay": best["overlay"], "checks": _chk(best["checks"])}


SCANS = {"ict": _scan_ict, "smc": _scan_smc, "elliott": _scan_elliott, "technical": _scan_tech}
strat_ict = lambda x: _memo(x, "ict", _scan_ict)["signal"]
strat_smc = lambda x: _memo(x, "smc", _scan_smc)["signal"]
strat_elliott = lambda x: _memo(x, "elliott", _scan_elliott)["signal"]
strat_technical = lambda x: _memo(x, "technical", _scan_tech)["signal"]


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


'''
rep("# (الاسم، الدالة، الوزن، النوع)\nSTRATEGIES", CORE + "# (الاسم، الدالة، الوزن، النوع)\nSTRATEGIES")
rep("STRATEGIES: list[tuple[str, Callable, float, str]] = [\n",
    '''STRATEGIES: list[tuple[str, Callable, float, str]] = [
    ("ict", strat_ict, 1.8, "core"),
    ("smc", strat_smc, 1.8, "core"),
    ("elliott", strat_elliott, 1.4, "core"),
    ("technical", strat_technical, 1.5, "core"),
''')

# ---------------------------------------------------------------- 5) شرح الاستراتيجيات الأساسية
INFO = r'''STRATEGY_INFO.update({
    "ict": {
        "title": "ICT — سحب السيولة + MSS + OTE", "regime": "أساسية (أي نظام)",
        "entry": ["سحب سيولة: شمعة (آخر 15) كسرت قاع سابق مؤكد وأغلقت فوقه (للبيع: قمة وأغلقت تحتها)",
                  "MSS: إغلاق لاحق فوق آخر قمة مؤكدة قبل السحب، مع شمعة اندفاع جسمها ≥ 0.8 ATR",
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


'''
rep("def regime_multiplier(regime: str, kind: str) -> float:\n    if kind == \"neutral\" or regime == \"mixed\":",
    INFO + "def regime_multiplier(regime: str, kind: str) -> float:\n    if kind in (\"neutral\", \"core\") or regime == \"mixed\":")

# ---------------------------------------------------------------- 6) build_views
i0 = S.index("def build_views(x, found, regime):")
i1 = S.index("def _wait(")
S = S[:i0] + '''def build_views(x, found, regime):
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


''' + S[i1:]

# ---------------------------------------------------------------- 7) analyze: شرط الأساسية + منطقة الدخول
rep('''    if win < STRICT_SCORE and htf != side:
        res["note"] = "إشارة حدّية: تحتاج توافق اتجاه الساعة (1H)"
        return res
''', '''    if win < STRICT_SCORE and htf != side:
        res["note"] = "إشارة حدّية: تحتاج توافق اتجاه الساعة (1H)"
        return res
    if REQUIRE_CORE and not any(s.side == side and s.name in SCANS for s in found):
        res["note"] = "لا توجد موافقة من استراتيجية أساسية (ICT / SMC / إليوت / التحليل الفني)"
        return res
''')
rep('''    res.update({"decision": "BUY" if side == 1 else "SELL", "side": side})
    return res''', '''    zs = [s.zone for s in found if s.side == side and s.zone]
    if zs:
        ez = {"top": zs[0][0], "bottom": zs[0][1]}
    else:
        ez = {"top": entry + 0.15 * atr_v, "bottom": entry - 0.15 * atr_v}
    res["entry_zone"] = {**ez, "side": side}
    res.update({"decision": "BUY" if side == 1 else "SELL", "side": side})
    return res''')

# ---------------------------------------------------------------- 8) رسالة تليغرام بمنطقة الدخول
rep('''        src = "هيكلي" if t.sl_source == "structure" else "ATR"\n''',
    '''        src = "هيكلي" if t.sl_source == "structure" else "ATR"
        z = a.get("entry_zone")
        ez = f"منطقة الدخول: <code>{fmt(z['bottom'], sp)} – {fmt(z['top'], sp)}</code>\\n" if z else ""\n''')
rep('''f"الدخول: <code>{fmt(t.entry, sp)}</code>\\n"\n''', '''f"الدخول: <code>{fmt(t.entry, sp)}</code>\\n{ez}"\n''')

# ---------------------------------------------------------------- 9) api_candles حتى 1000
rep('async def api_candles(symbol: str, limit: int = Query(200, ge=50, le=300)):',
    'async def api_candles(symbol: str, limit: int = Query(400, ge=50, le=1000)):')

# ---------------------------------------------------------------- 10) صفحة الشارت الجديدة
c0 = S.index('CHART_PAGE = """')
c1 = S.index('@app.get("/chart/{symbol}"')
CHART = r'''CHART_PAGE = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__SYM__ — Zero Reversal</title>
<style>:root{color-scheme:light dark;--bg:#fff;--fg:#1a1a1a;--mut:#6b7280;--bd:#e5e7eb;--card:#f3f4f6;--acc:#6366f1}
@media(prefers-color-scheme:dark){:root{--bg:#0f1117;--fg:#e8e8ea;--mut:#9aa0aa;--bd:#262a33;--card:#181b23}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}
header{display:flex;gap:10px;align-items:center;padding:10px 12px;flex-wrap:wrap}a{color:inherit}.m{color:var(--mut)}
.logo{font-weight:800;background:linear-gradient(90deg,#6366f1,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent}
#box{height:50vh;min-height:300px;direction:ltr;position:relative}canvas{display:block}
.lg{padding:2px 12px 6px;font-size:12px;display:flex;gap:12px;flex-wrap:wrap}.lg i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-inline-end:4px}
.bt{display:flex;gap:8px;padding:0 12px 8px;flex-wrap:wrap}.bt button{background:var(--card);color:var(--fg);border:1px solid var(--bd);border-radius:8px;padding:6px 12px}
#v{padding:0 12px 12px}.sum,.sel{background:var(--card);border-radius:12px;padding:10px;margin-bottom:10px;line-height:1.7}
.sel{border:1px solid var(--acc)}.sel ul{margin:6px 0 0;padding-inline-start:18px}.sel li{margin:2px 0;list-style:none;margin-inline-start:-18px}
h4{margin:14px 0 4px;color:var(--acc)}.r{border-bottom:1px solid var(--bd);padding:9px 6px;cursor:pointer;border-radius:8px}
.r.on{background:var(--card);outline:1px solid var(--acc)}.tag{background:#16a34a;color:#fff;border-radius:6px;padding:1px 6px;font-size:12px}
.hint{font-size:12px;color:var(--mut);margin:4px 0}
footer{text-align:center;padding:18px 0 28px;color:var(--mut);font-size:13px}footer b{background:linear-gradient(90deg,#6366f1,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent}</style></head><body>
<header><a href="/">← الرئيسية</a><span class="logo">Zero Reversal</span><b>__SYM__</b><span id="i" class="m"></span></header>
<div id="box"><canvas id="cv"></canvas></div>
<div class="lg m"><span><i style="background:#3b82f6"></i>EMA20</span><span><i style="background:#f59e0b"></i>EMA50</span><span><i style="background:#a855f7"></i>EMA200</span></div>
<div class="bt"><button onclick="N=100;draw()">100</button><button onclick="N=200;draw()">200</button><button onclick="N=400;draw()">400</button><button onclick="N=600;draw()">600</button><button onclick="pick(null)">إلغاء التحديد</button></div>
<div id="v"></div>
<footer>Developed by <b>aziz</b></footer>
<script>
const SYM='__SYM__';let DATA=null,AN=null,MO=true,N=200,SEL=null;
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const selView=()=>AN&&AN.views&&SEL?AN.views.find(v=>v.name===SEL):null;
function draw(){
 const d=DATA;if(!d||!d.candles.length)return;
 const cv=document.getElementById('cv'),box=document.getElementById('box'),dpr=window.devicePixelRatio||1;
 const W=box.clientWidth,H=box.clientHeight;
 cv.width=W*dpr;cv.height=H*dpr;cv.style.width=W+'px';cv.style.height=H+'px';
 const g=cv.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,W,H);
 const fg=css('--fg'),mut=css('--mut'),bd=css('--bd'),bg=css('--bg');
 const C=d.candles.slice(-N),padR=66,padB=20,padT=8,pw=W-padR,ph=H-padB-padT;
 let hi=-Infinity,lo=Infinity;C.forEach(c=>{hi=Math.max(hi,c.high);lo=Math.min(lo,c.low)});
 const T=d.trade;if(T){[T.entry,T.sl,T.tp].forEach(v=>{hi=Math.max(hi,v);lo=Math.min(lo,v)})}
 const pad=(hi-lo)*0.06||1;hi+=pad;lo-=pad;
 const y=v=>padT+(hi-v)/(hi-lo)*ph,step=pw/C.length,x=i=>step*(i+0.5);
 const xt=t=>{let i=C.findIndex(c=>c.time>=t);if(i<0)i=C.length-1;return x(i)};
 const clipY=v=>Math.max(padT,Math.min(padT+ph,y(v)));
 g.font='11px system-ui';
 for(let k=0;k<=5;k++){const v=lo+(hi-lo)*k/5,yy=y(v);g.strokeStyle=bd;g.lineWidth=1;g.beginPath();g.moveTo(0,yy);g.lineTo(pw,yy);g.stroke();
  g.fillStyle=mut;g.textAlign='left';g.textBaseline='middle';g.fillText(v.toFixed(d.decimals),pw+4,yy);}
 g.textAlign='center';g.textBaseline='alphabetic';
 for(let k=0;k<4;k++){const i=Math.floor((C.length-1)*(k+0.5)/4);g.fillStyle=mut;
  g.fillText(new Date(C[i].time*1000).toISOString().slice(5,16).replace('T',' '),x(i),H-5);}
 const zc=s=>s==1?'22,163,74':s==-1?'220,38,38':'99,102,241';
 const box2=(t0,top,bot,s,label,a)=>{const x0=Math.max(0,xt(t0)-step/2),y1=clipY(top),y2=clipY(bot);if(Math.abs(y2-y1)<1)return;
  g.fillStyle='rgba('+zc(s)+','+a+')';g.fillRect(x0,y1,pw-x0,y2-y1);g.strokeStyle='rgba('+zc(s)+',0.9)';g.lineWidth=1;g.strokeRect(x0,y1,pw-x0,y2-y1);
  if(label){g.fillStyle='rgb('+zc(s)+')';g.textAlign='left';g.textBaseline='top';g.fillText(label,x0+4,Math.min(y1,y2)+3)}};
 const ov=selView()&&selView().overlay;
 if(AN&&AN.entry_zone&&!T){const L0=C[Math.max(0,C.length-30)].time;box2(L0,AN.entry_zone.top,AN.entry_zone.bottom,AN.entry_zone.side,'منطقة الدخول',0.22)}
 if(T){const t0=Date.parse(T.opened_at+'Z')/1000;box2(t0,T.tp,T.entry,1,'',0.10);box2(t0,T.entry,T.sl,-1,'',0.10)}
 if(ov)(ov.zones||[]).forEach(z=>box2(z.t0,z.top,z.bottom,z.side,z.label,0.16));
 const lineOf=(arr,col,w)=>{const m=new Map(arr.map(p=>[p.time,p.value]));g.strokeStyle=col;g.lineWidth=w;g.beginPath();let st=false;
  C.forEach((c,i)=>{const v=m.get(c.time);if(v===undefined){st=false;return}if(!st){g.moveTo(x(i),y(v));st=true}else g.lineTo(x(i),y(v))});g.stroke()};
 lineOf(d.ema200,'#a855f7',1.6);lineOf(d.ema50,'#f59e0b',1.2);lineOf(d.ema20,'#3b82f6',1.2);
 const bw=Math.max(1,step*0.65);
 C.forEach((c,i)=>{const col=c.close>=c.open?'#16a34a':'#dc2626';g.strokeStyle=col;g.fillStyle=col;g.lineWidth=1;
  g.beginPath();g.moveTo(x(i),y(c.high));g.lineTo(x(i),y(c.low));g.stroke();
  g.fillRect(x(i)-bw/2,y(Math.max(c.open,c.close)),bw,Math.max(1,Math.abs(y(c.open)-y(c.close))))});
 if(ov){(ov.lines||[]).forEach(l=>{if(l.price>hi||l.price<lo)return;const x0=Math.max(0,xt(l.t0));g.strokeStyle='#f59e0b';g.lineWidth=1.4;g.setLineDash([5,4]);
   g.beginPath();g.moveTo(x0,y(l.price));g.lineTo(pw,y(l.price));g.stroke();g.setLineDash([]);
   g.fillStyle='#f59e0b';g.textAlign='left';g.textBaseline='bottom';g.fillText(l.label,x0+4,y(l.price)-2)});
  (ov.points||[]).forEach(p=>{if(p.price>hi||p.price<lo)return;const px_=xt(p.time),py=y(p.price);g.fillStyle='#22d3ee';g.beginPath();g.arc(px_,py,4,0,7);g.fill();
   g.fillStyle=fg;g.textAlign='center';g.textBaseline='bottom';g.fillText(p.label,px_,py-6)})}
 if(T){[['دخول',T.entry,'#9ca3af'],['وقف',T.sl,'#dc2626'],['هدف',T.tp,'#16a34a']].forEach(([n,p,c])=>{
  g.strokeStyle=c;g.setLineDash([6,4]);g.lineWidth=1.5;g.beginPath();g.moveTo(0,y(p));g.lineTo(pw,y(p));g.stroke();g.setLineDash([]);
  g.fillStyle=c;g.textAlign='left';g.textBaseline='middle';g.fillText(n+' '+p.toFixed(d.decimals),4,y(p)-8)})}
 const last=C[C.length-1].close;g.fillStyle=fg;g.fillRect(pw,y(last)-8,padR,16);
 g.fillStyle=bg;g.textAlign='left';g.textBaseline='middle';g.fillText(last.toFixed(d.decimals),pw+4,y(last));
}
const ic=b=>b==1?'🟢':b==-1?'🔴':'⚪';
function row(v){return '<div class="r'+(v.name===SEL?' on':'')+'" onclick="pick(\''+v.name+'\')"><div>'+ic(v.bias)+' <b>'+v.title+'</b> '+(v.signal?'<span class="tag">إشارة</span>':'')+'</div><div class="m">'+v.text+'</div></div>'}
function views(){
 const el=document.getElementById('v'),a=AN;
 if(!a||!a.views){el.innerHTML='<div class="sum m">'+(MO?'لم يُحلَّل بعد: بانتظار إغلاق شمعة.':'السوق مغلق حالياً: لا يوجد تحليل جديد.')+'</div>';return}
 const bc=a.bias_counts||{};
 const dec={BUY:'شراء 🟢',SELL:'بيع 🔴',WAIT:'انتظار ⚪'}[a.decision]||a.decision;
 const htf={'1':'صاعد','-1':'هابط','0':'محايد'}[String(a.htf)];
 let h='<div class="sum"><b>القرار: '+dec+'</b> | النقاط '+a.score+' (شراء '+a.long_score+' / بيع '+a.short_score+')<br>السوق: '+a.regime+' (ADX '+a.adx+') | اتجاه 1H: '+htf+'<br>آراء الاستراتيجيات: 🟢 '+bc.bull+' صاعد • 🔴 '+bc.bear+' هابط • ⚪ '+bc.neutral+' محايد'+
  (a.entry_zone?'<br>🎯 منطقة الدخول: '+a.entry_zone.bottom.toFixed(DATA.decimals)+' – '+a.entry_zone.top.toFixed(DATA.decimals):'')+
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
function pick(n){SEL=(n===null||SEL===n)?null:n;views();draw();if(SEL)window.scrollTo({top:0,behavior:'smooth'})}
async function load(){
 const inf=document.getElementById('i');
 try{
  const r=await fetch('/api/candles/'+SYM+'?limit=600');
  if(!r.ok){inf.textContent='لا توجد بيانات بعد ('+r.status+') — تحقق من /api/status';return}
  DATA=await r.json();
  inf.textContent=(DATA.trade?(DATA.trade.side==1?'صفقة شراء مفتوحة':'صفقة بيع مفتوحة'):'لا توجد صفقة');
  const s=await (await fetch('/api/analyze/'+SYM)).json();AN=s.analysis;MO=s.market_open;
  views();draw();
 }catch(e){inf.textContent='خطأ: '+e}
}
addEventListener('resize',draw);load();setInterval(load,30000);
</script></body></html>"""


'''
S = S[:c0] + CHART + S[c1:]

# ---------------------------------------------------------------- 11) هوية الصفحة الرئيسية
rep('<h3>Zero Reversal Engine</h3>', '<h3><span style="background:linear-gradient(90deg,#6366f1,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent">Zero Reversal Engine</span></h3>')
rep('</tbody></table></div>\n<script>', '</tbody></table></div>\n<footer style="text-align:center;padding:22px 0;color:var(--mut)">Developed by <b style="background:linear-gradient(90deg,#6366f1,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent">aziz</b></footer>\n<script>')

open("/mnt/user-data/outputs/app.py", "w", encoding="utf-8").write(S)
print("patched OK", len(S.splitlines()))
