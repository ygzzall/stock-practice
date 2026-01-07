from fastapi import FastAPI, HTTPException, Query
import yfinance as yf
import pandas_ta as ta
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import borsapy as bp  # <-- Yeni Takvim için
from datetime import datetime

# ==========================================
# 1. API KURULUMU
# ==========================================
app = FastAPI(
    title="Finans Terminali API",
    description="Gelişmiş Stratejiler + Backtest + Ekonomik Takvim",
    version="27.0"
)

# ==========================================
# 2. EKONOMİK TAKVİM (BORSAPY)
# ==========================================
class TakvimMotoru:
    def getir(self):
        try:
            cal = bp.EconomicCalendar()
            df = cal.events(period="1w") 
            
            if df.empty: raise Exception("Veri yok")

            sonuclar = []
            for _, row in df.iterrows():
                # Önem derecesi kontrolü (Stringe çevirip bakıyoruz)
                onem = str(row.get('Importance', '1'))
                
                # Sadece Orta (2) ve Yüksek (3) önemlileri al
                if onem in ['2', '3', 'High', 'Medium']:
                    sonuclar.append({
                        "saat": str(row.get('Time', '00:00')),
                        "ulke": row.get('Country', 'Dünya'),
                        "olay": row.get('Event', 'Bilinmeyen Olay'),
                        "onem": "Yüksek" if onem in ['3', 'High'] else "Orta"
                    })
            
            return sonuclar[:20]

        except Exception as e:
            print(f"Takvim Hatası: {e}")
            return [
                {"saat": "⚠️", "ulke": "Sistem", "olay": "Takvim Verisi Çekilemedi", "onem": "Yüksek"},
                {"saat": "15:30", "ulke": "ABD", "olay": "Tarım Dışı İstihdam (Tahmin)", "onem": "Yüksek"}
            ]

# ==========================================
# 3. HABER MOTORU (GOOGLE RSS - Eskisi)
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
        except: return []

