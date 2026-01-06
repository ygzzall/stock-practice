from fastapi import FastAPI, HTTPException, Query
import yfinance as yf
import pandas_ta as ta
import pandas as pd
import numpy as np
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, List, Dict, Any

# ==========================================
# 1. API KURULUMU
# ==========================================
app = FastAPI(
    title="Finans Terminali API",
    description="Ali Perşembe Stratejileri + Google Haberler + Backtest",
    version="26.0"
)


# ==========================================
# 2. MOTORLAR (HESAPLAMA ÇEKİRDEĞİ)
# ==========================================

class AnalizMotoru:
    def veriyi_hazirla(self, df: pd.DataFrame, kisa: int, uzun: int, tur: str) -> pd.DataFrame:
        if len(df) < uzun:
            return None

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

        # Hacim & Mum
        df['Vol_SMA'] = df['Volume'].rolling(20).mean()
        body = abs(df['Open'] - df['Close'])
        lower = df[['Open', 'Close']].min(axis=1) - df['Low']
        upper = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['Hammer'] = (lower > body * 2) & (upper < body * 0.5)

        return df.dropna()

    def sinyal_uret(self, df: pd.DataFrame, atr_kat: float):
        trades = []
        in_pos = False
        entry_price = 0.0
        stop_loss = 0.0
        highest = 0.0
        live_stop = 0.0
        live_status = "NÖTR"

        for i in range(1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i - 1]
            price = row['Close']
            atr = row['ATRr_14']
            date = str(df.index[i].date())  # JSON için string'e çeviriyoruz

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
                    trades.append(
                        {'tarih': date, 'islem': reason, 'fiyat': round(exit_price, 2), 'sonuc': round(pnl * 100, 2)})
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
                    trades.append({'tarih': date, 'islem': 'ALIŞ', 'fiyat': round(price, 2), 'sonuc': 0})
                    live_stop = stop_loss
                    live_status = "ALIMDA"

        return trades, live_status, live_stop


# ==========================================
# 3. YORUMCU FONKSİYONU
# ==========================================
def detayli_yorum_getir(df, status, live_stop, atr_kat):
    son = df.iloc[-1]
    fiyat = son['Close']
    ma_long = son['MA_Long']
    atr = son['ATRr_14']
    vol = son['Volume']
    vol_sma = son.get('Vol_SMA', vol)
    sma50 = son.get('SMA_50', son['MA_Short'])

    # Sütun bulma
    cols = df.columns
    bbu_col = [c for c in cols if c.startswith('BBU')][0]
    bbl_col = [c for c in cols if c.startswith('BBL')][0]
    bb_upper = son[bbu_col]
    bb_lower = son[bbl_col]

    # Trend
    if fiyat > ma_long:
        trend_msg = f"Fiyat ({fiyat:.2f}) Ana Trendin ({ma_long:.2f}) üzerinde. Piyasa BOĞA."
        trend_code = "UP"
    else:
        trend_msg = f"Fiyat ({fiyat:.2f}) Ana Trendin ({ma_long:.2f}) altında. Piyasa AYI."
        trend_code = "DOWN"

    # Hacim
    if vol > vol_sma * 1.2:
        vol_msg = "Hacim yüksek (Güçlü)."
    elif vol < vol_sma * 0.8:
        vol_msg = "Hacim düşük (Zayıf)."
    else:
        vol_msg = "Hacim normal."

    # Sıkışma
    bb_width = (bb_upper - bb_lower) / sma50
    sqz_msg = "Sıkışma VAR! Patlama yakın." if bb_width < 0.10 else "Volatilite normal."

    # Aksiyon
    if status == "ALIMDA":
        action_msg = f"Sistem ALIMDA. Stop: {live_stop:.2f}"
    else:
        action_msg = "Sistem BEKLEMEDE."

    return {
        "trend_mesaj": trend_msg,
        "trend_yonu": trend_code,
        "hacim_mesaj": vol_msg,
        "sikisma_mesaj": sqz_msg,
        "aksiyon_mesaj": action_msg,
        "stop_mesafesi": round(atr * atr_kat, 2)
    }


