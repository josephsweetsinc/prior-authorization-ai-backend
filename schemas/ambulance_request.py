from datetime import date, datetime, time
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
)

from models.ambulance_request import (
    AmbulatoryStatus,
    DenialReason,
    InsuranceType,
    NovitasStatus,
    PatientRelationshipToInsured,
    PatientSex,
    RequestStatus,
    TransportationType,
)
from schemas.ai_extraction import ExtractedTransportationData

# Error messages
DENIAL_NOTES_REQUIRED_MSG = (
    'denial_notes is required when denial_reason is OTHER_REASON'
)


class CompletionStatus(StrEnum):
    """Enumeration of completion statuses for request validation."""

    MISSING = 'missing'  # Required item is missing
    INCOMPLETE = 'incomplete'  # Item exists but is incomplete
    COMPLETE = 'complete'  # Item is complete and valid


def get_denial_reason_display_name(reason: DenialReason) -> str:
    """Get human-readable display name for denial reason.

    Args:
        reason: Denial reason enum value.

    Returns:
        Human-readable display name.

    """
    mapping = {
        DenialReason.DUPLICATE_REQUEST: 'Duplicate Request',
        DenialReason.INVALID_REQUEST_TYPE: 'Invalid Request Type',
        DenialReason.INVALID_DIAGNOSIS_CODE: 'Invalid Diagnosis Code',
        DenialReason.MISSING_PHYSICIAN_SIGNATURE: 'Missing Physician Signature',
        DenialReason.TRANSPORT_LEVEL_NOT_MEDICALLY_NECESSARY: (
            'Transport Level Not Medically Necessary'
        ),
        DenialReason.INCOMPLETE_MEDICAL_DOCUMENTATION: (
            'Incomplete Medical Documentation'
        ),
        DenialReason.OUTDATED_OR_EXPIRED_DOCUMENTS: (
            'Outdated or Expired Documents'
        ),
        DenialReason.INCORRECT_OR_INCONSISTENT_PATIENT_INFORMATION: (
            'Incorrect or Inconsistent Patient Information'
        ),
        DenialReason.OTHER_REASON: 'Other Reason',
    }
    return mapping.get(reason, reason.value.replace('_', ' ').title())


class AmbulanceRequestsListResponseSchema(BaseModel):
    """Response schema for paginated list of requests.

    Attributes:
        items: List of ambulance requests.
        page: Current page number.
        total: Total number of requests.
        showing: Number of items shown on current page.
        total_pages: Total number of pages.

    """

    items: list['AmbulanceRequestResponseSchema'] = Field(
        description='List of ambulance requests',
    )
    page: int = Field(
        description='Current page number',
        examples=[1],
    )
    total: int = Field(
        description='Total number of requests',
        examples=[325],
    )
    showing: int = Field(
        description='Number of items shown on current page',
        examples=[8],
    )
    total_pages: int = Field(
        description='Total number of pages',
        examples=[41],
    )


class FileUploadResponseSchema(BaseModel):
    """Response schema for uploaded file."""

    id: Annotated[
        int,
        Field(
            description='Unique identifier of the uploaded file.', examples=[1]
        ),
    ]
    filename: Annotated[
        str,
        Field(
            description='Original name of the uploaded file.',
            examples=['medical_data.pdf'],
        ),
    ]
    file_size: Annotated[
        int,
        Field(
            description='Size of the uploaded file in bytes.', examples=[254920]
        ),
    ]
    content_type: Annotated[
        str,
        Field(
            description='MIME type detected for the uploaded file.',
            examples=['application/pdf'],
        ),
    ]
    file_url: Annotated[
        str,
        Field(
            description='Presigned URL for downloading the uploaded file.',
            examples=['https://s3.amazonaws.com/bucket/file.pdf'],
        ),
    ]
    model_config = ConfigDict(from_attributes=True)


class CompletionStatusItem(BaseModel):
    """Schema for a single completion status item."""

    name: str = Field(description='Name of the item being checked')
    status: CompletionStatus = Field(description='Completion status')
    message: str | None = Field(
        default=None,
        description='Helper message explaining what is needed',
    )


