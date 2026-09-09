from datetime import date, datetime, time
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models import BaseIdMixin, BaseTimeStampMixin, SoftDelete

if TYPE_CHECKING:
    from models import RequestFile, User
    from models.incoming_fax import IncomingFax


class TransportationType(StrEnum):
    """Enumeration of transportation types."""

    AMBULANCE = 'ambulance'
    WHEELCHAIR = 'wheelchair'
    STRETCHER = 'stretcher'
    BLS = 'bls'  # Basic Life Support
    ALS = 'als'  # Advanced Life Support
    CCT = 'cct'  # Critical Care Transport


class RequestStatus(StrEnum):
    """Enumeration of request statuses."""

    DRAFT = 'draft'
    SUBMITTED = 'submitted'
    PENDING = 'pending'
    APPROVED = 'approved'
    DENIED = 'denied'


class NovitasStatus(StrEnum):
    """Enumeration of Novitas prior-authorization submission statuses.

    Tracks the external Novitas (Medicare Administrative Contractor)
    determination separately from this system's own internal
    RequestStatus (which reflects our admin's internal review, not
    Novitas's decision). UTN_RECEIVED, APPROVED, DENIED, and
    ADDITIONAL_INFO_REQUESTED are recorded manually by an admin once
    known, since Novitas does not expose an API to poll or parse.
    """

    NOT_SUBMITTED = 'not_submitted'
    SUBMITTED = 'submitted'
    UTN_RECEIVED = 'utn_received'
    ADDITIONAL_INFO_REQUESTED = 'additional_info_requested'
    APPROVED = 'approved'
    DENIED = 'denied'


class DenialReason(StrEnum):
    """Enumeration of denial reasons."""

    DUPLICATE_REQUEST = 'duplicate_request'
    INVALID_REQUEST_TYPE = 'invalid_request_type'
    INVALID_DIAGNOSIS_CODE = 'invalid_diagnosis_code'
    MISSING_PHYSICIAN_SIGNATURE = 'missing_physician_signature'
    TRANSPORT_LEVEL_NOT_MEDICALLY_NECESSARY = (
        'transport_level_not_medically_necessary'
    )
    INCOMPLETE_MEDICAL_DOCUMENTATION = 'incomplete_medical_documentation'
    OUTDATED_OR_EXPIRED_DOCUMENTS = 'outdated_or_expired_documents'
    INCORRECT_OR_INCONSISTENT_PATIENT_INFORMATION = (
        'incorrect_or_inconsistent_patient_information'
    )
    OTHER_REASON = 'other_reason'


class AmbulatoryStatus(StrEnum):
    """Enumeration of ambulatory statuses."""

    AMBULATORY = 'ambulatory'
    NON_AMBULATORY = 'non-ambulatory'


class PatientSex(StrEnum):
    """Enumeration of patient sex (CMS-1500 Box 3)."""

    MALE = 'male'
    FEMALE = 'female'


class InsuranceType(StrEnum):
    """Enumeration of insurance/payer types (CMS-1500 Box 1)."""

    MEDICARE = 'medicare'
    MEDICAID = 'medicaid'
    TRICARE = 'tricare'
    CHAMPVA = 'champva'
    GROUP_HEALTH_PLAN = 'group_health_plan'
    FECA_BLACK_LUNG = 'feca_black_lung'
    OTHER = 'other'


class PatientRelationshipToInsured(StrEnum):
    """Enumeration of patient's relationship to insured (CMS-1500 Box 6)."""

    SELF = 'self'
    SPOUSE = 'spouse'
    CHILD = 'child'
    OTHER = 'other'


