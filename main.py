import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from tradingview_screener import Query, col

# استيراد TvDatafeed لحساب التاريخي
try:
    from tvdatafeed import TvDatafeed, Interval
    tv = TvDatafeed()
except ImportError:
    tv = None

# إعدادات التلغرام من متغيرات البيئة
TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

RIYADH = ZoneInfo("Asia/Riyadh")
SEEN_FILE = "seen_saudi.json"

MAX_SHOWN = 10  # الحد الأقصى للأسهم المعروضة في الرسالة الواحدة
CHECK_INTERVAL_SECONDS = 180  # الفحص كل 3 دقائق (180 ثانية)

# --- إعدادات فلتر VVV (POC + اختراق + VWAP صاعد + انفجار حجم) ---
VVV_LOOKBACK = 20             # عدد الشموع لتحديد القاعدة/النطاق
VVV_TIGHT_RANGE_MAX = 0.05    # أقصى اتساع للقاعدة كنسبة من السعر (5%)
VVV_VWAP_LOOKBACK = 5         # عدد الشموع للخلف للتأكد أن VWAP صاعد
VVV_REL_VOLUME_MIN = 1.5      # الحد الأدنى لانفجار الحجم مقارنة بمتوسط القاعدة
VVV_VALUE_AREA_PCT = 0.70     # نسبة الفوليوم لمنطقة القيمة (Value Area)
VVV_BINS = 24                 # عدد شرائح فوليوم بروفايل


