import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from tradingview_screener import Query, col

# إعدادات التلغرام من متغيرات البيئة
TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

RIYADH = ZoneInfo("Asia/Riyadh")
SEEN_FILE = "seen_saudi.json"

MAX_SHOWN = 10
CHECK_INTERVAL_SECONDS = 300          # 5 دقائق للتنبيهات التفصيلية
CARD_INTERVAL_MINUTES = 10            # البطاقة كل 10 دقائق
SCAN_START_MINUTES = 10 * 60          # 10:00
SCAN_END_MINUTES = 16 * 60            # 16:00

# الحد الأدنى لزيادة التغير حتى يُعاد إرسال السهم
MIN_CHANGE_INCREASE = 0.5

# فلاتر مخففة لتناسب السوق السعودي
MIN_DAILY_CHANGE = 0.5
MIN_VOLUME = 5_000
MIN_AVG_VOLUME_10D = 10_000
MIN_RELATIVE_VOLUME = 0.5
NEWS_CACHE = {}

# عدد الأسهم في بطاقة الأسهم الفعالة
TOP_ACTIVE_COUNT = 10


def get_saudi_stocks_dict():
    """قائمة الأسهم السعودية المحدثة + اختصارات قصيرة"""
    return {
        "4150": "التعمير", "9523": "لدن", "2030": "المصافي", "2222": "أرامكو",
        "2380": "بترورابغ", "2381": "الحفر", "2382": "أديس", "4030": "البحري",
        "1201": "تكوين", "1202": "ميكو", "1210": "بيسيآي", "1211": "معادن",
        "1301": "أسلاك", "1304": "اليمامة", "1320": "أنابيب", "1321": "الشرق",
        "1322": "أماك", "1323": "يوسيآيس", "1324": "الراشد", "1325": "حديد",
        "2001": "كيمانول", "2010": "سابك", "2020": "المغذيات", "2060": "التصنيع",
        "2090": "جيسكو", "2150": "زجاج", "2170": "اللجين", "2180": "فيبكو",
        "2200": "أنابيب", "2210": "نماء", "2220": "معدنية", "2223": "لوبريف",
        "2240": "صناعات", "2250": "المجموعة", "2290": "ينساب", "2300": "الورق",
        "2310": "سبكيم", "2330": "المتقدمة", "2350": "كيان", "2360": "الفخارية",
        "3002": "نجران", "3003": "المدينة", "3004": "الشمالية", "3005": "أمالقرى",
        "3007": "الواحة", "3008": "الكثيري", "3010": "العربية", "3020": "اليمامة",
        "3030": "السعودية", "3040": "القصيم", "3050": "الجنوب", "3060": "ينبع",
        "3080": "الشرقية", "3090": "تبوك", "3091": "الجوف", "3092": "الرياض",
        "4143": "تالكو", "1212": "استرا", "1214": "شاكر", "1302": "يوان",
        "1303": "الكهربائية", "2040": "الخزف", "2110": "الكابلات", "2160": "اميانتيت",
        "2320": "البابطين", "2370": "مسك", "4110": "باتك", "4140": "صادرات",
        "4141": "العمران", "4142": "كابلات", "1831": "مهارة", "1832": "صدر",
        "1833": "الموارد", "1834": "سماسكو", "1835": "تمكين", "4270": "طباعة",
        "6004": "كاتريون", "2190": "سيسكو", "4031": "الأرضية", "4040": "سابتكو",
        "4260": "بدجت", "4261": "ذيب", "4262": "لومي", "4263": "سال",
        "1810": "سيرا", "4090": "طيبة", "4170": "شمس", "4250": "جبلاطمر",
        "4290": "الخليج", "4291": "التعليم", "4292": "عطاء", "6002": "هرفي",
        "6013": "التطويرية", "6015": "أمريكانا", "6017": "جاهز", "4003": "اكسترا",
        "4008": "ساكو", "4050": "ساسكو", "4190": "جرير", "4192": "السيف",
        "4200": "الدريس", "4001": "العثيم", "4161": "بنداوود", "4162": "المنجم",
        "4163": "الدواء", "4164": "النهدي", "2050": "صافولا", "2270": "سدافكو",
        "2280": "المراعي", "2281": "تنمية", "2283": "المطاحن", "2284": "الحديثة",
        "6010": "نادك", "6070": "الجوف", "4002": "المواساة", "4004": "دله",
        "4005": "رعاية", "4007": "الحمادي", "4009": "الألماني", "4013": "الحبيب",
        "4017": "فقيه", "2070": "الدوائية", "4015": "جمجوم", "1010": "الرياض",
        "1020": "الجزيرة", "1030": "الاستثمار", "1050": "بياسإف", "1060": "الأول",
        "1080": "العربي", "1120": "الراجحي", "1140": "البلاد", "1150": "الإنماء",
        "1180": "الأهلي", "1111": "تداول", "7200": "امآيإس", "7202": "سلوشنز",
        "7203": "علم", "7010": "STC", "7020": "موبايلي", "7030": "زين",
        "2082": "أكوا", "2083": "مرافق", "5110": "الكهرباء",
        # أسهم جديدة
        "9542": "كيير", "9595": "دبليوإسإم", "4144": "رعوم", "9612": "سما",
        "9578": "أطلس", "9552": "توب", "7201": "البحر",
        "4310": "معرفة", "6050": "السعودية", "4080": "سيناد", "9572": "ال",
        "4230": "ريد", "9549": "نسيج", "9557": "المصانع", "9560": "البحر",
        "9563": "الجزيرة", "9570": "الراية", "9580": "الخدمات", "9590": "التقنية",
        "9600": "الأولى", "9620": "الواحة", "9630": "النور", "9640": "السلام",
    }


