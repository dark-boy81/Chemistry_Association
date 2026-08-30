"""
هندلر مشترک دکمه این‌لاین «بازگشت به منوی اصلی» که در زیرمنوهای مختلف استفاده می‌شود.
بخش‌های واقعی (نشریه، رویدادها، FAQ، ارتباط با ادمین) هرکدام در فایل مستقل خودشان
پیاده‌سازی شده‌اند.
"""
from telegram import Update
from telegram.ext import ContextTypes


async def back_to_main_note_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دکمه این‌لاین «بازگشت به منوی اصلی» — چون کیبورد ثابت پایین صفحه همیشه در دسترسه،
    فقط یک یادآوری کوچک نشان می‌دهیم."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🏠 برای بازگشت به منوی اصلی از دکمه‌های پایین صفحه استفاده کنید.")