class AmbulanceRequest(BaseIdMixin, BaseTimeStampMixin, SoftDelete):
    """Ambulance request model.

    Fields:
    - user_id: ID of the user (provider) who created the request.
    - transportation_type: Type of transportation (enum).
    - patient_first_name: Patient's first name.
    - patient_last_name: Patient's last name.
    - patient_date_of_birth: Patient's date of birth.
    - patient_id: Patient's ID.
    - date_of_transport: Date of transport.
    - time_of_transport: Time of transport.
    - pickup_address: Pickup address.
    - destination_address: Destination address.
    - primary_diagnosis: Primary diagnosis (filled by AI later).
    - medical_justification: Medical justification (filled by AI later).
    - status: Current status of the request.
    - form_number: CMS form number (e.g., CMS-10344).
    - reviewer_id: ID of the reviewer (provider) who set the request status.
    - ambulatory_status: Ambulatory status of the patient (enum).
    - oxygen_required: Whether oxygen is required for the patient.
    - ai_accuracy: AI confidence in filled data (percentage with 1 decimal).
    - ordering_physician: Name of the ordering physician.
    - physician_phone: Phone number of the ordering physician.
    """

    __tablename__ = 'ambulance_requests'

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        comment='ID of the user who created the request',
    )
    transportation_type: Mapped[TransportationType] = mapped_column(
        Enum(TransportationType),
        nullable=False,
        comment='Type of transportation',
    )
    patient_first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment='Patient first name',
    )
    patient_last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment='Patient last name',
    )
    patient_date_of_birth: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment='Patient date of birth',
    )
    patient_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment='Patient ID',  #  Medicare number
    )
    date_of_transport: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment='Date of transport',
    )
    time_of_transport: Mapped[time] = mapped_column(
        Time,
        nullable=False,
        comment='Time of transport',
    )
    pickup_address: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment='Pickup address',
    )
    destination_address: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment='Destination address',
    )
    primary_diagnosis: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment='Primary diagnosis (filled by AI)',
    )
    medical_justification: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment='Medical justification (filled by AI)',
    )
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus),
        nullable=False,
        server_default='DRAFT',
        comment='Current status of the request',
    )
    denial_reason: Mapped[DenialReason | None] = mapped_column(
        Enum(DenialReason),
        nullable=True,
        comment='Reason for denial if request was denied',
    )
    denial_notes: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        comment='Additional notes for denial (required if denial_reason is OTHER_REASON)',  # noqa: E501
    )
    form_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment='CMS form number (e.g., CMS-10344)',
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        comment='ID of the reviewer (provider) who set the request status',
    )
    ambulatory_status: Mapped['AmbulatoryStatus | None'] = mapped_column(
        Enum(AmbulatoryStatus),
        nullable=True,
        comment='Ambulatory status of the patient',
    )
    oxygen_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default='false',
        comment='Whether oxygen is required for the patient',
    )
    ai_accuracy: Mapped[float | None] = mapped_column(
        Numeric(4, 1),
        nullable=True,
        comment='AI confidence in filled data (percentage with 1 decimal place, e.g., 37.3)',  # noqa: E501
    )
    ordering_physician: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment='Name of the ordering physician',
    )
    physician_phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment='Phone number of the ordering physician',
    )
    expiration_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment='Prior authorization expiration date',
    )
    patient_sex: Mapped['PatientSex | None'] = mapped_column(
        Enum(PatientSex),
        nullable=True,
        comment='Patient sex (CMS-1500 Box 3)',
    )
    ordering_physician_npi: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment='NPI of the ordering physician (CMS-1500 Box 17b)',
    )
    insurance_type: Mapped['InsuranceType | None'] = mapped_column(
        Enum(InsuranceType),
        nullable=True,
        comment='Type of insurance/payer (CMS-1500 Box 1)',
    )
    insurance_payer_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment='Name of the insurance carrier/payer',
    )
    insured_id_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment=(
            "Insured's ID number (CMS-1500 Box 1a); "
            'same as patient_id when the patient is the insured'
        ),
    )
    insured_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment=(
            "Insured's name (CMS-1500 Box 4) if different from the patient"
        ),
    )
    patient_relationship_to_insured: Mapped[
        'PatientRelationshipToInsured | None'
    ] = mapped_column(
        Enum(PatientRelationshipToInsured),
        nullable=True,
        comment="Patient's relationship to insured (CMS-1500 Box 6)",
    )
    utn: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment=(
            'Unique Tracking Number issued by Novitas once a prior '
            'authorization decision is made (CMS-1500 Box 23)'
        ),
    )
    novitas_status: Mapped['NovitasStatus'] = mapped_column(
        Enum(NovitasStatus),
        nullable=False,
        server_default='NOT_SUBMITTED',
        comment='Status of the external Novitas prior authorization',
    )
    novitas_submitted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment='When the Novitas PA package was faxed to Novitas',
    )
    novitas_fax_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('incoming_faxes.id', ondelete='SET NULL'),
        nullable=True,
        comment='Outbound fax record for the Novitas PA package submission',
    )

    # Relationships
    reviewer: Mapped['User | None'] = relationship(
        'User',
        foreign_keys=[reviewer_id],
    )
    status_history: Mapped[list['RequestStatusHistory']] = relationship(
        'RequestStatusHistory',
        back_populates='request',
        cascade='all, delete-orphan',
    )
    files: Mapped[list['RequestFile']] = relationship(
        'RequestFile',
        back_populates='request',
        cascade='all, delete-orphan',
    )
    novitas_fax: Mapped['IncomingFax | None'] = relationship(
        'IncomingFax',
        foreign_keys=[novitas_fax_id],
    )

    @property
    def patient_full_name(self) -> str:
        """Return patient full name."""
        return f'{self.patient_first_name} {self.patient_last_name}'

    def __repr__(self) -> str:
        """Return a string representation of the request."""
        return f'<AmbulanceRequest {self.id} - {self.status}>'


class RequestStatusHistory(BaseIdMixin, BaseTimeStampMixin):
    """Request status history model for tracking status changes.

    Fields:
    - request_id: ID of the ambulance request.
    - status: Status at this point in time.
    - notes: Optional notes about the status change.
    """

    __tablename__ = 'request_status_history'

    request_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('ambulance_requests.id', ondelete='CASCADE'),
        nullable=False,
        comment='ID of the ambulance request',
    )
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus),
        nullable=False,
        comment='Status at this point in time',
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment='Optional notes about the status change',
    )

    # Relationships
    request: Mapped['AmbulanceRequest'] = relationship(
        'AmbulanceRequest',
        back_populates='status_history',
    )

    def __repr__(self) -> str:
        """Return a string representation of the status history."""
        return (
            f'<RequestStatusHistory {self.id} - '
            f'Request {self.request_id} - {self.status}>'
        )
