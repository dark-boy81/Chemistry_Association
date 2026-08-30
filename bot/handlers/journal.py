"""
هندلرهای بخش نشریه:
- کاربر: نمایش شماره فعلی، آرشیو شماره‌های قبلی، دانلود PDF
  (ورودی از دکمه ثابت «📚 نشریه پژواک شیمی» + دکمه‌های این‌لاین برای ناوبری داخلی)
- ادمین: افزودن شماره جدید با گفتگوی چندمرحله‌ای، و مشاهده لیست شماره‌ها (از داخل پنل مدیریت)

نکته طراحی: فایل PDF به‌صورت file_id تلگرام ذخیره می‌شود، نه در Supabase Storage —
ساده‌ترین راه برای ارسال/دریافت از طریق خود ربات بدون نیاز به زیرساخت اضافه. اگر در
فاز پنل وب نیاز به لینک عمومی و دائمی شد، باید فایل‌ها به Supabase Storage منتقل شوند.
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
from database.models import JournalIssue

# --- کوئری‌های کمکی ---


def get_latest_issue():
    session = get_session()
    try:
        return session.query(JournalIssue).order_by(JournalIssue.issue_number.desc()).first()
    finally:
        session.close()


def list_all_issues():
    session = get_session()
    try:
        return session.query(JournalIssue).order_by(JournalIssue.issue_number.desc()).all()
    finally:
        session.close()


def get_issue_by_id(issue_id: str):
    session = get_session()
    try:
        return session.query(JournalIssue).filter_by(id=issue_id).first()
    finally:
        session.close()


def _issue_caption(issue: JournalIssue) -> str:
    lines = [f"📚 شماره {issue.issue_number} — {issue.title}"]
    if issue.abstract:
        lines.extend(["", issue.abstract])
    return "\n".join(lines)


def _latest_issue_view():
    issue = get_latest_issue()
    if issue is None:
        text = "📚 هنوز هیچ شماره‌ای از نشریه منتشر نشده است."
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🗄 آرشیو شماره‌های قبلی", callback_data="journal_archive")]]
        )
        return text, keyboard

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📥 دانلود این شماره", callback_data=f"journal_download_{issue.id}")],
            [InlineKeyboardButton("🗄 آرشیو شماره‌های قبلی", callback_data="journal_archive")],
        ]
    )
    return _issue_caption(issue), keyboard


# --- منوی کاربر ---


async def journal_menu_text_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ورودی از دکمه ثابت «📚 نشریه پژواک شیمی»."""
    text, keyboard = _latest_issue_view()
    await update.message.reply_text(text, reply_markup=keyboard)


