import logging
from datetime import UTC, datetime, time
from io import BytesIO

from fastapi import UploadFile
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from core import BaseService
from dao import (
    AmbulanceRequestDAO,
    RequestFileDAO,
    RequestStatusHistoryDAO,
    UserDAO,
)
from exceptions import (
    AmbulanceRequestAllFilesUploadFailedException,
    AmbulanceRequestEmptyDocumentEmtpyException,
    AmbulanceRequestEmptyDocumentFileNameException,
    AmbulanceRequestFilesAlreadyLinkedException,
    AmbulanceRequestInvalidFileIdsException,
    AmbulanceRequestInvalidStatusException,
    AmbulanceRequestNotFoundException,
    AmbulanceRequestPDFGenerationException,
    AmbulanceRequestPermissionException,
    IncorrectFileSizeException,
    UnknownFiletypeException,
)
from models import (
    AmbulanceRequest,
    RequestFile,
    RequestStatus,
    User,
    UserRole,
)
from models.ambulance_request import DenialReason, TransportationType
from schemas import (
    AdminRequestWithStatusHistorySchema,
    AdminUpdateRequestSchema,
    AIExtractionResponse,
    AmbulanceRequestResponseSchema,
    CompletionStatus,
    CompletionStatusItem,
    CompletionStatusSchema,
    CreateAmbulanceRequestParseSchema,
    CreateAmbulanceRequestSchema,
    FileUploadResponseSchema,
    FileUploadWithExtractionResponseSchema,
    RequestDocumentSchema,
    RequestStatusHistoryResponseSchema,
    RequestWithStatusHistorySchema,
)
from services.ai.extractor import AIExtractionService
from services.aws.actions import S3Actions
from services.call_sheet import CallSheetService
from services.cms1500_generator import CMS1500GeneratorService
from services.notification import NotificationService
from services.pdf_generator import PDFGeneratorService

logger = logging.getLogger(__name__)

# Validation constants
MIN_NAME_LENGTH = 3
MIN_ADDRESS_LENGTH = 5
EMPTY_FILE_SIZE = 0
MIN_TOTAL_COUNT = 0
DEFAULT_ADMIN_LIMIT = 1000
PRESIGNED_URL_EXPIRATION = 3600  # 1 hour in seconds