class CompletionStatusSchema(BaseModel):
    """Schema for overall completion status of a request."""

    overall_status: CompletionStatus = Field(
        description='Overall completion status (missing/incomplete/complete)'
    )
    missing_fields: list[CompletionStatusItem] = Field(
        default_factory=list,
        description='List of missing or incomplete required fields only',
    )
    missing_documents: list[CompletionStatusItem] = Field(
        default_factory=list,
        description='List of missing or incomplete required documents only',
    )
    can_submit: bool = Field(
        description='Whether the request can be submitted',
    )


class FileUploadWithExtractionResponseSchema(BaseModel):
    """Response schema for file upload with AI-extracted data."""

    request_id: Annotated[
        int,
        Field(
            description='ID of the created ambulance request (DRAFT status)',
            examples=[1],
        ),
    ]
    extracted_data: 'ExtractedTransportationData' = Field(
        description='Data extracted by AI from uploaded documents',
    )
    completion_status: 'CompletionStatusSchema' = Field(
        description='Completion status of the request',
    )


class CreateAmbulanceRequestParseSchema(BaseModel):
    """Input schema for initiating the AI data extraction process.

    This schema validates the payload required to trigger the AI analysis
    of previously uploaded medical documents. It ensures that at least one
    file identifier is provided to perform the extraction.

    Attributes:
        file_ids (list[int]): A list of unique identifiers for the files to be
            analyzed. Must contain at least one file ID. These IDs correspond
            to the records created during the file upload step.

    """

    file_ids: Annotated[
        list[int],
        Field(
            min_length=1,
            examples=[[1, 2, 3]],
            description='IDs of uploaded files (at least one required)',
        ),
    ]


class CreateAmbulanceRequestSchema(BaseModel):
    """Schema for creating ambulance request (combines step 2 and 3)."""

    request_id: Annotated[
        int,
        Field(
            description='ID of the draft request to update and submit',
            examples=[1],
        ),
    ]
    file_ids: Annotated[
        list[int] | None,
        Field(
            default=None,
            description='List of file IDs to link to the request',
            examples=[[1, 2]],
        ),
    ]
    transportation_type: TransportationType
    patient_first_name: Annotated[
        str,
        Field(
            min_length=3,
            max_length=15,
            pattern=r'^[a-zA-Z]+$',
            examples=['John'],
            description='Patient first name as it appears in the document',
        ),
    ]
    patient_last_name: Annotated[
        str,
        Field(
            min_length=3,
            max_length=15,
            pattern=r'^[a-zA-Z]+$',
            examples=['Doe'],
            description='Patient last name as it appears in the document',
        ),
    ]
    patient_date_of_birth: Annotated[
        date,
        Field(
            description='Patient date of birth',
            examples=[date(1960, 1, 1)],
        ),
    ]
    patient_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=50,
            description=(
                'Patient Medicare Beneficiary Identifier (MBI) or other ID'
            ),
            examples=['1EG4-TE5-MK72'],
        ),
    ]
    date_of_transport: Annotated[
        date,
        Field(
            description='Patient date of transport',
            examples=[date(2025, 12, 6)],
        ),
    ]
    time_of_transport: Annotated[
        time,
        Field(
            description='Time of transport',
            examples=[time(13, 40)],
        ),
    ]
    pickup_address: Annotated[
        str,
        Field(
            min_length=5,
            max_length=500,
            examples=['123 Main St, Springfield, IL 62701'],
        ),
    ]
    destination_address: Annotated[
        str,
        Field(
            min_length=5,
            max_length=500,
            examples=[
                'Memorial Dialysis Center, '
                '456 Medical Dr, Springfield, IL 62702'
            ],
        ),
    ]
    primary_diagnosis: str | None = Field(
        None,
        examples=['Chronic heart failure, mobility impaired'],
    )
    medical_justification: str | None = Field(
        None,
        examples=[
            'Patient requires repetitive non-emergent ambulance transport'
            ' for dialysis treatment three times weekly.'
            ' Patient is bedbound and unable to sit upright'
            ' for extended periods due to '
            'severe cardiovascular complications.'
            ' Standard wheelchair van transport is contraindicated.'
        ],
    )
    form_number: str | None = None
    ambulatory_status: AmbulatoryStatus | None = Field(
        None,
        examples=[AmbulatoryStatus.NON_AMBULATORY],
        description='Patient ambulatory status',
    )
    oxygen_required: bool = Field(
        False,  # noqa: FBT003
        examples=[False],
        description='Whether oxygen is required for the patient',
    )
    ordering_physician: str | None = Field(
        None,
        examples=['Dr. John Smith'],
        description='Name of the ordering physician',
        max_length=200,
    )
    physician_phone: str | None = Field(
        None,
        examples=['555-123-4567'],
        description='Phone number of the ordering physician',
        max_length=50,
    )
    ordering_physician_npi: str | None = Field(
        None,
        examples=['1234567893'],
        description='NPI of the ordering physician (CMS-1500 Box 17b)',
        max_length=10,
    )
    patient_sex: PatientSex | None = Field(
        None,
        examples=[PatientSex.FEMALE],
        description='Patient sex (CMS-1500 Box 3)',
    )
    insurance_type: InsuranceType | None = Field(
        None,
        examples=[InsuranceType.MEDICARE],
        description='Type of insurance/payer (CMS-1500 Box 1)',
    )
    insurance_payer_name: str | None = Field(
        None,
        examples=['Medicare'],
        description='Name of the insurance carrier/payer',
        max_length=200,
    )
    insured_id_number: str | None = Field(
        None,
        examples=['1EG4-TE5-MK72'],
        description="Insured's ID number (CMS-1500 Box 1a)",
        max_length=50,
    )
    insured_name: str | None = Field(
        None,
        examples=['John Doe'],
        description=(
            "Insured's name (CMS-1500 Box 4), if different from the patient"
        ),
        max_length=200,
    )
    patient_relationship_to_insured: PatientRelationshipToInsured | None = (
        Field(
            None,
            examples=[PatientRelationshipToInsured.SELF],
            description="Patient's relationship to insured (CMS-1500 Box 6)",
        )
    )


