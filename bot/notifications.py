"""
اطلاع‌رسانی‌های خودکار ربات:
- ارسال پیام همگانی به همه کاربران (هنگام انتشار شماره جدید نشریه یا رویداد جدید)
- ارتقای خودکار از لیست انتظار وقتی جایی در یک رویداد خالی می‌شود — برای رویداد
  رایگان بلافاصله تایید می‌شود؛ برای رویداد پولی یک پیشنهاد با مهلت محدود پرداخت
  ارسال می‌شود (بدون گرفتن فیش از قبل، چون تا آن لحظه معلوم نبود جایی برایش هست)
- بررسی دوره‌ای پیشنهادهای منقضی‌شده و انتقال نوبت به نفر بعدی لیست انتظار
- یادآوری خودکار به ثبت‌نامی‌های تاییدشده، ۲۴ ساعت قبل از شروع رویداد
"""
import asyncio
from datetime import datetime, timedelta

from telegram.ext import ContextTypes

from bot.tz import utc_naive_to_local_str
from database.db import get_session
from database.models import Event, Registration, RegistrationStatus, UserAccount

# وضعیت‌هایی که یک جای رویداد را اشغال کرده‌اند (تعریف محلی برای پرهیز از import
# چرخه‌ای با bot/handlers/events.py که خودش این ماژول را import می‌کند)
_RESERVED_STATUSES = (RegistrationStatus.PENDING, RegistrationStatus.APPROVED, RegistrationStatus.OFFERED)

# مهلت پرداخت وقتی نوبت کسی از لیست انتظار می‌رسد (فقط رویدادهای پولی)
WAITLIST_OFFER_HOURS = 1


async def broadcast_to_all_users(bot, text: str, reply_markup=None) -> None:
    """پیام را برای همه کاربران ثبت‌شده در ربات ارسال می‌کند (کاربرانی که ربات را بلاک
    کرده باشند به‌سادگی رد می‌شوند)."""
    session = get_session()
    try:
        telegram_ids = [u.telegram_id for u in session.query(UserAccount).all()]
    finally:
        session.close()

    for telegram_id in telegram_ids:
        try:
            await bot.send_message(chat_id=telegram_id, text=text, reply_markup=reply_markup)
        except Exception:
            pass
        await asyncio.sleep(0.05)  # جلوگیری از برخورد به محدودیت نرخ ارسال تلگرام


async def try_promote_waitlist(bot, event_id: str) -> None:
    """وقتی ثبت‌نامی لغو/رد می‌شود یا ظرفیت زیاد می‌شود، اولین نفر در لیست انتظار را
    ارتقا می‌دهد:
    - رویداد رایگان → تایید خودکار فوری
    - رویداد پولی → وضعیت «نوبت رسیده» به همراه اطلاعات پرداخت و مهلت محدود برای
      ارسال فیش (فیش تا این لحظه گرفته نشده بود، چون معلوم نبود جایی برایش باز می‌شود)
    """
    session = get_session()
    try:
        event = session.query(Event).filter_by(id=event_id).first()
        if event is None:
            return

        taken = (
            session.query(Registration)
            .filter(Registration.event_id == event_id, Registration.status.in_(_RESERVED_STATUSES))
            .count()
        )
        if taken >= event.capacity:
            return

        next_waiting = (
            session.query(Registration)
            .filter_by(event_id=event_id, status=RegistrationStatus.WAITLISTED)
            .order_by(Registration.submitted_at.asc())
            .first()
        )
        if next_waiting is None:
            return

        is_free = not event.price
        if is_free:
            next_waiting.status = RegistrationStatus.APPROVED
        else:
            next_waiting.status = RegistrationStatus.OFFERED
            next_waiting.offer_expires_at = datetime.utcnow() + timedelta(hours=WAITLIST_OFFER_HOURS)
        session.commit()

        user = session.query(UserAccount).filter_by(id=next_waiting.user_id).first()
        user_telegram_id = user.telegram_id if user else None
        tracking_code = next_waiting.tracking_code
        event_title = event.title
        price = event.price
        card_number = event.card_number
    finally:
        session.close()

    if not user_telegram_id:
        return

    if is_free:
        text = (
            f"🎉 جای خالی در رویداد «{event_title}» باز شد و ثبت‌نام شما "
            f"(کد {tracking_code}) به‌طور خودکار تایید شد!"
        )
    else:
        price_text = f"{int(price):,} تومان" if price else ""
        card_line = f"\n\nشماره کارت: {card_number}" if card_number else ""
        text = (
            f"🎉 جای خالی در رویداد «{event_title}» باز شد! نوبت ثبت‌نام شما (کد {tracking_code}) رسیده است.\n\n"
            f"لطفاً ظرف مدت {WAITLIST_OFFER_HOURS} ساعت مبلغ {price_text} را واریز کرده و تصویر یا فایل فیش "
            f"واریزی را همینجا برای ربات ارسال کنید.{card_line}\n\n"
            "⚠️ اگر تا پایان این مهلت فیش ارسال نشود، نوبت به نفر بعدی لیست انتظار داده می‌شود."
        )
    try:
        await bot.send_message(chat_id=user_telegram_id, text=text)
    except Exception:
        pass


