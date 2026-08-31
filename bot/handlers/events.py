"""
هندلرهای بخش رویدادها:

کاربر:
- مشاهده رویدادهای فعال و جزئیات هرکدام (ظرفیت باقی‌مانده، هزینه، زمان، توضیحات)
- ثبت‌نام با پر کردن فیلدهای پویایی که ادمین برای آن رویداد تعریف کرده
- مشاهده شماره کارت و آپلود فیش واریزی برای رویدادهای غیررایگان (رویدادهای رایگان
  خودکار تایید می‌شوند)
- دریافت کد پیگیری و مشاهده وضعیت ثبت‌نام
- لغو ثبت‌نام (فقط تا قبل از تایید ادمین) و امکان ثبت‌نام دوباره بعد از لغو/رد

ادمین:
- افزودن رویداد جدید + شماره کارت + انتخاب فیلدهای موردنیاز از یک فهرست از پیش
  تعریف‌شده
- مشاهده لیست رویدادها، ویرایش هرکدام (عنوان/توضیحات/ظرفیت/هزینه/شماره کارت/تاریخ)
- لغو رویداد (با ارسال پیام دلخواه به همه ثبت‌نام‌کنندگان فعال) یا حذف کامل آن
- تایید/رد فیش‌های واریزی در انتظار بررسی (با نوتیف فوری به همه ادمین‌ها هنگام
  رسیدن فیش جدید)
"""
import asyncio
import random
import re
import string
from datetime import datetime

import jdatetime
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
from bot.notifications import broadcast_to_all_users, try_promote_waitlist
from database.db import get_session
from database.models import (
    Admin,
    Event,
    EventField,
    FieldType,
    Registration,
    RegistrationFieldValue,
    RegistrationStatus,
    UserAccount,
)

# --- فهرست از پیش تعریف‌شده فیلدهای ثبت‌نام ---
# ادمین هنگام ساخت رویداد از بین این‌ها انتخاب می‌کند که کدام‌ها موردنیازند.
FIELD_CATALOG = [
    ("first_name", "نام", FieldType.TEXT),
    ("last_name", "نام خانوادگی", FieldType.TEXT),
    ("student_code", "کد دانشجویی", FieldType.TEXT),
    ("national_id", "کد ملی", FieldType.TEXT),
    ("major", "رشته", FieldType.TEXT),
    ("entry_year", "سال ورودی", FieldType.NUMBER),
    ("phone", "شماره تماس", FieldType.PHONE),
]
FIELD_LABELS = {key: label for key, label, _ in FIELD_CATALOG}
FIELD_TYPES = {key: ftype for key, _, ftype in FIELD_CATALOG}

STATUS_LABELS = {
    RegistrationStatus.PENDING: "⏳ در انتظار بررسی",
    RegistrationStatus.APPROVED: "✅ تایید شده",
    RegistrationStatus.REJECTED: "❌ رد شده",
    RegistrationStatus.WAITLISTED: "🕒 در لیست انتظار",
    RegistrationStatus.CANCELLED: "🚫 لغو شده",
}

# وضعیت‌هایی که یعنی کاربر "همین الان" یک ثبت‌نام فعال دارد و نباید دوباره ثبت‌نام کند
ACTIVE_STATUSES = (RegistrationStatus.PENDING, RegistrationStatus.APPROVED, RegistrationStatus.WAITLISTED)

# فرمت تاریخ ورودی: هم میلادی هم شمسی، با - یا / بین اجزا
_DATE_PATTERN = re.compile(r"^(\d{3,4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2})$")


def _parse_event_datetime(text: str):
    """هم فرمت میلادی و هم شمسی را می‌فهمد — بر اساس عدد سال تشخیص می‌دهد کدام است
    (سال‌های شمسی فعلی حدود ۱۴۰۰ هستند و میلادی همیشه بالای ۱۵۰۰). اگر فرمت اصلاً
    قابل‌فهم نباشد None برمی‌گرداند تا خطای واضح به ادمین نشان داده شود (نه سکوت)."""
    match = _DATE_PATTERN.match(text.strip())
    if not match:
        return None

    year, month, day, hour, minute = (int(g) for g in match.groups())
    try:
        if year < 1500:
            return jdatetime.datetime(year, month, day, hour, minute).togregorian()
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


# --- کوئری‌های کمکی ---


def list_active_events():
    session = get_session()
    try:
        return session.query(Event).filter_by(is_active=True).order_by(Event.created_at.desc()).all()
    finally:
        session.close()


def list_all_events():
    session = get_session()
    try:
        return session.query(Event).order_by(Event.created_at.desc()).all()
    finally:
        session.close()


def get_event_by_id(event_id: str):
    session = get_session()
    try:
        return session.query(Event).filter_by(id=event_id).first()
    finally:
        session.close()


def get_event_fields(event_id: str):
    session = get_session()
    try:
        return session.query(EventField).filter_by(event_id=event_id).order_by(EventField.display_order).all()
    finally:
        session.close()


