"""
دستور /start — ثبت/به‌روزرسانی کاربر در دیتابیس و نمایش کیبورد ثابت منوی اصلی
(با دکمه اضافه «🛠 پنل مدیریت» اگر فرستنده ادمین باشد). همچنین دیپ‌لینک‌های
مستقیم به یک رویداد (`?start=ev_<event_id>`) یا یک شماره نشریه
(`?start=is_<issue_id>`) را مدیریت می‌کند.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import main_reply_keyboard
from database.db import get_session
from database.models import Admin, UserAccount


def is_admin_telegram_id(telegram_id: int) -> bool:
    session = get_session()
    try:
        return session.query(Admin).filter_by(telegram_id=telegram_id).first() is not None
    finally:
        session.close()


def upsert_user(telegram_id: int, username: str | None, full_name: str | None) -> None:
    session = get_session()
    try:
        user = session.query(UserAccount).filter_by(telegram_id=telegram_id).first()
        if user is None:
            user = UserAccount(telegram_id=telegram_id, username=username, full_name=full_name)
            session.add(user)
        else:
            user.username = username
            user.full_name = full_name
        session.commit()
    finally:
        session.close()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    upsert_user(tg_user.id, tg_user.username, tg_user.full_name)
    admin = is_admin_telegram_id(tg_user.id)

    text = (
        f"سلام {tg_user.first_name} 👋\n\n"
        "به ربات انجمن علمی شیمی دانشگاه آزاد گرگان خوش آمدید.\n"
        "از دکمه‌های پایین صفحه استفاده کنید 👇"
    )
    await update.message.reply_text(text, reply_markup=main_reply_keyboard(admin))

    if context.args:
        await _handle_start_payload(update, context, context.args[0])


async def _handle_start_payload(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str) -> None:
    """دیپ‌لینک‌های مستقیم را مدیریت می‌کند — import ها عمداً داخل تابع هستند تا از
    وابستگی چرخه‌ای با ماژول‌های events/journal (که خودشان از start.py استفاده
    می‌کنند) جلوگیری شود."""
    if payload.startswith("ev_"):
        from bot.handlers.events import _event_detail_view, get_event_by_id

        event_id = payload[3:]
        event = get_event_by_id(event_id)
        if event is None:
            await update.message.reply_text("این رویداد یافت نشد یا حذف شده است.")
            return
        text, keyboard = _event_detail_view(event, update.effective_user.id)
        await update.message.reply_text(text, reply_markup=keyboard)

    elif payload.startswith("is_"):
        from bot.handlers.journal import _issue_caption, _record_engagement, get_issue_by_id

        issue_id = payload[3:]
        issue = get_issue_by_id(issue_id)
        if issue is None:
            await update.message.reply_text("این شماره یافت نشد.")
            return
        _record_engagement(update.effective_user.id, issue.id, "view")
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📥 دانلود PDF", callback_data=f"journal_download_{issue.id}")]]
        )
        await update.message.reply_text(_issue_caption(issue), reply_markup=keyboard)
