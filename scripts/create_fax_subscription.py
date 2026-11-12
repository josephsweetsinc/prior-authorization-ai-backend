"""One-off/renewal tool: register PAAI's webhook with RingCentral.

There's no RingCentral console UI for this - subscribing to inbound
fax notifications is only possible via their Subscription API, so
this has to be run manually once (and again whenever the subscription
is about to expire, since RingCentral does not renew it automatically).

Builds the full webhook URL itself from the given base URL plus the
configured RINGCENTRAL_WEBHOOK_SECRET, so the secret never has to be
passed on the command line (which would show up in shell history and
process listings).

Usage:
    python scripts/create_fax_subscription.py <base_url>

Example:
    python scripts/create_fax_subscription.py https://dev-api.infopaai.com

"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings  # noqa: E402
from services.fax.ringcentral_client import RingCentralClient  # noqa: E402


async def create_fax_subscription(base_url: str) -> bool:
    """Create the inbound-fax webhook subscription.

    Args:
        base_url: Scheme + host the backend is reachable at (no
            trailing slash), e.g. https://dev-api.infopaai.com.

    Returns:
        bool: True if the subscription was created successfully.

    """
    settings = Settings.load()
    webhook_secret = settings.ringcentral_settings.WEBHOOK_SECRET
    if not webhook_secret:
        print('❌ RINGCENTRAL_WEBHOOK_SECRET is not configured')
        return False

    webhook_url = f'{base_url}/api/v1/fax/webhook?token={webhook_secret}'

    client = RingCentralClient()
    try:
        result = await client.create_subscription(webhook_url=webhook_url)
    except Exception as e:
        print(f'❌ Failed to create subscription: {e}')
        return False
    else:
        print('✅ Subscription created')
        print(f"   id: {result.get('id')}")
        print(f"   status: {result.get('status')}")
        print(f"   expires: {result.get('expirationTime')}")
        return True
    finally:
        await client.aclose()


async def main() -> None:  # noqa: D103
    if len(sys.argv) != 2:  # noqa: PLR2004
        print('Usage: python scripts/create_fax_subscription.py <base_url>')
        print(
            'Example: python scripts/create_fax_subscription.py'
            ' https://dev-api.infopaai.com'
        )
        sys.exit(1)
    base_url = sys.argv[1].rstrip('/')
    created = await create_fax_subscription(base_url)
    sys.exit(0 if created else 1)


if __name__ == '__main__':
    asyncio.run(main())
