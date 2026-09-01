"""
هندلرهای بخش سوالات متداول (FAQ):
- کاربر: مشاهده لیست سوالات و جواب هرکدام
- ادمین: افزودن سوال جدید، مشاهده لیست، ویرایش سوال/پاسخ، حذف
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
from bot.activity_log import log_admin_activity
from bot.keyboards import BTN_CANCEL, cancel_reply_keyboard, main_reply_keyboard
from database.db import get_session
from database.models import Admin, FAQ

# --- کوئری‌های کمکی ---


def list_faqs():
    session = get_session()
    try:
        return session.query(FAQ).order_by(FAQ.display_order, FAQ.created_at).all()
    finally:
        session.close()


def get_faq_by_id(faq_id: str):
    session = get_session()
    try:
        return session.query(FAQ).filter_by(id=faq_id).first()
    finally:
        session.close()


def _truncate(text: str, length: int = 40) -> str:
    return text if len(text) <= length else text[: length - 1] + "…"


# --- منوی کاربر ---


def _faq_list_view():
    faqs = list_faqs()
    if not faqs:
        return "❓ هنوز سوالی ثبت نشده است.", None
    buttons = [[InlineKeyboardButton(_truncate(f.question), callback_data=f"faq_view_{f.id}")] for f in faqs]
    return "❓ سوالات متداول — روی هرکدام بزنید:", InlineKeyboardMarkup(buttons)


async def faq_menu_text_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, keyboard = _faq_list_view()
    await update.message.reply_text(text, reply_markup=keyboard)


async def faq_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    text, keyboard = _faq_list_view()
    await query.edit_message_text(text, reply_markup=keyboard)


async def faq_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    faq_id = context.match.group("faq_id")
    faq = get_faq_by_id(faq_id)
    if faq is None:
        await query.edit_message_text("این سوال یافت نشد.")
        return

    text = f"❓ {faq.question}\n\n{faq.answer}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت", callback_data="faq_list")]])
    await query.edit_message_text(text, reply_markup=keyboard)


# --- مدیریت FAQ توسط ادمین ---


async def admin_faq_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    buttons = [
        [InlineKeyboardButton("➕ افزودن سوال جدید", callback_data="admin_faq_add")],
        [InlineKeyboardButton("📋 لیست سوالات", callback_data="admin_faq_list")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_menu")],
    ]
    await query.edit_message_text("❓ مدیریت سوالات متداول:", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_faq_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    faqs = list_faqs()
    if not faqs:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_faq")]])
        await query.edit_message_text("هنوز هیچ سوالی ثبت نشده است.", reply_markup=keyboard)
        return

    buttons = [
        [InlineKeyboardButton(_truncate(f.question), callback_data=f"admin_faq_view_{f.id}")] for f in faqs
    ]
    buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_faq")])
    await query.edit_message_text("📋 روی هر سوال بزنید تا مشاهده/ویرایش کنید:", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_faq_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    faq_id = context.match.group("faq_id")
    faq = get_faq_by_id(faq_id)
    if faq is None:
        await query.edit_message_text("این سوال یافت نشد.")
        return

    text = f"❓ {faq.question}\n\n{faq.answer}"
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ ویرایش سوال", callback_data=f"admin_faq_edit_question_{faq.id}")],
            [InlineKeyboardButton("✏️ ویرایش پاسخ", callback_data=f"admin_faq_edit_answer_{faq.id}")],
            [InlineKeyboardButton("🗑 حذف", callback_data=f"admin_faq_delete_{faq.id}")],
            [InlineKeyboardButton("⬅️ بازگشت به لیست", callback_data="admin_faq_list")],
        ]
    )
    await query.edit_message_text(text, reply_markup=keyboard)


async def admin_faq_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    faq_id = context.match.group("faq_id")
    session = get_session()
    try:
        faq = session.query(FAQ).filter_by(id=faq_id).first()
        if faq is not None:
            question_text = faq.question
            session.delete(faq)
            session.commit()
        else:
            question_text = None
    finally:
        session.close()

    if question_text is not None:
        log_admin_activity(
            query.from_user.id, query.from_user.username, "faq_deleted", f"سوال «{_truncate(question_text)}» را حذف کرد"
        )

    text, keyboard = _faq_list_view()
    await query.edit_message_text("✅ سوال حذف شد.\n\n" + text, reply_markup=keyboard)


# --- افزودن سوال جدید (گفتگو) ---

ADD_QUESTION, ADD_ANSWER = range(2)


async def admin_faq_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return ConversationHandler.END

    context.user_data["new_faq"] = {}
    await query.edit_message_text("➕ در حال افزودن سوال جدید...")
    await context.bot.send_message(
        chat_id=query.from_user.id, text="متن سوال را بفرستید:", reply_markup=cancel_reply_keyboard()
    )
    return ADD_QUESTION


async def admin_faq_receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_faq"]["question"] = update.message.text.strip()
    await update.message.reply_text("متن پاسخ را بفرستید:")
    return ADD_ANSWER


async def admin_faq_receive_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data.get("new_faq", {})
    data["answer"] = update.message.text.strip()

    session = get_session()
    try:
        admin_row = session.query(Admin).filter_by(telegram_id=update.effective_user.id).first()
        count = session.query(FAQ).count()
        faq = FAQ(
            question=data["question"],
            answer=data["answer"],
            display_order=count,
            created_by_admin_id=admin_row.id if admin_row else None,
        )
        session.add(faq)
        session.commit()
    finally:
        session.close()

    context.user_data.pop("new_faq", None)
    log_admin_activity(
        update.effective_user.id,
        update.effective_user.username,
        "faq_created",
        f"سوال «{_truncate(data['question'])}» را اضافه کرد",
    )
    await update.message.reply_text("✅ سوال جدید با موفقیت اضافه شد.", reply_markup=main_reply_keyboard(True))
    return ConversationHandler.END


async def admin_faq_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("new_faq", None)
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("افزودن سوال لغو شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


def build_faq_add_conversation() -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", admin_faq_add_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), admin_faq_add_cancel),
    ]
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_faq_add_start, pattern="^admin_faq_add$")],
        states={
            ADD_QUESTION: [*cancel_handlers, MessageHandler(filters.TEXT & ~filters.COMMAND, admin_faq_receive_question)],
            ADD_ANSWER: [*cancel_handlers, MessageHandler(filters.TEXT & ~filters.COMMAND, admin_faq_receive_answer)],
        },
        fallbacks=cancel_handlers,
    )


# --- ویرایش سوال/پاسخ موجود (گفتگو) ---

WAITING_EDIT_VALUE = 0


async def admin_faq_edit_field_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return ConversationHandler.END

    field, faq_id = context.match.group("field"), context.match.group("faq_id")
    faq = get_faq_by_id(faq_id)
    if faq is None:
        await query.edit_message_text("این سوال یافت نشد.")
        return ConversationHandler.END

    context.user_data["editing_faq"] = {"faq_id": faq_id, "field": field}
    label = "سوال" if field == "question" else "پاسخ"
    await query.edit_message_text(f"در حال ویرایش {label}...")
    await context.bot.send_message(
        chat_id=query.from_user.id, text=f"{label} جدید را بفرستید:", reply_markup=cancel_reply_keyboard()
    )
    return WAITING_EDIT_VALUE


async def admin_faq_edit_receive_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    editing = context.user_data.get("editing_faq")
    if not editing:
        return ConversationHandler.END

    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("متن نمی‌تواند خالی باشد.")
        return WAITING_EDIT_VALUE

    session = get_session()
    try:
        faq = session.query(FAQ).filter_by(id=editing["faq_id"]).first()
        if faq is not None:
            setattr(faq, editing["field"], text)
            session.commit()
            question_snapshot = faq.question
        else:
            question_snapshot = None
    finally:
        session.close()

    context.user_data.pop("editing_faq", None)
    if question_snapshot is not None:
        field_label = "سوال" if editing["field"] == "question" else "پاسخ"
        log_admin_activity(
            update.effective_user.id,
            update.effective_user.username,
            "faq_edited",
            f"{field_label} سوال «{_truncate(question_snapshot)}» را ویرایش کرد",
        )
    await update.message.reply_text("✅ تغییرات با موفقیت ذخیره شد.", reply_markup=main_reply_keyboard(True))
    return ConversationHandler.END


async def admin_faq_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("editing_faq", None)
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("ویرایش لغو شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


def build_faq_edit_conversation() -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", admin_faq_edit_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), admin_faq_edit_cancel),
    ]
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_faq_edit_field_start, pattern=r"^admin_faq_edit_(?P<field>question|answer)_(?P<faq_id>.+)$"
            )
        ],
        states={
            WAITING_EDIT_VALUE: [*cancel_handlers, MessageHandler(filters.TEXT & ~filters.COMMAND, admin_faq_edit_receive_value)],
        },
        fallbacks=cancel_handlers,
    )
