"""
تنظیمات پروژه — تمام متغیرهای محیطی از فایل .env خوانده می‌شوند.
پیش از اجرا، فایل .env.example را کپی و به .env تغییر نام دهید و مقادیر را پر کنید.
"""
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# رشته محرمانه برای تایید صحت درخواست‌های webhook تلگرام (هدر X-Telegram-Bot-Api-Secret-Token)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# آدرس عمومی سرویس؛ روی Render به‌صورت خودکار در RENDER_EXTERNAL_URL موجود است
PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است. آن را در فایل .env یا در Render قرار دهید.")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL تنظیم نشده است. آن را در فایل .env یا در Render قرار دهید.")

if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET تنظیم نشده است. آن را در فایل .env یا در Render قرار دهید.")
