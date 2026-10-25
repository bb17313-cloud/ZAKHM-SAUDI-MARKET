import json
import os
import sys
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
CHECK_INTERVAL_SECONDS = 300
SCAN_START_MINUTES = 9 * 60 + 45
SCAN_END_MINUTES = 16 * 60 + 30

# === فلاتر مخففة لتناسب السوق السعودي ===
MIN_DAILY_CHANGE = 0.5
MIN_VOLUME = 5_000
MIN_AVG_VOLUME_10D = 10_000
MIN_RELATIVE_VOLUME = 0.5
NEWS_CACHE = {}

def get_saudi_stocks_dict():
    """قائمة الأسهم السعودية المحدثة"""
    return {
        "4150": "التعمير", "9523": "لدن", "2030": "المصافي", "2222": "أرامكو السعودية", 
        "2380": "بترو رابغ", "2381": "الحفر العربية", "2382": "اديس", "4030": "البحري", 
        "1201": "تكوين", "1202": "ميكو", "1210": "بي سي آي", "1211": "معادن", 
        "1301": "أسلاك", "1304": "اليمامة للحديد", "1320": "أنابيب السعودية", 
        "1321": "أنابيب الشرق", "1322": "أماك", "1323": "يو سي آي سي", "1324": "صالح الراشد",
        "1325": "حديد وطني",  # ← تمت الإضافة
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
    """فلاتر الزخم العامة بعد تخفيفها لتناسب السوق السعودي."""
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


def run_screen(filters, columns, sort_col, tickers_dict=None):
    """يستخدم السوق السعودي كاملاً بدل قائمة محدودة"""
    query = (
        Query()
        .set_markets("saudi")
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
    today = datetime.now(RIYADH).strftime("%Y-%m-%d")
    try:
        with open(SEEN_FILE) as f:
            data = json.load(f)
        if data.get("date") == today:
            counts = data.get("counts", {})
            last_run_timestamp = data.get("last_run_timestamp", 0)
            return today, counts, last_run_timestamp
        else:
            print("📅 تاريخ جديد للسوق، جاري إعادة ضبط سجل التنبيهات والوقت لتجنب التعليق...")
            return today, {}, 0
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return today, {}, 0


def save_seen(today, counts, last_run_timestamp):
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
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def fetch_live_news(ticker, company_name):
    cache_key = (str(ticker), str(company_name))
    if cache_key in NEWS_CACHE:
        return NEWS_CACHE[cache_key]

    query = (
        f'("{ticker}" OR "{company_name}") '
        '(site:saudiexchange.sa OR site:argaam.com OR site:mubasher.info)'
    )
    try:
        response = requests.get(
            "https://news.google.com/rss/search",
            params={"q": query, "hl": "ar", "gl": "SA", "ceid": "SA:ar"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        allowed = ("saudiexchange.sa", "argaam.com", "mubasher.info")
        results = []
        seen = set()
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            date = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = (source_el.text or "").strip() if source_el is not None else ""
            if not title or not link:
                continue
            try:
                final_link = requests.get(
                    link, headers={"User-Agent": "Mozilla/5.0"},
                    allow_redirects=True, timeout=8
                ).url
            except Exception:
                final_link = link
            if not any(domain in final_link.lower() for domain in allowed):
                continue
            key = (title, final_link)
            if key in seen:
                continue
            seen.add(key)
            results.append((title, final_link, date, source))
            if len(results) >= 3:
                break
        NEWS_CACHE[cache_key] = results
        return results
    except Exception as e:
        print(f"تعذر جلب أخبار {ticker}: {e}")
        NEWS_CACHE[cache_key] = []
        return []


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


def calculate_levels(price, high, low):
    pivot = (high + low + price) / 3

    r1 = (2 * pivot) - low if ((2 * pivot) - low) > price else price * 1.025
    r2 = pivot + (high - low) if (pivot + (high - low)) > r1 else r1 * 1.03
    r3 = high + 2 * (pivot - low) if (high + 2 * (pivot - low)) > r2 else r2 * 1.04

    support_intraday = low

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
    now_riyadh = datetime.now(RIYADH)
    minutes_now = now_riyadh.hour * 60 + now_riyadh.minute
    if now_riyadh.weekday() in (4, 5) or not (SCAN_START_MINUTES <= minutes_now <= SCAN_END_MINUTES):
        print(f"⏸️ خارج نافذة الفحص السعودية: {now_riyadh:%Y-%m-%d %H:%M:%S} بتوقيت الرياض")
        return

    today, counts, last_run_timestamp = load_seen()
    now_timestamp = time.time()

    elapsed = now_timestamp - last_run_timestamp

    if last_run_timestamp > 0 and elapsed < CHECK_INTERVAL_SECONDS:
        remaining = int(CHECK_INTERVAL_SECONDS - elapsed)
        print(f"⏳ لم تمضِ 5 دقائق بعد منذ آخر فحص. المتبقي: {remaining} ثانية.")
        return

    print(f"🚀 جاري تنفيذ الفحص الشامل لجميع الأسهم والفلاتر...")

    extra, sort_col, defs = screens()
    stocks_dict = get_saudi_stocks_dict()

    tech_cols = [
        "high", "low", "sector", "average_volume_10d_calc", "relative_volume_10d_calc"
    ]

    columns = list(dict.fromkeys(["name", "close", "volume"] + extra + tech_cols))
    price_c, chg_c, vol_c = "close", "change", "volume"
    had_error = False

    for label, filters in defs.items():
        try:
            df = run_screen(filters, columns, sort_col)
        except Exception as e:
            print(f"[السوق السعودي/{label}] error: {e}")
            had_error = True
            continue

        if df is None or df.empty:
            print(f"[السوق السعودي/{label}] 0 matches")
            continue

        results = []
        for _, row in df.iterrows():
            ticker_name = str(row.get('clean_name', row['name'])).strip()
            results.append((ticker_name, row))

        print(f"[السوق السعودي/{label}] {len(results)} matches")

        header = f"🚨 تحديث الزخم والأسهم | {label}"
        blocks = []

        for idx, (ticker, row) in enumerate(results[:MAX_SHOWN], 1):
            stock_lines = []
            arabic_name = escape_html(stocks_dict.get(ticker, ticker))
            sector = escape_html(str(row.get('sector', 'N/A')).strip())

            tv_url = f"https://www.tradingview.com/chart/?symbol=TADAWUL:{ticker}"

            price = float(row[price_c]) if row[price_c] else 0.0
            change = float(row[chg_c]) if row[chg_c] else 0.0
            volume = float(row[vol_c]) if row[vol_c] else 0.0
            high = float(row['high']) if 'high' in row and row['high'] else price * 1.02
            low = float(row['low']) if 'low' in row and row['low'] else price * 0.98
            lvl = calculate_levels(price, high, low)

            stock_lines.append(f"🔥 {arabic_name} ({ticker})")
            stock_lines.append(f"🏢 القطاع: {sector}")
            stock_lines.append(f"💵 السعر: {price:.2f} ر.س | التغير: +{change:.1f}% | Vol: {int(volume):,}")

            news = fetch_live_news(ticker, stocks_dict.get(ticker, ticker))
            if news:
                stock_lines.append("📰 الأخبار والمحفزات:")
                for title, link, date, source in news:
                    date_text = f" — {date}" if date else ""
                    source_text = f" ({source})" if source else ""
                    stock_lines.append(
                        f"• <a href='{escape_html(link)}'>{escape_html(title)}</a>"
                        f"{escape_html(source_text)}{escape_html(date_text)}"
                    )

            stock_lines.append(f"🎯 الأهداف: {lvl['t1']:.2f} ر.س -&gt; {lvl['t2']:.2f} ر.س -&gt; {lvl['t3']:.2f} ر.س")
            stock_lines.append(f"🛡️ الدعم: {lvl['support_intraday']:.2f} ر.س | ⛔️ الوقف: {lvl['stop_1']:.2f} ر.س")
            stock_lines.append(f"<a href='{tv_url}'>TradingView</a>")
            stock_lines.append("-----------------------------------\n")

            blocks.append("\n".join(stock_lines))

        footer = "\nللفرز فقط، تأكد من البيانات قبل أي قرار."
        send_chunked(header, blocks, footer)

    save_seen(today, counts, now_timestamp)
    if had_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
