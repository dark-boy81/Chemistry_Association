"""
ابزارهای مشترک بین مکالمه‌های مختلف ربات.
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.handlers.start import is_admin_telegram_id
from database.models import RegistrationStatus

require_admin = is_admin_telegram_id

STATUS_LABELS = {
    RegistrationStatus.PENDING: "⏳ در انتظار تایید",
    RegistrationStatus.APPROVED: "✅ تایید شده",
    RegistrationStatus.REJECTED: "❌ رد شده",
    RegistrationStatus.WAITLISTED: "🕒 در لیست انتظار",
    RegistrationStatus.CANCELLED: "🚫 لغو شده",
}


def translate_status(status: RegistrationStatus) -> str:
    return STATUS_LABELS.get(status, str(status))


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.message:
        await update.message.reply_text("عملیات لغو شد. برای شروع دوباره /start را بزنید.")
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("عملیات لغو شد.")
    return ConversationHandler.END
