import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from tradingview_screener import Query, col

# استيراد TvDatafeed لحساب التاريخي (RSI 15 دقيقة + ما بعد الإغلاق)
try:
    try:
        from tvDatafeed import TvDatafeed, Interval
    except ImportError:
        from tvdatafeed import TvDatafeed, Interval
    tv = TvDatafeed()
except ImportError as e:
    print(f"⚠️ tvdatafeed غير متاح، الفلاتر التاريخية معطلة: {e}")
    tv = None

# إعدادات التلغرام من متغيرات البيئة
TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

RIYADH = ZoneInfo("Asia/Riyadh")
SEEN_FILE = "seen_saudi.json"

# تشغيل يدوي للتجربة: يتجاوز فاصل 3 دقائق وشرط ارتفاع السعر ويرسل رسائل جديدة
FORCE_RESEND = os.environ.get("FORCE_RESEND", "").strip().lower() == "true"

MAX_SHOWN = 10  # الحد الأقصى للأسهم المعروضة في الرسالة الواحدة
CHECK_INTERVAL_SECONDS = 180  # الفحص كل 3 دقائق (180 ثانية)

# --- إعدادات الفلاتر الجديدة ---
MIN_VOLUME = 20000            # الحد الأدنى للسيولة (فوليوم) في كل الفلاتر
OPEN_MOVE_MIN = 0.5           # أدنى حركة % من سعر الافتتاح
RSI_BOUNCE_LEVELS = (30, 40)  # مستويات ارتداد RSI (فاصل 15 دقيقة)
RSI_MOMENTUM_LEVEL = 60       # مستوى اختراق RSI للزخم (فاصل 15 دقيقة)
RSI_15M_BARS = 60             # عدد شموع 15 دقيقة لحساب RSI
POST_CLOSE_HOUR = 15          # ساعة الإغلاق (توقيت السعودية)
POST_MOVE_MIN_PCT = 1.0       # أدنى ارتفاع % عن شمعة إغلاق 15:00
POST_1M_BARS = 120            # عدد شموع الدقيقة لفحص ما بعد الإغلاق

# --- إعدادات الفلتر القوي المدمج (انعكاس + شمعة سيولة + سكويز) على 15 دقيقة ---
STRONG_15M_BARS = 80          # عدد شموع 15 دقيقة المجلوبة
STRONG_RSI_LOW = 40           # RSI لازم يكون نزل إلى هذا المستوى أو أقل مؤخراً
STRONG_RSI_LOOKBACK = 12      # عدد الشموع للبحث عن قاع RSI
STRONG_BLACK_LOOKBACK = 8     # عدد الشموع للبحث عن شمعة السيولة السوداء
STRONG_BLACK_MULT = 1.8       # فوليوم شمعة السيولة >= 1.8x متوسط آخر 20 شمعة
SQ_LENGTH = 20                # طول السكويز (بولنجر / كلتنر / المومنتم)
SQ_BB_MULT = 2.0              # مضاعف البولنجر
SQ_KC_MULT = 1.5              # مضاعف كلتنر
SQ_FIRE_LOOKBACK = 5          # انفجار السكويز خلال آخر N شموع