class AmbulanceRequestService(BaseService):
    """Service for ambulance request operations."""

    def __init__(
        self,
        db_session: AsyncSession,
        *,
        request_dao: AmbulanceRequestDAO | None = None,
        file_dao: RequestFileDAO | None = None,
        status_history_dao: RequestStatusHistoryDAO | None = None,
        s3_actions: S3Actions | None = None,
        ai_extraction_service: AIExtractionService | None = None,
        notification_service: NotificationService | None = None,
        user_dao: UserDAO | None = None,
        pdf_generator_service: PDFGeneratorService | None = None,
        call_sheet_service: CallSheetService | None = None,
        cms1500_generator_service: CMS1500GeneratorService | None = None,
    ):
        """Initialize AmbulanceRequestService."""
        super().__init__(db_session)
        self._request_dao = request_dao or AmbulanceRequestDAO(db_session)
        self._file_dao = file_dao or RequestFileDAO(db_session)
        self._status_history_dao = (
            status_history_dao or RequestStatusHistoryDAO(db_session)
        )
        self._s3_actions = s3_actions or S3Actions()
        self._ai_extraction_service = (
            ai_extraction_service
            or AIExtractionService(s3_actions=self._s3_actions)
        )
        self._notification_service = (
            notification_service or NotificationService(db_session)
        )
        self._user_dao = user_dao or UserDAO(db_session)
        self._pdf_generator_service = (
            pdf_generator_service or PDFGeneratorService()
        )
        self._call_sheet_service = (
            call_sheet_service or CallSheetService()
        )
        self._cms1500_generator_service = (
            cms1500_generator_service or CMS1500GeneratorService()
        )

    async def upload_file(
        self,
        file: UploadFile,
        user_id: int,
    ) -> FileUploadResponseSchema:
        """Upload a file to S3 and create file record.

        File validation is handled by S3Actions (FileActionMixin).

        Args:
            file: Uploaded file.
            user_id: ID of the user uploading the file.

        Returns:
            FileUploadResponseSchema: Uploaded file information.

        Raises:
            UnknownFiletypeException: If file type is not supported.
            IncorrectFileSizeException: If file size exceeds maximum allowed.

        """
        if not file.filename:
            raise AmbulanceRequestEmptyDocumentFileNameException

        # Read file content
        content = await file.read()
        file_size = len(content)

        if file_size == EMPTY_FILE_SIZE:
            raise AmbulanceRequestEmptyDocumentEmtpyException

        # Convert bytes to BytesIO for S3Actions
        file_obj = BytesIO(content)

        # Upload to S3 using S3Actions (validation happens inside)
        # S3Actions will validate file type and size using FileActionMixin
        s3_key, uploaded_content_type = self._s3_actions.upload_file(
            file_obj=file_obj,
            file_name=file.filename or 'unknown',
            file_size=file_size,
            declared_content_type=file.content_type,
            prefix=f'users/{user_id}/ambulance-requests',
        )

        # Create file record (without request_id for now)
        # We'll link it to request later in step 3
        # Use content_type determined by S3Actions
        request_file = await self._file_dao.create(
            request_id=None,
            # Temporary, will be updated when request is created
            filename=file.filename or 'unknown',
            s3_key=s3_key,
            file_size=file_size,
            content_type=uploaded_content_type,
        )
        await self._session.flush()
        await self._session.commit()
        return FileUploadResponseSchema(
            id=request_file.id,
            filename=request_file.filename,
            file_size=request_file.file_size,
            content_type=request_file.content_type,
            file_url=self._s3_actions.get_presigned_url(
                s3_key,
                expires_in=self._s3_actions.S3_EXPIRATION_TIME,
                require_object=True,
            ),
        )

    async def _extract_s3_keys(
        self, *, files: list[UploadFile], user_id: int
    ) -> list[FileUploadResponseSchema]:
        uploaded_files: list[FileUploadResponseSchema] = []
        errors: list[str] = []

        # Upload files
        for file in files:
            try:
                uploaded_file = await self.upload_file(
                    file=file, user_id=user_id
                )
                uploaded_files.append(uploaded_file)
            except (
                AmbulanceRequestEmptyDocumentFileNameException,
                AmbulanceRequestEmptyDocumentEmtpyException,
                UnknownFiletypeException,
                IncorrectFileSizeException,
            ) as e:
                errors.append(f'{file.filename or "Unknown file"}: {e.detail}')
            except Exception:
                logger.exception('Error uploading file %s', file.filename)
                errors.append(
                    f'{file.filename or "Unknown file"}: Failed to upload'
                )

        if errors:
            if not uploaded_files:
                # If all files failed, raise an exception
                raise AmbulanceRequestAllFilesUploadFailedException(
                    errors=errors
                )
            # If some files succeeded, log errors but continue
            logger.warning('Some files failed to upload: %s', '; '.join(errors))
        return uploaded_files

    async def upload_files(
        self,
        files: list[UploadFile],
        user_id: int,
    ) -> list[FileUploadResponseSchema]:
        """Uploads multiple files to S3 and creates corresponding db records.

        This method processes a batch of uploaded files, saving each
        valid file to cloud storage and registering it in the system.
        It delegates the actual upload logic and error aggregation
        to an internal helper method.

        Args:
            files (list[UploadFile]): A list of file objects
                received from the client request.
            user_id (int): The unique id of the user performing the upload.

        Returns:
            list[FileUploadResponseSchema]: A list of schema objects
                containing details for all successfully uploaded files.

        Raises:
            AmbulanceRequestAllFilesUploadFailedException: If every file
                in the provided list fails to upload due to validation
                or storage errors.

        """
        return await self._extract_s3_keys(files=files, user_id=user_id)

    async def create_request_with_extraction(
        self, request_data: CreateAmbulanceRequestParseSchema, user_id: int
    ) -> FileUploadWithExtractionResponseSchema:
        """Validates file IDs, performs extraction, creates draft request.

        This method checks that all requested files exist in the database
        and are not already linked to another ambulance request.
        If validation passes, it retrieves the corresponding S3 keys
        and delegates processing to the AI extraction service.
        A draft request is created with status DRAFT and linked to the files.

        Args:
            request_data (CreateAmbulanceRequestParseSchema): Schema containing
                the list of file IDs to be processed.
            user_id (int): The ID of the user initiating the extraction request.

        Returns:
            FileUploadWithExtractionResponseSchema: Schema with request ID
                and structured data extracted from documents by AI.

        Raises:
            AmbulanceRequestInvalidFileIdsException: If one or more
                provided file IDs do not exist in the database.
            AmbulanceRequestFilesAlreadyLinkedException: If one or more
                files are
                already associated with an existing ambulance request.

        """
        file_records: list[RequestFile] = await self._file_dao.get_by_ids(
            request_data.file_ids
        )
        # Matches file_records by id for better perf
        file_records_by_id = {
            file_record.id: file_record for file_record in file_records
        }
        # Validate files and check if they're already linked to a request
        file_s3_keys: list[str] = []
        invalid_file_ids: list[int] = []
        linked_file_ids: list[int] = []
        for file_id in request_data.file_ids:
            file_record = file_records_by_id.get(file_id)
            if not file_record:  # File not found
                invalid_file_ids.append(file_id)
            elif file_record.request_id is not None:  # Already linked
                linked_file_ids.append(file_id)
            else:  # Eligible for extraction
                file_s3_keys.append(file_record.s3_key)
        # Validate that all files were found
        if invalid_file_ids:
            raise AmbulanceRequestInvalidFileIdsException(
                invalid_file_ids=invalid_file_ids
            )
        # Check if any files are already linked to a request
        if linked_file_ids:
            raise AmbulanceRequestFilesAlreadyLinkedException
        ai_response: AIExtractionResponse = (
            await self._ai_extraction_service.extract_data_from_files(
                file_s3_keys=file_s3_keys,
                user_id=user_id,
            )
        )
        extracted = ai_response.extracted_data

        # Create draft request with extracted data
        # Use default values for required fields if not extracted

        today = datetime.now(UTC).date()
        draft_request = await self._request_dao.create(
            user_id=user_id,
            transportation_type=extracted.transportation_type
            or TransportationType.AMBULANCE,
            patient_first_name=extracted.patient_first_name or 'Unknown',
            patient_last_name=extracted.patient_last_name or 'Unknown',
            patient_date_of_birth=extracted.patient_date_of_birth or today,
            patient_id=extracted.patient_id or 'TBD',
            date_of_transport=extracted.date_of_transport or today,
            time_of_transport=extracted.time_of_transport or time(12, 0),
            pickup_address=extracted.pickup_address or 'Pending',
            destination_address=extracted.destination_address or 'Pending',
            primary_diagnosis=extracted.primary_diagnosis,
            medical_justification=extracted.medical_justification,
            form_number=extracted.form_number,
            status=RequestStatus.DRAFT,
            ambulatory_status=extracted.ambulatory_status,
            oxygen_required=extracted.oxygen_required,
            ai_accuracy=extracted.confidence_score,
            ordering_physician=extracted.ordering_physician,
            physician_phone=extracted.physician_phone,
            ordering_physician_npi=extracted.ordering_physician_npi,
            patient_sex=extracted.patient_sex,
            insurance_type=extracted.insurance_type,
            insurance_payer_name=extracted.insurance_payer_name,
            insured_id_number=extracted.insured_id_number,
            insured_name=extracted.insured_name,
            patient_relationship_to_insured=(
                extracted.patient_relationship_to_insured
            ),
        )
        await self._session.flush()

        # Link files to draft request
        for file_id in request_data.file_ids:
            await self._file_dao.update_request_id(
                file_id=file_id,
                request_id=draft_request.id,
            )
        await self._session.commit()
        await self._session.refresh(draft_request)

        # Get completion status
        completion_status = await self.get_completion_status(
            request=draft_request
        )

        return FileUploadWithExtractionResponseSchema(
            request_id=draft_request.id,
            extracted_data=ai_response.extracted_data,
            completion_status=completion_status,
        )

    async def create_request(  # noqa: C901,PLR0912, PLR0915
        self,
        user_id: int,
        request_data: CreateAmbulanceRequestSchema,
    ) -> AmbulanceRequestResponseSchema:
        """Update draft request and submit it.

        Args:
            user_id: ID of the user creating the request.
            request_data: Request data with request_id of draft to update.

        Returns:
            AmbulanceRequestResponseSchema: Updated and submitted request.

        """
        # Get existing draft request
        request = await self._request_dao.get_by_id(
            request_id=request_data.request_id,
        )
        if not request:
            raise AmbulanceRequestNotFoundException
        if request.user_id != user_id:
            raise AmbulanceRequestPermissionException
        if request.status != RequestStatus.DRAFT:
            raise AmbulanceRequestInvalidStatusException(  # noqa: TRY003
                'Request is not in DRAFT status'
            )

        # Apply request body to request object BEFORE completion check,
        # so get_completion_status evaluates the data we are about to submit.
        # Use request_data attributes directly (already validated by FastAPI).
        request.transportation_type = request_data.transportation_type
        request.patient_first_name = request_data.patient_first_name
        request.patient_last_name = request_data.patient_last_name
        request.patient_date_of_birth = request_data.patient_date_of_birth
        request.patient_id = request_data.patient_id
        request.date_of_transport = request_data.date_of_transport
        request.time_of_transport = request_data.time_of_transport
        request.pickup_address = request_data.pickup_address
        request.destination_address = request_data.destination_address
        request.oxygen_required = request_data.oxygen_required
        if request_data.primary_diagnosis is not None:
            request.primary_diagnosis = request_data.primary_diagnosis
        if request_data.medical_justification is not None:
            request.medical_justification = request_data.medical_justification
        if request_data.form_number is not None:
            request.form_number = request_data.form_number
        if request_data.ambulatory_status is not None:
            request.ambulatory_status = request_data.ambulatory_status
        if request_data.ordering_physician is not None:
            request.ordering_physician = request_data.ordering_physician
        if request_data.physician_phone is not None:
            request.physician_phone = request_data.physician_phone
        if request_data.ordering_physician_npi is not None:
            request.ordering_physician_npi = (
                request_data.ordering_physician_npi
            )
        if request_data.patient_sex is not None:
            request.patient_sex = request_data.patient_sex
        if request_data.insurance_type is not None:
            request.insurance_type = request_data.insurance_type
        if request_data.insurance_payer_name is not None:
            request.insurance_payer_name = (
                request_data.insurance_payer_name
            )
        if request_data.insured_id_number is not None:
            request.insured_id_number = request_data.insured_id_number
        if request_data.insured_name is not None:
            request.insured_name = request_data.insured_name
        if request_data.patient_relationship_to_insured is not None:
            request.patient_relationship_to_insured = (
                request_data.patient_relationship_to_insured
            )

        # Check if request can be submitted (uses request state we just set)
        completion_status = await self.get_completion_status(request=request)
        if not completion_status.can_submit:
            missing_items = (
                completion_status.missing_fields
                + completion_status.missing_documents
            )
            missing_names = ', '.join([item.name for item in missing_items])
            raise AmbulanceRequestInvalidStatusException(  # noqa: TRY003
                f'Cannot submit request. Missing required items: '
                f'{missing_names}.'
            )

        # status is always updated to SUBMITTED
        request.status = RequestStatus.SUBMITTED
        await self._session.flush()

        # Link any additional files provided in request_data
        if request_data.file_ids:
            for file_id in request_data.file_ids:
                # Check if file exists and belongs to user happens in file_dao usually, but checking here
                # We trust file_ids are valid for the user or we should validate them.
                # Ideally we should validate them, but for now we just link them.
                # Assuming valid IDs from frontend.
                await self._file_dao.update_request_id(
                    file_id=file_id,
                    request_id=request.id,
                )

        await self._status_history_dao.create(
            request_id=request.id,
            status=RequestStatus.SUBMITTED,
            notes='Request submitted',
        )
        await self._session.flush()

        # Create notifications for all admins about the new submitted request
        try:
            admin_users = await self._user_dao.get_all(
                roles=[UserRole.ADMIN],
                limit=DEFAULT_ADMIN_LIMIT,  # Get all admins
            )
            for admin in admin_users:
                try:
                    await self._notification_service.create_status_update_notification(  # noqa: E501
                        user_id=admin.id,
                        request_id=request.id,
                        status_message=f'New request #{request.id}'
                        f' has been submitted for review',
                    )
                except Exception:
                    logger.exception(
                        'Failed to create notification for '
                        'admin %s about request %s',
                        admin.id,
                        request.id,
                    )
        except Exception:
            logger.exception(
                'Failed to create notifications for admins about request %s',
                request.id,
            )

        await self._session.commit()
        await self._session.refresh(request)
        return AmbulanceRequestResponseSchema.model_validate(request)

    async def get_request_by_id(
        self,
        user: User,
        request_id: int,
    ) -> RequestWithStatusHistorySchema | AdminRequestWithStatusHistorySchema:
        """Get request by id.

        Args:
            request_id: Request ID.
            user: User.

        Returns:
            RequestWithStatusHistorySchema: Request information.

        Raises:
            ValueError: If request not found.

        """
        request = await self._request_dao.get_by_id(
            request_id=request_id,
        )
        if not request:
            raise AmbulanceRequestNotFoundException
        # User can see his own requests, or all if he is an admin
        if request.user_id != user.id and user.role != UserRole.ADMIN:
            raise AmbulanceRequestPermissionException

        # If admin opens SUBMITTED request for the first time, change to PENDING
        if (
            user.role == UserRole.ADMIN
            and request.status == RequestStatus.SUBMITTED
        ):
            # Check if request was ever in PENDING status
            status_history = await self._status_history_dao.get_by_request_id(
                request_id=request_id
            )
            has_been_pending = any(
                entry.status == RequestStatus.PENDING
                for entry in status_history
            )
            if not has_been_pending:
                request.status = RequestStatus.PENDING
                await self._session.flush()
                await self._status_history_dao.create(
                    request_id=request_id,
                    status=RequestStatus.PENDING,
                    notes='Request opened by admin for review',
                )
                await self._session.flush()
                # Create notification for the request owner
                try:
                    await self._notification_service.create_status_update_notification(  # noqa: E501
                        user_id=request.user_id,
                        request_id=request_id,
                        status_message=f'Request #{request_id} is now under review',  # noqa: E501
                        # TODO: Move it to some constants
                    )
                except Exception:
                    logger.exception(
                        'Failed to create notification for pending request %s',
                        request_id,
                    )
                await self._session.commit()
                await self._session.refresh(request)

        # Get files and generate presigned URLs
        files = await self._file_dao.get_by_request_id(request_id=request_id)
        logger.info(
            'Found %s files for request %s. File details: %s',
            len(files),
            request_id,
            [
                {'id': f.id, 'request_id': f.request_id, 'filename': f.filename}
                for f in files
            ],
        )
        documents = []
        for file in files:
            try:
                download_url = self._s3_actions.get_presigned_url(
                    key=file.s3_key,
                    expires_in=PRESIGNED_URL_EXPIRATION,
                )
                documents.append(
                    RequestDocumentSchema(
                        id=file.id,
                        filename=file.filename,
                        file_size=file.file_size,
                        content_type=file.content_type,
                        download_url=download_url,
                    )
                )
            except Exception:
                logger.exception(
                    'Failed to generate presigned URL for file %s', file.id
                )
                documents.append(
                    RequestDocumentSchema(
                        id=file.id,
                        filename=file.filename,
                        file_size=file.file_size,
                        content_type=file.content_type,
                        download_url='',
                    )
                )

        # Get completion status
        completion_status = await self.get_completion_status(request=request)

        # Get status history
        status_history = await self._status_history_dao.get_by_request_id(
            request_id=request_id
        )
        status_history_schemas = [
            RequestStatusHistoryResponseSchema.model_validate(entry)
            for entry in status_history
        ]

        # Return different schemas based on user role
        if user.role == UserRole.ADMIN:
            return AdminRequestWithStatusHistorySchema(
                id=request.id,
                user_id=request.user_id,
                transportation_type=request.transportation_type,
                patient_first_name=request.patient_first_name,
                patient_last_name=request.patient_last_name,
                patient_date_of_birth=request.patient_date_of_birth,
                patient_id=request.patient_id,
                date_of_transport=request.date_of_transport,
                time_of_transport=request.time_of_transport,
                pickup_address=request.pickup_address,
                destination_address=request.destination_address,
                primary_diagnosis=request.primary_diagnosis,
                medical_justification=request.medical_justification,
                status=request.status,
                form_number=request.form_number,
                reviewer_id=request.reviewer_id,
                ambulatory_status=request.ambulatory_status,
                oxygen_required=request.oxygen_required,
                ai_accuracy=float(request.ai_accuracy)
                if request.ai_accuracy
                else None,
                ordering_physician=request.ordering_physician,
                physician_phone=request.physician_phone,
                ordering_physician_npi=request.ordering_physician_npi,
                patient_sex=request.patient_sex,
                insurance_type=request.insurance_type,
                insurance_payer_name=request.insurance_payer_name,
                insured_id_number=request.insured_id_number,
                insured_name=request.insured_name,
                patient_relationship_to_insured=(
                    request.patient_relationship_to_insured
                ),
                denial_reason=request.denial_reason,
                denial_notes=request.denial_notes,
                created_at=request.created_at,
                updated_at=request.updated_at,
                status_history=status_history_schemas,
                documents=documents,
                completion_status=completion_status,
            )
        return RequestWithStatusHistorySchema(
            id=request.id,
            user_id=request.user_id,
            patient_first_name=request.patient_first_name,
            patient_last_name=request.patient_last_name,
            primary_diagnosis=request.primary_diagnosis,
            status=request.status,
            pickup_address=request.pickup_address,
            destination_address=request.destination_address,
            transportation_type=request.transportation_type,
            patient_id=request.patient_id,
            form_number=request.form_number,
            created_at=request.created_at,
            updated_at=request.updated_at,
            status_history=status_history_schemas,
            documents=documents,
            completion_status=completion_status,
        )

    async def get_all_requests(
        self,
        user: User,
        *,
        page: int = 1,
        limit: int = 8,
        search: str | None = None,
        status: RequestStatus | None = None,
        days: int | None = None,
    ) -> tuple[
        list[AmbulanceRequestResponseSchema],
        int,
        int,
        int,
        int,
    ]:
        """Get all requests for a user with pagination.

        Admin users see all requests in the system.
        Provider users see only their own requests.
        Status history is always included.

        Args:
            user: User object with role information.
            page: Page number (1-based).
            limit: Number of items per page.
            search: Search term for patient name or ID.
            status: Request status to filter by.
            days: Number of days to filter by (from today).

        Returns:
            tuple containing:
                - List of requests.
                - Total count of requests.
                - Current page number.
                - Total number of pages.

        """
        offset = (page - 1) * limit
        requests: list[AmbulanceRequest] = []
        total: int = 0

        match user.role:
            case UserRole.ADMIN:
                # Admin can see all requests except DRAFT
                total = await self._request_dao.count_all(
                    search=search, status=status, days=days
                )
                requests = await self._request_dao.get_all(
                    offset=offset,
                    limit=limit,
                    search=search,
                    status=status,
                    days=days,
                )
            case _:
                # Provider can see only their own requests
                total = await self._request_dao.count_by_user_id(
                    user_id=user.id,
                    search=search,
                    status=status,
                    days=days,
                )
                requests = await self._request_dao.get_by_user_id(
                    user_id=user.id,
                    offset=offset,
                    limit=limit,
                    search=search,
                    status=status,
                    days=days,
                )

        total_pages = (
            (total + limit - 1) // limit if total > MIN_TOTAL_COUNT else 1
        )
        showing = len(requests)

        return (
            [
                AmbulanceRequestResponseSchema.model_validate(req)
                for req in requests
            ],
            total,
            page,
            total_pages,
            showing,
        )

    async def get_request_status_history(
        self,
        request_id: int,
    ) -> list[RequestStatusHistoryResponseSchema]:
        """Get status history for a request.

        Args:
            request_id: Request ID.

        Returns:
            list[RequestStatusHistoryResponseSchema]: Status history.

        """
        history = await self._status_history_dao.get_by_request_id(
            request_id=request_id
        )
        return [
            RequestStatusHistoryResponseSchema.model_validate(entry)
            for entry in history
        ]

    async def search_by_patient_id_and_name(
        self,
        *,
        user: User,
        patient_id: str | None = None,
        patient_name: str | None = None,
    ) -> list[int]:
        """Search request IDs by patient ID and/or name.

        Admin users see all matching requests.
        Provider users see only their own matching requests.

        Args:
            user: User object with role information.
            patient_id: Optional patient ID to search for.
            patient_name: Optional patient name to search for.

        Returns:
            List of request IDs matching the criteria.

        """
        user_id = None if user.role == UserRole.ADMIN else user.id
        return await self._request_dao.search_by_patient_id_and_name(
            patient_id=patient_id,
            patient_name=patient_name,
            user_id=user_id,
        )

    async def get_completion_status(  # noqa: PLR0912, C901
        self,
        request: AmbulanceRequest,
    ) -> CompletionStatusSchema:
        """Check completion status of a request.

        Validates required fields and documents to determine if request
        can be submitted.

        Args:
            request: AmbulanceRequest to check.

        Returns:
            CompletionStatusSchema: Completion status with details.

        """
        required_fields: list[CompletionStatusItem] = []
        required_documents: list[CompletionStatusItem] = []

        # Check required fields
        # Basic patient information
        if not request.patient_first_name:
            required_fields.append(
                CompletionStatusItem(
                    name='Patient First Name',
                    status=CompletionStatus.MISSING,
                    message='Patient first name is required',
                )
            )
        elif len(request.patient_first_name.strip()) < MIN_NAME_LENGTH:
            required_fields.append(
                CompletionStatusItem(
                    name='Patient First Name',
                    status=CompletionStatus.INCOMPLETE,
                    message='Patient first name must be at least 3 characters',
                )
            )
        else:
            required_fields.append(
                CompletionStatusItem(
                    name='Patient First Name',
                    status=CompletionStatus.COMPLETE,
                )
            )

        if not request.patient_last_name:
            required_fields.append(
                CompletionStatusItem(
                    name='Patient Last Name',
                    status=CompletionStatus.MISSING,
                    message='Patient last name is required',
                )
            )
        elif len(request.patient_last_name.strip()) < MIN_NAME_LENGTH:
            required_fields.append(
                CompletionStatusItem(
                    name='Patient Last Name',
                    status=CompletionStatus.INCOMPLETE,
                    message='Patient last name must be at least 3 characters',
                )
            )
        else:
            required_fields.append(
                CompletionStatusItem(
                    name='Patient Last Name',
                    status=CompletionStatus.COMPLETE,
                )
            )

        if not request.patient_id:
            required_fields.append(
                CompletionStatusItem(
                    name='Patient ID',
                    status=CompletionStatus.MISSING,
                    message=(
                        'Patient Medicare Beneficiary Identifier (MBI) '
                        'is required'
                    ),
                )
            )
        else:
            required_fields.append(
                CompletionStatusItem(
                    name='Patient ID',
                    status=CompletionStatus.COMPLETE,
                )
            )

        if not request.pickup_address or request.pickup_address == 'Pending':
            required_fields.append(
                CompletionStatusItem(
                    name='Pickup Address',
                    status=CompletionStatus.MISSING,
                    message='Pickup address is required',
                )
            )
        elif len(request.pickup_address.strip()) < MIN_ADDRESS_LENGTH:
            required_fields.append(
                CompletionStatusItem(
                    name='Pickup Address',
                    status=CompletionStatus.INCOMPLETE,
                    message='Pickup address must be at least 5 characters',
                )
            )
        else:
            required_fields.append(
                CompletionStatusItem(
                    name='Pickup Address',
                    status=CompletionStatus.COMPLETE,
                )
            )

        if (
            not request.destination_address
            or request.destination_address == 'Pending'
        ):
            required_fields.append(
                CompletionStatusItem(
                    name='Destination Address',
                    status=CompletionStatus.MISSING,
                    message='Destination address is required',
                )
            )
        elif len(request.destination_address.strip()) < MIN_ADDRESS_LENGTH:
            required_fields.append(
                CompletionStatusItem(
                    name='Destination Address',
                    status=CompletionStatus.INCOMPLETE,
                    message='Destination address must be at least 5 characters',
                )
            )
        else:
            required_fields.append(
                CompletionStatusItem(
                    name='Destination Address',
                    status=CompletionStatus.COMPLETE,
                )
            )

        # Check required documents
        files = await self._file_dao.get_by_request_id(request_id=request.id)

        # Check for Verification of Medical Necessity document by content
        # Check for Verification of Medical Necessity document by content
        # Note: We are no longer checking for this as a mandatory requirement
        # to save on LLM costs and reduce friction
        # has_verification = await self._check_verification_document_by_content(
        #     files=files,
        #     form_number=request.form_number,
        # )

        # Filter only missing/incomplete items
        missing_fields = [
            item
            for item in required_fields
            if item.status
            in (CompletionStatus.MISSING, CompletionStatus.INCOMPLETE)
        ]
        missing_documents = [
            item
            for item in required_documents
            if item.status
            in (CompletionStatus.MISSING, CompletionStatus.INCOMPLETE)
        ]

        # Determine overall status
        all_items = required_fields + required_documents
        missing_items = [
            item
            for item in all_items
            if item.status == CompletionStatus.MISSING
        ]
        incomplete_items = [
            item
            for item in all_items
            if item.status == CompletionStatus.INCOMPLETE
        ]

        if missing_items:
            overall_status = CompletionStatus.MISSING
        elif incomplete_items:
            overall_status = CompletionStatus.INCOMPLETE
        else:
            overall_status = CompletionStatus.COMPLETE

        can_submit = overall_status in (
            CompletionStatus.COMPLETE,
            CompletionStatus.INCOMPLETE,
        )

        return CompletionStatusSchema(
            overall_status=overall_status,
            missing_fields=missing_fields,
            missing_documents=missing_documents,
            can_submit=can_submit,
        )

    async def _check_verification_document_by_content(
        self,
        files: list[RequestFile],
        form_number: str | None,
    ) -> bool:
        """Check if Verification of Medical Necessity document exists.

        This method analyzes document content using AI to determine if any
        of the uploaded files contains Verification of Medical Necessity
        information.

        Args:
            files: List of request files to check.
            form_number: Optional form number from the request.

        Returns:
            True if Verification of Medical Necessity document is found,
            False otherwise.

        """
        if not files:
            return False

        # Quick check: if form_number contains CMS-13614,
        # it's likely a Verification form
        if form_number:
            form_lower = form_number.lower()
            if any(keyword in form_lower for keyword in ['13614', 'cms-13614']):
                logger.info(
                    (
                        'Found Verification of Medical Necessity '
                        'based on form_number: %s'
                    ),
                    form_number,
                )
                return True

        # Check document content using AI for each file
        verification_prompt = """You are a medical document analyst.
Analyze the provided document and determine if it is a "Verification of
Medical Necessity" form or document.

A Verification of Medical Necessity document typically contains:
- Form numbers like CMS-13614, CMS-1500, or similar
- Headers/titles mentioning "Verification of Medical Necessity",
  "Certificate of Medical Necessity", or "Medical Necessity Statement"
- Sections about medical justification for transportation
- Physician signatures related to medical necessity
- CMS (Centers for Medicare & Medicaid Services) form references

Respond with ONLY one word: "YES" if this is a Verification of Medical
Necessity document, or "NO" if it is not."""

        for file in files:
            try:
                # Download file from S3
                (
                    file_bytes,
                    content_type,
                ) = await self._ai_extraction_service._download_file_from_s3(  # noqa: SLF001
                    file.s3_key
                )

                # Process document to images
                processor = self._ai_extraction_service._document_processor  # noqa: SLF001
                images = await processor.process_document(
                    file_bytes, content_type
                )

                if not images:
                    continue

                # Build message for AI
                message_content = (
                    self._ai_extraction_service._build_message_content(images)  # noqa: SLF001
                )
                messages = [
                    SystemMessage(content=verification_prompt),
                    HumanMessage(content=message_content),
                ]

                # Call LLM
                response = await self._ai_extraction_service._llm.ainvoke(  # noqa: SLF001
                    messages
                )
                # Handle response content which can be str or list
                if hasattr(response, 'content'):
                    content = response.content
                    if isinstance(content, str):
                        response_text = content.strip().upper()
                    else:
                        # If content is a list, convert to string
                        response_text = str(content).strip().upper()
                else:
                    response_text = str(response).strip().upper()

                logger.info(
                    'AI verification check for file %s (%s): %s',
                    file.filename,
                    file.s3_key,
                    response_text,
                )

                if 'YES' in response_text:
                    logger.info(
                        'Found Verification of Medical Necessity in file: %s',
                        file.filename,
                    )
                    return True

            except Exception:
                logger.exception(
                    (
                        'Failed to check Verification of Medical Necessity '
                        'for file %s'
                    ),
                    file.filename,
                )
                # Continue checking other files if one fails
                continue

        return False

    async def update_request_status(
        self,
        request_id: int,
        new_status: RequestStatus,
        notes: str | None = None,
    ) -> AmbulanceRequestResponseSchema:
        """Update the status of an existing ambulance request.

        Args:
            request_id (int): ID of the request to update.
            new_status (RequestStatus): New status value to apply.
            notes (str | None): Optional notes describing the status update.

        Returns:
            AmbulanceRequestResponseSchema: Updated request information.

        Raises:
            AmbulanceRequestNotFoundException: If the request does not exist.

        """
        request = await self._request_dao.get_by_id(request_id=request_id)
        if not request:
            raise AmbulanceRequestNotFoundException
        request.status = new_status
        await self._session.flush()
        await self._status_history_dao.create(
            request_id=request_id,
            status=new_status,
            notes=notes,
        )
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(request)

        return AmbulanceRequestResponseSchema.model_validate(request)

    async def approve_request(
        self,
        request_id: int,
        reviewer_id: int,
    ) -> AmbulanceRequestResponseSchema:
        """Approve an ambulance request.

        Args:
            request_id: ID of the request to approve.
            reviewer_id: ID of the admin reviewing the request.

        Returns:
            AmbulanceRequestResponseSchema: Approved request.

        Raises:
            AmbulanceRequestNotFoundException: If the request does not exist.

        """
        request = await self._request_dao.get_by_id(request_id=request_id)
        if not request:
            raise AmbulanceRequestNotFoundException

        if request.status not in (
            RequestStatus.SUBMITTED,
            RequestStatus.PENDING,
        ):
            raise AmbulanceRequestInvalidStatusException(  # noqa: TRY003
                f'Cannot approve request in {request.status} status'
            )

        request.status = RequestStatus.APPROVED
        request.reviewer_id = reviewer_id
        request.denial_reason = None
        request.denial_notes = None
        await self._session.flush()
        await self._status_history_dao.create(
            request_id=request_id,
            status=RequestStatus.APPROVED,
            notes='Request approved by admin',
        )
        await self._session.flush()
        # Create notification for the request owner
        try:
            await self._notification_service.create_status_update_notification(
                user_id=request.user_id,
                request_id=request_id,
                status_message=f'Request #{request_id} has been approved',
            )
        except Exception:
            logger.exception(
                'Failed to create notification for approved request %s',
                request_id,
            )
        await self._session.commit()
        await self._session.refresh(request)

        return AmbulanceRequestResponseSchema.model_validate(request)

    async def deny_request(
        self,
        request_id: int,
        reviewer_id: int,
        denial_reason: 'DenialReason',
        denial_notes: str | None = None,
    ) -> AmbulanceRequestResponseSchema:
        """Deny an ambulance request.

        Args:
            request_id: ID of the request to deny.
            reviewer_id: ID of the admin reviewing the request.
            denial_reason: Reason for denial.
            denial_notes: Additional notes
                (required if denial_reason is OTHER_REASON).

        Returns:
            AmbulanceRequestResponseSchema: Denied request.

        Raises:
            AmbulanceRequestNotFoundException: If the request does not exist.
            ValueError: If denial_notes is missing for OTHER_REASON.

        """
        if denial_reason == DenialReason.OTHER_REASON and not denial_notes:
            raise AmbulanceRequestInvalidStatusException(  # noqa: TRY003
                'denial_notes is required when denial_reason is OTHER_REASON'
            )

        request = await self._request_dao.get_by_id(request_id=request_id)
        if not request:
            raise AmbulanceRequestNotFoundException
        request.status = RequestStatus.DENIED
        request.reviewer_id = reviewer_id
        request.denial_reason = denial_reason
        request.denial_notes = denial_notes
        await self._session.flush()
        await self._status_history_dao.create(
            request_id=request_id,
            status=RequestStatus.DENIED,
            notes=f'Request denied: {denial_reason.value}',
        )
        await self._session.flush()
        # Create notification for the request owner
        try:
            await self._notification_service.create_status_update_notification(
                user_id=request.user_id,
                request_id=request_id,
                status_message=f'Request #{request_id} has been denied',
            )
        except Exception:
            logger.exception(
                'Failed to create notification for denied request %s',
                request_id,
            )
        await self._session.commit()
        await self._session.refresh(request)

        return AmbulanceRequestResponseSchema.model_validate(request)

    async def update_request_by_admin(  # noqa: PLR0915, PLR0912, C901
        self,
        request_id: int,
        update_data: AdminUpdateRequestSchema,
    ) -> AdminRequestWithStatusHistorySchema:
        """Update request fields by admin.

        Admin can update all fields except ai_accuracy and status.

        Args:
            request_id: ID of the request to update.
            update_data: Data to update.

        Returns:
            AdminRequestWithStatusHistorySchema: Updated request.

        Raises:
            AmbulanceRequestNotFoundException: If the request does not exist.

        """
        request = await self._request_dao.get_by_id(request_id=request_id)
        if not request:
            raise AmbulanceRequestNotFoundException

        # Update only provided fields
        if update_data.transportation_type is not None:
            request.transportation_type = update_data.transportation_type
        if update_data.patient_first_name is not None:
            request.patient_first_name = update_data.patient_first_name
        if update_data.patient_last_name is not None:
            request.patient_last_name = update_data.patient_last_name
        if update_data.patient_date_of_birth is not None:
            request.patient_date_of_birth = update_data.patient_date_of_birth
        if update_data.patient_id is not None:
            request.patient_id = update_data.patient_id
        if update_data.date_of_transport is not None:
            request.date_of_transport = update_data.date_of_transport
        if update_data.time_of_transport is not None:
            request.time_of_transport = update_data.time_of_transport
        if update_data.pickup_address is not None:
            request.pickup_address = update_data.pickup_address
        if update_data.destination_address is not None:
            request.destination_address = update_data.destination_address
        if update_data.primary_diagnosis is not None:
            request.primary_diagnosis = update_data.primary_diagnosis
        if update_data.medical_justification is not None:
            request.medical_justification = update_data.medical_justification
        if update_data.form_number is not None:
            request.form_number = update_data.form_number
        if update_data.reviewer_id is not None:
            request.reviewer_id = update_data.reviewer_id
        if update_data.ambulatory_status is not None:
            request.ambulatory_status = update_data.ambulatory_status
        if update_data.oxygen_required is not None:
            request.oxygen_required = update_data.oxygen_required
        if update_data.ordering_physician is not None:
            request.ordering_physician = update_data.ordering_physician
        if update_data.physician_phone is not None:
            request.physician_phone = update_data.physician_phone
        if update_data.ordering_physician_npi is not None:
            request.ordering_physician_npi = (
                update_data.ordering_physician_npi
            )
        if update_data.patient_sex is not None:
            request.patient_sex = update_data.patient_sex
        if update_data.insurance_type is not None:
            request.insurance_type = update_data.insurance_type
        if update_data.insurance_payer_name is not None:
            request.insurance_payer_name = update_data.insurance_payer_name
        if update_data.insured_id_number is not None:
            request.insured_id_number = update_data.insured_id_number
        if update_data.insured_name is not None:
            request.insured_name = update_data.insured_name
        if update_data.patient_relationship_to_insured is not None:
            request.patient_relationship_to_insured = (
                update_data.patient_relationship_to_insured
            )
        if update_data.denial_reason is not None:
            request.denial_reason = update_data.denial_reason
        if update_data.denial_notes is not None:
            request.denial_notes = update_data.denial_notes

        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(request)

        # Get files and generate presigned URLs
        files = await self._file_dao.get_by_request_id(request_id=request_id)
        documents = []
        for file in files:
            try:
                download_url = self._s3_actions.get_presigned_url(
                    key=file.s3_key,
                    expires_in=PRESIGNED_URL_EXPIRATION,
                )
                documents.append(
                    RequestDocumentSchema(
                        id=file.id,
                        filename=file.filename,
                        file_size=file.file_size,
                        content_type=file.content_type,
                        download_url=download_url,
                    )
                )
            except Exception:
                logger.exception(
                    'Failed to generate presigned URL for file %s', file.id
                )
                documents.append(
                    RequestDocumentSchema(
                        id=file.id,
                        filename=file.filename,
                        file_size=file.file_size,
                        content_type=file.content_type,
                        download_url='',
                    )
                )

        # Get completion status
        completion_status = await self.get_completion_status(request=request)

        # Get status history
        status_history = await self._status_history_dao.get_by_request_id(
            request_id=request_id
        )
        status_history_schemas = [
            RequestStatusHistoryResponseSchema.model_validate(entry)
            for entry in status_history
        ]

        # Manually construct response with all required fields
        return AdminRequestWithStatusHistorySchema(
            id=request.id,
            user_id=request.user_id,
            transportation_type=request.transportation_type,
            patient_first_name=request.patient_first_name,
            patient_last_name=request.patient_last_name,
            patient_date_of_birth=request.patient_date_of_birth,
            patient_id=request.patient_id,
            date_of_transport=request.date_of_transport,
            time_of_transport=request.time_of_transport,
            pickup_address=request.pickup_address,
            destination_address=request.destination_address,
            primary_diagnosis=request.primary_diagnosis,
            medical_justification=request.medical_justification,
            status=request.status,
            form_number=request.form_number,
            reviewer_id=request.reviewer_id,
            ambulatory_status=request.ambulatory_status,
            oxygen_required=request.oxygen_required,
            ai_accuracy=float(request.ai_accuracy)
            if request.ai_accuracy
            else None,
            ordering_physician=request.ordering_physician,
            physician_phone=request.physician_phone,
            ordering_physician_npi=request.ordering_physician_npi,
            patient_sex=request.patient_sex,
            insurance_type=request.insurance_type,
            insurance_payer_name=request.insurance_payer_name,
            insured_id_number=request.insured_id_number,
            insured_name=request.insured_name,
            patient_relationship_to_insured=(
                request.patient_relationship_to_insured
            ),
            denial_reason=request.denial_reason,
            denial_notes=request.denial_notes,
            created_at=request.created_at,
            updated_at=request.updated_at,
            status_history=status_history_schemas,
            documents=documents,
            completion_status=completion_status,
        )

    async def generate_pdf(
        self,
        request_id: int,
        user: User,
    ) -> bytes:
        """Generate CMS-10344 PDF for a request.

        Args:
            request_id: ID of the request to generate PDF for.
            user: Current authenticated user.

        Returns:
            bytes: PDF file bytes.

        Raises:
            AmbulanceRequestNotFoundException: If request not found.
            AmbulanceRequestPermissionException: If user doesn't have
                permission.
            AmbulanceRequestPDFGenerationException: If request has missing
                fields.

        """
        # Get request
        request = await self._request_dao.get_by_id(request_id=request_id)
        if not request:
            raise AmbulanceRequestNotFoundException

        # Check permissions: admin can download any, provider only their own
        if request.user_id != user.id and user.role != UserRole.ADMIN:
            raise AmbulanceRequestPermissionException

        # Check completion status - PDF can only be generated
        # if all validations pass
        completion_status = await self.get_completion_status(request=request)
        if not completion_status.can_submit:
            missing_items = (
                completion_status.missing_fields
                + completion_status.missing_documents
            )
            missing_names = ', '.join([item.name for item in missing_items])
            error_msg = (
                f'Cannot generate PDF. Missing required items: '
                f'{missing_names}. All required fields and documents '
                f'must be completed before PDF can be generated.'
            )
            raise AmbulanceRequestPDFGenerationException(error_msg)

        # Generate PDF
        pdf_bytes = self._pdf_generator_service.generate_cms_10344_pdf(
            request=request
        )

        logger.info(
            'Generated CMS-10344 PDF for request %s (size: %d bytes)',
            request_id,
            len(pdf_bytes),
        )

        return pdf_bytes

    async def generate_call_sheet_pdf(
        self,
        request_id: int,
        user: User,
    ) -> bytes:
        """Generate a Call Sheet PDF for a request.

        Unlike the CMS-10344 PDF, the Call Sheet is an operational
        dispatch document, not a regulatory submission, so it can be
        generated as soon as the request exists - it does not require
        the same full completion-status validation.

        Args:
            request_id: ID of the request to generate the Call Sheet for.
            user: Current authenticated user.

        Returns:
            bytes: Filled (but not flattened) Call Sheet PDF file bytes.

        Raises:
            AmbulanceRequestNotFoundException: If request not found.
            AmbulanceRequestPermissionException: If user doesn't have
                permission.

        """
        request = await self._request_dao.get_by_id(request_id=request_id)
        if not request:
            raise AmbulanceRequestNotFoundException

        if request.user_id != user.id and user.role != UserRole.ADMIN:
            raise AmbulanceRequestPermissionException

        pdf_bytes = self._call_sheet_service.generate_call_sheet_pdf(
            request=request
        )

        logger.info(
            'Generated Call Sheet PDF for request %s (size: %d bytes)',
            request_id,
            len(pdf_bytes),
        )

        return pdf_bytes

    async def generate_cms1500_pdf(
        self,
        request_id: int,
        user: User,
    ) -> bytes:
        """Generate a CMS-1500 claim data summary PDF for a request.

        Like the Call Sheet, this does not require full completion-status
        validation - it is a data summary reviewable at any stage, and
        clearly marks which CMS-1500 fields (service lines, billing
        provider info) are not yet available from prior authorization
        data.

        Args:
            request_id: ID of the request to generate the CMS-1500 for.
            user: Current authenticated user.

        Returns:
            bytes: CMS-1500 PDF file bytes.

        Raises:
            AmbulanceRequestNotFoundException: If request not found.
            AmbulanceRequestPermissionException: If user doesn't have
                permission.

        """
        request = await self._request_dao.get_by_id(request_id=request_id)
        if not request:
            raise AmbulanceRequestNotFoundException

        if request.user_id != user.id and user.role != UserRole.ADMIN:
            raise AmbulanceRequestPermissionException

        pdf_bytes = self._cms1500_generator_service.generate_cms1500_pdf(
            request=request
        )

        logger.info(
            'Generated CMS-1500 PDF for request %s (size: %d bytes)',
            request_id,
            len(pdf_bytes),
        )

        return pdf_bytes
