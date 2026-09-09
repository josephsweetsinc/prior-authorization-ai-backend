"""Tests for AmbulanceRequestDAO, RequestStatusHistoryDAO, RequestFileDAO."""

from datetime import UTC, date, datetime, time, timedelta

import pytest

from dao import (
    AmbulanceRequestDAO,
    RequestFileDAO,
    RequestStatusHistoryDAO,
)
from models.ambulance_request import RequestStatus, TransportationType


class TestAmbulanceRequestDAO:
    """Test suite for AmbulanceRequestDAO."""

    @pytest.mark.asyncio
    async def test_create(
        self,
        db_session,
        user_factory,
    ):
        """Test creating an ambulance request."""
        user = await user_factory()
        await db_session.commit()

        dao = AmbulanceRequestDAO(db_session)
        request = await dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St, Springfield, IL 62701',
            destination_address='Memorial Dialysis Center, 456 Medical Dr',
            primary_diagnosis='Chronic heart failure',
            medical_justification='Patient requires transport',
            form_number='CMS-10344',
            status=RequestStatus.DRAFT,
        )
        await db_session.commit()

        assert request.id is not None
        assert request.user_id == user.id
        assert request.transportation_type == TransportationType.AMBULANCE
        assert request.patient_first_name == 'John'
        assert request.patient_last_name == 'Doe'
        assert request.patient_id == 'DA123456789HY'
        assert request.status == RequestStatus.DRAFT
        assert request.form_number == 'CMS-10344'

    @pytest.mark.asyncio
    async def test_get_by_id(
        self,
        db_session,
        user_factory,
    ):
        """Test getting request by ID."""
        user = await user_factory()
        await db_session.commit()

        dao = AmbulanceRequestDAO(db_session)
        created = await dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
        )
        await db_session.commit()

        found = await dao.get_by_id(created.id)

        assert found is not None
        assert found.id == created.id
        assert found.patient_first_name == 'John'
        # Should include relationships
        assert hasattr(found, 'files')
        assert hasattr(found, 'status_history')

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(
        self,
        db_session,
    ):
        """Test getting non-existent request returns None."""
        dao = AmbulanceRequestDAO(db_session)
        found = await dao.get_by_id(99999)
        assert found is None

    @pytest.mark.asyncio
    async def test_get_by_id_for_update(
        self,
        db_session,
        user_factory,
    ):
        """Test getting request by ID with a row lock."""
        user = await user_factory()
        await db_session.commit()

        dao = AmbulanceRequestDAO(db_session)
        created = await dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
        )
        await db_session.commit()

        found = await dao.get_by_id_for_update(created.id)

        assert found is not None
        assert found.id == created.id
        assert found.patient_first_name == 'John'

    @pytest.mark.asyncio
    async def test_get_by_id_for_update_not_found(
        self,
        db_session,
    ):
        """Test getting a non-existent request with a row lock returns
        None.
        """  # noqa: D205
        dao = AmbulanceRequestDAO(db_session)
        found = await dao.get_by_id_for_update(99999)
        assert found is None

    @pytest.mark.asyncio
    async def test_get_by_user_id(
        self,
        db_session,
        user_factory,
    ):
        """Test getting all requests for a user."""
        user1 = await user_factory(email='user1@example.com')
        user2 = await user_factory(email='user2@example.com')
        await db_session.commit()

        dao = AmbulanceRequestDAO(db_session)

        # Create requests for user1
        request1 = await dao.create(
            user_id=user1.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
        )
        request2 = await dao.create(
            user_id=user1.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='Jane',
            patient_last_name='Smith',
            patient_date_of_birth=date(1975, 5, 15),
            patient_id='DA987654321AB',
            date_of_transport=date(2025, 12, 7),
            time_of_transport=time(14, 0),
            pickup_address='789 Oak Ave',
            destination_address='321 Pine St',
        )
        # Create request for user2
        await dao.create(
            user_id=user2.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='Bob',
            patient_last_name='Johnson',
            patient_date_of_birth=date(1990, 3, 20),
            patient_id='DA111222333CD',
            date_of_transport=date(2025, 12, 8),
            time_of_transport=time(15, 0),
            pickup_address='555 Elm St',
            destination_address='777 Maple Dr',
        )
        await db_session.commit()

        user1_requests = await dao.get_by_user_id(user_id=user1.id)

        assert len(user1_requests) == 2
        assert all(req.user_id == user1.id for req in user1_requests)
        # Should be ordered by created_at desc
        request_ids = {req.id for req in user1_requests}
        assert request_ids == {request1.id, request2.id}
        # Verify ordering (newer first)
        assert user1_requests[0].created_at >= user1_requests[1].created_at
        # Verify status_history is always loaded
        assert all(hasattr(req, 'status_history') for req in user1_requests)

    @pytest.mark.asyncio
    async def test_get_by_user_id_with_pagination(
        self,
        db_session,
        user_factory,
    ):
        """Test getting requests for a user with pagination."""
        user = await user_factory()
        await db_session.commit()

        dao = AmbulanceRequestDAO(db_session)

        # Create 5 requests
        request_ids = []
        for i in range(5):
            request = await dao.create(
                user_id=user.id,
                transportation_type=TransportationType.AMBULANCE,
                patient_first_name=f'Patient{i}',
                patient_last_name='Doe',
                patient_date_of_birth=date(1980, 1, 1),
                patient_id=f'DA12345678{i}HY',
                date_of_transport=date(2025, 12, 6),
                time_of_transport=time(13, 40),
                pickup_address='123 Main St',
                destination_address='456 Medical Dr',
            )
            request_ids.append(request.id)
            await db_session.commit()

        # Get first page (offset=0, limit=2)
        first_page = await dao.get_by_user_id(
            user_id=user.id, offset=0, limit=2
        )
        assert len(first_page) == 2
        # Verify descending order (newer first, then by ID desc)
        # Since requests are created sequentially, newer ones have higher IDs
        assert first_page[0].id > first_page[1].id

        # Get next page (offset=2, limit=2)
        second_page = await dao.get_by_user_id(
            user_id=user.id, offset=2, limit=2
        )
        # Should get next 2 items
        assert len(second_page) == 2
        # Should not overlap with first page
        first_page_ids = {req.id for req in first_page}
        second_page_ids = {req.id for req in second_page}
        assert first_page_ids.isdisjoint(second_page_ids), (
            f'Pages overlap: first_page={first_page_ids}, second_page={second_page_ids}'
        )

        # Get last page (offset=4, limit=2)
        third_page = await dao.get_by_user_id(
            user_id=user.id, offset=4, limit=2
        )
        # Should get remaining 1 item
        assert len(third_page) == 1

    @pytest.mark.asyncio
    async def test_get_all(
        self,
        db_session,
        user_factory,
    ):
        """Test getting all requests (for admin)."""
        user1 = await user_factory(email='user1@example.com')
        user2 = await user_factory(email='user2@example.com')
        await db_session.commit()

        dao = AmbulanceRequestDAO(db_session)

        # Create requests for both users (with SUBMITTED status so admin can see them)
        await dao.create(
            user_id=user1.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
            status=RequestStatus.SUBMITTED,
        )
        await dao.create(
            user_id=user2.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='Jane',
            patient_last_name='Smith',
            patient_date_of_birth=date(1975, 5, 15),
            patient_id='DA987654321AB',
            date_of_transport=date(2025, 12, 7),
            time_of_transport=time(14, 0),
            pickup_address='789 Oak Ave',
            destination_address='321 Pine St',
            status=RequestStatus.SUBMITTED,
        )
        await db_session.commit()

        all_requests = await dao.get_all()

        assert len(all_requests) == 2
        user_ids = {req.user_id for req in all_requests}
        assert user_ids == {user1.id, user2.id}
        # Verify status_history is always loaded
        assert all(hasattr(req, 'status_history') for req in all_requests)

    @pytest.mark.asyncio
    async def test_get_all_with_pagination(
        self,
        db_session,
        user_factory,
    ):
        """Test getting all requests with pagination."""
        user1 = await user_factory(email='user1@example.com')
        user2 = await user_factory(email='user2@example.com')
        await db_session.commit()

        dao = AmbulanceRequestDAO(db_session)

        # Create 5 requests across both users (with SUBMITTED status so admin can see them)
        request_ids = []
        for i in range(5):
            user = user1 if i % 2 == 0 else user2
            request = await dao.create(
                user_id=user.id,
                transportation_type=TransportationType.AMBULANCE,
                patient_first_name=f'Patient{i}',
                patient_last_name='Doe',
                patient_date_of_birth=date(1980, 1, 1),
                patient_id=f'DA12345678{i}HY',
                date_of_transport=date(2025, 12, 6),
                time_of_transport=time(13, 40),
                pickup_address='123 Main St',
                destination_address='456 Medical Dr',
                status=RequestStatus.SUBMITTED,
            )
            request_ids.append(request.id)
            await db_session.commit()

        # Get first page (offset=0, limit=2)
        first_page = await dao.get_all(offset=0, limit=2)
        assert len(first_page) == 2
        # Verify descending order (newer first, then by ID desc)
        assert first_page[0].id > first_page[1].id

        # Get next page (offset=2, limit=2)
        second_page = await dao.get_all(offset=2, limit=2)
        # Should get next 2 items
        assert len(second_page) == 2
        # Should not overlap with first page
        first_page_ids = {req.id for req in first_page}
        second_page_ids = {req.id for req in second_page}
        assert first_page_ids.isdisjoint(second_page_ids), (
            f'Pages overlap: first_page={first_page_ids}, second_page={second_page_ids}'
        )

        # Get last page (offset=4, limit=2)
        third_page = await dao.get_all(offset=4, limit=2)
        # Should get remaining 1 item
        assert len(third_page) == 1

    @pytest.mark.asyncio
    async def test_get_expiring_requests(
        self,
        db_session,
        user_factory,
    ):
        """Test getting requests expiring in N days."""
        user = await user_factory()
        await db_session.commit()

        dao = AmbulanceRequestDAO(db_session)
        today = datetime.now(tz=UTC).date()

        # Create request expiring in 30 days (APPROVED)
        request_30 = await dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
            status=RequestStatus.APPROVED,
        )
        request_30.expiration_date = today + timedelta(days=30)

        # Create request expiring in 15 days (APPROVED)
        request_15 = await dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='Jane',
            patient_last_name='Smith',
            patient_date_of_birth=date(1990, 1, 1),
            patient_id='DA987654321XY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(14, 0),
            pickup_address='456 Oak Ave',
            destination_address='789 Pine St',
            status=RequestStatus.APPROVED,
        )
        request_15.expiration_date = today + timedelta(days=15)

        # Create request expiring in 30 days but DENIED (should not be returned)
        request_denied = await dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='Bob',
            patient_last_name='Brown',
            patient_date_of_birth=date(1985, 1, 1),
            patient_id='DA555555555AA',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(15, 0),
            pickup_address='789 Elm St',
            destination_address='321 Maple Dr',
            status=RequestStatus.DENIED,
        )
        request_denied.expiration_date = today + timedelta(days=30)

        await db_session.commit()

        # Test getting requests expiring in 30 days
        expiring_30 = await dao.get_expiring_requests(days=30)
        assert len(expiring_30) == 1
        assert expiring_30[0].id == request_30.id

        # Test getting requests expiring in 15 days
        expiring_15 = await dao.get_expiring_requests(days=15)
        assert len(expiring_15) == 1
        assert expiring_15[0].id == request_15.id

        # Test getting requests expiring in 7 days (none)
        expiring_7 = await dao.get_expiring_requests(days=7)
        assert len(expiring_7) == 0

    @pytest.mark.asyncio
    async def test_get_expiring_requests_only_approved(
        self,
        db_session,
        user_factory,
    ):
        """Test that only APPROVED requests are returned."""
        user = await user_factory()
        await db_session.commit()

        dao = AmbulanceRequestDAO(db_session)
        today = datetime.now(tz=UTC).date()

        # Create requests with different statuses
        statuses = [
            RequestStatus.DRAFT,
            RequestStatus.SUBMITTED,
            RequestStatus.PENDING,
            RequestStatus.APPROVED,
            RequestStatus.DENIED,
        ]

        for status in statuses:
            request = await dao.create(
                user_id=user.id,
                transportation_type=TransportationType.AMBULANCE,
                patient_first_name='Test',
                patient_last_name='User',
                patient_date_of_birth=date(1980, 1, 1),
                patient_id=f'DA{status.value}',
                date_of_transport=date(2025, 12, 6),
                time_of_transport=time(13, 40),
                pickup_address='123 Main St',
                destination_address='456 Medical Dr',
                status=status,
            )
            request.expiration_date = today + timedelta(days=30)

        await db_session.commit()

        # Only APPROVED should be returned
        expiring = await dao.get_expiring_requests(days=30)
        assert len(expiring) == 1
        assert expiring[0].status == RequestStatus.APPROVED

    @pytest.mark.asyncio
    async def test_get_expiring_requests_no_expiration_date(
        self,
        db_session,
        user_factory,
    ):
        """Test that requests without expiration_date are not returned."""
        user = await user_factory()
        await db_session.commit()

        dao = AmbulanceRequestDAO(db_session)
        today = datetime.now(tz=UTC).date()

        # Create request with expiration_date
        request_with_exp = await dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
            status=RequestStatus.APPROVED,
        )
        request_with_exp.expiration_date = today + timedelta(days=30)

        # Create request without expiration_date
        request_no_exp = await dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='Jane',
            patient_last_name='Smith',
            patient_date_of_birth=date(1990, 1, 1),
            patient_id='DA987654321XY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(14, 0),
            pickup_address='456 Oak Ave',
            destination_address='789 Pine St',
            status=RequestStatus.APPROVED,
        )
        # expiration_date is None

        await db_session.commit()

        expiring = await dao.get_expiring_requests(days=30)
        assert len(expiring) == 1
        assert expiring[0].id == request_with_exp.id


