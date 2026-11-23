"""One-off recovery tool: process a fax the webhook never picked up.

A fax RingCentral received but never turned into a draft (webhook
notification missed, malformed, or not recognized - see
FaxService.process_webhook_payload's logging) is still sitting safely
in RingCentral's own message store regardless. This lists recent
inbound fax messages directly via the API, processes the chosen one
exactly as the webhook path would (download to S3, create the
IncomingFax row, then auto-draft an ambulance request from it), and
reports the result - bypassing the webhook entirely.

Usage:
    python scripts/recover_missed_fax.py list
    python scripts/recover_missed_fax.py process <message_id>
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from config.settings import Settings  # noqa: E402
from services.ambulance_request import AmbulanceRequestService  # noqa: E402
from services.fax.fax_service import FaxService  # noqa: E402
from services.fax.ringcentral_client import RingCentralClient  # noqa: E402

settings = Settings.load()


async def list_recent_faxes() -> None:
    """Print recent inbound fax messages from RingCentral's own store."""
    client = RingCentralClient()
    try:
        messages = await client.list_inbound_fax_messages()
    finally:
        await client.aclose()

    if not messages:
        print('No inbound fax messages found.')
        return

    for msg in messages:
        print(
            f'id={msg.get("id")}  '
            f'from={msg.get("from", {}).get("phoneNumber")}  '
            f'created={msg.get("creationTime")}  '
            f'status={msg.get("messageStatus")}'
        )


async def process_fax(message_id: str) -> bool:
    """Process one fax message as if the webhook had delivered it.

    Args:
        message_id: RingCentral message ID (from `list`).

    Returns:
        bool: True if a draft request was created.

    """
    engine = create_async_engine(
        settings.database_settings.url(),
        echo=False,
        pool_pre_ping=True,
    )
    try:
        session_maker = async_sessionmaker(
            bind=engine, expire_on_commit=False
        )
        async with session_maker() as session:
            fax_service = FaxService(db_session=session)
            fax = await fax_service.process_inbound_message(message_id)
            if not fax:
                print(f'❌ Fax message {message_id} could not be stored')
                return False
            print(f'✅ Stored fax id={fax.id} (status={fax.status})')

            request_service = AmbulanceRequestService(
                db_session=session, fax_service=fax_service
            )
            draft = await request_service.create_draft_request_from_fax(
                fax.id
            )
            if not draft:
                print(
                    '❌ No draft request created - check logs for why '
                    '(extraction failure, no admin configured, etc.)'
                )
                return False
            print(f'✅ Draft request created: id={draft.id}')
            print(
                f'   patient: {draft.patient_first_name} '
                f'{draft.patient_last_name}'
            )
            print(f'   status: {draft.status}')
        return True
    finally:
        await engine.dispose()


async def main() -> None:  # noqa: D103
    if len(sys.argv) < 2:  # noqa: PLR2004
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    if command == 'list':
        await list_recent_faxes()
        return

    if command == 'process':
        if len(sys.argv) != 3:  # noqa: PLR2004
            print(
                'Usage: python scripts/recover_missed_fax.py '
                'process <message_id>'
            )
            sys.exit(1)
        success = await process_fax(sys.argv[2])
        sys.exit(0 if success else 1)

    print(__doc__)
    sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
