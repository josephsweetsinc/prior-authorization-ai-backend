"""Service for generating Call Sheet PDFs from the org's fillable template."""

import logging
from collections.abc import Callable
from pathlib import Path

import fitz

from models.ambulance_request import AmbulanceRequest

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / 'assets'
    / 'templates'
    / 'masters_ambulance_call_sheet.pdf'
)

# Maps the template's AcroForm field names to how to derive their value
# from an AmbulanceRequest. Every other field on the template (vitals,
# pupils, lung sounds, chief complaint, medications, allergies, narrative,
# driver/attendant/coach#, times, etc.) is filled in by hand by the crew
# during the actual transport - none of that data exists in the prior
# authorization request.
FIELD_VALUE_GETTERS: dict[str, Callable[[AmbulanceRequest], str]] = {
    'PATIENT NAME': (
        lambda r: f'{r.patient_first_name} {r.patient_last_name}'.strip()
    ),
    'ORIGIN': lambda r: r.pickup_address or '',
    'DESTINATION': lambda r: r.destination_address or '',
    'DATE OF SERVICE': (
        lambda r: r.date_of_transport.strftime('%m/%d/%Y')
        if r.date_of_transport
        else ''
    ),
    'ORDERED BY': lambda r: r.ordering_physician or '',
}


class CallSheetService:
    """Service for generating Call Sheet PDFs from the org's template.

    Fills the fields on the real, fillable Masters Ambulance Service
    Transport Call Sheet template that are known ahead of time from the
    ambulance request; every other field is left blank and fillable for
    the crew to complete by hand during the run.

    """

    def __init__(self, template_path: Path | None = None) -> None:
        """Initialize CallSheetService.

        Args:
            template_path: Optional path to the fillable PDF template.
                Defaults to the bundled Masters Ambulance Service template.

        """
        self._template_path = template_path or DEFAULT_TEMPLATE_PATH

    def generate_call_sheet_pdf(self, request: AmbulanceRequest) -> bytes:
        """Generate a Call Sheet PDF pre-filled from an ambulance request.

        Args:
            request: AmbulanceRequest instance to source field values from.

        Returns:
            bytes: Filled (but not flattened) PDF file bytes.

        Raises:
            FileNotFoundError: If the template PDF is missing.

        """
        if not self._template_path.exists():
            raise FileNotFoundError(  # noqa: TRY003
                f'Call Sheet template not found at {self._template_path}'
            )

        doc = fitz.open(self._template_path)
        try:
            filled_count = 0
            for page_num in range(doc.page_count):
                page = doc[page_num]
                for widget in page.widgets() or []:  # type: ignore[attr-defined]
                    getter = FIELD_VALUE_GETTERS.get(widget.field_name)
                    if getter is None:
                        continue
                    widget.field_value = getter(request)
                    widget.update()
                    filled_count += 1
            pdf_bytes: bytes = doc.tobytes()
        finally:
            doc.close()

        logger.info(
            'Generated Call Sheet PDF for request %s '
            '(%d fields filled, size: %d bytes)',
            getattr(request, 'id', 'unknown'),
            filled_count,
            len(pdf_bytes),
        )
        return pdf_bytes
