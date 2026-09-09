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
        'call_sheet_data': None,
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

    def test_generate_fills_interactive_field_values(
        self, service: CallSheetService
    ):
        """Test that call_sheet_data values fill the other ~115 fields."""
        request = _make_request(
            call_sheet_data={
                'DRIVER': 'Bob Builder',
                'Dispatched': '14:32',
                'Narrative 1': 'Patient stable throughout transport.',
            }
        )

        pdf_bytes = service.generate_call_sheet_pdf(request)

        values = _read_field_values(pdf_bytes)
        assert values['DRIVER'] == 'Bob Builder'
        assert values['Dispatched'] == '14:32'
        assert values['Narrative 1'] == (
            'Patient stable throughout transport.'
        )

    def test_generate_interactive_value_overrides_derived_value(
        self, service: CallSheetService
    ):
        """Test that an interactively-entered value for one of the five
        known fields takes priority over the auto-derived one.
        """  # noqa: D205
        request = _make_request(
            call_sheet_data={'PATIENT NAME': 'Corrected Name'}
        )

        pdf_bytes = service.generate_call_sheet_pdf(request)

        values = _read_field_values(pdf_bytes)
        assert values['PATIENT NAME'] == 'Corrected Name'

    def test_get_editable_field_names_excludes_signatures_and_buttons(
        self, service: CallSheetService
    ):
        """Test that signature and submit-button widgets aren't editable."""
        names = service.get_editable_field_names()

        assert 'PATIENT NAME' in names
        assert 'Dispatched' in names
        assert 'SIGNATURE' not in names
        assert 'SubmitButton2' not in names

    def test_get_editable_field_names_missing_template_raises(
        self, tmp_path
    ):
        """Test that a missing template file raises FileNotFoundError."""
        service = CallSheetService(
            template_path=tmp_path / 'does-not-exist.pdf'
        )

        with pytest.raises(FileNotFoundError):
            service.get_editable_field_names()
