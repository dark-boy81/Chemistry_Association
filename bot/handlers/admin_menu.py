"""
پنل مدیریت داخل ربات — ورود از طریق دکمه ثابت «🛠 پنل مدیریت»،
و ناوبری داخلی زیربخش‌ها با دکمه‌های این‌لاین. دسترسی فقط برای آیدی‌های
تلگرامی ثبت‌شده در جدول admins. «لاگ فعالیت ادمین‌ها» فقط برای ادمین ارشد نمایش
داده می‌شود (کنترلش در keyboards.admin_menu_keyboard انجام می‌شود).
"""
from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.admins import is_senior_admin
from bot.handlers.start import is_admin_telegram_id
from bot.keyboards import admin_menu_keyboard


async def admin_menu_text_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ورودی از دکمه ثابت «🛠 پنل مدیریت»."""
    if not is_admin_telegram_id(update.effective_user.id):
        await update.message.reply_text("⛔️ شما به این بخش دسترسی ندارید.")
        return
    senior = is_senior_admin(update.effective_user.id)
    await update.message.reply_text(
        "پنل مدیریت — یکی از گزینه‌ها را انتخاب کنید:", reply_markup=admin_menu_keyboard(senior)
    )


async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بازگشت به زیرمنوی مدیریت از یک بخش عمیق‌تر (این‌لاین)."""
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return
    senior = is_senior_admin(query.from_user.id)
    await query.edit_message_text(
        "پنل مدیریت — یکی از گزینه‌ها را انتخاب کنید:", reply_markup=admin_menu_keyboard(senior)
    )
