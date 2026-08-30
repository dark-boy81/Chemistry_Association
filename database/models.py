"""
مدل‌های دیتابیس پروژه ربات انجمن علمی شیمی / نشریه پژواک شیمی.

جدول‌ها:
- Admin: ادمین‌های ربات (حداکثر ۵ نفر)، با نقش ارشد یا عادی
- UserAccount: کاربران عادی ربات
- JournalIssue: شماره‌های نشریه (PDF + چکیده)
- Event: رویدادها
- EventField: فیلدهای پویای ثبت‌نام که ادمین برای هر رویداد تعریف می‌کند
- Registration: ثبت‌نام هر کاربر در یک رویداد (وضعیت، فیش، کد پیگیری)
- RegistrationFieldValue: مقدار هرکدام از فیلدهای پویا برای یک ثبت‌نام خاص
- FAQ: سوالات متداول
- SupportMessage: پیام‌های رد و بدل شده بین کاربر و ادمین
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.db import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class AdminRole(str, enum.Enum):
    SENIOR = "senior"   # ادمین ارشد — می‌تواند ادمین اضافه/حذف کند و ارشدیت را منتقل کند
    ADMIN = "admin"      # ادمین عادی


class RegistrationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WAITLISTED = "waitlisted"
    CANCELLED = "cancelled"


class FieldType(str, enum.Enum):
    TEXT = "text"
    NUMBER = "number"
    PHONE = "phone"


class MessageDirection(str, enum.Enum):
    USER_TO_ADMIN = "user_to_admin"
    ADMIN_TO_USER = "admin_to_user"


class Admin(Base):
    __tablename__ = "admins"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)
    role = Column(Enum(AdminRole), nullable=False, default=AdminRole.ADMIN)
    added_by_telegram_id = Column(BigInteger, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)


class UserAccount(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)

    registrations = relationship("Registration", back_populates="user")
    messages = relationship("SupportMessage", back_populates="user")


class JournalIssue(Base):
    __tablename__ = "journal_issues"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    issue_number = Column(Integer, nullable=False)
    title = Column(String(300), nullable=False)
    abstract = Column(Text, nullable=True)
    pdf_file_url = Column(Text, nullable=False)
    uploaded_by_admin_id = Column(UUID(as_uuid=False), ForeignKey("admins.id"), nullable=True)
    published_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("issue_number", name="uq_issue_number"),)


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    capacity = Column(Integer, nullable=False)
    price = Column(Numeric(12, 0), nullable=True)  # مبلغ به تومان؛ برای رویداد رایگان خالی بماند
    event_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by_admin_id = Column(UUID(as_uuid=False), ForeignKey("admins.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    fields = relationship("EventField", back_populates="event", cascade="all, delete-orphan")
    registrations = relationship("Registration", back_populates="event", cascade="all, delete-orphan")


class EventField(Base):
    """فیلد پویای ثبت‌نام — ادمین برای هر رویداد فیلدهای موردنیاز را خودش تعریف می‌کند
    (مثلاً نام، نام‌خانوادگی، کد دانشجویی، کد ملی، رشته، سال ورودی، شماره تماس)."""

    __tablename__ = "event_fields"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    event_id = Column(UUID(as_uuid=False), ForeignKey("events.id"), nullable=False)
    field_key = Column(String(100), nullable=False)     # مثال: national_id
    field_label = Column(String(200), nullable=False)   # مثال: کد ملی
    field_type = Column(Enum(FieldType), default=FieldType.TEXT)
    is_required = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)

    event = relationship("Event", back_populates="fields")


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    event_id = Column(UUID(as_uuid=False), ForeignKey("events.id"), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    tracking_code = Column(String(20), unique=True, nullable=False)
    status = Column(Enum(RegistrationStatus), default=RegistrationStatus.PENDING)
    receipt_file_url = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by_admin_id = Column(UUID(as_uuid=False), ForeignKey("admins.id"), nullable=True)

    event = relationship("Event", back_populates="registrations")
    user = relationship("UserAccount", back_populates="registrations")
    field_values = relationship(
        "RegistrationFieldValue", back_populates="registration", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_user"),)


class RegistrationFieldValue(Base):
    __tablename__ = "registration_field_values"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    registration_id = Column(UUID(as_uuid=False), ForeignKey("registrations.id"), nullable=False)
    event_field_id = Column(UUID(as_uuid=False), ForeignKey("event_fields.id"), nullable=False)
    value = Column(Text, nullable=False)

    registration = relationship("Registration", back_populates="field_values")


class FAQ(Base):
    __tablename__ = "faqs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    display_order = Column(Integer, default=0)
    created_by_admin_id = Column(UUID(as_uuid=False), ForeignKey("admins.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    admin_id = Column(UUID(as_uuid=False), ForeignKey("admins.id"), nullable=True)
    direction = Column(Enum(MessageDirection), nullable=False)
    message_text = Column(Text, nullable=False)
    is_answered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("UserAccount", back_populates="messages")
