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
CARD_INTERVAL_MINUTES = 3             # بطاقة الأسهم الفعالة كل 3 دقائق
SCAN_START_MINUTES = 10 * 60          # 10:00
SCAN_END_MINUTES = 16 * 60            # 16:00

# الحد الأدنى لزيادة التغير حتى يُعاد إرسال السهم
MIN_CHANGE_INCREASE = 0.3

# فلاتر مخففة لتناسب السوق السعودي وضمان عدم خلو النتائج
MIN_DAILY_CHANGE = 0.2
MIN_VOLUME = 2_000
MIN_RELATIVE_VOLUME = 0.2
NEWS_CACHE = {}

# عدد الأسهم في بطاقة الأسهم الفعالة
TOP_ACTIVE_COUNT = 10


def get_saudi_stocks_dict():
    """قائمة الأسهم السعودية المحدثة بالأسماء العربية الدقيقة"""
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
        "2082": "أكوا", "2083": "مرافق", "5110": "الكهرباء", "4210": "الخزف",
        "9542": "كيير", "9595": "دبليوإسإم", "4144": "رعوم", "9612": "سما",
        "9578": "أطلس", "9552": "توب", "7201": "البحر", "4310": "معرفة",
        "6050": "السعودية", "4080": "سيناد", "4230": "ريد", "9549": "نسيج",
        "9557": "المصانع", "9560": "البحر", "9563": "الجزيرة", "9570": "الراية",
        "9580": "الخدمات", "9590": "التقنية", "9600": "الأولى", "9620": "الواحة",
        "9630": "النور", "9640": "السلام", "9605": "نيفط", "9591": "فيو",
        "4327": "المتطورة", "9619": "ملتي", "9608": "أنابيب", "4191": "الأنابيب",
        "9602": "يقين", "4300": "الدار", "4322": "سمنت الشرقية",
        "4194": "تداول ريت", "6002": "هرفي"
    }


def short_name(name: str) -> str:
    if not name:
        return ""
    remove = ["شركة", "مساهمة", "سعودية", "السعودية", "الـ", "Co.", "Company",
              "International", "Trading", "for", "and", "General"]
    parts = name.replace(".", " ").split()
    cleaned = [p for p in parts if p not in remove and len(p) > 1]
    if cleaned:
        return cleaned[0][:12]
    return name[:12]


ARABIC_NAME_CACHE = {}


def resolve_arabic_name(ticker, stocks_dict, tv_desc=""):
    if ticker in stocks_dict:
        return stocks_dict[ticker]
    if ticker in ARABIC_NAME_CACHE:
        return ARABIC_NAME_CACHE[ticker]

    def is_arabic(s):
        return any("\u0600" <= c <= "\u06FF" for c in s)

    name = ""
    if tv_desc and is_arabic(tv_desc):
        name = short_name(tv_desc)

    if not name:
        try:
            r = requests.post(
                "https://scanner.tradingview.com/ksa/scan",
                json={
                    "symbols": {"tickers": [f"TADAWUL:{ticker}"]},
                    "columns": ["description"],
                    "options": {"lang": "ar"},
                },
                timeout=10,
            )
            data = r.json().get("data", [])
            if data:
                desc = str(data[0]["d"][0] or "").strip()
                if is_arabic(desc):
                    name = short_name(desc)
        except Exception:
            pass

    if name:
        ARABIC_NAME_CACHE[ticker] = name
        return name
    return f"سهم {ticker}"


def screens():
    common_momentum = [
        col("close") > 0,
        col("change") >= MIN_DAILY_CHANGE,
        col("volume") >= MIN_VOLUME,
    ]
    early_momentum = common_momentum + [col("change") <= 3.0]
    
    intraday_momentum = [
        col("close") > 0,
        col("change") >= 0.01,
        col("change") <= 8.0,
        col("volume") >= MIN_VOLUME,
    ]
    
    strong_momentum = common_momentum
    extra = ["close", "change", "volume"]
    return extra, "change", {
        "1️⃣ زخم مبكر (0.2% - 3.0%)": early_momentum,
        "2️⃣ زخم لحظي (0.01% - 8.0%)": intraday_momentum,
        "3️⃣ زخم قوي (0.2% فأعلى)": strong_momentum,
    }


def run_screen(filters, columns, sort_col):
    try:
        query = (
            Query()
            .set_markets("ksa")
            .select(*columns)
            .where(*filters)
            .order_by(sort_col, ascending=False)
            .limit(300)
        )
        _, df = query.get_scanner_data()
        if df is not None and not df.empty:
            df["clean_name"] = df["name"].astype(str).str.replace("TADAWUL:", "").str.strip()
            return df
    except Exception as e:
        print(f"⚠️ خطأ في الاستعلام من TradingView: {e}")
    return None


