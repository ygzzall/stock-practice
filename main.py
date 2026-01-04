import streamlit as st
import yfinance as yf
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- SAYFA AYARLARI (Mobilde tam ekran görünmesi için) ---
st.set_page_config(page_title="Yapay Zeka Borsa Analizi", page_icon="📈", layout="wide")

# --- BAŞLIK ---
st.title("📱 Cep Analiz Kokpiti v5.0")
st.markdown("Yapay Zeka Destekli Teknik Analiz ve Yorumlama")

# --- SIDEBAR (MOBİLDE SOL MENÜ) ---
st.sidebar.header("⚙️ Ayarlar")

# 1. Girişler
piyasa_secimi = st.sidebar.selectbox("Piyasa Seçiniz:", ["🇹🇷 BIST", "🇺🇸 ABD", "₿ Kripto"])
sembol_giris = st.sidebar.text_input("Hisse Kodu (Örn: THYAO, AAPL, BTC):", value="THYAO").upper()
vade_secimi = st.sidebar.selectbox("Vade Seçiniz:",
                                   ["1 Hafta (15dk)", "1 Ay (Saatlik)", "6 Ay (Günlük)", "1 Yıl (Günlük)"])

# 2. Sembol ve Vade Ayarı
if piyasa_secimi == "🇹🇷 BIST":
    sembol = sembol_giris + ".IS" if ".IS" not in sembol_giris else sembol_giris
elif piyasa_secimi == "₿ Kripto":
    sembol = sembol_giris + "-USD" if "-USD" not in sembol_giris else sembol_giris
else:
    sembol = sembol_giris

if "1 Hafta" in vade_secimi:
    p, i = "5d", "15m"
elif "1 Ay" in vade_secimi:
    p, i = "1mo", "60m"
elif "6 Ay" in vade_secimi:
    p, i = "6mo", "1d"
else:
    p, i = "1y", "1d"


# --- ANALİZ MOTORLARI ---
def profesyonel_yorum_uret(df):
    son = df.iloc[-1]
    fiyat = son['Close']
    rsi = son['RSI_14']
    mfi = son['MFI_14']

    st_col = [c for c in df.columns if c.startswith('SUPERT_')][0]
    sma_col = [c for c in df.columns if c.startswith('SMA_50')][0]
    macd_col = [c for c in df.columns if c.startswith('MACD_')][0]
    macds_col = [c for c in df.columns if c.startswith('MACDs_')][0]
    bbu_col = [c for c in df.columns if c.startswith('BBU_')][0]
    bbl_col = [c for c in df.columns if c.startswith('BBL_')][0]

    supertrend = son[st_col]
    sma50 = son[sma_col]
    macd = son[macd_col]
    sinyal = son[macds_col]
    bb_ust = son[bbu_col]
    bb_alt = son[bbl_col]

    # PUANLAMA
    puan = 50
    if fiyat > sma50: puan += 10
    if fiyat > supertrend: puan += 10
    if rsi > 50: puan += 5
    if macd > sinyal: puan += 15
    if mfi > 50: puan += 10

    # METİNLER
    if (fiyat > sma50) and (fiyat > supertrend):
        trend = "🟢 GÜÇLÜ BOĞA (YÜKSELİŞ)"
    elif (fiyat < sma50) and (fiyat < supertrend):
        trend = "🔴 GÜÇLÜ AYI (DÜŞÜŞ)"
    else:
        trend = "🟠 YATAY / KARARSIZ"

    if puan >= 80:
        oneri = "🚀 GÜÇLÜ AL"
    elif 60 <= puan < 80:
        oneri = "✅ ALIM BÖLGESİ"
    elif 40 <= puan < 60:
        oneri = "👀 İZLE / NÖTR"
    elif 20 <= puan < 40:
        oneri = "⚠️ SATIŞ BASKISI"
    else:
        oneri = "❌ GÜÇLÜ SAT"

    uyari = "Normal seyir."
    if fiyat > bb_ust: uyari = "⚠️ Bollinger üstü delindi (Kâr satışı riski)."
    if fiyat < bb_alt: uyari = "⚡ Bollinger altı delindi (Tepki fırsatı)."
    if rsi > 75: uyari += " 🔥 RSI Aşırı Şişti!"
    if rsi < 25: uyari += " 💎 RSI Aşırı Ucuz!"

    return puan, trend, oneri, uyari


