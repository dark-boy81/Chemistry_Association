"""
ارسال پیام همگانی دستی توسط ادمین به همه کاربران ربات — مستقل از انتشار نشریه یا
رویداد جدید (که آن‌ها اطلاع‌رسانی خودکار دارند، در bot/notifications.py).
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

from bot.handlers.start import is_admin_telegram_id
from bot.keyboards import BTN_CANCEL, cancel_reply_keyboard, main_reply_keyboard
from bot.notifications import broadcast_to_all_users
from database.db import get_session
from database.models import UserAccount

WAITING_BROADCAST_MESSAGE = 0


async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return ConversationHandler.END

    await query.edit_message_text("📢 در حال آماده‌سازی پیام همگانی...")
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="متن پیامی که برای همه کاربران ربات ارسال شود را بنویسید:",
        reply_markup=cancel_reply_keyboard(),
    )
    return WAITING_BROADCAST_MESSAGE


async def admin_broadcast_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    session = get_session()
    try:
        count = session.query(UserAccount).count()
    finally:
        session.close()

    await update.message.reply_text(f"⏳ در حال ارسال به {count} کاربر...")
    await broadcast_to_all_users(context.bot, f"📢 پیام از طرف ادمین:\n\n{text}")

    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("✅ پیام همگانی ارسال شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


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
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_receive),
            ],
        },
        fallbacks=cancel_handlers,
    )
