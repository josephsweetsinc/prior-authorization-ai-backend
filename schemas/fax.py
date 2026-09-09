"""Pydantic schemas for fax intake and management."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from models.incoming_fax import FaxDirection, FaxStatus


class IncomingFaxResponseSchema(BaseModel):
    """Response schema for a single fax."""

    id: Annotated[
        int,
        Field(description='Unique identifier of the fax.', examples=[1]),
    ]
    direction: FaxDirection
    status: FaxStatus
    provider_message_id: Annotated[
        str,
        Field(description="Fax provider's message ID.", examples=['12345']),
    ]
    from_number: Annotated[
        str | None,
        Field(description='Sender fax number.', examples=['+15551234567']),
    ] = None
    to_number: Annotated[
        str | None,
        Field(
            description='Recipient fax number.', examples=['+15557654321']
        ),
    ] = None
    page_count: Annotated[
        int | None,
        Field(description='Number of pages in the fax.', examples=[3]),
    ] = None
    content_type: Annotated[
        str | None,
        Field(
            description='MIME type of the stored document.',
            examples=['application/pdf'],
        ),
    ] = None
    file_size: Annotated[
        int | None,
        Field(
            description='Size of the stored document in bytes.',
            examples=[254920],
        ),
    ] = None
    request_id: Annotated[
        int | None,
        Field(
            description='Linked ambulance request ID, once matched.',
            examples=[42],
        ),
    ] = None
    download_url: Annotated[
        str | None,
        Field(
            default=None,
            description='Presigned URL for downloading the fax document.',
        ),
    ] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncomingFaxListResponseSchema(BaseModel):
    """Response schema for paginated list of faxes."""

    items: list[IncomingFaxResponseSchema]
    page: int = Field(description='Current page number', examples=[1])
    total: int = Field(description='Total number of faxes', examples=[42])
    showing: int = Field(
        description='Number of items shown on current page', examples=[20]
    )
    total_pages: int = Field(
        description='Total number of pages', examples=[3]
    )


class LinkFaxToRequestSchema(BaseModel):
    """Schema for manually linking a fax to an ambulance request."""

    request_id: Annotated[
        int,
        Field(
            description='ID of the ambulance request to link this fax to.',
            examples=[42],
        ),
    ]