class AmbulanceRequestResponseSchema(BaseModel):
    """Response schema for ambulance request."""

    id: Annotated[
        int,
        Field(
            description='Unique identifier of the ambulance request.',
            examples=[1],
        ),
    ]
    user_id: Annotated[
        int,
        Field(
            description='Unique identifier of user that created the request.',
            examples=[2],
        ),
    ]
    patient_first_name: Annotated[
        str,
        Field(
            min_length=3,
            max_length=15,
            pattern=r'^[a-zA-Z]+$',
            examples=['John'],
        ),
    ]
    patient_last_name: Annotated[
        str,
        Field(
            min_length=3,
            max_length=15,
            pattern=r'^[a-zA-Z]+$',
            examples=['Doe'],
        ),
    ]
    primary_diagnosis: Annotated[
        str | None,
        Field(
            ...,
            examples=['Chronic heart failure, mobility impaired'],
        ),
    ]
    status: RequestStatus
    pickup_address: Annotated[
        str,
        Field(
            min_length=5,
            max_length=500,
            examples=['123 Main St, Springfield, IL 62701'],
        ),
    ]
    destination_address: Annotated[
        str,
        Field(
            min_length=5,
            max_length=500,
            examples=[
                'Memorial Dialysis Center, '
                '456 Medical Dr, Springfield, IL 62702'
            ],
        ),
    ]
    transportation_type: TransportationType
    patient_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=50,
            description=(
                'Patient Medicare Beneficiary Identifier (MBI) or other ID'
            ),
            examples=['1EG4-TE5-MK72'],
        ),
    ]
    form_number: Annotated[
        str | None,
        Field(
            default=None,
            description='CMS form number (e.g., CMS-10344)',
            examples=['CMS-10344'],
        ),
    ]
    utn: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                'Unique Tracking Number issued by Novitas (CMS-1500 Box 23)'
            ),
            examples=['A1234B5678C9'],
        ),
    ]
    novitas_status: Annotated[
        NovitasStatus,
        Field(
            default=NovitasStatus.NOT_SUBMITTED,
            description='Status of the external Novitas prior authorization',
        ),
    ]
    novitas_submitted_at: Annotated[
        datetime | None,
        Field(
            default=None,
            description='When the Novitas PA package was faxed to Novitas',
        ),
    ]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RequestStatusHistoryResponseSchema(BaseModel):
    """Response schema for request status history."""

    id: Annotated[
        int,
        Field(
            description='Unique identifier of ambulance request status.',
            examples=[1],
        ),
    ]
    request_id: Annotated[
        int,
        Field(
            description='Unique identifier of ambulance request.', examples=[1]
        ),
    ]
    status: RequestStatus
    notes: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RequestDocumentSchema(BaseModel):
    """Schema for request document with download URL."""

    id: int
    filename: str
    file_size: int
    content_type: str
    download_url: str = Field(
        description='Presigned URL for downloading the document',
    )

    model_config = ConfigDict(from_attributes=True)