def load_seen():
    today = datetime.now(RIYADH).strftime("%Y-%m-%d")
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
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
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "date": today,
                "alerted": alerted,
                "last_run_timestamp": last_run_timestamp,
                "last_card_timestamp": last_card_timestamp,
                "card_seen": card_seen,
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ خطأ أثناء حفظ الملف المحلي: {e}")


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
    from email.utils import parsedate_to_datetime

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
            timeout=10,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        allowed = ("saudiexchange.sa", "argaam.com", "mubasher.info")
        now_utc = datetime.now(ZoneInfo("UTC"))
        results = []
        seen = set()
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = (source_el.text or "").strip() if source_el is not None else ""
            source_url = source_el.get("url", "") if source_el is not None else ""
            if not title or not link:
                continue

            # 1) المصادر المسموحة فقط
            if source_url and not any(d in source_url for d in allowed):
                continue

            # 2) إزالة اسم المصدر المكرر من آخر العنوان
            if source and title.endswith(f" - {source}"):
                title = title[: -len(f" - {source}")].strip()

            # 3) الخبر لازم يذكر رمز السهم أو اسمه في العنوان
            names = {str(ticker), str(company_name)}
            if not any(n and n in title for n in names):
                continue

            # 4) آخر 48 ساعة فقط + تنسيق التاريخ بتوقيت الرياض
            date_text = ""
            dt = None
            try:
                dt = parsedate_to_datetime(pub)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                if (now_utc - dt).total_seconds() > 48 * 3600:
                    continue
                date_text = dt.astimezone(RIYADH).strftime("%d/%m %H:%M")
            except Exception:
                pass

            key = (title, link)
            if key in seen:
                continue
            seen.add(key)
            results.append((dt, (title, link, date_text, source)))

        results.sort(key=lambda x: x[0] or now_utc, reverse=True)
        results = [r[1] for r in results[:2]]
        NEWS_CACHE[cache_key] = results
        return results
    except Exception:
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
    stop_1 = support_intraday * 0.985

    return {
        "support_intraday": support_intraday,
        "t1": r1,
        "t2": r2,
        "t3": r3,
        "stop_1": stop_1,
    }


def should_alert(ticker, current_change, alerted):
    if ticker not in alerted:
        return True
    last_change = alerted[ticker].get("change", 0)
    return current_change >= last_change + MIN_CHANGE_INCREASE


def fetch_top_active_stocks(stocks_dict):
    filters = [
        col("close") > 0,
        col("change") >= 0.05,
        col("volume") >= MIN_VOLUME,
    ]
    columns = ["name", "close", "change", "volume", "description"]
    try:
        query = (
            Query()
            .set_markets("ksa")
            .select(*columns)
            .where(*filters)
            .order_by("change", ascending=False)
            .limit(50)
        )
        _, df = query.get_scanner_data()
        if df is None or df.empty:
            return []

        df["clean_name"] = df["name"].astype(str).str.replace("TADAWUL:", "").str.strip()
        results = []
        for _, row in df.iterrows():
            ticker = str(row.get("clean_name", "")).strip()
            if not ticker:
                continue
            price = float(row["close"]) if row["close"] else 0.0
            change = float(row["change"]) if row["change"] else 0.0
            volume = float(row["volume"]) if row["volume"] else 0.0

            name = resolve_arabic_name(ticker, stocks_dict, str(row.get("description", "") or "").strip())

            results.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change": change,
                "volume": volume,
            })
            if len(results) >= TOP_ACTIVE_COUNT:
                break
        return results
    except Exception as e:
        print(f"⚠️ خطأ في جلب الأسهم الفعالة: {e}")
        return []


def build_active_card(stocks, now_riyadh):
    time_str = now_riyadh.strftime("%I:%M %p").lstrip("0")
    header = (
        f"⏱ <b>الأسهم الفعالة · لايف · آخر 3 دقائق</b>\n"
        f"<code>{time_str} بتوقيت السعودية</code>\n"
    )

    lines = [header]
    for i, s in enumerate(stocks, 1):
        ticker = s["ticker"]
        change = s["change"]
        price = s["price"]
        name = escape_html(s["name"])
        tv_url = f"https://www.tradingview.com/chart/?symbol=TADAWUL:{ticker}"

        line = (
            f"{i}. {name} "
            f"<a href=\"{tv_url}\">{ticker}</a> "
            f"<b>+{change:.2f}%</b> · <code>{price:.2f}</code>"
        )
        lines.append(line)

    return "\n".join(lines)


