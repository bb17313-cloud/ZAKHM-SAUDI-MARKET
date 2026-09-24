"""Saudi Stock Market (TADAWUL) Screener Bot.

Runs the buy / reversal screens for the Saudi market session (10:00 - 15:15 + final check at 15:35)
and sends NEW hits with dynamically calculated support/resistance and targets to Telegram.
Needs env vars BOT_TOKEN and CHAT_ID.
"""
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from tradingview_screener import Query, col

TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

RIYADH = ZoneInfo("Asia/Riyadh")
SEEN_FILE = "seen_saudi.json"

# شروط الحجم والسيولة للسوق السعودي (بالريال السعودي)
MIN_TURNOVER = 1_000_000       # السعر × متوسط الحجم 10 أيام (بالريال)
MIN_VOL_REGULAR = 100_000      # الحد الأدنى للحجم في الجلسة

MAX_SHOWN = 10                  # الحد الأقصى للأسهم لكل رسالة


def is_market_open():
    """التحقق من أوقات تداول السوق السعودي (الأحد إلى الخميس من 10:00 إلى 15:35)."""
    now = datetime.now(RIYADH)
    
    # عطلة نهاية الأسبوع في السعودية (الجمعة 4 والسبت 5)
    if now.weekday() in (4, 5):
        return False

    minutes = now.hour * 60 + now.minute
    
    # من الساعة 10:00 صباحاً (600 دقيقة) حتى 15:35 مساءً (935 دقيقة)
    if 10 * 60 <= minutes <= 15 * 60 + 35:
        return True
        
    return False


def screens():
    """شروط التصفية للسوق السعودي (شراء وانعكاس)."""
    trend_up = [col("EMA21") > col("EMA50")]
    oversold = [col("close") < col("EMA21"), col("RSI") < 40]

    buy = [
        col("close") > 1,
        col("change") > 0,
        col("volume") >= MIN_VOL_REGULAR,
        col("relative_volume_10d_calc") > 1,
        col("Mom") > 0,
    ] + trend_up

    rev = [
        col("close") > 1,
        col("change") > 1,
        col("volume") >= MIN_VOL_REGULAR,
        col("relative_volume_10d_calc") > 1.5,
    ] + oversold

    extra = ["close", "change", "volume"]
    return extra, "volume", {"شراء": buy, "انعكاس": rev}


def run_screen(filters, columns, sort_col):
    """جلب بيانات الأسهم السعودية من TradingView بدون أخطاء URL."""
    query = (
        Query()
        .select(*columns)
        .where(
            col("type") == "stock",
            col("exchange") == "TADAWUL",
            *filters
        )
        .order_by(sort_col, ascending=False)
        .limit(150)
    )
    _, df = query.get_scanner_data()
    if df.empty:
        return df
    return df[df["close"] * df["average_volume_10d_calc"] > MIN_TURNOVER]


def load_seen():
    """تحميل سجل اليوم وتراكم العدادات."""
    today = datetime.now(RIYADH).strftime("%Y-%m-%d")
    try:
        with open(SEEN_FILE) as f:
            data = json.load(f)
        if data.get("date") == today:
            seen_keys = set(data.get("keys", []))
            counts = data.get("counts", {})
            return today, seen_keys, counts
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return today, set(), {}


def save_seen(today, keys, counts):
    """حفظ المفاتيح والعدادات."""
    with open(SEEN_FILE, "w") as f:
        json.dump({
            "date": today,
            "keys": sorted(keys),
            "counts": counts
        }, f, indent=2)


def send(text):
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


def calculate_levels(price, high, low, ema21, ema50):
    """حساب مستويات الدعم والمقاومة والأهداف والوقف بناءً على منطق Auto-Flip و EMA."""
    pivot = (high + low + price) / 3
    
    r1 = (2 * pivot) - low if ((2 * pivot) - low) > price else price * 1.025
    r2 = pivot + (high - low) if (pivot + (high - low)) > r1 else r1 * 1.03
    r3 = high + 2 * (pivot - low) if (high + 2 * (pivot - low)) > r2 else r2 * 1.04

    support_intraday = min(low, ema21 if 0 < ema21 < price else low)
    support_ilz = min(ema50 if 0 < ema50 < price else support_intraday * 0.98, pivot)

    t1, t2, t3, t4 = r1, r2, r3, r3 * 1.03
    t_max = t4 * 1.05

    stop_1 = support_intraday * 0.985
    stop_2 = support_ilz * 0.975

    return {
        "support_intraday": support_intraday,
        "support_ilz": support_ilz,
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "t_max": t_max,
        "stop_1": stop_1,
        "stop_2": stop_2,
    }


