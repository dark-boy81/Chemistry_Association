"""
تست‌های endpoint وب‌هوک تلگرام (server.py):
- بررسی secret (هدر گم‌شده، غلط، غیر-ASCII)
- آپدیت معتبر باید در صف (update_queue) گذاشته شود، نه مستقیم پردازش (bot/app.py آن را
  در پس‌زمینه پردازش می‌کند تا اگر یک Handler کند بود، پاسخ به تلگرام معطل نماند)
- بدنه‌های نامعتبر (JSON خراب، آرایه به‌جای شیء، dict بدون update_id) باید ۴۰۰ بدهند،
  نه خطای ۵۰۰ که هم برای Render بد است و هم باعث می‌شود تلگرام دوباره همان را بفرستد
- بدنه‌ی بیش‌ازحد بزرگ باید ۴۱۳ بدهد

نکته: چون بدنه‌ی این فایل import سنگین دارد (کل bot.app از طریق server import می‌شود)،
اجرا نیاز به متغیرهای محیطی دارد: BOT_TOKEN، DATABASE_URL، WEBHOOK_SECRET (مثل بقیه‌ی
پروژه). برای اجرای این تست به‌تنهایی:

    export BOT_TOKEN=123456:TEST DATABASE_URL=postgresql://... WEBHOOK_SECRET=s
    python -m unittest tests.test_webhook -v
"""
import os
import unittest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import server


class FakeQueue:
    """صف ساختگی برای اینکه ببینیم آپدیت به صف رسیده، نه اینکه واقعاً پردازش شود."""

    def __init__(self):
        self.items = []

    async def put(self, item):
        self.items.append(item)


class WebhookTests(unittest.TestCase):
    def setUp(self):
        self.original_queue = server.telegram_app.update_queue
        self.queue = FakeQueue()
        server.telegram_app.update_queue = self.queue
        self.client = TestClient(server.app)
        self.secret = os.environ["WEBHOOK_SECRET"]
        self.headers = {"X-Telegram-Bot-Api-Secret-Token": self.secret}

    def tearDown(self):
        server.telegram_app.update_queue = self.original_queue

    def test_missing_header_rejected(self):
        r = self.client.post("/telegram/webhook", json={"update_id": 1})
        self.assertEqual(r.status_code, 403)

    def test_wrong_secret_rejected(self):
        r = self.client.post(
            "/telegram/webhook", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}
        )
        self.assertEqual(r.status_code, 403)

    def test_non_ascii_header_does_not_500(self):
        r = self.client.post(
            "/telegram/webhook",
            json={"update_id": 1},
            headers=[(b"X-Telegram-Bot-Api-Secret-Token", "é☃".encode("utf-8"))],
        )
        self.assertEqual(r.status_code, 403)

    def test_valid_update_is_queued_not_processed_inline(self):
        valid = {
            "update_id": 42,
            "message": {"message_id": 1, "date": 0, "chat": {"id": 1, "type": "private"}, "text": "hi"},
        }
        r = self.client.post("/telegram/webhook", json=valid, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.queue.items), 1)
        self.assertEqual(self.queue.items[0].update_id, 42)

    def test_invalid_json_returns_400_not_500(self):
        r = self.client.post(
            "/telegram/webhook", data=b"not json{{{", headers={**self.headers, "Content-Type": "application/json"}
        )
        self.assertEqual(r.status_code, 400)

    def test_valid_json_missing_update_id_returns_400(self):
        r = self.client.post("/telegram/webhook", json={"no_update_id": True}, headers=self.headers)
        self.assertEqual(r.status_code, 400)

    def test_json_array_instead_of_object_returns_400(self):
        r = self.client.post("/telegram/webhook", json=["not", "a", "dict"], headers=self.headers)
        self.assertEqual(r.status_code, 400)

    def test_empty_json_object_returns_400(self):
        r = self.client.post("/telegram/webhook", json={}, headers=self.headers)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(self.queue.items), 0)

    def test_oversized_body_returns_413(self):
        big_body = b'{"update_id": 1, "pad": "' + b"x" * 1_100_000 + b'"}'
        r = self.client.post(
            "/telegram/webhook", data=big_body, headers={**self.headers, "Content-Type": "application/json"}
        )
        self.assertEqual(r.status_code, 413)


if __name__ == "__main__":
    unittest.main()
