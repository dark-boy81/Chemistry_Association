"""
سرور FastAPI — نقطه ورود اصلی برای استقرار روی Render.

مسئولیت‌ها:
- دریافت آپدیت‌های تلگرام از طریق webhook (به‌جای polling)
- در startup: ساخت جدول‌های دیتابیس، افزودن خودکار ادمین ارشد اول، و ثبت آدرس
  webhook نزد تلگرام
- در فازهای بعدی: میزبانی API پنل مدیریت وب هم همینجا اضافه می‌شود

اجرا روی Render:
    uvicorn server:app --host 0.0.0.0 --port $PORT
"""
import logging

from fastapi import FastAPI, Request, Response
from telegram import Update

from bot.app import build_application
from config import PUBLIC_URL, WEBHOOK_SECRET
from database.db import init_db
from database.seed_admin import ensure_seed_admin

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/telegram/webhook"

app = FastAPI(title="ربات انجمن علمی شیمی — سرور")
telegram_app = build_application()


def _build_webhook_url() -> str:
    if not PUBLIC_URL:
        raise RuntimeError(
            "آدرس عمومی سرویس مشخص نیست. روی Render متغیر RENDER_EXTERNAL_URL به‌صورت "
            "خودکار ست می‌شود؛ در محیط دیگر، PUBLIC_URL را در .env قرار دهید."
        )
    return f"{PUBLIC_URL.rstrip('/')}{WEBHOOK_PATH}"


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    ensure_seed_admin()

    await telegram_app.initialize()
    await telegram_app.start()

    webhook_url = _build_webhook_url()
    await telegram_app.bot.set_webhook(
        url=webhook_url,
        secret_token=WEBHOOK_SECRET,
        allowed_updates=Update.ALL_TYPES,
    )
    logger.info("Webhook با موفقیت روی این آدرس تنظیم شد: %s", webhook_url)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await telegram_app.stop()
    await telegram_app.shutdown()


@app.get("/")
async def health_check() -> dict:
    """برای بررسی سلامت سرویس (Render Health Check) و تست دستی در مرورگر."""
    return {"status": "ok", "service": "chemistry-assoc-bot"}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request) -> Response:
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_header != WEBHOOK_SECRET:
        logger.warning("درخواست webhook با secret token نامعتبر رد شد.")
        return Response(status_code=403)

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return Response(status_code=200)