# --- إعدادات بطاقة LIVE (شمعة السيولة السوداء + الدايموند) ---
LIVE_1M_BARS = 60             # عدد شموع الدقيقة المستخدمة في التحليل
LIQ_LOOKBACK = 20             # عدد الشموع لحساب متوسط الفوليوم
LIQ_VOLUME_MULT = 1.8         # شمعة السيولة السوداء: فوليوم >= 1.8x المتوسط


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
    """الفلاتر الأساسية (4 فلاتر)"""
    open_move = [
        col("close") > 0,
        col("change_from_open") >= OPEN_MOVE_MIN,
        col("volume") >= MIN_VOLUME,
    ]

    post_close_candidates = [
        col("close") > 0,
        col("volume") >= MIN_VOLUME,
    ]

    # فلترة أولية بـ RSI|15 فقط لتقليل عدد الأسهم المفحوصة تاريخياً
    rsi_bounce_candidates = [
        col("close") > 0,
        col("volume") >= MIN_VOLUME,
        col("RSI|15") >= 30,
        col("RSI|15") <= 50,
    ]

    rsi_momentum_candidates = [
        col("close") > 0,
        col("volume") >= MIN_VOLUME,
        col("RSI|15") >= RSI_MOMENTUM_LEVEL,
        col("RSI|15") <= 75,
    ]

    # فلترة أولية بـ RSI|15 فقط لتقليل عدد الأسهم المفحوصة تاريخياً
    strong_candidates = [
        col("close") > 0,
        col("volume") >= MIN_VOLUME,
        col("RSI|15") >= STRONG_RSI_LOW,
        col("RSI|15") <= 80,
    ]

    extra = ["close", "change", "volume"]
    return extra, "change", {
        "1️⃣ انطلاق من الافتتاح (+0.5% وسيولة 20K)": open_move,
        "🌙 2️⃣ ما بعد الإغلاق (+1% عن إغلاق 15:00)": post_close_candidates,
        "🔄 3️⃣ انعكاس RSI من 30/40 (15 دقيقة)": rsi_bounce_candidates,
        "⚡ 4️⃣ زخم RSI فوق 60 (15 دقيقة)": rsi_momentum_candidates,
        "💎 5️⃣ قوي: انعكاس + سيولة + سكويز (15 دقيقة)": strong_candidates,
    }


def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def check_rsi_bounce_15m(ticker):
    """انعكاس: RSI (15 دقيقة) ارتد صعوداً فوق 30 أو فوق 40 (كان تحته في الشمعة السابقة)"""
    if tv is None:
        return False, None

    try:
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=Interval.in_15_minute, n_bars=RSI_15M_BARS)
        if df is None or df.empty or len(df) < 20:
            return False, None

        df['rsi'] = calculate_rsi(df['close'], 14)
        curr_rsi = df['rsi'].iloc[-1]
        prev_rsi = df['rsi'].iloc[-2]
        if pd.isna(curr_rsi) or pd.isna(prev_rsi):
            return False, None

        for level in RSI_BOUNCE_LEVELS:
            if prev_rsi <= level < curr_rsi:
                return True, {
                    "rsi_15m": float(curr_rsi),
                    "rsi_prev_15m": float(prev_rsi),
                    "rsi_level": level,
                }

        return False, None
    except Exception as e:
        print(f"خطأ في فحص انعكاس RSI 15 دقيقة للسهم {ticker}: {e}")
        return False, None


def check_rsi_momentum_15m(ticker):
    """زخم: RSI (15 دقيقة) تجاوز 60 صعوداً (كان تحته في الشمعة السابقة)"""
    if tv is None:
        return False, None

    try:
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=Interval.in_15_minute, n_bars=RSI_15M_BARS)
        if df is None or df.empty or len(df) < 20:
            return False, None

        df['rsi'] = calculate_rsi(df['close'], 14)
        curr_rsi = df['rsi'].iloc[-1]
        prev_rsi = df['rsi'].iloc[-2]
        if pd.isna(curr_rsi) or pd.isna(prev_rsi):
            return False, None

        if prev_rsi <= RSI_MOMENTUM_LEVEL < curr_rsi:
            return True, {
                "rsi_15m": float(curr_rsi),
                "rsi_prev_15m": float(prev_rsi),
                "rsi_level": RSI_MOMENTUM_LEVEL,
            }

        return False, None
    except Exception as e:
        print(f"خطأ في فحص زخم RSI 15 دقيقة للسهم {ticker}: {e}")
        return False, None