def count_taken_spots(event_id: str) -> int:
    session = get_session()
    try:
        return (
            session.query(Registration)
            .filter(
                Registration.event_id == event_id,
                Registration.status.in_([RegistrationStatus.PENDING, RegistrationStatus.APPROVED]),
            )
            .count()
        )
    finally:
        session.close()


def get_latest_user_registration(event_id: str, telegram_id: int):
    """آخرین ثبت‌نام این کاربر برای این رویداد را برمی‌گرداند (صرف‌نظر از وضعیت) —
    برای تشخیص اینکه آیا کاربر ثبت‌نام فعال دارد یا می‌تواند دوباره ثبت‌نام کند."""
    session = get_session()
    try:
        user = session.query(UserAccount).filter_by(telegram_id=telegram_id).first()
        if user is None:
            return None
        return (
            session.query(Registration)
            .filter_by(event_id=event_id, user_id=user.id)
            .order_by(Registration.submitted_at.desc())
            .first()
        )
    finally:
        session.close()


def _generate_tracking_code() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"REG-{suffix}"


# --- منوی کاربر: لیست و جزئیات رویداد ---


def _events_list_view():
    events = list_active_events()
    if not events:
        text = "📅 در حال حاضر رویداد فعالی وجود ندارد."
        return text, None

    buttons = [[InlineKeyboardButton(e.title, callback_data=f"event_view_{e.id}")] for e in events]
    return "📅 رویدادهای فعال:", InlineKeyboardMarkup(buttons)


async def events_menu_text_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, keyboard = _events_list_view()
    await update.message.reply_text(text, reply_markup=keyboard)


async def event_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    text, keyboard = _events_list_view()
    await query.edit_message_text(text, reply_markup=keyboard)


