"""
تبدیل زمان بین UTC (که در دیتابیس ذخیره می‌شود) و منطقه زمانی ایران (که ادمین وارد
می‌کند و کاربر می‌بیند).

ایران از سال ۱۴۰۱ (۲۰۲۲ میلادی) دیگر ساعت تابستانی ندارد، پس افست ثابت +۰۳:۳۰
همیشه درست است — نیازی به دیتابیس IANA/tzdata نیست.
"""
from datetime import datetime, timedelta, timezone

IRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def local_to_utc_naive(dt: datetime) -> datetime:
    """یک datetime ساده (naive) که بر حسب ساعت محلی ایران وارد شده را به یک
    datetime ساده بر حسب UTC تبدیل می‌کند — برای ذخیره در دیتابیس."""
    return dt.replace(tzinfo=IRAN_TZ).astimezone(timezone.utc).replace(tzinfo=None)


def utc_naive_to_local_str(dt_utc, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """یک datetime ساده UTC (که در دیتابیس ذخیره شده) را به رشته‌ی ساعت محلی ایران
    تبدیل می‌کند — برای نمایش به کاربر/ادمین."""
    if dt_utc is None:
        return ""
    local = dt_utc.replace(tzinfo=timezone.utc).astimezone(IRAN_TZ)
    return local.strftime(fmt)
