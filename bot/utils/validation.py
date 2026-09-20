"""
سقف طول و محدوده‌ی مجاز ورودی‌ها.

چرا لازم است؟
- تلگرام خودش سقف دارد (پیام ۴۰۹۶ کاراکتر، caption عکس/فایل ۱۰۲۴ کاراکتر)؛ اگر ورودی
  بلندتر از آن وارد جایی مثل caption فیش یا پیام ارسالی به ادمین‌ها شود، ارسال با خطا
  مواجه می‌شود (و در چند جا خطا بی‌صدا نادیده گرفته می‌شود).
- ستون‌های دیتابیس (مثل String(300) یا Integer) هم سقف دارند؛ بهتر است قبل از commit
  با پیام مناسب به کاربر برگردانده شود، نه با خطای دیتابیس.

همه‌ی مقادیر اینجا تعریف شده‌اند تا تغییرشان در آینده فقط یک جا لازم باشد.
"""
from typing import Optional

# --- ورودی‌های کاربر ---
MAX_TEXT_FIELD_LEN = 100  # فیلدهای متنی ثبت‌نام (نام، نام خانوادگی، رشته، کد ملی، ...)
MAX_NUMERIC_FIELD_LEN = 20  # فیلدهای عددی/تلفن ثبت‌نام
MAX_CONTACT_MESSAGE_LEN = 3000  # پیام «ارتباط با ادمین» (به‌علاوه‌ی پیشوند باید زیر ۴۰۹۶ بماند)

# --- ورودی‌های ادمین: رویداد ---
MAX_EVENT_TITLE_LEN = 200  # ستون دیتابیس String(300)
MAX_EVENT_DESCRIPTION_LEN = 2000
MAX_EVENT_VENUE_LEN = 200  # ستون دیتابیس String(300)
MAX_CARD_NUMBER_LEN = 64  # ستون دیتابیس String(64)
MAX_EVENT_CAPACITY = 5000  # ستون دیتابیس Integer
MAX_EVENT_PRICE = 999_999_999  # تومان؛ ستون دیتابیس Numeric(12, 0)

# --- ورودی‌های ادمین: سایر بخش‌ها ---
MAX_ADMIN_MESSAGE_LEN = 3000  # پیام همگانی / پیام لغو رویداد / پیام به شرکت‌کنندگان
MAX_FAQ_QUESTION_LEN = 300
MAX_FAQ_ANSWER_LEN = 3000
MAX_JOURNAL_TITLE_LEN = 200  # ستون دیتابیس String(300)؛ در caption فایل PDF هم استفاده می‌شود
MAX_JOURNAL_ABSTRACT_LEN = 3000
MAX_JOURNAL_NUMBER = 9999
MAX_TELEGRAM_ID_DIGITS = 15  # آیدی عددی تلگرام (ستون BigInteger)


def length_error(text: str, max_len: int, label: str) -> Optional[str]:
    """اگر متن از سقف بلندتر باشد، پیام خطای فارسی برمی‌گرداند؛ وگرنه None."""
    if len(text) > max_len:
        return (
            f"⚠️ {label} خیلی طولانی است ({len(text)} کاراکتر). "
            f"حداکثر {max_len} کاراکتر مجاز است؛ لطفاً کوتاه‌تر بفرستید."
        )
    return None


def parse_int_in_range(text: str, min_value: int, max_value: int) -> Optional[int]:
    """
    متن را به عدد صحیح تبدیل می‌کند و فقط اگر بین min_value و max_value باشد برمی‌گرداند؛
    در غیر این صورت None. ارقام فارسی/عربی هم پذیرفته می‌شوند (int() پایتون آن‌ها را می‌فهمد).
    """
    # isdecimal (نه isdigit) چون isdigit کاراکترهایی مثل «²» را هم قبول می‌کند که int() رد می‌کند
    if not text or not text.isdecimal():
        return None
    value = int(text)
    if value < min_value or value > max_value:
        return None
    return value


def validate_event_value(field: str, text: str) -> Optional[str]:
    """
    اعتبارسنجی مقدار یک فیلد رویداد (هم برای ساخت رویداد و هم برای ویرایش).
    field یکی از: title, desc, capacity, price, card, venue
    اگر مشکل داشت پیام خطای فارسی برمی‌گرداند؛ وگرنه None.
    """
    if field == "title":
        if not text:
            return "عنوان نمی‌تواند خالی باشد."
        return length_error(text, MAX_EVENT_TITLE_LEN, "عنوان")
    if field == "desc":
        return length_error(text, MAX_EVENT_DESCRIPTION_LEN, "توضیحات")
    if field == "capacity":
        if parse_int_in_range(text, 1, MAX_EVENT_CAPACITY) is None:
            return f"لطفاً یک عدد صحیح بین ۱ تا {MAX_EVENT_CAPACITY} بفرستید."
        return None
    if field == "price":
        if text == "-":
            return None
        if parse_int_in_range(text, 0, MAX_EVENT_PRICE) is None:
            return (
                f"لطفاً فقط عدد (حداکثر {MAX_EVENT_PRICE:,} تومان) بفرستید "
                "یا برای رایگان بودن - بفرستید."
            )
        return None
    if field == "card":
        if text == "-":
            return None
        return length_error(text, MAX_CARD_NUMBER_LEN, "شماره کارت")
    if field == "venue":
        return length_error(text, MAX_EVENT_VENUE_LEN, "مکان برگزاری")
    return None
