"""Tests for RequestAccessLogDAO."""

import pytest

from dao import RequestAccessLogDAO
from models.request_access_log import PHIAccessAction


@pytest.fixture
def access_log_dao(db_session):
    """Create RequestAccessLogDAO instance."""
    return RequestAccessLogDAO(db_session)


class TestRequestAccessLogDAO:
    """Test suite for RequestAccessLogDAO."""

    @pytest.mark.asyncio
    async def test_create(
        self,
        access_log_dao,
        db_session,
        user_factory,
        ambulance_request_factory,
    ):
        """Test creating an access log entry."""
        user = await user_factory()
        request = await ambulance_request_factory(user_id=user.id)
        await db_session.commit()

        entry = await access_log_dao.create(
            request_id=request.id,
            user_id=user.id,
            action=PHIAccessAction.VIEW,
        )
        await db_session.commit()

        assert entry.id is not None
        assert entry.request_id == request.id
        assert entry.user_id == user.id
        assert entry.action == PHIAccessAction.VIEW

    @pytest.mark.asyncio
    async def test_get_by_request_id_orders_newest_first(
        self,
        access_log_dao,
        db_session,
        user_factory,
        ambulance_request_factory,
    ):
        """Test that entries are returned newest first."""
        user = await user_factory()
        request = await ambulance_request_factory(user_id=user.id)
        await db_session.commit()

        await access_log_dao.create(
            request_id=request.id,
            user_id=user.id,
            action=PHIAccessAction.VIEW,
        )
        await access_log_dao.create(
            request_id=request.id,
            user_id=user.id,
            action=PHIAccessAction.DOWNLOAD_CALL_SHEET,
        )
        await db_session.commit()

        entries = await access_log_dao.get_by_request_id(request.id)

        assert len(entries) == 2
        assert entries[0].action == PHIAccessAction.DOWNLOAD_CALL_SHEET
        assert entries[1].action == PHIAccessAction.VIEW

    @pytest.mark.asyncio
    async def test_get_by_request_id_scoped_to_request(
        self,
        access_log_dao,
        db_session,
        user_factory,
        ambulance_request_factory,
    ):
        """Test that entries for one request don't leak into another's."""
        user = await user_factory()
        request_a = await ambulance_request_factory(user_id=user.id)
        request_b = await ambulance_request_factory(user_id=user.id)
        await db_session.commit()

        await access_log_dao.create(
            request_id=request_a.id,
            user_id=user.id,
            action=PHIAccessAction.VIEW,
        )
        await db_session.commit()

        assert len(await access_log_dao.get_by_request_id(request_a.id)) == 1
        assert await access_log_dao.get_by_request_id(request_b.id) == []

    @pytest.mark.asyncio
    async def test_create_with_no_user(
        self,
        access_log_dao,
        db_session,
        user_factory,
        ambulance_request_factory,
    ):
        """Test that user_id may be None (unknown/system access)."""
        owner = await user_factory()
        request = await ambulance_request_factory(user_id=owner.id)
        await db_session.commit()

        entry = await access_log_dao.create(
            request_id=request.id,
            user_id=None,
            action=PHIAccessAction.VIEW,
        )
        await db_session.commit()

        assert entry.user_id is None