async def journal_latest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دکمه «بازگشت» از آرشیو — نمایش دوباره شماره فعلی."""
    query = update.callback_query
    await query.answer()
    text, keyboard = _latest_issue_view()
    await query.edit_message_text(text, reply_markup=keyboard)


async def journal_archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    issues = list_all_issues()
    if not issues:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت", callback_data="journal_latest")]])
        await query.edit_message_text("📚 هنوز هیچ شماره‌ای منتشر نشده است.", reply_markup=keyboard)
        return

    buttons = [
        [InlineKeyboardButton(f"شماره {i.issue_number} — {i.title}", callback_data=f"journal_view_{i.id}")]
        for i in issues
    ]
    buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="journal_latest")])
    await query.edit_message_text("🗄 آرشیو شماره‌های نشریه:", reply_markup=InlineKeyboardMarkup(buttons))


async def journal_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    issue_id = context.match.group("issue_id")
    issue = get_issue_by_id(issue_id)
    if issue is None:
        await query.edit_message_text("این شماره یافت نشد.")
        return

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📥 دانلود PDF", callback_data=f"journal_download_{issue.id}")],
            [InlineKeyboardButton("⬅️ بازگشت به آرشیو", callback_data="journal_archive")],
        ]
    )
    await query.edit_message_text(_issue_caption(issue), reply_markup=keyboard)


async def journal_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("در حال ارسال فایل...")

    issue_id = context.match.group("issue_id")
    issue = get_issue_by_id(issue_id)
    if issue is None:
        await context.bot.send_message(chat_id=query.from_user.id, text="این شماره یافت نشد.")
        return

    await context.bot.send_document(
        chat_id=query.from_user.id,
        document=issue.pdf_file_url,
        caption=f"شماره {issue.issue_number} — {issue.title}",
    )


# --- مدیریت نشریه توسط ادمین ---


async def admin_journal_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    buttons = [
        [InlineKeyboardButton("➕ افزودن شماره جدید", callback_data="admin_journal_add")],
        [InlineKeyboardButton("📋 لیست شماره‌ها", callback_data="admin_journal_list")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_menu")],
    ]
    await query.edit_message_text("📚 مدیریت نشریه:", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_journal_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    issues = list_all_issues()
    if not issues:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_journal")]])
        await query.edit_message_text("هنوز هیچ شماره‌ای ثبت نشده است.", reply_markup=keyboard)
        return

    buttons = [
        [InlineKeyboardButton(f"شماره {i.issue_number} — {i.title}", callback_data=f"admin_journal_editview_{i.id}")]
        for i in issues
    ]
    buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_journal")])
    await query.edit_message_text(
        "📋 روی هر شماره بزنید تا مشاهده/ویرایش کنید:", reply_markup=InlineKeyboardMarkup(buttons)
    )


def _issue_edit_view(issue: JournalIssue):
    text = _issue_caption(issue) + "\n\n✏️ برای ویرایش، یکی از گزینه‌های زیر را انتخاب کنید:"
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ ویرایش عنوان", callback_data=f"admin_journal_edit_title_{issue.id}")],
            [InlineKeyboardButton("✏️ ویرایش شماره", callback_data=f"admin_journal_edit_number_{issue.id}")],
            [InlineKeyboardButton("✏️ ویرایش چکیده", callback_data=f"admin_journal_edit_abstract_{issue.id}")],
            [InlineKeyboardButton("📄 جایگزینی فایل PDF", callback_data=f"admin_journal_edit_pdf_{issue.id}")],
            [InlineKeyboardButton("⬅️ بازگشت به لیست", callback_data="admin_journal_list")],
        ]
    )
    return text, keyboard


async def admin_journal_editview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    issue_id = context.match.group("issue_id")
    issue = get_issue_by_id(issue_id)
    if issue is None:
        await query.edit_message_text("این شماره یافت نشد.")
        return

    text, keyboard = _issue_edit_view(issue)
    await query.edit_message_text(text, reply_markup=keyboard)


EDIT_FIELD_LABELS = {
    "title": "عنوان جدید را بفرستید:",
    "number": "شماره جدید را بفرستید (فقط عدد):",
    "abstract": "چکیده جدید را بفرستید:",
    "pdf": "فایل PDF جدید را بفرستید:",
}

WAITING_EDIT_VALUE = 0


async def admin_journal_edit_field_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return ConversationHandler.END

    field, issue_id = context.match.group("field"), context.match.group("issue_id")
    issue = get_issue_by_id(issue_id)
    if issue is None:
        await query.edit_message_text("این شماره یافت نشد.")
        return ConversationHandler.END

    context.user_data["editing_issue"] = {"issue_id": issue_id, "field": field}
    await query.edit_message_text(f"در حال ویرایش «{field}» برای شماره {issue.issue_number}...")
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=EDIT_FIELD_LABELS[field],
        reply_markup=cancel_reply_keyboard(),
    )
    return WAITING_EDIT_VALUE


async def admin_journal_edit_receive_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    editing = context.user_data.get("editing_issue")
    if not editing:
        return ConversationHandler.END

    issue_id, field = editing["issue_id"], editing["field"]

    session = get_session()
    try:
        issue = session.query(JournalIssue).filter_by(id=issue_id).first()
        if issue is None:
            await update.message.reply_text("این شماره دیگر وجود ندارد.", reply_markup=main_reply_keyboard(True))
            context.user_data.pop("editing_issue", None)
            return ConversationHandler.END

        if field == "pdf":
            document = update.message.document
            if document is None or document.mime_type != "application/pdf":
                await update.message.reply_text("لطفاً یک فایل PDF ارسال کنید.")
                return WAITING_EDIT_VALUE
            issue.pdf_file_url = document.file_id

        elif field == "number":
            text = update.message.text.strip() if update.message.text else ""
            if not text.isdigit():
                await update.message.reply_text("لطفاً فقط عدد بفرستید.")
                return WAITING_EDIT_VALUE
            new_number = int(text)
            duplicate = (
                session.query(JournalIssue)
                .filter(JournalIssue.issue_number == new_number, JournalIssue.id != issue_id)
                .first()
            )
            if duplicate:
                await update.message.reply_text(f"⚠️ شماره {new_number} قبلاً برای شماره دیگری ثبت شده است.")
                return WAITING_EDIT_VALUE
            issue.issue_number = new_number

        else:  # title یا abstract
            text = update.message.text.strip() if update.message.text else ""
            if not text:
                await update.message.reply_text("متن نمی‌تواند خالی باشد.")
                return WAITING_EDIT_VALUE
            setattr(issue, field, text)

        session.commit()
    finally:
        session.close()

    context.user_data.pop("editing_issue", None)
    await update.message.reply_text("✅ تغییرات با موفقیت ذخیره شد.", reply_markup=main_reply_keyboard(True))
    return ConversationHandler.END


async def admin_journal_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("editing_issue", None)
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("ویرایش لغو شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


def build_journal_edit_conversation() -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", admin_journal_edit_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), admin_journal_edit_cancel),
    ]
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_journal_edit_field_start,
                pattern=r"^admin_journal_edit_(?P<field>title|number|abstract|pdf)_(?P<issue_id>.+)$",
            )
        ],
        states={
            WAITING_EDIT_VALUE: [
                *cancel_handlers,
                MessageHandler(filters.TEXT | filters.Document.PDF, admin_journal_edit_receive_value),
            ],
        },
        fallbacks=cancel_handlers,
    )


WAITING_PDF, WAITING_TITLE, WAITING_NUMBER, WAITING_ABSTRACT = range(4)


async def admin_journal_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return ConversationHandler.END

    context.user_data["new_issue"] = {}
    await query.edit_message_text("📄 در حال شروع افزودن شماره جدید...")
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="فایل PDF شماره جدید نشریه را ارسال کنید.\n(برای انصراف، دکمه «❌ انصراف» را بزنید.)",
        reply_markup=cancel_reply_keyboard(),
    )
    return WAITING_PDF


async def admin_journal_receive_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    document = update.message.document
    if document is None or document.mime_type != "application/pdf":
        await update.message.reply_text("لطفاً یک فایل PDF ارسال کنید.")
        return WAITING_PDF

    context.user_data["new_issue"]["pdf_file_id"] = document.file_id
    await update.message.reply_text("عنوان این شماره را وارد کنید:")
    return WAITING_TITLE


async def admin_journal_receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_issue"]["title"] = update.message.text.strip()
    await update.message.reply_text("شماره این نشریه چندم است؟ (فقط عدد)")
    return WAITING_NUMBER


async def admin_journal_receive_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("لطفاً فقط عدد بفرستید (مثلاً 4).")
        return WAITING_NUMBER

    context.user_data["new_issue"]["issue_number"] = int(text)
    await update.message.reply_text("چکیده این شماره را بنویسید:")
    return WAITING_ABSTRACT


async def admin_journal_receive_abstract(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data.get("new_issue", {})
    data["abstract"] = update.message.text.strip()

    session = get_session()
    try:
        existing = session.query(JournalIssue).filter_by(issue_number=data["issue_number"]).first()
        if existing:
            context.user_data.pop("new_issue", None)
            await update.message.reply_text(
                f"⚠️ شماره {data['issue_number']} از قبل ثبت شده است. عملیات لغو شد.",
                reply_markup=main_reply_keyboard(True),
            )
            return ConversationHandler.END

        issue = JournalIssue(
            issue_number=data["issue_number"],
            title=data["title"],
            abstract=data["abstract"],
            pdf_file_url=data["pdf_file_id"],
        )
        session.add(issue)
        session.commit()
    finally:
        session.close()

    context.user_data.pop("new_issue", None)
    await update.message.reply_text(
        f"✅ شماره {data['issue_number']} با عنوان «{data['title']}» با موفقیت اضافه شد.",
        reply_markup=main_reply_keyboard(True),
    )
    return ConversationHandler.END


async def admin_journal_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("new_issue", None)
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("عملیات افزودن شماره جدید لغو شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


def build_journal_add_conversation() -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", admin_journal_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), admin_journal_cancel),
    ]
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_journal_add_start, pattern="^admin_journal_add$")],
        states={
            WAITING_PDF: [*cancel_handlers, MessageHandler(filters.Document.PDF, admin_journal_receive_pdf)],
            WAITING_TITLE: [
                *cancel_handlers,
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_journal_receive_title),
            ],
            WAITING_NUMBER: [
                *cancel_handlers,
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_journal_receive_number),
            ],
            WAITING_ABSTRACT: [
                *cancel_handlers,
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_journal_receive_abstract),
            ],
        },
        fallbacks=cancel_handlers,
    )
