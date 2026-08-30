"""
کیبوردهای ربات:
- کیبورد ثابت پایین صفحه (Reply Keyboard) برای منوی اصلی — همیشه در دسترس است،
  دقیقاً مثل ربات‌های معروفی که یک منوی ثابت پایین + دکمه‌های این‌لاین برای جزئیات دارند.
- کیبوردهای این‌لاین (ضمیمه پیام) برای زیرمنوها، ناوبری داخلی و اکشن‌های هر بخش.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

BTN_JOURNAL = "📚 نشریه پژواک شیمی"
BTN_EVENTS = "📅 رویدادها"
BTN_FAQ = "❓ سوالات متداول"
BTN_CONTACT = "✉️ ارتباط با ادمین"
BTN_ADMIN_PANEL = "🛠 پنل مدیریت"
BTN_CANCEL = "❌ انصراف"


def main_reply_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    """منوی اصلی — کیبورد ثابت پایین صفحه، همیشه در دسترس کاربر."""
    rows = [
        [KeyboardButton(BTN_JOURNAL), KeyboardButton(BTN_EVENTS)],
        [KeyboardButton(BTN_FAQ), KeyboardButton(BTN_CONTACT)],
    ]
    if is_admin:
        rows.append([KeyboardButton(BTN_ADMIN_PANEL)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    """کیبورد موقت هنگام گفتگوهای چندمرحله‌ای (مثل افزودن شماره نشریه) —
    جایگزین موقت منوی اصلی تا از تداخل دکمه‌ها با متن ورودی جلوگیری شود."""
    return ReplyKeyboardMarkup([[KeyboardButton(BTN_CANCEL)]], resize_keyboard=True)


def back_to_main_inline_button() -> InlineKeyboardButton:
    return InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_main_note")


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """زیرمنوی این‌لاین پنل مدیریت — بعد از زدن دکمه ثابت «🛠 پنل مدیریت» نمایش داده می‌شود."""
    buttons = [
        [InlineKeyboardButton("📅 مدیریت رویدادها", callback_data="admin_events")],
        [InlineKeyboardButton("🧾 تایید فیش‌های واریزی", callback_data="admin_receipts")],
        [InlineKeyboardButton("📚 مدیریت نشریه", callback_data="admin_journal")],
        [InlineKeyboardButton("❓ مدیریت FAQ", callback_data="admin_faq")],
        [InlineKeyboardButton("👥 مدیریت ادمین‌ها", callback_data="admin_manage_admins")],
        [InlineKeyboardButton("📊 آمار و گزارش", callback_data="admin_stats")],
        [back_to_main_inline_button()],
    ]
    return InlineKeyboardMarkup(buttons)
