"""Tests for CMS1500GeneratorService."""

from datetime import date
from types import SimpleNamespace

import fitz
import pytest

from models.ambulance_request import (
    InsuranceType,
    PatientRelationshipToInsured,
    PatientSex,
    ProcedureCode,
)
from services.cms1500_generator import CMS1500GeneratorService


def _make_request(**overrides):
    """Build a lightweight stand-in for an AmbulanceRequest."""
    defaults = {
        'id': 1,
        'insurance_type': InsuranceType.MEDICARE,
        'insurance_payer_name': 'Medicare',
        'insured_id_number': '1EG4-TE5-MK72',
        'insured_name': None,
        'patient_relationship_to_insured': (
            PatientRelationshipToInsured.SELF
        ),
        'patient_first_name': 'John',
        'patient_last_name': 'Doe',
        'patient_date_of_birth': date(1960, 1, 1),
        'patient_sex': PatientSex.MALE,
        'patient_id': '1EG4-TE5-MK72',
        'primary_diagnosis': 'Chronic heart failure, mobility impaired',
        'ordering_physician': 'Dr. Jane Smith',
        'ordering_physician_npi': '1234567893',
        'physician_phone': '555-123-4567',
        'utn': None,
        'date_of_transport': date(2026, 3, 15),
        'number_of_trips': None,
        'procedure_code': ProcedureCode.A0428,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_organization(**overrides):
    """Build a lightweight stand-in for an Organization."""
    defaults = {
        'medic_name': 'Acme Ambulance Co.',
        'npi': '9876543210',
        'address': '789 Fleet St, Springfield, IL 62701',
        'phone': '555-987-6543',
        'fax': '555-987-6544',
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract all text from every page of a PDF's bytes."""
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        return ''.join(page.get_text() for page in doc)
    finally:
        doc.close()


class TestCMS1500GeneratorService:
    """Test suite for CMS1500GeneratorService."""

    @pytest.fixture
    def service(self) -> CMS1500GeneratorService:
        """Create CMS1500GeneratorService instance."""
        return CMS1500GeneratorService()

    def test_generate_includes_known_fields(
        self, service: CMS1500GeneratorService
    ):
        """Test that available request data appears in the generated PDF."""
        request = _make_request()

        pdf_bytes = service.generate_cms1500_pdf(request)
        text = _extract_text(pdf_bytes)

        assert 'Medicare' in text
        assert '1EG4-TE5-MK72' in text
        assert 'Doe, John' in text
        assert '01-01-1960' in text
        assert 'Male' in text
        assert 'Chronic heart failure, mobility impaired' in text
        assert 'Dr. Jane Smith' in text
        assert '1234567893' in text
        assert '555-123-4567' in text
        assert 'Self' in text

    def test_generate_notes_missing_service_line_data(
        self, service: CMS1500GeneratorService
    ):
        """Test that the service-line/billing gap is called out."""
        request = _make_request()

        pdf_bytes = service.generate_cms1500_pdf(request)
        text = _extract_text(pdf_bytes)

        assert 'billing staff' in text.lower()

    def test_generate_handles_missing_optional_fields(
        self, service: CMS1500GeneratorService
    ):
        """Test that missing insurance/physician data doesn't raise and
        renders as N/A.
        """  # noqa: D205
        request = _make_request(
            insurance_type=None,
            insurance_payer_name=None,
            insured_id_number=None,
            ordering_physician=None,
            ordering_physician_npi=None,
            physician_phone=None,
            primary_diagnosis=None,
        )

        pdf_bytes = service.generate_cms1500_pdf(request)
        text = _extract_text(pdf_bytes)

        assert 'N/A' in text

    def test_generate_includes_utn_once_issued(
        self, service: CMS1500GeneratorService
    ):
        """Test that Box 23 renders the UTN once Novitas has issued one."""
        request = _make_request(utn='A1234B5678C9')

        pdf_bytes = service.generate_cms1500_pdf(request)
        text = _extract_text(pdf_bytes)

        assert 'A1234B5678C9' in text

    def test_generate_includes_service_line_data(
        self, service: CMS1500GeneratorService
    ):
        """Test that Box 24 (date of service, HCPCS, units) is filled in
        from data this system now actually has.
        """  # noqa: D205
        request = _make_request(
            date_of_transport=date(2026, 3, 15),
            procedure_code=ProcedureCode.A0426,
            number_of_trips=12,
        )

        pdf_bytes = service.generate_cms1500_pdf(request)
        text = _extract_text(pdf_bytes)

        assert '03-15-2026' in text
        assert 'A0426' in text
        assert '12' in text

    def test_generate_includes_billing_provider_data(
        self, service: CMS1500GeneratorService
    ):
        """Test that Box 32/33 is filled in from the organization profile."""
        request = _make_request()
        organization = _make_organization()

        pdf_bytes = service.generate_cms1500_pdf(request, organization)
        text = _extract_text(pdf_bytes)

        assert 'Acme Ambulance Co.' in text
        assert '9876543210' in text
        assert '789 Fleet St, Springfield, IL' in text
        assert '62701' in text
        assert '555-987-6543' in text

    def test_generate_handles_missing_organization(
        self, service: CMS1500GeneratorService
    ):
        """Test that a request without an organization profile set up
        doesn't raise and renders blank billing-provider fields.
        """  # noqa: D205
        pdf_bytes = service.generate_cms1500_pdf(
            _make_request(), organization=None
        )
        text = _extract_text(pdf_bytes)

        assert 'N/A' in text

    def test_generate_notes_remaining_billing_gaps(
        self, service: CMS1500GeneratorService
    ):
        """Test that the still-unavailable fields (charges, diagnosis
        pointer) are called out, not silently omitted.
        """  # noqa: D205
        pdf_bytes = service.generate_cms1500_pdf(_make_request())
        text = _extract_text(pdf_bytes)

        assert 'charges' in text.lower()
        assert 'diagnosis pointer' in text.lower()

    def test_generate_fits_on_one_page(
        self, service: CMS1500GeneratorService
    ):
        """Test that the summary fits on a single page for typical data."""
        pdf_bytes = service.generate_cms1500_pdf(_make_request())

        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        try:
            assert len(doc) == 1
        finally:
            doc.close()
