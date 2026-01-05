import streamlit as st
import yfinance as yf
import pandas_ta as ta
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Finans Asistanı", layout="wide")
st.title("Finans Asistanı")
st.markdown("Finans Asistanı ile bilgi birikimlerinizi arttırabilirsiniz. Yatırım Tavsiyesi Değildir!")

# ==========================================
# 1. AYARLAR
# ==========================================
st.sidebar.header("Yatırımcı Profili")
profil = st.sidebar.radio(
    "Tarzın Nedir?",
    [" - Kısa Vadeli Yatırımcı", " - Orta Vadeli Yatırımcı", " - Uzun Vadeli Yatırımcı"]
)

if "Scalper" in profil:
    ma_tur, kisa, uzun, atr_kat, vade = "EMA", 9, 21, 1.5, "6mo"
elif "Trader" in profil:
    ma_tur, kisa, uzun, atr_kat, vade = "SMA", 50, 200, 2.5, "2y"
else:
    ma_tur, kisa, uzun, atr_kat, vade = "SMA", 100, 200, 3.5, "5y"

st.sidebar.markdown("---")
st.sidebar.header("🔎 Piyasa Seçimi")
piyasa = st.sidebar.selectbox("Piyasa:", ["BIST (Hisse)", "Kripto", "ABD Borsası", "Emtia", "Endeksler"])

# --- DEĞİŞKEN TANIMLAMALARI (Hata Önleyici) ---
secilen_sembol = ""
sembol_adi = ""
arama_terimi = ""

if piyasa == "BIST (Hisse)":
    raw_sym = st.sidebar.text_input("Kod (Örn: THYAO):", "THYAO").upper()
    secilen_sembol = raw_sym + ".IS"
    sembol_adi = raw_sym
    arama_terimi = f"{raw_sym} Hisse Haberleri"
elif piyasa == "Kripto":
    raw_sym = st.sidebar.text_input("Kod (Örn: BTC):", "BTC").upper()
    secilen_sembol = raw_sym + "-USD"
    sembol_adi = raw_sym
    arama_terimi = f"{raw_sym} Kripto Haber"
elif piyasa == "Emtia":
    liste = {"Altın": "GC=F", "Petrol": "CL=F"}
    secim = st.sidebar.selectbox("Seç:", list(liste.keys()))
    secilen_sembol = liste[secim]
    sembol_adi = secim
    arama_terimi = f"{secim} Piyasa Haberleri"
elif piyasa == "Endeksler":
    liste = {"BIST 100": "XU100.IS", "S&P 500": "^GSPC", "DAX": "^GDAXI"}
    secim = st.sidebar.selectbox("Seç:", list(liste.keys()))
    secilen_sembol = liste[secim]
    sembol_adi = secim
    arama_terimi = f"{secim} Borsa Haberleri"
else:
    raw_sym = st.sidebar.text_input("Kod (Örn: AAPL):", "AAPL").upper()
    secilen_sembol = raw_sym
    sembol_adi = raw_sym
    arama_terimi = f"{raw_sym} Stock News"


