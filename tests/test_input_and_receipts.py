"""
تست‌های واحد (بدون نیاز به دیتابیس یا اتصال به تلگرام) برای:
- bot/utils/validation.py  (سقف طول و محدوده‌ی ورودی‌ها)
- bot/utils/receipts.py    (اعتبارسنجی فایل فیش و انتخاب متد درست ارسال)

اجرا (از ریشه‌ی پروژه):
    python -m unittest discover -s tests -v
"""
import asyncio
import unittest
from types import SimpleNamespace as NS

from telegram.error import BadRequest

from bot.utils import receipts
from bot.utils.validation import (
    MAX_EVENT_CAPACITY,
    length_error,
    parse_int_in_range,
    validate_event_value,
)


def _doc(mime, name="f", size=1000, file_id="FID"):
    return NS(mime_type=mime, file_name=name, file_size=size, file_id=file_id)


def _msg(photo=None, document=None):
    return NS(photo=photo or [], document=document)


class ValidationTests(unittest.TestCase):
    def test_length_error(self):
        self.assertIsNone(length_error("a" * 10, 10, "x"))
        self.assertIsNotNone(length_error("a" * 11, 10, "x"))

    def test_parse_int_in_range(self):
        self.assertEqual(parse_int_in_range("12", 1, 100), 12)
        self.assertEqual(parse_int_in_range("۱۲", 1, 100), 12)  # ارقام فارسی
        self.assertIsNone(parse_int_in_range("0", 1, 100))
        self.assertIsNone(parse_int_in_range("101", 1, 100))
        self.assertIsNone(parse_int_in_range("-5", 1, 100))
        self.assertIsNone(parse_int_in_range("abc", 1, 100))
        self.assertIsNone(parse_int_in_range("²", 1, 100))  # isdigit درست، int() نادرست
        self.assertIsNone(parse_int_in_range("", 1, 100))

    def test_event_values(self):
        self.assertIsNotNone(validate_event_value("title", ""))
        self.assertIsNotNone(validate_event_value("title", "x" * 201))
        self.assertIsNone(validate_event_value("title", "x" * 200))
        self.assertIsNone(validate_event_value("capacity", str(MAX_EVENT_CAPACITY)))
        self.assertIsNotNone(validate_event_value("capacity", str(MAX_EVENT_CAPACITY + 1)))
        self.assertIsNone(validate_event_value("price", "-"))  # رایگان
        self.assertIsNone(validate_event_value("price", "0"))
        self.assertIsNotNone(validate_event_value("price", "9" * 15))
        self.assertIsNone(validate_event_value("card", "-"))
        self.assertIsNotNone(validate_event_value("card", "1" * 65))
        self.assertIsNone(validate_event_value("date", "هرچیزی"))  # فیلد ناشناخته/تاریخ: چیزی چک نمی‌شود


class ExtractReceiptTests(unittest.TestCase):
    def test_photo(self):
        photo = [NS(file_id="small", file_size=10), NS(file_id="big", file_size=5000)]
        r, err = receipts.extract_receipt(_msg(photo=photo))
        self.assertIsNone(err)
        self.assertEqual((r.file_id, r.file_type), ("big", "photo"))

    def test_allowed_documents(self):
        for mime in ("application/pdf", "image/png", "image/jpeg", "IMAGE/JPEG"):
            r, err = receipts.extract_receipt(_msg(document=_doc(mime)))
            self.assertIsNone(err, mime)
            self.assertEqual(r.file_type, "document")

    def test_generic_mime_falls_back_to_extension(self):
        r, err = receipts.extract_receipt(_msg(document=_doc("application/octet-stream", "receipt.PDF")))
        self.assertIsNone(err)
        self.assertIsNotNone(r)
        r, err = receipts.extract_receipt(_msg(document=_doc("application/octet-stream", "malware.exe")))
        self.assertIsNone(r)
        self.assertEqual(err, receipts.INVALID_FILE_TEXT)

    def test_rejected_documents(self):
        for mime in ("application/zip", "video/mp4", "image/heic", "text/html"):
            r, err = receipts.extract_receipt(_msg(document=_doc(mime, "a.pdf")))  # اسم فایل فریب‌دهنده
            self.assertIsNone(r, mime)
            self.assertEqual(err, receipts.INVALID_FILE_TEXT)

    def test_size_limit(self):
        big = receipts.MAX_RECEIPT_BYTES + 1
        r, err = receipts.extract_receipt(_msg(document=_doc("application/pdf", size=big)))
        self.assertEqual(err, receipts.TOO_LARGE_TEXT)

    def test_no_file(self):
        self.assertEqual(receipts.extract_receipt(_msg()), (None, None))


class FakeBot:
    def __init__(self, photo_fails=False):
        self.calls, self.photo_fails = [], photo_fails

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None):
        self.calls.append(("photo", caption, reply_markup))
        if self.photo_fails:
            raise BadRequest("wrong type of the web page content")

    async def send_document(self, chat_id, document, caption=None, reply_markup=None):
        self.calls.append(("document", caption, reply_markup))

    async def send_message(self, chat_id, text, reply_markup=None):
        self.calls.append(("message", text, reply_markup))


def _send(bot, file_type, caption, kb="KB"):
    asyncio.run(receipts.send_receipt_message(bot, 1, "FID", file_type, caption, kb))
    return [c[0] for c in bot.calls]


class SendReceiptTests(unittest.TestCase):
    def test_photo_and_document_use_matching_method(self):
        self.assertEqual(_send(FakeBot(), "photo", "cap"), ["photo"])
        self.assertEqual(_send(FakeBot(), "document", "cap"), ["document"])

    def test_legacy_type_falls_back_to_document(self):
        self.assertEqual(_send(FakeBot(photo_fails=False), None, "cap"), ["photo"])
        self.assertEqual(_send(FakeBot(photo_fails=True), None, "cap"), ["photo", "document"])

    def test_long_caption_is_split(self):
        bot = FakeBot()
        kinds = _send(bot, "photo", "x" * 2000)
        self.assertEqual(kinds, ["photo", "message"])
        self.assertLessEqual(len(bot.calls[0][1]), 1024)
        self.assertIsNone(bot.calls[0][2])  # دکمه‌ها فقط روی پیام آخر
        self.assertEqual(bot.calls[1][2], "KB")


if __name__ == "__main__":
    unittest.main()