def check_post_close_signal(ticker):
    """
    ما بعد الإغلاق: السعر بعد 15:00 (توقيت السعودية) أعلى من إغلاق شمعة 15:00 بـ 1% أو أكثر،
    مع دخول سيولة (مجموع فوليوم شموع ما بعد 15:00) >= MIN_VOLUME.
    """
    if tv is None:
        return False, None

    try:
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=Interval.in_1_minute, n_bars=POST_1M_BARS)
        if df is None or df.empty:
            return False, None

        # وقت 15:00 بتوقيت السعودية محوّل لتوقيت الجهاز (مثل توقيت فهرس tvdatafeed)
        cutoff = (
            datetime.now(RIYADH)
            .replace(hour=POST_CLOSE_HOUR, minute=0, second=0, microsecond=0)
            .astimezone()
            .replace(tzinfo=None)
        )

        regular = df[df.index < cutoff]
        post = df[df.index >= cutoff]
        if regular.empty or post.empty:
            return False, None
        if regular.index[-1].date() != cutoff.date():
            return False, None

        ref_close = float(regular['close'].iloc[-1])
        post_price = float(post['close'].iloc[-1])
        post_volume = float(post['volume'].sum())
        if ref_close <= 0:
            return False, None

        change_pct = ((post_price - ref_close) / ref_close) * 100

        if change_pct >= POST_MOVE_MIN_PCT and post_volume >= MIN_VOLUME:
            return True, {
                "post_price": post_price,
                "post_change_pct": change_pct,
                "post_volume": int(post_volume),
                "post_ref_close": ref_close,
            }

        return False, None
    except Exception as e:
        print(f"خطأ في فحص ما بعد الإغلاق للسهم {ticker}: {e}")
        return False, None


def _linreg_last(y):
    """قيمة خط الانحدار الخطي عند آخر نقطة في النافذة (مثل linreg في Pine)"""
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)
    return intercept + slope * (len(y) - 1)


def calc_squeeze(df):
    """
    السكويز (TTM): نقطة سوداء = البولنجر داخل كلتنر، وإلا نقطة خضراء.
    المومنتم: linreg لـ (الإغلاق - متوسط منتصف النطاق والمتوسط).
    """
    close, high, low = df['close'], df['high'], df['low']

    basis = close.rolling(SQ_LENGTH).mean()
    dev = SQ_BB_MULT * close.rolling(SQ_LENGTH).std(ddof=0)
    upper_bb, lower_bb = basis + dev, basis - dev

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    range_ma = tr.rolling(SQ_LENGTH).mean()
    upper_kc = basis + SQ_KC_MULT * range_ma
    lower_kc = basis - SQ_KC_MULT * range_ma

    sqz_on = (lower_bb > lower_kc) & (upper_bb < upper_kc)

    mid = ((high.rolling(SQ_LENGTH).max() + low.rolling(SQ_LENGTH).min()) / 2 + basis) / 2
    mom = (close - mid).rolling(SQ_LENGTH).apply(_linreg_last, raw=True)

    return sqz_on, mom


