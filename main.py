import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from tradingview_screener import Query, col

# استيراد TvDatafeed لحساب التاريخي والهارمونيك
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
        "4150": "التعمير", "9523": "لدن", "2030": "المصافي", "2222": "أرامكو السعودية", 
        "2380": "بترو رابغ", "2381": "الحفر العربية", "2382": "اديس", "4030": "البحري", 
        "1201": "تكوين", "1202": "ميكو", "1210": "بي سي آي", "1211": "معادن", 
        "1301": "أسلاك", "1304": "اليمامة للحديد", "1320": "أنابيب السعودية", 
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
        "1831": "مهارة", "1832": "صدر", "1833": "الموارد", "1834": "سماسكو", "1835": "تمكين",
        "4270": "طباعة وتغليف", "6004": "كاتريون", "2190": "سيسكو القابضة", "4031": "الأرضية",
        "4040": "سابتكو", "4260": "بدجت السعودية", "4261": "ذيب", "4262": "لومي", "4263": "سال",
        "1810": "سيرا", "4090": "طيبة", "4170": "شمس", "4250": "جبل عمر", "4290": "الخليج للتدريب",
        "4291": "الوطنية للتعليم", "4292": "عطاء", "6002": "هرفي للأغذية", "6013": "التطويرية الغذائية",
        "6015": "أمريكانا", "6017": "جاهز", "4003": "اكسترا", "4008": "ساكو", "4050": "ساسكو",
        "4190": "جرير", "4192": "السيف غاليري", "4200": "الدريس", "4001": "أسواق العثيم",
        "4161": "بن داود", "4162": "المنجم", "4163": "الدواء", "4164": "النهدي", "2050": "مجموعة صافولا",
        "2270": "سدافكو", "2280": "المراعي", "2281": "تنمية", "2283": "المطاحن الأولى", "2284": "المطاحن الحديثة",
        "6010": "نادك", "6070": "الجوف", "4002": "المواساة", "4004": "دله الصحية", "4005": "رعاية",
        "4007": "الحمادي", "4009": "السعودي الألماني الصحية", "4013": "سليمان الحبيب", "4017": "فقيه الطبية",
        "2070": "الدوائية", "4015": "جمجوم فارما", "1010": "الرياض", "1020": "الجزيرة", "1030": "الاستثمار",
        "1050": "بي اس اف", "1060": "الأول", "1080": "العربي", "1120": "الراجحي", "1140": "البلاد",
        "1150": "الإنماء", "1180": "الأهلي", "1111": "مجموعة تداول", "7200": "ام أي اس", "7202": "سلوشنز",
        "7203": "علم", "7010": "اس تي سي", "7020": "اتحاد اتصالات", "7030": "زين السعودية", "2082": "أكوا",
        "2083": "مرافق", "5110": "السعودية للطاقة"
    }


