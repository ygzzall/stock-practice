from fastapi import FastAPI, HTTPException, Query
import yfinance as yf
import pandas_ta as ta
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import borsapy as bp
from datetime import datetime, timedelta

app = FastAPI(
    title="Pro Terminal API",
    description="Ali Perşembe Stratejileri + 5 Piyasa + Haberler + Takvim",
    version="36.0"
)

# ==========================================
# 1. FON MOTORU (TEFAS / BORSAPY)
# ==========================================
class FonMotoru:
    def getir(self, kod):
        try:
            tefas = bp.Tefas()
            bitis = datetime.now()
            baslangic = bitis - timedelta(days=365*2) # 2 Yıllık veri al
            
            # Veriyi çek
            df = tefas.get_history(kod, start=baslangic, end=bitis)
            if df is None or df.empty: return None
            
            # Sütun isimlerini küçük harfe çevir ve temizle
            df.columns = [c.lower() for c in df.columns]
            
            # Tarih index ayarla
            if 'tarih' in df.columns:
                df['Date'] = pd.to_datetime(df['tarih'])
                df.set_index('Date', inplace=True)
            
            # Fiyat sütununu bul ve 'Close' yap
            col_map = {'fiyat': 'Close', 'price': 'Close', 'değer': 'Close'}
            for tr, en in col_map.items():
                if tr in df.columns: df.rename(columns={tr: 'Close'}, inplace=True)
            
            if 'Close' not in df.columns: return None
            
            # OHLC Verilerini Doldur (Fonlarda tek fiyat vardır)
            df['Open'] = df['Close']
            df['High'] = df['Close']
            df['Low'] = df['Close']
            df['Volume'] = 1000000 # Sanal hacim
            df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
            
            return df.dropna()
        except Exception as e:
            print(f"Fon Hatası: {e}")
            return None

# ==========================================
# 2. TAKVİM MOTORU (SAĞLAMLAŞTIRILMIŞ)
# ==========================================
class TakvimMotoru:
    def getir(self):
        veriler = []
        try:
            # Borsapy'den çekmeyi dene
            cal = bp.EconomicCalendar()
            df = cal.events(period="1w") 
            
            if not df.empty:
                for _, row in df.iterrows():
                    onem = str(row.get('Importance', '1'))
                    # Sadece Orta ve Yüksek önemlileri al
                    if onem in ['2', '3', 'High', 'Medium']:
                        veriler.append({
                            "saat": str(row.get('Time', '00:00')),
                            "ulke": str(row.get('Country', 'Dünya')),
                            "olay": str(row.get('Event', 'Bilinmeyen Olay')),
                            "onem": "Yüksek" if onem in ['3', 'High'] else "Orta"
                        })
            
            if not veriler: raise Exception("Borsapy boş veri döndü")
            return veriler[:20]

        except Exception as e:
            # Hata olursa YEDEK LİSTE döndür (Uygulama çökmesin)
            print(f"Takvim Hatası: {e}")
            return [
                {"saat": "15:30", "ulke": "ABD", "olay": "Tarım Dışı İstihdam (Tahmin)", "onem": "Yüksek"},
                {"saat": "16:00", "ulke": "ABD", "olay": "İşsizlik Oranı", "onem": "Yüksek"},
                {"saat": "21:00", "ulke": "ABD", "olay": "FED Faiz Kararı", "onem": "Yüksek"},
                {"saat": "10:00", "ulke": "TUR", "olay": "Enflasyon Verisi (TÜFE)", "onem": "Yüksek"},
                {"saat": "⚠️", "ulke": "Sistem", "olay": "Canlı Veri Çekilemedi (Yedek Mod)", "onem": "Düşük"}
            ]

# ==========================================
# 3. HABER MOTORU (GOOGLE RSS)
# ==========================================
class HaberMotoru:
    def getir(self, terim: str):
        # Google News RSS (Türkçe)
        rss_url = f"https://news.google.com/rss/search?q={terim}&hl=tr-TR&gl=TR&ceid=TR:tr"
        try:
            response = requests.get(rss_url, timeout=5)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                haberler = []
                for item in root.findall('./channel/item')[:15]:
                    haberler.append({
                        'baslik': item.find('title').text,
                        'link': item.find('link').text,
                        'tarih': item.find('pubDate').text
                    })
                return haberler
            return []
        except: return []

