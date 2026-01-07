from fastapi import FastAPI, HTTPException
import yfinance as yf
import pandas_ta as ta
import pandas as pd
import requests
import xml.etree.ElementTree as ET

app = FastAPI(title="AI Terminal API", version="44.0")

class PersembeAnalizMotoru:
    def hesapla(self, df):
        df.ta.sma(length=50, append=True) 
        df.ta.sma(length=200, append=True)
        df.ta.adx(length=14, append=True) 
        df.ta.atr(length=14, append=True)
        df.ta.rsi(length=14, append=True)
        return df.dropna()

    def rapor_uret(self, df):
        son = df.iloc[-1]
        fiyat = son['Close']
        sma50 = son['SMA_50']
        sma200 = son['SMA_200']
        adx = son.get('ADX_14', 0)
        atr = son.get('ATRr_14', 0)
        rsi = son.get('RSI_14', 50)
        
        maddeler = []
        puan = 0
        
        # 1. ADX Filtresi: Trend Var mı?
        if adx < 20:
            return {
                "durum": "NÖTR", "renk": "GRAY", "stop_seviyesi": 0,
                "detay": {
                    "trend_mesaj": "Yatay Piyasa",
                    "aksiyon_mesaj": f"Piyasa gücü (ADX: {adx:.0f}) oldukça zayıf seyrediyor. | Ali Perşembe disiplinine göre, belirgin bir trendin olmadığı 'testere' piyasasında sermayeyi korumak ve işlem yapmadan izlemek en profesyonel yaklaşımdır."
                }
            }

        # 2. Trend Yönü
        if sma50 > sma200:
            puan += 1
            if fiyat > sma50:
                puan += 1
                maddeler.append("Ana trend boğa (yükseliş) kontrolünde. Fiyatın 50 günlük ortalama üzerinde kalması, yükseliş disiplininin korunduğunu teyit ediyor.")
            else:
                maddeler.append("Orta vadeli trendde yorulma emareleri var. Fiyatın 50 günlük ortalamanın altına sarkması, kısa süreli bir geri çekilme riskine işaret ediyor.")
        else:
            puan -= 1
            maddeler.append("Piyasa ayı (düşüş) baskısı altında. 200 günlük ortalamanın altında kalınması, her yükselişin matematiksel olarak bir satış fırsatı olarak görüldüğü bir döneme işaret eder.")

        # 3. Momentum (Aşırılık)
        if rsi > 70:
            maddeler.append(f"Momentum (RSI: {rsi:.0f}) aşırı alım bölgesinde bir şişme gösteriyor. Sermaye yönetimi gereği, kâr realizasyonu yapmayanlar piyasanın ani dönüşlerine hazırlıklı olmalıdır.")
        elif rsi < 30:
            maddeler.append(f"Momentum (RSI: {rsi:.0f}) aşırı satım bölgesinde. Satışların tükenme noktasına yaklaştığı bu aşamada panik değil, dönüş sinyali aranmalıdır.")
        else:
            maddeler.append(f"Momentum (RSI: {rsi:.0f}) nötr bölgede; piyasa ana trend yönünde hareketine devam etmek için enerji topluyor.")

        # 4. ATR Stop
        stop_seviyesi = fiyat - (atr * 2)
        maddeler.append(f"Piyasa oynaklığı (ATR) baz alındığında, stop seviyesi {stop_seviyesi:.2f} olarak hesaplanmıştır. Bu seviyenin altındaki kapanışlar, matematiksel olarak trendin bittiğinin kanıtıdır.")

        durum = "NÖTR"
        renk = "GRAY"
        if puan >= 1.5: durum, renk = "ALIMDA", "GREEN"
        elif puan <= -1: durum, renk = "SATIMDA", "RED"
            
        return {
            "durum": durum, "renk": renk, "stop_seviyesi": round(stop_seviyesi, 2),
            "detay": {
                "trend_mesaj": "Yükseliş" if sma50 > sma200 else "Düşüş",
                "trend_yonu": "UP" if sma50 > sma200 else "DOWN",
                "aksiyon_mesaj": " | ".join(maddeler)
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

        motor = PersembeAnalizMotoru()
        df = motor.hesapla(df)
        sonuc = motor.rapor_uret(df)
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