def grafik_ciz(df, sembol):
    # İndikatör Sütunları
    st_col = [c for c in df.columns if c.startswith('SUPERT_')][0]
    sma_col = [c for c in df.columns if c.startswith('SMA_50')][0]
    bbu_col = [c for c in df.columns if c.startswith('BBU_')][0]
    bbl_col = [c for c in df.columns if c.startswith('BBL_')][0]
    macd_col = [c for c in df.columns if c.startswith('MACD_')][0]
    macdh_col = [c for c in df.columns if c.startswith('MACDh_')][0]
    macds_col = [c for c in df.columns if c.startswith('MACDs_')][0]

    # Grafik
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.50, 0.15, 0.15, 0.20],
        subplot_titles=(f"{sembol} Fiyat", "RSI", "MFI", "MACD")
    )

    # Panel 1
    fig.add_trace(
        go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Fiyat"),
        row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df[sma_col], line=dict(color='orange', width=2), name="SMA 50"), row=1,
                  col=1)
    fig.add_trace(
        go.Scatter(x=df.index, y=df[st_col], line=dict(color='red', width=1.5, dash='dot'), name="SuperTrend"), row=1,
        col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df[bbu_col], line=dict(color='gray', width=1, dash='dash'), name="BB Üst"),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df[bbl_col], line=dict(color='gray', width=1, dash='dash'), fill='tonexty',
                             name="BB Alt"), row=1, col=1)

    # Panel 2 (RSI)
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI_14'], line=dict(color='purple', width=2), name="RSI"), row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)

    # Panel 3 (MFI)
    fig.add_trace(go.Scatter(x=df.index, y=df['MFI_14'], line=dict(color='blue', width=2), name="MFI"), row=3, col=1)
    fig.add_hline(y=20, line_dash="dot", line_color="green", row=3, col=1)
    fig.add_hline(y=80, line_dash="dot", line_color="red", row=3, col=1)

    # Panel 4 (MACD)
    colors = ['green' if val >= 0 else 'red' for val in df[macdh_col]]
    fig.add_trace(go.Bar(x=df.index, y=df[macdh_col], marker_color=colors, name="MACD Hist"), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df[macd_col], line=dict(color='black', width=1), name="MACD"), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df[macds_col], line=dict(color='orange', width=1), name="Sinyal"), row=4,
                  col=1)

    fig.update_layout(height=800, xaxis_rangeslider_visible=False, showlegend=False,
                      margin=dict(l=10, r=10, t=30, b=10))
    return fig


# --- UYGULAMA AKIŞI ---
if st.sidebar.button("Analizi Başlat 🚀"):
    with st.spinner(f"{sembol} verileri işleniyor..."):
        try:
            df = yf.Ticker(sembol).history(period=p, interval=i)
            if len(df) < 20:
                st.error("Veri yetersiz veya sembol hatalı.")
            else:
                # İndikatörler
                df.ta.rsi(length=14, append=True)
                df.ta.mfi(length=14, append=True)
                df.ta.macd(fast=12, slow=26, signal=9, append=True)
                df.ta.supertrend(length=10, multiplier=3, append=True)
                df.ta.sma(length=50, append=True)
                df.ta.bbands(length=20, std=2, append=True)

                # Yorum Üret
                puan, trend, oneri, uyari = profesyonel_yorum_uret(df)

                # --- 1. RAPOR KISMI (MOBİL UYUMLU KARTLAR) ---
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Teknik Puan", f"{puan}/100")
                col2.metric("Trend", trend.split(" ")[1])  # Sadece kelimeyi al
                col3.metric("Sinyal", oneri.split(" ")[1])
                col4.metric("Fiyat", f"{df['Close'].iloc[-1]:.2f}")

                # Detaylı Yorum Kutusu (Expander - Mobilde yer kaplamasın diye açılır kapanır)
                with st.expander("📝 Detaylı Yapay Zeka Raporunu Oku", expanded=True):
                    st.markdown(f"""
                    **ANALİZ ÖZETİ:**
                    * **Trend Durumu:** {trend}
                    * **Strateji:** {oneri}
                    * **Risk Uyarısı:** {uyari}
                    """)

                    st.info("""
                    **📚 İNDİKATÖR SÖZLÜĞÜ:**
                    * **SMA 50 (Turuncu):** Ana yön. Üstündeyse Yükseliş.
                    * **SuperTrend (Kırmızı Nokta):** Stop seviyesi.
                    * **RSI (Mor):** 30 altı ucuz, 70 üstü pahalı.
                    * **MFI (Mavi):** Para girişi.
                    """)

                # --- 2. GRAFİK KISMI ---
                st.plotly_chart(grafik_ciz(df, sembol), use_container_width=True)

        except Exception as e:
            st.error(f"Hata: {e}")