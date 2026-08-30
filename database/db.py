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
    statements = [
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS reminder_sent BOOLEAN DEFAULT FALSE",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