def _event_detail_view(event: Event, telegram_id: int):
    taken = count_taken_spots(event.id)
    remaining = event.capacity - taken

    lines = [f"📅 {event.title}"]
    if event.description:
        lines.extend(["", event.description])
    lines.append("")
    lines.append(f"💰 هزینه: {'رایگان' if not event.price else f'{int(event.price):,} تومان'}")
    if event.event_date:
        lines.append(f"🗓 زمان برگزاری: {event.event_date.strftime('%Y-%m-%d %H:%M')}")
    if remaining > 0:
        lines.append(f"🪑 ظرفیت باقی‌مانده: {remaining} از {event.capacity}")
    else:
        lines.append("🪑 ظرفیت تکمیل شده — ثبت‌نام شما در لیست انتظار قرار می‌گیرد.")

    existing = get_latest_user_registration(event.id, telegram_id)
    buttons = []
    if existing is None or existing.status not in ACTIVE_STATUSES:
        if existing is not None:
            lines.append("")
            lines.append(
                f"ثبت‌نام قبلی شما: {STATUS_LABELS.get(existing.status, existing.status)} — می‌توانید دوباره ثبت‌نام کنید."
            )
        buttons.append([InlineKeyboardButton("📝 ثبت‌نام", callback_data=f"event_register_{event.id}")])
    else:
        lines.append("")
        lines.append(f"وضعیت ثبت‌نام شما: {STATUS_LABELS.get(existing.status, existing.status)}")
        lines.append(f"کد پیگیری: {existing.tracking_code}")
        if existing.status in (RegistrationStatus.PENDING, RegistrationStatus.WAITLISTED):
            buttons.append([InlineKeyboardButton("❌ لغو ثبت‌نام", callback_data=f"event_cancel_{existing.id}")])

    buttons.append([InlineKeyboardButton("⬅️ بازگشت به لیست رویدادها", callback_data="event_list")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def event_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    event_id = context.match.group("event_id")
    event = get_event_by_id(event_id)
    if event is None:
        await query.edit_message_text("این رویداد یافت نشد.")
        return

    text, keyboard = _event_detail_view(event, query.from_user.id)
    await query.edit_message_text(text, reply_markup=keyboard)


async def event_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    registration_id = context.match.group("registration_id")
    session = get_session()
    try:
        registration = session.query(Registration).filter_by(id=registration_id).first()
        if registration is None:
            await query.edit_message_text("این ثبت‌نام یافت نشد.")
            return
        if registration.status not in (RegistrationStatus.PENDING, RegistrationStatus.WAITLISTED):
            await query.answer("این ثبت‌نام قابل لغو نیست.", show_alert=True)
            return
        registration.status = RegistrationStatus.CANCELLED
        event_id = registration.event_id
        session.commit()
    finally:
        session.close()

    event = get_event_by_id(event_id)
    text, keyboard = _event_detail_view(event, query.from_user.id)
    await query.edit_message_text("✅ ثبت‌نام شما لغو شد.\n\n" + text, reply_markup=keyboard)
    await try_promote_waitlist(context.bot, event_id)


# --- گفتگوی ثبت‌نام در رویداد ---

REG_COLLECTING, REG_RECEIPT = range(2)


async def event_register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    event_id = context.match.group("event_id")
    event = get_event_by_id(event_id)
    if event is None or not event.is_active:
        await query.edit_message_text("این رویداد یافت نشد یا غیرفعال است.")
        return ConversationHandler.END

    existing = get_latest_user_registration(event_id, query.from_user.id)
    if existing is not None and existing.status in ACTIVE_STATUSES:
        await query.answer("شما در حال حاضر برای این رویداد ثبت‌نام فعال دارید.", show_alert=True)
        return ConversationHandler.END

    fields = get_event_fields(event_id)
    context.user_data["reg"] = {
        "event_id": event_id,
        "answers": {},
        "field_queue": [(f.id, f.field_label, f.field_type) for f in fields],
        "requires_payment": bool(event.price),
        "card_number": event.card_number,
        "price": event.price,
    }

    await query.edit_message_text(f"📝 در حال ثبت‌نام برای «{event.title}»...")
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="برای انصراف در هر لحظه، دکمه «❌ انصراف» را بزنید.",
        reply_markup=cancel_reply_keyboard(),
    )

    if not fields:
        return await _proceed_after_fields(update, context)

    first_label = fields[0].field_label
    await context.bot.send_message(chat_id=query.from_user.id, text=f"{first_label} را وارد کنید:")
    return REG_COLLECTING


async def _proceed_after_fields(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reg = context.user_data["reg"]
    chat_id = update.effective_user.id
    if reg["requires_payment"]:
        price_text = f"{int(reg['price']):,} تومان" if reg.get("price") else ""
        card = reg.get("card_number")
        if card:
            text = (
                f"💳 لطفاً مبلغ {price_text} را به شماره کارت زیر واریز کنید:\n\n{card}\n\n"
                "سپس تصویر یا فایل فیش واریزی را همینجا ارسال کنید."
            )
        else:
            text = f"لطفاً مبلغ {price_text} را واریز کرده و سپس تصویر یا فایل فیش واریزی را ارسال کنید."
        await context.bot.send_message(chat_id=chat_id, text=text)
        return REG_RECEIPT
    return await _finalize_registration(update, context, receipt_file_id=None)


async def reg_collect_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reg = context.user_data.get("reg")
    if not reg or not reg["field_queue"]:
        return ConversationHandler.END

    field_id, label, field_type = reg["field_queue"][0]
    value = (update.message.text or "").strip()

    if field_type in (FieldType.NUMBER, FieldType.PHONE) and not value.replace("+", "").isdigit():
        await update.message.reply_text(f"لطفاً {label} را فقط با عدد وارد کنید.")
        return REG_COLLECTING

    if not value:
        await update.message.reply_text("این فیلد نمی‌تواند خالی باشد.")
        return REG_COLLECTING

    reg["answers"][field_id] = value
    reg["field_queue"].pop(0)

    if reg["field_queue"]:
        next_label = reg["field_queue"][0][1]
        await update.message.reply_text(f"{next_label} را وارد کنید:")
        return REG_COLLECTING

    return await _proceed_after_fields(update, context)


async def reg_receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file_id = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id

    if file_id is None:
        await update.message.reply_text("لطفاً تصویر یا فایل فیش واریزی را ارسال کنید.")
        return REG_RECEIPT

    return await _finalize_registration(update, context, receipt_file_id=file_id)


async def _finalize_registration(update: Update, context: ContextTypes.DEFAULT_TYPE, receipt_file_id):
    reg = context.user_data["reg"]
    tg_user = update.effective_user

    session = get_session()
    try:
        user = session.query(UserAccount).filter_by(telegram_id=tg_user.id).first()
        if user is None:
            user = UserAccount(telegram_id=tg_user.id, username=tg_user.username, full_name=tg_user.full_name)
            session.add(user)
            session.flush()

        event = session.query(Event).filter_by(id=reg["event_id"]).first()
        taken = (
            session.query(Registration)
            .filter(
                Registration.event_id == event.id,
                Registration.status.in_([RegistrationStatus.PENDING, RegistrationStatus.APPROVED]),
            )
            .count()
        )
        is_full = taken >= event.capacity

        if is_full:
            status = RegistrationStatus.WAITLISTED
        elif not reg["requires_payment"]:
            status = RegistrationStatus.APPROVED
        else:
            status = RegistrationStatus.PENDING

        registration = Registration(
            event_id=event.id,
            user_id=user.id,
            tracking_code=_generate_tracking_code(),
            status=status,
            receipt_file_url=receipt_file_id,
        )
        session.add(registration)
        session.flush()

        for field_id, value in reg["answers"].items():
            session.add(
                RegistrationFieldValue(registration_id=registration.id, event_field_id=field_id, value=value)
            )

        session.commit()
        tracking_code = registration.tracking_code
        final_status = registration.status
        registration_id = registration.id
        event_title = event.title
        admin_ids = [a.telegram_id for a in session.query(Admin).all()]
    finally:
        session.close()

    context.user_data.pop("reg", None)

    status_text = STATUS_LABELS.get(final_status, final_status)
    await update.effective_message.reply_text(
        f"✅ ثبت‌نام شما ثبت شد.\nکد پیگیری: {tracking_code}\nوضعیت: {status_text}",
        reply_markup=main_reply_keyboard(is_admin_telegram_id(update.effective_user.id)),
    )

    if final_status == RegistrationStatus.PENDING:
        notify_keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🧾 بررسی فیش", callback_data=f"admin_receipt_view_{registration_id}")]]
        )
        for admin_telegram_id in admin_ids:
            try:
                await context.bot.send_message(
                    chat_id=admin_telegram_id,
                    text=f"🧾 فیش جدیدی در انتظار بررسی است.\n\nرویداد: {event_title}\nکد پیگیری: {tracking_code}",
                    reply_markup=notify_keyboard,
                )
            except Exception:
                pass

    return ConversationHandler.END


async def event_register_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("reg", None)
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("ثبت‌نام لغو شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


def build_event_registration_conversation() -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", event_register_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), event_register_cancel),
    ]
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(event_register_start, pattern=r"^event_register_(?P<event_id>.+)$")],
        states={
            REG_COLLECTING: [*cancel_handlers, MessageHandler(filters.TEXT & ~filters.COMMAND, reg_collect_field)],
            REG_RECEIPT: [
                *cancel_handlers,
                MessageHandler(filters.PHOTO | filters.Document.ALL, reg_receive_receipt),
            ],
        },
        fallbacks=cancel_handlers,
    )


