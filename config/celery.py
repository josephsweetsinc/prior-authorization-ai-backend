"""Celery configuration for background tasks."""

import logging
import os

from celery import Celery  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]

from config.settings import Settings

logger = logging.getLogger(__name__)

settings = Settings.load()


def get_redis_url() -> str:
    """Get Redis URL from environment or settings.

    Returns:
        str: Redis connection URL.

    """
    # Check if REDIS_URL is set in environment (for docker-compose)
    redis_url = os.getenv('REDIS_URL')
    if redis_url:
        return redis_url

    # Check individual environment variables
    redis_host = os.getenv('REDIS_HOST', settings.redis_settings.HOST)
    redis_port = os.getenv('REDIS_PORT', str(settings.redis_settings.PORT))
    redis_db = os.getenv('REDIS_DB', str(settings.redis_settings.DB))

    return f'redis://{redis_host}:{redis_port}/{redis_db}'


def create_celery_app() -> Celery:
    """Create and configure Celery application.

    Returns:
        Celery: Configured Celery application instance.

    """
    redis_url = get_redis_url()
    celery_app = Celery(
        'paai',
        broker=redis_url,
        backend=redis_url,
    )

    celery_app.conf.update(
        timezone='UTC',
        enable_utc=True,
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        task_track_started=True,
        task_time_limit=30 * 60,  # 30 minutes
        task_soft_time_limit=25 * 60,  # 25 minutes
        worker_prefetch_multiplier=1,
        worker_max_tasks_per_child=1000,
        imports=(
            'tasks.expiration_reminders',
            'tasks.user_tasks',
        ),
    )

    # Schedule periodic tasks
    celery_app.conf.beat_schedule = {
        'check-expiration-reminders': {
            'task': 'tasks.expiration_reminders.check_expiration_reminders',
            'schedule': crontab(hour=8, minute=0),  # Daily at 8:00 AM
        },
        'deactivate-unapproved-providers': {
            'task': 'tasks.user_tasks.deactivate_unapproved_providers',
            'schedule': crontab(hour=0, minute=0),  # Daily at midnight
        },
    }

    return celery_app


# Create Celery app instance
celery_app = create_celery_app()

# Set as default app for shared_task decorator
celery_app.set_default()
