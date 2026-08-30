"""
هندلرهای بخش «ارتباط با ادمین»:
- کاربر پیام می‌نویسد → به همه ادمین‌ها فوروارد می‌شود
- هر ادمین با زدن دکمه «✍️ پاسخ» می‌تواند مستقیم به همان کاربر جواب بدهد
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
from database.db import get_session
from database.models import Admin, MessageDirection, SupportMessage, UserAccount

WAITING_USER_MESSAGE, WAITING_ADMIN_REPLY = range(2)


def _get_all_admin_telegram_ids():
    session = get_session()
    try:
        return [a.telegram_id for a in session.query(Admin).all()]
    finally:
        session.close()


# --- کاربر: ارسال پیام به ادمین‌ها ---


async def contact_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "پیام خود را برای ادمین‌های انجمن بنویسید:", reply_markup=cancel_reply_keyboard()
    )
    return WAITING_USER_MESSAGE


async def contact_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.effective_user
    text = update.message.text.strip()

    session = get_session()
    try:
        user = session.query(UserAccount).filter_by(telegram_id=tg_user.id).first()
        if user is None:
            user = UserAccount(telegram_id=tg_user.id, username=tg_user.username, full_name=tg_user.full_name)
            session.add(user)
            session.flush()

        support_message = SupportMessage(
            user_id=user.id, direction=MessageDirection.USER_TO_ADMIN, message_text=text
        )
        session.add(support_message)
        session.commit()
        message_id = support_message.id
        admin_ids = [a.telegram_id for a in session.query(Admin).all()]
    finally:
        session.close()

    sender_name = tg_user.full_name or tg_user.username or str(tg_user.id)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✍️ پاسخ", callback_data=f"admin_reply_{message_id}")]])
    for admin_telegram_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_telegram_id,
                text=f"📩 پیام جدید از {sender_name}:\n\n{text}",
                reply_markup=keyboard,
            )
        except Exception:
            continue

    admin = is_admin_telegram_id(tg_user.id)
    await update.message.reply_text(
        "✅ پیام شما برای ادمین‌ها ارسال شد. به‌زودی پاسخ داده می‌شود.",
        reply_markup=main_reply_keyboard(admin),
    )
    return ConversationHandler.END


async def contact_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("ارسال پیام لغو شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


def build_contact_conversation(contact_button_text: str) -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", contact_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), contact_cancel),
    ]
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Text([contact_button_text]), contact_start)],
        states={
            WAITING_USER_MESSAGE: [
                *cancel_handlers,
                MessageHandler(filters.TEXT & ~filters.COMMAND, contact_receive_message),
            ],
        },
        fallbacks=cancel_handlers,
    )


# --- ادمین: پاسخ به پیام کاربر ---


async def admin_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return ConversationHandler.END

    message_id = context.match.group("message_id")
    session = get_session()
    try:
        support_message = session.query(SupportMessage).filter_by(id=message_id).first()
        if support_message is None:
            await query.edit_message_text("این پیام دیگر در دسترس نیست.")
            return ConversationHandler.END
        user = session.query(UserAccount).filter_by(id=support_message.user_id).first()
        if user is None:
            await query.edit_message_text("کاربر فرستنده این پیام یافت نشد.")
            return ConversationHandler.END
        user_telegram_id = user.telegram_id
    finally:
        session.close()

    context.user_data["reply_to"] = {"message_id": message_id, "user_telegram_id": user_telegram_id}
    await context.bot.send_message(
        chat_id=query.from_user.id, text="پاسخ خود را بنویسید:", reply_markup=cancel_reply_keyboard()
    )
    return WAITING_ADMIN_REPLY


async def admin_reply_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_to = context.user_data.get("reply_to")
    if not reply_to:
        return ConversationHandler.END

    text = update.message.text.strip()
    session = get_session()
    try:
        original = session.query(SupportMessage).filter_by(id=reply_to["message_id"]).first()
        if original is not None:
            original.is_answered = True
            admin_row = session.query(Admin).filter_by(telegram_id=update.effective_user.id).first()
            reply_row = SupportMessage(
                user_id=original.user_id,
                admin_id=admin_row.id if admin_row else None,
                direction=MessageDirection.ADMIN_TO_USER,
                message_text=text,
                is_answered=True,
            )
            session.add(reply_row)
            session.commit()
    finally:
        session.close()

    try:
        await context.bot.send_message(
            chat_id=reply_to["user_telegram_id"], text=f"📬 پاسخ از طرف ادمین:\n\n{text}"
        )
    except Exception:
        pass

    context.user_data.pop("reply_to", None)
    await update.message.reply_text("✅ پاسخ ارسال شد.", reply_markup=main_reply_keyboard(True))
    return ConversationHandler.END


async def admin_reply_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("reply_to", None)
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("پاسخ لغو شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


def build_admin_reply_conversation() -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", admin_reply_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), admin_reply_cancel),
    ]
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_reply_start, pattern=r"^admin_reply_(?P<message_id>.+)$")],
        states={
            WAITING_ADMIN_REPLY: [
                *cancel_handlers,
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reply_receive),
            ],
        },
        fallbacks=cancel_handlers,
    )
