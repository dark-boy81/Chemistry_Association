"""
افزودن اولین ادمین ارشد به دیتابیس در صورت خالی بودن رکورد مربوطه.

- `ensure_seed_admin()` در startup سرور (server.py) خودکار صدا زده می‌شود —
  یعنی نیازی به اجرای دستی این اسکریپت روی Render نیست.
- اجرای مستقل هم ممکن است (مثلاً برای تست محلی):
      python -m database.seed_admin
"""
from database.db import get_session, init_db
from database.models import Admin, AdminRole

FIRST_ADMIN_TELEGRAM_ID = 1026901196
FIRST_ADMIN_USERNAME = "arasharabzade"


def ensure_seed_admin() -> None:
    """اگر این ادمین در دیتابیس نباشد، به‌عنوان ادمین ارشد اضافه می‌شود. ایمن برای فراخوانی مکرر است."""
    session = get_session()
    try:
        existing = session.query(Admin).filter_by(telegram_id=FIRST_ADMIN_TELEGRAM_ID).first()
        if existing:
            return
        admin = Admin(
            telegram_id=FIRST_ADMIN_TELEGRAM_ID,
            username=FIRST_ADMIN_USERNAME,
            role=AdminRole.SENIOR,
        )
        session.add(admin)
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    ensure_seed_admin()
    print("بررسی/افزودن ادمین ارشد انجام شد.")
