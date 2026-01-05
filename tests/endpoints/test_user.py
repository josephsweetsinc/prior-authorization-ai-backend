"""Tests for user admin endpoints and self-profile updates."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from dependencies.auth import get_admin_user_from_token, get_current_user
from endpoints.user import update_me
from main import app
from models.user import UserRole
from schemas.user import UpdateUserRequestSchema, UserResponseShema


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
def auth_headers() -> dict[str, str]:
    """Create auth headers with mock token."""
    return {'Authorization': 'Bearer mock_token'}


class TestUserAdminEndpoints:
    """Test suite for user admin and profile endpoints."""

    @pytest.mark.asyncio
    async def test_update_me_success_for_provider(
        self,
        user_factory,
    ):
        """Provider user can successfully update only their own profile via /me."""
        user = await user_factory(role=UserRole.PROVIDER)
        update_data = UpdateUserRequestSchema(name='UpdatedName')

        # Prepare a mock service and verify that endpoint calls it correctly
        mock_service = AsyncMock()
        mock_service.update_user_by_id.return_value = UserResponseShema(
            id=user.id,
            name=update_data.name,
            surname=user.surname,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
        )

        result = await update_me(
            user_data=update_data,
            user=user,
            service=mock_service,
        )

        # Ensure endpoint delegates to service with current user id
        mock_service.update_user_by_id.assert_awaited_once_with(
            user_id=user.id,
            user_data=update_data,
        )
        # And returns the updated user data
        assert result.id == user.id
        assert result.name == update_data.name

    @pytest.mark.asyncio
    async def test_update_me_unauthorized_without_token(
        self,
        client: TestClient,
    ):
        """Updating /me without auth token should be unauthorized."""
        response = client.patch(
            '/Prod/api/v1/user/me',
            json={'name': 'UpdatedName'},
        )

        # FastAPI returns 401 for missing auth, but 403 is also acceptable
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_can_update_provider_by_id(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        db_session,
        user_factory,
    ):
        """Admin can update another provider user by id."""
        admin = await user_factory(
            email='admin@example.com',
            role=UserRole.ADMIN,
        )
        provider = await user_factory(
            email='provider@example.com',
            role=UserRole.PROVIDER,
        )
        await db_session.commit()

        async def get_admin_override():
            return admin

        app.dependency_overrides[get_admin_user_from_token] = get_admin_override

        update_data = {'name': 'ProviderUpdated'}

        with patch(
            'endpoints.user.UserService.update_user_by_id',
            new_callable=AsyncMock,
        ) as mock_update:
            mock_update.return_value = UserResponseShema(
                id=provider.id,
                name=update_data['name'],
                surname=provider.surname,
                email=provider.email,
                role=provider.role,
                is_active=provider.is_active,
            )

            response = client.patch(
                f'/Prod/api/v1/user/{provider.id}',
                json=update_data,
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data['id'] == provider.id
            assert data['name'] == update_data['name']

            mock_update.assert_awaited_once()
            args, kwargs = mock_update.call_args
            assert kwargs['user_id'] == provider.id
            assert isinstance(kwargs['user_data'], UpdateUserRequestSchema)
            assert kwargs['user_data'].name == update_data['name']

    @pytest.mark.asyncio
    async def test_non_admin_cannot_update_other_user_by_id(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        db_session,
        user_factory,
    ):
        """Non-admin user must not be able to update other users by id."""
        provider = await user_factory(
            email='provider@example.com',
            role=UserRole.PROVIDER,
        )
        other_user = await user_factory(
            email='other@example.com',
            role=UserRole.PROVIDER,
        )
        await db_session.commit()

        async def get_user_override():
            return provider

        app.dependency_overrides[get_current_user] = get_user_override

        update_data = {'name': 'ShouldNotUpdate'}

        with patch(
            'endpoints.user.UserService.update_user_by_id',
            new_callable=AsyncMock,
        ) as mock_update:
            response = client.patch(
                f'/Prod/api/v1/user/{other_user.id}',
                json=update_data,
                headers=auth_headers,
            )

            # Dependency get_admin_user_from_token should block this request
            assert response.status_code in (401, 403, 404)
            mock_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_all_users_success(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        db_session,
        user_factory,
    ):
        """Test getting all users endpoint with pagination."""
        admin = await user_factory(
            email='admin@example.com',
            role=UserRole.ADMIN,
        )
        await db_session.commit()

        # Override dependency
        async def get_admin_override():
            return admin

        app.dependency_overrides[get_admin_user_from_token] = get_admin_override

        with patch(
            'services.user.UserService.get_all_users',
            new_callable=AsyncMock,
        ) as mock_get:
            from datetime import datetime

            from schemas.user import UserListItemSchema

            mock_get.return_value = (
                [
                    UserListItemSchema(
                        id=1,
                        full_name='John Doe',
                        email='john@example.com',
                        role=UserRole.PROVIDER,
                        is_active=True,
                        last_login=datetime(2025, 1, 1, 12, 0, 0),
                    ),
                    UserListItemSchema(
                        id=2,
                        full_name='Jane Smith',
                        email='jane@example.com',
                        role=UserRole.PROVIDER,
                        is_active=True,
                        last_login=datetime(2025, 1, 2, 12, 0, 0),
                    ),
                ],
                2,  # total
                1,  # page
                1,  # total_pages
                2,  # showing
            )

            response = client.get(
                '/Prod/api/v1/user/',
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert 'items' in data
            assert 'page' in data
            assert 'total' in data
            assert 'showing' in data
            assert 'total_pages' in data
            assert len(data['items']) == 2
            assert data['items'][0]['email'] == 'john@example.com'
            assert data['items'][1]['email'] == 'jane@example.com'
            assert data['total'] == 2
            assert data['page'] == 1
            assert data['total_pages'] == 1
            assert data['showing'] == 2

    @pytest.mark.asyncio
    async def test_get_all_users_empty(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        db_session,
        user_factory,
    ):
        """Test getting users when there are none."""
        admin = await user_factory(
            email='admin@example.com',
            role=UserRole.ADMIN,
        )
        await db_session.commit()

        # Override dependency
        async def get_admin_override():
            return admin

        app.dependency_overrides[get_admin_user_from_token] = get_admin_override

        with patch(
            'services.user.UserService.get_all_users',
            new_callable=AsyncMock,
            return_value=([], 0, 1, 1, 0),  # items, total, page, total_pages, showing
        ):
            response = client.get(
                '/Prod/api/v1/user/',
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert 'items' in data
            assert len(data['items']) == 0
            assert data['total'] == 0
            assert data['page'] == 1
            assert data['total_pages'] == 1
            assert data['showing'] == 0

    @pytest.mark.asyncio
    async def test_get_all_users_with_pagination(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        db_session,
        user_factory,
    ):
        """Test getting users with pagination parameters."""
        admin = await user_factory(
            email='admin@example.com',
            role=UserRole.ADMIN,
        )
        await db_session.commit()

        # Override dependency
        async def get_admin_override():
            return admin

        app.dependency_overrides[get_admin_user_from_token] = get_admin_override

        with patch(
            'services.user.UserService.get_all_users',
            new_callable=AsyncMock,
        ) as mock_get:
            from datetime import datetime

            from schemas.user import UserListItemSchema

            mock_get.return_value = (
                [
                    UserListItemSchema(
                        id=1,
                        full_name='Bob Johnson',
                        email='bob@example.com',
                        role=UserRole.PROVIDER,
                        is_active=True,
                        last_login=datetime(2025, 1, 3, 12, 0, 0),
                    ),
                ],
                5,  # total
                2,  # page
                3,  # total_pages
                1,  # showing
            )

            response = client.get(
                '/Prod/api/v1/user/?page=2',
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data['items']) == 1
            assert data['total'] == 5
            assert data['page'] == 2
            assert data['total_pages'] == 3
            assert data['showing'] == 1
            # Verify service was called with correct parameters
            mock_get.assert_called_once_with(
                page=2, limit=8, search=None
            )

    @pytest.mark.asyncio
    async def test_get_all_users_with_search(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        db_session,
        user_factory,
    ):
        """Test getting users with search parameter."""
        admin = await user_factory(
            email='admin@example.com',
            role=UserRole.ADMIN,
        )
        await db_session.commit()

        # Override dependency
        async def get_admin_override():
            return admin

        app.dependency_overrides[get_admin_user_from_token] = get_admin_override

        with patch(
            'services.user.UserService.get_all_users',
            new_callable=AsyncMock,
        ) as mock_get:
            from datetime import datetime

            from schemas.user import UserListItemSchema

            mock_get.return_value = (
                [
                    UserListItemSchema(
                        id=1,
                        full_name='John Doe',
                        email='john@example.com',
                        role=UserRole.PROVIDER,
                        is_active=True,
                        last_login=datetime(2025, 1, 1, 12, 0, 0),
                    ),
                ],
                1,  # total
                1,  # page
                1,  # total_pages
                1,  # showing
            )

            response = client.get(
                '/Prod/api/v1/user/?search=John',
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data['items']) == 1
            assert data['items'][0]['full_name'] == 'John Doe'
            # Verify service was called with search parameter
            mock_get.assert_called_once_with(
                page=1, limit=8, search='John'
            )

    @pytest.mark.asyncio
    async def test_get_all_users_non_admin_forbidden(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        db_session,
        user_factory,
    ):
        """Test that non-admin users cannot access get all users endpoint."""
        provider = await user_factory(
            email='provider@example.com',
            role=UserRole.PROVIDER,
        )
        await db_session.commit()

        # Override dependency with provider (not admin)
        async def get_user_override():
            return provider

        app.dependency_overrides[get_current_user] = get_user_override

        # Don't override get_admin_user_from_token - should fail
        # Since dependencies=[Depends(get_admin_user_from_token)] is used,
        # FastAPI will return 403 if dependency fails, or 404 if endpoint not found
        response = client.get(
            '/Prod/api/v1/user/',
            headers=auth_headers,
        )

        # Should be forbidden since get_admin_user_from_token is required
        # FastAPI may return 404 if dependency is not satisfied
        assert response.status_code in (401, 403, 404)
