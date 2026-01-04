import streamlit as st
import yfinance as yf
import pandas_ta as ta
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="V10.1 Eğitimli Kokpit", page_icon="🎓", layout="wide")

# --- BAŞLIK ---
st.title("Borsa Pratiği Botu")
st.markdown("Hisse, Kripto, Emtia ve **Detaylı İndikatör Eğitimi**")

# --- SIDEBAR ---
st.sidebar.header("⚙️ Ayarlar")

piyasa_secimi = st.sidebar.selectbox(
    "Piyasa Seçiniz:",
    [
        "📊 Borsa Endeksleri (Dünya)",
        "🏆 Emtia (Altın/Petrol/Metal)",
        "🌎 Yabancı Fonlar (ETF)",
        "🇹🇷 BIST (Hisse)",
        "🇺🇸 ABD (Hisse)",
        "₿ Kripto"
    ]
)

# --- AKILLI SEÇİM MANTIĞI ---
secilen_sembol = ""
sembol_adi = ""

if piyasa_secimi == "📊 Borsa Endeksleri (Dünya)":
    endeksler = {
        "🇹🇷 BIST 100 (Genel)": "XU100.IS",
        "🇹🇷 BIST 30 (Devler)": "XU030.IS",
        "🇹🇷 BIST Banka": "XBANK.IS",
        "🇺🇸 S&P 500 (ABD Devleri)": "^GSPC",
        "🇺🇸 Nasdaq (Teknoloji)": "^NDX",
        "🇺🇸 Dow Jones (Sanayi)": "^DJI",
        "🇩🇪 DAX (Almanya)": "^GDAXI",
        "😨 VIX (Korku Endeksi)": "^VIX"
    }
    secim = st.sidebar.selectbox("Endeks Seçiniz:", list(endeksler.keys()))
    secilen_sembol = endeksler[secim]
    sembol_adi = secim

elif piyasa_secimi == "🏆 Emtia (Altın/Petrol/Metal)":
    emtialar = {
        "🟡 Altın (Ons)": "GC=F",
        "⚪ Gümüş (Ons)": "SI=F",
        "🛢️ Ham Petrol (WTI)": "CL=F",
        "🛢️ Brent Petrol": "BZ=F",
        "⛽ Doğalgaz": "NG=F",
        "🥉 Bakır": "HG=F"
    }
    secim = st.sidebar.selectbox("Emtia Seçiniz:", list(emtialar.keys()))
    secilen_sembol = emtialar[secim]
    sembol_adi = secim

elif piyasa_secimi == "🌎 Yabancı Fonlar (ETF)":
    etfler = {
        "🏛 SPY - S&P 500 Fonu": "SPY",
        "💻 QQQ - Nasdaq Fonu": "QQQ",
        "🌍 VT - Dünya Borsaları": "VT",
        "🟡 GLD - Altın Fonu": "GLD",
        "⚪ SLV - Gümüş Fonu": "SLV"
    }
    secim = st.sidebar.selectbox("Fon Seçiniz:", list(etfler.keys()))
    secilen_sembol = etfler[secim]
    sembol_adi = secim

elif piyasa_secimi == "🇹🇷 BIST (Hisse)":
    giris = st.sidebar.text_input("Hisse Kodu (Örn: THYAO):", value="THYAO").upper()
    secilen_sembol = giris + ".IS" if ".IS" not in giris else giris
    sembol_adi = giris

elif piyasa_secimi == "🇺🇸 ABD (Hisse)":
    giris = st.sidebar.text_input("Hisse Kodu (Örn: AAPL):", value="AAPL").upper()
    secilen_sembol = giris
    sembol_adi = giris

elif piyasa_secimi == "₿ Kripto":
    giris = st.sidebar.text_input("Coin Kodu (Örn: BTC):", value="BTC").upper()
    secilen_sembol = giris + "-USD" if "-USD" not in giris else giris
    sembol_adi = giris

vade_secimi = st.sidebar.selectbox("Vade Seçiniz:",
                                   ["1 Hafta (15dk)", "1 Ay (Saatlik)", "6 Ay (Günlük)", "1 Yıl (Günlük)"])


