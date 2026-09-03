"""
تبدیل زمان بین UTC (که در دیتابیس ذخیره می‌شود) و منطقه زمانی ایران، و نمایش تاریخ
به‌صورت شمسی همراه با نام روز هفته (چون کاربران و ادمین‌های این ربات در ایران
هستند و با تقویم میلادی راحت نیستند، حتی اگر تاریخ را به میلادی وارد کرده باشند).

ایران از سال ۱۴۰۱ (۲۰۲۲ میلادی) دیگر ساعت تابستانی ندارد، پس افست ثابت +۰۳:۳۰
همیشه درست است — نیازی به دیتابیس IANA/tzdata نیست.
"""
from datetime import datetime, timedelta, timezone

import jdatetime

IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

jdatetime.set_locale("fa_IR")


def local_to_utc_naive(dt: datetime) -> datetime:
    """یک datetime ساده (naive) که بر حسب ساعت محلی ایران وارد شده را به یک
    datetime ساده بر حسب UTC تبدیل می‌کند — برای ذخیره در دیتابیس."""
    return dt.replace(tzinfo=IRAN_TZ).astimezone(timezone.utc).replace(tzinfo=None)


def utc_naive_to_local_str(dt_utc) -> str:
    """یک datetime ساده UTC (که در دیتابیس ذخیره شده) را به رشته‌ی تاریخ شمسی +
    نام روز هفته + ساعت محلی ایران تبدیل می‌کند — برای نمایش به کاربر/ادمین.
    مثال خروجی: «یکشنبه ۲۹ شهریور ۱۴۰۵ - ساعت ۱۸:۰۰»."""
    if dt_utc is None:
        return ""
    local = dt_utc.replace(tzinfo=timezone.utc).astimezone(IRAN_TZ)
    jalali = jdatetime.datetime.fromgregorian(datetime=local.replace(tzinfo=None))
    return jalali.strftime("%A %d %B %Y - ساعت %H:%M")
