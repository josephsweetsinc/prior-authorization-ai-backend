import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.params import Security

from core import exception_handler, get_service, timing_handler
from dependencies import get_current_user, get_provider_user_from_token
from models import User
from schemas.ambulance_request import (
    AmbulanceRequestResponseSchema,
    AmbulanceRequestsListResponseSchema,
    CreateAmbulanceRequestParseSchema,
    CreateAmbulanceRequestSchema,
    FileUploadResponseSchema,
    FileUploadWithExtractionResponseSchema,
    RequestWithStatusHistorySchema,
)
from services import AmbulanceRequestService

logger = logging.getLogger(__name__)

ambulance_request_router = APIRouter()


@ambulance_request_router.post(
    '/files',
    description='Upload medical documents from user.',
    summary='Upload medical documents.',
    response_model=list[FileUploadResponseSchema],
)
@timing_handler
@exception_handler
async def upload_files(
    files: Annotated[list[UploadFile], File()],
    user: Annotated[User, Security(get_provider_user_from_token)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> list[FileUploadResponseSchema]:
    """Upload medical document files to S3.

    This endpoint:
    1. Uploads files to S3
    2. Creates file records in database
    3. Returns uploaded files info

    Args:
        files: List of files (PDF, DOC, DOCX, XLS, XLSX, max 10MB each).
        user: Current authenticated user.
        service: Ambulance request service.

    Returns:
        list[FileUploadResponseSchema]: List of uploaded files info.

    Raises:
        HTTPException: If file upload fails.

    """
    return await service.upload_files(files=files, user_id=user.id)


@ambulance_request_router.post(
    '/extraction',
    description='Step 2: Parse medical documents and get info from AI.',
    summary='Get info from documents by AI.',
    response_model=FileUploadWithExtractionResponseSchema,
)
@timing_handler
@exception_handler
async def create_request_with_extraction(
    request_data: CreateAmbulanceRequestParseSchema,
    user: Annotated[User, Security(get_provider_user_from_token)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> FileUploadWithExtractionResponseSchema:
    """Triggers AI extraction of medical data from previously uploaded files.

    This endpoint acts as the second step in the request workflow.
    It takes a list of file IDs (uploaded in Step 1), validates them, and
    sends the documents to an AI service to parse medical details.

    The result is returned for user verification and is not yet saved
    as a permanent ambulance request in the system.

    Args:
        request_data (CreateAmbulanceRequestParseSchema): The input payload
            containing the list of file IDs to be analyzed.
        user (User): The currently authenticated provider user.
        service (AmbulanceRequestService): The injected service instance.

    Returns:
        FileUploadWithExtractionResponseSchema: The structured data
            extracted from the medical documents.

    """
    return await service.create_request_with_extraction(
        request_data=request_data, user_id=user.id
    )


@ambulance_request_router.post(
    '/create',
    description='Create ambulance request with info verified by provider.',
    summary='Create ambulance request.',
    response_model=AmbulanceRequestResponseSchema,
)
@exception_handler
async def create_request(
    request_data: CreateAmbulanceRequestSchema,
    user: Annotated[User, Security(get_provider_user_from_token)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> AmbulanceRequestResponseSchema:
    """Create a new ambulance request.

    This endpoint combines step 2 (transportation info) and step 3 (review).
    The request is created with status PROCESSING.

    Args:
        request_data: Request data with transportation info and review data.
        user: Current authenticated user.
        service: Ambulance request service.

    Returns:
        AmbulanceRequestResponseSchema: Created request.

    Raises:
        HTTPException: If request creation fails.

    """
    return None


@ambulance_request_router.get(
    '/{request_id}',
    description='Get ambulance request by ID',
    response_model=RequestWithStatusHistorySchema,
)
@exception_handler
async def get_request(
    request_id: int,
    user: Annotated[User, Security(get_current_user)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> RequestWithStatusHistorySchema:
    """Get ambulance request by ID with status history.

    Args:
        request_id: Request ID.
        user: Current authenticated user.
        service: Ambulance request service.

    Returns:
        RequestWithStatusHistorySchema: Request with status history.

    Raises:
        HTTPException: If request not found or access denied.

    """
    return await service.get_request_by_id(
        request_id=request_id,
        user=user,
    )


@ambulance_request_router.get(
    '/',
    description='Get all ambulance requests with cursor pagination',
    response_model=AmbulanceRequestsListResponseSchema,
)
@exception_handler
async def get_user_requests(
    user: Annotated[User, Security(get_current_user)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
    cursor: int | None = Query(
        None,
        description='Cursor for pagination (request ID to start from)',
        examples=[10],
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description='Maximum number of items to return',
        examples=[20],
    ),
) -> AmbulanceRequestsListResponseSchema:
    """Get all ambulance requests with cursor pagination.

    Admin users see all requests in the system.
    Provider users see only their own requests.
    Status history is always included.

    Args:
        cursor: Cursor for pagination (request ID to start from).
        limit: Maximum number of items to return.
        user: Current authenticated user.
        service: Ambulance request service.

    Returns:
        AmbulanceRequestsListResponseSchema: Paginated list of requests.

    """
    items, next_cursor, has_more = await service.get_all_requests(
        user=user,
        cursor=cursor,
        limit=limit,
    )
    return AmbulanceRequestsListResponseSchema(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )
