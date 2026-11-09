"""
apply_changes.py - يطبّق تعديلات "نسبة النجاح فوق 70%" على app.py تلقائياً.
الاستخدام:   python apply_changes.py app.py
- ينسخ النسخة الأصلية إلى app.py.bak أولاً.
- لا يلمس سطر TELEGRAM_TOKEN (يتحقق من ذلك قبل الحفظ).
- إن لم يجد أحد المواضع يتوقف دون أي تعديل.
"""
import re
import shutil
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "app.py"
src = open(path, encoding="utf-8").read()
if "HTF_HARD" in src:
    print("التعديلات مطبّقة مسبقاً (وُجد HTF_HARD). لم يتغير شيء.")
    sys.exit(0)


def token_line(s):
    return next((l for l in s.splitlines() if l.startswith("TELEGRAM_TOKEN")), "")


orig_token = token_line(src)
out = src


def sub1(old, new, name):
    global out
    if out.count(old) != 1:
        sys.exit(f"تعذّر العثور على الموضع بشكل فريد: {name}. لم يُحفظ أي تعديل.")
    out = out.replace(old, new)


# 1) القيم الافتراضية
sub1('CORE_CONFIRM = _i("CORE_CONFIRM", 2)', 'CORE_CONFIRM = _i("CORE_CONFIRM", 3)', "CORE_CONFIRM")
sub1('MIN_SCORE = _f("MIN_SCORE", 1.0)', 'MIN_SCORE = _f("MIN_SCORE", 2.0)', "MIN_SCORE")
sub1('MIN_SL_ATR = _f("MIN_SL_ATR", 1.0)', 'MIN_SL_ATR = _f("MIN_SL_ATR", 2.0)', "MIN_SL_ATR")
sub1('RISK_REWARD = _f("RISK_REWARD", 2.0)', 'RISK_REWARD = _f("RISK_REWARD", 0.3)', "RISK_REWARD")

# 2) متغيران جديدان
sub1('ATR_SL_MULT = _f("ATR_SL_MULT", 1.5)',
     'HTF_HARD = _b("HTF_HARD", "1")                  # إلزام اتفاق اتجاه 1H\n'
     'MIN_ADX = _f("MIN_ADX", 20)                     # أقل قوة اتجاه ADX\n'
     'ATR_SL_MULT = _f("ATR_SL_MULT", 1.5)', "ATR_SL_MULT")

# 3) فلتران جديدان داخل analyze بعد فلتر الإشارة الحدّية
anchor = '        res["note"] = "إشارة حدّية: تحتاج توافق اتجاه الساعة (1H)"\n        return res\n'
sub1(anchor, anchor +
     '    if HTF_HARD and htf != side:\n'
     '        res["note"] = "اتجاه 1H لا يوافق الإشارة"\n'
     '        return res\n'
     '    if adx_v < MIN_ADX:\n'
     '        res["note"] = f"ADX {adx_v:.0f} أقل من {MIN_ADX:g}"\n'
     '        return res\n', "فلاتر 1H/ADX")

# 4) هدف واحد عندما RR < 1
m = re.search(r'    targets = \[\{"label": "TP1".*?\]\n', out, flags=re.S)
if not m:
    sys.exit("تعذّر العثور على قائمة targets. لم يُحفظ أي تعديل.")
out = out[:m.start()] + (
    '    targets = [{"label": "TP", "r": round(rr, 2)}] if rr < 1 else [\n'
    '        {"label": "TP1", "r": 1.0}, {"label": "TP2", "r": round(rr, 2)},\n'
    '        {"label": "TP3", "r": round(max(3.0, rr + 1.0), 2)}]\n') + out[m.end():]
sub1('    if ell and ell.get("tgt") is not None:', '    if rr >= 1 and ell and ell.get("tgt") is not None:', "هدف إليوت")

if token_line(out) != orig_token:
    sys.exit("خطأ أمان: سطر التوكن تغيّر. أُلغي الحفظ.")
compile(out, path, "exec")  # يتأكد أن الملف سليم لغوياً
shutil.copy(path, path + ".bak")
open(path, "w", encoding="utf-8").write(out)
print("تم. النسخة الأصلية في", path + ".bak", "- سطر التوكن لم يتغير.")