def check_strong_combo_15m(ticker):
    """
    الفلتر القوي المدمج (فاصل 15 دقيقة فقط):
    1) انعكاس: RSI نزل إلى 40 أو أقل خلال آخر 12 شمعة وهو الآن صاعد.
    2) شمعة سيولة سوداء: شمعة خضراء فوليومها >= 1.8x متوسط 20 شمعة (وفوليوم >= MIN_VOLUME) خلال آخر 8 شموع.
    3) دايموند: السعر الحالي أغلق فوق هاي شمعة السيولة.
    4) سكويز: انفجر (أسود -> أخضر) خلال آخر 5 شموع، والمومنتم موجب وصاعد (أزرق فاتح).
    تُستخدم آخر شمعة مكتملة فقط أثناء الجلسة.
    """
    if tv is None:
        return False, None

    try:
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=Interval.in_15_minute, n_bars=STRONG_15M_BARS)
        if df is None or df.empty or len(df) < 50:
            return False, None

        # أثناء الجلسة الشمعة الأخيرة غير مكتملة، نحذفها
        if 10 <= datetime.now(RIYADH).hour < POST_CLOSE_HOUR:
            df = df.iloc[:-1]
        n = len(df)
        if n < 50:
            return False, None

        df['rsi'] = calculate_rsi(df['close'], 14)
        rsi_now = df['rsi'].iloc[-1]
        rsi_prev = df['rsi'].iloc[-2]
        if pd.isna(rsi_now) or pd.isna(rsi_prev):
            return False, None

        # 1) الانعكاس
        rsi_low = df['rsi'].iloc[-STRONG_RSI_LOOKBACK:].min()
        if not (rsi_low <= STRONG_RSI_LOW and rsi_now > rsi_prev):
            return False, None

        # 2) + 3) شمعة السيولة السوداء والدايموند
        highs = df['high'].tolist()
        opens = df['open'].tolist()
        closes = df['close'].tolist()
        volumes = df['volume'].tolist()

        black_high = None
        black_ratio = 0.0
        for i in range(n - STRONG_BLACK_LOOKBACK, n):
            vol_slice = [v for v in volumes[max(0, i - LIQ_LOOKBACK):i] if v is not None and v > 0]
            if not vol_slice:
                continue
            avg_vol = sum(vol_slice) / len(vol_slice)
            curr_vol = volumes[i] or 0.0
            if avg_vol > 0 and curr_vol >= avg_vol * STRONG_BLACK_MULT and curr_vol >= MIN_VOLUME and closes[i] > opens[i]:
                black_high = float(highs[i])
                black_ratio = curr_vol / avg_vol

        if black_high is None:
            return False, None

        price = float(closes[-1])
        if price <= black_high:
            return False, None

        # 4) السكويز والمومنتم
        sqz_on, mom = calc_squeeze(df)
        mom_now = mom.iloc[-1]
        mom_prev = mom.iloc[-2]
        if pd.isna(mom_now) or pd.isna(mom_prev):
            return False, None
        if bool(sqz_on.iloc[-1]):
            return False, None
        if not (mom_now > 0 and mom_now > mom_prev):
            return False, None

        fired_bars_ago = None
        for j in range(n - SQ_FIRE_LOOKBACK, n):
            if bool(sqz_on.iloc[j - 1]) and not bool(sqz_on.iloc[j]):
                fired_bars_ago = n - 1 - j
        if fired_bars_ago is None:
            return False, None

        return True, {
            "rsi_15m": float(rsi_now),
            "sq_rsi_low": float(rsi_low),
            "sq_black_high": black_high,
            "sq_black_ratio": float(black_ratio),
            "sq_mom": float(mom_now),
            "sq_fired_bars": int(fired_bars_ago),
        }
    except Exception as e:
        print(f"خطأ في فحص الفلتر القوي المدمج للسهم {ticker}: {e}")
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
    """تحميل سجل التنبيهات ووقت آخر فحص مع إعادة الضبط التلقائي للأيام الجديدة"""
    today = datetime.now(RIYADH).strftime("%Y-%m-%d")
    try:
        with open(SEEN_FILE) as f:
            data = json.load(f)
        # التحقق هل التاريخ المخزن يطابق تاريخ اليوم الحالي
        if data.get("date") == today:
            counts = data.get("counts", {})
            last_run_timestamp = data.get("last_run_timestamp", 0)
            cards = data.get("cards", {})
            return today, counts, last_run_timestamp, cards
        else:
            print("📅 تاريخ جديد للسوق، جاري إعادة ضبط سجل التنبيهات والوقت لتجنب التعليق...")
            return today, {}, 0, {}
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return today, {}, 0, {}