class TestRequestStatusHistoryDAO:
    """Test suite for RequestStatusHistoryDAO."""

    @pytest.mark.asyncio
    async def test_create(
        self,
        db_session,
        user_factory,
    ):
        """Test creating status history entry."""
        user = await user_factory()
        await db_session.commit()

        request_dao = AmbulanceRequestDAO(db_session)
        request = await request_dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
        )
        await db_session.commit()

        history_dao = RequestStatusHistoryDAO(db_session)
        history = await history_dao.create(
            request_id=request.id,
            status=RequestStatus.SUBMITTED,
            notes='Request submitted',
        )
        await db_session.commit()

        assert history.id is not None
        assert history.request_id == request.id
        assert history.status == RequestStatus.SUBMITTED
        assert history.notes == 'Request submitted'

    @pytest.mark.asyncio
    async def test_get_by_request_id(
        self,
        db_session,
        user_factory,
    ):
        """Test getting status history for a request."""
        user = await user_factory()
        await db_session.commit()

        request_dao = AmbulanceRequestDAO(db_session)
        request = await request_dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
        )
        await db_session.commit()

        history_dao = RequestStatusHistoryDAO(db_session)
        history1 = await history_dao.create(
            request_id=request.id,
            status=RequestStatus.SUBMITTED,
            notes='Request submitted',
        )
        history2 = await history_dao.create(
            request_id=request.id,
            status=RequestStatus.PENDING,
            notes='Under review',
        )
        await db_session.commit()

        all_history = await history_dao.get_by_request_id(request.id)

        assert len(all_history) == 2
        # Should be ordered by created_at asc
        assert all_history[0].id == history1.id
        assert all_history[1].id == history2.id
        assert all_history[0].status == RequestStatus.SUBMITTED
        assert all_history[1].status == RequestStatus.PENDING


