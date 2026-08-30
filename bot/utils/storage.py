"""
آپلود فایل (PDF نشریه، عکس فیش واریزی) در Supabase Storage.

نیازمند SUPABASE_URL و SUPABASE_KEY (کلید service_role — نه anon) در تنظیمات.
باکت‌های موردنیاز باید از قبل در پنل Supabase (Storage) ساخته شده باشند:
- "journal-pdfs"  (Public) — برای فایل‌های PDF نشریه
- "receipts"        (Private) — برای عکس فیش‌های واریزی
"""
from functools import lru_cache

from supabase import Client, create_client

from config import SUPABASE_KEY, SUPABASE_URL

JOURNAL_BUCKET = "journal-pdfs"
RECEIPTS_BUCKET = "receipts"


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL و SUPABASE_KEY تنظیم نشده‌اند. برای آپلود فایل، این دو متغیر "
            "را در Render (بخش Environment) با کلید service_role پروژه Supabase پر کنید."
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upload_public_file(bucket: str, path: str, content: bytes, content_type: str) -> str:
    """فایل را در یک باکت عمومی آپلود می‌کند و لینک مستقیم دانلود را برمی‌گرداند."""
    client = get_client()
    client.storage.from_(bucket).upload(
        path,
        content,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return client.storage.from_(bucket).get_public_url(path)


def upload_private_file(bucket: str, path: str, content: bytes, content_type: str) -> str:
    """فایل را در یک باکت خصوصی آپلود می‌کند و مسیر ذخیره‌شده (نه لینک عمومی) را برمی‌گرداند."""
    client = get_client()
    client.storage.from_(bucket).upload(
        path,
        content,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return path


def get_signed_url(bucket: str, path: str, expires_in_seconds: int = 3600) -> str:
    """برای نمایش موقت فایل‌های خصوصی (مثل فیش واریزی) به ادمین استفاده می‌شود."""
    client = get_client()
    result = client.storage.from_(bucket).create_signed_url(path, expires_in_seconds)
    return result["signedURL"] if "signedURL" in result else result.get("signed_url", "")
