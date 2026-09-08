"""Tests for fax endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from config.settings import Settings
from dependencies.auth import get_admin_user_from_token
from main import app
from models.incoming_fax import FaxDirection, FaxStatus
from models.user import UserRole
from schemas.fax import (
    IncomingFaxListResponseSchema,
    IncomingFaxResponseSchema,
)


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_dependencies():
    """Reset dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_admin() -> MagicMock:
    """Create mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = 'admin@example.com'
    user.role = UserRole.ADMIN
    user.is_active = True
    return user


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Create auth headers with mock token."""
    return {'Authorization': 'Bearer mock_token'}


@pytest.fixture
def sample_fax_schema() -> IncomingFaxResponseSchema:
    """Create a sample fax response schema."""
    return IncomingFaxResponseSchema(
        id=1,
        direction=FaxDirection.INBOUND,
        status=FaxStatus.RECEIVED,
        provider_message_id='rc-1',
        from_number='+15551234567',
        to_number='+15557654321',
        page_count=2,
        content_type='application/pdf',
        file_size=1024,
        request_id=None,
        download_url='https://s3.example.com/presigned-url',
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class TestFaxWebhookEndpoint:
    """Test suite for the RingCentral fax webhook endpoint."""

    def test_validation_handshake_echoes_token(self, client: TestClient):
        """Test that the validation-token handshake is echoed back."""
        response = client.post(
            '/Prod/api/v1/fax/webhook',
            headers={'Validation-Token': 'handshake-value'},
        )
        assert response.status_code == 200
        assert response.headers['Validation-Token'] == 'handshake-value'

    def test_webhook_rejects_missing_secret(self, client: TestClient):
        """Test that a request without the shared secret is rejected."""
        settings = Settings.load()
        settings.ringcentral_settings.WEBHOOK_SECRET = 'configured-secret'

        response = client.post('/Prod/api/v1/fax/webhook', json={})

        assert response.status_code == 401

    def test_webhook_rejects_wrong_secret(self, client: TestClient):
        """Test that a request with the wrong shared secret is rejected."""
        settings = Settings.load()
        settings.ringcentral_settings.WEBHOOK_SECRET = 'configured-secret'

        response = client.post(
            '/Prod/api/v1/fax/webhook?token=wrong-secret', json={}
        )

        assert response.status_code == 401

    def test_webhook_accepts_correct_secret(self, client: TestClient):
        """Test that a request with the correct shared secret is accepted."""
        settings = Settings.load()
        settings.ringcentral_settings.WEBHOOK_SECRET = 'configured-secret'

        with patch(
            'services.fax.fax_service.FaxService.process_webhook_payload',
            new_callable=AsyncMock,
        ) as mock_process:
            mock_process.return_value = []
            response = client.post(
                '/Prod/api/v1/fax/webhook?token=configured-secret',
                json={'body': {'changes': []}},
            )

        assert response.status_code == 200
        mock_process.assert_awaited_once()


class TestFaxAdminEndpoints:
    """Test suite for admin-facing fax endpoints."""

    @pytest.mark.asyncio
    async def test_list_faxes_requires_admin(
        self,
        client: TestClient,
        mock_admin,
        auth_headers,
        sample_fax_schema,
    ):
        """Test that the fax list endpoint returns paginated faxes."""

        async def get_admin_override():
            return mock_admin

        app.dependency_overrides[get_admin_user_from_token] = (
            get_admin_override
        )

        with patch(
            'services.fax.fax_service.FaxService.list_faxes',
            new_callable=AsyncMock,
        ) as mock_list:
            mock_list.return_value = IncomingFaxListResponseSchema(
                items=[sample_fax_schema],
                page=1,
                total=1,
                showing=1,
                total_pages=1,
            )
            response = client.get(
                '/Prod/api/v1/fax/', headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 1
        assert data['items'][0]['provider_message_id'] == 'rc-1'

    @pytest.mark.asyncio
    async def test_get_fax_success(
        self,
        client: TestClient,
        mock_admin,
        auth_headers,
        sample_fax_schema,
    ):
        """Test getting a single fax's details."""

        async def get_admin_override():
            return mock_admin

        app.dependency_overrides[get_admin_user_from_token] = (
            get_admin_override
        )

        with patch(
            'services.fax.fax_service.FaxService.get_fax',
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = sample_fax_schema
            response = client.get(
                '/Prod/api/v1/fax/1', headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()['id'] == 1

    @pytest.mark.asyncio
    async def test_link_fax_to_request_success(
        self,
        client: TestClient,
        mock_admin,
        auth_headers,
        sample_fax_schema,
    ):
        """Test manually linking a fax to a request."""

        async def get_admin_override():
            return mock_admin

        app.dependency_overrides[get_admin_user_from_token] = (
            get_admin_override
        )

        with patch(
            'services.fax.fax_service.FaxService.link_fax_to_request',
            new_callable=AsyncMock,
        ) as mock_link:
            mock_link.return_value = sample_fax_schema
            response = client.post(
                '/Prod/api/v1/fax/1/link',
                json={'request_id': 42},
                headers=auth_headers,
            )

        assert response.status_code == 200
        mock_link.assert_awaited_once_with(
            fax_id=1, request_id=42, matched_by_user_id=mock_admin.id
        )
