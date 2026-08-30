"""
راه‌اندازی اتصال به دیتابیس (PostgreSQL روی Supabase) با SQLAlchemy.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


def get_session():
    """یک نشست (session) جدید دیتابیس برمی‌گرداند. مصرف‌کننده مسئول close کردن آن است."""
    return SessionLocal()


def init_db() -> None:
    """تمام جدول‌های تعریف‌شده در مدل‌ها را در دیتابیس (در صورت نبود) می‌سازد."""
    import database.models  # noqa: F401  (اطمینان از ثبت مدل‌ها روی Base قبل از create_all)

    Base.metadata.create_all(bind=engine)