# ==========================================
# 2. ANALİZ MOTORU
# ==========================================
class AnalizMotoru:
    def veriyi_hazirla(self, df, kisa, uzun, tur):
        if len(df) < uzun: return None

        # Trend
        if tur == "SMA":
            df.ta.sma(length=kisa, append=True)
            df.ta.sma(length=uzun, append=True)
            df['MA_Short'] = df[f'SMA_{kisa}']
            df['MA_Long'] = df[f'SMA_{uzun}']
        else:
            df.ta.ema(length=kisa, append=True)
            df.ta.ema(length=uzun, append=True)
            df['MA_Short'] = df[f'EMA_{kisa}']
            df['MA_Long'] = df[f'EMA_{uzun}']

        # Göstergeler
        df.ta.atr(length=14, append=True)
        df.ta.adx(length=14, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.bbands(length=20, std=2, append=True)

        # Hacim Ortalaması
        df['Vol_SMA'] = df['Volume'].rolling(20).mean()

        # Mum Formasyonu
        body = abs(df['Open'] - df['Close'])
        lower = df[['Open', 'Close']].min(axis=1) - df['Low']
        upper = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['Hammer'] = (lower > body * 2) & (upper < body * 0.5)

        return df.dropna()

    def sinyal_uret(self, df, atr_kat):
        trades, buys, sells = [], [], []
        in_pos = False
        entry_price = 0.0
        stop_loss = 0.0
        highest = 0.0
        live_status = "NÖTR"
        live_stop = 0.0

        for i in range(1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i - 1]
            price = row['Close']
            atr = row['ATRr_14']
            date = df.index[i]

            trend_up = (row['MA_Short'] > row['MA_Long']) or (price > row['MA_Short'])
            trend_down = (price < row['MA_Short']) and (row['MA_Short'] < row['MA_Long'])

            trigger = ((prev['RSI_14'] < 30) and (row['RSI_14'] > 30)) or row['Hammer']
            power = row['ADX_14'] > 20

            if in_pos:
                stop_hit = row['Low'] <= stop_loss
                trend_exit = trend_down
                force_exit = (i == len(df) - 1)

                if stop_hit or trend_exit or force_exit:
                    in_pos = False
                    if stop_hit:
                        exit_price = stop_loss
                        reason = 'SATIŞ (Stop)'
                    elif trend_exit:
                        exit_price = price
                        reason = 'SATIŞ (Trend)'
                    else:
                        exit_price = price
                        reason = 'SATIŞ (Kapanış)'

                    pnl = (exit_price - entry_price) / entry_price
                    trades.append({'Tarih': date, 'İşlem': reason, 'Fiyat': exit_price, 'Sonuç': pnl})
                    sells.append({'Date': date, 'Price': exit_price})
                    live_status = "NÖTR"
                else:
                    if row['High'] > highest:
                        highest = row['High']
                        new_stop = highest - (atr * atr_kat)
                        if new_stop > stop_loss: stop_loss = new_stop
                    live_stop = stop_loss
                    live_status = "ALIMDA"
            else:
                if trend_up and power and trigger:
                    in_pos = True
                    entry_price = price
                    highest = price
                    stop_loss = price - (atr * atr_kat)
                    trades.append({'Tarih': date, 'İşlem': 'ALIŞ', 'Fiyat': price, 'Sonuç': 0})
                    buys.append({'Date': date, 'Price': price})
                    live_stop = stop_loss
                    live_status = "ALIMDA"

        return trades, buys, sells, live_status, live_stop


# ==========================================
# 3. YORUMCU (DÜZELTİLMİŞ)
# ==========================================
def detayli_yorum_getir(df, status, live_stop, atr_kat):
    son = df.iloc[-1]
    fiyat = son['Close']
    ma_long = son['MA_Long']
    atr = son['ATRr_14']
    vol = son['Volume']
    vol_sma = son.get('Vol_SMA', vol)  # Hata önleyici
    sma50 = son.get('SMA_50', son['MA_Short'])

    # --- HATA DÜZELTMESİ: SÜTUN İSMİNİ OTOMATİK BUL ---
    # Bazen 'BBU_20_2.0' bazen 'BBU_20_2' oluyor. Otomatik buluyoruz:
    cols = df.columns
    bbu_col = [c for c in cols if c.startswith('BBU')][0]
    bbl_col = [c for c in cols if c.startswith('BBL')][0]

    bb_upper = son[bbu_col]
    bb_lower = son[bbl_col]

    # 1. Trend Analizi
    if fiyat > ma_long:
        trend_msg = f"Fiyat Ana Trendin ({ma_long:.2f}) üzerinde. Piyasa **BOĞA (Yükseliş)** karakterinde."
        trend_icon = "🟢"
    else:
        trend_msg = f"Fiyat Ana Trendin ({ma_long:.2f}) altında. Piyasa **AYI (Düşüş)** baskısında."
        trend_icon = "🔴"

    # 2. Risk & Stop
    stop_mesafe = atr * atr_kat
    risk_msg = f"ATR Volatilitesi: {atr:.2f}. Güvenli stop mesafesi şu anki fiyattan {stop_mesafe:.2f} birim aşağıdadır."

    # 3. Hacim Teyidi
    if vol > vol_sma * 1.2:
        vol_msg = "Hacim, ortalamanın %20 üzerinde. Mevcut hareket **güçlü ve iştahlı** (Gerçek)."
    elif vol < vol_sma * 0.8:
        vol_msg = "Hacim ortalamanın altında. Yükseliş veya düşüş **cılız kalabilir** (Tuzak ihtimali)."
    else:
        vol_msg = "Hacim standart seviyelerde, olağandışı bir para girişi/çıkışı yok."

    # 4. Sıkışma / Patlama
    bb_width = (bb_upper - bb_lower) / sma50
    if bb_width < 0.10:
        sqz_msg = "Bollinger bantları çok daraldı (Sıkışma). **Sert bir patlama (Kırılım) çok yakın!**"
    else:
        sqz_msg = "Volatilite normal, bantlar açık. Olağan dalgalanma sürüyor."

    # 5. Aksiyon
    if status == "ALIMDA":
        action_msg = f"Sistem **ALIMDA**. Stop seviyen **{live_stop:.2f}**. Fiyat bunun altına inmedikçe trendi sür."
    else:
        action_msg = "Sistem **BEKLEMEDE**. Henüz güvenli bir giriş sinyali oluşmadı."

    return trend_msg, trend_icon, risk_msg, vol_msg, sqz_msg, action_msg


# ==========================================
# 4. HABER MOTORU
# ==========================================
class HaberMotoru:
    def google_haberleri_getir(self, anahtar_kelime):
        rss_url = f"https://news.google.com/rss/search?q={anahtar_kelime}&hl=tr-TR&gl=TR&ceid=TR:tr"
        try:
            response = requests.get(rss_url, timeout=5)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                haberler = []
                for item in root.findall('./channel/item')[:8]:
                    haberler.append({
                        'baslik': item.find('title').text,
                        'link': item.find('link').text,
                        'tarih': item.find('pubDate').text
                    })
                return haberler
            return []
        except:
            return []


# ==========================================
# 5. UYGULAMA
# ==========================================
if st.sidebar.button("Analiz Et 🚀"):
    with st.spinner("Piyasa röntgeni çekiliyor..."):
        try:
            p_map = {"6mo": "6mo", "2y": "2y", "5y": "5y"}
            df = yf.Ticker(secilen_sembol).history(period=p_map[vade], interval="1d")

            if df.empty:
                st.error(f"Veri yok. Sembol: {secilen_sembol}")
                st.stop()

            # Analiz
            motor = AnalizMotoru()
            df = motor.veriyi_hazirla(df, kisa, uzun, ma_tur)
            trades, buys, sells, status, live_stop = motor.sinyal_uret(df, atr_kat)

            # Yorum (5 Madde) - Artık hata vermez
            t_msg, t_ico, r_msg, v_msg, s_msg, a_msg = detayli_yorum_getir(df, status, live_stop, atr_kat)

            # Haber
            haber_botu = HaberMotoru()
            haberler = haber_botu.google_haberleri_getir(arama_terimi)

            # --- EKRAN ---
            tab1, tab2, tab3 = st.tabs(["📊 5-Boyutlu Analiz", "📜 Backtest", "📰 Haberler"])

            with tab1:
                last_price = df['Close'].iloc[-1]
                c1, c2, c3 = st.columns(3)
                c1.metric("Fiyat", f"{last_price:.2f}")
                c2.metric("Trend", t_ico)

                if status == "ALIMDA":
                    c3.metric("Stop", f"{live_stop:.2f}", delta_color="inverse")
                    st.success(f"**SONUÇ:** {a_msg}")
                else:
                    c3.metric("Durum", "NÖTR")
                    st.warning(f"**SONUÇ:** {a_msg}")

                with st.expander("🧠 Yapay Zeka Detaylı Raporu (Oku)", expanded=True):
                    st.markdown(f"""
                    * **🌊 Trend:** {t_msg}
                    * **🛡️ Risk Yönetimi:** {r_msg}
                    * **📊 Hacim Teyidi:** {v_msg}
                    * **💥 Sıkışma (Squeeze):** {s_msg}
                    """)

                # Grafik
                fig = go.Figure()
                fig.add_trace(
                    go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                                   name="Fiyat"))
                fig.add_trace(
                    go.Scatter(x=df.index, y=df['MA_Long'], line=dict(color='black', width=2), name="Ana Trend"))
                if buys: fig.add_trace(
                    go.Scatter(x=[x['Date'] for x in buys], y=[x['Price'] for x in buys], mode='markers', name='AL',
                               marker=dict(color='green', size=12, symbol='triangle-up')))
                if sells: fig.add_trace(
                    go.Scatter(x=[x['Date'] for x in sells], y=[x['Price'] for x in sells], mode='markers', name='SAT',
                               marker=dict(color='red', size=12, symbol='triangle-down')))
                fig.update_layout(height=500, title=f"{sembol_adi} Analiz Grafiği", template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)

            with tab2:
                if trades:
                    satislar = [t for t in trades if 'SATIŞ' in t['İşlem']]
                    if satislar:
                        karli = len([t for t in satislar if t['Sonuç'] > 0])
                        basari = (karli / len(satislar) * 100)

                        st.metric("Başarı Oranı", f"%{basari:.1f}")

                        df_t = pd.DataFrame(trades)
                        df_t['Sonuç'] = df_t['Sonuç'].apply(lambda x: f"%{x * 100:.2f}" if x != 0 else "-")
                        st.dataframe(df_t, use_container_width=True)
                    else:
                        st.warning("Henüz kapanmış işlem yok.")
                else:
                    st.info("İşlem yok.")

            with tab3:
                st.subheader("Son Gelişmeler")
                if haberler:
                    for h in haberler:
                        st.markdown(f"**[{h['baslik']}]({h['link']})**")
                        st.caption(f"📅 {h['tarih']}")
                        st.markdown("---")
                else:
                    st.warning("Haber bulunamadı.")

        except Exception as e:
            st.error(f"Hata: {e}")
