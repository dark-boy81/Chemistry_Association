"""
ارسال پیام به تمام ادمین‌ها (مثلاً هنگام ثبت‌نام جدید یا پیام کاربر برای پشتیبانی).
"""
import logging

from telegram import InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from database.db import get_session
from database.models import Admin

logger = logging.getLogger(__name__)


def get_all_admin_telegram_ids() -> list[int]:
    session = get_session()
    try:
        return [a.telegram_id for a in session.query(Admin).all()]
    finally:
        session.close()


async def notify_all_admins(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    for admin_telegram_id in get_all_admin_telegram_ids():
        try:
            await context.bot.send_message(
                chat_id=admin_telegram_id, text=text, reply_markup=reply_markup
            )
        except TelegramError:
            logger.warning("ارسال پیام به ادمین %s ناموفق بود.", admin_telegram_id)
