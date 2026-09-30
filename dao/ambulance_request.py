from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import selectinload

from core.dao import BaseDAO
from models.ambulance_request import (
    AmbulanceRequest,
    AmbulatoryStatus,
    InsuranceType,
    PatientRelationshipToInsured,
    PatientSex,
    RequestStatus,
    RequestStatusHistory,
)
from models.request_file import RequestFile


class AmbulanceRequestDAO(BaseDAO):
    """DAO for AmbulanceRequest model."""

    async def create(
        self,
        *,
        user_id: int,
        transportation_type: str,
        patient_first_name: str,
        patient_last_name: str,
        patient_date_of_birth: date,
        patient_id: str,
        date_of_transport: date,
        time_of_transport: time,
        pickup_address: str,
        destination_address: str,
        primary_diagnosis: str | None = None,
        medical_justification: str | None = None,
        form_number: str | None = None,
        status: RequestStatus = RequestStatus.DRAFT,
        ambulatory_status: AmbulatoryStatus | None = None,
        oxygen_required: bool = False,
        ai_accuracy: float | None = None,
        ordering_physician: str | None = None,
        physician_phone: str | None = None,
        ordering_physician_npi: str | None = None,
        patient_sex: PatientSex | None = None,
        insurance_type: InsuranceType | None = None,
        insurance_payer_name: str | None = None,
        insured_id_number: str | None = None,
        insured_name: str | None = None,
        patient_relationship_to_insured: (
            PatientRelationshipToInsured | None
        ) = None,
    ) -> AmbulanceRequest:
        """Create a new ambulance request.

        Args:
            user_id: ID of the user creating the request.
            transportation_type: Type of transportation.
            patient_first_name: Patient's first name.
            patient_last_name: Patient's last name.
            patient_date_of_birth: Patient's date of birth.
            patient_id: Patient's ID.
            date_of_transport: Date of transport.
            time_of_transport: Time of transport.
            pickup_address: Pickup address.
            destination_address: Destination address.
            primary_diagnosis: Primary diagnosis (optional).
            medical_justification: Medical justification (optional).
            form_number: CMS form number (optional).
            status: Request status (default: PROCESSING).
            ambulatory_status: Patient ambulatory status (optional).
            oxygen_required: Whether oxygen is required (default: False).
            ai_accuracy: AI confidence in filled data (optional).
            ordering_physician: Name of ordering physician (optional).
            physician_phone: Phone number of ordering physician (optional).
            ordering_physician_npi: NPI of ordering physician (optional).
            patient_sex: Patient sex (optional).
            insurance_type: Type of insurance/payer (optional).
            insurance_payer_name: Name of insurance carrier (optional).
            insured_id_number: Insured's ID number (optional).
            insured_name: Insured's name, if different from patient
                (optional).
            patient_relationship_to_insured: Patient's relationship to
                insured (optional).

        Returns:
            AmbulanceRequest: Created request instance.

        """
        request = AmbulanceRequest(
            user_id=user_id,
            transportation_type=transportation_type,
            patient_first_name=patient_first_name,
            patient_last_name=patient_last_name,
            patient_date_of_birth=patient_date_of_birth,
            patient_id=patient_id,
            date_of_transport=date_of_transport,
            time_of_transport=time_of_transport,
            pickup_address=pickup_address,
            destination_address=destination_address,
            primary_diagnosis=primary_diagnosis,
            medical_justification=medical_justification,
            form_number=form_number,
            status=status,
            ambulatory_status=ambulatory_status,
            oxygen_required=oxygen_required,
            ai_accuracy=ai_accuracy,
            ordering_physician=ordering_physician,
            physician_phone=physician_phone,
            ordering_physician_npi=ordering_physician_npi,
            patient_sex=patient_sex,
            insurance_type=insurance_type,
            insurance_payer_name=insurance_payer_name,
            insured_id_number=insured_id_number,
            insured_name=insured_name,
            patient_relationship_to_insured=patient_relationship_to_insured,
        )
        self._session.add(request)
        await self._session.flush()
        await self._session.refresh(request)
        return request

    async def get_by_id(
        self,
        request_id: int,
    ) -> AmbulanceRequest | None:
        """Get request by id.

        Args:
            request_id: Request ID.
            include_files: Whether to include related files.
            include_status_history: Whether to include status history.

        Returns:
            AmbulanceRequest | None: Request instance or None if not found.

        """
        stmt = (
            select(AmbulanceRequest)
            .where(
                AmbulanceRequest.id == request_id,
                AmbulanceRequest.is_active.is_(True),
            )
            .options(
                selectinload(AmbulanceRequest.files),
                selectinload(AmbulanceRequest.status_history),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(
        self,
        request_id: int,
    ) -> AmbulanceRequest | None:
        """Get request by id, locking the row for the rest of the transaction.

        Used for read-modify-write updates to a single column (e.g.
        merging into the call_sheet_data JSON blob) where two concurrent
        writers could otherwise silently drop each other's changes. Not
        supported by SQLite (used in tests); SQLAlchemy's SQLite dialect
        just omits the locking clause there, so it's safe to call in any
        environment, but only actually locks on Postgres.

        Args:
            request_id: Request ID.

        Returns:
            AmbulanceRequest | None: Request instance or None if not found.

        """
        stmt = (
            select(AmbulanceRequest)
            .where(
                AmbulanceRequest.id == request_id,
                AmbulanceRequest.is_active.is_(True),
            )
            .with_for_update()
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    def _build_filter_stmt(
        self,
        *,
        user_id: int | None = None,
        search: str | None = None,
        status: RequestStatus | None = None,
        days: int | None = None,
    ) -> Select[Any]:
        """Build base filter statement for requests.

        Args:
            user_id: User ID to filter by (None for all users - admin view).
            search: Search term for patient name or ID.
            status: Request status to filter by.
            days: Number of days to filter by (from today).

        Returns:
            select: SQLAlchemy select statement with filters applied.

        """
        stmt = select(AmbulanceRequest).where(
            AmbulanceRequest.is_active == True  # noqa: E712
        )

        if user_id is not None:
            stmt = stmt.where(AmbulanceRequest.user_id == user_id)
        # Admin view: exclude DRAFT requests unless explicitly filtered by DRAFT
        elif status != RequestStatus.DRAFT:
            stmt = stmt.where(AmbulanceRequest.status != RequestStatus.DRAFT)

        if search:
            search_pattern = f'%{search}%'
            stmt = stmt.where(
                or_(
                    AmbulanceRequest.patient_first_name.ilike(search_pattern),
                    AmbulanceRequest.patient_last_name.ilike(search_pattern),
                    AmbulanceRequest.patient_id.ilike(search_pattern),
                )
            )

        if status:
            stmt = stmt.where(AmbulanceRequest.status == status)

        if days is not None:
            if days == 0:  # Today
                today_start = datetime.now(UTC).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                today_end = today_start + timedelta(days=1)
                stmt = stmt.where(
                    AmbulanceRequest.created_at >= today_start,
                    AmbulanceRequest.created_at < today_end,
                )
            else:
                date_from = datetime.now(UTC) - timedelta(days=days)
                stmt = stmt.where(AmbulanceRequest.created_at >= date_from)

        return stmt

    async def count_by_user_id(
        self,
        user_id: int,
        *,
        search: str | None = None,
        status: RequestStatus | None = None,
        days: int | None = None,
    ) -> int:
        """Count requests for a user with filters.

        Args:
            user_id: User ID.
            search: Search term for patient name or ID.
            status: Request status to filter by.
            days: Number of days to filter by (from today).

        Returns:
            int: Total count of requests.

        """
        stmt = self._build_filter_stmt(
            user_id=user_id, search=search, status=status, days=days
        )
        stmt = select(func.count()).select_from(stmt.subquery())
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def get_by_user_id(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 8,
        search: str | None = None,
        status: RequestStatus | None = None,
        days: int | None = None,
    ) -> list[AmbulanceRequest]:
        """Get all requests for a user with pagination and filters.

        Args:
            user_id: User ID.
            offset: Number of items to skip.
            limit: Maximum number of items to return.
            search: Search term for patient name or ID.
            status: Request status to filter by.
            days: Number of days to filter by (from today).

        Returns:
            list[AmbulanceRequest]: List of requests.

        """
        stmt = self._build_filter_stmt(
            user_id=user_id, search=search, status=status, days=days
        )
        stmt = (
            stmt.order_by(
                AmbulanceRequest.created_at.desc(), AmbulanceRequest.id.desc()
            )
            .offset(offset)
            .limit(limit)
        )
        stmt = stmt.options(selectinload(AmbulanceRequest.status_history))
        stmt = stmt.options(selectinload(AmbulanceRequest.files))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_all(
        self,
        *,
        search: str | None = None,
        status: RequestStatus | None = None,
        days: int | None = None,
    ) -> int:
        """Count all requests with filters.

        Args:
            search: Search term for patient name or ID.
            status: Request status to filter by.
            days: Number of days to filter by (from today).

        Returns:
            int: Total count of requests.

        """
        stmt = self._build_filter_stmt(
            user_id=None, search=search, status=status, days=days
        )
        stmt = select(func.count()).select_from(stmt.subquery())
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def get_all(
        self,
        *,
        offset: int = 0,
        limit: int = 8,
        search: str | None = None,
        status: RequestStatus | None = None,
        days: int | None = None,
    ) -> list[AmbulanceRequest]:
        """Get all requests (for admin users) with pagination and filters.

        Args:
            offset: Number of items to skip.
            limit: Maximum number of items to return.
            search: Search term for patient name or ID.
            status: Request status to filter by.
            days: Number of days to filter by (from today).

        Returns:
            list[AmbulanceRequest]: List of all requests.

        """
        stmt = self._build_filter_stmt(
            user_id=None, search=search, status=status, days=days
        )
        stmt = (
            stmt.order_by(
                AmbulanceRequest.created_at.desc(), AmbulanceRequest.id.desc()
            )
            .offset(offset)
            .limit(limit)
        )
        stmt = stmt.options(selectinload(AmbulanceRequest.status_history))
        stmt = stmt.options(selectinload(AmbulanceRequest.files))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search_by_patient_id_and_name(
        self,
        *,
        patient_id: str | None = None,
        patient_name: str | None = None,
        user_id: int | None = None,
    ) -> list[int]:
        """Search request IDs by patient ID and/or name.

        Args:
            patient_id: Optional patient ID to search for.
            patient_name: Optional patient name to search for (matches name).
            user_id: Optional user ID to filter by. If None, returns all.

        Returns:
            List of request IDs matching the criteria.

        """
        stmt = select(AmbulanceRequest.id).where(
            AmbulanceRequest.is_active == True  # noqa: E712
        )

        # Filter by user_id if provided (for non-admin users)
        if user_id is not None:
            stmt = stmt.where(AmbulanceRequest.user_id == user_id)

        if patient_id is not None:
            stmt = stmt.where(
                AmbulanceRequest.patient_id.ilike(f'%{patient_id}%')
            )

        if patient_name is not None:
            search_pattern = f'%{patient_name}%'
            stmt = stmt.where(
                or_(
                    AmbulanceRequest.patient_first_name.ilike(search_pattern),
                    AmbulanceRequest.patient_last_name.ilike(search_pattern),
                    func.concat(
                        AmbulanceRequest.patient_first_name,
                        ' ',
                        AmbulanceRequest.patient_last_name,
                    ).ilike(search_pattern),
                )
            )

        stmt = stmt.order_by(
            AmbulanceRequest.created_at.desc(), AmbulanceRequest.id.desc()
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_expiring_requests(self, days: int) -> list[AmbulanceRequest]:
        """Get active requests expiring in exactly N days.

        Args:
            days: Number of days until expiration.

        Returns:
            list[AmbulanceRequest]: List of requests expiring in N days.

        """
        today = datetime.now(tz=UTC).date()
        target_date = today + timedelta(days=days)

        stmt = (
            select(AmbulanceRequest)
            .where(AmbulanceRequest.status == RequestStatus.APPROVED)
            .where(AmbulanceRequest.expiration_date.isnot(None))
            .where(AmbulanceRequest.expiration_date == target_date)
            .where(AmbulanceRequest.is_active.is_(True))
            .where(AmbulanceRequest.deleted_at.is_(None))
        )

        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class RequestStatusHistoryDAO(BaseDAO):
    """DAO for RequestStatusHistory model."""

    async def create(
        self,
        *,
        request_id: int,
        status: RequestStatus,
        notes: str | None = None,
    ) -> RequestStatusHistory:
        """Create a new status history entry.

        Args:
            request_id: ID of the request.
            status: Status at this point in time.
            notes: Optional notes about the status change.

        Returns:
            RequestStatusHistory: Created status history instance.

        """
        status_history = RequestStatusHistory(
            request_id=request_id,
            status=status,
            notes=notes,
        )
        self._session.add(status_history)
        await self._session.flush()
        await self._session.refresh(status_history)
        return status_history

    async def get_by_request_id(
        self,
        request_id: int,
    ) -> list[RequestStatusHistory]:
        """Get all status history entries for a request.

        Args:
            request_id: Request ID.

        Returns:
            list[RequestStatusHistory]: List of status history entries.

        """
        stmt = (
            select(RequestStatusHistory)
            .where(RequestStatusHistory.request_id == request_id)
            .order_by(RequestStatusHistory.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class RequestFileDAO(BaseDAO):
    """DAO for RequestFile model."""

    async def create(
        self,
        *,
        request_id: int | None,
        filename: str,
        s3_key: str,
        file_size: int,
        content_type: str,
    ) -> RequestFile:
        """Create a new request file entry.

        Args:
            request_id: ID of the request (nullable for temporary files).
            filename: Original filename.
            s3_key: S3 object key.
            file_size: File size in bytes.
            content_type: MIME type of the file.

        Returns:
            RequestFile: Created file instance.

        """
        request_file = RequestFile(
            request_id=request_id,
            filename=filename,
            s3_key=s3_key,
            file_size=file_size,
            content_type=content_type,
        )
        self._session.add(request_file)
        await self._session.flush()
        await self._session.refresh(request_file)
        return request_file

    async def get_by_id(self, file_id: int) -> RequestFile | None:
        """Get file by id.

        Args:
            file_id: File ID.

        Returns:
            RequestFile | None: File instance or None if not found.

        """
        stmt = select(RequestFile).where(RequestFile.id == file_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ids(
        self,
        file_ids: list[int],
    ) -> list[RequestFile]:
        """Get files by list of IDs.

        Args:
            file_ids: List of file IDs.

        Returns:
            list[RequestFile]: List of file instances.

        """
        if not file_ids:
            return []
        stmt = select(RequestFile).where(RequestFile.id.in_(file_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_request_id(self, request_id: int) -> list[RequestFile]:
        """Get all files for a request.

        Args:
            request_id: Request ID.

        Returns:
            list[RequestFile]: List of files.

        """
        stmt = select(RequestFile).where(RequestFile.request_id == request_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_request_id(
        self,
        file_id: int,
        request_id: int,
    ) -> RequestFile | None:
        """Update request_id for a file.

        Args:
            file_id: File ID.
            request_id: Request ID to link.

        Returns:
            RequestFile | None: Updated file instance or None if not found.

        """
        stmt = (
            update(RequestFile)
            .where(RequestFile.id == file_id)
            .values(request_id=request_id)
            .returning(RequestFile)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one_or_none()

    async def delete_by_id(self, file_id: int) -> RequestFile | None:
        """Delete file by id.

        Args:
            file_id: File ID.

        Returns:
            RequestFile | None: Deleted file instance or None if not found.

        """
        file = await self.get_by_id(file_id)
        if file:
            await self._session.delete(file)
            await self._session.flush()
        return file