# --- مدیریت رویدادها توسط ادمین ---


async def admin_events_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    buttons = [
        [InlineKeyboardButton("➕ افزودن رویداد جدید", callback_data="admin_event_add")],
        [InlineKeyboardButton("📋 لیست رویدادها", callback_data="admin_event_list")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_menu")],
    ]
    await query.edit_message_text("📅 مدیریت رویدادها:", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_event_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    events = list_all_events()
    if not events:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_events")]])
        await query.edit_message_text("هنوز هیچ رویدادی ثبت نشده است.", reply_markup=keyboard)
        return

    buttons = []
    for e in events:
        taken = count_taken_spots(e.id)
        status = "فعال" if e.is_active else "غیرفعال/لغوشده"
        buttons.append(
            [InlineKeyboardButton(f"{e.title} — {taken}/{e.capacity} ({status})", callback_data=f"admin_event_detail_{e.id}")]
        )
    buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_events")])
    await query.edit_message_text("📋 روی هر رویداد بزنید تا مدیریتش کنید:", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_event_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    event_id = context.match.group("event_id")
    session = get_session()
    try:
        event = session.query(Event).filter_by(id=event_id).first()
        if event is None:
            await query.edit_message_text("این رویداد یافت نشد.")
            return
        status_counts = {
            status: session.query(Registration).filter_by(event_id=event_id, status=status).count()
            for status in RegistrationStatus
        }
        title, description = event.title, event.description
        capacity, price, card_number = event.capacity, event.price, event.card_number
        event_date, is_active = event.event_date, event.is_active
    finally:
        session.close()

    lines = [f"📅 {title}", ""]
    if description:
        lines.append(description)
        lines.append("")
    lines.append(f"وضعیت: {'فعال' if is_active else 'غیرفعال/لغوشده'}")
    lines.append(f"ظرفیت: {capacity}")
    lines.append(f"هزینه: {'رایگان' if not price else f'{int(price):,} تومان'}")
    if card_number:
        lines.append(f"شماره کارت: {card_number}")
    if event_date:
        lines.append(f"زمان برگزاری: {event_date.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("📋 ثبت‌نام‌ها:")
    for status, count in status_counts.items():
        lines.append(f"  • {STATUS_LABELS.get(status, status)}: {count}")

    buttons = [
        [
            InlineKeyboardButton("✏️ عنوان", callback_data=f"admin_event_edit_title_{event_id}"),
            InlineKeyboardButton("✏️ توضیحات", callback_data=f"admin_event_edit_description_{event_id}"),
        ],
        [
            InlineKeyboardButton("✏️ ظرفیت", callback_data=f"admin_event_edit_capacity_{event_id}"),
            InlineKeyboardButton("✏️ هزینه", callback_data=f"admin_event_edit_price_{event_id}"),
        ],
        [
            InlineKeyboardButton("✏️ شماره کارت", callback_data=f"admin_event_edit_card_{event_id}"),
            InlineKeyboardButton("✏️ تاریخ", callback_data=f"admin_event_edit_date_{event_id}"),
        ],
    ]
    if is_active:
        buttons.append([InlineKeyboardButton("🚫 لغو رویداد", callback_data=f"admin_event_cancelev_{event_id}")])
    buttons.append([InlineKeyboardButton("🗑 حذف کامل رویداد", callback_data=f"admin_event_delask_{event_id}")])
    buttons.append([InlineKeyboardButton("⬅️ بازگشت به لیست", callback_data="admin_event_list")])

    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


ADD_TITLE, ADD_DESCRIPTION, ADD_CAPACITY, ADD_PRICE, ADD_CARD_NUMBER, ADD_DATE, ADD_FIELDS = range(7)


async def admin_event_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return ConversationHandler.END

    context.user_data["new_event"] = {}
    await query.edit_message_text("📅 در حال افزودن رویداد جدید...")
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="عنوان رویداد را وارد کنید:",
        reply_markup=cancel_reply_keyboard(),
    )
    return ADD_TITLE


async def admin_event_receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_event"]["title"] = update.message.text.strip()
    await update.message.reply_text("توضیحات رویداد را بنویسید (اگر توضیحی نیست، - بفرستید):")
    return ADD_DESCRIPTION


async def admin_event_receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["new_event"]["description"] = None if text == "-" else text
    await update.message.reply_text("ظرفیت رویداد چند نفر است؟ (فقط عدد)")
    return ADD_CAPACITY


async def admin_event_receive_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("لطفاً یک عدد صحیح بزرگ‌تر از صفر بفرستید.")
        return ADD_CAPACITY
    context.user_data["new_event"]["capacity"] = int(text)
    await update.message.reply_text("هزینه ثبت‌نام به تومان چقدر است؟ برای رویداد رایگان - بفرستید.")
    return ADD_PRICE


async def admin_event_receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "-":
        context.user_data["new_event"]["price"] = None
        context.user_data["new_event"]["card_number"] = None
        await update.message.reply_text(
            "تاریخ و ساعت برگزاری را بفرستید:\n"
            "• میلادی: 2026-09-20 18:00\n"
            "• شمسی: 1404-06-29 18:00\n"
            "یا برای رد کردن این مرحله، - بفرستید."
        )
        return ADD_DATE
    if not text.isdigit():
        await update.message.reply_text("لطفاً فقط عدد بفرستید یا برای رایگان بودن - بفرستید.")
        return ADD_PRICE

    context.user_data["new_event"]["price"] = int(text)
    await update.message.reply_text("شماره کارتی که کاربر باید مبلغ را به آن واریز کند را بفرستید:")
    return ADD_CARD_NUMBER


async def admin_event_receive_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("لطفاً شماره کارت را بفرستید.")
        return ADD_CARD_NUMBER

    context.user_data["new_event"]["card_number"] = text
    await update.message.reply_text(
        "تاریخ و ساعت برگزاری را بفرستید:\n"
        "• میلادی: 2026-09-20 18:00\n"
        "• شمسی: 1404-06-29 18:00\n"
        "یا برای رد کردن این مرحله، - بفرستید."
    )
    return ADD_DATE


async def admin_event_receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == "-":
        context.user_data["new_event"]["event_date"] = None
    else:
        parsed = _parse_event_datetime(text)
        if parsed is None:
            await update.message.reply_text(
                "متوجه این فرمت تاریخ نشدم. لطفاً به یکی از این شکل‌ها بفرستید:\n"
                "• میلادی: 2026-09-20 18:00\n"
                "• شمسی: 1404-06-29 18:00\n"
                "یا برای رد کردن این مرحله (بدون یادآوری خودکار)، - بفرستید."
            )
            return ADD_DATE
        context.user_data["new_event"]["event_date"] = parsed

    context.user_data["new_event"]["selected_fields"] = set()
    keyboard = _build_field_selection_keyboard(set())
    await update.message.reply_text(
        "کدام اطلاعات از ثبت‌نام‌کننده لازم است؟ روی گزینه‌ها بزنید تا انتخاب/لغو شوند، "
        "و در پایان «✅ تایید و ساخت رویداد» را بزنید:",
        reply_markup=keyboard,
    )
    return ADD_FIELDS


def _build_field_selection_keyboard(selected: set) -> InlineKeyboardMarkup:
    buttons = []
    for key, label, _ in FIELD_CATALOG:
        mark = "☑️" if key in selected else "⬜️"
        buttons.append([InlineKeyboardButton(f"{mark} {label}", callback_data=f"eventfield_toggle_{key}")])
    buttons.append([InlineKeyboardButton("✅ تایید و ساخت رویداد", callback_data="eventfield_confirm")])
    return InlineKeyboardMarkup(buttons)


async def admin_event_toggle_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    key = context.match.group("key")
    selected = context.user_data.setdefault("new_event", {}).setdefault("selected_fields", set())
    if key in selected:
        selected.discard(key)
    else:
        selected.add(key)

    await query.edit_message_reply_markup(reply_markup=_build_field_selection_keyboard(selected))
    return ADD_FIELDS


async def admin_event_confirm_fields(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = context.user_data.get("new_event", {})

    session = get_session()
    try:
        admin_row = session.query(Admin).filter_by(telegram_id=query.from_user.id).first()
        event = Event(
            title=data["title"],
            description=data.get("description"),
            capacity=data["capacity"],
            price=data.get("price"),
            card_number=data.get("card_number"),
            event_date=data.get("event_date"),
            created_by_admin_id=admin_row.id if admin_row else None,
        )
        session.add(event)
        session.flush()

        for order, key in enumerate(data.get("selected_fields", [])):
            session.add(
                EventField(
                    event_id=event.id,
                    field_key=key,
                    field_label=FIELD_LABELS[key],
                    field_type=FIELD_TYPES[key],
                    is_required=True,
                    display_order=order,
                )
            )
        session.commit()
        title = event.title
    finally:
        session.close()

    context.user_data.pop("new_event", None)
    await query.edit_message_text(f"✅ رویداد «{title}» با موفقیت ساخته شد.")
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="می‌توانید از منوی پایین صفحه ادامه دهید.",
        reply_markup=main_reply_keyboard(True),
    )
    await broadcast_to_all_users(
        context.bot,
        f"📅 رویداد جدید اضافه شد: «{title}»\n\nبرای مشاهده جزئیات و ثبت‌نام، از منوی «📅 رویدادها» استفاده کنید.",
    )
    return ConversationHandler.END


async def admin_event_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("new_event", None)
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("افزودن رویداد لغو شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


def build_admin_event_add_conversation() -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", admin_event_add_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), admin_event_add_cancel),
    ]
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_event_add_start, pattern="^admin_event_add$")],
        states={
            ADD_TITLE: [*cancel_handlers, MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_receive_title)],
            ADD_DESCRIPTION: [
                *cancel_handlers,
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_receive_description),
            ],
            ADD_CAPACITY: [
                *cancel_handlers,
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_receive_capacity),
            ],
            ADD_PRICE: [*cancel_handlers, MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_receive_price)],
            ADD_CARD_NUMBER: [
                *cancel_handlers,
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_receive_card_number),
            ],
            ADD_DATE: [*cancel_handlers, MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_receive_date)],
            ADD_FIELDS: [
                *cancel_handlers,
                CallbackQueryHandler(admin_event_toggle_field, pattern=r"^eventfield_toggle_(?P<key>.+)$"),
                CallbackQueryHandler(admin_event_confirm_fields, pattern="^eventfield_confirm$"),
            ],
        },
        fallbacks=cancel_handlers,
    )


