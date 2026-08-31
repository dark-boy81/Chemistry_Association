"""
ساخت و پیکربندی Application ربات تلگرام (ثبت همه هندلرها) — این ماژول مستقل از حالت
اجرا (polling یا webhook) است تا هم از server.py و هم از bot/main.py قابل استفاده باشد.
"""
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot.handlers.admin_menu import admin_menu_callback, admin_menu_text_entry
from bot.handlers.admins import (
    admin_add_start,
    admin_manage_menu_callback,
    admin_remove_confirm_callback,
    admin_remove_prompt_callback,
    admin_transfer_execute_callback,
    admin_transfer_pick_callback,
    admin_transfer_start,
    build_admin_add_conversation,
)
from bot.handlers.contact import build_admin_reply_conversation, build_contact_conversation
from bot.handlers.events import (
    admin_event_delete_confirm_callback,
    admin_event_delete_prompt_callback,
    admin_event_detail_callback,
    admin_event_list_callback,
    admin_events_menu_callback,
    admin_receipt_approve_callback,
    admin_receipt_reject_callback,
    admin_receipt_view_callback,
    admin_receipts_menu_callback,
    build_admin_event_add_conversation,
    build_event_cancel_conversation,
    build_event_edit_conversation,
    build_event_registration_conversation,
    event_cancel_callback,
    event_list_callback,
    event_view_callback,
    events_menu_text_entry,
)
from bot.handlers.faq import (
    admin_faq_delete_callback,
    admin_faq_list_callback,
    admin_faq_menu_callback,
    admin_faq_view_callback,
    build_faq_add_conversation,
    build_faq_edit_conversation,
    faq_list_callback,
    faq_menu_text_entry,
    faq_view_callback,
)
from bot.handlers.journal import (
    admin_journal_editview_callback,
    admin_journal_list_callback,
    admin_journal_menu_callback,
    build_journal_add_conversation,
    build_journal_edit_conversation,
    journal_archive_callback,
    journal_download_callback,
    journal_latest_callback,
    journal_menu_text_entry,
    journal_view_callback,
)
from bot.handlers.start import start_command
from bot.handlers.stats import (
    admin_stats_export_callback,
    admin_stats_menu_callback,
    admin_stats_pick_event_callback,
)
from bot.handlers.user_menu import back_to_main_note_callback
from bot.keyboards import BTN_ADMIN_PANEL, BTN_CONTACT, BTN_EVENTS, BTN_FAQ, BTN_JOURNAL
from bot.notifications import send_event_reminders_job
from config import BOT_TOKEN


