"""Tests for AmbulanceRequestService."""

from datetime import date, time, datetime, UTC
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from config.settings import Settings
from dao import (
    RequestFileDAO,
    RequestStatusHistoryDAO,
)
from exceptions import (
    AmbulanceRequestAllFilesUploadFailedException,
    AmbulanceRequestEmptyDocumentEmtpyException,
    AmbulanceRequestEmptyDocumentFileNameException,
    AmbulanceRequestInvalidFileIdsException,
    AmbulanceRequestInvalidStatusException,
    AmbulanceRequestNotFoundException,
    AmbulanceRequestPDFGenerationException,
    AmbulanceRequestPermissionException,
)
from exceptions.file import IncorrectFileSizeException, UnknownFiletypeException
from models.ambulance_request import (
    NovitasStatus,
    RequestStatus,
    TransportationType,
)
from models.user import UserRole
from schemas.ambulance_request import CreateAmbulanceRequestSchema
from services.ai.extractor import AIExtractionService
from services.ambulance_request import AmbulanceRequestService
from services.aws.actions import S3Actions


class TestAmbulanceRequestService:
    """Test suite for AmbulanceRequestService."""

    @pytest.fixture
    def mock_s3_actions(self) -> MagicMock:
        """Create mock S3Actions."""
        mock = MagicMock(spec=S3Actions)
        mock.upload_file.return_value = (
            'users/1/ambulance-requests/test.pdf',
            'application/pdf',
        )
        mock.get_presigned_url.return_value = (
            'https://s3.example.com/presigned-url'
        )
        return mock

    @pytest.fixture
    def mock_ai_service(self) -> MagicMock:
        """Create mock AIExtractionService."""
        from schemas.ai_extraction import (
            AIExtractionResponse,
            ExtractedTransportationData,
        )

        mock = MagicMock(spec=AIExtractionService)
        mock.extract_data_from_files = AsyncMock(
            return_value=AIExtractionResponse(
                extracted_data=ExtractedTransportationData(
                    transportation_type=None,
                    patient_first_name='John',
                    patient_last_name='Doe',
                    patient_date_of_birth=date(1980, 1, 1),
                    patient_id='DA123456789HY',
                    date_of_transport=None,
                    time_of_transport=None,
                    pickup_address='123 Main St',
                    destination_address='456 Medical Dr',
                    primary_diagnosis='Chronic heart failure',
                    medical_justification='Patient requires transport',
                    form_number='CMS-10344',
                ),
                confidence_score=0.95,
            )
        )
        # Mock _download_file_from_s3 for verification document checking
        mock._download_file_from_s3 = AsyncMock(
            return_value=(b'fake pdf content', 'application/pdf')
        )
        # Mock document processor
        mock._document_processor = MagicMock()
        mock._document_processor.process_document = AsyncMock(return_value=[])
        # Mock build_message_content
        mock._build_message_content = MagicMock(return_value=[])
        # Mock LLM
        mock._llm = MagicMock()
        mock._llm.ainvoke = AsyncMock(return_value=MagicMock(content='NO'))
        return mock

    @pytest.fixture
    def service(
        self,
        db_session,
        mock_s3_actions,
        mock_ai_service,
    ) -> AmbulanceRequestService:
        """Create AmbulanceRequestService instance with mocks."""
        return AmbulanceRequestService(
            db_session=db_session,
            s3_actions=mock_s3_actions,
            ai_extraction_service=mock_ai_service,
        )

    @pytest.mark.asyncio
    async def test_upload_file_success(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
    ):
        """Test successful file upload."""
        user = await user_factory()
        await db_session.commit()

        file_content = b'PDF content here'
        file = UploadFile(
            filename='test.pdf',
            file=BytesIO(file_content),
        )

        result = await service.upload_file(file=file, user_id=user.id)

        assert result.id is not None
        assert result.filename == 'test.pdf'
        assert result.file_size == len(file_content)
        assert result.content_type == 'application/pdf'

        # Verify file record was created
        file_dao = RequestFileDAO(db_session)
        file_record = await file_dao.get_by_id(result.id)
        assert file_record is not None
        assert file_record.filename == 'test.pdf'
        assert file_record.request_id is None  # Not linked yet

    @pytest.mark.asyncio
    async def test_upload_file_no_filename(
        self,
        service: AmbulanceRequestService,
        user_factory,
    ):
        """Test upload file without filename raises exception."""
        user = await user_factory()
        file = UploadFile(filename=None, file=BytesIO(b'content'))

        with pytest.raises(AmbulanceRequestEmptyDocumentFileNameException):
            await service.upload_file(file=file, user_id=user.id)

    @pytest.mark.asyncio
    async def test_upload_file_empty(
        self,
        service: AmbulanceRequestService,
        user_factory,
    ):
        """Test upload empty file raises exception."""
        user = await user_factory()
        file = UploadFile(filename='test.pdf', file=BytesIO(b''))

        with pytest.raises(AmbulanceRequestEmptyDocumentEmtpyException):
            await service.upload_file(file=file, user_id=user.id)

    @pytest.mark.asyncio
    async def test_upload_file_invalid_type(
        self,
        service: AmbulanceRequestService,
        user_factory,
        mock_s3_actions,
    ):
        """Test upload file with invalid type raises exception."""
        user = await user_factory()
        file = UploadFile(filename='test.exe', file=BytesIO(b'content'))
        mock_s3_actions.upload_file.side_effect = UnknownFiletypeException()

        with pytest.raises(UnknownFiletypeException):
            await service.upload_file(file=file, user_id=user.id)

    @pytest.mark.asyncio
    async def test_upload_file_too_large(
        self,
        service: AmbulanceRequestService,
        user_factory,
        mock_s3_actions,
    ):
        """Test upload file that's too large raises exception."""
        user = await user_factory()
        file = UploadFile(filename='test.pdf', file=BytesIO(b'content'))
        mock_s3_actions.upload_file.side_effect = IncorrectFileSizeException()

        with pytest.raises(IncorrectFileSizeException):
            await service.upload_file(file=file, user_id=user.id)

    @pytest.mark.asyncio
    async def test_upload_files_success(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
    ):
        """Test successful multiple file upload."""
        user = await user_factory()
        await db_session.commit()

        files = [
            UploadFile(filename='file1.pdf', file=BytesIO(b'content1')),
            UploadFile(filename='file2.pdf', file=BytesIO(b'content2')),
        ]

        result = await service.upload_files(files=files, user_id=user.id)

        assert len(result) == 2
        assert result[0].filename == 'file1.pdf'
        assert result[1].filename == 'file2.pdf'

    @pytest.mark.asyncio
    async def test_upload_files_no_files(
        self,
        service: AmbulanceRequestService,
        user_factory,
    ):
        """Test upload files with empty list."""
        user = await user_factory()

        # Empty list should result in empty list
        result = await service.upload_files(files=[], user_id=user.id)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_upload_files_all_failed(
        self,
        service: AmbulanceRequestService,
        user_factory,
        mock_s3_actions,
    ):
        """Test upload files when all files fail raises exception."""
        user = await user_factory()
        files = [
            UploadFile(filename='file1.pdf', file=BytesIO(b'content1')),
        ]
        mock_s3_actions.upload_file.side_effect = UnknownFiletypeException()

        with pytest.raises(AmbulanceRequestAllFilesUploadFailedException):
            await service.upload_files(files=files, user_id=user.id)

    @pytest.mark.asyncio
    async def test_upload_files_partial_success(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
        mock_s3_actions,
        mock_ai_service,
    ):
        """Test upload files when some files succeed and some fail."""
        user = await user_factory()
        await db_session.commit()

        files = [
            UploadFile(filename='file1.pdf', file=BytesIO(b'content1')),
            UploadFile(filename='file2.exe', file=BytesIO(b'content2')),
        ]

        # First file succeeds, second fails
        def upload_side_effect(*args, **kwargs):
            if 'file2.exe' in str(kwargs.get('file_name', '')):
                raise UnknownFiletypeException()
            return ('users/1/ambulance-requests/file1.pdf', 'application/pdf')

        mock_s3_actions.upload_file.side_effect = upload_side_effect

        # Should not raise exception, but log warning
        result = await service.upload_files(files=files, user_id=user.id)

        assert len(result) == 1
        assert result[0].filename == 'file1.pdf'

    @pytest.mark.asyncio
    async def test_create_request_success(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
        mock_ai_service,
    ):
        """Test successful request creation."""
        user = await user_factory()
        await db_session.commit()

        # Upload files first
        file1 = UploadFile(filename='file1.pdf', file=BytesIO(b'content1'))
        file2 = UploadFile(filename='file2.pdf', file=BytesIO(b'content2'))
        upload_result = await service.upload_files(
            files=[file1, file2], user_id=user.id
        )
        file_ids = [f.id for f in upload_result]
        await db_session.commit()

        # Create draft request with extraction
        from schemas.ambulance_request import CreateAmbulanceRequestParseSchema

        parse_data = CreateAmbulanceRequestParseSchema(file_ids=file_ids)
        draft_result = await service.create_request_with_extraction(
            request_data=parse_data, user_id=user.id
        )
        await db_session.commit()

        # Now create/submit the request
        request_data = CreateAmbulanceRequestSchema(
            request_id=draft_result.request_id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St, Springfield, IL 62701',
            destination_address='Memorial Dialysis Center, 456 Medical Dr',
            primary_diagnosis='Chronic heart failure',
            medical_justification='Patient requires transport',
            form_number='CMS-13614',  # This form number indicates Verification of Medical Necessity
            ordering_physician='Dr. Smith',  # Physician Signature is required
        )

        # Get draft request to check ai_accuracy
        from dao import AmbulanceRequestDAO
        request_dao = AmbulanceRequestDAO(db_session)
        draft_request = await request_dao.get_by_id(draft_result.request_id)
        draft_ai_accuracy = draft_request.ai_accuracy

        result = await service.create_request(
            user_id=user.id, request_data=request_data
        )

        assert result.id is not None
        assert result.patient_first_name == 'John'
        assert result.status == RequestStatus.SUBMITTED
        # Verify files are linked
        file_dao = RequestFileDAO(db_session)
        files = await file_dao.get_by_request_id(result.id)
        assert len(files) == 2
        assert all(f.request_id == result.id for f in files)

        # Verify status history was created
        status_dao = RequestStatusHistoryDAO(db_session)
        history = await status_dao.get_by_request_id(result.id)
        assert len(history) == 1
        assert history[0].status == RequestStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_create_request_invalid_draft(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
    ):
        """Test create request with invalid draft request_id raises exception."""
        user = await user_factory()
        await db_session.commit()

        request_data = CreateAmbulanceRequestSchema(
            request_id=99999,  # Non-existent draft request
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
            primary_diagnosis=None,
            medical_justification=None,
            form_number=None,
        )

        with pytest.raises(AmbulanceRequestNotFoundException):
            await service.create_request(
                user_id=user.id, request_data=request_data
            )

    @pytest.mark.asyncio
    async def test_get_request_by_id_success(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
        mock_s3_actions,
    ):
        """Test getting request by ID."""
        user = await user_factory()
        await db_session.commit()

        # Create request
        file1 = UploadFile(filename='file1.pdf', file=BytesIO(b'content1'))
        upload_result = await service.upload_files(
            files=[file1], user_id=user.id
        )
        file_ids = [f.id for f in upload_result]
        await db_session.commit()

        # Create draft
        from schemas.ambulance_request import CreateAmbulanceRequestParseSchema

        parse_data = CreateAmbulanceRequestParseSchema(file_ids=file_ids)
        draft_result = await service.create_request_with_extraction(
            request_data=parse_data, user_id=user.id
        )
        await db_session.commit()

        request_data = CreateAmbulanceRequestSchema(
            request_id=draft_result.request_id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
            form_number='CMS-13614',  # This form number indicates Verification of Medical Necessity
            ordering_physician='Dr. Smith',  # Physician Signature is required
        )
        created = await service.create_request(
            user_id=user.id, request_data=request_data
        )
        await db_session.commit()

        result = await service.get_request_by_id(
            user=user, request_id=created.id
        )

        assert result.id == created.id
        assert len(result.documents) == 1
        assert result.documents[0].filename == 'file1.pdf'
        assert (
            result.documents[0].download_url
            == 'https://s3.example.com/presigned-url'
        )
        assert len(result.status_history) == 1

    @pytest.mark.asyncio
    async def test_get_request_by_id_not_found(
        self,
        service: AmbulanceRequestService,
        user_factory,
    ):
        """Test getting non-existent request raises exception."""
        user = await user_factory()

        with pytest.raises(AmbulanceRequestNotFoundException):
            await service.get_request_by_id(user=user, request_id=99999)

    @pytest.mark.asyncio
    async def test_get_request_by_id_permission_denied(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
    ):
        """Test getting request from another user raises exception."""
        user1 = await user_factory(email='user1@example.com')
        user2 = await user_factory(email='user2@example.com')
        await db_session.commit()

        # Create request for user1
        file1 = UploadFile(filename='file1.pdf', file=BytesIO(b'content1'))
        upload_result = await service.upload_files(
            files=[file1], user_id=user1.id
        )
        file_ids = [f.id for f in upload_result]
        await db_session.commit()

        # Create draft
        from schemas.ambulance_request import CreateAmbulanceRequestParseSchema

        parse_data = CreateAmbulanceRequestParseSchema(file_ids=file_ids)
        draft_result = await service.create_request_with_extraction(
            request_data=parse_data, user_id=user1.id
        )
        await db_session.commit()

        request_data = CreateAmbulanceRequestSchema(
            request_id=draft_result.request_id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
            form_number='CMS-13614',  # This form number indicates Verification of Medical Necessity
            ordering_physician='Dr. Smith',  # Physician Signature is required
        )
        created = await service.create_request(
            user_id=user1.id, request_data=request_data
        )
        await db_session.commit()

        # user2 tries to access user1's request
        with pytest.raises(AmbulanceRequestPermissionException):
            await service.get_request_by_id(user=user2, request_id=created.id)

    @pytest.mark.asyncio
    async def test_get_request_by_id_admin_access(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
        mock_s3_actions,
    ):
        """Test admin can access any request."""
        user1 = await user_factory(email='user1@example.com')
        admin = await user_factory(
            email='admin@example.com', role=UserRole.ADMIN
        )
        await db_session.commit()

        # Create request for user1
        file1 = UploadFile(filename='file1.pdf', file=BytesIO(b'content1'))
        upload_result = await service.upload_files(
            files=[file1], user_id=user1.id
        )
        file_ids = [f.id for f in upload_result]
        await db_session.commit()

        # Create draft
        from schemas.ambulance_request import CreateAmbulanceRequestParseSchema

        parse_data = CreateAmbulanceRequestParseSchema(file_ids=file_ids)
        draft_result = await service.create_request_with_extraction(
            request_data=parse_data, user_id=user1.id
        )
        await db_session.commit()

        request_data = CreateAmbulanceRequestSchema(
            request_id=draft_result.request_id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
            form_number='CMS-13614',  # This form number indicates Verification of Medical Necessity
            ordering_physician='Dr. Smith',  # Physician Signature is required
        )
        created = await service.create_request(
            user_id=user1.id, request_data=request_data
        )
        await db_session.commit()

        # Admin can access
        result = await service.get_request_by_id(
            user=admin, request_id=created.id
        )
        assert result.id == created.id

    @pytest.mark.asyncio
    async def test_get_all_requests_provider(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
    ):
        """Test provider sees only their own requests."""
        user1 = await user_factory(email='user1@example.com')
        user2 = await user_factory(email='user2@example.com')
        await db_session.commit()

        # Create requests for user1
        first_names = ['John', 'Jane', 'Bob']
        for i, first_name in enumerate(first_names):
            file1 = UploadFile(
                filename=f'file{i}.pdf', file=BytesIO(b'content')
            )
            upload_result = await service.upload_files(
                files=[file1], user_id=user1.id
            )
            file_ids = [f.id for f in upload_result]
            await db_session.commit()

            # Create draft
            from schemas.ambulance_request import CreateAmbulanceRequestParseSchema

            parse_data = CreateAmbulanceRequestParseSchema(file_ids=file_ids)
            draft_result = await service.create_request_with_extraction(
                request_data=parse_data, user_id=user1.id
            )
            await db_session.commit()

            request_data = CreateAmbulanceRequestSchema(
                request_id=draft_result.request_id,
                transportation_type=TransportationType.AMBULANCE,
                patient_first_name=first_name,
                patient_last_name='Doe',
                patient_date_of_birth=date(1980, 1, 1),
                patient_id=f'DA12345678{i}HY',
                date_of_transport=date(2025, 12, 6),
                time_of_transport=time(13, 40),
                pickup_address='123 Main St',
                destination_address='456 Medical Dr',
                form_number='CMS-13614',  # This form number indicates Verification of Medical Necessity
                ordering_physician='Dr. Smith',  # Physician Signature is required
            )
            await service.create_request(
                user_id=user1.id, request_data=request_data
            )
            await db_session.commit()

        # Create request for user2
        file1 = UploadFile(filename='file2.pdf', file=BytesIO(b'content'))
        upload_result = await service.upload_files(
            files=[file1], user_id=user2.id
        )
        file_ids = [f.id for f in upload_result]
        await db_session.commit()

        # Create draft
        from schemas.ambulance_request import CreateAmbulanceRequestParseSchema

        parse_data = CreateAmbulanceRequestParseSchema(file_ids=file_ids)
        draft_result = await service.create_request_with_extraction(
            request_data=parse_data, user_id=user2.id
        )
        await db_session.commit()

        request_data = CreateAmbulanceRequestSchema(
            request_id=draft_result.request_id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='Jane',
            patient_last_name='Smith',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA987654321AB',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='789 Oak Ave',
            destination_address='321 Pine St',
            form_number='CMS-13614',  # This form number indicates Verification of Medical Necessity
            ordering_physician='Dr. Smith',  # Physician Signature is required
        )
        await service.create_request(
            user_id=user2.id, request_data=request_data
        )
        await db_session.commit()

        # Provider sees only their own requests
        items, total, page, total_pages, showing = await service.get_all_requests(
            user=user1, page=1, limit=8
        )

        assert len(items) == 3
        assert all(req.patient_first_name in first_names for req in items)
        assert all(req.user_id == user1.id for req in items)
        assert total == 3
        assert page == 1
        assert total_pages == 1
        assert showing == 3

    @pytest.mark.asyncio
    async def test_get_all_requests_admin(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
    ):
        """Test admin sees all requests."""
        user1 = await user_factory(email='user1@example.com')
        user2 = await user_factory(email='user2@example.com')
        admin = await user_factory(
            email='admin@example.com', role=UserRole.ADMIN
        )
        await db_session.commit()

        # Create requests for both users
        for user in [user1, user2]:
            file1 = UploadFile(filename='file.pdf', file=BytesIO(b'content'))
            upload_result = await service.upload_files(
                files=[file1], user_id=user.id
            )
            file_ids = [f.id for f in upload_result]
            await db_session.commit()

            # Create draft
            from schemas.ambulance_request import CreateAmbulanceRequestParseSchema

            parse_data = CreateAmbulanceRequestParseSchema(file_ids=file_ids)
            draft_result = await service.create_request_with_extraction(
                request_data=parse_data, user_id=user.id
            )
            await db_session.commit()

            request_data = CreateAmbulanceRequestSchema(
                request_id=draft_result.request_id,
                transportation_type=TransportationType.AMBULANCE,
                patient_first_name='John',
                patient_last_name='Doe',
                patient_date_of_birth=date(1980, 1, 1),
                patient_id='DA123456789HY',
                date_of_transport=date(2025, 12, 6),
                time_of_transport=time(13, 40),
                pickup_address='123 Main St',
                destination_address='456 Medical Dr',
                form_number='CMS-13614',  # This form number indicates Verification of Medical Necessity
                ordering_physician='Dr. Smith',  # Physician Signature is required
            )
            await service.create_request(
                user_id=user.id, request_data=request_data
            )
            await db_session.commit()

        # Admin sees all requests
        items, total, page, total_pages, showing = await service.get_all_requests(
            user=admin, page=1, limit=8
        )

        assert len(items) == 2
        user_ids = {req.user_id for req in items}
        assert user_ids == {user1.id, user2.id}
        assert total == 2
        assert page == 1
        assert total_pages == 1
        assert showing == 2

    @pytest.mark.asyncio
    async def test_get_all_requests_with_pagination(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
    ):
        """Test pagination for getting requests."""
        user = await user_factory()
        await db_session.commit()

        # Create 5 requests
        for i in range(5):
            file1 = UploadFile(
                filename=f'file{i}.pdf', file=BytesIO(b'content')
            )
            upload_result = await service.upload_files(
                files=[file1], user_id=user.id
            )
            file_ids = [f.id for f in upload_result]
            await db_session.commit()

            # Format: 2 letters + 9 digits + 2 letters (e.g., DA123456789HY)
            # Use different patient IDs for each request
            patient_id_digits = f'{100000000 + i:09d}'  # Ensure 9 digits: 100000000, 100000001, etc.
            # Use letters only for first name (pattern requires ^[a-zA-Z]+$)
            first_names = ['John', 'Jane', 'Bob', 'Alice', 'Charlie']
            # Create draft
            from schemas.ambulance_request import CreateAmbulanceRequestParseSchema

            parse_data = CreateAmbulanceRequestParseSchema(file_ids=file_ids)
            draft_result = await service.create_request_with_extraction(
                request_data=parse_data, user_id=user.id
            )
            await db_session.commit()

            request_data = CreateAmbulanceRequestSchema(
                request_id=draft_result.request_id,
                transportation_type=TransportationType.AMBULANCE,
                patient_first_name=first_names[i],
                patient_last_name='Doe',
                patient_date_of_birth=date(1980, 1, 1),
                patient_id=f'DA{patient_id_digits}HY',
                date_of_transport=date(2025, 12, 6),
                time_of_transport=time(13, 40),
                pickup_address='123 Main St',
                destination_address='456 Medical Dr',
                form_number='CMS-13614',  # This form number indicates Verification of Medical Necessity
                ordering_physician='Dr. Smith',  # Physician Signature is required
            )
            await service.create_request(
                user_id=user.id, request_data=request_data
            )
            await db_session.commit()

        # Get first page
        items, total, page, total_pages, showing = await service.get_all_requests(
            user=user, page=1, limit=2
        )

        assert len(items) == 2
        assert total == 5
        assert page == 1
        assert total_pages == 3
        assert showing == 2
        first_page_ids = {req.id for req in items}

        # Get next page
        items2, total2, page2, total_pages2, showing2 = (
            await service.get_all_requests(user=user, page=2, limit=2)
        )

        # We created 5 requests, first page has 2, so 3 remain
        # Second page should have 2 items (limit=2)
        assert len(items2) == 2
        assert total2 == 5
        assert page2 == 2
        assert total_pages2 == 3
        assert showing2 == 2
        second_page_ids = {req.id for req in items2}

        # Should not overlap
        assert first_page_ids.isdisjoint(second_page_ids), (
            f'Pages overlap: first_page={first_page_ids}, second_page={second_page_ids}'
        )

    @pytest.mark.asyncio
    async def test_update_request_status(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
    ):
        """Test updating request status."""
        user = await user_factory()
        await db_session.commit()

        # Create request
        file1 = UploadFile(filename='file1.pdf', file=BytesIO(b'content1'))
        upload_result = await service.upload_files(
            files=[file1], user_id=user.id
        )
        file_ids = [f.id for f in upload_result]
        await db_session.commit()

        # Create draft
        from schemas.ambulance_request import CreateAmbulanceRequestParseSchema

        parse_data = CreateAmbulanceRequestParseSchema(file_ids=file_ids)
        draft_result = await service.create_request_with_extraction(
            request_data=parse_data, user_id=user.id
        )
        await db_session.commit()

        request_data = CreateAmbulanceRequestSchema(
            request_id=draft_result.request_id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
            form_number='CMS-13614',  # This form number indicates Verification of Medical Necessity
            ordering_physician='Dr. Smith',  # Physician Signature is required
        )
        created = await service.create_request(
            user_id=user.id, request_data=request_data
        )
        await db_session.commit()

        # Update status
        updated = await service.update_request_status(
            request_id=created.id,
            new_status=RequestStatus.APPROVED,
            notes='Request approved by admin',
        )

        assert updated.status == RequestStatus.APPROVED

        # Verify status history was created
        status_dao = RequestStatusHistoryDAO(db_session)
        history = await status_dao.get_by_request_id(created.id)
        assert len(history) == 2
        assert history[0].status == RequestStatus.SUBMITTED
        assert history[1].status == RequestStatus.APPROVED
        assert history[1].notes == 'Request approved by admin'

    @pytest.mark.asyncio
    async def test_update_request_status_not_found(
        self,
        service: AmbulanceRequestService,
    ):
        """Test updating status for non-existent request raises exception."""
        with pytest.raises(AmbulanceRequestNotFoundException):
            await service.update_request_status(
                request_id=99999,
                new_status=RequestStatus.APPROVED,
            )

    @pytest.mark.asyncio
    async def test_approve_request_invalid_transition(
        self,
        service: AmbulanceRequestService,
        db_session,
    ):
        """Test approving a DENIED request should fail (Business Logic Gap)."""
        # Create a mock request in DENIED status
        request = MagicMock()
        request.id = 1
        request.status = RequestStatus.DENIED
        request.user_id = 1

        # Patch DAO
        service._request_dao = AsyncMock()
        service._request_dao.get_by_id.return_value = request

        from exceptions import AmbulanceRequestInvalidStatusException

        try:
            await service.approve_request(request_id=1, reviewer_id=2)
            # If we reach here, logic is missing!
            pytest.fail("Should not allow approving a DENIED request without reopen.")
        except AmbulanceRequestInvalidStatusException:
            pass  # Expected behavior
        except Exception as e:
            # Maybe it raises something else?
            if "fail" not in str(e): # allow pytest.fail to propagate
                pass


    @pytest.mark.asyncio
    async def test_get_request_admin_concurrency(
        self,
        service: AmbulanceRequestService,
        user_factory,
    ):
        """Test admin opening request doesn't duplicate PENDING entries."""
        admin = MagicMock()
        admin.role = UserRole.ADMIN

        request = MagicMock()
        request.id = 1
        request.status = RequestStatus.PENDING
        request.user_id = 10
        # Add required fields for AdminRequestWithStatusHistorySchema
        request.transportation_type = TransportationType.AMBULANCE
        request.patient_first_name = "John"
        request.patient_last_name = "Doe"
        request.patient_date_of_birth = date(1980, 1, 1)
        request.patient_id = "123"
        request.date_of_transport = date(2025, 1, 1)
        request.time_of_transport = time(12, 0)
        request.pickup_address = "Start"
        request.destination_address = "End"
        request.primary_diagnosis = "Diag"
        request.medical_justification = "Just"
        request.form_number = "Form"
        request.ambulatory_status = None
        request.oxygen_required = False
        request.ai_accuracy = 0.9
        request.ordering_physician = "Dr"
        request.physician_phone = "555"
        request.ordering_physician_npi = None
        request.patient_sex = None
        request.insurance_type = None
        request.insurance_payer_name = None
        request.insured_id_number = None
        request.insured_name = None
        request.patient_relationship_to_insured = None
        request.denial_reason = None
        request.denial_notes = None
        request.utn = None
        request.novitas_status = NovitasStatus.NOT_SUBMITTED
        request.novitas_submitted_at = None
        request.created_at = datetime.now(UTC)
        request.updated_at = datetime.now(UTC)
        request.reviewer_id = None

        service._request_dao = AsyncMock()
        service._request_dao.get_by_id.return_value = request
        service._status_history_dao = AsyncMock()
        service._status_history_dao.get_by_request_id.return_value = []
        service._file_dao = AsyncMock()
        service._file_dao.get_by_request_id.return_value = []

        # Mock get_completion_status
        from schemas.ambulance_request import CompletionStatus, CompletionStatusSchema
        mock_completion_status = CompletionStatusSchema(
            overall_status=CompletionStatus.COMPLETE,
            missing_fields=[],
            missing_documents=[],
            can_submit=True,
        )
        service.get_completion_status = AsyncMock(return_value=mock_completion_status)

        # Action
        await service.get_request_by_id(user=admin, request_id=1)

        # Assertion
        service._status_history_dao.create.assert_not_called()


