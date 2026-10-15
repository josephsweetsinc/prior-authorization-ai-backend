from sqlalchemy import select, update

from core.dao import BaseDAO
from models import Organization


class OrganizationDAO(BaseDAO):
    """DAO for Organization model."""

    async def get_by_user_id(self, user_id: int) -> Organization | None:
        """Get organization by user ID.

        Args:
            user_id: User ID.

        Returns:
            Organization | None: Organization instance or None if not found.

        """
        stmt = select(Organization).where(
            Organization.user_id == user_id,
            Organization.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        provider_type: str | None = None,
        professional_id: str | None = None,
        medic_name: str | None = None,
        npi: str | None = None,
        address: str | None = None,
        phone: str | None = None,
        fax: str | None = None,
    ) -> Organization:
        """Create a new organization.

        Args:
            user_id: User ID.
            provider_type: Provider type (optional).
            professional_id: Professional ID (optional).
            medic_name: Medic name (optional).
            npi: Organization's own NPI (optional).
            address: Organization's billing name and address (optional).
            phone: Contact phone number (optional).
            fax: Contact fax number (optional).

        Returns:
            Organization: Organization instance.

        """
        organization = Organization(
            user_id=user_id,
            provider_type=provider_type,
            professional_id=professional_id,
            medic_name=medic_name,
            npi=npi,
            address=address,
            phone=phone,
            fax=fax,
        )
        self._session.add(organization)
        await self._session.flush()
        await self._session.refresh(organization)
        return organization

    async def update_by_user_id(
        self,
        user_id: int,
        *,
        provider_type: str | None = None,
        professional_id: str | None = None,
        medic_name: str | None = None,
        npi: str | None = None,
        address: str | None = None,
        phone: str | None = None,
        fax: str | None = None,
    ) -> Organization | None:
        """Update organization by user ID.

        Args:
            user_id: User ID.
            provider_type: New provider type (optional).
            professional_id: New professional ID (optional).
            medic_name: New medic name (optional).
            npi: New organization NPI (optional).
            address: New billing name and address (optional).
            phone: New contact phone number (optional).
            fax: New contact fax number (optional).

        Returns:
            Organization | None: Updated organization instance or None.

        """
        update_values = {}
        if provider_type is not None:
            update_values['provider_type'] = provider_type
        if professional_id is not None:
            update_values['professional_id'] = professional_id
        if medic_name is not None:
            update_values['medic_name'] = medic_name
        if npi is not None:
            update_values['npi'] = npi
        if address is not None:
            update_values['address'] = address
        if phone is not None:
            update_values['phone'] = phone
        if fax is not None:
            update_values['fax'] = fax

        if not update_values:
            return await self.get_by_user_id(user_id)

        stmt = (
            update(Organization)
            .where(
                Organization.user_id == user_id,
                Organization.is_active.is_(True),
            )
            .values(**update_values)
            .returning(Organization)
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
