"""Tests for UserService."""

from datetime import UTC, datetime

import pytest

from models.user import UserRole
from services import UserService


class TestUserService:
    """Test suite for UserService."""

    @pytest.mark.asyncio
    async def test_get_all_users(
        self,
        service: UserService,
        user_factory,
        db_session,
    ):
        """Test getting all users with pagination."""
        user1 = await user_factory(
            email='user1@example.com',
            name='John',
            surname='Doe',
        )
        user2 = await user_factory(
            email='user2@example.com',
            name='Jane',
            surname='Smith',
        )
        await db_session.commit()

        items, total, page, total_pages, showing = await service.get_all_users(
            page=1, limit=8
        )

        assert len(items) == 2
        assert total == 2
        assert page == 1
        assert total_pages == 1
        assert showing == 2

        # Verify items structure
        emails = {item.email for item in items}
        assert emails == {user1.email, user2.email}
        assert all(item.full_name for item in items)
        assert all(item.role in [UserRole.ADMIN, UserRole.PROVIDER] for item in items)

    @pytest.mark.asyncio
    async def test_get_all_users_with_pagination(
        self,
        service: UserService,
        user_factory,
        db_session,
    ):
        """Test pagination for getting users."""
        # Create 5 users
        for i in range(5):
            await user_factory(
                email=f'user{i}@example.com',
                name=f'User{i}',
                surname='Test',
            )
            await db_session.commit()

        # Get first page
        items, total, page, total_pages, showing = await service.get_all_users(
            page=1, limit=2
        )

        assert len(items) == 2
        assert total == 5
        assert page == 1
        assert total_pages == 3
        assert showing == 2
        first_page_emails = {item.email for item in items}

        # Get next page
        items2, total2, page2, total_pages2, showing2 = await service.get_all_users(
            page=2, limit=2
        )

        assert len(items2) == 2
        assert total2 == 5
        assert page2 == 2
        assert total_pages2 == 3
        assert showing2 == 2
        second_page_emails = {item.email for item in items2}

        # Should not overlap
        assert first_page_emails.isdisjoint(second_page_emails), (
            f'Pages overlap: first_page={first_page_emails}, second_page={second_page_emails}'
        )

    @pytest.mark.asyncio
    async def test_get_all_users_with_search(
        self,
        service: UserService,
        user_factory,
        db_session,
    ):
        """Test getting users with search filter."""
        user1 = await user_factory(
            email='john.doe@example.com',
            name='John',
            surname='Doe',
        )
        user2 = await user_factory(
            email='jane.smith@example.com',
            name='Jane',
            surname='Smith',
        )
        user3 = await user_factory(
            email='bob.johnson@example.com',
            name='Bob',
            surname='Johnson',
        )
        await db_session.commit()

        # Search by name - 'John' matches name='John' and surname='Johnson'
        items, total, page, total_pages, showing = await service.get_all_users(
            page=1, limit=8, search='John'
        )

        assert len(items) == 2  # Matches both 'John' (name) and 'Johnson' (surname)
        assert total == 2
        emails = {item.email for item in items}
        assert user1.email in emails
        assert user3.email in emails

        # Search by exact email to get only one result
        items, total, page, total_pages, showing = await service.get_all_users(
            page=1, limit=8, search='john.doe@example.com'
        )

        assert len(items) == 1
        assert total == 1
        assert items[0].email == user1.email

        # Search by surname
        items, total, page, total_pages, showing = await service.get_all_users(
            page=1, limit=8, search='Smith'
        )

        assert len(items) == 1
        assert total == 1
        assert items[0].email == user2.email

        # Search by email
        items, total, page, total_pages, showing = await service.get_all_users(
            page=1, limit=8, search='jane.smith'
        )

        assert len(items) == 1
        assert total == 1
        assert items[0].email == user2.email

    @pytest.mark.asyncio
    async def test_get_all_users_empty(
        self,
        service: UserService,
    ):
        """Test getting users when there are none."""
        items, total, page, total_pages, showing = await service.get_all_users(
            page=1, limit=8
        )

        assert len(items) == 0
        assert total == 0
        assert page == 1
        assert total_pages == 1
        assert showing == 0

    @pytest.mark.asyncio
    async def test_get_all_users_includes_last_login(
        self,
        service: UserService,
        user_factory,
        db_session,
    ):
        """Test that get_all_users includes last_login field."""
        user = await user_factory(email='test@example.com')
        await db_session.commit()

        # Update last_login
        from dao import UserDAO

        user_dao = UserDAO(db_session)
        await user_dao.update_last_login(user.id)
        await db_session.commit()

        items, total, page, total_pages, showing = await service.get_all_users(
            page=1, limit=8
        )

        assert len(items) == 1
        assert items[0].last_login is not None
        assert isinstance(items[0].last_login, datetime)

    @pytest.mark.asyncio
    async def test_get_all_users_last_login_none(
        self,
        service: UserService,
        user_factory,
        db_session,
    ):
        """Test that get_all_users handles None last_login."""
        user = await user_factory(email='test@example.com')
        await db_session.commit()

        items, total, page, total_pages, showing = await service.get_all_users(
            page=1, limit=8
        )

        assert len(items) == 1
        # last_login can be None if user never logged in
        assert items[0].last_login is None or isinstance(items[0].last_login, datetime)

    @pytest.mark.asyncio
    async def test_get_all_users_full_name_format(
        self,
        service: UserService,
        user_factory,
        db_session,
    ):
        """Test that full_name is correctly formatted."""
        user = await user_factory(
            email='test@example.com',
            name='John',
            surname='Doe',
        )
        await db_session.commit()

        items, total, page, total_pages, showing = await service.get_all_users(
            page=1, limit=8
        )

        assert len(items) == 1
        assert items[0].full_name == 'John Doe'

    @pytest.mark.asyncio
    async def test_deactivate_unapproved_providers(
        self,
        service: UserService,
        user_factory,
        db_session,
    ):
        """Test deactivating unapproved providers older than 30 days."""
        from datetime import timedelta
        from sqlalchemy import update
        from models import User

        user1 = await user_factory(
            email='recent_provider@example.com',
            role=UserRole.PROVIDER,
        )
        
        user2 = await user_factory(
            email='old_provider@example.com',
            role=UserRole.PROVIDER,
        )
        
        user3 = await user_factory(
            email='inactive_old_provider@example.com',
            role=UserRole.PROVIDER,
        )
        
        user4 = await user_factory(
            email='old_admin@example.com',
            role=UserRole.ADMIN,
        )
        
        await db_session.commit()
        
        old_date = datetime.now(UTC) - timedelta(days=31)
        
        await db_session.execute(
            update(User)
            .where(User.id == user2.id)
            .values(last_approved_at=old_date)
        )
        
        await db_session.execute(
            update(User)
            .where(User.id == user3.id)
            .values(last_approved_at=old_date, is_active=False)
        )
        
        await db_session.execute(
            update(User)
            .where(User.id == user4.id)
            .values(last_approved_at=old_date)
        )
        
        await db_session.commit()
        
        deactivated_count = await service.deactivate_unapproved_providers()
        
        assert deactivated_count == 1
        
        await db_session.refresh(user1)
        await db_session.refresh(user2)
        await db_session.refresh(user3)
        await db_session.refresh(user4)
        
        assert user1.is_active is True
        assert user2.is_active is False
        assert user2.deleted_at is not None
        assert user3.is_active is False
        assert user4.is_active is True
