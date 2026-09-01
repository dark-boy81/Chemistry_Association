"""
لاگ فعالیت ادمین‌ها — ثبت خودکار مهم‌ترین اکشن‌های ادمینی (ساخت/ویرایش/حذف/لغو
رویداد، تایید/رد فیش، مدیریت نشریه و FAQ، مدیریت ادمین‌ها، پیام همگانی) برای
شفافیت بین ادمین‌های مختلف.
"""
from database.db import get_session
from database.models import AdminActivityLog


def log_admin_activity(telegram_id: int, username: str | None, action: str, description: str) -> None:
    session = get_session()
    try:
        session.add(
            AdminActivityLog(
                admin_telegram_id=telegram_id,
                admin_username=username,
                action=action,
                description=description,
            )
        )
        session.commit()
    finally:
        session.close()
