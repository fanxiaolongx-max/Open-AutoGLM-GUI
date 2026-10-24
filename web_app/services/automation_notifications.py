"""Deliver intervention alerts through already-configured channels."""
import asyncio
import logging

logger = logging.getLogger(__name__)


async def notify(message):
    errors = []
    try:
        from web_app.services.telegram_bot import telegram_bot_service
        await telegram_bot_service.send_system_notification(message)
    except Exception as exc:
        errors.append('telegram: '+str(exc))
    try:
        from web_app.services.email_service import email_service
        if email_service.config.enabled:
            success, detail = await asyncio.to_thread(email_service.send_task_report,
                task_name='自动化需要处理',success_count=0,failed_count=1,total_count=1,details=message)
            if not success:
                errors.append('email: '+detail)
    except Exception as exc:
        errors.append('email: '+str(exc))
    for error in errors:
        logger.error('Automation alert delivery failed: %s',error)
    return errors
