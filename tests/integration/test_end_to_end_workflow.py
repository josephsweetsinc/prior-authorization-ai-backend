"""End-to-end integration test for the full prior-authorization workflow.

Exercises the complete lifecycle this product is built around: receive
fax -> create request -> human reviews -> approve -> generate correct
package -> submit to Novitas -> receive response -> update the
existing request.

Each step was already covered by its own unit tests on the branch that
built it. What those can't catch is how the pieces behave once wired
together - this test shares one AmbulanceRequestService and one
FaxService, backed by the same real DB session and real DAOs, across
every step, and mocks only the true external boundaries: the
RingCentral HTTP API, S3 storage, and the AI extraction LLM. The PDF
generation step is real (the actual bundled Form 13614 template filled
via PyMuPDF), not mocked, since that's exactly the "generate correct
package" step the workflow depends on.
"""

from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

import fitz
import pytest

from config.settings import Settings
from dao import AmbulanceRequestDAO
from models.ambulance_request import NovitasStatus, RequestStatus
from models.incoming_fax import FaxStatus
from models.user import UserRole
from schemas.ai_extraction import (
    AIExtractionResponse,
    ExtractedTransportationData,
)
from schemas.ambulance_request import (
    AdminUpdateRequestSchema,
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


class TestEndToEndWorkflow:
    """Full fax-to-Novitas-response lifecycle, across real services."""

    @pytest.fixture(autouse=True)
    def _configure_settings(self):
        """Configure the Novitas fax number and fax-intake admin for
        this test, restoring both afterward.
        """  # noqa: D205
        settings = Settings.load()
        original_novitas_number = (
            settings.ringcentral_settings.NOVITAS_FAX_NUMBER
        )
        original_intake_admin_email = (
            settings.ringcentral_settings.FAX_INTAKE_ADMIN_EMAIL
        )
        settings.ringcentral_settings.NOVITAS_FAX_NUMBER = NOVITAS_FAX_NUMBER
        settings.ringcentral_settings.FAX_INTAKE_ADMIN_EMAIL = (
            'fax-intake@example.com'
        )
        yield
        settings.ringcentral_settings.NOVITAS_FAX_NUMBER = (
            original_novitas_number
        )
        settings.ringcentral_settings.FAX_INTAKE_ADMIN_EMAIL = (
            original_intake_admin_email
        )

    @pytest.fixture(autouse=True)
    def mock_process_inbound_fax_task(self):
        """Prevent process_inbound_message from enqueueing a real Celery
        task, which would try to reach a Redis/AMQP broker that isn't
        available in tests - create_draft_request_from_fax is called
        directly instead, synchronously, exactly as the task would.
        """  # noqa: D205
        with patch(
            'tasks.fax_processing.process_inbound_fax.delay'
        ) as mock_delay:
            yield mock_delay

    @pytest.fixture
    def mock_s3_actions(self) -> MagicMock:
        """Mock S3Actions - the only non-DB external boundary besides
        RingCentral and the LLM.
        """  # noqa: D205
        mock = MagicMock(spec=S3Actions)
        mock.download_from_s3.return_value = (
            b'%PDF-1.4 fake PCS content',
            'application/pdf',
        )
        mock.get_presigned_url.return_value = (
            'https://s3.example.com/presigned-url'
        )
        return mock

    @pytest.fixture
    def mock_ringcentral_client(self) -> MagicMock:
        """Mock RingCentralClient, distinguishing the referral fax from
        the later Novitas response fax by message_id.
        """  # noqa: D205
        mock = MagicMock(spec=RingCentralClient)

        async def get_message_side_effect(message_id: str):
            if message_id == 'rc-novitas-response':
                return {
                    'from': {'phoneNumber': NOVITAS_FAX_NUMBER},
                    'to': [{'phoneNumber': PAAI_RINGCENTRAL_FAX_NUMBER}],
                    'faxPageCount': 1,
                    'attachments': [
                        {'id': 'att-response', 'contentType': 'application/pdf'}
                    ],
                }
            return {
                'from': {'phoneNumber': REFERRING_PROVIDER_FAX_NUMBER},
                'to': [{'phoneNumber': PAAI_RINGCENTRAL_FAX_NUMBER}],
                'faxPageCount': 3,
                'attachments': [
                    {'id': 'att-referral', 'contentType': 'application/pdf'}
                ],
            }

        mock.get_message = AsyncMock(side_effect=get_message_side_effect)
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
    def mock_ai_extraction_service(self) -> MagicMock:
        """Mock the AI extraction service - the LLM call itself, not
        the extraction plumbing around it.
        """  # noqa: D205
        mock = MagicMock(spec=AIExtractionService)
        mock.extract_data_from_files = AsyncMock(
            return_value=AIExtractionResponse(
                extracted_data=ExtractedTransportationData(
                    patient_first_name='Jane',
                    patient_last_name='Roe',
                    patient_date_of_birth=date(1975, 6, 15),
                    patient_id='1EG4TE5MK73',
                    pickup_address='123 Oak St, Springfield, IL 62701',
                    destination_address=(
                        'Memorial Dialysis Center, 456 Medical Dr, '
                        'Springfield, IL 62702'
                    ),
                    primary_diagnosis='End-stage renal disease',
                    medical_justification=(
                        'Patient requires wheelchair van transport for '
                        'dialysis three times weekly'
                    ),
                    form_number='CMS-13614',
                ),
                extraction_metadata={
                    'status': 'success',
                    'files_processed': '1',
                },
            )
        )
        return mock

    @pytest.fixture
    def fax_service(
        self, db_session, mock_s3_actions, mock_ringcentral_client
    ) -> FaxService:
        """Real FaxService, real DB session, mocked external calls."""
        return FaxService(
            db_session=db_session,
            s3_actions=mock_s3_actions,
            ringcentral_client=mock_ringcentral_client,
        )

    @pytest.fixture
    def service(
        self,
        db_session,
        mock_s3_actions,
        mock_ai_extraction_service,
        fax_service,
    ) -> AmbulanceRequestService:
        """Real AmbulanceRequestService sharing the same DB session and
        the same FaxService instance as the fixture above, so writes
        from either are visible to both.
        """  # noqa: D205
        return AmbulanceRequestService(
            db_session=db_session,
            s3_actions=mock_s3_actions,
            ai_extraction_service=mock_ai_extraction_service,
            fax_service=fax_service,
        )

    @pytest.mark.asyncio
    async def test_full_fax_to_novitas_response_lifecycle(  # noqa: PLR0915
        self,
        db_session,
        user_factory,
        fax_service: FaxService,
        service: AmbulanceRequestService,
        mock_ringcentral_client: MagicMock,
        mock_ai_extraction_service: MagicMock,
    ):
        """Walk the entire product workflow against real services.

        receive fax -> create request -> human reviews -> approve ->
        generate correct package -> submit to Novitas -> receive
        response -> update the existing request.
        """
        # An admin exists to own fax-drafted requests, and a second,
        # different admin does the actual review/approval - proving
        # the fax-draft deadlock fix (any admin, not just the one that
        # owns the draft, can act on it).
        fax_intake_admin = await user_factory(
            email='fax-intake@example.com', role=UserRole.ADMIN
        )
        reviewing_admin = await user_factory(
            email='reviewer@example.com', role=UserRole.ADMIN
        )
        await db_session.commit()

        # --- receive fax ---
        referral_fax = await fax_service.process_inbound_message(
            'rc-referral-e2e'
        )
        assert referral_fax is not None
        assert referral_fax.status == FaxStatus.RECEIVED

        # --- create request ---
        draft = await service.create_draft_request_from_fax(referral_fax.id)
        assert draft is not None
        assert draft.status == RequestStatus.DRAFT
        assert draft.user_id == fax_intake_admin.id
        assert draft.patient_first_name == 'Jane'
        mock_ai_extraction_service.extract_data_from_files.assert_awaited_once()

        await db_session.refresh(referral_fax)
        assert referral_fax.status == FaxStatus.MATCHED
        assert referral_fax.request_id == draft.id

        # --- human reviews: attaches the Verification of Medical
        # Necessity document the fax itself didn't include as a
        # separate RequestFile ---
        file_dao = service._file_dao  # noqa: SLF001
        await file_dao.create(
            request_id=draft.id,
            uploaded_by_user_id=reviewing_admin.id,
            filename='verification-of-medical-necessity.pdf',
            s3_key='faxes/supporting/verification.pdf',
            file_size=2048,
            content_type='application/pdf',
        )
        await db_session.commit()

        request_data = CreateAmbulanceRequestSchema(
            request_id=draft.id,
            transportation_type=draft.transportation_type,
            patient_first_name='Jane',
            patient_last_name='Roe',
            patient_date_of_birth=date(1975, 6, 15),
            patient_id='1EG4TE5MK73',
            date_of_transport=date(2026, 1, 15),
            time_of_transport=time(9, 30),
            pickup_address='123 Oak St, Springfield, IL 62701',
            destination_address=(
                'Memorial Dialysis Center, 456 Medical Dr, '
                'Springfield, IL 62702'
            ),
            primary_diagnosis='End-stage renal disease',
            medical_justification=(
                'Patient requires wheelchair van transport for dialysis '
                'three times weekly'
            ),
            form_number='CMS-13614',
            ordering_physician='Dr. Smith',
        )

        # --- human submits (a *different* admin than the draft's
        # owner - the deadlock fix) ---
        submitted = await service.create_request(
            user=reviewing_admin, request_data=request_data
        )
        assert submitted.status == RequestStatus.SUBMITTED

        # --- approve ---
        approved = await service.approve_request(
            request_id=draft.id, reviewer_id=reviewing_admin.id
        )
        assert approved.status == RequestStatus.APPROVED

        # --- generate correct package & submit to Novitas ---
        after_submit = await service.submit_to_novitas(
            request_id=draft.id, user=reviewing_admin
        )
        assert after_submit.novitas_status == NovitasStatus.SUBMITTED

        request_dao = AmbulanceRequestDAO(db_session)
        request_row = await request_dao.get_by_id(request_id=draft.id)
        assert request_row.novitas_fax_id is not None

        mock_ringcentral_client.send_fax.assert_awaited_once()
        send_fax_kwargs = mock_ringcentral_client.send_fax.call_args.kwargs
        assert send_fax_kwargs['to_number'] == NOVITAS_FAX_NUMBER
        cover_sheet_attachment = send_fax_kwargs['attachments'][0]
        cover_sheet_filename, cover_sheet_bytes, cover_sheet_content_type = (
            cover_sheet_attachment
        )
        assert cover_sheet_filename.startswith('Form13614_')
        assert cover_sheet_content_type == 'application/pdf'
        # The supporting document attached during review also goes out
        # with the package - a real, correct package, not just the
        # cover sheet alone.
        assert len(send_fax_kwargs['attachments']) == 2

        # The generated cover sheet is a real, live-filled AcroForm
        # against the actual bundled Form 13614 template - not a fake
        # placeholder PDF - and carries the real patient data through.
        generated_doc = fitz.open(stream=cover_sheet_bytes, filetype='pdf')
        try:
            assert generated_doc.is_form_pdf
            field_values = {
                widget.field_name: widget.field_value
                for page in generated_doc
                for widget in (page.widgets() or [])
            }
            assert field_values.get('Beneficiary Last Name') == 'Roe'
            assert field_values.get('Beneficiary First Name') == 'Jane'
        finally:
            generated_doc.close()

        # --- receive response ---
        # Novitas faxes back a determination to the same shared inbound
        # line. It must not be treated as a new patient referral.
        response_fax = await fax_service.process_inbound_message(
            'rc-novitas-response'
        )
        assert response_fax is not None
        assert response_fax.from_number == NOVITAS_FAX_NUMBER

        no_draft = await service.create_draft_request_from_fax(
            response_fax.id
        )
        assert no_draft is None
        await db_session.refresh(response_fax)
        assert response_fax.status == FaxStatus.UNRESOLVED
        assert response_fax.request_id is None

        all_requests = await request_dao.get_all(offset=0, limit=100)
        assert len(all_requests) == 1, (
            'Novitas response fax must not create a second, bogus draft'
        )

        # --- update the existing request ---
        # An admin reviews the response fax, links it to the original
        # request, and records the outcome - the two existing manual
        # tools this relies on, now reachable because the response
        # fax was held instead of being misprocessed above.
        linked_response_fax = await fax_service.link_fax_to_request(
            fax_id=response_fax.id,
            request_id=draft.id,
            matched_by_user_id=reviewing_admin.id,
        )
        assert linked_response_fax.request_id == draft.id

        final = await service.update_request_by_admin(
            request_id=draft.id,
            update_data=AdminUpdateRequestSchema(
                novitas_status=NovitasStatus.APPROVED,
                utn='A1234567890',
            ),
        )

        assert final.novitas_status == NovitasStatus.APPROVED
        assert final.utn == 'A1234567890'
        # Our own internal review status is a separate thing from
        # Novitas's external determination, and stays as the admin
        # left it.
        assert final.status == RequestStatus.APPROVED

        await db_session.refresh(response_fax)
        assert response_fax.status == FaxStatus.MATCHED
        assert response_fax.matched_by_user_id == reviewing_admin.id
