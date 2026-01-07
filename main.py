from fastapi import FastAPI, HTTPException, Query
import yfinance as yf
import pandas_ta as ta
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

app = FastAPI(title="Pro Terminal API", version="40.0")

# ==========================================
# 1. ALİ PERŞEMBE ANALİZ MOTORU
# ==========================================
class AnalizMotoru:
    def veriyi_hazirla(self, df):
        df.ta.sma(length=50, append=True) 
        df.ta.sma(length=200, append=True)
        df.ta.adx(length=14, append=True) 
        df.ta.atr(length=14, append=True)
        df.ta.rsi(length=14, append=True)
        df['Vol_SMA'] = df['Volume'].rolling(20).mean()
        return df.dropna()

    def analiz_et(self, df):
        son = df.iloc[-1]
        fiyat = son['Close']
        sma50 = son['SMA_50']
        sma200 = son['SMA_200']
        adx = son.get('ADX_14', 0)
        atr = son.get('ATRr_14', 0)
        rsi = son.get('RSI_14', 50)
        
        nedenler = []
        puan = 0
        
        # Trend
        if sma50 > sma200:
            puan += 1
            nedenler.append(f"✅ Pozitif Trend (50 > 200 SMA)")
        else:
            puan -= 1
            nedenler.append(f"🔻 Negatif Trend (50 < 200 SMA)")
            
        if fiyat > sma50:
            puan += 1
            nedenler.append(f"✅ Fiyat ortalamanın üzerinde.")
        
        # Güç (ADX)
        if adx > 25:
            nedenler.append(f"🔥 Güçlü Trend (ADX: {adx:.0f})")
        else:
            puan -= 0.5
            nedenler.append(f"💤 Zayıf Trend (ADX: {adx:.0f})")
            
        # Karar
        durum = "NÖTR"
        renk = "GRAY"
        if puan >= 1.5: durum, renk = "ALIMDA", "GREEN"
        elif puan <= -1: durum, renk = "SATIMDA", "RED"
            
        stop_seviyesi = fiyat - (atr * 2) 
        return {
            "durum": durum, "renk": renk, "stop_seviyesi": round(stop_seviyesi, 2),
            "detay": {
                "trend_mesaj": "Boğa" if sma50 > sma200 else "Ayı",
                "trend_yonu": "UP" if sma50 > sma200 else "DOWN",
                "aksiyon_mesaj": " | ".join(nedenler)
            }
        }

# ==========================================
# 2. HABER MOTORU
# ==========================================
class HaberMotoru:
    def getir(self, terim: str):
        rss_url = f"https://news.google.com/rss/search?q={terim}&hl=tr-TR&gl=TR&ceid=TR:tr"
        try:
            response = requests.get(rss_url, timeout=5)
            root = ET.fromstring(response.content)
            return [{"baslik": i.find('title').text, "link": i.find('link').text, "tarih": i.find('pubDate').text} for i in root.findall('./channel/item')[:10]]
        except: return []

# ==========================================
# 3. ENDPOINTS
# ==========================================
@app.get("/analiz")
def analiz_yap(sembol: str, piyasa: str = "BIST"):
    s = sembol.upper()
    try:
        ticker = s
        if piyasa == "BIST": ticker = f"{s}.IS"
        elif piyasa == "Emtia":
            m = {"ALTIN": "GC=F", "GÜMÜŞ": "SI=F", "PETROL": "CL=F"}
            ticker = m.get(s, s)
        elif piyasa == "Endeksler":
            m = {"BIST 100": "XU100.IS", "S&P 500": "^GSPC", "NASDAQ": "^IXIC"}
            ticker = m.get(s, s)
            
        df = yf.Ticker(ticker).history(period="2y", interval="1d")
        if df.empty: raise HTTPException(status_code=404)

        motor = AnalizMotoru()
        df = motor.veriyi_hazirla(df)
        sonuc = motor.analiz_et(df)
        grafik = [{"tarih": str(r.name.date()), "close": r['Close']} for _, r in df.tail(60).iterrows()]

        return {"sembol": s, "fiyat": round(df['Close'].iloc[-1], 2), "analiz": sonuc, "grafik_verisi": grafik}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/haberler")
def haberler(terim: str):
    return HaberMotoru().getir(terim)
