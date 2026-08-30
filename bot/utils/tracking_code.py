"""
تولید کد پیگیری یکتا برای ثبت‌نام‌ها (مثلاً PJ-7K9X2QAB).
"""
import random
import string

from database.db import get_session
from database.models import Registration

_ALPHABET = string.ascii_uppercase + string.digits


def _random_code(length: int = 8) -> str:
    return "".join(random.choices(_ALPHABET, k=length))


def generate_unique_tracking_code() -> str:
    """کدی می‌سازد که در جدول registrations یکتا باشد."""
    session = get_session()
    try:
        for _ in range(20):
            code = f"PJ-{_random_code()}"
            exists = session.query(Registration).filter_by(tracking_code=code).first()
            if not exists:
                return code
        raise RuntimeError("ساخت کد پیگیری یکتا پس از چند بار تلاش ناموفق بود.")
    finally:
        session.close()