# --- ویرایش رویداد موجود (گفتگوی تک‌فیلدی) ---

EVENT_EDIT_PROMPTS = {
    "title": "عنوان جدید را بفرستید:",
    "description": "توضیحات جدید را بفرستید (برای خالی‌کردن، - بفرستید):",
    "capacity": "ظرفیت جدید را بفرستید (فقط عدد):",
    "price": "هزینه جدید را بفرستید (فقط عدد، یا برای رایگان‌کردن - بفرستید):",
    "card": "شماره کارت جدید را بفرستید (برای حذف، - بفرستید):",
    "date": (
        "تاریخ و ساعت جدید را بفرستید:\n"
        "• میلادی: 2026-09-20 18:00\n"
        "• شمسی: 1404-06-29 18:00\n"
        "یا برای حذف تاریخ، - بفرستید."
    ),
}

WAITING_EVENT_EDIT_VALUE = 0


async def admin_event_edit_field_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return ConversationHandler.END

    field, event_id = context.match.group("field"), context.match.group("event_id")
    context.user_data["editing_event"] = {"event_id": event_id, "field": field}
    await query.edit_message_text("✏️ در حال ویرایش رویداد...")
    await context.bot.send_message(
        chat_id=query.from_user.id, text=EVENT_EDIT_PROMPTS[field], reply_markup=cancel_reply_keyboard()
    )
    return WAITING_EVENT_EDIT_VALUE


