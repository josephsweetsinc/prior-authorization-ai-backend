"""Celery tasks for automated inbound fax processing."""

import asyncio
import concurrent.futures
import logging

from celery import shared_task  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.settings import Settings
from services.ambulance_request import AmbulanceRequestService

logger = logging.getLogger(__name__)

settings = Settings.load()


@shared_task(name='tasks.fax_processing.process_inbound_fax')  # type: ignore[misc]
def process_inbound_fax(fax_id: int) -> int | None:
    """Auto-extract and draft an ambulance request from an inbound fax.

    Triggered by FaxService.process_inbound_message once a fax has
    been downloaded and stored, so this runs off the webhook request
    thread. Delegates the actual extraction and draft creation to
    AmbulanceRequestService.create_draft_request_from_fax, which is
    idempotent per fax_id.

    Args:
        fax_id: ID of the IncomingFax record to process.

    Returns:
        int | None: The created draft request's ID, or None if the
            fax was not eligible for processing or extraction failed.

    """
    logger.info('Starting inbound fax auto-processing for fax %s', fax_id)

    async def _run() -> int | None:
        """Run the extraction/draft-creation in async context."""
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
                service = AmbulanceRequestService(db_session=session)
                draft_request = await service.create_draft_request_from_fax(
                    fax_id
                )
                return draft_request.id if draft_request else None
        finally:
            # Clean up engine to avoid connection pool issues
            await engine.dispose()

    # Run in separate thread to avoid event loop conflicts with Celery
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, _run())
        try:
            request_id = future.result()
        except Exception:
            logger.exception('Error auto-processing fax %s', fax_id)
            raise
        else:
            logger.info(
                'Completed inbound fax auto-processing for fax %s '
                '(draft request id=%s)',
                fax_id,
                request_id,
            )
            return request_id