def get_saudi_stocks_dict():
    """قائمة الأسهم السعودية المحدثة"""
    return {
        # الأسهم المضافة حديثاً
        "4150": "التعمير",
        "9523": "لدن",
        
        # القائمة الأساسية
        "2030": "المصافي", "2222": "أرامكو السعودية", "2380": "بترو رابغ", "2381": "الحفر العربية",
        "2382": "اديس", "4030": "البحري", "1201": "تكوين", "1202": "ميكو", "1210": "بي سي آي",
        "1211": "معادن", "1301": "أسلاك", "1304": "اليمامة للحديد", "1320": "أنابيب السعودية",
        "1321": "أنابيب الشرق", "1322": "أماك", "1323": "يو سي آي سي", "1324": "صالح الراشد",
        "2001": "كيمانول", "2010": "سابك", "2020": "سابك للمغذيات الزراعية", "2060": "التصنيع",
        "2090": "جيسكو", "2150": "زجاج", "2170": "اللجين", "2180": "فيبكو", "2200": "أنابيب",
        "2210": "نماء للكيماويات", "2220": "معدنية", "2223": "لوبريف", "2240": "صناعات",
        "2250": "المجموعة السعودية", "2290": "ينساب", "2300": "صناعة الورق", "2310": "سبكيم العالمية",
        "2330": "المتقدمة", "2350": "كيان السعودية", "2360": "الفخارية", "3002": "اسمنت نجران",
        "3003": "اسمنت المدينة", "3004": "اسمنت الشمالية", "3005": "أسمنت أم القرى", "3007": "الواحة",
        "3008": "الكثيري", "3010": "اسمنت العربية", "3020": "أسمنت اليمامة", "3030": "اسمنت السعودية",
        "3040": "اسمنت القصيم", "3050": "اسمنت الجنوب", "3060": "أسمنت ينبع", "3080": "اسمنت الشرقية",
        "3090": "اسمنت تبوك", "3091": "أسمنت الجوف", "3092": "اسمنت الرياض", "4143": "تالكو",
        "1212": "استرا الصناعية", "1214": "شاكر", "1302": "يوان", "1303": "الصناعات الكهربائية",
        "2040": "الخزف السعودي", "2110": "الكابلات السعودية", "2160": "اميانتيت", "2320": "البابطين",
        "2370": "مسك", "4110": "باتك", "4140": "صادرات", "4141": "العمران", "4142": "كابلات الرياض",
        "4144": "رووم", "4145": "او جي سي", "4146": "جاز", "4147": "سي جي اس", "4148": "الوسائل الصناعية",
        "1831": "مهارة", "1832": "صدر", "1833": "الموارد", "1834": "سماسكو", "1835": "تمكين",
        "4270": "طباعة وتغليف", "6004": "كاتريون", "2190": "سيسكو القابضة", "4031": "الأرضية",
        "4040": "سابتكو", "4260": "بدجت السعودية", "4261": "ذيب", "4262": "لومي", "4263": "سال",
        "4264": "طيران ناس", "4265": "شري", "1213": "نسيج", "2130": "صدق", "2340": "ارتيكس",
        "4011": "لازوردي", "4012": "الأاصيل", "1810": "سيرا", "1820": "بان", "1830": "لحام للرياضة",
        "4090": "طيبة", "4170": "شمس", "4250": "جيل عمر", "4290": "الخليج للتدريب", "4291": "الوطنية للتعليم",
        "4292": "عطاء", "6002": "هرفي للأغذية", "6012": "ريدان", "6013": "التطويرية الغذائية",
        "6014": "التمار", "6015": "أمريكانا", "6016": "برغرايززر", "6017": "جاهز", "6018": "الأندية للرياضة",
        "6019": "المسار الشامل", "6022": "أرماح", "4003": "اكسترا", "4008": "ساكو", "4050": "ساسكو",
        "4051": "باعظيم", "4180": "مجموعة فتيحي", "4190": "جرير", "4191": "أبو معطي", "4192": "السيف غاليري",
        "4193": "نايس ون", "4194": "محطة البناء", "4200": "الدريس", "4240": "سينومي ريتيل",
        "4001": "أسواق العثيم", "4006": "اسواق المزرعة", "4061": "انعام القابضة", "4160": "ثمار",
        "4161": "بن داود", "4162": "المنجم", "4163": "الدواء", "4164": "النهدي", "2050": "مجموعة صافولا",
        "2100": "وفرة", "2140": "ايان", "2270": "سدافكو", "2280": "المراعي", "2281": "تنمية",
        "2282": "نقى", "2283": "المطاحن الأولى", "2284": "المطاحن الحديثة", "2285": "المطاحن العربية",
        "2286": "المطاحن الرابعة", "2287": "انتاج", "2288": "نفوذ", "4080": "سناد القابضة",
        "6001": "حلواني اخوان", "6010": "نادك", "6020": "جلكو", "6040": "تبوك الزراعية", "6050": "الأسماك",
        "6060": "الشرقية سمنة", "6070": "الجوف", "6090": "جازادكو", "4165": "الماجد للعود", "2230": "الكيميائية",
        "4002": "المواساة", "4004": "دله الصحية", "4005": "رعاية", "4007": "الحمادي", "4009": "السعودي الألماني الصحية",
        "4013": "سليمان الحبيب", "4014": "دار المعدات", "4017": "فقيه الطبية", "4018": "الموسى",
        "4019": "اس ام علي للرعاية الصحية", "4021": "المركز الكندي الطبي", "2070": "الدوائية",
        "4015": "جمجوم فارما", "4016": "أفالون فارما", "1010": "الرياض", "1020": "الجزيرة", "1030": "الاستثمار",
        "1050": "بي اس اف", "1060": "الأول", "1080": "العربي", "1120": "الراجحي", "1140": "البلاد",
        "1150": "الإنماء", "1180": "الأهلي", "1111": "مجموعة تداول", "1182": "أملاك", "1183": "سهل",
        "2120": "متطورة", "4081": "النايفات", "4082": "مرنة", "4083": "تسهيل", "4084": "دراية",
        "4130": "درب السعودية", "4280": "المملكة", "7200": "ام أي اس", "7201": "بحر العرب", "7202": "سلوشنز",
        "7203": "علم", "7204": "تويي", "7205": "دي بي اس", "7211": "عزم", "7010": "اس تي سي",
        "7020": "اتحاد اتصالات", "7030": "زين السعودية", "7040": "قو للاتصالات", "2080": "الغاز القابضة",
        "2081": "الخريف", "2082": "أكوا", "2083": "مرافق", "2084": "مباهنا", "5110": "السعودية للطاقة",
        "4330": "الرياض ريت", "4331": "الجزيرة ريت", "4332": "جدوى ريت الحرمين", "4333": "تعليم ريت",
        "4334": "المعذر ريت", "4335": "مشاركة ريت", "4337": "العزيزية ريت", "4338": "الأهلي ريت 1",
        "4339": "دراية ريت", "4340": "الراجحي ريت", "4342": "جدوى ريت السعودية", "4344": "سدكو كابيتال ريت",
        "4345": "الإنماء ريت للتجزئة"
    }


