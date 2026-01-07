from fastapi import FastAPI, HTTPException, Query
import yfinance as yf
import pandas_ta as ta
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import borsapy as bp
from datetime import datetime

# ==========================================
# 🚀 API AYARLARI (V28.0 Final)
# ==========================================
app = FastAPI(
    title="Pro Terminal API",
    description="Backtest + Grafik + Takvim + Haberler",
    version="28.0"
)

# ==========================================
# 1. SAĞLAMLAŞTIRILMIŞ TAKVİM MOTORU
# ==========================================
class TakvimMotoru:
    def getir(self):
        veriler = []
        try:
            # 1. YÖNTEM: Borsapy Kütüphanesi
            cal = bp.EconomicCalendar()
            df = cal.events(period="1w") 
            
            if not df.empty:
                for _, row in df.iterrows():
                    onem = str(row.get('Importance', '1'))
                    # Sadece Orta (2) ve Yüksek (3) önemlileri al
                    if onem in ['2', '3', 'High', 'Medium']:
                        veriler.append({
                            "saat": str(row.get('Time', '00:00')),
                            "ulke": str(row.get('Country', 'Dünya')),
                            "olay": str(row.get('Event', 'Bilinmeyen Olay')),
                            "onem": "Yüksek" if onem in ['3', 'High'] else "Orta"
                        })
            
            # Eğer boş döndüyse hata fırlat (Yedeğe geçsin)
            if not veriler: raise Exception("Borsapy boş veri döndü")
            
            return veriler[:20]

        except Exception as e:
            print(f"Takvim Hatası (Yedek Devrede): {e}")
            # 2. YÖNTEM: YEDEK MANUEL LİSTE
            return [
                {"saat": "15:30", "ulke": "ABD", "olay": "Tarım Dışı İstihdam (Tahmin)", "onem": "Yüksek"},
                {"saat": "16:00", "ulke": "ABD", "olay": "İşsizlik Oranı", "onem": "Yüksek"},
                {"saat": "21:00", "ulke": "ABD", "olay": "FED Faiz Kararı", "onem": "Yüksek"},
                {"saat": "10:00", "ulke": "TUR", "olay": "Enflasyon Verisi (TÜFE)", "onem": "Yüksek"},
                {"saat": "⚠️", "ulke": "Sistem", "olay": "Canlı Veri Çekilemedi (Manuel Mod)", "onem": "Düşük"}
            ]

