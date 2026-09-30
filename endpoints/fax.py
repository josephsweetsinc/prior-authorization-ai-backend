import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.params import Security

from config.settings import Settings
from core import exception_handler, get_service
from dependencies import get_admin_user_from_token
from exceptions import FaxWebhookUnauthorizedException
from models import User
from models.incoming_fax import FaxStatus
from schemas.fax import (
    IncomingFaxListResponseSchema,
    IncomingFaxResponseSchema,
    LinkFaxToRequestSchema,
)
from services import FaxService

logger = logging.getLogger(__name__)

settings = Settings.load()

fax_router = APIRouter()

VALIDATION_TOKEN_HEADER = 'Validation-Token'  # noqa: S105 -- header name, not a credential


@fax_router.post(
    '/webhook',
    description=(
        'RingCentral fax webhook endpoint. Handles both the subscription '
        'validation handshake and new fax notification events.'
    ),
    summary='RingCentral fax webhook',
)
async def fax_webhook(
    request: Request,
    service: Annotated[FaxService, Depends(get_service(FaxService))],
    token: str | None = Query(
        default=None,
        description=(
            'Shared secret configured on the RingCentral subscription URL.'
        ),
    ),
) -> Response:
    """Receive RingCentral fax webhook notifications.

    RingCentral verifies a new subscription by sending a request with a
    Validation-Token header, which must be echoed back unchanged. Actual
    fax notifications are validated using a shared secret embedded as a
    query parameter in the subscribed webhook URL, since RingCentral does
    not sign webhook request bodies.

    Args:
        request: Raw FastAPI request (needed to read the validation header
            and JSON body without triggering strict schema validation on
            the validation handshake request, which has no body).
        service: Fax service.
        token: Shared secret from the webhook URL query string.

    Returns:
        Response: 200 with the echoed Validation-Token header during the
            handshake, or 200 with a small acknowledgement body otherwise.

    Raises:
        FaxWebhookUnauthorizedException: If the shared secret is missing
            or does not match the configured value.

    """
    validation_token = request.headers.get(VALIDATION_TOKEN_HEADER)
    if validation_token:
        return Response(
            status_code=200,
            headers={VALIDATION_TOKEN_HEADER: validation_token},
        )

    expected_secret = settings.ringcentral_settings.WEBHOOK_SECRET
    if not expected_secret or token != expected_secret:
        raise FaxWebhookUnauthorizedException

    payload = await request.json()
    faxes = await service.process_webhook_payload(payload)
    logger.info('Processed %d fax(es) from webhook', len(faxes))
    return Response(status_code=200)


@fax_router.get(
    '/',
    description='Get all faxes with pagination (admin only)',
    summary='List faxes',
    response_model=IncomingFaxListResponseSchema,
)
@exception_handler
async def list_faxes(
    user: Annotated[User, Security(get_admin_user_from_token)],
    service: Annotated[FaxService, Depends(get_service(FaxService))],
    page: int = Query(1, ge=1, description='Page number (1-based)'),
    status: str | None = Query(
        None, description='Filter by fax status', examples=['unresolved']
    ),
) -> IncomingFaxListResponseSchema:
    """List all faxes with pagination (admin only).

    Args:
        user: Current authenticated admin user.
        service: Fax service.
        page: Page number (1-based).
        status: Optional status to filter by.

    Returns:
        IncomingFaxListResponseSchema: Paginated list of faxes.

    """
    status_enum: FaxStatus | None = None
    if status:
        try:
            status_enum = FaxStatus(status.lower())
        except ValueError:
            status_enum = None

    return await service.list_faxes(page=page, status=status_enum)


@fax_router.get(
    '/{fax_id}',
    description='Get fax details by ID (admin only)',
    summary='Get fax',
    response_model=IncomingFaxResponseSchema,
)
@exception_handler
async def get_fax(
    fax_id: int,
    user: Annotated[User, Security(get_admin_user_from_token)],
    service: Annotated[FaxService, Depends(get_service(FaxService))],
) -> IncomingFaxResponseSchema:
    """Get fax details, including a presigned download URL (admin only).

    Args:
        fax_id: ID of the fax.
        user: Current authenticated admin user.
        service: Fax service.

    Returns:
        IncomingFaxResponseSchema: Fax details.

    """
    return await service.get_fax(fax_id)


@fax_router.post(
    '/{fax_id}/link',
    description='Manually link an unresolved fax to a request (admin only)',
    summary='Link fax to request',
    response_model=IncomingFaxResponseSchema,
)
@exception_handler
async def link_fax_to_request(
    fax_id: int,
    link_data: LinkFaxToRequestSchema,
    user: Annotated[User, Security(get_admin_user_from_token)],
    service: Annotated[FaxService, Depends(get_service(FaxService))],
) -> IncomingFaxResponseSchema:
    """Manually link a fax to an ambulance request (admin only).

    Args:
        fax_id: ID of the fax to link.
        link_data: Request ID to link this fax to.
        user: Current authenticated admin user.
        service: Fax service.

    Returns:
        IncomingFaxResponseSchema: Updated fax.

    """
    return await service.link_fax_to_request(
        fax_id=fax_id,
        request_id=link_data.request_id,
        matched_by_user_id=user.id,
    )