# --- VERİ ÇEKME ---
def veri_getir(sembol, vade):
    if "1 Hafta" in vade:
        p, i = "5d", "15m"
    elif "1 Ay" in vade:
        p, i = "1mo", "60m"
    elif "6 Ay" in vade:
        p, i = "6mo", "1d"
    else:
        p, i = "1y", "1d"
    return yf.Ticker(sembol).history(period=p, interval=i)


# --- YORUM MOTORU ---
def detayli_yorum_uret(df):
    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.supertrend(length=10, multiplier=3, append=True)
    df.ta.sma(length=50, append=True)
    df.ta.bbands(length=20, std=2, append=True)
    df.ta.mfi(length=14, append=True)

    son = df.iloc[-1]
    fiyat = son['Close']
    rsi = son['RSI_14']
    mfi = son['MFI_14']
    macd = son['MACD_12_26_9']
    macd_sinyal = son['MACDs_12_26_9']

    st_col = [c for c in df.columns if c.startswith('SUPERT_')][0]
    sma_col = [c for c in df.columns if c.startswith('SMA_50')][0]
    bbu_col = [c for c in df.columns if c.startswith('BBU_')][0]
    bbl_col = [c for c in df.columns if c.startswith('BBL_')][0]

    supertrend = son[st_col]
    sma50 = son[sma_col]
    bb_ust = son[bbu_col]
    bb_alt = son[bbl_col]

    # Trend
    trend_txt = ""
    trend_puan = 0
    if fiyat > sma50:
        trend_txt += "Fiyat 50 günlük ortalamanın üzerinde (Pozitif). "
        trend_puan += 25
    else:
        trend_txt += "Fiyat ortalamanın altında (Negatif). "

    if fiyat > supertrend:
        trend_txt += "SuperTrend AL sinyali veriyor."
        trend_puan += 25
    else:
        trend_txt += "SuperTrend direnci kırılamadı."

    # Momentum
    mom_txt = ""
    if rsi > 70:
        mom_txt += f"RSI {rsi:.1f} (Aşırı Pahalı/Şişkin). "
    elif rsi < 30:
        mom_txt += f"RSI {rsi:.1f} (Aşırı Ucuz/Dip). "
    else:
        mom_txt += "RSI nötr. "

    if macd > macd_sinyal:
        mom_txt += "MACD Al verdi."
        trend_puan += 25
    else:
        mom_txt += "MACD Sat verdi."

    # Risk
    risk_txt = ""
    if fiyat > bb_ust:
        risk_txt += "Fiyat Bollinger üstünü deldi, düzeltme gelebilir."
    elif fiyat < bb_alt:
        risk_txt += "Fiyat Bollinger altına sarktı, tepki gelebilir."
    else:
        risk_txt += "Volatilite normal."

    if mfi > 50: trend_puan += 25

    if trend_puan >= 75:
        karar = "GÜÇLÜ AL 🚀"
    elif 50 <= trend_puan < 75:
        karar = "AL / TUT ✅"
    elif 25 <= trend_puan < 50:
        karar = "İZLE / BEKLE 👀"
    else:
        karar = "SAT / UZAK DUR ❌"

    return df, trend_txt, mom_txt, risk_txt, karar, trend_puan


# --- GRAFİK ---
def grafik_ciz(df, baslik):
    st_col = [c for c in df.columns if c.startswith('SUPERT_')][0]
    sma_col = [c for c in df.columns if c.startswith('SMA_50')][0]
    bbu_col = [c for c in df.columns if c.startswith('BBU_')][0]
    bbl_col = [c for c in df.columns if c.startswith('BBL_')][0]
    macd_col = [c for c in df.columns if c.startswith('MACD_')][0]
    macdh_col = [c for c in df.columns if c.startswith('MACDh_')][0]
    macds_col = [c for c in df.columns if c.startswith('MACDs_')][0]

    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.50, 0.15, 0.15, 0.20],
                        subplot_titles=(f"{baslik} Fiyat & Bollinger", "RSI (Güç)", "MFI (Para)", "MACD (Trend)"))

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

    fig.add_trace(go.Scatter(x=df.index, y=df['RSI_14'], line=dict(color='purple', width=2), name="RSI"), row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df['MFI_14'], line=dict(color='blue', width=2), name="MFI"), row=3, col=1)
    fig.add_hline(y=20, line_dash="dot", line_color="green", row=3, col=1)
    fig.add_hline(y=80, line_dash="dot", line_color="red", row=3, col=1)

    colors = ['green' if val >= 0 else 'red' for val in df[macdh_col]]
    fig.add_trace(go.Bar(x=df.index, y=df[macdh_col], marker_color=colors, name="MACD Hist"), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df[macd_col], line=dict(color='black', width=1), name="MACD"), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df[macds_col], line=dict(color='orange', width=1), name="Sinyal"), row=4,
                  col=1)

    fig.update_layout(height=900, xaxis_rangeslider_visible=False, showlegend=False,
                      margin=dict(l=10, r=10, t=30, b=10))
    return fig


