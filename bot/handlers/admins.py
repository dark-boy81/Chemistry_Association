"""
هندلرهای بخش «مدیریت ادمین‌ها» — فقط ادمین ارشد می‌تواند ادمین اضافه/حذف کند
یا ارشدیت را به شخص دیگری منتقل کرده و کناره‌گیری کند. حداکثر ۵ ادمین مجاز است.
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
from bot.keyboards import BTN_CANCEL, admin_menu_keyboard, cancel_reply_keyboard, main_reply_keyboard
from database.db import get_session
from database.models import (
    FAQ,
    Admin,
    AdminRole,
    Event,
    JournalIssue,
    Registration,
    SupportMessage,
)

MAX_ADMINS = 5


def list_admins():
    session = get_session()
    try:
        return session.query(Admin).order_by(Admin.role, Admin.added_at).all()
    finally:
        session.close()


def is_senior_admin(telegram_id: int) -> bool:
    session = get_session()
    try:
        admin = session.query(Admin).filter_by(telegram_id=telegram_id).first()
        return admin is not None and admin.role == AdminRole.SENIOR
    finally:
        session.close()


def _detach_admin_references(session, admin_id: str) -> None:
    """قبل از حذف یک ادمین، همه ارجاع‌های خارجی (رویداد/نشریه/FAQ/فیش/پیام) به او را
    خالی می‌کند تا حذف با خطای foreign key مواجه نشود؛ خود رکوردها حذف نمی‌شوند."""
    session.query(Event).filter_by(created_by_admin_id=admin_id).update({"created_by_admin_id": None})
    session.query(JournalIssue).filter_by(uploaded_by_admin_id=admin_id).update({"uploaded_by_admin_id": None})
    session.query(FAQ).filter_by(created_by_admin_id=admin_id).update({"created_by_admin_id": None})
    session.query(Registration).filter_by(reviewed_by_admin_id=admin_id).update({"reviewed_by_admin_id": None})
    session.query(SupportMessage).filter_by(admin_id=admin_id).update({"admin_id": None})


def _admin_display_name(admin: Admin) -> str:
    if admin.username:
        return f"@{admin.username}"
    if admin.full_name:
        return admin.full_name
    return str(admin.telegram_id)


# --- منوی اصلی مدیریت ادمین‌ها ---


async def admin_manage_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    admins = list_admins()
    senior = is_senior_admin(query.from_user.id)

    lines = ["👥 لیست ادمین‌ها:", ""]
    for a in admins:
        role_label = "👑 ارشد" if a.role == AdminRole.SENIOR else "ادمین"
        lines.append(f"• {_admin_display_name(a)} — {role_label}")

    buttons = []
    if senior:
        if len(admins) < MAX_ADMINS:
            buttons.append([InlineKeyboardButton("➕ افزودن ادمین جدید", callback_data="admin_add_new")])
        for a in admins:
            if a.role != AdminRole.SENIOR:
                buttons.append(
                    [InlineKeyboardButton(f"🗑 حذف {_admin_display_name(a)}", callback_data=f"admin_removeask_{a.id}")]
                )
        buttons.append([InlineKeyboardButton("🔁 انتقال ارشدیت و کناره‌گیری", callback_data="admin_transfer_start")])
    else:
        lines.append("")
        lines.append("(فقط ادمین ارشد می‌تواند ادمین اضافه/حذف کند یا ارشدیت را منتقل کند.)")

    buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_menu")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


# --- افزودن ادمین جدید ---

ADD_ADMIN_ID = 0


async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_senior_admin(query.from_user.id):
        await query.edit_message_text("⛔️ فقط ادمین ارشد می‌تواند ادمین اضافه کند.")
        return ConversationHandler.END

    if len(list_admins()) >= MAX_ADMINS:
        await query.edit_message_text(f"⚠️ حداکثر تعداد ادمین ({MAX_ADMINS} نفر) پر شده است.")
        return ConversationHandler.END

    await query.edit_message_text("➕ در حال افزودن ادمین جدید...")
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="آیدی عددی تلگرام ادمین جدید را بفرستید.\n"
        "(می‌توانید با فوروارد کردن یک پیام از او و دیدن آیدی، یا از طریق ربات‌هایی مثل @userinfobot آن را پیدا کنید.)",
        reply_markup=cancel_reply_keyboard(),
    )
    return ADD_ADMIN_ID


async def admin_add_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("لطفاً فقط آیدی عددی تلگرام را بفرستید.")
        return ADD_ADMIN_ID

    new_telegram_id = int(text)
    session = get_session()
    try:
        existing = session.query(Admin).filter_by(telegram_id=new_telegram_id).first()
        if existing:
            await update.message.reply_text(
                "این شخص از قبل ادمین است.", reply_markup=main_reply_keyboard(True)
            )
            return ConversationHandler.END

        if session.query(Admin).count() >= MAX_ADMINS:
            await update.message.reply_text(
                f"⚠️ حداکثر تعداد ادمین ({MAX_ADMINS} نفر) پر شده است.", reply_markup=main_reply_keyboard(True)
            )
            return ConversationHandler.END

        username = None
        full_name = None
        try:
            chat = await context.bot.get_chat(new_telegram_id)
            username = chat.username
            full_name = chat.full_name
        except Exception:
            pass

        admin = Admin(
            telegram_id=new_telegram_id,
            username=username,
            full_name=full_name,
            role=AdminRole.ADMIN,
            added_by_telegram_id=update.effective_user.id,
        )
        session.add(admin)
        session.commit()
    finally:
        session.close()

    log_admin_activity(
        update.effective_user.id,
        update.effective_user.username,
        "admin_added",
        f"ادمین جدید با آیدی {new_telegram_id} اضافه کرد",
    )
    await update.message.reply_text(
        f"✅ ادمین جدید با آیدی {new_telegram_id} اضافه شد.", reply_markup=main_reply_keyboard(True)
    )
    try:
        await context.bot.send_message(
            chat_id=new_telegram_id,
            text="🎉 شما توسط ادمین ارشد به‌عنوان ادمین ربات اضافه شدید.\nبرای مشاهده پنل مدیریت، /start را بزنید.",
        )
    except Exception:
        pass
    return ConversationHandler.END


async def admin_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("افزودن ادمین لغو شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


def build_admin_add_conversation() -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", admin_add_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), admin_add_cancel),
    ]
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_start, pattern="^admin_add_new$")],
        states={
            ADD_ADMIN_ID: [*cancel_handlers, MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_receive_id)],
        },
        fallbacks=cancel_handlers,
    )


# --- حذف ادمین ---


async def admin_remove_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_senior_admin(query.from_user.id):
        await query.edit_message_text("⛔️ فقط ادمین ارشد می‌تواند ادمین حذف کند.")
        return

    admin_id = context.match.group("admin_id")
    session = get_session()
    try:
        target = session.query(Admin).filter_by(id=admin_id).first()
        if target is None:
            await query.edit_message_text("این ادمین یافت نشد.")
            return
        if target.role == AdminRole.SENIOR:
            await query.answer("نمی‌توانید ادمین ارشد را حذف کنید؛ ابتدا ارشدیت را منتقل کنید.", show_alert=True)
            return
        name = _admin_display_name(target)
    finally:
        session.close()

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"admin_remove_confirm_{admin_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data="admin_manage_admins")],
        ]
    )
    await query.edit_message_text(f"آیا از حذف {name} از لیست ادمین‌ها مطمئن هستید؟", reply_markup=keyboard)


async def admin_remove_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_senior_admin(query.from_user.id):
        await query.edit_message_text("⛔️ فقط ادمین ارشد می‌تواند ادمین حذف کند.")
        return

    admin_id = context.match.group("admin_id")
    session = get_session()
    try:
        target = session.query(Admin).filter_by(id=admin_id).first()
        if target is None or target.role == AdminRole.SENIOR:
            await query.edit_message_text("این عملیات دیگر ممکن نیست.")
            return
        removed_telegram_id = target.telegram_id
        name = _admin_display_name(target)
        _detach_admin_references(session, target.id)
        session.delete(target)
        session.commit()
    except Exception:
        session.rollback()
        await query.edit_message_text("⚠️ خطایی هنگام حذف رخ داد. دوباره تلاش کنید.")
        return
    finally:
        session.close()

    log_admin_activity(query.from_user.id, query.from_user.username, "admin_removed", f"{name} را از ادمین‌ها حذف کرد")
    await query.edit_message_text(f"✅ {name} از لیست ادمین‌ها حذف شد.")
    try:
        await context.bot.send_message(chat_id=removed_telegram_id, text="دسترسی مدیریتی شما در ربات لغو شد.")
    except Exception:
        pass


# --- انتقال ارشدیت و کناره‌گیری ---


async def admin_transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_senior_admin(query.from_user.id):
        await query.edit_message_text("⛔️ فقط ادمین ارشد می‌تواند ارشدیت را منتقل کند.")
        return

    admins = [a for a in list_admins() if a.telegram_id != query.from_user.id]
    if not admins:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_manage_admins")]])
        await query.edit_message_text(
            "ابتدا حداقل یک ادمین دیگر اضافه کنید تا بتوانید ارشدیت را به او منتقل کنید.",
            reply_markup=keyboard,
        )
        return

    buttons = [
        [InlineKeyboardButton(_admin_display_name(a), callback_data=f"admin_transfer_pick_{a.id}")] for a in admins
    ]
    buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_manage_admins")])
    await query.edit_message_text(
        "ارشدیت به کدام ادمین منتقل شود؟ (پس از انتقال، شما دیگر ادمین نخواهید بود)",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_transfer_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_senior_admin(query.from_user.id):
        await query.edit_message_text("⛔️ فقط ادمین ارشد می‌تواند ارشدیت را منتقل کند.")
        return

    admin_id = context.match.group("admin_id")
    session = get_session()
    try:
        target = session.query(Admin).filter_by(id=admin_id).first()
        if target is None:
            await query.edit_message_text("این ادمین یافت نشد.")
            return
        name = _admin_display_name(target)
    finally:
        session.close()

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ بله، ارشدیت را منتقل کن", callback_data=f"admin_transfer_execute_{admin_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data="admin_manage_admins")],
        ]
    )
    await query.edit_message_text(
        f"آیا مطمئن هستید می‌خواهید ارشدیت را به {name} منتقل کنید؟ شما به ادمین عادی تنزل پیدا می‌کنید "
        "(همچنان ادمین باقی می‌مانید، فقط دیگر دسترسی ارشد نخواهید داشت).",
        reply_markup=keyboard,
    )


async def admin_transfer_execute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_senior_admin(query.from_user.id):
        await query.edit_message_text("⛔️ فقط ادمین ارشد می‌تواند ارشدیت را منتقل کند.")
        return

    admin_id = context.match.group("admin_id")
    session = get_session()
    try:
        target = session.query(Admin).filter_by(id=admin_id).first()
        requester = session.query(Admin).filter_by(telegram_id=query.from_user.id).first()
        if target is None or requester is None:
            await query.edit_message_text("این عملیات دیگر ممکن نیست.")
            return

        target.role = AdminRole.SENIOR
        requester.role = AdminRole.ADMIN
        target_telegram_id = target.telegram_id
        target_name = _admin_display_name(target)
        session.commit()
    except Exception:
        session.rollback()
        await query.edit_message_text("⚠️ خطایی هنگام انتقال ارشدیت رخ داد. دوباره تلاش کنید.")
        return
    finally:
        session.close()

    log_admin_activity(
        query.from_user.id, query.from_user.username, "admin_transferred", f"ارشدیت را به {target_name} منتقل کرد"
    )
    await query.edit_message_text(f"✅ ارشدیت به {target_name} منتقل شد. شما اکنون ادمین عادی هستید.")
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="از همکاری شما در دوران ارشدیت سپاسگزاریم 🙏 همچنان به‌عنوان ادمین عادی در دسترسید.",
        reply_markup=main_reply_keyboard(True),
    )
    try:
        await context.bot.send_message(
            chat_id=target_telegram_id, text="🎉 شما اکنون ادمین ارشد ربات انجمن علمی شیمی هستید."
        )
    except Exception:
        pass