def screens():
    """الفلاتر الأساسية المحسّنة"""
    
    # 1. بداية انطلاق (0.5% - 2.5%)
    early_momentum = [
        col("close") > 0,
        col("change") >= 0.5,
        col("change") <= 2.5,
        col("volume") >= 150000,
        col("close") > col("VWAP")
    ]

    # 2. اختراق لحظي وسيولة (1.0% - 6.0%)
    intraday_breakout = [
        col("close") > 0,
        col("change") >= 1.0,
        col("change") <= 6.0,
        col("volume") >= 200000,
        col("close") > col("VWAP"),
        col("close") > col("EMA20")
    ]

    # 3. اختراق أسبوعي
    swing_choch = [
        col("close") > 0,
        col("change") >= 1.0,
        col("volume") >= 200000,
        col("close") > col("EMA20"),
        col("close") > col("high|1W")
    ]

    # 4. فلتر الانعكاس
    reversal_signal = [
        col("close") > 0,
        col("volume") >= 100000,
        col("RSI") <= 35,
        col("SMA10") > col("SMA20"),
        col("SMA10|1") <= col("SMA20|1")
    ]

    # 5. زخم 3 دقائق
    momentum_3m = [
        col("close") > 0,
        col("change") >= 0.5,
        col("volume") >= 100000,
        col("close") > col("VWAP"),
        col("close") > col("EMA10")
    ]

    # 6. فلتر VVV
    vvv_candidates = [
        col("close") > 0,
        col("change") >= 0.3,
        col("volume") >= 150000,
        col("close") > col("VWAP"),
    ]

    # 7. فلتر الارتداد القوي من القاع اللحظي (V-Shape Reversal)
    v_bottom_bounce = [
        col("close") > 0,
        col("volume") >= 100000,
        col("close") > col("VWAP"),
    ]

    extra = ["close", "change", "volume"]
    return extra, "change", {
        "1️⃣ بداية انطلاق (0.5% - 2.5%)": early_momentum,
        "2️⃣ اختراق لحظي وسيولة (1.0% - 6.0%)": intraday_breakout,
        "3️⃣ اختراق و CHOCH أسبوعي": swing_choch,
        "🔄 فلتر الانعكاس (SMA Cross + RSI <= 35)": reversal_signal,
        "⚡ 5️⃣ زخم 3 دقائق (Pine Script)": momentum_3m,
        "🎯 VVV Alert (POC + اختراق)": vvv_candidates,
        "🔄 7️⃣ ارتداد قوي من القاع (V-Reversal 2%)": v_bottom_bounce,
    }


