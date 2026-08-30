"""
اجرای محلی ربات با polling — فقط برای توسعه اختیاری.
برای استقرار روی Render از server.py (حالت webhook) استفاده می‌شود.

اجرا (اختیاری، محلی):
    python -m bot.main
"""
import logging

from bot.app import build_application
from database.db import init_db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    init_db()
    application = build_application()
    logger.info("ربات در حال اجرا (polling)...")
    application.run_polling()


if __name__ == "__main__":
    main()
