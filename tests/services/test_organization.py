"""Tests for OrganizationService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from models import Organization
from schemas import UpdateOrganizationRequestSchema
from services.organization import OrganizationService


@pytest.fixture
def mock_session():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_organization_dao():
    """Mock OrganizationDAO."""
    return AsyncMock()


@pytest.fixture
def organization_service(
    mock_session,
    mock_organization_dao,
):
    """Create OrganizationService instance with mocks."""
    return OrganizationService(
        db_session=mock_session,
        organization_dao=mock_organization_dao,
    )


class TestOrganizationService:
    """Test suite for OrganizationService."""

    @pytest.mark.asyncio
    async def test_update_organization_exists(
        self,
        organization_service,
        mock_organization_dao,
        mock_session,
    ):
        """Test updating existing organization."""
        user_id = 1
        update_data = UpdateOrganizationRequestSchema(
            medic_name="Doctor House",
            provider_type="Clinic",
            professional_id="ID123"
        )

        existing_org = MagicMock(spec=Organization)
        existing_org.id = 10
        mock_organization_dao.get_by_user_id.return_value = existing_org

        updated_org = MagicMock(spec=Organization)
        updated_org.id = 10
        updated_org.medic_name = update_data.medic_name
        updated_org.provider_type = update_data.provider_type
        updated_org.professional_id = update_data.professional_id
        updated_org.user_id = user_id
        updated_org.npi = None
        updated_org.address = None
        updated_org.phone = None
        updated_org.fax = None

        mock_organization_dao.update_by_user_id.return_value = updated_org

        result = await organization_service.update_organization_by_user_id(
            user_id, update_data
        )

        assert result.medic_name == "Doctor House"
        mock_organization_dao.update_by_user_id.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_organization_create_new(
        self,
        organization_service,
        mock_organization_dao,
        mock_session,
    ):
        """Test creating new organization if not exists during update."""
        user_id = 1
        update_data = UpdateOrganizationRequestSchema(
            medic_name="New Doctor",
            provider_type="Hospital",
            professional_id="ID456"
        )

        mock_organization_dao.get_by_user_id.return_value = None

        new_org = MagicMock(spec=Organization)
        new_org.id = 20
        new_org.medic_name = update_data.medic_name
        new_org.provider_type = update_data.provider_type
        new_org.professional_id = update_data.professional_id
        new_org.user_id = user_id
        new_org.npi = None
        new_org.address = None
        new_org.phone = None
        new_org.fax = None

        mock_organization_dao.create.return_value = new_org

        result = await organization_service.update_organization_by_user_id(
            user_id, update_data
        )

        assert result.medic_name == "New Doctor"
        mock_organization_dao.create.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