def short_name(name: str) -> str:
    """اختصار الاسم لكلمة واحدة تقريباً"""
    if not name:
        return ""
    remove = ["شركة", "مساهمة", "سعودية", "السعودية", "الـ", "Co.", "Company",
              "International", "Trading", "for", "and", "General"]
    parts = name.replace(".", " ").split()
    cleaned = [p for p in parts if p not in remove and len(p) > 1]
    if cleaned:
        return cleaned[0][:12]
    return name[:12]


def screens():
    common_momentum = [
        col("close") > 0,
        col("change") >= MIN_DAILY_CHANGE,
        col("volume") >= MIN_VOLUME,
        col("average_volume_10d_calc") >= MIN_AVG_VOLUME_10D,
        col("relative_volume_10d_calc") >= MIN_RELATIVE_VOLUME,
    ]
    early_momentum = common_momentum + [col("change") <= 3.0]
    intraday_momentum = common_momentum + [col("change") <= 7.0]
    strong_momentum = common_momentum
    extra = ["close", "change", "volume"]
    return extra, "change", {
        "1️⃣ زخم مبكر (0.5% - 3.0%)": early_momentum,
        "2️⃣ زخم لحظي (0.5% - 7.0%)": intraday_momentum,
        "3️⃣ زخم قوي (0.5% فأعلى)": strong_momentum,
    }


def run_screen(filters, columns, sort_col):
    query = (
        Query()
        .set_markets("ksa")
        .select(*columns)
        .where(*filters)
        .order_by(sort_col, ascending=False)
        .limit(300)
    )
    try:
        _, df = query.get_scanner_data()
    except Exception as e:
        print(f"خطأ في الاستعلام من TradingView: {e}")
        return None

    if df is not None and not df.empty:
        df["clean_name"] = df["name"].astype(str).str.replace("TADAWUL:", "").str.strip()
        return df
    return df


def load_seen():
    today = datetime.now(RIYADH).strftime("%Y-%m-%d")
    try:
        with open(SEEN_FILE) as f:
            data = json.load(f)
        if data.get("date") == today:
            return (
                today,
                data.get("alerted", {}),
                data.get("last_run_timestamp", 0),
                data.get("last_card_timestamp", 0),
                data.get("card_seen", {}),
            )
        else:
            print("📅 تاريخ جديد، جاري إعادة ضبط سجل التنبيهات...")
            return today, {}, 0, 0, {}
    except (FileNotFoundError, json.JSONDecodeError):
        return today, {}, 0, 0, {}


def save_seen(today, alerted, last_run_timestamp, last_card_timestamp, card_seen):
    with open(SEEN_FILE, "w") as f:
        json.dump({
            "date": today,
            "alerted": alerted,
            "last_run_timestamp": last_run_timestamp,
            "last_card_timestamp": last_card_timestamp,
            "card_seen": card_seen,
        }, f, indent=2, ensure_ascii=False)


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