class TestRequestFileDAO:
    """Test suite for RequestFileDAO."""

    @pytest.mark.asyncio
    async def test_create(
        self,
        db_session,
    ):
        """Test creating a file record."""
        dao = RequestFileDAO(db_session)
        file = await dao.create(
            request_id=None,
            filename='test.pdf',
            s3_key='users/1/ambulance-requests/test.pdf',
            file_size=1024,
            content_type='application/pdf',
        )
        await db_session.commit()

        assert file.id is not None
        assert file.request_id is None
        assert file.filename == 'test.pdf'
        assert file.s3_key == 'users/1/ambulance-requests/test.pdf'
        assert file.file_size == 1024
        assert file.content_type == 'application/pdf'

    @pytest.mark.asyncio
    async def test_get_by_id(
        self,
        db_session,
    ):
        """Test getting file by ID."""
        dao = RequestFileDAO(db_session)
        created = await dao.create(
            request_id=None,
            filename='test.pdf',
            s3_key='users/1/test.pdf',
            file_size=1024,
            content_type='application/pdf',
        )
        await db_session.commit()

        found = await dao.get_by_id(created.id)

        assert found is not None
        assert found.id == created.id
        assert found.filename == 'test.pdf'

    @pytest.mark.asyncio
    async def test_get_by_request_id(
        self,
        db_session,
        user_factory,
    ):
        """Test getting all files for a request."""
        user = await user_factory()
        await db_session.commit()

        request_dao = AmbulanceRequestDAO(db_session)
        request = await request_dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
        )
        await db_session.commit()

        file_dao = RequestFileDAO(db_session)
        file1 = await file_dao.create(
            request_id=request.id,
            filename='file1.pdf',
            s3_key='users/1/file1.pdf',
            file_size=1024,
            content_type='application/pdf',
        )
        file2 = await file_dao.create(
            request_id=request.id,
            filename='file2.pdf',
            s3_key='users/1/file2.pdf',
            file_size=2048,
            content_type='application/pdf',
        )
        # File without request_id
        await file_dao.create(
            request_id=None,
            filename='file3.pdf',
            s3_key='users/1/file3.pdf',
            file_size=3072,
            content_type='application/pdf',
        )
        await db_session.commit()

        request_files = await file_dao.get_by_request_id(request.id)

        assert len(request_files) == 2
        assert all(f.request_id == request.id for f in request_files)
        assert {f.id for f in request_files} == {file1.id, file2.id}

    @pytest.mark.asyncio
    async def test_update_request_id(
        self,
        db_session,
        user_factory,
    ):
        """Test updating request_id for a file."""
        user = await user_factory()
        await db_session.commit()

        request_dao = AmbulanceRequestDAO(db_session)
        request = await request_dao.create(
            user_id=user.id,
            transportation_type=TransportationType.AMBULANCE,
            patient_first_name='John',
            patient_last_name='Doe',
            patient_date_of_birth=date(1980, 1, 1),
            patient_id='DA123456789HY',
            date_of_transport=date(2025, 12, 6),
            time_of_transport=time(13, 40),
            pickup_address='123 Main St',
            destination_address='456 Medical Dr',
        )
        await db_session.commit()

        file_dao = RequestFileDAO(db_session)
        file = await file_dao.create(
            request_id=None,
            filename='test.pdf',
            s3_key='users/1/test.pdf',
            file_size=1024,
            content_type='application/pdf',
        )
        await db_session.commit()

        updated = await file_dao.update_request_id(
            file_id=file.id,
            request_id=request.id,
        )
        await db_session.commit()

        assert updated is not None
        assert updated.id == file.id
        assert updated.request_id == request.id

        # Verify it's updated in DB
        found = await file_dao.get_by_id(file.id)
        assert found is not None
        assert found.request_id == request.id

    @pytest.mark.asyncio
    async def test_update_request_id_not_found(
        self,
        db_session,
    ):
        """Test updating request_id for non-existent file returns None."""
        file_dao = RequestFileDAO(db_session)
        updated = await file_dao.update_request_id(
            file_id=99999,
            request_id=1,
        )
        assert updated is None
