import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
)
from fastapi.params import Security

from core import exception_handler, get_service, timing_handler
from dependencies import (
    get_admin_user_from_token,
    get_current_user,
    get_provider_user_from_token,
)
from exceptions import AmbulanceRequestSearchParametersMissingException
from models import RequestStatus, User
from schemas.ambulance_request import (
    AdminRequestWithStatusHistorySchema,
    AdminUpdateRequestSchema,
    AmbulanceRequestResponseSchema,
    AmbulanceRequestsListResponseSchema,
    ApproveRequestSchema,
    CreateAmbulanceRequestParseSchema,
    CreateAmbulanceRequestSchema,
    DenyRequestSchema,
    FileUploadResponseSchema,
    FileUploadWithExtractionResponseSchema,
    RequestWithStatusHistorySchema,
)
from schemas.search import SearchRequestsResponseSchema
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
    """Triggers AI extraction of medical data and creates draft request.

    This endpoint acts as the second step in the request workflow.
    It takes a list of file IDs (uploaded in Step 1), validates them, and
    sends the documents to an AI service to parse medical details.
    A draft request is created with status DRAFT and its ID is returned.

    Args:
        request_data (CreateAmbulanceRequestParseSchema): The input payload
            containing the list of file IDs to be analyzed.
        user (User): The currently authenticated provider user.
        service (AmbulanceRequestService): The injected service instance.

    Returns:
        FileUploadWithExtractionResponseSchema: The structured data
            extracted from the medical documents and the created request ID.

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
    """Update draft request and submit it.

    This endpoint updates an existing draft request with verified data
    and changes its status to SUBMITTED.

    Args:
        request_data: Request data with request_id and verified information.
        user: Current authenticated user.
        service: Ambulance request service.

    Returns:
        AmbulanceRequestResponseSchema: Updated and submitted request.

    Raises:
        HTTPException: If request update fails.

    """
    return await service.create_request(
        user_id=user.id, request_data=request_data
    )


@ambulance_request_router.get(
    '/search',
    description='Search requests by patient ID and/or name',
    summary='Search requests by patient',
    response_model=SearchRequestsResponseSchema,
)
@exception_handler
async def search_requests(
    user: Annotated[User, Security(get_current_user)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
    patient_id: str | None = Query(
        None,
        description='Patient ID to search for',
        examples=['1EG4-TE5-MK72'],
    ),
    patient_name: str | None = Query(
        None,
        description='Patient name to search for (matches first name',
        examples=['John', 'Doe', 'John Doe'],
    ),
) -> SearchRequestsResponseSchema:
    """Search requests by patient ID and/or name.

    Returns list of request IDs matching the search criteria.
    At least one parameter (patient_id or patient_name) must be provided.

    Args:
        user: Current authenticated admin user.
        service: Ambulance request service.
        patient_id: Optional patient ID to search for.
        patient_name: Optional patient name to search for.

    Returns:
        SearchRequestsResponseSchema: List of request IDs.

    Raises:
        AmbulanceRequestSearchParametersMissingException: If both parameters
         are None.

    """
    if patient_id is None and patient_name is None:
        raise AmbulanceRequestSearchParametersMissingException

    request_ids = await service.search_by_patient_id_and_name(
        user=user,
        patient_id=patient_id,
        patient_name=patient_name,
    )
    return SearchRequestsResponseSchema(request_ids=request_ids)


@ambulance_request_router.get(
    '/{request_id}/download-pdf',
    description='Download CMS-10344 PDF form for a request',
    summary='Download CMS-10344 PDF',
    response_class=Response,
)
@exception_handler
async def download_pdf(
    request_id: int,
    user: Annotated[User, Security(get_current_user)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> Response:
    """Download CMS-10344 PDF form for a request.

    Admin users can download PDF for any request.
    Provider users can only download PDF for their own requests.

    PDF is only generated if all validation checks pass (all required fields
    and documents are present).

    Args:
        request_id: Request ID to generate PDF for.
        user: Current authenticated user (admin or provider).
        service: Ambulance request service.

    Returns:
        Response: PDF file as downloadable attachment.

    Raises:
        HTTPException: If request not found, permission denied,
            or validation fails.

    """
    pdf_bytes = await service.generate_pdf(request_id=request_id, user=user)

    # Generate filename with request ID and timestamp
    timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
    filename = f'CMS-10344_Request-{request_id}_{timestamp}.pdf'

    return Response(
        content=pdf_bytes,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
        },
    )


@ambulance_request_router.get(
    '/{request_id}/call-sheet-pdf',
    description='Download Call Sheet PDF for a request',
    summary='Download Call Sheet PDF',
    response_class=Response,
)
@exception_handler
async def download_call_sheet_pdf(
    request_id: int,
    user: Annotated[User, Security(get_current_user)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> Response:
    """Download Call Sheet PDF for a request.

    Admin users can download the Call Sheet for any request.
    Provider users can only download it for their own requests.

    The Call Sheet is pre-filled with the fields known from the request
    (patient name, origin, destination, date of service, ordering
    physician); everything else on the form (vitals, chief complaint,
    medications, times, driver/attendant, etc.) is left blank and
    fillable for the crew to complete during the actual transport.

    Args:
        request_id: Request ID to generate the Call Sheet for.
        user: Current authenticated user (admin or provider).
        service: Ambulance request service.

    Returns:
        Response: PDF file as downloadable attachment.

    Raises:
        HTTPException: If request not found or permission denied.

    """
    pdf_bytes = await service.generate_call_sheet_pdf(
        request_id=request_id, user=user
    )

    timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
    filename = f'Call-Sheet_Request-{request_id}_{timestamp}.pdf'

    return Response(
        content=pdf_bytes,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
        },
    )


@ambulance_request_router.get(
    '/{request_id}/cms1500-pdf',
    description='Download CMS-1500 claim data summary PDF for a request',
    summary='Download CMS-1500 PDF',
    response_class=Response,
)
@exception_handler
async def download_cms1500_pdf(
    request_id: int,
    user: Annotated[User, Security(get_current_user)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> Response:
    """Download CMS-1500 claim data summary PDF for a request.

    Admin users can download the CMS-1500 summary for any request.
    Provider users can only download it for their own requests.

    This is a data summary of the CMS-1500 fields available from prior
    authorization data (insurance, patient, diagnosis, referring
    physician), labeled with the form's real box numbers. Service-line
    and billing provider data (Boxes 24, 25, 32, 33) are not available
    from this system and are called out on the document for billing
    staff to complete.

    Args:
        request_id: Request ID to generate the CMS-1500 summary for.
        user: Current authenticated user (admin or provider).
        service: Ambulance request service.

    Returns:
        Response: PDF file as downloadable attachment.

    Raises:
        HTTPException: If request not found or permission denied.

    """
    pdf_bytes = await service.generate_cms1500_pdf(
        request_id=request_id, user=user
    )

    timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
    filename = f'CMS-1500_Request-{request_id}_{timestamp}.pdf'

    return Response(
        content=pdf_bytes,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
        },
    )


@ambulance_request_router.get(
    '/{request_id}',
    description='Get ambulance request by ID',
    response_model=RequestWithStatusHistorySchema
    | AdminRequestWithStatusHistorySchema,
)
@exception_handler
async def get_request(
    request_id: int,
    user: Annotated[User, Security(get_current_user)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> RequestWithStatusHistorySchema | AdminRequestWithStatusHistorySchema:
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
    description='Get all ambulance requests with pagination',
    response_model=AmbulanceRequestsListResponseSchema,
)
@exception_handler
async def get_user_requests(
    user: Annotated[User, Security(get_current_user)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
    page: int = Query(
        1,
        ge=1,
        description='Page number (1-based)',
        examples=[1],
    ),
    search: str | None = Query(
        None,
        description='Search by patient first name, last name, or patient ID',
        examples=['John'],
    ),
    status: str | None = Query(
        None,
        description='Filter by request status',
        examples=['pending'],
    ),
    days: int | None = Query(
        None,
        description='Filter by number of days (0=today, 7, 30, 90, 365)',
        examples=[7],
    ),
) -> AmbulanceRequestsListResponseSchema:
    """Get all ambulance requests with pagination.

    Admin users see all requests in the system.
    Provider users see only their own requests.
    Status history is always included.

    Args:
        page: Page number (1-based).
        search: Search term for patient name or ID.
        status: Request status to filter by.
        days: Number of days to filter by (0=today, 7, 30, 90, 365).
        user: Current authenticated user.
        service: Ambulance request service.

    Returns:
        AmbulanceRequestsListResponseSchema: Paginated list of requests.

    """
    status_enum: RequestStatus | None = None
    if status:
        try:
            status_enum = RequestStatus(status.lower())
        except ValueError:
            status_enum = None

    (
        items,
        total,
        current_page,
        total_pages,
        showing,
    ) = await service.get_all_requests(
        user=user,
        page=page,
        limit=8,
        search=search,
        status=status_enum,
        days=days,
    )
    return AmbulanceRequestsListResponseSchema(
        items=items,
        page=current_page,
        total=total,
        showing=showing,
        total_pages=total_pages,
    )


@ambulance_request_router.post(
    '/{request_id}/approve',
    description='Approve an ambulance request (admin only)',
    summary='Approve request',
    response_model=AmbulanceRequestResponseSchema,
)
@exception_handler
async def approve_request(
    request_id: int,
    request_data: ApproveRequestSchema,
    user: Annotated[User, Security(get_admin_user_from_token)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> AmbulanceRequestResponseSchema:
    """Approve an ambulance request.

    Only admin users can approve requests.

    Args:
        request_id: Request ID to approve.
        request_data: Approval data (empty schema).
        user: Current authenticated user (must be admin).
        service: Ambulance request service.

    Returns:
        AmbulanceRequestResponseSchema: Approved request.

    Raises:
        HTTPException: If user is not admin, request not found, or approval.

    """
    return await service.approve_request(
        request_id=request_id,
        reviewer_id=user.id,
    )


@ambulance_request_router.post(
    '/{request_id}/submit-to-novitas',
    description=(
        'Fax the Novitas prior-authorization package for a request '
        '(admin only)'
    ),
    summary='Submit to Novitas',
    response_model=AmbulanceRequestResponseSchema,
)
@exception_handler
async def submit_to_novitas(
    request_id: int,
    user: Annotated[User, Security(get_admin_user_from_token)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> AmbulanceRequestResponseSchema:
    """Fax the Novitas prior-authorization package for a request.

    Only admin users can submit to Novitas, and only after the request
    has been approved. Builds and sends the CMS-10344 authorization
    form plus any uploaded supporting documents in a single fax.

    Args:
        request_id: Request ID to submit.
        user: Current authenticated user (must be admin).
        service: Ambulance request service.

    Returns:
        AmbulanceRequestResponseSchema: Updated request.

    Raises:
        HTTPException: If user is not admin, request not found, not
            approved, already submitted, or the fax fails to send.

    """
    return await service.submit_to_novitas(
        request_id=request_id,
        user=user,
    )


@ambulance_request_router.post(
    '/{request_id}/deny',
    description='Deny an ambulance request (admin only)',
    summary='Deny request',
    response_model=AmbulanceRequestResponseSchema,
)
@exception_handler
async def deny_request(
    request_id: int,
    request_data: DenyRequestSchema,
    user: Annotated[User, Security(get_admin_user_from_token)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> AmbulanceRequestResponseSchema:
    """Deny an ambulance request.

    Only admin users can deny requests.
    If denial_reason is OTHER_REASON, denial_notes is required.

    Args:
        request_id: Request ID to deny.
        request_data: Denial data with reason and optional notes.
        user: Current authenticated user (must be admin).
        service: Ambulance request service.

    Returns:
        AmbulanceRequestResponseSchema: Denied request.

    Raises:
        HTTPException: If user is not admin, request not found, or denial fails.

    """
    return await service.deny_request(
        request_id=request_id,
        reviewer_id=user.id,
        denial_reason=request_data.denial_reason,
        denial_notes=request_data.denial_notes,
    )


@ambulance_request_router.patch(
    '/{request_id}',
    description='Update ambulance request fields (admin only)',
    summary='Update request by admin',
    response_model=AdminRequestWithStatusHistorySchema,
)
@exception_handler
async def update_request_by_admin(
    request_id: int,
    update_data: AdminUpdateRequestSchema,
    user: Annotated[User, Security(get_admin_user_from_token)],
    service: Annotated[
        AmbulanceRequestService, Depends(get_service(AmbulanceRequestService))
    ],
) -> AdminRequestWithStatusHistorySchema:
    """Update ambulance request fields by admin.

    Admin can update all fields except ai_accuracy and status.
    Only admin users can update requests.

    Args:
        request_id: Request ID to update.
        update_data: Data to update (all fields optional).
        user: Current authenticated user (must be admin).
        service: Ambulance request service.

    Returns:
        AdminRequestWithStatusHistorySchema: Updated request with all fields.

    Raises:
        HTTPException: If user is not admin, request not found, or update fails.

    """
    return await service.update_request_by_admin(
        request_id=request_id,
        update_data=update_data,
    )