class RequestWithStatusHistorySchema(AmbulanceRequestResponseSchema):
    """Response schema for request with status history (provider view)."""

    pickup_address: Annotated[
        str,
        Field(
            min_length=5,
            max_length=500,
            examples=['123 Main St, Springfield, IL 62701'],
        ),
    ]
    destination_address: Annotated[
        str,
        Field(
            min_length=5,
            max_length=500,
            examples=[
                'Memorial Dialysis Center, '
                '456 Medical Dr, Springfield, IL 62702'
            ],
        ),
    ]
    transportation_type: TransportationType
    patient_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=50,
            description=(
                'Patient Medicare Beneficiary Identifier (MBI) or other ID'
            ),
            examples=['1EG4-TE5-MK72'],
        ),
    ]
    status_history: list[RequestStatusHistoryResponseSchema] = []
    documents: list[RequestDocumentSchema] = Field(
        default_factory=list,
        description='List of documents attached to the request',
    )
    completion_status: 'CompletionStatusSchema' = Field(
        description='Completion status of the request',
    )
    model_config = ConfigDict(from_attributes=True)


class AdminRequestWithStatusHistorySchema(BaseModel):
    """Response schema for request with status history."""

    id: int
    user_id: int
    transportation_type: TransportationType
    patient_first_name: str
    patient_last_name: str
    patient_date_of_birth: date
    patient_id: str
    date_of_transport: date
    time_of_transport: time
    pickup_address: str
    destination_address: str
    primary_diagnosis: str | None
    medical_justification: str | None
    status: RequestStatus
    form_number: str | None
    reviewer_id: int | None
    ambulatory_status: AmbulatoryStatus | None
    oxygen_required: bool
    ai_accuracy: float | None
    ordering_physician: str | None
    physician_phone: str | None
    ordering_physician_npi: str | None
    patient_sex: PatientSex | None
    insurance_type: InsuranceType | None
    insurance_payer_name: str | None
    insured_id_number: str | None
    insured_name: str | None
    patient_relationship_to_insured: PatientRelationshipToInsured | None
    denial_reason: DenialReason | None
    denial_notes: str | None
    utn: str | None
    novitas_status: NovitasStatus
    novitas_submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    status_history: list[RequestStatusHistoryResponseSchema] = []
    documents: list[RequestDocumentSchema] = Field(
        default_factory=list,
        description='List of documents attached to the request',
    )
    completion_status: 'CompletionStatusSchema' = Field(
        description='Completion status of the request',
    )

    @field_serializer('denial_reason')
    def serialize_denial_reason(
        self, value: DenialReason | None, _info: object
    ) -> str | None:
        """Serialize denial_reason to human-readable display name.

        Args:
            value: Denial reason enum value or None.
            _info: Serialization info (unused).

        Returns:
            Human-readable denial reason name or None.

        """
        if value is None:
            return None
        return get_denial_reason_display_name(value)

    model_config = ConfigDict(from_attributes=True)


class ApproveRequestSchema(BaseModel):
    """Schema for approving a request."""

    # No additional fields needed for approval


