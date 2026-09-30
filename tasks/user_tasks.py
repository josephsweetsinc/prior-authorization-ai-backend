"""Celery tasks for scheduled user-account maintenance."""

import asyncio
import concurrent.futures
import logging

from celery import shared_task  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.settings import Settings
from services.user import UserService

logger = logging.getLogger(__name__)

settings = Settings.load()


@shared_task(name='tasks.user_tasks.deactivate_unapproved_providers')  # type: ignore[misc]
def deactivate_unapproved_providers() -> int:
    """Deactivate provider accounts not re-approved within 30 days.

    Runs daily at midnight.

    Returns:
        int: Number of deactivated users.

    """
    logger.info('Starting deactivate_unapproved_providers task')

    async def _run() -> int:
        """Run the deactivation check in async context."""
        # Create a new engine for each task to avoid event loop conflicts
        engine = create_async_engine(
            settings.database_settings.url(),
            echo=False,
            pool_pre_ping=True,
        )
        try:
            session_maker = async_sessionmaker(
                bind=engine,
                expire_on_commit=False,
            )
            async with session_maker() as session:
                service = UserService(db_session=session)
                return await service.deactivate_unapproved_providers()
        finally:
            # Clean up engine to avoid connection pool issues
            await engine.dispose()

    # Run in separate thread to avoid event loop conflicts with Celery
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, _run())
        try:
            deactivated_count = future.result()
        except Exception:
            logger.exception('Error in deactivate_unapproved_providers task')
            raise
        else:
            logger.info(
                'deactivate_unapproved_providers task completed: '
                '%d deactivated',
                deactivated_count,
            )
            return deactivated_count