# ==========================================
# 4. GELİŞMİŞ ANALİZ MOTORU (V26.0'dan Korundu)
# ==========================================
class AnalizMotoru:
    def veriyi_hazirla(self, df, kisa, uzun, tur):
        if len(df) < uzun: return None
        
        # Hareketli Ortalamalar
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

        # İndikatörler
        df.ta.atr(length=14, append=True)
        df.ta.adx(length=14, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.bbands(length=20, std=2, append=True) # Sıkışma için

        # Mum Formasyonları & Hacim
        df['Vol_SMA'] = df['Volume'].rolling(20).mean()
        body = abs(df['Open'] - df['Close'])
        lower = df[['Open', 'Close']].min(axis=1) - df['Low']
        upper = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['Hammer'] = (lower > body * 2) & (upper < body * 0.5)

        return df.dropna()

    def sinyal_uret(self, df, atr_kat):
        trades = []
        in_pos = False
        entry_price = 0.0
        stop_loss = 0.0
        highest = 0.0
        live_stop = 0.0
        live_status = "NÖTR"

        for i in range(1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            price = row['Close']
            atr = row['ATRr_14']
            date = str(df.index[i].date())

            # Trend & Sinyal Kuralları
            trend_up = (row['MA_Short'] > row['MA_Long'])
            trend_down = (row['MA_Short'] < row['MA_Long'])
            trigger = ((prev['RSI_14'] < 30) and (row['RSI_14'] > 30)) or row['Hammer']
            power = row['ADX_14'] > 20

            if in_pos:
                # Çıkış Kuralları
                stop_hit = row['Low'] <= stop_loss
                trend_exit = trend_down
                force_exit = (i == len(df) - 1)

                if stop_hit or trend_exit or force_exit:
                    in_pos = False
                    exit_price = stop_loss if stop_hit else price
                    pnl = (exit_price - entry_price) / entry_price
                    trades.append({'tarih': date, 'islem': 'SATIŞ', 'fiyat': round(exit_price, 2), 'sonuc': round(pnl*100, 2)})
                    live_status = "NÖTR"
                else:
                    # İz Süren Stop (Trailing Stop)
                    if row['High'] > highest:
                        highest = row['High']
                        new_stop = highest - (atr * atr_kat)
                        if new_stop > stop_loss: stop_loss = new_stop
                    live_stop = stop_loss
                    live_status = "ALIMDA"
            else:
                # Giriş Kuralları
                if trend_up and power and trigger:
                    in_pos = True
                    entry_price = price
                    highest = price
                    stop_loss = price - (atr * atr_kat)
                    trades.append({'tarih': date, 'islem': 'ALIŞ', 'fiyat': round(price, 2), 'sonuc': 0})
                    live_stop = stop_loss
                    live_status = "ALIMDA"
        
        return trades, live_status, live_stop

def detayli_yorum_getir(df, status, live_stop, atr_kat):
    son = df.iloc[-1]
    
    # Güvenli Sütun Bulma (Hata vermemesi için)
    bbu = son[[c for c in df.columns if c.startswith('BBU')][0]]
    bbl = son[[c for c in df.columns if c.startswith('BBL')][0]]
    sma50 = son['MA_Short'] # Yaklaşık değer
    
    # Sıkışma Analizi
    width = (bbu - bbl) / sma50
    sqz_msg = "🚨 Bollinger Sıkışması Var! Sert hareket gelebilir." if width < 0.10 else None

    return {
        "trend_mesaj": "Trend YUKARI 🐂" if son['MA_Short'] > son['MA_Long'] else "Trend AŞAĞI 🐻",
        "trend_yonu": "UP" if son['MA_Short'] > son['MA_Long'] else "DOWN",
        "hacim_mesaj": "Hacim Yüksek 🔥" if son['Volume'] > son.get('Vol_SMA', 0)*1.2 else "Hacim Normal",
        "sikisma_mesaj": sqz_msg,
        "aksiyon_mesaj": f"Sistem {status}. Stop: {live_stop:.2f}" if status == "ALIMDA" else "Beklemede kal.",
        "stop_mesafesi": round(son['ATRr_14'] * atr_kat, 2)
    }

# ==========================================
# 5. ENDPOINTS
# ==========================================
@app.get("/")
def home(): return {"durum": "API V27.0 Hazır 🚀"}

@app.get("/analiz")
def analiz_yap(
    sembol: str = Query(..., description="Örn: THYAO"),
    piyasa: str = "BIST",
    profil: str = "Trader"
):
    # 1. Profil Ayarları
    if profil == "Scalper": ma_tur, kisa, uzun, atr_kat, vade = "EMA", 9, 21, 1.5, "6mo"
    elif profil == "Trader": ma_tur, kisa, uzun, atr_kat, vade = "SMA", 50, 200, 2.5, "2y"
    else: ma_tur, kisa, uzun, atr_kat, vade = "SMA", 100, 200, 3.5, "5y"

    # 2. Sembol Düzeltme
    ticker = sembol.upper()
    if piyasa == "BIST" and not ticker.endswith(".IS"): ticker += ".IS"
    elif piyasa == "Kripto" and not ticker.endswith("-USD"): ticker += "-USD"
    elif piyasa == "Emtia":
        d = {"ALTIN": "GC=F", "PETROL": "CL=F"}
        if ticker in d: ticker = d[ticker]

    # 3. İşlem
    try:
        df = yf.Ticker(ticker).history(period="2y" if vade=="2y" else "5y", interval="1d") # Basitleştirildi
        if df.empty: raise HTTPException(status_code=404, detail="Veri yok")

        motor = AnalizMotoru()
        df = motor.veriyi_hazirla(df, kisa, uzun, ma_tur)
        trades, status, live_stop = motor.sinyal_uret(df, atr_kat)
        yorum = detayli_yorum_getir(df, status, live_stop, atr_kat)
        
        # Grafik Verisi Hazırla (Mobil İçin Son 30 Gün)
        grafik_veri = []
        for _, row in df.tail(30).reset_index().iterrows():
            grafik_veri.append({
                "tarih": str(row['Date'].date()),
                "close": row['Close']
            })

        return {
            "sembol": ticker,
            "fiyat": round(df['Close'].iloc[-1], 2),
            "analiz": {
                "durum": status,
                "stop_seviyesi": round(live_stop, 2),
                "detay": yorum
            },
            "grafik_verisi": grafik_veri # <-- Bu grafik çizimi için şart
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/takvim")
def takvim_getir():
    motor = TakvimMotoru()
    return {"takvim": motor.getir()}

@app.get("/haberler")
def haber_getir(terim: str):
    motor = HaberMotoru()
    return motor.getir(terim)
