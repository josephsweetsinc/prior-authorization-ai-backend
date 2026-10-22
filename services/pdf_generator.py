"""Service for generating the Novitas Form 13614 cover sheet."""

import logging
from pathlib import Path
from typing import Any

import fitz

from models.ambulance_request import AmbulanceRequest, PatientSex
from models.organization import Organization
from models.user import User

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / 'assets'
    / 'templates'
    / 'novitas_form_13614.pdf'
)

# The form's State combo box is constrained to the Novitas jurisdiction's
# states; an unrecognized/unparseable value is left blank rather than
# guessed, consistent with not inventing placeholder data.
_FORM_STATE_CHOICES = frozenset({'NJ', 'PA'})


def _parse_state_from_address(address: str | None) -> str | None:
    """Best-effort extraction of a 2-letter state code from a free-text address.

    Limited to the states this form actually accepts.

    Args:
        address: Free-text address string (e.g.
            "123 Main St, Springfield, NJ 07001").

    Returns:
        str | None: The matched state code, or None if no state in
            ``_FORM_STATE_CHOICES`` is confidently found.

    """
    if not address:
        return None
    tokens = address.replace(',', ' ').split()
    for token in tokens:
        candidate = token.strip().upper()
        if candidate in _FORM_STATE_CHOICES:
            return candidate
    return None


class PDFGeneratorService:
    """Service for generating the Novitas Form 13614 cover sheet.

    Fills the real, fillable CMS template rather than recreating it.
    """

    def __init__(self, template_path: Path | None = None) -> None:
        """Initialize PDFGeneratorService.

        Args:
            template_path: Optional path to the fillable Form 13614 PDF.
                Defaults to the bundled Novitas template.

        """
        self._template_path = template_path or DEFAULT_TEMPLATE_PATH

    def generate_novitas_cover_sheet_pdf(
        self,
        request: AmbulanceRequest,
        organization: Organization | None,
        submitted_by: User,
    ) -> bytes:
        """Generate the Novitas Form 13614 Medicare Part B fax cover sheet.

        Fills the real CMS form's AcroForm fields from the request (the
        beneficiary being transported) and the organization (the
        rendering/ambulance provider's own billing identity - NPI,
        address, and contact info, which don't vary per request). The
        output stays a live, editable form - the template has no
        JavaScript and no Submit button to strip (unlike the Call Sheet
        template), and the business workflow requires a fillable cover
        sheet so last-minute corrections can be made before faxing.

        Args:
            request: AmbulanceRequest instance to source beneficiary and
                transport data from.
            organization: The submitting user's Organization, for the
                rendering provider's NPI/address/contact fields. May be
                None if the organization profile hasn't been set up yet,
                in which case those fields are left blank.
            submitted_by: The admin user generating/submitting this
                package, used for the "Contact Name" and "Request
                Completed by" fields.

        Returns:
            bytes: PDF file bytes, pre-filled and still editable.

        Raises:
            FileNotFoundError: If the template PDF is missing.

        """
        if not self._template_path.exists():
            raise FileNotFoundError(  # noqa: TRY003
                f'Novitas Form 13614 template not found at '
                f'{self._template_path}'
            )

        contact_name = f'{submitted_by.name} {submitted_by.surname}'.strip()
        dob = (
            request.patient_date_of_birth.strftime('%m/%d/%Y')
            if request.patient_date_of_birth
            else ''
        )
        rendering_provider_name_and_address = '\n'.join(
            part
            for part in (
                organization.medic_name if organization else None,
                organization.address if organization else None,
            )
            if part
        )
        state = _parse_state_from_address(request.pickup_address)

        text_values = {
            'Beneficiary Last Name': request.patient_last_name or '',
            'Beneficiary First Name': request.patient_first_name or '',
            'HICN': request.patient_id or '',
            'Date of Birth': dob,
            "Rendering Provider's NPI": (
                organization.npi if organization else ''
            )
            or '',
            "Rendering Provider's Name and Address": (
                rendering_provider_name_and_address
            ),
            'Contact Name': contact_name,
            'Contact Phone Number': (
                organization.phone if organization else ''
            )
            or '',
            'Contact Fax Number': (organization.fax if organization else '')
            or '',
            'Number of Trips': (
                str(request.number_of_trips)
                if request.number_of_trips is not None
                else ''
            ),
            'Start Date of Authorization': (
                request.authorization_start_date.strftime('%m/%d/%Y')
                if request.authorization_start_date
                else ''
            ),
            'Date': '',
        }

        doc = fitz.open(self._template_path)
        try:
            page = doc[0]
            filled_count = 0
            for widget in page.widgets() or []:  # type: ignore[attr-defined]
                name = widget.field_name
                if name == 'Gender':
                    self._set_gender_widget(widget, request.patient_sex)
                    filled_count += 1
                    continue
                if name == 'Procedure Code(s)':
                    widget.field_value = request.procedure_code.value
                    widget.update()
                    filled_count += 1
                    continue
                if name == 'State':
                    widget.field_value = state or ' '
                    widget.update()
                    if state:
                        filled_count += 1
                    continue
                if name in text_values:
                    value = text_values[name]
                    if not value:
                        continue
                    widget.field_value = value
                    widget.update()
                    filled_count += 1

            pdf_bytes: bytes = doc.tobytes()
        finally:
            doc.close()

        logger.info(
            'Generated Novitas Form 13614 cover sheet for request %s '
            '(%d fields filled, size: %d bytes)',
            getattr(request, 'id', 'unknown'),
            filled_count,
            len(pdf_bytes),
        )
        return pdf_bytes

    @staticmethod
    def _set_gender_widget(
        widget: Any, patient_sex: PatientSex | None
    ) -> None:
        """Select the correct button in the Gender radio group.

        Each Male/Female option is a separate widget sharing the field
        name "Gender"; selecting one requires setting its own field_value
        to its export name and every other option in the group to "Off" -
        setting a shared field name to a single string across widgets
        does not reliably clear the others.

        Args:
            widget: One widget instance of the "Gender" radio group.
            patient_sex: The request's patient sex, or None if unknown.

        """
        states = widget.button_states().get('normal', [])
        on_name = next((s for s in states if s != 'Off'), None)
        desired = (
            'Male'
            if patient_sex == PatientSex.MALE
            else 'Female'
            if patient_sex == PatientSex.FEMALE
            else None
        )
        widget.field_value = on_name if on_name == desired else 'Off'
        widget.update()