# ==========================================
# 2. HABER MOTORU (Google RSS)
# ==========================================
class HaberMotoru:
    def getir(self, terim: str):
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
# 3. GELİŞMİŞ ANALİZ MOTORU
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

        # Göstergeler
        df.ta.atr(length=14, append=True)
        df.ta.adx(length=14, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        
        # Hacim Ortalaması
        df['Vol_SMA'] = df['Volume'].rolling(20).mean()
        
        return df.dropna()

    def sinyal_uret(self, df, atr_kat):
        trades = []
        in_pos = False
        stop_loss = 0.0
        live_status = "NÖTR"
        live_stop = 0.0
        
        # Backtest Döngüsü
        for i in range(1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            
            # Sinyal Koşulları
            trend_up = row['MA_Short'] > row['MA_Long']
            trend_down = row['MA_Short'] < row['MA_Long']
            rsi_uygun = row['RSI_14'] < 70
            
            # Alım
            if not in_pos and trend_up and rsi_uygun:
                in_pos = True
                stop_loss = row['Close'] - (row['ATRr_14'] * atr_kat)
                trades.append({'tarih': str(row.name.date()), 'islem': 'ALIŞ', 'fiyat': row['Close'], 'sonuc': 0})
                live_status = "ALIMDA"
                live_stop = stop_loss
            
            # Satış / Stop
            elif in_pos:
                stop_oldu = row['Low'] < stop_loss
                trend_dondu = trend_down
                
                if stop_oldu or trend_dondu:
                    in_pos = False
                    cikis_fiyati = stop_loss if stop_oldu else row['Close']
                    # Kar/Zarar Hesapla
                    giris_fiyati = trades[-1]['fiyat']
                    pnl = (cikis_fiyati - giris_fiyati) / giris_fiyati
                    
                    trades.append({'tarih': str(row.name.date()), 'islem': 'SATIŞ', 'fiyat': cikis_fiyati, 'sonuc': round(pnl*100, 2)})
                    live_status = "NÖTR"
                else:
                    # İz Süren Stop (Trailing Stop)
                    new_stop = row['Close'] - (row['ATRr_14'] * atr_kat)
                    if new_stop > stop_loss: stop_loss = new_stop
                    live_stop = stop_loss
        
        return trades, live_status, live_stop

def detayli_yorum(df, status, stop):
    son = df.iloc[-1]
    return {
        "trend_mesaj": "Yükseliş Trendi 🐂" if son['MA_Short'] > son['MA_Long'] else "Düşüş Trendi 🐻",
        "trend_yonu": "UP" if son['MA_Short'] > son['MA_Long'] else "DOWN",
        "aksiyon_mesaj": f"Sistem şu an {status}. Stop: {stop:.2f}" if status == "ALIMDA" else "Nakitte bekle.",
        "hacim_mesaj": "Hacim Ortalamanın Üstünde 🔥" if son['Volume'] > son['Vol_SMA'] else "Hacim Zayıf",
        "sikisma_mesaj": None
    }

# ==========================================
# 4. ENDPOINTS (KAPI NUMARALARI)
# ==========================================
@app.get("/")
def home(): return {"mesaj": "API V28.0 Aktif 🚀"}

@app.get("/analiz")
def analiz_yap(sembol: str, piyasa: str = "BIST", profil: str = "Trader"):
    # 1. Profil Ayarları
    if profil == "Scalper": p_set = ("EMA", 9, 21, 1.5, "6mo")
    elif profil == "Trader": p_set = ("SMA", 50, 200, 2.5, "2y")
    else: p_set = ("SMA", 100, 200, 3.5, "5y")
    
    ma, kisa, uzun, atr, vade = p_set
    
    # 2. Sembol Düzeltme
    s = sembol.upper()
    if piyasa == "BIST" and not s.endswith(".IS"): s += ".IS"
    elif piyasa == "Kripto" and not s.endswith("-USD"): s += "-USD"
    elif piyasa == "Emtia":
        d = {"ALTIN": "GC=F", "PETROL": "CL=F", "GÜMÜŞ": "SI=F"}
        if s in d: s = d[s]

    try:
        # 3. Veri Çek
        df = yf.Ticker(s).history(period=vade, interval="1d")
        if df.empty: raise HTTPException(status_code=404, detail="Veri yok")
        
        # 4. Analiz Et
        motor = AnalizMotoru()
        df = motor.veriyi_hazirla(df, kisa, uzun, ma)
        trades, status, stop = motor.sinyal_uret(df, atr)
        yorum = detayli_yorum(df, status, stop)
        
        # 5. Grafik Verisi (Son 60 gün - iOS Charts için)
        grafik = [{"tarih": str(r['Date'].date()), "close": r['Close']} for _, r in df.tail(60).reset_index().iterrows()]
        
        # 6. Backtest Özeti Hesapla
        karli = [t for t in trades if t['islem'] == 'SATIŞ' and t['sonuc'] > 0]
        tum_satis = [t for t in trades if t['islem'] == 'SATIŞ']
        basari = 0.0
        toplam_getiri = sum([t['sonuc'] for t in tum_satis])
        
        if tum_satis: basari = (len(karli) / len(tum_satis)) * 100

        # 7. Sonuç Dön
        return {
            "sembol": s,
            "fiyat": round(df['Close'].iloc[-1], 2),
            "analiz": {"durum": status, "stop_seviyesi": round(stop, 2), "detay": yorum},
            "backtest": {"toplam_islem": len(trades), "basari_orani": round(basari, 1), "toplam_getiri": round(toplam_getiri, 1)},
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