async def admin_event_edit_receive_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    editing = context.user_data.get("editing_event")
    if not editing:
        return ConversationHandler.END

    field, event_id = editing["field"], editing["event_id"]
    text = update.message.text.strip()
    capacity_increased = False

    session = get_session()
    try:
        event = session.query(Event).filter_by(id=event_id).first()
        if event is None:
            await update.message.reply_text("این رویداد دیگر وجود ندارد.", reply_markup=main_reply_keyboard(True))
            context.user_data.pop("editing_event", None)
            return ConversationHandler.END

        if field == "title":
            if not text:
                await update.message.reply_text("عنوان نمی‌تواند خالی باشد.")
                return WAITING_EVENT_EDIT_VALUE
            event.title = text
        elif field == "description":
            event.description = None if text == "-" else text
        elif field == "capacity":
            if not text.isdigit() or int(text) <= 0:
                await update.message.reply_text("لطفاً یک عدد صحیح بزرگ‌تر از صفر بفرستید.")
                return WAITING_EVENT_EDIT_VALUE
            new_capacity = int(text)
            capacity_increased = new_capacity > event.capacity
            event.capacity = new_capacity
        elif field == "price":
            if text == "-":
                event.price = None
            elif text.isdigit():
                event.price = int(text)
            else:
                await update.message.reply_text("لطفاً فقط عدد بفرستید یا - برای رایگان‌کردن.")
                return WAITING_EVENT_EDIT_VALUE
        elif field == "card":
            event.card_number = None if text == "-" else text
        elif field == "date":
            if text == "-":
                event.event_date = None
            else:
                parsed = _parse_event_datetime(text)
                if parsed is None:
                    await update.message.reply_text(
                        "متوجه این فرمت تاریخ نشدم. مثال میلادی: 2026-09-20 18:00 — مثال شمسی: 1404-06-29 18:00"
                    )
                    return WAITING_EVENT_EDIT_VALUE
                event.event_date = parsed

        session.commit()
    finally:
        session.close()

    context.user_data.pop("editing_event", None)
    await update.message.reply_text("✅ تغییرات ذخیره شد.", reply_markup=main_reply_keyboard(True))

    if capacity_increased:
        await try_promote_waitlist(context.bot, event_id)

    return ConversationHandler.END


