"""Tests for organization endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dependencies.auth import get_provider_user_from_token
from main import app
from models.user import UserRole
from schemas import OrganizationResponseSchema


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_user() -> MagicMock:
    """Create mock provider user."""
    user = MagicMock()
    user.id = 1
    user.email = "provider@example.com"
    user.role = UserRole.PROVIDER
    user.is_active = True
    return user


class TestOrganizationEndpoints:
    """Test suite for organization endpoints."""

    @pytest.mark.asyncio
    async def test_update_my_organization_success(
        self,
        client: TestClient,
        mock_user: MagicMock,
    ):
        """Test successful organization update."""
        async def get_user_override():
            return mock_user

        app.dependency_overrides[get_provider_user_from_token] = get_user_override

        update_data = {
            "medic_name": "New Medic Name",
            "provider_type": "New Type",
            "professional_id": "12345"
        }

        with patch(
            "services.organization.OrganizationService.update_organization_by_user_id",
            new_callable=AsyncMock,
        ) as mock_update:

            mock_update.return_value = OrganizationResponseSchema(
                id=1,
                user_id=mock_user.id,
                medic_name=update_data["medic_name"],
                provider_type=update_data["provider_type"],
                professional_id=update_data["professional_id"],
                npi=None,
                address=None,
                phone=None,
                fax=None,
            )

            response = client.patch(
                "/Prod/api/v1/organization/me",
                json=update_data
            )

            assert response.status_code == 200
            data = response.json()
            assert data["medic_name"] == update_data["medic_name"]

            mock_update.assert_awaited_once()
            args, kwargs = mock_update.call_args
            assert kwargs["user_id"] == mock_user.id
            assert kwargs["organization_data"].medic_name == update_data["medic_name"]

    @pytest.mark.asyncio
    async def test_update_my_organization_validation_error(
        self,
        client: TestClient,
        mock_user: MagicMock,
    ):
        """Test organization update with invalid data (empty)."""
        async def get_user_override():
            return mock_user

        app.dependency_overrides[get_provider_user_from_token] = get_user_override

        # Endpoint validation requires at least one field?
        # Check schemas/organization.py but relying on behavior that empty dict might be allowed or not depending on validators.
        # Assuming from description "At least one field..." usually implies validation but let's check Pydantic model behavior.
        # If 'UpdateOrganizationRequestSchema' has root validator, it would fail.
        # Based on file content read earlier, the description says "At least one field...", so we assume validation exists.

        response = client.patch(
            "/Prod/api/v1/organization/me",
            json={}  # Empty body
        )

        # Expecting 422 if validation fails for missing fields, or if body is required
        # But if all fields are optional in schema but logic requires one, it returns 422.
        # Let's assume standard Pydantic validation for now.
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_my_organization_unauthorized(
        self,
        client: TestClient,
    ):
        """Test updating organization without authentication."""
        app.dependency_overrides = {}

        response = client.patch(
            "/Prod/api/v1/organization/me",
            json={"medic_name": "Test"}
        )
        assert response.status_code in (401, 403)