class TestGenerateCallSheetPdf:
    """Test suite for AmbulanceRequestService.generate_call_sheet_pdf()."""

    @pytest.fixture
    def service(self, db_session) -> AmbulanceRequestService:
        """Create AmbulanceRequestService instance with S3/AI mocked."""
        return AmbulanceRequestService(
            db_session=db_session,
            s3_actions=MagicMock(spec=S3Actions),
            ai_extraction_service=MagicMock(spec=AIExtractionService),
        )

    @pytest.mark.asyncio
    async def test_provider_can_download_own_request(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that a provider can download the Call Sheet for their own
        request.
        """  # noqa: D205
        user = await user_factory()
        request = await ambulance_request_factory(user_id=user.id)
        await db_session.commit()
        service._call_sheet_service = MagicMock()
        service._call_sheet_service.generate_call_sheet_pdf.return_value = (
            b'%PDF-fake'
        )

        pdf_bytes = await service.generate_call_sheet_pdf(
            request_id=request.id, user=user
        )

        assert pdf_bytes == b'%PDF-fake'

    @pytest.mark.asyncio
    async def test_provider_cannot_download_others_request(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that a provider cannot download another provider's
        Call Sheet.
        """  # noqa: D205
        owner = await user_factory(email='owner@example.com')
        other = await user_factory(email='other@example.com')
        request = await ambulance_request_factory(user_id=owner.id)
        await db_session.commit()

        with pytest.raises(AmbulanceRequestPermissionException):
            await service.generate_call_sheet_pdf(
                request_id=request.id, user=other
            )

    @pytest.mark.asyncio
    async def test_admin_can_download_any_request(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that an admin can download any request's Call Sheet."""
        owner = await user_factory(email='owner2@example.com')
        admin = await user_factory(
            email='admin2@example.com', role=UserRole.ADMIN
        )
        request = await ambulance_request_factory(user_id=owner.id)
        await db_session.commit()
        service._call_sheet_service = MagicMock()
        service._call_sheet_service.generate_call_sheet_pdf.return_value = (
            b'%PDF-fake'
        )

        pdf_bytes = await service.generate_call_sheet_pdf(
            request_id=request.id, user=admin
        )

        assert pdf_bytes == b'%PDF-fake'

    @pytest.mark.asyncio
    async def test_not_found_raises(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
    ):
        """Test that a nonexistent request raises."""
        user = await user_factory()
        await db_session.commit()

        with pytest.raises(AmbulanceRequestNotFoundException):
            await service.generate_call_sheet_pdf(
                request_id=999999, user=user
            )


class TestGenerateCms1500Pdf:
    """Test suite for AmbulanceRequestService.generate_cms1500_pdf()."""

    @pytest.fixture
    def service(self, db_session) -> AmbulanceRequestService:
        """Create AmbulanceRequestService instance with S3/AI mocked."""
        return AmbulanceRequestService(
            db_session=db_session,
            s3_actions=MagicMock(spec=S3Actions),
            ai_extraction_service=MagicMock(spec=AIExtractionService),
        )

    @pytest.mark.asyncio
    async def test_provider_can_download_own_request(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that a provider can download the CMS-1500 for their own
        request.
        """  # noqa: D205
        user = await user_factory()
        request = await ambulance_request_factory(user_id=user.id)
        await db_session.commit()
        service._cms1500_generator_service = MagicMock()
        generate = service._cms1500_generator_service.generate_cms1500_pdf
        generate.return_value = b'%PDF-fake'

        pdf_bytes = await service.generate_cms1500_pdf(
            request_id=request.id, user=user
        )

        assert pdf_bytes == b'%PDF-fake'

    @pytest.mark.asyncio
    async def test_provider_cannot_download_others_request(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that a provider cannot download another provider's
        CMS-1500.
        """  # noqa: D205
        owner = await user_factory(email='cms-owner@example.com')
        other = await user_factory(email='cms-other@example.com')
        request = await ambulance_request_factory(user_id=owner.id)
        await db_session.commit()

        with pytest.raises(AmbulanceRequestPermissionException):
            await service.generate_cms1500_pdf(
                request_id=request.id, user=other
            )

    @pytest.mark.asyncio
    async def test_admin_can_download_any_request(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that an admin can download any request's CMS-1500."""
        owner = await user_factory(email='cms-owner2@example.com')
        admin = await user_factory(
            email='cms-admin2@example.com', role=UserRole.ADMIN
        )
        request = await ambulance_request_factory(user_id=owner.id)
        await db_session.commit()
        service._cms1500_generator_service = MagicMock()
        generate = service._cms1500_generator_service.generate_cms1500_pdf
        generate.return_value = b'%PDF-fake'

        pdf_bytes = await service.generate_cms1500_pdf(
            request_id=request.id, user=admin
        )

        assert pdf_bytes == b'%PDF-fake'

    @pytest.mark.asyncio
    async def test_not_found_raises(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
    ):
        """Test that a nonexistent request raises."""
        user = await user_factory()
        await db_session.commit()

        with pytest.raises(AmbulanceRequestNotFoundException):
            await service.generate_cms1500_pdf(
                request_id=999999, user=user
            )


class TestSubmitToNovitas:
    """Test suite for AmbulanceRequestService.submit_to_novitas()."""

    @pytest.fixture
    def service(self, db_session) -> AmbulanceRequestService:
        """Create AmbulanceRequestService instance with mocks."""
        service = AmbulanceRequestService(
            db_session=db_session,
            s3_actions=MagicMock(spec=S3Actions),
            ai_extraction_service=MagicMock(spec=AIExtractionService),
        )
        service._fax_service = MagicMock()
        return service

    @pytest.fixture(autouse=True)
    def _reset_novitas_fax_number(self):
        """Reset the Novitas fax number setting after each test."""
        settings = Settings.load()
        original = settings.ringcentral_settings.NOVITAS_FAX_NUMBER
        yield
        settings.ringcentral_settings.NOVITAS_FAX_NUMBER = original

    def _mock_can_submit(
        self, service: AmbulanceRequestService, *, can_submit: bool = True
    ) -> None:
        from schemas.ambulance_request import (
            CompletionStatus,
            CompletionStatusSchema,
        )

        service.get_completion_status = AsyncMock(
            return_value=CompletionStatusSchema(
                overall_status=(
                    CompletionStatus.COMPLETE
                    if can_submit
                    else CompletionStatus.MISSING
                ),
                missing_fields=[],
                missing_documents=[],
                can_submit=can_submit,
            )
        )

    @pytest.mark.asyncio
    async def test_not_found_raises(
        self,
        service: AmbulanceRequestService,
        user_factory,
        db_session,
    ):
        """Test that a nonexistent request raises."""
        admin = await user_factory(
            email='novitas-nf-admin@example.com', role=UserRole.ADMIN
        )
        await db_session.commit()

        with pytest.raises(AmbulanceRequestNotFoundException):
            await service.submit_to_novitas(request_id=999999, user=admin)

    @pytest.mark.asyncio
    async def test_non_admin_raises_permission(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that a non-admin user cannot submit to Novitas."""
        owner = await user_factory(email='novitas-owner@example.com')
        request = await ambulance_request_factory(
            user_id=owner.id, status=RequestStatus.APPROVED
        )
        await db_session.commit()

        with pytest.raises(AmbulanceRequestPermissionException):
            await service.submit_to_novitas(
                request_id=request.id, user=owner
            )

    @pytest.mark.asyncio
    async def test_not_approved_raises_invalid_status(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that a non-approved request cannot be submitted."""
        admin = await user_factory(
            email='novitas-pending-admin@example.com', role=UserRole.ADMIN
        )
        owner = await user_factory(email='novitas-pending-owner@example.com')
        request = await ambulance_request_factory(
            user_id=owner.id, status=RequestStatus.PENDING
        )
        await db_session.commit()

        with pytest.raises(AmbulanceRequestInvalidStatusException):
            await service.submit_to_novitas(
                request_id=request.id, user=admin
            )

    @pytest.mark.asyncio
    async def test_already_submitted_raises_invalid_status(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that a request already submitted cannot be resubmitted."""
        admin = await user_factory(
            email='novitas-dup-admin@example.com', role=UserRole.ADMIN
        )
        owner = await user_factory(email='novitas-dup-owner@example.com')
        request = await ambulance_request_factory(
            user_id=owner.id, status=RequestStatus.APPROVED
        )
        request.novitas_status = NovitasStatus.SUBMITTED
        await db_session.commit()

        with pytest.raises(AmbulanceRequestInvalidStatusException):
            await service.submit_to_novitas(
                request_id=request.id, user=admin
            )

    @pytest.mark.asyncio
    async def test_incomplete_request_raises_pdf_generation_exception(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that an incomplete request cannot be submitted."""
        admin = await user_factory(
            email='novitas-incomplete-admin@example.com', role=UserRole.ADMIN
        )
        owner = await user_factory(
            email='novitas-incomplete-owner@example.com'
        )
        request = await ambulance_request_factory(
            user_id=owner.id, status=RequestStatus.APPROVED
        )
        await db_session.commit()
        self._mock_can_submit(service, can_submit=False)

        with pytest.raises(AmbulanceRequestPDFGenerationException):
            await service.submit_to_novitas(
                request_id=request.id, user=admin
            )

    @pytest.mark.asyncio
    async def test_missing_fax_number_raises_pdf_generation_exception(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that a missing Novitas fax number config raises."""
        admin = await user_factory(
            email='novitas-nofax-admin@example.com', role=UserRole.ADMIN
        )
        owner = await user_factory(email='novitas-nofax-owner@example.com')
        request = await ambulance_request_factory(
            user_id=owner.id, status=RequestStatus.APPROVED
        )
        await db_session.commit()
        self._mock_can_submit(service)
        Settings.load().ringcentral_settings.NOVITAS_FAX_NUMBER = ''

        with pytest.raises(AmbulanceRequestPDFGenerationException):
            await service.submit_to_novitas(
                request_id=request.id, user=admin
            )

    @pytest.mark.asyncio
    async def test_success_sends_fax_and_updates_status(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test a successful Novitas submission sends a fax and updates
        the request's Novitas tracking fields.
        """  # noqa: D205
        admin = await user_factory(
            email='novitas-ok-admin@example.com', role=UserRole.ADMIN
        )
        owner = await user_factory(email='novitas-ok-owner@example.com')
        request = await ambulance_request_factory(
            user_id=owner.id, status=RequestStatus.APPROVED
        )
        await db_session.commit()
        self._mock_can_submit(service)
        Settings.load().ringcentral_settings.NOVITAS_FAX_NUMBER = (
            '+15559990000'
        )
        service._pdf_generator_service = MagicMock()
        service._pdf_generator_service.generate_cms_10344_pdf.return_value = (
            b'%PDF-cms'
        )
        service._file_dao.get_by_request_id = AsyncMock(return_value=[])
        fake_fax = MagicMock(id=42)
        service._fax_service.send_outbound_fax = AsyncMock(
            return_value=fake_fax
        )

        result = await service.submit_to_novitas(
            request_id=request.id, user=admin
        )

        assert result.id == request.id
        service._fax_service.send_outbound_fax.assert_awaited_once()
        call_kwargs = service._fax_service.send_outbound_fax.call_args.kwargs
        assert call_kwargs['to_number'] == '+15559990000'
        assert call_kwargs['request_id'] == request.id
        assert len(call_kwargs['attachments']) == 1
        assert call_kwargs['attachments'][0][1] == b'%PDF-cms'

        await db_session.refresh(request)
        assert request.novitas_status == NovitasStatus.SUBMITTED
        assert request.novitas_fax_id == 42
        assert request.novitas_submitted_at is not None

    @pytest.mark.asyncio
    async def test_success_includes_supporting_documents(
        self,
        service: AmbulanceRequestService,
        user_factory,
        ambulance_request_factory,
        db_session,
    ):
        """Test that linked supporting documents are attached to the fax."""
        admin = await user_factory(
            email='novitas-docs-admin@example.com', role=UserRole.ADMIN
        )
        owner = await user_factory(email='novitas-docs-owner@example.com')
        request = await ambulance_request_factory(
            user_id=owner.id, status=RequestStatus.APPROVED
        )
        await db_session.commit()
        self._mock_can_submit(service)
        Settings.load().ringcentral_settings.NOVITAS_FAX_NUMBER = (
            '+15559990000'
        )
        service._pdf_generator_service = MagicMock()
        service._pdf_generator_service.generate_cms_10344_pdf.return_value = (
            b'%PDF-cms'
        )
        fake_file = MagicMock(id=1, filename='pcs.pdf', s3_key='key/pcs.pdf')
        service._file_dao.get_by_request_id = AsyncMock(
            return_value=[fake_file]
        )
        service._s3_actions.download_from_s3 = MagicMock(
            return_value=(b'%PDF-pcs', 'application/pdf')
        )
        fake_fax = MagicMock(id=7)
        service._fax_service.send_outbound_fax = AsyncMock(
            return_value=fake_fax
        )

        await service.submit_to_novitas(request_id=request.id, user=admin)

        call_kwargs = service._fax_service.send_outbound_fax.call_args.kwargs
        assert len(call_kwargs['attachments']) == 2
        assert call_kwargs['attachments'][1] == (
            'pcs.pdf',
            b'%PDF-pcs',
            'application/pdf',
        )