# ==========================================
# 4. ALİ PERŞEMBE ANALİZ MOTORU
# ==========================================
class AnalizMotoru:
    def veriyi_hazirla(self, df):
        # 1. Hareketli Ortalamalar (Trend)
        df.ta.sma(length=50, append=True)  # Orta Vade
        df.ta.sma(length=200, append=True) # Uzun Vade (Ana Trend)
        
        # 2. Trend Gücü (ADX - Ali Perşembe Kuralı)
        df.ta.adx(length=14, append=True) 
        
        # 3. Volatilite ve Stop (ATR)
        df.ta.atr(length=14, append=True)
        
        # 4. Momentum
        df.ta.rsi(length=14, append=True)
        
        # 5. Hacim Ortalaması
        df['Vol_SMA'] = df['Volume'].rolling(20).mean()
        
        return df.dropna()

    def analiz_et(self, df):
        son = df.iloc[-1]
        
        # Değerler
        fiyat = son['Close']
        sma50 = son['SMA_50']
        sma200 = son['SMA_200']
        adx = son.get('ADX_14', 0)
        atr = son.get('ATRr_14', 0)
        rsi = son.get('RSI_14', 50)
        
        nedenler = []
        puan = 0
        
        # --- STRATEJİ MANTIĞI ---
        
        # 1. Trend Yönü (Golden Cross / Death Cross)
        if sma50 > sma200:
            puan += 1
            nedenler.append(f"✅ Altın Kesişim (Golden Cross): 50 G.O ({sma50:.2f}) > 200 G.O")
        else:
            puan -= 1
            nedenler.append(f"🔻 Ölüm Kesişimi (Death Cross): Uzun vade trend düşüşte.")
            
        # 2. Fiyatın Ortalamaya Göre Konumu
        if fiyat > sma50:
            puan += 1
            nedenler.append(f"✅ Fiyat ({fiyat:.2f}), 50 Günlük ortalamanın üzerinde.")
        else:
            nedenler.append(f"⚠️ Fiyat ortalamaların altında baskılanıyor.")

        # 3. Trend Gücü (ADX)
        if adx > 25:
            nedenler.append(f"🔥 Trend Güçlü (ADX: {adx:.0f} > 25).")
        else:
            puan -= 0.5 
            nedenler.append(f"💤 Trend Zayıf/Yatay (ADX: {adx:.0f}). Testere piyasası riski.")
            
        # 4. RSI Durumu
        if rsi < 30:
            puan += 1
            nedenler.append(f"⚡ RSI ({rsi:.0f}) aşırı satışta. Tepki alımı gelebilir.")
        elif rsi > 70:
            nedenler.append(f"⚠️ RSI ({rsi:.0f}) aşırı ısındı. Kar satışı gelebilir.")
        else:
            nedenler.append(f"ℹ️ RSI ({rsi:.0f}) nötr bölgede.")

        # KARAR
        durum = "NÖTR"
        renk = "GRAY"
        
        if puan >= 2:
            durum = "ALIMDA"
            renk = "GREEN"
        elif puan <= -1:
            durum = "SATIMDA"
            renk = "RED"
            
        # ATR Trailing Stop (Ali Perşembe Stili)
        # Fiyatın 2 ATR altı stop seviyesidir
        stop_seviyesi = fiyat - (atr * 2) 
        if stop_seviyesi < 0: stop_seviyesi = 0

        return {
            "durum": durum,
            "renk": renk,
            "stop_seviyesi": round(stop_seviyesi, 2),
            "detay": {
                "trend_mesaj": "Boğa Piyasası 🐂" if sma50 > sma200 else "Ayı Piyasası 🐻",
                "trend_yonu": "UP" if sma50 > sma200 else "DOWN",
                "aksiyon_mesaj": " | ".join(nedenler), # iOS bunu parçalayacak
                "hacim_mesaj": "Hacim Yüksek" if son['Volume'] > son['Vol_SMA'] else "Hacim Düşük",
                "sikisma_mesaj": None
            }
        }

# ==========================================
# 5. ENDPOINTS
# ==========================================
@app.get("/")
def home(): return {"mesaj": "API V36.0 (Full Paket) Aktif 🚀"}

@app.get("/analiz")
def analiz_yap(sembol: str, piyasa: str = "BIST"):
    s = sembol.upper()
    df = None
    
    try:
        # --- VERİ KAYNAĞI SEÇİMİ ---
        if piyasa == "Fon" or piyasa == "Fonlar":
            motor = FonMotoru()
            df = motor.getir(s)
            if df is None: raise HTTPException(status_code=404, detail="Fon bulunamadı")
            
        else:
            # Yfinance Mapping (Sembol Eşleştirme)
            ticker = s
            if piyasa == "BIST" and not s.endswith(".IS"): ticker = f"{s}.IS"
            elif piyasa == "ABD": ticker = s 
            elif piyasa == "Kripto" and not s.endswith("-USD"): ticker = f"{s}-USD"
            elif piyasa == "Emtia":
                map_emtia = {"ALTIN": "GC=F", "GÜMÜŞ": "SI=F", "PETROL": "CL=F", "DOĞALGAZ": "NG=F", "BAKIR": "HG=F"}
                if s in map_emtia: ticker = map_emtia[s]
            elif piyasa == "Endeksler":
                map_endeks = {
                    "BIST 100": "XU100.IS", "BIST 30": "XU030.IS", "BANKA": "XBANK.IS",
                    "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "DOW JONES": "^DJI", "DAX": "^GDAXI", "VIX": "^VIX"
                }
                if s in map_endeks: ticker = map_endeks[s]
            
            # Veriyi Çek (2 Yıllık - 200 günlük ortalama için şart)
            df = yf.Ticker(ticker).history(period="2y", interval="1d")
        
        if df is None or df.empty: raise HTTPException(status_code=404, detail="Veri yok")

        # --- ANALİZ ---
        motor = AnalizMotoru()
        df = motor.veriyi_hazirla(df)
        sonuc = motor.analiz_et(df)
        
        # --- GRAFİK VERİSİ (Son 90 Gün) ---
        grafik = [{"tarih": str(r.name.date()), "close": r['Close']} for _, r in df.tail(90).iterrows()]

        return {
            "sembol": s,
            "fiyat": round(df['Close'].iloc[-1], 2),
            "analiz": sonuc,
            "grafik_verisi": grafik
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/takvim")
def takvim():
    return {"takvim": TakvimMotoru().getir()}

@app.get("/haberler")
def haberler(terim: str):
    motor = HaberMotoru()
    return motor.getir(terim)
