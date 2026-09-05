"""
راه‌اندازی اتصال به دیتابیس (PostgreSQL روی Supabase) با SQLAlchemy.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


def get_session():
    """یک نشست (session) جدید دیتابیس برمی‌گرداند. مصرف‌کننده مسئول close کردن آن است."""
    return SessionLocal()


def init_db() -> None:
    """تمام جدول‌های تعریف‌شده در مدل‌ها را در دیتابیس (در صورت نبود) می‌سازد،
    و ستون‌های جدیدی که بعداً به مدل‌های موجود اضافه شده‌اند را هم (بدون نیاز به
    ابزار migration جداگانه) روی جدول‌های از قبل موجود اضافه می‌کند."""
    import database.models  # noqa: F401  (اطمینان از ثبت مدل‌ها روی Base قبل از create_all)

    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()


def _apply_lightweight_migrations() -> None:
    """اجرای امن و idempotent — هر بار در startup اجرا می‌شود، فقط اگر ستون از قبل
    نباشد آن را اضافه می‌کند. جایگزین ساده‌ای برای Alembic تا وقتی پروژه به آن نیاز پیدا کند."""
    # افزودن مقدار جدید به یک ENUM موجود در پستگرس باید در تراکنش جداگانه (autocommit)
    # اجرا شود، نه در همان تراکنش دستورات دیگر.
    # ⚠️ نکته مهم: SQLAlchemy برای Enum(RegistrationStatus) به‌صورت پیش‌فرض از نام عضو
    # پایتونی (مثل PENDING) به‌عنوان مقدار ذخیره‌شده در پستگرس استفاده می‌کند، نه مقدار
    # رشته‌ای‌اش (مثل "pending") — پس مقدار جدید enum باید حروف بزرگ باشد.
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text("ALTER TYPE registrationstatus ADD VALUE IF NOT EXISTS 'OFFERED'"))

    statements = [
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS reminder_sent BOOLEAN DEFAULT FALSE",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS card_number VARCHAR(64)",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS venue VARCHAR(300)",
        "ALTER TABLE registrations DROP CONSTRAINT IF EXISTS uq_event_user",
        "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS offer_expires_at TIMESTAMP",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