async def admin_event_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("editing_event", None)
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text("ویرایش لغو شد.", reply_markup=main_reply_keyboard(admin))
    return ConversationHandler.END


def build_event_edit_conversation() -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", admin_event_edit_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), admin_event_edit_cancel),
    ]
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_event_edit_field_start,
                pattern=r"^admin_event_edit_(?P<field>title|description|capacity|price|card|date)_(?P<event_id>.+)$",
            )
        ],
        states={
            WAITING_EVENT_EDIT_VALUE: [
                *cancel_handlers,
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_edit_receive_value),
            ],
        },
        fallbacks=cancel_handlers,
    )


# --- حذف کامل رویداد ---


async def admin_event_delete_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    event_id = context.match.group("event_id")
    session = get_session()
    try:
        event = session.query(Event).filter_by(id=event_id).first()
        if event is None:
            await query.edit_message_text("این رویداد یافت نشد.")
            return
        reg_count = session.query(Registration).filter_by(event_id=event_id).count()
        title = event.title
    finally:
        session.close()

    warning = f"\n\n⚠️ این رویداد {reg_count} ثبت‌نام دارد که همراه آن حذف خواهند شد." if reg_count else ""
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ بله، کاملاً حذف کن", callback_data=f"admin_event_delyes_{event_id}")],
            [InlineKeyboardButton("❌ انصراف", callback_data=f"admin_event_detail_{event_id}")],
        ]
    )
    await query.edit_message_text(f"آیا از حذف کامل «{title}» مطمئن هستید؟{warning}", reply_markup=keyboard)


async def admin_event_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    event_id = context.match.group("event_id")
    session = get_session()
    try:
        event = session.query(Event).filter_by(id=event_id).first()
        if event is None:
            await query.edit_message_text("این رویداد قبلاً حذف شده است.")
            return
        title = event.title
        session.delete(event)  # cascade به event_fields / registrations / registration_field_values
        session.commit()
    finally:
        session.close()

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت به لیست", callback_data="admin_event_list")]])
    await query.edit_message_text(f"✅ رویداد «{title}» به‌طور کامل حذف شد.", reply_markup=keyboard)


# --- لغو رویداد (با پیام به ثبت‌نام‌کنندگان) ---

WAITING_CANCEL_EVENT_MESSAGE = 0


async def admin_event_cancelev_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return ConversationHandler.END

    event_id = context.match.group("event_id")
    context.user_data["cancelling_event"] = event_id
    await query.edit_message_text("🚫 در حال لغو رویداد...")
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="متن پیامی که برای همه ثبت‌نام‌کنندگان فعال این رویداد ارسال شود را بنویسید (دلیل لغو):",
        reply_markup=cancel_reply_keyboard(),
    )
    return WAITING_CANCEL_EVENT_MESSAGE


async def admin_event_cancelev_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event_id = context.user_data.get("cancelling_event")
    if not event_id:
        return ConversationHandler.END

    message_text = update.message.text.strip()
    session = get_session()
    try:
        event = session.query(Event).filter_by(id=event_id).first()
        if event is None:
            await update.message.reply_text("این رویداد یافت نشد.", reply_markup=main_reply_keyboard(True))
            context.user_data.pop("cancelling_event", None)
            return ConversationHandler.END

        event.is_active = False
        affected = (
            session.query(Registration)
            .filter(Registration.event_id == event_id, Registration.status.in_(ACTIVE_STATUSES))
            .all()
        )
        recipients = []
        for reg in affected:
            user = session.query(UserAccount).filter_by(id=reg.user_id).first()
            if user:
                recipients.append(user.telegram_id)
            reg.status = RegistrationStatus.CANCELLED

        title = event.title
        session.commit()
    finally:
        session.close()

    context.user_data.pop("cancelling_event", None)
    await update.message.reply_text(
        f"✅ رویداد «{title}» لغو شد. در حال اطلاع‌رسانی به {len(recipients)} نفر...",
        reply_markup=main_reply_keyboard(True),
    )

    for telegram_id in recipients:
        try:
            await context.bot.send_message(
                chat_id=telegram_id, text=f"⚠️ رویداد «{title}» لغو شد.\n\nپیام ادمین: {message_text}"
            )
        except Exception:
            pass
        await asyncio.sleep(0.05)

    return ConversationHandler.END


async def admin_event_cancelev_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("cancelling_event", None)
    admin = is_admin_telegram_id(update.effective_user.id)
    await update.message.reply_text(
        "لغو رویداد انجام نشد؛ رویداد دست‌نخورده باقی ماند.", reply_markup=main_reply_keyboard(admin)
    )
    return ConversationHandler.END


def build_event_cancel_conversation() -> ConversationHandler:
    cancel_handlers = [
        CommandHandler("cancel", admin_event_cancelev_cancel),
        MessageHandler(filters.Text([BTN_CANCEL]), admin_event_cancelev_cancel),
    ]
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_event_cancelev_start, pattern=r"^admin_event_cancelev_(?P<event_id>.+)$")
        ],
        states={
            WAITING_CANCEL_EVENT_MESSAGE: [
                *cancel_handlers,
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_cancelev_receive),
            ],
        },
        fallbacks=cancel_handlers,
    )


