"""
ارسال پیام همگانی دستی توسط ادمین به همه کاربران ربات — مستقل از انتشار نشریه یا
رویداد جدید (که آن‌ها اطلاع‌رسانی خودکار دارند، در bot/notifications.py).

سه نوع ورودی از ادمین پذیرفته می‌شود:
۱. متن ساده (خودِ ادمین تایپ کرده) → با پیشوند «📢 پیام از طرف ادمین» ارسال می‌شود،
   دقیقاً مثل قبل، فقط سقفش به‌جای عدد دلخواه ۳۰۰۰، به سقف واقعی تلگرام نزدیک شده.
۲. عکس/ویدیو/فایل/GIF با کپشن (ادمین خودش فرستاده) → بدون هیچ پیشوندی، همان‌طور که
   هست کپی می‌شود (کپشن هم اگر باشد دست‌نخورده می‌ماند).
۳. یک پیام فوروارد‌شده (از کانال/گروه/چت دیگری) → دقیقاً همان‌طور که هست، بدون هیچ
   پیشوندی، برای همه کپی می‌شود — even اگر خودش متن ساده باشد، نه رسانه.

تشخیص (۱) در برابر (۲ و ۳): اگر پیام متن دارد (message.text) و فوروارد‌شده نیست،
یعنی ادمین خودش تایپ کرده → حالت (۱). در غیر این صورت (فوروارد‌شده، یا رسانه با یا
بدون کپشن) → کپی می‌شود (هندلرهای ۲ و ۳ در کد یکی‌اند چون copy_message خودش نوع
محتوا را مدیریت می‌کند).
"""
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.activity_log import log_admin_activity
from bot.handlers.start import is_admin_telegram_id
from bot.keyboards import BTN_CANCEL, cancel_reply_keyboard, main_reply_keyboard
from bot.notifications import broadcast_to_all_users, copy_to_all_users
from bot.utils.validation import TELEGRAM_CAPTION_LIMIT, TELEGRAM_TEXT_MESSAGE_LIMIT, length_error
from database.db import get_session
from database.models import UserAccount

WAITING_BROADCAST_MESSAGE = 0

_BROADCAST_PREFIX = "📢 پیام از طرف ادمین:\n\n"
# سقف پیام خالص متنی: سقف واقعی تلگرام منهای طول همین پیشوند، تا با اضافه شدنش هیچ‌وقت
# از ۴۰۹۶ رد نشود (پیشوند ثابت است، پس این عدد هم هر بار یکی است، نه این‌که هر بار
# دوباره محاسبه‌اش کنیم چیزی عوض شود — فقط خوانایی کد را بیشتر می‌کند)
MAX_BROADCAST_PLAIN_TEXT_LEN = TELEGRAM_TEXT_MESSAGE_LIMIT - len(_BROADCAST_PREFIX)

# انواع پیامی که به‌عنوان «پست» قابل ارسال همگانی هستند: متن، عکس، ویدیو، فایل، GIF.
# استیکر/صوت/لوکیشن/مخاطب/نظرسنجی عمداً اینجا نیستند — این‌ها را هم copy_message
# فنی می‌تواند کپی کند، ولی چیزی نیست که این فیچر برایش خواسته شده، و بهتر است ادمین
# پیام واضح «این نوع پشتیبانی نمی‌شود» ببیند تا با سکوت گیج شود.
_SUPPORTED_BROADCAST_CONTENT = (
    filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.ANIMATION
)


def _count_users() -> int:
    session = get_session()
    try:
        return session.query(UserAccount).count()
    finally:
        session.close()


async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return ConversationHandler.END

    await query.edit_message_text("📢 در حال آماده‌سازی پیام همگانی...")
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=(
            "پیامی که برای همه کاربران ربات ارسال شود را بفرستید:\n"
            "متن، عکس/ویدیو/فایل با کپشن، یا حتی یک پست فوروارد‌شده از جای دیگر — هر"
            " کدام را بفرستید همان برای همه کپی می‌شود."
        ),
        reply_markup=cancel_reply_keyboard(),
    )
    return WAITING_BROADCAST_MESSAGE


async def admin_broadcast_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    is_forwarded = message.forward_origin is not None

    if message.text and not is_forwarded:
        # ادمین خودش متن تایپ کرده — پیشوند اضافه و مثل قبل با send_message ارسال می‌شود
        text = message.text.strip()
        error = length_error(text, MAX_BROADCAST_PLAIN_TEXT_LEN, "پیام")
        if error:
            await message.reply_text(error)
            return WAITING_BROADCAST_MESSAGE

        count = _count_users()
        await message.reply_text(f"⏳ در حال ارسال به {count} کاربر...")
        await broadcast_to_all_users(context.bot, f"{_BROADCAST_PREFIX}{text}")
        kind_label = "متنی"
    else:
        # رسانه (عکس/ویدیو/فایل/GIF) یا یک پست فوروارد‌شده — دقیقاً همان‌طور که هست،
        # بدون هیچ پیشوندی، کپی می‌شود
        if message.caption:
            error = length_error(message.caption, TELEGRAM_CAPTION_LIMIT, "کپشن")
            if error:
                await message.reply_text(error)
                return WAITING_BROADCAST_MESSAGE

        count = _count_users()
        await message.reply_text(f"⏳ در حال ارسال به {count} کاربر...")
        await copy_to_all_users(context.bot, from_chat_id=message.chat_id, message_id=message.message_id)
        kind_label = "فوروارد‌شده" if is_forwarded else "رسانه‌ای"

    log_admin_activity(
        update.effective_user.id,
        update.effective_user.username,
        "broadcast_sent",
        f"پیام همگانی ({kind_label}) برای {count} کاربر فرستاد",
    )
    admin = is_admin_telegram_id(update.effective_user.id)
    await message.reply_text("✅ پیام همگانی ارسال شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


async def admin_broadcast_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "⚠️ این نوع پیام پشتیبانی نمی‌شود.\n"
        "برای ارسال همگانی فقط متن، عکس، ویدیو، فایل یا GIF (از جمله فوروارد‌شده) را بفرستید."
    )
    return WAITING_BROADCAST_MESSAGE


async def admin_broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("ارسال پیام همگانی لغو شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


def build_admin_broadcast_conversation() -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", admin_broadcast_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), admin_broadcast_cancel),
    ]
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")],
        states={
            WAITING_BROADCAST_MESSAGE: [
                *cancel_handlers,
                MessageHandler(_SUPPORTED_BROADCAST_CONTENT & ~filters.COMMAND, admin_broadcast_receive),
                MessageHandler(filters.ALL & ~filters.COMMAND, admin_broadcast_unsupported),
            ],
        },
        fallbacks=cancel_handlers,
    )