def build_application() -> Application:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))

    # گفتگوهای چندمرحله‌ای — باید قبل از هندلرهای متنی/این‌لاین عمومی ثبت شوند
    application.add_handler(build_journal_add_conversation())
    application.add_handler(build_journal_edit_conversation())
    application.add_handler(build_admin_event_add_conversation())
    application.add_handler(build_event_edit_conversation())
    application.add_handler(build_event_cancel_conversation())
    application.add_handler(build_event_registration_conversation())
    application.add_handler(build_faq_add_conversation())
    application.add_handler(build_faq_edit_conversation())
    application.add_handler(build_contact_conversation(BTN_CONTACT))
    application.add_handler(build_admin_reply_conversation())
    application.add_handler(build_admin_add_conversation())

    # دکمه‌های ثابت پایین صفحه (منوی اصلی)
    application.add_handler(MessageHandler(filters.Text([BTN_JOURNAL]), journal_menu_text_entry))
    application.add_handler(MessageHandler(filters.Text([BTN_EVENTS]), events_menu_text_entry))
    application.add_handler(MessageHandler(filters.Text([BTN_FAQ]), faq_menu_text_entry))
    application.add_handler(MessageHandler(filters.Text([BTN_ADMIN_PANEL]), admin_menu_text_entry))
    # توجه: دکمه BTN_CONTACT به‌عنوان entry point گفتگوی contact ثبت شده (بالاتر)

    # دکمه‌های این‌لاین بخش نشریه (کاربر)
    application.add_handler(CallbackQueryHandler(journal_latest_callback, pattern="^journal_latest$"))
    application.add_handler(CallbackQueryHandler(journal_archive_callback, pattern="^journal_archive$"))
    application.add_handler(
        CallbackQueryHandler(journal_view_callback, pattern=r"^journal_view_(?P<issue_id>.+)$")
    )
    application.add_handler(
        CallbackQueryHandler(journal_download_callback, pattern=r"^journal_download_(?P<issue_id>.+)$")
    )

    # دکمه‌های این‌لاین بخش رویدادها (کاربر)
    application.add_handler(CallbackQueryHandler(event_list_callback, pattern="^event_list$"))
    application.add_handler(CallbackQueryHandler(event_view_callback, pattern=r"^event_view_(?P<event_id>.+)$"))
    application.add_handler(
        CallbackQueryHandler(event_cancel_callback, pattern=r"^event_cancel_(?P<registration_id>.+)$")
    )

    # دکمه‌های این‌لاین بخش FAQ (کاربر)
    application.add_handler(CallbackQueryHandler(faq_list_callback, pattern="^faq_list$"))
    application.add_handler(CallbackQueryHandler(faq_view_callback, pattern=r"^faq_view_(?P<faq_id>.+)$"))

    # پنل مدیریت — این‌لاین (زیرمنوی اصلی مدیریت)
    application.add_handler(CallbackQueryHandler(admin_menu_callback, pattern="^admin_menu$"))

    # مدیریت نشریه
    application.add_handler(CallbackQueryHandler(admin_journal_menu_callback, pattern="^admin_journal$"))
    application.add_handler(CallbackQueryHandler(admin_journal_list_callback, pattern="^admin_journal_list$"))
    application.add_handler(
        CallbackQueryHandler(admin_journal_editview_callback, pattern=r"^admin_journal_editview_(?P<issue_id>.+)$")
    )

    # مدیریت رویدادها
    application.add_handler(CallbackQueryHandler(admin_events_menu_callback, pattern="^admin_events$"))
    application.add_handler(CallbackQueryHandler(admin_event_list_callback, pattern="^admin_event_list$"))
    application.add_handler(
        CallbackQueryHandler(admin_event_detail_callback, pattern=r"^admin_event_detail_(?P<event_id>.+)$")
    )
    application.add_handler(
        CallbackQueryHandler(admin_event_delete_prompt_callback, pattern=r"^admin_event_delask_(?P<event_id>.+)$")
    )
    application.add_handler(
        CallbackQueryHandler(admin_event_delete_confirm_callback, pattern=r"^admin_event_delyes_(?P<event_id>.+)$")
    )

    # تایید/رد فیش‌های واریزی
    application.add_handler(CallbackQueryHandler(admin_receipts_menu_callback, pattern="^admin_receipts$"))
    application.add_handler(
        CallbackQueryHandler(admin_receipt_view_callback, pattern=r"^admin_receipt_view_(?P<registration_id>.+)$")
    )
    application.add_handler(
        CallbackQueryHandler(
            admin_receipt_approve_callback, pattern=r"^admin_receipt_approve_(?P<registration_id>.+)$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            admin_receipt_reject_callback, pattern=r"^admin_receipt_reject_(?P<registration_id>.+)$"
        )
    )

    # مدیریت FAQ
    application.add_handler(CallbackQueryHandler(admin_faq_menu_callback, pattern="^admin_faq$"))
    application.add_handler(CallbackQueryHandler(admin_faq_list_callback, pattern="^admin_faq_list$"))
    application.add_handler(CallbackQueryHandler(admin_faq_view_callback, pattern=r"^admin_faq_view_(?P<faq_id>.+)$"))
    application.add_handler(
        CallbackQueryHandler(admin_faq_delete_callback, pattern=r"^admin_faq_delete_(?P<faq_id>.+)$")
    )

    # مدیریت ادمین‌ها
    application.add_handler(CallbackQueryHandler(admin_manage_menu_callback, pattern="^admin_manage_admins$"))
    application.add_handler(
        CallbackQueryHandler(admin_remove_prompt_callback, pattern=r"^admin_removeask_(?P<admin_id>.+)$")
    )
    application.add_handler(
        CallbackQueryHandler(admin_remove_confirm_callback, pattern=r"^admin_remove_confirm_(?P<admin_id>.+)$")
    )
    application.add_handler(CallbackQueryHandler(admin_transfer_start, pattern="^admin_transfer_start$"))
    application.add_handler(
        CallbackQueryHandler(admin_transfer_pick_callback, pattern=r"^admin_transfer_pick_(?P<admin_id>.+)$")
    )
    application.add_handler(
        CallbackQueryHandler(admin_transfer_execute_callback, pattern=r"^admin_transfer_execute_(?P<admin_id>.+)$")
    )

    # آمار و گزارش
    application.add_handler(CallbackQueryHandler(admin_stats_menu_callback, pattern="^admin_stats$"))
    application.add_handler(
        CallbackQueryHandler(admin_stats_pick_event_callback, pattern="^admin_stats_pick_event$")
    )
    application.add_handler(
        CallbackQueryHandler(admin_stats_export_callback, pattern=r"^admin_stats_export_(?P<event_id>.+)$")
    )

    # دکمه مشترک «بازگشت به منوی اصلی» در زیرمنوها
    application.add_handler(CallbackQueryHandler(back_to_main_note_callback, pattern="^back_to_main_note$"))

    # Job زمان‌بندی‌شده: هر ۳۰ دقیقه بررسی رویدادهای نزدیک برای ارسال یادآوری خودکار
    application.job_queue.run_repeating(send_event_reminders_job, interval=1800, first=15)

    return application
