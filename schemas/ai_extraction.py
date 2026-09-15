"""Pydantic schemas for AI-extracted data from medical documents."""

from datetime import date, time

from pydantic import BaseModel, Field

from models.ambulance_request import (
    AmbulatoryStatus,
    InsuranceType,
    PatientRelationshipToInsured,
    PatientSex,
    TransportationType,
)


class ExtractedTransportationData(BaseModel):
    """Data extracted by AI from medical documents.

    This schema represents the structured data that AI extracts
    from uploaded medical documents. It matches the fields
    required for the transportation information form.

    All fields are optional as AI may not be able to extract
    all information from the provided documents.

    """

    transportation_type: TransportationType | None = Field(
        default=None,
        examples=[TransportationType.AMBULANCE],
        description=(
            'Type of medical transportation required. '
            'Options: ambulance, wheelchair, stretcher, bls, als, cct'
        ),
    )
    patient_first_name: str | None = Field(
        default=None,
        examples=['John'],
        description='Patient first name as it appears in the document',
    )
    patient_last_name: str | None = Field(
        default=None,
        examples=['Doe'],
        description='Patient last name as it appears in the document',
    )
    patient_date_of_birth: date | None = Field(
        default=None,
        examples=['1980-01-01'],
        description='Patient date of birth in YYYY-MM-DD format',
    )
    patient_id: str | None = Field(
        default=None,
        examples=['13874414D'],
        description=(
            'Patient Medicare Beneficiary Identifier (MBI) or other ID. '
            'Medicare MBI format: 1AA0A00AA00 (11 characters)'
        ),
    )
    date_of_transport: date | None = Field(
        default=None,
        examples=['2025-12-06'],
        description='Scheduled or requested date of transport',
    )
    time_of_transport: time | None = Field(
        default=None,
        examples=['13:45'],
        description='Scheduled or requested time of transport in HH:MM format',
    )
    pickup_address: str | None = Field(
        default=None,
        examples=['123 Main St, Springfield, IL 62701'],
        description='Full pickup address including street, city, state, ZIP',
    )
    destination_address: str | None = Field(
        default=None,
        examples=['123 Main St, Springfield, IL 62701'],
        description=(
            'Full destination address (hospital, clinic, etc.) '
            'including street, city, state, ZIP'
        ),
    )
    primary_diagnosis: str | None = Field(
        default=None,
        examples=['Chronic heart failure, mobility impaired'],
        description=(
            'Primary diagnosis or medical condition requiring transport. '
            'Include ICD-10 code if present in document'
        ),
    )
    medical_justification: str | None = Field(
        default=None,
        examples=[
            'Patient requires ambulance transport for dialysis treatment'
        ],
        description=(
            'Medical necessity justification explaining why ambulance '
            'transport is required (patient condition, mobility status, etc.)'
        ),
    )
    form_number: str | None = Field(
        default=None,
        examples=['CMS-10344'],
        description='CMS form number if present (e.g., CMS-10344)',
    )
    ambulatory_status: AmbulatoryStatus | None = Field(
        default=None,
        examples=[AmbulatoryStatus.AMBULATORY],
        description=(
            'Patient ambulatory status. '
            'Options: "ambulatory" - patient can walk, '
            '"non-ambulatory" - patient cannot walk or requires assistance'
        ),
    )
    oxygen_required: bool = Field(
        default=False,
        examples=[False],
        description='Whether oxygen is required for the patient during transport',  # noqa: E501
    )
    ordering_physician: str | None = Field(
        default=None,
        examples=['Dr. John Smith'],
        description='Name of the physician who ordered the transport',
    )
    physician_phone: str | None = Field(
        default=None,
        examples=['555-123-4567'],
        description='Phone number of the ordering physician',
    )
    ordering_physician_npi: str | None = Field(
        default=None,
        examples=['1234567893'],
        description=(
            'National Provider Identifier (NPI) of the ordering physician. '
            '10-digit number, often near the physician name/signature or '
            'labeled "NPI"'
        ),
    )
    patient_sex: PatientSex | None = Field(
        default=None,
        examples=[PatientSex.FEMALE],
        description='Patient sex as it appears in the document',
    )
    insurance_type: InsuranceType | None = Field(
        default=None,
        examples=[InsuranceType.MEDICARE],
        description=(
            'Type of insurance/payer. Options: medicare, medicaid, '
            'tricare, champva, group_health_plan, feca_black_lung, other'
        ),
    )
    insurance_payer_name: str | None = Field(
        default=None,
        examples=['Medicare', 'Blue Cross Blue Shield'],
        description='Name of the insurance carrier/payer',
    )
    insured_id_number: str | None = Field(
        default=None,
        examples=['1EG4-TE5-MK72'],
        description=(
            "Insured's ID/member number. Usually the same as the patient's "
            'Medicare Beneficiary Identifier when the patient is the '
            'insured'
        ),
    )
    insured_name: str | None = Field(
        default=None,
        examples=['John Doe'],
        description=(
            "Insured's name, only if different from the patient "
            '(e.g., patient is a dependent/spouse of the insured)'
        ),
    )
    patient_relationship_to_insured: PatientRelationshipToInsured | None = (
        Field(
            default=None,
            examples=[PatientRelationshipToInsured.SELF],
            description=(
                "Patient's relationship to the insured. Options: self, "
                'spouse, child, other. Defaults to "self" for most '
                'Medicare beneficiaries'
            ),
        )
    )
    confidence_score: float | None = Field(
        default=None,
        description="AI's self-assessment of extraction accuracy (0 to 100)",
    )


class AIExtractionResponse(BaseModel):
    """Response from AI extraction service.

    Contains extracted data and metadata about the extraction process.

    """

    extracted_data: ExtractedTransportationData = Field(
        description='Data extracted by AI from documents',
    )
    extraction_metadata: dict[str, str] | None = Field(
        None,
        description='Additional metadata about the extraction process',
    )
