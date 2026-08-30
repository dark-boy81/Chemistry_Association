"""
دستور /start — ثبت/به‌روزرسانی کاربر در دیتابیس و نمایش کیبورد ثابت منوی اصلی
(با دکمه اضافه «🛠 پنل مدیریت» اگر فرستنده ادمین باشد).
"""
from telegram import Update
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
        "به ربات انجمن علمی شیمی و نشریه پژواک شیمی خوش آمدید.\n"
        "از دکمه‌های پایین صفحه استفاده کنید 👇"
    )
    await update.message.reply_text(text, reply_markup=main_reply_keyboard(admin))