# ==========================================
# 4. HABER MOTORU (GOOGLE RSS)
# ==========================================
class HaberMotoru:
    def getir(self, terim: str):
        rss_url = f"https://news.google.com/rss/search?q={terim}&hl=tr-TR&gl=TR&ceid=TR:tr"
        try:
            response = requests.get(rss_url, timeout=5)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                haberler = []
                for item in root.findall('./channel/item')[:10]:
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
# 5. ENDPOINTS (KAPI NUMARALARI)
# ==========================================

@app.get("/")
def home():
    return {"durum": "API Çalışıyor 🚀", "versiyon": "V26.0"}


@app.get("/analiz")
def analiz_yap(
        sembol: str = Query(..., description="Örn: THYAO, BTC"),
        piyasa: str = Query("BIST", enum=["BIST", "Kripto", "ABD", "Emtia", "Endeksler"]),
        profil: str = Query("Trader", enum=["Scalper", "Trader", "Investor"])
):
    """
    Ana analiz fonksiyonu. Mobil uygulama buraya istek atacak.
    """
    # 1. Profil Ayarları
    if profil == "Scalper":
        ma_tur, kisa, uzun, atr_kat, vade = "EMA", 9, 21, 1.5, "6mo"
    elif profil == "Trader":
        ma_tur, kisa, uzun, atr_kat, vade = "SMA", 50, 200, 2.5, "2y"
    else:  # Investor
        ma_tur, kisa, uzun, atr_kat, vade = "SMA", 100, 200, 3.5, "5y"

    # 2. Sembol Formatlama ve Haber Terimi
    ticker = sembol.upper()
    haber_terimi = f"{ticker} Finans Haberleri"

    if piyasa == "BIST" and not ticker.endswith(".IS"):
        ticker += ".IS"
        haber_terimi = f"{sembol} Hisse Haber"
    elif piyasa == "Kripto" and not ticker.endswith("-USD"):
        ticker += "-USD"
        haber_terimi = f"{sembol} Kripto"
    elif piyasa == "Emtia":
        emtia_map = {"ALTIN": "GC=F", "PETROL": "CL=F"}
        if ticker in emtia_map: ticker = emtia_map[ticker]

    # 3. Veri Çekme
    try:
        p_map = {"6mo": "6mo", "2y": "2y", "5y": "5y"}
        df = yf.Ticker(ticker).history(period=p_map[vade], interval="1d")

        if df.empty:
            raise HTTPException(status_code=404, detail="Veri bulunamadı")

        # 4. Analiz
        motor = AnalizMotoru()
        df = motor.veriyi_hazirla(df, kisa, uzun, ma_tur)
        if df is None:
            raise HTTPException(status_code=400, detail="Yetersiz veri")

        trades, status, live_stop = motor.sinyal_uret(df, atr_kat)
        yorumlar = detayli_yorum_getir(df, status, live_stop, atr_kat)

        # 5. Backtest Özeti
        basari_orani = 0.0
        toplam_getiri = 0.0
        if trades:
            satislar = [t for t in trades if 'SATIŞ' in t['islem']]
            if satislar:
                karli = len([t for t in satislar if t['sonuc'] > 0])
                basari_orani = round((karli / len(satislar)) * 100, 1)
                toplam_getiri = round(sum([t['sonuc'] for t in satislar]), 1)

        # 6. Grafik Verisi (Mobil için son 30 mum yeterli olabilir)
        # Veriyi küçültüyoruz ki hızlı gitsin
        son_df = df.tail(30).reset_index()
        grafik_veri = []
        for _, row in son_df.iterrows():
            grafik_veri.append({
                "tarih": str(row['Date'].date()),
                "open": row['Open'],
                "high": row['High'],
                "low": row['Low'],
                "close": row['Close']
            })

        return {
            "sembol": ticker,
            "fiyat": round(df['Close'].iloc[-1], 2),
            "analiz": {
                "durum": status,
                "stop_seviyesi": round(live_stop, 2),
                "detay": yorumlar
            },
            "backtest": {
                "toplam_islem": len(trades),
                "basari_orani": basari_orani,
                "toplam_getiri": toplam_getiri,
                "islem_gecmisi": trades[-5:]  # Son 5 işlem
            },
            "grafik_verisi": grafik_veri
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/haberler")
def haber_getir(terim: str):
    """
    Sadece haber çekmek için hafif endpoint.
    """
    bot = HaberMotoru()
    return bot.getir(terim)