def save_seen(today, counts, last_run_timestamp, cards=None):
    with open(SEEN_FILE, "w") as f:
        json.dump({
            "date": today,
            "counts": counts,
            "last_run_timestamp": last_run_timestamp,
            "cards": cards or {}
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


def send_get_id(text):
    """إرسال رسالة وإرجاع رقمها (لتعديلها لاحقاً بدل إرسال رسالة جديدة)"""
    if not TOKEN or not CHAT_ID:
        print("تحذير: BOT_TOKEN أو CHAT_ID غير موجود.")
        return None
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
        if r.ok:
            return r.json()["result"]["message_id"]
        print(f"خطأ تيليجرام: {r.status_code} — {r.text[:300]}")
    except Exception as e:
        print(f"خطأ send_get_id: {e}")
    return None


def edit_message(message_id, text):
    """تعديل رسالة موجودة. يرجع True عند النجاح (أو إذا لم يتغير النص)"""
    if not TOKEN or not CHAT_ID:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/editMessageText",
            data={
                "chat_id": CHAT_ID,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if r.ok:
            return True
        if "message is not modified" in r.text:
            return True
        print(f"خطأ تعديل الرسالة: {r.status_code} — {r.text[:300]}")
    except Exception as e:
        print(f"خطأ edit_message: {e}")
    return False


def escape_html(value) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def send_chunked(header, blocks, footer=""):
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


# ---------------------------------------------------------
# شمعة السيولة السوداء + الدايموند + اتجاه 9 شموع / 3 دقائق
# ---------------------------------------------------------
def get_1m_df(ticker):
    """جلب شموع الدقيقة مرة واحدة للسهم (تُستخدم للسيولة والاتجاه)"""
    if tv is None:
        return None
    try:
        df = tv.get_hist(symbol=ticker, exchange='TADAWUL', interval=Interval.in_1_minute, n_bars=LIVE_1M_BARS)
        if df is None or df.empty or len(df) < 10:
            return None
        return df
    except Exception as e:
        print(f"خطأ في جلب شموع الدقيقة للسهم {ticker}: {e}")
        return None


def analyze_liquidity_and_diamond(df):
    """
    شمعة السيولة السوداء: شمعة فوليومها >= 1.8x متوسط آخر 20 شمعة.
    إشارة الدايموند: السعر الحالي اخترق أعلى سعر (High) لآخر شمعة سوداء.
    """
    result = {
        "available": False,
        "has_black_candle": False,
        "black_high": 0.0,
        "diamond_breakout": False,
        "volume_ratio": 1.0,
    }
    if df is None:
        return result

    try:
        highs = df['high'].tolist()
        closes = df['close'].tolist()
        volumes = df['volume'].tolist()

        if len(closes) < 10:
            return result

        result["available"] = True

        lookback = min(LIQ_LOOKBACK, len(closes) - 3)
        black_highs = []
        for i in range(max(5, lookback), len(closes)):
            vol_slice = [v for v in volumes[max(0, i - LIQ_LOOKBACK):i] if v is not None and v > 0]
            if not vol_slice:
                continue
            avg_vol = sum(vol_slice) / len(vol_slice)
            curr_vol = volumes[i] or 0.0

            if avg_vol > 0 and curr_vol >= avg_vol * LIQ_VOLUME_MULT:
                h = highs[i]
                if h is not None:
                    result["has_black_candle"] = True
                    black_highs.append(round(float(h), 2))
                    result["volume_ratio"] = round(curr_vol / avg_vol, 1)

        if black_highs:
            last_blk_high = black_highs[-1]
            result["black_high"] = last_blk_high
            if float(closes[-1]) >= last_blk_high:
                result["diamond_breakout"] = True
    except Exception as e:
        print(f"خطأ في تحليل السيولة والدايموند: {e}")

    return result


def analyze_trend_3m(df):
    """اتجاه آخر 9 شموع على فاصل 3 دقائق (مبنية من شموع الدقيقة)"""
    if df is None:
        return "غير متاح"
    try:
        c3 = df.resample('3min').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        if len(c3) > 1:
            c3 = c3.iloc[:-1]  # حذف الشمعة غير المكتملة
        c3 = c3.iloc[-9:]
        if len(c3) < 3:
            return "غير كافٍ"

        c0 = float(c3['close'].iloc[-3])
        c1 = float(c3['close'].iloc[-2])
        c2 = float(c3['close'].iloc[-1])
        o2 = float(c3['open'].iloc[-1])

        if c0 < c1 < c2:
            return "📈 صاعد قوي" if c2 > o2 else "📈 صاعد"
        if c0 > c1 > c2:
            return "📉 هابط قوي" if c2 < o2 else "📉 هابط"
        return "➡️ عرضي"
    except Exception as e:
        print(f"خطأ في حساب الاتجاه: {e}")
        return "غير متاح"


def build_card(idx, label, header_tag, arabic_name, ticker, curr_count, sector,
               price, change, volume, vwap, rsi, entry_price,
               trend_word, liq, row, lvl, tv_url, time_str):
    """بطاقة LIVE مرتبة في أقسام"""
    sep = "───────────────"
    lines = []

    # --- الرأس ---
    lines.append(f"🔴 <b>LIVE | #{idx} {arabic_name} ({ticker})</b>{header_tag}")
    lines.append(f"🚨 <b>[تنبيه {curr_count}]</b> | 🏷 {escape_html(label)}")
    lines.append(f"🏢 <b>القطاع:</b> {sector}")
    lines.append(sep)

    # --- السعر والحركة ---
    lines.append(f"💵 <b>السعر:</b> {price:.2f} ر.س | <b>التغير:</b> +{change:.1f}%")
    if entry_price and entry_price > 0:
        since = ((price - entry_price) / entry_price) * 100
        lines.append(f"↗️ <b>التغير منذ أول تنبيه:</b> {'+' if since >= 0 else ''}{since:.2f}%")
    lines.append(f"📊 <b>Vol:</b> {int(volume):,}" + (f" | <b>VWAP:</b> {vwap:.2f} ر.س" if vwap > 0 else ""))
    if rsi > 0:
        lines.append(f"📉 <b>RSI:</b> {rsi:.1f}")
    lines.append(f"🧭 <b>الاتجاه (9 شموع / 3د):</b> {trend_word}")
    lines.append(sep)

    # --- السيولة والدايموند ---
    if not liq["available"]:
        lines.append("⬛ <b>شمعة السيولة السوداء:</b> غير متاح")
        lines.append("💎 <b>إشارة دايموند:</b> غير متاح")
    else:
        b_high = f"{liq['black_high']:.2f}" if liq["black_high"] > 0 else "—"
        if liq["has_black_candle"]:
            lines.append(f"⬛ <b>شمعة السيولة السوداء:</b> تم الرصد (فوليوم {liq['volume_ratio']}x | هاي: {b_high})")
        else:
            lines.append("⬛ <b>شمعة السيولة السوداء:</b> قيد المراقبة")
        if liq["diamond_breakout"]:
            lines.append(f"💎 <b>إشارة دايموند:</b> ✨ تم الاختراق فوق {b_high}")
        else:
            lines.append(f"💎 <b>إشارة دايموند:</b> ⏳ بانتظار اختراق {b_high}")
    lines.append(sep)

    # --- تفاصيل خاصة بالفلتر (تظهر فقط إن وجدت) ---
    special = []
    if 'rsi_prev_15m' in row and not pd.isna(row['rsi_prev_15m']):
        special.append(
            f"📉 <b>RSI 15د:</b> {row['rsi_15m']:.1f} (السابقة {row['rsi_prev_15m']:.1f}) | <b>المستوى:</b> {int(row['rsi_level'])}"
        )
    if 'sq_black_high' in row and not pd.isna(row['sq_black_high']):
        special.append(
            f"⬛ <b>سيولة 15د:</b> شمعة {row['sq_black_ratio']:.1f}x | 💎 تم الاختراق فوق {row['sq_black_high']:.2f}"
        )
        special.append(
            f"🟢 <b>السكويز:</b> انفجر قبل {int(row['sq_fired_bars'])} شمعة | <b>المومنتم:</b> {row['sq_mom']:.2f} ⬆️ (أزرق فاتح)"
        )
        special.append(f"📉 <b>أدنى RSI حديث:</b> {row['sq_rsi_low']:.1f}")
    if 'post_change_pct' in row and not pd.isna(row['post_change_pct']):
        special.append(
            f"🌙 <b>ما بعد الإغلاق:</b> +{row['post_change_pct']:.2f}% عن إغلاق 15:00 ({row['post_ref_close']:.2f} ر.س)"
        )
        special.append(f"📊 <b>سيولة ما بعد الإغلاق:</b> {int(row['post_volume']):,} سهم")
    if special:
        lines.extend(special)
        lines.append(sep)

    # --- الأهداف والدعم والوقف ---
    lines.append(f"🎯 <b>الأهداف:</b> {lvl['t1']:.2f} -&gt; {lvl['t2']:.2f} -&gt; {lvl['t3']:.2f} ر.س")
    lines.append(f"🛡️ <b>الدعم:</b> {lvl['support_intraday']:.2f} ر.س | ⛔️ <b>الوقف:</b> {lvl['stop_1']:.2f} ر.س")
    lines.append(sep)

    # --- التذييل ---
    lines.append(f"🕒 <b>آخر تحديث:</b> {time_str} (السعودية)")
    lines.append(f"📈 <b>الشارت:</b> <a href='{tv_url}'>TradingView</a>")
    lines.append("للفرز فقط، تأكد على الشارت قبل أي قرار.")

    return "\n".join(lines)


def main():
    today, counts, last_run_timestamp, cards = load_seen()
    now_timestamp = time.time()

    elapsed = now_timestamp - last_run_timestamp

    # التحقق من الفارق الزمني بشرط ألا يكون وقت التشغيل السابق قادماً من يوم قديم غير مصفر
    if not FORCE_RESEND and last_run_timestamp > 0 and elapsed < CHECK_INTERVAL_SECONDS:
        remaining = int(CHECK_INTERVAL_SECONDS - elapsed)
        print(f"⏳ لم تمضِ 3 دقائق بعد منذ آخر فحص. المتبقي: {remaining} ثانية.")
        return

    print(f"🚀 جاري تنفيذ الفحص الشامل لجميع الأسهم والفلاتر...")

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
    now_riyadh = datetime.now(RIYADH)

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

        if "ما بعد الإغلاق" in label:
            if tv is not None and now_riyadh.hour >= POST_CLOSE_HOUR:
                valid_rows = []
                for _, row in df.iterrows():
                    ticker_name = str(row.get('clean_name', row['name'])).strip()
                    is_valid, post_info = check_post_close_signal(ticker_name)
                    if is_valid:
                        row_dict = row.to_dict()
                        row_dict.update(post_info)
                        row_dict['close'] = post_info['post_price']
                        row_dict['change'] = post_info['post_change_pct']
                        valid_rows.append(row_dict)
                df = pd.DataFrame(valid_rows)
            else:
                df = pd.DataFrame()
        elif "انعكاس RSI" in label:
            if tv is not None:
                valid_rows = []
                for _, row in df.iterrows():
                    ticker_name = str(row.get('clean_name', row['name'])).strip()
                    is_valid, rsi_info = check_rsi_bounce_15m(ticker_name)
                    if is_valid:
                        row_dict = row.to_dict()
                        row_dict.update(rsi_info)
                        valid_rows.append(row_dict)
                df = pd.DataFrame(valid_rows)
            else:
                df = pd.DataFrame()
        elif "زخم RSI" in label:
            if tv is not None:
                valid_rows = []
                for _, row in df.iterrows():
                    ticker_name = str(row.get('clean_name', row['name'])).strip()
                    is_valid, rsi_info = check_rsi_momentum_15m(ticker_name)
                    if is_valid:
                        row_dict = row.to_dict()
                        row_dict.update(rsi_info)
                        valid_rows.append(row_dict)
                df = pd.DataFrame(valid_rows)
            else:
                df = pd.DataFrame()
        elif "قوي" in label:
            if tv is not None:
                valid_rows = []
                for _, row in df.iterrows():
                    ticker_name = str(row.get('clean_name', row['name'])).strip()
                    is_valid, strong_info = check_strong_combo_15m(ticker_name)
                    if is_valid:
                        row_dict = row.to_dict()
                        row_dict.update(strong_info)
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

        header_tag = ""

        for idx, (ticker, row) in enumerate(results[:MAX_SHOWN], 1):
            arabic_name = escape_html(stocks_dict.get(ticker, ticker))
            sector = escape_html(str(row.get('sector', 'N/A')).strip())

            tv_url = f"https://www.tradingview.com/chart/?symbol=TADAWUL:{ticker}"

            price = float(row[price_c]) if row[price_c] else 0.0
            change = float(row[chg_c]) if row[chg_c] else 0.0
            volume = float(row[vol_c]) if row[vol_c] else 0.0
            vwap = float(row.get('VWAP', 0.0) or 0.0)
            rsi = float(row.get('rsi_15m', row.get('RSI', 0.0)) or 0.0)

            high = float(row['high']) if 'high' in row and row['high'] else price * 1.02
            low = float(row['low']) if 'low' in row and row['low'] else price * 0.98
            ema20 = float(row['EMA20']) if 'EMA20' in row and row['EMA20'] else price * 0.99
            ema50 = float(row['EMA50']) if 'EMA50' in row and row['EMA50'] else price * 0.97

            # --- السيولة والدايموند والاتجاه (استدعاء واحد لشموع الدقيقة) ---
            df_1m = get_1m_df(ticker)
            liq = analyze_liquidity_and_diamond(df_1m)
            trend_word = analyze_trend_3m(df_1m)

            # --- التحديث: تنبيه جديد فقط إذا ارتفع السعر عن آخر تنبيه ---
            card_key = f"{label}|{ticker}"
            card_state = cards.get(card_key, {})
            updates_done = card_state.get("updates", 0)
            last_price = card_state.get("last_price", price)
            price_increased = price > last_price

            if card_state and not price_increased and not FORCE_RESEND:
                print(f"ℹ️ {ticker} ({label}) لم يرتفع عن آخر تنبيه — تخطي التحديث")
                continue

            curr_count = counts.get(ticker, 0) + 1
            counts[ticker] = curr_count

            lvl = calculate_levels(price, high, low, ema20, ema50)

            entry_price = card_state.get("entry_price", price)
            time_str = datetime.now(RIYADH).strftime("%H:%M")

            card = build_card(
                idx, label, header_tag, arabic_name, ticker, curr_count, sector,
                price, change, volume, vwap, rsi, entry_price,
                trend_word, liq, row, lvl, tv_url, time_str
            )

            # --- إرسال البطاقة أول مرة، وبعدها تعديل نفس الرسالة ---
            msg_id = card_state.get("msg_id")
            if msg_id and not FORCE_RESEND:
                if not edit_message(msg_id, card):
                    msg_id = send_get_id(card)
            else:
                msg_id = send_get_id(card)

            cards[card_key] = {
                "msg_id": msg_id,
                "entry_price": entry_price,
                "last_price": price,
                "last_black_candle": liq["has_black_candle"],
                "last_diamond": liq["diamond_breakout"],
                "updates": updates_done + 1,
            }

    save_seen(today, counts, now_timestamp, cards)
    if had_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