def screens():
    """الفلاتر الأساسية مع تعديل الشروط"""
    
    # 1. بداية انطلاق (0.5% - 2.5%) - فوليوم 100k
    early_momentum = [
        col("close") > 0,
        col("change") >= 0.5,
        col("change") <= 2.5,
        col("volume") >= 100000,
        col("close") > col("VWAP")
    ]

    # 2. اختراق لحظي وسيولة (1.0% - 6.0%) - فوليوم 100k
    intraday_breakout = [
        col("close") > 0,
        col("change") >= 1.0,
        col("change") <= 6.0,
        col("volume") >= 100000,
        col("close") > col("VWAP"),
        col("close") > col("EMA20")
    ]

    # 3. اختراق أسبوعي - فوليوم 100k
    swing_choch = [
        col("close") > 0,
        col("change") >= 1.0,
        col("volume") >= 100000,
        col("close") > col("EMA20"),
        col("close") > col("high|1W")
    ]

    # 4. فلتر الانعكاس الهارمونيك المطور (تصفية مبدئية)
    reversal_signal = [
        col("close") > 0,
        col("volume") >= 20000,
        col("RSI") <= 40,
    ]

    # 5. زخم 3 دقائق - فوليوم تصفية مبدئي
    momentum_3m = [
        col("close") > 0,
        col("change") >= 0.5,
        col("volume") >= 10000,
        col("close") > col("VWAP"),
        col("close") > col("EMA10")
    ]

    # 6. فلتر VVV - فوليوم 80k
    vvv_candidates = [
        col("close") > 0,
        col("change") >= 0.3,
        col("volume") >= 80000,
        col("close") > col("VWAP"),
    ]

    # 7. فلتر الارتداد المبكر (15 دقيقة) - فوليوم تصفية مبدئي
    v_bottom_bounce_15m = [
        col("close") > 0,
        col("volume") >= 5000,
    ]

    extra = ["close", "change", "volume"]
    return extra, "change", {
        "1️⃣ بداية انطلاق (0.5% - 2.5%)": early_momentum,
        "2️⃣ اختراق لحظي وسيولة (1.0% - 6.0%)": intraday_breakout,
        "3️⃣ اختراق و CHOCH أسبوعي": swing_choch,
        "🔄 4️⃣ الانعكاس والهارمونيك AB=CD (1H)": reversal_signal,
        "⚡ 5️⃣ زخم 3 دقائق (Pine Script)": momentum_3m,
        "🎯 VVV Alert (POC + اختراق)": vvv_candidates,
        "🔄 7️⃣ ارتداد الفوليوم المبكر (فاصل 15 دقيقة)": v_bottom_bounce_15m,
    }


