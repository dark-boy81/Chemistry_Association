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
import hmac
import json
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


def _secret_matches(header_value) -> bool:
    """مقایسه‌ی هم‌زمان‌بر-ثابت (constant-time) تا از طریق زمان پاسخ، secret حدس زده نشود."""
    if not header_value:
        return False
    return hmac.compare_digest(header_value.encode("utf-8"), WEBHOOK_SECRET.encode("utf-8"))


# سقف اندازه‌ی بدنه‌ی درخواست (Defense in depth؛ Telegram خودش هرگز چنین درخواست‌های
# بزرگی نمی‌فرستد — این فقط جلوی درخواست‌های عجیب را قبل از پردازش JSON می‌گیرد)
MAX_WEBHOOK_BODY_BYTES = 1_000_000  # ۱ مگابایت


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request) -> Response:
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not _secret_matches(secret_header):
        logger.warning("درخواست webhook با secret token نامعتبر رد شد.")
        return Response(status_code=403)

    body = await request.body()
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        logger.warning("درخواست webhook به‌خاطر حجم زیاد رد شد (%s بایت).", len(body))
        return Response(status_code=413)

    try:
        data = json.loads(body)
        update = Update.de_json(data, telegram_app.bot)
    except (ValueError, TypeError, AttributeError) as exc:
        # بدنه‌ی نامعتبر: نه JSON درست (ValueError از json.loads)، یا JSON معتبر ولی ساختار
        # Update نامعتبر — مثلاً رشته یا لیست به‌جای dict (AttributeError)، یا dict بدون
        # فیلدهای لازم مثل update_id (TypeError از سازنده‌ی Update). de_json خودش فقط برای
        # ورودی «خالی» (None/{}) مقدار None برمی‌گرداند، نه برای هر ورودی نامعتبری.
        logger.warning("بدنه‌ی webhook قابل تجزیه نبود: %s", exc)
        return Response(status_code=400)

    if update is None:
        logger.warning("بدنه‌ی webhook یک Update معتبر تلگرام نبود.")
        return Response(status_code=400)

    # به‌جای پردازش مستقیم و همزمان با درخواست HTTP (که در صورت کند بودن یک Handler باعث
    # timeout پاسخ به تلگرام و ارسال دوباره‌ی همان آپدیت می‌شد)، آپدیت به صف داخلی PTB اضافه
    # می‌شود. telegram_app.start() (در startup) یک تسک پس‌زمینه دارد که همین صف را می‌خواند
    # و آپدیت‌ها را به‌ترتیب و جدا از چرخه‌ی درخواست/پاسخ این endpoint پردازش می‌کند.
    await telegram_app.update_queue.put(update)
    return Response(status_code=200)