async def check_expired_offers_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """هر چند دقیقه یک‌بار اجرا می‌شود (طبق زمان‌بندی در bot/app.py): پیشنهادهای
    پرداخت (وضعیت OFFERED) که مهلتشان گذشته را لغو کرده و نوبت را به نفر بعدی
    لیست انتظار همان رویداد می‌دهد."""
    now = datetime.utcnow()
    session = get_session()
    try:
        expired = (
            session.query(Registration)
            .filter(
                Registration.status == RegistrationStatus.OFFERED,
                Registration.offer_expires_at.isnot(None),
                Registration.offer_expires_at < now,
            )
            .all()
        )

        to_process = []
        for reg in expired:
            reg.status = RegistrationStatus.CANCELLED
            reg.offer_expires_at = None
            user = session.query(UserAccount).filter_by(id=reg.user_id).first()
            event = session.query(Event).filter_by(id=reg.event_id).first()
            to_process.append((user.telegram_id if user else None, event.title if event else "", reg.event_id))

        session.commit()
    finally:
        session.close()

    for telegram_id, title, event_id in to_process:
        if telegram_id:
            try:
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=(
                        f"⏰ مهلت {WAITLIST_OFFER_HOURS} ساعته پرداخت برای «{title}» به پایان رسید و نوبت شما "
                        "به نفر بعدی لیست انتظار داده شد. در صورت تمایل می‌توانید دوباره ثبت‌نام کنید."
                    ),
                )
            except Exception:
                pass
        await try_promote_waitlist(context.bot, event_id)


async def send_event_reminders_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """هر بار که این Job اجرا می‌شود (طبق زمان‌بندی در bot/app.py)، رویدادهایی که در
    ۲۴ ساعت آینده برگزار می‌شوند و هنوز یادآوری برایشان ارسال نشده را پیدا کرده و به
    ثبت‌نامی‌های تاییدشده یادآوری می‌فرستد."""
    now = datetime.utcnow()
    window_end = now + timedelta(hours=24)

    session = get_session()
    try:
        upcoming = (
            session.query(Event)
            .filter(
                Event.event_date.isnot(None),
                Event.event_date >= now,
                Event.event_date <= window_end,
                Event.reminder_sent.is_(False),
            )
            .all()
        )

        to_remind = []
        for event in upcoming:
            approved = (
                session.query(Registration)
                .filter_by(event_id=event.id, status=RegistrationStatus.APPROVED)
                .all()
            )
            for reg in approved:
                user = session.query(UserAccount).filter_by(id=reg.user_id).first()
                if user:
                    to_remind.append((user.telegram_id, event.title, event.event_date))
            event.reminder_sent = True

        session.commit()
    finally:
        session.close()

    for telegram_id, title, event_date in to_remind:
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=f"⏰ یادآوری: رویداد «{title}» فردا ({utc_naive_to_local_str(event_date)}) برگزار می‌شود.",
            )
        except Exception:
            pass
        await asyncio.sleep(0.05)