def calculate_rsi(series, period=14):
    """حساب مؤشر RSI14"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def check_abcd_reversal_1h(ticker):
    """فحص نموذج الهارمونيك AB=CD وانعكاس الزخم على فاصل 1H"""
    if tv is None:
        return True, None

    try:
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=Interval.in_1_hour, n_bars=60)
        if df is None or df.empty or len(df) < 30:
            return False, None

        df['rsi'] = calculate_rsi(df['close'], 14)
        df['sma10'] = df['close'].rolling(10).mean()
        df['sma20'] = df['close'].rolling(20).mean()

        curr = df.iloc[-1]
        curr_vol = float(curr['volume'])
        curr_price = float(curr['close'])
        curr_rsi = float(curr['rsi']) if not pd.isna(curr['rsi']) else 50.0

        # شرط السيولة: شمعة الساعة >= 20,000 سهم
        if curr_vol < 20000:
            return False, None

        # استخراج القمم والقيعان (Pivot Highs & Pivot Lows)
        highs = df['high'].values
        lows = df['low'].values

        pivot_highs = []
        pivot_lows = []

        for i in range(2, len(df) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                pivot_highs.append((i, highs[i]))
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                pivot_lows.append((i, lows[i]))

        has_abcd = False
        prz_d = 0.0
        bc_ratio = 0.0

        # البحث عن متتالية الهارمونيك A -> B -> C -> D
        if len(pivot_highs) >= 2 and len(pivot_lows) >= 1:
            for ph1 in reversed(pivot_highs[-4:]):  # القمة A
                a_idx, a_price = ph1
                b_candidates = [pl for pl in pivot_lows if pl[0] > a_idx]  # القاع B
                if not b_candidates:
                    continue
                b_idx, b_price = b_candidates[0]

                c_candidates = [ph for ph in pivot_highs if ph[0] > b_idx and ph[1] < a_price]  # القمة C
                if not c_candidates:
                    continue
                c_idx, c_price = c_candidates[0]

                if len(df) - 1 <= c_idx:
                    continue

                ab_len = a_price - b_price
                bc_len = c_price - b_price

                if ab_len <= 0 or bc_len <= 0:
                    continue

                ratio = bc_len / ab_len

                # نسبة تصحيح الموجة BC يجب أن تكون بين 50% إلى 88.6%
                if 0.50 <= ratio <= 0.886:
                    target_d = c_price - ab_len  # معادلة AB = CD
                    price_diff_pct = abs(curr_price - target_d) / target_d * 100

                    # التأكد من وصول السعر لنطاق منطقة الانعكاس PRZ (هامش ±2.5%)
                    if price_diff_pct <= 2.5:
                        has_abcd = True
                        prz_d = target_d
                        bc_ratio = ratio * 100
                        break

        # شروط تأكيد الارتداد
        sma_cross = float(curr['sma10']) > float(curr['sma20']) if not pd.isna(curr['sma10']) and not pd.isna(curr['sma20']) else False
        rsi_oversold = curr_rsi <= 38
        is_green_candle = curr_price > float(curr['open'])

        # قبول الإشارة إذا تحقق نموذج AB=CD مع تأكيد زخم، أو انعكاس RSI و SMA كلاسيكي
        if has_abcd and (rsi_oversold or sma_cross or is_green_candle):
            return True, {
                "vol_1h": int(curr_vol),
                "rsi_1h": curr_rsi,
                "has_abcd": True,
                "prz_d": prz_d,
                "bc_ratio": bc_ratio
            }
        elif not has_abcd and rsi_oversold and sma_cross:
            return True, {
                "vol_1h": int(curr_vol),
                "rsi_1h": curr_rsi,
                "has_abcd": False
            }

        return False, None
    except Exception as e:
        print(f"خطأ في فحص نموذج AB=CD للسهم {ticker}: {e}")
        return False, None


def check_15m_bounce_signal(ticker):
    """فحص الارتداد المبكر وتصاعد الفوليوم (>= 5,000 للشمعة) على فاصل 15 دقيقة"""
    if tv is None:
        return True, None

    try:
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=Interval.in_15_minute, n_bars=25)
        if df is None or df.empty or len(df) < 15:
            return False, None

        df['vol_sma10'] = df['volume'].rolling(window=10).mean()

        curr = df.iloc[-1]
        prev1 = df.iloc[-2]
        prev2 = df.iloc[-3]

        local_low = float(df['low'].iloc[-4:].min())
        curr_price = float(curr['close'])

        bounce_pct = ((curr_price - local_low) / local_low) * 100
        has_bounce = bounce_pct >= 0.8

        curr_vol = float(curr['volume'])
        has_min_vol_15m = curr_vol >= 5000

        vol_sma = float(curr['vol_sma10']) if curr['vol_sma10'] else 1.0
        vol_spike = curr_vol >= (vol_sma * 1.25)
        vol_ascending = (curr_vol > float(prev1['volume'])) and (float(prev1['volume']) > float(prev2['volume']))

        is_green_candle = curr_price > float(curr['open']) or curr_price >= float(curr['high']) * 0.998

        if has_bounce and has_min_vol_15m and (vol_spike or vol_ascending) and is_green_candle:
            return True, {
                "bounce_pct": bounce_pct,
                "vol_15m": int(curr_vol),
                "vol_ratio": curr_vol / vol_sma if vol_sma else 1.0
            }

        return False, None
    except Exception as e:
        print(f"خطأ في فحص ارتداد 15 دقيقة للسهم {ticker}: {e}")
        return False, None


def check_3m_pine_signal(ticker):
    """فحص شروط زخم 3 دقائق (فوليوم الشمعة الحالية >= 10,000)"""
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

        curr_vol = float(curr['volume'])
        has_min_vol_3m = curr_vol >= 10000

        is_gain = curr['candle_change'] >= 0.8
        is_vol_acc = (curr_vol > prev1['volume']) and (prev1['volume'] > prev2['volume'])
        is_vol_spike = curr_vol > (curr['vol_sma20'] * 1.1)
        is_above_trend = (curr['close'] > curr['ema10']) or (curr['close'] > curr['vwap'])

        buy_signal = is_gain and is_vol_acc and is_vol_spike and is_above_trend and has_min_vol_3m

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
        print(f"خطأ تيليجرام: {e} — نص الرسالة: {text[:300]}")


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

    t1, t2, t3 = r1, r2, r3
    t_max = r3 * 1.05
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

        # تطبيق التصفية الخاصة بكل فلتر
        if "بداية انطلاق" in label:
            df = df[df["close"] >= df["high"] * 0.98]
        elif "اختراق لحظي" in label:
            df = df[df["close"] >= df["high"] * 0.98]
        elif "الانعكاس" in label:
            # فحص الهارمونيك AB=CD وفوليوم شمعة الساعة
            if tv is not None:
                valid_rows = []
                for _, row in df.iterrows():
                    ticker_name = str(row.get('clean_name', row['name'])).strip()
                    is_valid, abcd_info = check_abcd_reversal_1h(ticker_name)
                    if is_valid:
                        row_dict = row.to_dict()
                        if abcd_info:
                            row_dict.update(abcd_info)
                        valid_rows.append(row_dict)
                df = pd.DataFrame(valid_rows)
        elif "15 دقيقة" in label:
            if tv is not None:
                valid_rows = []
                for _, row in df.iterrows():
                    ticker_name = str(row.get('clean_name', row['name'])).strip()
                    is_valid, bounce_info = check_15m_bounce_signal(ticker_name)
                    if is_valid:
                        row_dict = row.to_dict()
                        row_dict.update(bounce_info)
                        valid_rows.append(row_dict)
                df = pd.DataFrame(valid_rows)
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
            rsi = float(row.get('rsi_1h', row.get('RSI', 0.0)) or 0.0)

            high = float(row['high']) if 'high' in row and row['high'] else price * 1.02
            low = float(row['low']) if 'low' in row and row['low'] else price * 0.98
            ema20 = float(row['EMA20']) if 'EMA20' in row and row['EMA20'] else price * 0.99
            ema50 = float(row['EMA50']) if 'EMA50' in row and row['EMA50'] else price * 0.97

            curr_count = counts.get(ticker, 0) + 1
            counts[ticker] = curr_count

            lvl = calculate_levels(price, high, low, ema20, ema50)

            stock_lines.append(f"🔥 <b>دخول جديد إلى القائمة – #{idx} {arabic_name} ({ticker})</b>")
            stock_lines.append(f"🚨 🛑 <b>[تنبيه {curr_count}]</b>")

            if row.get('has_abcd'):
                stock_lines.append(f"📐 <b>نموذج الهارمونيك:</b> AB=CD مكتمل على فاصل الساعة (1H)")
                stock_lines.append(f"🎯 <b>منطقة الانعكاس PRZ (D):</b> {row['prz_d']:.2f} ر.س | <b>نسبة BC:</b> {row['bc_ratio']:.1f}%")

            if 'vol_1h' in row:
                stock_lines.append(f"⏱️ <b>فوليوم شمعة الساعة:</b> {row['vol_1h']:,} سهم")

            if 'bounce_pct' in row:
                stock_lines.append(f"📈 <b>ارتداد 15M:</b> +{row['bounce_pct']:.2f}% من القاع اللحظي")
                stock_lines.append(f"📊 <b>فوليوم 15M:</b> {row['vol_15m']:,} (تسارع {row['vol_ratio']:.1f}x)")

            if rsi > 0:
                stock_lines.append(f"📉 <b>RSI (1H):</b> {rsi:.1f}")

            stock_lines.append(f"🏢 <b>القطاع:</b> {sector}")
            stock_lines.append(f"💵 <b>السعر:</b> {price:.2f} ر.س | <b>التغير:</b> +{change:.1f}% | Vol: {int(volume):,}")
            stock_lines.append(f"📈 <b>الشارت:</b> <a href='{tv_url}'>TradingView</a>")

            stock_lines.append(f"🎯 <b>الأهداف:</b> {lvl['t1']:.2f} ر.س -&gt; {lvl['t2']:.2f} ر.س -&gt; {lvl['t3']:.2f} ر.س")
            stock_lines.append(f"🛡️ <b>الدعم:</b> {lvl['support_intraday']:.2f} ر.س | ⛔️ <b>الوقف:</b> {lvl['stop_1']:.2f} ر.س")
            if vwap > 0:
                stock_lines.append(f"📊 <b>VWAP:</b> {vwap:.2f} ر.س")
            stock_lines.append("-----------------------------------\n")

            blocks.append("\n".join(stock_lines))

        footer = "\nللفرز فقط، تأكد على الشارت قبل أي قرار."
        send_chunked(header, blocks, footer)

    save_seen(today, counts, now_timestamp)
    if had_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
