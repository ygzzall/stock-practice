from fastapi import FastAPI, HTTPException
import yfinance as yf
import pandas_ta as ta
import pandas as pd
import requests
import xml.etree.ElementTree as ET

app = FastAPI(title="AI Terminal API", version="42.0")

class AliPersembeMotoru:
    def hesapla(self, df):
        # 1. Ali Perşembe'nin Trend Filtreleri
        df.ta.sma(length=50, append=True) 
        df.ta.sma(length=200, append=True)
        # 2. Trend Gücü (ADX olmadan Ali Perşembe olmaz)
        df.ta.adx(length=14, append=True) 
        # 3. Volatilite ve Dinamik Stop (ATR)
        df.ta.atr(length=14, append=True)
        df.ta.rsi(length=14, append=True)
        return df.dropna()

    def karar_ver(self, df):
        son = df.iloc[-1]
        fiyat = son['Close']
        sma50 = son['SMA_50']
        sma200 = son['SMA_200']
        adx = son.get('ADX_14', 0)
        atr = son.get('ATRr_14', 0)
        rsi = son.get('RSI_14', 50)
        
        nedenler = []
        puan = 0
        
        # KURAL 1: Trend Gücü Kontrolü (ADX)
        # Ali Perşembe der ki: "ADX 25'in altındaysa trend yoktur, uzak dur."
        if adx < 20:
            return {
                "durum": "NÖTR", "renk": "GRAY", "stop_seviyesi": 0,
                "detay": {"trend_mesaj": "Yatay", "trend_yonu": "SIDE", "aksiyon_mesaj": f"ADX düşük ({adx:.0f}). Piyasa şu an yönsüz ve testere modunda. İşlem riski yüksek."}
            }

        # KURAL 2: Hareketli Ortalama Kesişimi ve Fiyat Konumu
        if sma50 > sma200:
            puan += 1
            nedenler.append("Uzun vadeli trend boğa aşamasında (50 > 200 SMA).")
        else:
            puan -= 1
            nedenler.append("Uzun vadeli trend ayı aşamasında (50 < 200 SMA).")
            
        if fiyat > sma50:
            puan += 1
            nedenler.append("Fiyat kısa vadeli trend desteğinin üzerinde.")
        
        # KURAL 3: Momentum (RSI)
        if rsi < 35:
            puan += 1
            nedenler.append("Fiyat aşırı satım bölgesinden toparlanıyor.")
        elif rsi > 70:
            nedenler.append("Fiyat momentumun zirvesine yakın, kar satışı beklenebilir.")

        # SONUÇ
        durum = "NÖTR"
        renk = "GRAY"
        if puan >= 1.5: durum, renk = "ALIMDA", "GREEN"
        elif puan <= -1: durum, renk = "SATIMDA", "RED"
            
        # Ali Perşembe'nin İz Süren Stopu (2 * ATR)
        stop_seviyesi = fiyat - (atr * 2) 
        
        return {
            "durum": durum, "renk": renk, "stop_seviyesi": round(stop_seviyesi, 2),
            "detay": {
                "trend_mesaj": "Yükseliş" if sma50 > sma200 else "Düşüş",
                "trend_yonu": "UP" if sma50 > sma200 else "DOWN",
                "aksiyon_mesaj": " | ".join(nedenler)
            }
        }

@app.get("/analiz")
def analiz_yap(sembol: str, piyasa: str = "BIST"):
    s = sembol.upper().strip()
    try:
        ticker = s
        if piyasa == "BIST": ticker = f"{s}.IS"
        elif piyasa == "Endeksler":
            mapping = {"BIST 100": "XU100.IS", "BIST 30": "XU030.IS", "S&P 500": "^GSPC", "NASDAQ": "^IXIC"}
            ticker = mapping.get(s, s)
        elif piyasa == "Emtia":
            mapping = {"ALTIN": "GC=F", "GÜMÜŞ": "SI=F", "PETROL": "CL=F"}
            ticker = mapping.get(s, s)
            
        df = yf.Ticker(ticker).history(period="2y", interval="1d")
        if df.empty: raise HTTPException(status_code=404, detail="Veri bulunamadı.")

        motor = AliPersembeMotoru()
        df = motor.hesapla(df)
        sonuc = motor.karar_ver(df)
        grafik = [{"tarih": str(r.name.date()), "close": r['Close']} for _, r in df.tail(60).iterrows()]

        return {"sembol": s, "fiyat": round(df['Close'].iloc[-1], 2), "analiz": sonuc, "grafik_verisi": grafik}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/haberler")
def haberler(terim: str):
    rss_url = f"https://news.google.com/rss/search?q={terim}&hl=tr-TR&gl=TR&ceid=TR:tr"
    try:
        response = requests.get(rss_url, timeout=5)
        root = ET.fromstring(response.content)
        return [{"baslik": i.find('title').text, "link": i.find('link').text, "tarih": i.find('pubDate').text} for i in root.findall('./channel/item')[:10]]
    except: return []