# --- ÇALIŞTIR ---
if st.sidebar.button("Analiz Et 🚀"):
    with st.spinner(f"{sembol_adi} verileri çekiliyor..."):
        try:
            df = veri_getir(secilen_sembol, vade_secimi)

            if df is None or len(df) < 10:
                st.error("❌ Veri bulunamadı. Piyasa kapalı olabilir.")
            else:
                df, t_txt, m_txt, r_txt, karar, puan = detayli_yorum_uret(df)

                # Başlık & Metrikler
                st.header(f"📊 Analiz: {sembol_adi}")
                c1, c2, c3 = st.columns(3)
                c1.metric("Skor", f"{puan}/100")
                c2.metric("Karar", karar)
                c3.metric("Son Fiyat", f"{df['Close'].iloc[-1]:.2f}")

                # Yorum Kartları
                with st.expander("🌊 1. Trend Analizi", expanded=True):
                    st.write(t_txt)
                with st.expander("🚀 2. Momentum (Güç)", expanded=True):
                    st.write(m_txt)
                with st.expander("🛡️ 3. Risk Durumu", expanded=True):
                    st.write(r_txt)

                # Grafik
                st.plotly_chart(grafik_ciz(df, sembol_adi), use_container_width=True)

                # --- YENİ EKLENEN EĞİTİM BÖLÜMÜ ---
                with st.expander("📚 Teknik Sözlük: İndikatörler Ne Anlama Geliyor?", expanded=True):
                    st.markdown("""
                    ### 1. Grafikteki Çizgiler
                    * **🟠 SMA 50 (Turuncu Çizgi):** *Basit Hareketli Ortalama.* Fiyatın son 50 mumdaki ortalamasıdır. Fiyat turuncu çizginin üzerindeyse trend **Yükseliş**, altındaysa **Düşüş** yönündedir.
                    * **🔴 SuperTrend (Kırmızı Noktalar):** *Trend Takipçisi.* Fiyat bu noktaların altına düşerse "Stop Ol" (Zarar Kes) sinyali üretir. Noktalar fiyatın üstündeyse düşüş, altındaysa yükseliş trendi vardır.
                    * **⬜ Bollinger Bantları (Gri Alan):** *Volatilite Kanalı.* Fiyat genelde bu gri alanın içinde hareket eder.
                        * **Üst Banda Değerse:** Fiyat pahalıdır, düzeltme gelebilir.
                        * **Alt Banda Değerse:** Fiyat ucuzdur, tepki gelebilir.

                    ### 2. Alttaki Paneller
                    * **🟣 RSI (Göreceli Güç Endeksi):** *Hız Göstergesi.* 0 ile 100 arasındadır.
                        * **70 Üstü:** Piyasa aşırı coşkulu (Pahalı). Satış yiyebilir.
                        * **30 Altı:** Piyasa aşırı ölü (Ucuz). Alım fırsatı olabilir.
                    * **🔵 MFI (Para Akış Endeksi):** *Hacim Göstergesi.* RSI'ın "Hacim" eklenmiş halidir. Fiyat yükselirken MFI da yükseliyorsa bu yükseliş sağlıklıdır (Para girişi vardır).
                    * **📊 MACD (Trend Gücü):** *Kesişim Göstergesi.* Siyah çizgi, Turuncu çizgiyi **YUKARI** keserse "AL", **AŞAĞI** keserse "SAT" sinyalidir. Histogram (Çubuklar) yeşilse alıcılar, kırmızıysa satıcılar güçlüdür.
                    """)

        except Exception as e:
            st.error(f"Hata: {e}")
