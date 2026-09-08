"""Tests for CallSheetService."""

from datetime import date
from types import SimpleNamespace

import fitz
import pytest

from services.call_sheet import CallSheetService


def _make_request(**overrides):
    """Build a lightweight stand-in for an AmbulanceRequest."""
    defaults = {
        'id': 1,
        'patient_first_name': 'John',
        'patient_last_name': 'Doe',
        'pickup_address': '123 Main St, Springfield, IL 62701',
        'destination_address': (
            'Memorial Dialysis Center, 456 Medical Dr, Springfield, IL 62702'
        ),
        'date_of_transport': date(2026, 3, 15),
        'ordering_physician': 'Dr. Jane Smith',
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _read_field_values(pdf_bytes: bytes) -> dict[str, str]:
    """Read all AcroForm field values from a filled PDF's bytes."""
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        values = {}
        for page in doc:
            for widget in page.widgets() or []:
                values[widget.field_name] = widget.field_value
        return values
    finally:
        doc.close()


class TestCallSheetService:
    """Test suite for CallSheetService."""

    @pytest.fixture
    def service(self) -> CallSheetService:
        """Create CallSheetService using the real bundled template."""
        return CallSheetService()

    def test_generate_fills_known_fields(self, service: CallSheetService):
        """Test that the five known fields are filled with request data."""
        request = _make_request()

        pdf_bytes = service.generate_call_sheet_pdf(request)

        values = _read_field_values(pdf_bytes)
        assert values['PATIENT NAME'] == 'John Doe'
        assert values['ORIGIN'] == '123 Main St, Springfield, IL 62701'
        assert values['DESTINATION'] == (
            'Memorial Dialysis Center, 456 Medical Dr, Springfield, IL 62702'
        )
        assert values['DATE OF SERVICE'] == '03/15/2026'
        assert values['ORDERED BY'] == 'Dr. Jane Smith'

    def test_generate_leaves_clinical_fields_blank(
        self, service: CallSheetService
    ):
        """Test that clinical/dispatch fields the request has no data for
        are left blank (not filled with placeholder text).
        """  # noqa: D205
        request = _make_request()

        pdf_bytes = service.generate_call_sheet_pdf(request)

        values = _read_field_values(pdf_bytes)
        assert values.get('DRIVER') in (None, '')
        assert values.get('COACH') in (None, '')
        assert values.get('Narrative 1') in (None, '')

    def test_generate_handles_missing_optional_fields(
        self, service: CallSheetService
    ):
        """Test that a missing ordering physician doesn't raise."""
        request = _make_request(ordering_physician=None)

        pdf_bytes = service.generate_call_sheet_pdf(request)

        values = _read_field_values(pdf_bytes)
        assert values['ORDERED BY'] == ''

    def test_generate_missing_template_raises(self, tmp_path):
        """Test that a missing template file raises FileNotFoundError."""
        service = CallSheetService(
            template_path=tmp_path / 'does-not-exist.pdf'
        )

        with pytest.raises(FileNotFoundError):
            service.generate_call_sheet_pdf(_make_request())
