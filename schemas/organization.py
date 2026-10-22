from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UpdateOrganizationRequestSchema(BaseModel):
    """Organization update request schema."""

    provider_type: Annotated[
        str | None,
        Field(
            None,
            max_length=512,
            examples=['Hospital', 'Clinic'],
            description='Type of provider',
        ),
    ]
    professional_id: Annotated[
        str | None,
        Field(
            None,
            max_length=128,
            examples=['PROF123456'],
            description='Professional ID',
        ),
    ]
    medic_name: Annotated[
        str | None,
        Field(
            None,
            max_length=128,
            examples=['Dr. John Smith'],
            description='Medic name',
        ),
    ]
    npi: Annotated[
        str | None,
        Field(
            None,
            max_length=10,
            examples=['1234567893'],
            description=(
                "Organization's own NPI, used as the rendering provider "
                'on Novitas Form 13614'
            ),
        ),
    ]
    address: Annotated[
        str | None,
        Field(
            None,
            max_length=500,
            examples=['123 Main St, Springfield, IL 62701'],
            description=(
                "Organization's billing name and address, as printed on "
                'Novitas Form 13614'
            ),
        ),
    ]
    phone: Annotated[
        str | None,
        Field(
            None,
            max_length=50,
            examples=['555-123-4567'],
            description='Contact phone number for Novitas Form 13614',
        ),
    ]
    fax: Annotated[
        str | None,
        Field(
            None,
            max_length=50,
            examples=['555-123-4568'],
            description='Contact fax number for Novitas Form 13614',
        ),
    ]

    @model_validator(mode='after')
    def validate_at_least_one_field(self) -> 'UpdateOrganizationRequestSchema':
        """Validate that at least one field is provided for update."""
        if all(
            value is None
            for value in (
                self.provider_type,
                self.professional_id,
                self.medic_name,
                self.npi,
                self.address,
                self.phone,
                self.fax,
            )
        ):
            raise ValueError(  # noqa: TRY003
                'At least one field must be provided'
            )
        return self


class OrganizationResponseSchema(BaseModel):
    """Organization response schema."""

    id: int
    user_id: int
    provider_type: str | None
    professional_id: str | None
    medic_name: str | None
    npi: str | None
    address: str | None
    phone: str | None
    fax: str | None

    model_config = ConfigDict(from_attributes=True)