def main():
    if not is_market_open():
        print("السوق السعودي مغلق حالياً، خارج أوقات التداول.")
        return

    today, seen, counts = load_seen()
    extra, sort_col, defs = screens()
    
    tech_cols = ["high", "low", "EMA21", "EMA50", "sector", "VWAP"]
    columns = list(dict.fromkeys(["name", "close", "volume", "average_volume_10d_calc"] + extra + tech_cols))
    price_c, chg_c, vol_c = "close", "change", "volume"
    had_error = False

    for label, filters in defs.items():
        try:
            df = run_screen(filters, columns, sort_col)
        except Exception as e:  # noqa: BLE001
            print(f"[السوق السعودي/{label}] error: {e}")
            had_error = True
            continue

        fresh = []
        for _, row in df.iterrows():
            key = f"saudi:{label}:{row['name']}"
            if key not in seen:
                seen.add(key)
                fresh.append(row)

        print(f"[السوق السعودي/{label}] {len(df)} matches, {len(fresh)} new")
        if not fresh:
            continue

        lines = [f"<b>🇸🇦 السوق السعودي (تداول) | {label}</b>\n"]
        for row in fresh[:MAX_SHOWN]:
            ticker = str(row['name']).strip().upper()
            sector = str(row.get('sector', 'N/A')).strip()
            
            # رابط الشارت المباشر للأسهم السعودية على TradingView
            tv_url = f"https://www.tradingview.com/chart/?symbol=TADAWUL:{ticker}"
            
            price = float(row[price_c]) if row[price_c] else 0.0
            change = float(row[chg_c]) if row[chg_c] else 0.0
            volume = float(row[vol_c]) if row[vol_c] else 0.0
            vwap = float(row.get('VWAP', 0.0) or 0.0)
            
            high = float(row['high']) if 'high' in row and row['high'] else price * 1.02
            low = float(row['low']) if 'low' in row and row['low'] else price * 0.98
            ema21 = float(row['EMA21']) if 'EMA21' in row and row['EMA21'] else price * 0.99
            ema50 = float(row['EMA50']) if 'EMA50' in row and row['EMA50'] else price * 0.97

            curr_count = counts.get(ticker, 0)
            if curr_count == 0:
                counts[ticker] = 0
                header = f"🔥 <b>دخول جديد إلى {ticker}</b>"
                repeat_str = ""
            else:
                if change >= 1.5:
                    curr_count += 1
                    counts[ticker] = curr_count
                
                repeat_str = f" [<b>تنبيه {curr_count}</b>]" if curr_count > 0 else ""

                if change >= 5.0:
                    header = f"🔥 <b>تسارع زخم مفاجئ – {ticker}</b> (📈 +{change:.1f}%)"
                else:
                    header = f"🔥 <b>تحديث حركة {ticker}</b>"

            lvl = calculate_levels(price, high, low, ema21, ema50)

            lines.append(f"{header}")
            lines.append(f"القائمة 🚨{repeat_str}")
            lines.append(f"🏛️ <b>القطاع:</b> {sector}")
            lines.append(f"💵 <b>السعر:</b> {price:.2f} ر.س | <b>التغير:</b> +{change:.1f}% | Vol: {int(volume):,}")
            lines.append(f"📈 <b>الشارت:</b> <a href='{tv_url}'>TradingView</a>")
            lines.append(f"🎯 <b>الأهداف:</b> {lvl['t1']:.2f} ر.س -&gt; {lvl['t2']:.2f} ر.س -&gt; {lvl['t3']:.2f} ر.س")
            lines.append(f"(أقصى هدف: {lvl['t_max']:.2f} ر.س)")
            lines.append(f"🛡️ <b>الدعم:</b> {lvl['support_intraday']:.2f} ر.س | ⛔️ <b>الوقف:</b> {lvl['stop_1']:.2f} ر.س")
            if vwap > 0:
                lines.append(f"📊 <b>VWAP:</b> {vwap:.2f} ر.س")
            lines.append("-----------------------------------\n")

        if len(fresh) > MAX_SHOWN:
            lines.append(f"+{len(fresh) - MAX_SHOWN} أخرى\n")
        lines.append("للفرز فقط، تأكد على الشارت قبل أي قرار.")
        
        send("\n".join(lines))

    save_seen(today, seen, counts)
    if had_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