def calculate_rsi(series, period=14):
    """حساب مؤشر RSI14"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def check_3m_pine_signal(ticker):
    """فحص شروط Pine Script الخاصة بفلتر زخم 3 دقائق"""
    if tv is None:
        return True, None, None

    try:
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=Interval.in_3_minute, n_bars=30)
        if df is None or df.empty or len(df) < 20:
            return False, None, None

        df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()

        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['pv'] = df['typical_price'] * df['volume']
        df['vwap'] = df['pv'].cumsum() / df['volume'].cumsum()

        df['vol_sma20'] = df['volume'].rolling(window=20).mean()
        df['candle_change'] = ((df['close'] - df['open']) / df['open']) * 100

        curr = df.iloc[-1]
        prev1 = df.iloc[-2]
        prev2 = df.iloc[-3]

        is_gain = curr['candle_change'] >= 0.8
        is_vol_acc = (curr['volume'] > prev1['volume']) and (prev1['volume'] > prev2['volume'])
        is_vol_spike = curr['volume'] > (curr['vol_sma20'] * 1.1)
        is_above_trend = (curr['close'] > curr['ema10']) or (curr['close'] > curr['vwap'])

        buy_signal = is_gain and is_vol_acc and is_vol_spike and is_above_trend

        if buy_signal:
            stop_loss = float(curr['low'])
            target_price = float(curr['close'] + ((curr['close'] - curr['low']) * 1.5))
            return True, stop_loss, target_price

        return False, None, None
    except Exception as e:
        print(f"خطأ في فحص فلتر 3 دقائق للسهم {ticker}: {e}")
        return False, None, None


def calculate_volume_profile(df, num_bins=VVV_BINS, value_area_pct=VVV_VALUE_AREA_PCT):
    """حساب POC و Value Area"""
    lo = float(df['low'].min())
    hi = float(df['high'].max())

    if hi == lo:
        return {"poc": hi, "vah": hi, "val": lo}

    bin_size = (hi - lo) / num_bins
    bin_edges = [lo + i * bin_size for i in range(num_bins)]
    bins = {edge: 0.0 for edge in bin_edges}

    typical_prices = (df['high'] + df['low'] + df['close']) / 3
    for tp, vol in zip(typical_prices, df['volume']):
        idx = min(int((tp - lo) / bin_size), num_bins - 1)
        bins[bin_edges[idx]] += float(vol)

    poc_price = max(bins, key=bins.get)

    total_volume = sum(bins.values())
    target_volume = total_volume * value_area_pct
    sorted_prices = sorted(bins.keys())
    poc_idx = sorted_prices.index(poc_price)

    captured = bins[poc_price]
    lo_idx, hi_idx = poc_idx, poc_idx

    while captured < target_volume and (lo_idx > 0 or hi_idx < len(sorted_prices) - 1):
        vol_below = bins[sorted_prices[lo_idx - 1]] if lo_idx > 0 else -1
        vol_above = bins[sorted_prices[hi_idx + 1]] if hi_idx < len(sorted_prices) - 1 else -1

        if vol_above >= vol_below:
            hi_idx += 1
            captured += bins[sorted_prices[hi_idx]]
        else:
            lo_idx -= 1
            captured += bins[sorted_prices[lo_idx]]

    vah = sorted_prices[hi_idx] + bin_size
    val = sorted_prices[lo_idx]

    return {"poc": poc_price, "vah": vah, "val": val}


def check_vvv_setup(ticker):
    """فحص إعداد VVV"""
    if tv is None:
        return False, None

    try:
        n_bars = VVV_LOOKBACK + VVV_VWAP_LOOKBACK + 10
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=Interval.in_15_minute, n_bars=n_bars)
        if df is None or df.empty or len(df) < (VVV_LOOKBACK + VVV_VWAP_LOOKBACK + 1):
            return False, None

        base_df = df.iloc[-(VVV_LOOKBACK + 1):-1]
        current = df.iloc[-1]

        base_high = float(base_df['high'].max())
        base_low = float(base_df['low'].min())
        price = float(current['close'])

        range_pct = (base_high - base_low) / price if price else 1.0
        tight_base = range_pct <= VVV_TIGHT_RANGE_MAX
        breakout = price > base_high

        typical_price = (df['high'] + df['low'] + df['close']) / 3
        pv = typical_price * df['volume']
        vwap_series = pv.cumsum() / df['volume'].cumsum()
        vwap_now = float(vwap_series.iloc[-1])
        vwap_prior = float(vwap_series.iloc[-1 - VVV_VWAP_LOOKBACK])
        vwap_rising = vwap_now > vwap_prior
        price_above_vwap = price > vwap_now

        avg_volume = float(base_df['volume'].mean())
        rel_volume = float(current['volume']) / avg_volume if avg_volume else 0.0
        volume_spike = rel_volume >= VVV_REL_VOLUME_MIN

        is_setup = tight_base and breakout and vwap_rising and price_above_vwap and volume_spike
        if not is_setup:
            return False, None

        vp = calculate_volume_profile(df.iloc[-VVV_LOOKBACK:])

        return True, {
            "poc": vp["poc"],
            "vah": vp["vah"],
            "val": vp["val"],
            "breakout_level": base_high,
            "rel_volume": rel_volume,
            "vwap_vvv": vwap_now,
        }
    except Exception as e:
        print(f"خطأ في فحص إعداد VVV للسهم {ticker}: {e}")
        return False, None


def get_historical_power_trend_age(ticker, interval):
    """حساب عدد الشموع المتتالية لـ Power Trend"""
    if tv is None:
        return 0

    try:
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=interval, n_bars=100)
        if df is None or df.empty or len(df) < 50:
            return 0

        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['sma50'] = df['close'].rolling(window=50).mean()
        df['rsi'] = calculate_rsi(df['close'], 14)

        df['pt_active'] = (
            (df['close'] > df['ema20']) &
            (df['ema20'] > df['sma50']) &
            (df['rsi'] > 50)
        )

        age = 0
        for is_active in reversed(df['pt_active'].values):
            if bool(is_active):
                age += 1
            else:
                break
        return age
    except Exception as e:
        print(f"خطأ في جلب تاريخ الشمعات للسهم {ticker}: {e}")
        return 0


def run_screen(filters, columns, sort_col, tickers_dict):
    symbols = [f"TADAWUL:{t}" for t in tickers_dict.keys()]

    query = (
        Query()
        .set_tickers(*symbols)
        .select(*columns)
        .where(*filters)
        .order_by(sort_col, ascending=False)
        .limit(300)
    )

    try:
        _, df = query.get_scanner_data()
    except Exception as e:
        print(f"خطأ في الاستعلام من TradingView: {e}")
        df = None

    if df is not None and not df.empty:
        df["clean_name"] = df["name"].astype(str).str.replace("TADAWUL:", "").str.strip()
        return df

    return df


def load_seen():
    """تحميل سجل التنبيهات ووقت آخر فحص"""
    today = datetime.now(RIYADH).strftime("%Y-%m-%d")
    try:
        with open(SEEN_FILE) as f:
            data = json.load(f)
        if data.get("date") == today:
            counts = data.get("counts", {})
            last_run_timestamp = data.get("last_run_timestamp", 0)
            return today, counts, last_run_timestamp
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return today, {}, 0


def save_seen(today, counts, last_run_timestamp):
    """حفظ سجل التنبيهات ووقت الفحص الحالي"""
    with open(SEEN_FILE, "w") as f:
        json.dump({
            "date": today,
            "counts": counts,
            "last_run_timestamp": last_run_timestamp
        }, f, indent=2)


def send(text):
    if not TOKEN or not CHAT_ID:
        print("تحذير: BOT_TOKEN أو CHAT_ID غير موجود.")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"خطأ تيليجرام: {e} — نص الرسالة (أول 300 حرف): {text[:300]}")


def escape_html(value) -> str:
    """تهريب رموز HTML لتيليجرام"""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def send_chunked(header, blocks, footer=""):
    """إرسال التنبيهات مقسمة لحزم آمنة تحت حد حروف تلغرام"""
    MAX_LEN = 3800

    chunks = []
    current = f"{header}\n\n" if header else ""

    for block in blocks:
        if current and len(current) + len(block) > MAX_LEN:
            chunks.append(current)
            current = ""
        current += block

    if footer:
        if current and len(current) + len(footer) > MAX_LEN:
            chunks.append(current)
            current = footer
        else:
            current += footer

    if current.strip():
        chunks.append(current)

    for chunk in chunks:
        send(chunk)


def calculate_levels(price, high, low, ema20, ema50):
    pivot = (high + low + price) / 3

    r1 = (2 * pivot) - low if ((2 * pivot) - low) > price else price * 1.025
    r2 = pivot + (high - low) if (pivot + (high - low)) > r1 else r1 * 1.03
    r3 = high + 2 * (pivot - low) if (high + 2 * (pivot - low)) > r2 else r2 * 1.04

    support_intraday = min(low, ema20 if 0 < ema20 < price else low)

    t1, t2, t3, t4 = r1, r2, r3, r3 * 1.03
    t_max = t4 * 1.05

    stop_1 = support_intraday * 0.985

    return {
        "support_intraday": support_intraday,
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "t_max": t_max,
        "stop_1": stop_1,
    }


def main():
    today, counts, last_run_timestamp = load_seen()
    now_timestamp = time.time()

    elapsed = now_timestamp - last_run_timestamp

    if elapsed < CHECK_INTERVAL_SECONDS:
        remaining = int(CHECK_INTERVAL_SECONDS - elapsed)
        print(f"⏳ لم تمضِ 3 دقائق بعد منذ آخر فحص. المتبقي: {remaining} ثانية.")
        return

    print(f"🚀 مرت {int(elapsed)} ثانية - جاري تنفيذ الفحص الشامل لجميع الأسهم والفلاتر...")

    extra, sort_col, defs = screens()
    stocks_dict = get_saudi_stocks_dict()

    tech_cols = [
        "high", "low", "EMA20", "EMA50", "EMA10", "sector", "VWAP",
        "price_52_week_high", "price_52_week_low",
        "high|1W", "high|2W", "RSI", "SMA10", "SMA20", "SMA10|1", "SMA20|1"
    ]

    columns = list(dict.fromkeys(["name", "close", "volume"] + extra + tech_cols))
    price_c, chg_c, vol_c = "close", "change", "volume"
    had_error = False

    for label, filters in defs.items():
        try:
            df = run_screen(filters, columns, sort_col, stocks_dict)
        except Exception as e:
            print(f"[السوق السعودي/{label}] error: {e}")
            had_error = True
            continue

        if df is None or df.empty:
            print(f"[السوق السعودي/{label}] 0 matches")
            continue

        # تطبيق التصفية الخاصة بكل فلتر عبر Pandas
        if "بداية انطلاق" in label:
            df = df[df["close"] >= df["high"] * 0.98]
        elif "اختراق لحظي" in label:
            df = df[df["close"] >= df["high"] * 0.98]
        elif "ارتداد قوي من القاع" in label:
            # صعود بنسبة 2% من القاع + التداول قرب أعلى سعر حققه الارتداد
            df = df[(df["close"] >= df["low"] * 1.02) & (df["close"] >= df["high"] * 0.985)]
        elif label == "⚡ 5️⃣ زخم 3 دقائق (Pine Script)":
            if tv is not None:
                valid_rows = []
                for _, row in df.iterrows():
                    ticker_name = str(row.get('clean_name', row['name'])).strip()
                    is_valid, sl_3m, tp_3m = check_3m_pine_signal(ticker_name)
                    if is_valid:
                        row_dict = row.to_dict()
                        row_dict['sl_3m'] = sl_3m
                        row_dict['tp_3m'] = tp_3m
                        valid_rows.append(row_dict)
                df = pd.DataFrame(valid_rows)
        elif label == "🎯 VVV Alert (POC + اختراق)":
            if tv is not None:
                valid_rows = []
                for _, row in df.iterrows():
                    ticker_name = str(row.get('clean_name', row['name'])).strip()
                    is_valid, vvv_data = check_vvv_setup(ticker_name)
                    if is_valid:
                        row_dict = row.to_dict()
                        row_dict.update(vvv_data)
                        valid_rows.append(row_dict)
                df = pd.DataFrame(valid_rows)
            else:
                df = pd.DataFrame()

        if df.empty:
            print(f"[السوق السعودي/{label}] 0 matches")
            continue

        results = []
        for _, row in df.iterrows():
            ticker_name = str(row.get('clean_name', row['name'])).strip()
            results.append((ticker_name, row))

        print(f"[السوق السعودي/{label}] {len(results)} matches")

        is_vvv_screen = label == "🎯 VVV Alert (POC + اختراق)"
        header_tag = " #vvv_alert" if is_vvv_screen else ""
        header = f"🚨 <b>تحديث الزخم والأسهم | {label}</b>{header_tag}"
        blocks = []

        for idx, (ticker, row) in enumerate(results[:MAX_SHOWN], 1):
            stock_lines = []
            arabic_name = escape_html(stocks_dict.get(ticker, ticker))
            sector = escape_html(str(row.get('sector', 'N/A')).strip())

            tv_url = f"https://www.tradingview.com/chart/?symbol=TADAWUL:{ticker}"

            price = float(row[price_c]) if row[price_c] else 0.0
            change = float(row[chg_c]) if row[chg_c] else 0.0
            volume = float(row[vol_c]) if row[vol_c] else 0.0
            vwap = float(row.get('VWAP', 0.0) or 0.0)
            rsi = float(row.get('RSI', 0.0) or 0.0)

            high = float(row['high']) if 'high' in row and row['high'] else price * 1.02
            low = float(row['low']) if 'low' in row and row['low'] else price * 0.98
            ema20 = float(row['EMA20']) if 'EMA20' in row and row['EMA20'] else price * 0.99
            ema50 = float(row['EMA50']) if 'EMA50' in row and row['EMA50'] else price * 0.97

            age_4h = get_historical_power_trend_age(ticker, Interval.in_4_hour) if tv else 0
            age_15m = get_historical_power_trend_age(ticker, Interval.in_15_minute) if tv else 0

            high_1w = float(row.get('high|1W', 0.0) or 0.0)
            high_2w = float(row.get('high|2W', 0.0) or 0.0)
            has_weekly_choch = (high_1w > 0 and price > high_1w) or (high_2w > 0 and price > high_2w)

            high52 = float(row.get('price_52_week_high', 0.0) or 0.0)
            low52 = float(row.get('price_52_week_low', 0.0) or 0.0)

            dist_high52 = ((price - high52) / high52 * 100) if high52 > 0 else 0.0
            dist_low52 = ((price - low52) / low52 * 100) if low52 > 0 else 0.0

            curr_count = counts.get(ticker, 0) + 1
            counts[ticker] = curr_count

            lvl = calculate_levels(price, high, low, ema20, ema50)

            if is_vvv_screen:
                stock_lines.append(f"🎯 <b>#vvv_alert – #{idx} {arabic_name} ({ticker})</b>")
            else:
                stock_lines.append(f"🔥 <b>دخول جديد إلى القائمة – #{idx} {arabic_name} ({ticker})</b>")
            stock_lines.append(f"🚨 🛑 <b>[تنبيه {curr_count}]</b>")

            if age_4h > 0:
                warning_label = " ( ⚠️اتجاه متقدم)" if age_4h > 4 else ""
                stock_lines.append(f"• Power Trend 4H : شمعة {age_4h}{warning_label}")

            if age_15m > 0:
                stock_lines.append(f"• Power Trend 15M : شمعة {age_15m}")

            if rsi > 0:
                stock_lines.append(f"📉 <b>RSI:</b> {rsi:.1f}")
            if has_weekly_choch:
                stock_lines.append("⚡️ <b>[CHOCH أسبوعي إيجابي: كسر القمة الأسبوعية]</b>")

            stock_lines.append(f"🏢 <b>القطاع:</b> {sector}")
            stock_lines.append(f"💵 <b>السعر:</b> {price:.2f} ر.س | <b>التغير:</b> +{change:.1f}% | Vol: {int(volume):,}")
            if high52 > 0 and low52 > 0:
                stock_lines.append(f"🏔️ <b>قمة 52 أسبوع:</b> {high52:.2f} ر.س ({dist_high52:.1f}%)")
                stock_lines.append(f"⛰️ <b>قاع 52 أسبوع:</b> {low52:.2f} ر.س (+{dist_low52:.1f}%)")
            stock_lines.append(f"📈 <b>الشارت:</b> <a href='{tv_url}'>TradingView</a>")

            if 'tp_3m' in row and row['tp_3m'] and 'sl_3m' in row and row['sl_3m']:
                stock_lines.append(f"🎯 <b>هدف 3m (1.5 R:R):</b> {row['tp_3m']:.2f} ر.س | ⛔️ <b>وقف 3m:</b> {row['sl_3m']:.2f} ر.س")

            if 'poc' in row and row.get('poc'):
                stock_lines.append(f"📍 <b>POC:</b> {row['poc']:.2f} ر.س | <b>Value Area:</b> {row['val']:.2f} - {row['vah']:.2f} ر.س")
                stock_lines.append(f"💥 <b>مستوى الاختراق:</b> {row['breakout_level']:.2f} ر.س | <b>Rel Vol:</b> {row['rel_volume']:.2f}x")

            stock_lines.append(f"🎯 <b>الأهداف:</b> {lvl['t1']:.2f} ر.س -&gt; {lvl['t2']:.2f} ر.س -&gt; {lvl['t3']:.2f} ر.س")
            stock_lines.append(f"(أقصى هدف: {lvl['t_max']:.2f} ر.س)")
            stock_lines.append(f"🛡️ <b>الدعم:</b> {lvl['support_intraday']:.2f} ر.س | ⛔️ <b>الوقف:</b> {lvl['stop_1']:.2f} ر.س")
            if vwap > 0:
                stock_lines.append(f"📊 <b>VWAP:</b> {vwap:.2f} ر.س")
            stock_lines.append("-----------------------------------\n")

            blocks.append("\n".join(stock_lines))

        footer = ""
        if len(results) > MAX_SHOWN:
            footer = f"\n+{len(results) - MAX_SHOWN} أسهم أخرى متطابقة...\nللفرز فقط، تأكد على الشارت قبل أي قرار."
        else:
            footer = "\nللفرز فقط، تأكد على الشارت قبل أي قرار."

        send_chunked(header, blocks, footer)

    save_seen(today, counts, now_timestamp)
    if had_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
