"""
تست‌های پیام همگانی ادمین (bot/handlers/broadcast.py) با آبجکت‌های واقعی PTB:
- متن ساده (پیشوند + سقف واقعی تلگرام منهای طول پیشوند)
- عکس/رسانه با کپشن (بدون پیشوند، از طریق copy_message)
- پست فوروارد‌شده، چه متنی و چه رسانه‌ای (بدون پیشوند، از طریق copy_message)
- یک کاربر بلاک‌کرده جلوی ادامه‌ی ارسال به بقیه را نمی‌گیرد
- ترکیب فیلترهای واقعی PTB برای مسیریابی نوع محتوای پشتیبانی‌نشده

اجرا نیاز به متغیرهای محیطی دارد: BOT_TOKEN، DATABASE_URL، WEBHOOK_SECRET (مثل بقیه‌ی
تست‌هایی که به دیتابیس وصل می‌شوند):
    export BOT_TOKEN=123456:TEST DATABASE_URL=postgresql://... WEBHOOK_SECRET=s
    python -m unittest discover -s tests -v
"""
import datetime
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Chat, Message, MessageOriginChannel, MessageOriginUser, PhotoSize, Update, User as TgUser
from telegram.ext import ConversationHandler

import bot.handlers.broadcast as bc
from bot.handlers.broadcast import MAX_BROADCAST_PLAIN_TEXT_LEN, build_admin_broadcast_conversation
from database.db import get_session, init_db
from database.models import Admin, AdminRole, Event, Registration, RegistrationFieldValue, SupportMessage, UserAccount


class FakeBot:
    def __init__(self, fail_chat_ids=()):
        self.sent = []  # (method, chat_id, payload)
        self.fail_chat_ids = set(fail_chat_ids)

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append(("send_message", chat_id, text))
        if chat_id in self.fail_chat_ids:
            from telegram.error import Forbidden

            raise Forbidden("blocked")

    async def copy_message(self, chat_id, from_chat_id, message_id):
        self.sent.append(("copy_message", chat_id, (from_chat_id, message_id)))


def _ctx(bot):
    c = MagicMock()
    c.bot = bot
    return c


def _real_text_message(text, message_id=501, chat_id=999, forward_origin=None):
    chat = Chat(id=chat_id, type="private")
    kwargs = dict(message_id=message_id, date=datetime.datetime.now(), chat=chat, text=text)
    if forward_origin is not None:
        kwargs["forward_origin"] = forward_origin
    return Message(**kwargs)


def _real_media_message(message_id=502, chat_id=999, caption=None, forward_origin=None):
    chat = Chat(id=chat_id, type="private")
    photo = (PhotoSize(file_id="ph1", file_unique_id="u1", width=10, height=10),)
    kwargs = dict(message_id=message_id, date=datetime.datetime.now(), chat=chat, photo=photo, caption=caption)
    if forward_origin is not None:
        kwargs["forward_origin"] = forward_origin
    return Message(**kwargs)


async def _run_handler(message, bot):
    # Message.reply_text یک متد فقط‌خواندنی روی کلاس PTB (دارای __slots__ و frozen) است،
    # پس نمی‌شود آن را روی یک instance ست کرد؛ به‌جایش در سطح کلاس patch می‌شود و mock آن
    # برگردانده می‌شود (چون نمی‌شود رویش نگهش داشت).
    eff_user = NS(id=999, username="adm")
    update = NS(message=message, effective_user=eff_user)
    with patch.object(Message, "reply_text", new_callable=AsyncMock) as reply_mock:
        result = await bc.admin_broadcast_receive(update, _ctx(bot))
    return result, reply_mock


class BroadcastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        session = get_session()
        try:
            for model in (RegistrationFieldValue, Registration, SupportMessage, Event, Admin, UserAccount):
                session.query(model).delete()
            session.commit()
            session.add(Admin(telegram_id=999, username="adm", role=AdminRole.SENIOR))
            for tid in (1, 2, 3):
                session.add(UserAccount(telegram_id=tid, username=f"u{tid}", full_name=f"U{tid}"))
            session.commit()
        finally:
            session.close()

    def _run(self, message, bot):
        import asyncio

        return asyncio.run(_run_handler(message, bot))

    def test_plain_text_uses_send_message_with_prefix(self):
        bot = FakeBot()
        msg = _real_text_message("سلام به همه، این یک پیام تستی است.")
        result, _ = self._run(msg, bot)
        self.assertTrue(all(c[0] == "send_message" for c in bot.sent))
        self.assertTrue(all(c[2].startswith(bc._BROADCAST_PREFIX) for c in bot.sent))
        self.assertEqual(sorted(c[1] for c in bot.sent), [1, 2, 3])
        self.assertEqual(result, ConversationHandler.END)

    def test_plain_text_exactly_at_cap_is_accepted(self):
        bot = FakeBot()
        msg = _real_text_message("ا" * MAX_BROADCAST_PLAIN_TEXT_LEN)
        self._run(msg, bot)
        sent = [c for c in bot.sent if c[0] == "send_message"]
        self.assertEqual(len(sent), 3)
        self.assertLessEqual(len(sent[0][2]), 4096)  # سقف واقعی تلگرام

    def test_plain_text_one_over_cap_is_rejected(self):
        bot = FakeBot()
        msg = _real_text_message("ا" * (MAX_BROADCAST_PLAIN_TEXT_LEN + 1))
        result, reply_mock = self._run(msg, bot)
        self.assertEqual(len(bot.sent), 0)
        self.assertEqual(result, bc.WAITING_BROADCAST_MESSAGE)
        self.assertEqual(reply_mock.await_count, 1)
        self.assertIn("طولانی", reply_mock.await_args[0][0])

    def test_photo_with_caption_uses_copy_message_without_prefix(self):
        bot = FakeBot()
        msg = _real_media_message(caption="عکس یادگاری از رویداد دیروز")
        self._run(msg, bot)
        copies = [c for c in bot.sent if c[0] == "copy_message"]
        self.assertEqual(len(bot.sent), 3)
        self.assertEqual(len(copies), 3)
        self.assertTrue(all(c[2] == (999, 502) for c in copies))
        self.assertEqual(sorted(c[1] for c in copies), [1, 2, 3])

    def test_caption_over_limit_is_rejected(self):
        bot = FakeBot()
        msg = _real_media_message(caption="ک" * 1025)
        result, _ = self._run(msg, bot)
        self.assertEqual(len(bot.sent), 0)
        self.assertEqual(result, bc.WAITING_BROADCAST_MESSAGE)

    def test_forwarded_plain_text_uses_copy_message_not_prefix(self):
        bot = FakeBot()
        origin = MessageOriginChannel(date=datetime.datetime.now(), chat=Chat(id=-100123, type="channel"), message_id=77)
        msg = _real_text_message("این یک پست فوروارد‌شده از کانال است، نباید پیشوند بگیرد.", forward_origin=origin)
        self._run(msg, bot)
        self.assertTrue(all(c[0] == "copy_message" for c in bot.sent))
        self.assertEqual(len(bot.sent), 3)

    def test_forwarded_media_with_caption_uses_copy_message(self):
        bot = FakeBot()
        origin = MessageOriginUser(date=datetime.datetime.now(), sender_user=TgUser(id=55, is_bot=False, first_name="X"))
        msg = _real_media_message(caption="فوروارد شده با کپشن", forward_origin=origin)
        self._run(msg, bot)
        self.assertTrue(all(c[0] == "copy_message" for c in bot.sent))
        self.assertEqual(len(bot.sent), 3)

    def test_one_blocked_user_does_not_stop_the_rest(self):
        bot = FakeBot(fail_chat_ids={2})
        msg = _real_text_message("پیام مهم برای همه")
        result, _ = self._run(msg, bot)
        self.assertEqual(sorted(c[1] for c in bot.sent if c[0] == "send_message"), [1, 2, 3])
        self.assertEqual(result, ConversationHandler.END)

    def test_unsupported_content_type_handler(self):
        import asyncio

        unsupported_msg = NS(reply_text=AsyncMock())
        r = asyncio.run(bc.admin_broadcast_unsupported(NS(message=unsupported_msg), _ctx(FakeBot())))
        self.assertEqual(unsupported_msg.reply_text.await_count, 1)
        self.assertEqual(r, bc.WAITING_BROADCAST_MESSAGE)

    def test_filter_composition_routes_correctly(self):
        conv = build_admin_broadcast_conversation()
        content_handler, fallback_handler = conv.states[bc.WAITING_BROADCAST_MESSAGE][-2:]

        def matches(filt, message):
            upd = Update(update_id=1, message=message)
            return filt.check_update(upd)

        plain = _real_text_message("hello")
        photo = _real_media_message(caption="x")
        sticker = Message(
            message_id=900,
            date=datetime.datetime.now(),
            chat=Chat(id=1, type="private"),
            sticker=NS(file_id="s1", file_unique_id="su1", width=1, height=1, is_animated=False, is_video=False, type="regular"),
        )

        self.assertTrue(matches(content_handler.filters, plain))
        self.assertTrue(matches(content_handler.filters, photo))
        self.assertFalse(matches(content_handler.filters, sticker))
        self.assertTrue(matches(fallback_handler.filters, sticker))


if __name__ == "__main__":
    unittest.main()
