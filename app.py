import streamlit as st
import plotly.graph_objects as go
from core.data_fetcher import DataFetcher
from core.smc_engine import SMCEngine
from core.wave_engine import WaveEngine
from core.signal_aggregator import SignalAggregator

st.set_page_config(page_title="محلل التقاء الاستراتيجيات", layout="wide")
st.title("📊 محلل الكريبتو متعدد الاستراتيجيات")
st.caption("SMC/ICT + التحليل الموجي — إشارات دخول وخروج وأهداف ووقف خسارة")

# الشريط الجانبي
with st.sidebar:
    st.header("الإعدادات")
    symbol = st.selectbox("العملة", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"])
    timeframe = st.selectbox("الإطار الزمني", ["1h", "4h", "1d"], index=1)
    min_confluence = st.slider("الحد الأدنى للتوافق", 1, 3, 2,
                               help="عدد الاستراتيجيات التي يجب أن تتفق قبل إصدار قرار")
    refresh = st.button("🔄 تحديث التحليل")

@st.cache_data(ttl=120)
def run_analysis(symbol, timeframe, min_confluence):
    fetcher = DataFetcher()
    df = fetcher.fetch_ohlcv(symbol, timeframe)
    current_price = fetcher.get_current_price(symbol)

    smc_signal = SMCEngine().analyze(df)
    wave_signal = WaveEngine().analyze(df)

    aggregator = SignalAggregator(min_confluence=min_confluence)
    final = aggregator.aggregate([smc_signal, wave_signal])
    return df, current_price, smc_signal, wave_signal, final

try:
    with st.spinner("جاري جلب البيانات وتحليلها..."):
        df, current_price, smc_sig, wave_sig, final = run_analysis(symbol, timeframe, min_confluence)

    # عرض السعر الحالي
    st.metric("السعر الحالي", f"${current_price:,.2f}")

    # القرار النهائي
    st.header("🎯 القرار النهائي")
    if final["decision"] == "انتظار":
        st.warning(f"⏸️ **انتظار** — {final['reason']}")
    else:
        color = "green" if final["direction"] == "bullish" else "red"
        st.success(f"**القرار: {final['decision']}** (توافق {final['confluence_count']} استراتيجيات)")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("نقطة الدخول", f"${final['entry']:,.2f}")
        c2.metric("وقف الخسارة", f"${final['stop_loss']:,.2f}")
        c3.metric("الهدف", f"${final['take_profit']:,.2f}" if final["take_profit"] else "—")
        c4.metric("نسبة المخاطرة/العائد", f"1:{final['risk_reward']}" if final["risk_reward"] else "—")

        st.caption(f"الاستراتيجيات المتفقة: {', '.join(final['confluence_strategies'])}")

    # تفاصيل كل استراتيجية
    st.header("🔍 تفاصيل الاستراتيجيات")
    tab1, tab2 = st.tabs(["SMC / ICT", "التحليل الموجي"])
    with tab1:
        st.json(smc_sig)
    with tab2:
        st.json(wave_sig)

    # الرسم البياني
    st.header("📈 الرسم البياني")
    fig = go.Figure(data=[go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color="green", decreasing_line_color="red"
    )])
    if final["entry"]:
        fig.add_hline(y=final["entry"], line_dash="dash", line_color="blue", annotation_text="Entry")
        fig.add_hline(y=final["stop_loss"], line_dash="dot", line_color="red", annotation_text="SL")
        if final["take_profit"]:
            fig.add_hline(y=final["take_profit"], line_dash="dot", line_color="green", annotation_text="TP")
    fig.update_layout(xaxis_rangeslider_visible=False, height=550)
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"حدث خطأ: {e}")
