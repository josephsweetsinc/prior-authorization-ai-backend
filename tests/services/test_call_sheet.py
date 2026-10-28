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


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract all rendered text from a filled PDF's bytes.

    Unlike _read_field_values (which reads the stored field value -
    always the full string regardless of whether it visually fits),
    this reads what actually gets drawn on the page, which is what
    catches a field silently clipping part of its text off.
    """
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        return ''.join(page.get_text() for page in doc)
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

    def test_generate_does_not_truncate_long_addresses(
        self, service: CallSheetService
    ):
        """Test that a long address isn't silently clipped off the
        rendered PDF.

        ORIGIN/DESTINATION are narrower than some real addresses at
        the template's original fixed font size - a prior check found
        ZIP codes missing from the rendered document even though the
        full address was stored as the field's value. _read_field_
        values can't catch this (it always returns the full stored
        string); only checking the actual rendered text can.
        """  # noqa: D205
        long_origin = (
            '12345 West Industrial Parkway Boulevard, '
            'Suite 4500, Pittsburgh, PA 15222'
        )
        long_destination = (
            'Allegheny General Hospital Emergency Department, '
            '320 East North Avenue, Pittsburgh, PA 15212'
        )
        request = _make_request(
            pickup_address=long_origin,
            destination_address=long_destination,
        )

        pdf_bytes = service.generate_call_sheet_pdf(request)

        text = _extract_text(pdf_bytes)
        assert long_origin in text
        assert long_destination in text

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

    def test_generate_explicit_empty_value_is_not_overridden_by_derived(
        self, service: CallSheetService
    ):
        """Test that explicitly clearing one of the five known fields
        leaves it blank, instead of falling back to the derived value.
        """  # noqa: D205
        request = _make_request(call_sheet_data={'PATIENT NAME': ''})

        pdf_bytes = service.generate_call_sheet_pdf(request)

        values = _read_field_values(pdf_bytes)
        assert values['PATIENT NAME'] == ''

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

    def test_generate_strips_embedded_javascript(
        self, service: CallSheetService
    ):
        """Test that no reachable JavaScript survives generation.

        The bundled template's Submit button runs a script with a
        hardcoded mailto SUBMITURL that would email a filled-in copy of
        the form - with real patient data - outside the app. Nothing
        reachable from the catalog or any widget should execute script
        content in the generated PDF.
        """
        pdf_bytes = service.generate_call_sheet_pdf(_make_request())

        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        try:
            for xref in range(1, doc.xref_length()):
                try:
                    obj = doc.xref_object(xref)
                except Exception:  # noqa: S112
                    continue
                assert '/S /JavaScript' not in obj, (
                    f'live JavaScript action survived at xref {xref}'
                )

            catalog = doc.xref_object(doc.pdf_catalog())
            assert '/AA null' in catalog or '/AA' not in catalog
        finally:
            doc.close()

    def test_generate_removes_submit_button(
        self, service: CallSheetService
    ):
        """Test that the Submit Form button widget is removed."""
        pdf_bytes = service.generate_call_sheet_pdf(_make_request())

        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        try:
            button_fields = [
                widget.field_name
                for page in doc
                for widget in (page.widgets() or [])
                if widget.field_type_string == 'Button'
            ]
            assert button_fields == []
        finally:
            doc.close()

    def test_generate_stays_a_live_fillable_form(
        self, service: CallSheetService
    ):
        """Test that stripping scripts doesn't flatten the form.

        Removing the Submit button and embedded JavaScript is a
        targeted fix for the exfiltration/auto-run risk, not a reason
        to flatten the rest of the form - crews still need to fill in
        the remaining ~115 fields by hand after generation.
        """
        pdf_bytes = service.generate_call_sheet_pdf(_make_request())

        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        try:
            assert doc.is_form_pdf
            field_names = {
                widget.field_name
                for page in doc
                for widget in (page.widgets() or [])
            }
            assert 'DRIVER' in field_names
            assert 'Narrative 1' in field_names
        finally:
            doc.close()