def run_once():
    now_riyadh = datetime.now(RIYADH)
    minutes_now = now_riyadh.hour * 60 + now_riyadh.minute

    if now_riyadh.weekday() in (4, 5) or not (SCAN_START_MINUTES <= minutes_now <= SCAN_END_MINUTES):
        print(f"⏸️ خارج نافذة الفحص: {now_riyadh:%Y-%m-%d %H:%M:%S} بتوقيت الرياض")
        return

    today, alerted, last_run_timestamp, last_card_timestamp, card_seen = load_seen()
    now_timestamp = time.time()
    stocks_dict = get_saudi_stocks_dict()

    # —— 1) بطاقة الأسهم الفعالة كل 3 دقائق ——
    current_slot = minutes_now // CARD_INTERVAL_MINUTES
    last_card_slot = -1
    if last_card_timestamp > 0:
        last_card_dt = datetime.fromtimestamp(last_card_timestamp, RIYADH)
        last_card_minutes = last_card_dt.hour * 60 + last_card_dt.minute
        last_card_slot = last_card_minutes // CARD_INTERVAL_MINUTES

    should_send_card = (last_card_timestamp == 0) or (current_slot != last_card_slot)

    if should_send_card:
        stocks = fetch_top_active_stocks(stocks_dict)
        if stocks:
            text = build_active_card(stocks, now_riyadh)
            send(text)
            card_seen = {s["ticker"]: s["change"] for s in stocks}
            last_card_timestamp = now_timestamp
            print(f"📋 أُرسلت بطاقة الأسهم الفعالة ({len(stocks)} أسهم)")
        else:
            print("⚠️ لم يتم العثور على أسهم نشطة لإرسال البطاقة حالياً")

    # —— 2) التنبيهات التفصيلية كل 5 دقائق ——
    elapsed = now_timestamp - last_run_timestamp if last_run_timestamp > 0 else CHECK_INTERVAL_SECONDS + 1
    if last_run_timestamp > 0 and elapsed < CHECK_INTERVAL_SECONDS:
        remaining = int(CHECK_INTERVAL_SECONDS - elapsed)
        print(f"⏳ لم تمضِ 5 دقائق بعد لتنفيذ الفحص التفصيلي. المتبقي: {remaining} ثانية.")
        save_seen(today, alerted, last_run_timestamp, last_card_timestamp, card_seen)
        return

    print(f"🚀 جاري تنفيذ الفحص التفصيلي... ({now_riyadh:%H:%M:%S})")

    extra, sort_col, defs = screens()
    tech_cols = ["high", "low", "sector", "description"]
    columns = list(dict.fromkeys(["name", "close", "volume"] + extra + tech_cols))
    price_c, chg_c, vol_c = "close", "change", "volume"

    already_sent_this_run = set()
    new_alerts_count = 0

    for label, filters in defs.items():
        df = run_screen(filters, columns, sort_col)
        if df is None or df.empty:
            print(f"[السوق السعودي/{label}] 0 matches أو خطأ في الاستعلام")
            continue

        results = []
        for _, row in df.iterrows():
            ticker_name = str(row.get("clean_name", row["name"])).strip()
            if ticker_name in already_sent_this_run:
                continue

            current_change = float(row[chg_c]) if row[chg_c] else 0.0
            if not should_alert(ticker_name, current_change, alerted):
                continue

            results.append((ticker_name, row, current_change))
            already_sent_this_run.add(ticker_name)

        print(f"[السوق السعودي/{label}] {len(results)} matches بعد الفلترة")

        if not results:
            continue

        header = f"🚨 تحديث الزخم والأسهم | {label}"
        blocks = []

        for ticker, row, current_change in results[:MAX_SHOWN]:
            stock_lines = []

            tv_desc = str(row.get("description", "") or "").strip()
            raw_arabic_name = resolve_arabic_name(ticker, stocks_dict, tv_desc)
            arabic_name = escape_html(raw_arabic_name)

            sector = escape_html(str(row.get("sector", "N/A")).strip())
            tv_url = f"https://www.tradingview.com/chart/?symbol=TADAWUL:{ticker}"

            price = float(row[price_c]) if row[price_c] else 0.0
            volume = float(row[vol_c]) if row[vol_c] else 0.0
            high = float(row["high"]) if "high" in row and row["high"] else price * 1.02
            low = float(row["low"]) if "low" in row and row["low"] else price * 0.98
            lvl = calculate_levels(price, high, low)

            stock_lines.append(f"🔥 {arabic_name} ({ticker})")
            stock_lines.append(f"🏢 القطاع: {sector}")
            stock_lines.append(f"💵 السعر: {price:.2f} ر.س | التغير: +{current_change:.1f}% | Vol: {int(volume):,}")

            news = fetch_live_news(ticker, raw_arabic_name)
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

            alerted[ticker] = {
                "change": current_change,
                "price": price,
                "time": now_riyadh.strftime("%H:%M")
            }
            new_alerts_count += 1

        footer = "\nللفرز فقط، تأكد من البيانات قبل أي قرار."
        send_chunked(header, blocks, footer)

    # تحديث وقت تشغيل الفحص التفصيلي فقط إذا تم إنجازه بنجاح
    save_seen(today, alerted, now_timestamp, last_card_timestamp, card_seen)
    print(f"✅ انتهى الفحص | تنبيهات جديدة أُرسلت: {new_alerts_count}")


if __name__ == "__main__":
    run_once()
