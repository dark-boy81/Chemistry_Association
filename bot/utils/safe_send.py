"""
جایگزین الگوی رایج:

    try:
        await bot.send_message(...)
    except Exception:
        pass

که خطاهای واقعی را کاملاً پنهان می‌کرد — چه خطای بی‌ضرر («کاربر ربات را بلاک کرده») و
چه خطای واقعی (تایپو در chat_id، قطعی شبکه، Bad Request به‌خاطر پارامتر اشتباه).

safe_send() دقیقاً همان کار try/except pass را می‌کند (خطا را می‌بلعد تا حلقه‌ی ارسال به
چند نفر با شکست یک نفر متوقف نشود)، با این تفاوت که همیشه لاگ می‌کند:
- سطح INFO برای حالت‌های عادی و منتظره (کاربر بلاک کرده / چت پاک شده) — این‌ها نویز نیستند
  که بخواهیم پنهانشان کنیم، ولی هم جزو خطای واقعی به حساب نمی‌آیند.
- سطح WARNING برای هر چیز غیرمنتظره (شبکه، Bad Request، Timeout، ...).

خروجی True/False است تا فراخوان‌کننده در صورت نیاز (مثلاً برای تصمیم‌گیری بعدی) بداند
ارسال موفق بود یا نه؛ اکثر جاها این مقدار برگشتی نادیده گرفته می‌شود، دقیقاً مثل قبل.
"""
import logging

from telegram.error import BadRequest, Forbidden, TelegramError

logger = logging.getLogger(__name__)

# این خطاها یعنی گیرنده دیگر در دسترس نیست (بلاک کرده، حساب حذف شده، چت پاک شده).
# اتفاقی عادی است، نه یک باگ در کد ما؛ پس سطح لاگش پایین‌تر (INFO) است.
_EXPECTED_UNREACHABLE = (Forbidden,)
_EXPECTED_BAD_REQUEST_SNIPPETS = ("chat not found", "user is deactivated", "bot was blocked")


async def safe_send(coro, *, context: str, chat_id=None) -> bool:
    """
    یک فراخوانی از پیش ساخته‌شده‌ی متد ارسال تلگرام (مثل ``bot.send_message(...)``) را
    اجرا می‌کند و خطای تلگرام را می‌بلعد ولی همیشه لاگ می‌کند.

    نمونه:
        await safe_send(
            bot.send_message(chat_id=uid, text="سلام"),
            context="notify_event_cancelled",
            chat_id=uid,
        )
    """
    try:
        await coro
        return True
    except _EXPECTED_UNREACHABLE:
        logger.info("گیرنده در دسترس نیست (%s): chat_id=%s", context, chat_id)
        return False
    except BadRequest as exc:
        message = str(exc).lower()
        if any(snippet in message for snippet in _EXPECTED_BAD_REQUEST_SNIPPETS):
            logger.info("گیرنده در دسترس نیست (%s): chat_id=%s error=%s", context, chat_id, exc)
        else:
            logger.warning("ارسال پیام تلگرام ناموفق (%s): chat_id=%s error=%s", context, chat_id, exc)
        return False
    except TelegramError as exc:
        logger.warning("ارسال پیام تلگرام ناموفق (%s): chat_id=%s error=%s", context, chat_id, exc)
        return False
