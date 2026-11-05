"""Acceptance checks for the production release blockers (PAAI-49).

Each test encodes one release blocker from the 04.11.2026 review as the
behaviour production needs, not as the current behaviour. They are
expected to FAIL until the matching fix lands; a green run of this
module is the sign-off for the release-blocker list.

Two blockers need an API whose shape is the fixer's choice (an admin
"attach document" action and a "reprocess fax" action). Their tests go
through ``_admin_attach_document`` / ``_reprocess_fax`` below, which
raise until they're wired to the real API.

Only true external boundaries are mocked (RingCentral, S3, the LLM);
DB access, DAOs and PDF generation are real.
"""

from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

import fitz
import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.settings import Settings
from dao import RequestFileDAO
from dao.incoming_fax import IncomingFaxDAO
from main import app
from models.ambulance_request import (
    AmbulanceRequest,
    RequestStatus,
    TransportationType,
)
from models.incoming_fax import FaxDirection, FaxStatus
from models.organization import Organization
from models.user import User, UserRole
from schemas.ai_extraction import (
    AIExtractionResponse,
    ExtractedTransportationData,
)
from schemas.ambulance_request import (
    AdminUpdateRequestSchema,
    AmbulanceRequestResponseSchema,
    CreateAmbulanceRequestSchema,
)
from services.ai.extractor import AIExtractionService
from services.ambulance_request import AmbulanceRequestService
from services.aws.actions import S3Actions
from services.fax.fax_service import FaxService
from services.fax.ringcentral_client import RingCentralClient

REFERRING_PROVIDER_FAX_NUMBER = '+15551112222'
NOVITAS_FAX_NUMBER = '+15559990000'
PAAI_RINGCENTRAL_FAX_NUMBER = '+15553334444'
FAX_INTAKE_ADMIN_EMAIL = 'fax-intake@example.com'
WEBHOOK_SECRET = 'configured-secret'
RENDERING_PROVIDER_NPI = '1234567893'


def _inbound_message(**overrides) -> dict:
    """RingCentral message payload for an inbound referral fax."""
    message = {
        'direction': 'Inbound',
        'from': {'phoneNumber': REFERRING_PROVIDER_FAX_NUMBER},
        'to': [{'phoneNumber': PAAI_RINGCENTRAL_FAX_NUMBER}],
        'faxPageCount': 3,
        'attachments': [
            {'id': 'att-referral', 'contentType': 'application/pdf'}
        ],
    }
    message.update(overrides)
    return message


def _submission_data(
    request_id: int, **overrides
) -> CreateAmbulanceRequestSchema:
    """A complete, valid submission an admin makes after reviewing a draft."""
    data = {
        'request_id': request_id,
        'transportation_type': TransportationType.AMBULANCE,
        'patient_first_name': 'Jane',
        'patient_last_name': 'Roe',
        'patient_date_of_birth': date(1975, 6, 15),
        'patient_id': '1EG4TE5MK73',
        'date_of_transport': date(2026, 1, 15),
        'time_of_transport': time(9, 30),
        'pickup_address': '123 Oak St, Springfield, IL 62701',
        'destination_address': '456 Medical Dr, Springfield, IL 62702',
        'primary_diagnosis': 'End-stage renal disease',
        'medical_justification': 'Wheelchair van transport for dialysis',
        'form_number': 'CMS-13614',
        'ordering_physician': 'Dr. Smith',
        'ordering_physician_npi': '1234567890',
    }
    data.update(overrides)
    return CreateAmbulanceRequestSchema.model_validate(data)


async def _admin_attach_document(
    service: AmbulanceRequestService,
    *,
    admin: User,
    request_id: int,
) -> None:
    """Attach a supporting document to a request as an admin.

    Wire this to the admin attach-document API once it exists.
    """
    raise NotImplementedError(
        'No admin attach-document API yet (release blocker #1)'
    )


async def _reprocess_fax(
    fax_service: FaxService,
    service: AmbulanceRequestService,
    *,
    fax_id: int,
) -> None:
    """Re-run intake for a FAILED / stuck fax.

    Wire this to the reprocess API once it exists.
    """
    raise NotImplementedError('No reprocess-fax API yet (release blocker #3)')


class TestReleaseBlockers:
    """One test (or a few) per release blocker, numbered as in the review."""

    @pytest.fixture(autouse=True)
    def _configure_settings(self):
        """Point the fax settings at test values, restoring them after."""
        ringcentral = Settings.load().ringcentral_settings
        originals = (
            ringcentral.NOVITAS_FAX_NUMBER,
            ringcentral.FAX_INTAKE_ADMIN_EMAIL,
            ringcentral.WEBHOOK_SECRET,
        )
        ringcentral.NOVITAS_FAX_NUMBER = NOVITAS_FAX_NUMBER
        ringcentral.FAX_INTAKE_ADMIN_EMAIL = FAX_INTAKE_ADMIN_EMAIL
        ringcentral.WEBHOOK_SECRET = WEBHOOK_SECRET
        yield
        (
            ringcentral.NOVITAS_FAX_NUMBER,
            ringcentral.FAX_INTAKE_ADMIN_EMAIL,
            ringcentral.WEBHOOK_SECRET,
        ) = originals

    @pytest.fixture(autouse=True)
    def mock_process_inbound_fax_task(self):
        """Keep process_inbound_message from enqueueing a real Celery task."""
        with patch(
            'tasks.fax_processing.process_inbound_fax.delay'
        ) as mock_delay:
            yield mock_delay

    @pytest.fixture
    def mock_s3_actions(self) -> MagicMock:
        """Mock S3Actions."""
        mock = MagicMock(spec=S3Actions)
        mock.download_from_s3.return_value = (
            b'%PDF-1.4 fake document',
            'application/pdf',
        )
        mock.get_presigned_url.return_value = (
            'https://s3.example.com/presigned-url'
        )
        return mock

    @pytest.fixture
    def mock_ringcentral_client(self) -> MagicMock:
        """Mock RingCentralClient returning an inbound referral fax."""
        mock = MagicMock(spec=RingCentralClient)
        mock.get_message = AsyncMock(return_value=_inbound_message())
        mock.get_document_attachment = MagicMock(
            side_effect=RingCentralClient.get_document_attachment
        )
        mock.download_attachment = AsyncMock(
            return_value=(b'%PDF-1.4 fake fax content', 'application/pdf')
        )
        mock.send_fax = AsyncMock(
            return_value={
                'id': 'rc-outbound-novitas-1',
                'messageStatus': 'Sent',
                'faxPageCount': 2,
            }
        )
        return mock

    @pytest.fixture
    def extracted_data(self) -> ExtractedTransportationData:
        """What the LLM pulls off the referral fax."""
        return ExtractedTransportationData(
            patient_first_name='Jane',
            patient_last_name='Roe',
            patient_date_of_birth=date(1975, 6, 15),
            patient_id='1EG4TE5MK73',
            pickup_address='123 Oak St, Springfield, IL 62701',
            destination_address='456 Medical Dr, Springfield, IL 62702',
            primary_diagnosis='End-stage renal disease',
            medical_justification='Wheelchair van transport for dialysis',
            ordering_physician_npi='1234567890',
        )

    @pytest.fixture
    def mock_ai_extraction_service(self, extracted_data) -> MagicMock:
        """Mock the LLM: extraction, and a YES from the document check."""
        mock = MagicMock(spec=AIExtractionService)
        mock.extract_data_from_files = AsyncMock(
            return_value=AIExtractionResponse(
                extracted_data=extracted_data,
                extraction_metadata={'status': 'success'},
            )
        )
        # The document check reaches into these private members.
        mock._download_file_from_s3 = AsyncMock(  # noqa: SLF001
            return_value=(b'%PDF-1.4 fake document', 'application/pdf')
        )
        processor = MagicMock()
        processor.process_document = AsyncMock(return_value=['page-1-image'])
        mock._document_processor = processor  # noqa: SLF001
        mock._build_message_content = MagicMock(  # noqa: SLF001
            return_value=[]
        )
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content='YES'))
        mock._llm = llm  # noqa: SLF001
        return mock

    @pytest.fixture
    def build_services(
        self,
        mock_s3_actions,
        mock_ringcentral_client,
        mock_ai_extraction_service,
    ):
        """Build a FaxService + AmbulanceRequestService pair on a session."""

        def _build(
            session: AsyncSession,
        ) -> tuple[FaxService, AmbulanceRequestService]:
            fax_service = FaxService(
                db_session=session,
                s3_actions=mock_s3_actions,
                ringcentral_client=mock_ringcentral_client,
            )
            service = AmbulanceRequestService(
                db_session=session,
                s3_actions=mock_s3_actions,
                ai_extraction_service=mock_ai_extraction_service,
                fax_service=fax_service,
            )
            return fax_service, service

        return _build

    @pytest_asyncio.fixture
    async def admins(self, db_session, user_factory) -> tuple[User, User]:
        """The fax-intake admin that owns fax drafts, and a reviewer."""
        intake_admin = await user_factory(
            email=FAX_INTAKE_ADMIN_EMAIL, role=UserRole.ADMIN
        )
        reviewer = await user_factory(
            email='reviewer@example.com', role=UserRole.ADMIN
        )
        await db_session.commit()
        return intake_admin, reviewer

    @pytest_asyncio.fixture
    async def approved_provider_request(
        self,
        db_session,
        user_factory,
        ambulance_request_factory,
    ) -> AmbulanceRequest:
        """An APPROVED provider request that is otherwise ready for Novitas.

        Its provider has a complete organization, so it passes any
        rendering-provider check - tests built on it are about something
        else.
        """
        provider = await user_factory(email='provider@example.com')
        db_session.add(
            Organization(
                user_id=provider.id,
                medic_name='Acme Ambulance',
                npi=RENDERING_PROVIDER_NPI,
                address='1 Depot Rd, Springfield, IL 62701',
                phone='+15550001111',
                fax='+15550002222',
            )
        )
        request = await ambulance_request_factory(
            user_id=provider.id,
            form_number='CMS-13614',
            status=RequestStatus.APPROVED,
        )
        await RequestFileDAO(db_session).create(
            request_id=request.id,
            uploaded_by_user_id=provider.id,
            filename='pcs.pdf',
            s3_key='users/1/ambulance-requests/pcs.pdf',
            file_size=2048,
            content_type='application/pdf',
        )
        await db_session.commit()
        return request

    # --- #1 Fax-to-Novitas workflow -------------------------------------

    @pytest.mark.asyncio
    async def test_1_fax_document_is_persisted_on_draft_in_celery_path(
        self, db_session, admins, build_services
    ):
        """The fax's document must survive as a RequestFile on its draft.

        Runs draft creation the way the Celery task does: on its own
        session, which is closed afterwards. Anything flushed but not
        committed is lost at that point.
        """
        fax_service, _ = build_services(db_session)
        fax = await fax_service.process_inbound_message('rc-referral-1')

        worker_session_maker = async_sessionmaker(
            bind=db_session.bind, expire_on_commit=False
        )
        async with worker_session_maker() as worker_session:
            _, worker_service = build_services(worker_session)
            draft = await worker_service.create_draft_request_from_fax(fax.id)
        assert draft is not None

        files = await RequestFileDAO(db_session).get_by_request_id(
            request_id=draft.id
        )
        assert len(files) == 1, (
            'Fax document was not committed with the draft - lost when '
            'the worker session closed'
        )

    @pytest.mark.asyncio
    async def test_1_admin_can_attach_missing_document_to_fax_draft(
        self, db_session, admins, build_services
    ):
        """An admin can add a document the fax didn't include."""
        _, reviewer = admins
        fax_service, service = build_services(db_session)
        fax = await fax_service.process_inbound_message('rc-referral-2')
        draft = await service.create_draft_request_from_fax(fax.id)
        await db_session.commit()

        await _admin_attach_document(
            service, admin=reviewer, request_id=draft.id
        )

        files = await RequestFileDAO(db_session).get_by_request_id(
            request_id=draft.id
        )
        assert len(files) == 2

    # --- #2 Novitas document validation --------------------------------

    @pytest.mark.asyncio
    async def test_2_fax_request_never_goes_to_novitas_without_rendering_provider(  # noqa: E501
        self, db_session, admins, build_services, mock_ringcentral_client
    ):
        """Form 13614 must carry a rendering provider, or not be sent.

        Either outcome is fine: submission refused, or the cover sheet's
        rendering-provider block is filled. A sent sheet with a blank
        NPI is not.
        """
        _, reviewer = admins
        fax_service, service = build_services(db_session)
        fax = await fax_service.process_inbound_message('rc-referral-3')
        draft = await service.create_draft_request_from_fax(fax.id)
        await service.create_request(
            user=reviewer, request_data=_submission_data(draft.id)
        )
        await service.approve_request(
            request_id=draft.id, reviewer_id=reviewer.id
        )

        try:
            await service.submit_to_novitas(request_id=draft.id, user=reviewer)
        except Exception:
            mock_ringcentral_client.send_fax.assert_not_awaited()
            return

        attachments = mock_ringcentral_client.send_fax.call_args.kwargs[
            'attachments'
        ]
        _, cover_sheet_bytes, _ = attachments[0]
        with fitz.open(stream=cover_sheet_bytes, filetype='pdf') as doc:
            fields = {
                widget.field_name: widget.field_value
                for page in doc
                for widget in (page.widgets() or [])
            }
        assert fields.get("Rendering Provider's NPI"), (
            'Form 13614 was faxed to Novitas with a blank rendering-'
            'provider NPI'
        )
        assert fields.get("Rendering Provider's Name and Address")

    @pytest.mark.asyncio
    async def test_2_placeholder_dob_blocks_submission(
        self, db_session, admins, build_services, extracted_data
    ):
        """A DOB the extractor didn't find must not count as filled in."""
        extracted_data.patient_date_of_birth = None
        fax_service, service = build_services(db_session)
        fax = await fax_service.process_inbound_message('rc-referral-4')
        draft = await service.create_draft_request_from_fax(fax.id)
        await db_session.commit()

        completion = await service.get_completion_status(request=draft)

        assert not completion.can_submit
        assert any(
            'birth' in item.name.lower() for item in completion.missing_fields
        ), [item.name for item in completion.missing_fields]

    # --- #3 Fax processing reliability ---------------------------------

    @pytest.mark.asyncio
    async def test_3_failed_fax_can_be_reprocessed(
        self, db_session, admins, build_services, mock_ringcentral_client
    ):
        """A fax that failed on a transient error can be taken in later."""
        fax_service, service = build_services(db_session)
        mock_ringcentral_client.download_attachment.side_effect = (
            httpx.ConnectTimeout('RingCentral timed out')
        )
        with pytest.raises(httpx.ConnectTimeout):
            await fax_service.process_inbound_message('rc-referral-5')
        fax = await IncomingFaxDAO(db_session).get_by_provider_message_id(
            'rc-referral-5'
        )
        assert fax.status == FaxStatus.FAILED

        mock_ringcentral_client.download_attachment.side_effect = None
        await _reprocess_fax(fax_service, service, fax_id=fax.id)

        await db_session.refresh(fax)
        assert fax.status != FaxStatus.FAILED
        assert fax.s3_key

    @pytest.mark.asyncio
    async def test_3_stuck_processing_fax_can_be_reprocessed(
        self, db_session, admins, build_services
    ):
        """A fax left in PROCESSING by a dead worker gets exactly one draft."""
        fax_service, service = build_services(db_session)
        fax = await fax_service.process_inbound_message('rc-referral-6')
        await IncomingFaxDAO(db_session).update_status(
            fax_id=fax.id, status=FaxStatus.PROCESSING
        )
        await db_session.commit()

        await _reprocess_fax(fax_service, service, fax_id=fax.id)

        await db_session.refresh(fax)
        assert fax.status == FaxStatus.MATCHED
        assert fax.request_id is not None

    # --- #4 Duplicate submissions ---------------------------------------

    @pytest.mark.asyncio
    async def test_4_timeout_after_send_is_not_resent(
        self,
        db_session,
        admins,
        build_services,
        mock_ringcentral_client,
        approved_provider_request,
    ):
        """A timed-out send may have reached Novitas - never auto-resend.

        RingCentral can accept the fax and still time out on the reply.
        A retry (or a second click) must not fax the PHI package again.
        """
        _, reviewer = admins
        reviewer_id = reviewer.id
        request_id = approved_provider_request.id
        _, service = build_services(db_session)
        mock_ringcentral_client.send_fax.side_effect = httpx.ReadTimeout(
            'no response from RingCentral'
        )

        with pytest.raises(Exception):  # noqa: B017, PT011
            await service.submit_to_novitas(
                request_id=request_id, user=reviewer
            )
        # The retry is a new HTTP request: fresh session state, fresh
        # user row - not the objects the failed attempt left expired.
        await db_session.rollback()
        reviewer = await db_session.get(User, reviewer_id)

        mock_ringcentral_client.send_fax.side_effect = None
        try:
            await service.submit_to_novitas(
                request_id=request_id, user=reviewer
            )
        except Exception as exc:
            assert 'greenlet' not in str(exc), exc  # noqa: PT017

        assert mock_ringcentral_client.send_fax.await_count == 1, (
            'Package was faxed to Novitas a second time after a timeout'
        )

    @pytest.mark.asyncio
    async def test_4_own_outbound_fax_is_not_ingested_as_inbound(
        self,
        db_session,
        admins,
        build_services,
        mock_ringcentral_client,
        mock_process_inbound_fax_task,
    ):
        """Our own fax to Novitas must not come back in as a referral."""
        fax_service, _ = build_services(db_session)
        mock_ringcentral_client.get_message.return_value = _inbound_message(
            direction='Outbound',
            **{
                'from': {'phoneNumber': PAAI_RINGCENTRAL_FAX_NUMBER},
                'to': [{'phoneNumber': NOVITAS_FAX_NUMBER}],
            },
        )

        await fax_service.process_inbound_message('rc-own-outbound')

        stored = await IncomingFaxDAO(db_session).get_by_provider_message_id(
            'rc-own-outbound'
        )
        assert stored is None or stored.direction != FaxDirection.INBOUND
        mock_process_inbound_fax_task.assert_not_called()

    # --- #5 Fax webhook security ----------------------------------------

    def test_5_webhook_rejects_non_ascii_token_with_401(self):
        """A malformed token is an auth failure, not a server error."""
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post('/Prod/api/v1/fax/webhook?token=%C3%A4', json={})

        assert response.status_code == 401

    # --- #6 Audit logging -----------------------------------------------

    @pytest.mark.asyncio
    async def test_6_audit_failure_does_not_break_viewing_a_request(
        self, db_session, admins, build_services, ambulance_request_factory
    ):
        """If the audit insert fails, the admin still gets the request."""
        _, reviewer = admins
        _, service = build_services(db_session)
        request = await ambulance_request_factory(
            user_id=reviewer.id, status=RequestStatus.SUBMITTED
        )
        await db_session.commit()
        service._access_log_dao.create = AsyncMock(  # noqa: SLF001
            side_effect=RuntimeError('audit table unavailable')
        )

        result = await service.get_request_by_id(
            user=reviewer, request_id=request.id
        )

        assert result.id == request.id

    # --- #8 Patient names -----------------------------------------------

    @pytest.mark.parametrize(
        ('first_name', 'last_name'),
        [
            ('Mary', "O'Brien"),
            ('Li', 'Ng'),
            ('Anna', 'Smith-Jones'),
            ('Mary Ann', 'Van Buren'),
        ],
    )
    def test_8_real_patient_names_are_accepted_on_submit_and_edit(
        self, first_name, last_name
    ):
        """Names with apostrophes, hyphens, spaces or 2 letters are valid."""
        try:
            _submission_data(
                1, patient_first_name=first_name, patient_last_name=last_name
            )
            AdminUpdateRequestSchema(
                patient_first_name=first_name, patient_last_name=last_name
            )
        except ValidationError as exc:
            pytest.fail(f'{first_name} {last_name} rejected: {exc}')

    @pytest.mark.asyncio
    async def test_8_request_with_real_name_can_be_returned_by_api(
        self, db_session, admins, ambulance_request_factory
    ):
        """A stored O'Brien must serialize, or every GET of it is a 500."""
        _, reviewer = admins
        request = await ambulance_request_factory(
            user_id=reviewer.id, patient_last_name="O'Brien"
        )
        await db_session.commit()

        try:
            AmbulanceRequestResponseSchema.model_validate(request)
        except ValidationError as exc:
            pytest.fail(f"Stored O'Brien can't be serialized: {exc}")
