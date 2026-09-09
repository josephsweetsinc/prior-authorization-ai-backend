"""Tests for CMS1500GeneratorService."""

from datetime import date
from types import SimpleNamespace

import fitz
import pytest

from models.ambulance_request import (
    InsuranceType,
    PatientRelationshipToInsured,
    PatientSex,
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