# --- تایید/رد فیش‌های واریزی توسط ادمین ---


async def admin_receipts_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    session = get_session()
    try:
        pending = (
            session.query(Registration)
            .filter_by(status=RegistrationStatus.PENDING)
            .order_by(Registration.submitted_at.asc())
            .all()
        )
        rows = []
        for r in pending:
            event = session.query(Event).filter_by(id=r.event_id).first()
            user = session.query(UserAccount).filter_by(id=r.user_id).first()
            label = f"{r.tracking_code} — {event.title if event else '؟'} — {user.full_name if user else '؟'}"
            rows.append((r.id, label))
    finally:
        session.close()

    if not rows:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_menu")]])
        await query.edit_message_text("🧾 در حال حاضر فیش در انتظار بررسی وجود ندارد.", reply_markup=keyboard)
        return

    buttons = [[InlineKeyboardButton(label, callback_data=f"admin_receipt_view_{rid}")] for rid, label in rows]
    buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_menu")])
    await query.edit_message_text("🧾 فیش‌های در انتظار بررسی:", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_receipt_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        await query.edit_message_text("⛔️ شما به این بخش دسترسی ندارید.")
        return

    registration_id = context.match.group("registration_id")
    session = get_session()
    try:
        registration = session.query(Registration).filter_by(id=registration_id).first()
        if registration is None:
            await query.edit_message_text("این ثبت‌نام یافت نشد.")
            return
        event = session.query(Event).filter_by(id=registration.event_id).first()
        user = session.query(UserAccount).filter_by(id=registration.user_id).first()
        field_values = session.query(RegistrationFieldValue).filter_by(registration_id=registration.id).all()
        answer_lines = []
        for fv in field_values:
            ef = session.query(EventField).filter_by(id=fv.event_field_id).first()
            label = ef.field_label if ef else "؟"
            answer_lines.append(f"• {label}: {fv.value}")

        caption_lines = [
            f"رویداد: {event.title if event else '؟'}",
            f"کاربر: {user.full_name if user else '؟'} (@{user.username if user and user.username else '-'})",
            f"کد پیگیری: {registration.tracking_code}",
        ]
        caption_lines.extend(answer_lines)
        caption = "\n".join(caption_lines)
        receipt_file_id = registration.receipt_file_url
    finally:
        session.close()

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ تایید", callback_data=f"admin_receipt_approve_{registration_id}"),
                InlineKeyboardButton("❌ رد", callback_data=f"admin_receipt_reject_{registration_id}"),
            ],
            [InlineKeyboardButton("⬅️ بازگشت به لیست", callback_data="admin_receipts")],
        ]
    )

    if receipt_file_id:
        await context.bot.send_photo(
            chat_id=query.from_user.id, photo=receipt_file_id, caption=caption, reply_markup=keyboard
        )
        try:
            await query.delete_message()
        except Exception:
            pass
    else:
        await query.edit_message_text(caption, reply_markup=keyboard)


async def _decide_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE, approve: bool) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin_telegram_id(query.from_user.id):
        return

    registration_id = context.match.group("registration_id")
    session = get_session()
    try:
        registration = session.query(Registration).filter_by(id=registration_id).first()
        if registration is None or registration.status != RegistrationStatus.PENDING:
            await query.answer("این ثبت‌نام دیگر در انتظار بررسی نیست.", show_alert=True)
            return

        admin_row = session.query(Admin).filter_by(telegram_id=query.from_user.id).first()
        registration.status = RegistrationStatus.APPROVED if approve else RegistrationStatus.REJECTED
        registration.reviewed_at = datetime.utcnow()
        registration.reviewed_by_admin_id = admin_row.id if admin_row else None
        session.commit()

        user = session.query(UserAccount).filter_by(id=registration.user_id).first()
        event = session.query(Event).filter_by(id=registration.event_id).first()
        tracking_code = registration.tracking_code
        user_telegram_id = user.telegram_id if user else None
        event_title = event.title if event else ""
        event_id = registration.event_id
    finally:
        session.close()

    result_text = "تایید ✅" if approve else "رد ❌"
    try:
        if query.message.caption:
            await query.message.edit_caption(caption=f"{query.message.caption}\n\nنتیجه: {result_text}")
        else:
            await query.edit_message_text(f"{query.message.text}\n\nنتیجه: {result_text}")
    except Exception:
        pass

    if user_telegram_id:
        status_text = "تایید شد ✅" if approve else "متاسفانه رد شد ❌"
        extra = "" if approve else "\n\nمی‌توانید دوباره برای این رویداد ثبت‌نام کنید."
        await context.bot.send_message(
            chat_id=user_telegram_id,
            text=f"ثبت‌نام شما برای «{event_title}» (کد پیگیری {tracking_code}) {status_text}{extra}",
        )

    if not approve:
        await try_promote_waitlist(context.bot, event_id)


async def admin_receipt_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _decide_receipt(update, context, approve=True)


async def admin_receipt_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _decide_receipt(update, context, approve=False)
