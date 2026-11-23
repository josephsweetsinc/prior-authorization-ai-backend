"""One-off diagnostic tool: list active admin accounts.

Useful whenever it matters which admin a fax-drafted request actually
got attributed to - create_draft_request_from_fax falls back to the
most recently created active admin whenever
RINGCENTRAL_FAX_INTAKE_ADMIN_EMAIL is unset or doesn't resolve, and
that fallback's own logging doesn't say which admin it picked.

Usage:
    python scripts/list_admins.py
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
from dao import UserDAO  # noqa: E402

settings = Settings.load()


async def list_admins() -> None:
    """Print all active admin accounts, newest first."""
    engine = create_async_engine(
        settings.database_settings.url(),
        echo=False,
        pool_pre_ping=True,
    )
    try:
        session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_maker() as session:
            user_dao = UserDAO(session)
            admins = await user_dao.get_all_admins()

        if not admins:
            print('No active admin accounts found.')
            return

        print(f'{len(admins)} active admin(s), newest first:')
        for i, admin in enumerate(admins):
            marker = '  <- fax-intake fallback picks this one' if i == 0 else ''
            print(
                f'  id={admin.id}  email={admin.email}  '
                f'created={admin.created_at}{marker}'
            )
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(list_admins())
