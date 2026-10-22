from sqlalchemy.ext.asyncio import AsyncSession

from core import BaseService
from dao import OrganizationDAO
from exceptions import UserNotFoundByIdException
from models import Organization
from schemas import (
    OrganizationResponseSchema,
    UpdateOrganizationRequestSchema,
)


class OrganizationService(BaseService):
    """Service layer for managing organization-related operations."""

    def __init__(
        self,
        db_session: AsyncSession,
        *,
        organization_dao: OrganizationDAO | None = None,
    ):
        """Initialize OrganizationService.

        Args:
            db_session (AsyncSession): Database session.
            organization_dao (OrganizationDAO | None): OrganizationDAO instance.

        """
        super().__init__(db_session)
        self._organization_dao = organization_dao or OrganizationDAO(db_session)

    async def get_organization_by_user_id(
        self,
        user_id: int,
    ) -> Organization | None:
        """Get organization by user ID.

        Args:
            user_id: User ID.

        Returns:
            Organization | None: Organization instance or None if not found.

        """
        return await self._organization_dao.get_by_user_id(user_id)

    async def update_organization_by_user_id(
        self,
        user_id: int,
        organization_data: UpdateOrganizationRequestSchema,
    ) -> OrganizationResponseSchema:
        """Update organization by user ID.

        Args:
            user_id: User ID.
            organization_data: UpdateOrganizationRequestSchema fields to update.

        Returns:
            OrganizationResponseSchema: Updated organization information.

        Raises:
            UserNotFoundByIdException: If organization not found.

        """
        # Try to get existing organization
        organization = await self._organization_dao.get_by_user_id(user_id)

        # If organization doesn't exist, create it
        if not organization:
            organization = await self._organization_dao.create(
                user_id=user_id,
                provider_type=organization_data.provider_type,
                professional_id=organization_data.professional_id,
                medic_name=organization_data.medic_name,
                npi=organization_data.npi,
                address=organization_data.address,
                phone=organization_data.phone,
                fax=organization_data.fax,
            )
        else:
            # Update existing organization
            organization = await self._organization_dao.update_by_user_id(
                user_id,
                provider_type=organization_data.provider_type,
                professional_id=organization_data.professional_id,
                medic_name=organization_data.medic_name,
                npi=organization_data.npi,
                address=organization_data.address,
                phone=organization_data.phone,
                fax=organization_data.fax,
            )

        await self._session.commit()

        if not organization:
            raise UserNotFoundByIdException

        return OrganizationResponseSchema.model_validate(organization)
