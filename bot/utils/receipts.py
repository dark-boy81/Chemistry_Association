"""
ابزارهای مربوط به فیش واریزی:

1. extract_receipt — فایل ارسالی کاربر را بررسی می‌کند: فقط عکس، یا فایل JPEG/PNG/PDF با
   حجم مجاز، و «نوع» فایل (photo یا document) را هم برمی‌گرداند.
2. send_receipt_message — فیش را برای ادمین با متد درست تلگرام (send_photo یا
   send_document) می‌فرستد.

چرا نوع فایل مهم است؟
تلگرام برای عکس و فایل، file_id متفاوتی می‌دهد و هرکدام را فقط با متد مخصوص خودش
می‌شود فرستاد. قبلاً فقط file_id ذخیره می‌شد و همیشه با send_photo نمایش داده می‌شد؛
پس فیش PDF یا «عکس ارسال‌شده به‌صورت فایل» برای ادمین باز نمی‌شد و ثبت‌نام در وضعیت
«در انتظار بررسی» گیر می‌کرد. حالا نوع فایل کنار file_id ذخیره می‌شود.
"""
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from telegram.error import BadRequest

logger = logging.getLogger(__name__)

RECEIPT_TYPE_PHOTO = "photo"
RECEIPT_TYPE_DOCUMENT = "document"

ALLOWED_DOCUMENT_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}
ALLOWED_DOCUMENT_EXTENSIONS = (".jpg", ".jpeg", ".png", ".pdf")
# بعضی کلاینت‌ها نوع فایل را دقیق گزارش نمی‌کنند؛ فقط در این حالت پسوند نام فایل ملاک است
_GENERIC_MIME_TYPES = ("", "application/octet-stream")

MAX_RECEIPT_BYTES = 10 * 1024 * 1024  # ۱۰ مگابایت

# محدودیت caption در تلگرام ۱۰۲۴ کاراکتر است. بعد از تایید/رد، ربات عبارت «نتیجه: ...»
# را به انتهای caption اضافه می‌کند؛ پس برای آن جا نگه می‌داریم.
CAPTION_SAFE_LIMIT = 950
_MESSAGE_LIMIT = 4000  # محدودیت پیام متنی ۴۰۹۶ است؛ کمی جا می‌گذاریم

INVALID_FILE_TEXT = (
    "⚠️ این نوع فایل قابل قبول نیست.\n"
    "لطفاً فیش را به‌صورت «عکس» یا فایل JPG / PNG / PDF ارسال کنید."
)
TOO_LARGE_TEXT = "⚠️ حجم فایل بیشتر از ۱۰ مگابایت است. لطفاً فایل کوچک‌تری ارسال کنید."


@dataclass(frozen=True)
class ReceiptFile:
    file_id: str
    file_type: str  # RECEIPT_TYPE_PHOTO یا RECEIPT_TYPE_DOCUMENT


def extract_receipt(message) -> Tuple[Optional[ReceiptFile], Optional[str]]:
    """
    خروجی: (receipt, error_text)
    - (ReceiptFile, None)  → فایل معتبر است
    - (None, "متن خطا")    → فایل ارسال شده ولی نامعتبر است؛ متن خطا را به کاربر نشان بدهید
    - (None, None)         → پیام اصلاً فایل/عکس نداشت
    """
    if message.photo:
        photo = message.photo[-1]
        if photo.file_size and photo.file_size > MAX_RECEIPT_BYTES:
            return None, TOO_LARGE_TEXT
        return ReceiptFile(photo.file_id, RECEIPT_TYPE_PHOTO), None

    document = message.document
    if document is not None:
        mime = (document.mime_type or "").lower()
        name = (document.file_name or "").lower()
        mime_ok = mime in ALLOWED_DOCUMENT_MIME_TYPES
        ext_ok = mime in _GENERIC_MIME_TYPES and name.endswith(ALLOWED_DOCUMENT_EXTENSIONS)
        if not (mime_ok or ext_ok):
            return None, INVALID_FILE_TEXT
        if document.file_size and document.file_size > MAX_RECEIPT_BYTES:
            return None, TOO_LARGE_TEXT
        return ReceiptFile(document.file_id, RECEIPT_TYPE_DOCUMENT), None

    return None, None


async def _send_media(bot, chat_id, file_id, file_type, caption, reply_markup):
    if file_type == RECEIPT_TYPE_DOCUMENT:
        return await bot.send_document(
            chat_id=chat_id, document=file_id, caption=caption, reply_markup=reply_markup
        )
    if file_type == RECEIPT_TYPE_PHOTO:
        return await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption, reply_markup=reply_markup)

    # ثبت‌نام‌های قدیمی (قبل از ذخیره‌ی نوع فایل): نوع مشخص نیست. اول به‌عنوان عکس امتحان
    # می‌کنیم و اگر تلگرام رد کرد (یعنی فایل از نوع document بوده) به‌عنوان فایل می‌فرستیم.
    try:
        return await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption, reply_markup=reply_markup)
    except BadRequest:
        return await bot.send_document(
            chat_id=chat_id, document=file_id, caption=caption, reply_markup=reply_markup
        )


async def send_receipt_message(bot, chat_id, file_id, file_type, caption, reply_markup) -> None:
    """
    فیش را همراه توضیحات و دکمه‌ها برای ادمین می‌فرستد.

    اگر caption کوتاه باشد، همه‌چیز در یک پیام می‌آید (عکس/فایل + توضیحات + دکمه‌ها).
    اگر بلند باشد (بیشتر از سقف تلگرام)، فایل با caption کوتاه‌شده فرستاده می‌شود و
    توضیحات کامل + دکمه‌ها در پیام متنی جداگانه‌ای بعد از آن می‌آید.

    اگر ارسال فایل ناموفق باشد، استثنای تلگرام به فراخوان‌کننده برمی‌گردد.
    """
    if len(caption) <= CAPTION_SAFE_LIMIT:
        await _send_media(bot, chat_id, file_id, file_type, caption, reply_markup)
        return

    short_caption = caption[: CAPTION_SAFE_LIMIT - 1] + "…"
    await _send_media(bot, chat_id, file_id, file_type, short_caption, None)
    await bot.send_message(chat_id=chat_id, text=caption[:_MESSAGE_LIMIT], reply_markup=reply_markup)