class DenyRequestSchema(BaseModel):
    """Schema for denying a request."""

    denial_reason: Annotated[
        DenialReason,
        Field(
            description='Reason for denial',
            examples=[DenialReason.DUPLICATE_REQUEST],
        ),
    ]
    denial_notes: Annotated[
        str | None,
        Field(
            default=None,
            max_length=256,
            description=(
                'Additional notes for denial '
                '(required if denial_reason is OTHER_REASON)'
            ),
            examples=['Custom denial reason explanation'],
        ),
    ]

    def model_post_init(self, __context: object) -> None:
        """Validate that denial_notes is provided for OTHER_REASON."""
        if (
            self.denial_reason == DenialReason.OTHER_REASON
            and not self.denial_notes
        ):
            raise ValueError(DENIAL_NOTES_REQUIRED_MSG)


class AdminUpdateRequestSchema(BaseModel):
    """Schema for admin to update request fields.

    All fields except ai_accuracy and status can be updated.
    """

    transportation_type: TransportationType | None = None
    patient_first_name: Annotated[
        str | None,
        Field(
            default=None,
            min_length=3,
            max_length=15,
            pattern=r'^[a-zA-Z]+$',
            examples=['John'],
        ),
    ]
    patient_last_name: Annotated[
        str | None,
        Field(
            default=None,
            min_length=3,
            max_length=15,
            pattern=r'^[a-zA-Z]+$',
            examples=['Doe'],
        ),
    ]
    patient_date_of_birth: date | None = None
    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            min_length=1,
            max_length=50,
            description=(
                'Patient Medicare Beneficiary Identifier (MBI) or other ID'
            ),
        ),
    ]
    date_of_transport: date | None = None
    time_of_transport: time | None = None
    pickup_address: Annotated[
        str | None,
        Field(
            default=None,
            min_length=5,
            max_length=500,
        ),
    ]
    destination_address: Annotated[
        str | None,
        Field(
            default=None,
            min_length=5,
            max_length=500,
        ),
    ]
    primary_diagnosis: str | None = None
    medical_justification: str | None = None
    form_number: str | None = None
    reviewer_id: int | None = None
    ambulatory_status: AmbulatoryStatus | None = None
    oxygen_required: bool | None = None
    ordering_physician: Annotated[
        str | None,
        Field(
            default=None,
            max_length=200,
        ),
    ]
    physician_phone: Annotated[
        str | None,
        Field(
            default=None,
            max_length=50,
        ),
    ]
    ordering_physician_npi: Annotated[
        str | None,
        Field(
            default=None,
            max_length=10,
        ),
    ]
    patient_sex: PatientSex | None = None
    insurance_type: InsuranceType | None = None
    insurance_payer_name: Annotated[
        str | None,
        Field(
            default=None,
            max_length=200,
        ),
    ]
    insured_id_number: Annotated[
        str | None,
        Field(
            default=None,
            max_length=50,
        ),
    ]
    insured_name: Annotated[
        str | None,
        Field(
            default=None,
            max_length=200,
        ),
    ]
    patient_relationship_to_insured: PatientRelationshipToInsured | None = (
        None
    )
    denial_reason: DenialReason | None = None
    denial_notes: Annotated[
        str | None,
        Field(
            default=None,
            max_length=256,
            description=(
                'Additional notes for denial '
                '(required if denial_reason is OTHER_REASON)'
            ),
        ),
    ]
    utn: Annotated[
        str | None,
        Field(
            default=None,
            max_length=50,
            description=(
                'Unique Tracking Number issued by Novitas, recorded '
                'manually once known (Novitas has no status API)'
            ),
            examples=['A1234B5678C9'],
        ),
    ]
    novitas_status: Annotated[
        NovitasStatus | None,
        Field(
            default=None,
            description=(
                'External Novitas prior authorization status, recorded '
                'manually once known'
            ),
        ),
    ]

    def model_post_init(self, __context: object) -> None:
        """Validate that denial_notes is provided for OTHER_REASON."""
        if (
            self.denial_reason == DenialReason.OTHER_REASON
            and not self.denial_notes
        ):
            raise ValueError(DENIAL_NOTES_REQUIRED_MSG)
