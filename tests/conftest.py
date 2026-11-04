"""Pytest configuration and shared fixtures."""

from collections.abc import AsyncGenerator, Callable
from datetime import UTC, date, datetime, time, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from config.database import Base
from dao import (
    AmbulanceRequestDAO,
    PasswordResetCodeDAO,
    RequestFileDAO,
    RequestStatusHistoryDAO,
    UserDAO,
)
from models import PasswordResetCode, User
from models.ambulance_request import (
    AmbulanceRequest,
    RequestStatus,
    RequestStatusHistory,
    TransportationType,
)
from models.user import UserRole
from services import UserService
from services.email import EmailService
from services.jwt.hasher import Hasher
from services.password import PasswordService


@pytest_asyncio.fixture(scope='function')
async def db_session() -> AsyncGenerator[AsyncSession]:
    """Create a test database session with in-memory SQLite.

    Yields:
        AsyncSession: Database session for testing.

    """
    # Create in-memory SQLite database for testing
    engine = create_async_engine(
        'sqlite+aiosqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def user_factory(db_session: AsyncSession) -> Callable:
    """Factory for creating User instances.

    Args:
        db_session: Database session.

    Returns:
        Callable: Factory function for creating users.

    """

    async def _create_user(
        *,
        name: str = 'John',
        surname: str = 'Doe',
        email: str = 'john.doe@example.com',
        password: str = 'hashed_password',
        role: UserRole = UserRole.PROVIDER,
        is_active: bool = True,
        phone_number: str | None = None,
        position: str | None = None,
        place_of_work: str | None = None,
    ) -> User:
        """Create a user instance.

        Args:
            name: User's first name.
            surname: User's last name.
            email: User's email address.
            password: Hashed password.
            role: User role.
            is_active: Whether user is active.
            phone_number: User's phone number.
            position: User's position.
            place_of_work: User's place of work.

        Returns:
            User: Created user instance.

        """
        user = User(
            name=name,
            surname=surname,
            email=email,
            password=password,
            role=role,
            is_active=is_active,
            phone_number=phone_number or '',
            position=position or '',
            place_of_work=place_of_work or '',
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)
        return user

    return _create_user


@pytest.fixture
def password_reset_code_factory(db_session: AsyncSession) -> Callable:
    """Factory for creating PasswordResetCode instances.

    Args:
        db_session: Database session.

    Returns:
        Callable: Factory function for creating password reset codes.

    """

    async def _create_reset_code(
        *,
        code: str = '12345',
        user_id: int = 1,
        expires_at: datetime | None = None,
        is_used: bool = False,
        is_verified: bool = False,
    ) -> PasswordResetCode:
        """Create a password reset code instance.

        Args:
            code: 5-digit reset code.
            user_id: User ID.
            expires_at: Expiration timestamp. If None, defaults to 15 minutes from now.
            is_used: Whether code is used.
            is_verified: Whether code is verified.

        Returns:
            PasswordResetCode: Created password reset code instance.

        """
        if expires_at is None:
            expires_at = datetime.now(UTC) + timedelta(minutes=15)

        reset_code = PasswordResetCode(
            code=code,
            user_id=user_id,
            expires_at=expires_at,
            is_used=is_used,
            is_verified=is_verified,
        )
        db_session.add(reset_code)
        await db_session.flush()
        await db_session.refresh(reset_code)
        return reset_code

    return _create_reset_code


@pytest.fixture
def user_dao(db_session: AsyncSession) -> UserDAO:
    """Create UserDAO instance.

    Args:
        db_session: Database session.

    Returns:
        UserDAO: UserDAO instance.

    """
    return UserDAO(db_session)


@pytest.fixture
def password_reset_code_dao(db_session: AsyncSession) -> PasswordResetCodeDAO:
    """Create PasswordResetCodeDAO instance.

    Args:
        db_session: Database session.

    Returns:
        PasswordResetCodeDAO: PasswordResetCodeDAO instance.

    """
    return PasswordResetCodeDAO(db_session)


@pytest.fixture
def email_service() -> EmailService:
    """Create EmailService instance with mock settings.

    Returns:
        EmailService: EmailService instance.

    """
    from config.settings import EmailSettings

    email_settings = EmailSettings(
        ADMIN_EMAIL='test@example.com',
        SMTP_HOST='localhost',
        SMTP_PORT=587,
        SMTP_USER=None,
        SMTP_PASSWORD=None,
        USE_TLS=False,
    )
    return EmailService(email_settings=email_settings)


@pytest.fixture
def hash_service() -> Hasher:
    """Create Hasher instance.

    Returns:
        Hasher: Hasher instance.

    """
    return Hasher()


@pytest.fixture
def password_reset_service(
    db_session: AsyncSession,
    password_reset_code_dao: PasswordResetCodeDAO,
    user_dao: UserDAO,
    email_service: EmailService,
    hash_service: Hasher,
) -> PasswordService:
    """Create PasswordResetService instance.

    Args:
        db_session: Database session.
        password_reset_code_dao: PasswordResetCodeDAO instance.
        user_dao: UserDAO instance.
        email_service: EmailService instance.
        hash_service: Hasher instance.

    Returns:
        PasswordService: PasswordResetService instance.

    """
    return PasswordService(
        db_session=db_session,
        password_reset_code_dao=password_reset_code_dao,
        user_dao=user_dao,
        email_service=email_service,
        hash_service=hash_service,
    )


@pytest.fixture
def ambulance_request_dao(db_session: AsyncSession) -> AmbulanceRequestDAO:
    """Create AmbulanceRequestDAO instance.

    Args:
        db_session: Database session.

    Returns:
        AmbulanceRequestDAO: AmbulanceRequestDAO instance.

    """
    return AmbulanceRequestDAO(db_session)


@pytest.fixture
def request_status_history_dao(
    db_session: AsyncSession,
) -> RequestStatusHistoryDAO:
    """Create RequestStatusHistoryDAO instance.

    Args:
        db_session: Database session.

    Returns:
        RequestStatusHistoryDAO: RequestStatusHistoryDAO instance.

    """
    return RequestStatusHistoryDAO(db_session)


@pytest.fixture
def request_file_dao(db_session: AsyncSession) -> RequestFileDAO:
    """Create RequestFileDAO instance.

    Args:
        db_session: Database session.

    Returns:
        RequestFileDAO: RequestFileDAO instance.

    """
    return RequestFileDAO(db_session)


@pytest.fixture
def ambulance_request_factory(
    db_session: AsyncSession,
) -> Callable:
    """Factory for creating AmbulanceRequest instances.

    Args:
        db_session: Database session.

    Returns:
        Callable: Factory function for creating ambulance requests.

    """

    async def _create_request(
        *,
        user_id: int,
        transportation_type: TransportationType = TransportationType.AMBULANCE,
        patient_first_name: str = 'John',
        patient_last_name: str = 'Doe',
        patient_date_of_birth: date = date(1980, 1, 1),
        patient_id: str = 'DA123456789HY',
        date_of_transport: date = date(2025, 12, 6),
        time_of_transport: time = time(13, 40),
        pickup_address: str = '123 Main St',
        destination_address: str = '456 Medical Dr',
        primary_diagnosis: str | None = 'Chronic heart failure',
        medical_justification: str | None = 'Patient requires transport',
        form_number: str | None = 'CMS-10344',
        ordering_physician_npi: str | None = '1234567890',
        status: RequestStatus = RequestStatus.DRAFT,
        created_at: datetime | None = None,
    ) -> AmbulanceRequest:
        """Create an ambulance request instance.

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
            primary_diagnosis: Primary diagnosis.
            medical_justification: Medical justification.
            form_number: CMS form number.
            ordering_physician_npi: Ordering/referring physician's NPI.
                Defaults to a valid-looking value so existing tests
                that aren't about this field don't need to care about
                the completion-status check it feeds.
            status: Request status.
            created_at: Optional custom created_at timestamp.

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
            ordering_physician_npi=ordering_physician_npi,
            status=status,
        )
        if created_at is not None:
            request.created_at = created_at
            request.updated_at = created_at
        db_session.add(request)
        await db_session.flush()
        await db_session.refresh(request)
        return request

    return _create_request


@pytest.fixture
def request_status_history_factory(
    db_session: AsyncSession,
) -> Callable:
    """Factory for creating RequestStatusHistory instances.

    Args:
        db_session: Database session.

    Returns:
        Callable: Factory function for creating status history entries.

    """

    async def _create_status_history(
        *,
        request_id: int,
        status: RequestStatus,
        notes: str | None = None,
        created_at: datetime | None = None,
    ) -> RequestStatusHistory:
        """Create a status history entry.

        Args:
            request_id: ID of the request.
            status: Status at this point in time.
            notes: Optional notes about the status change.
            created_at: Optional custom created_at timestamp.

        Returns:
            RequestStatusHistory: Created status history instance.

        """
        status_history = RequestStatusHistory(
            request_id=request_id,
            status=status,
            notes=notes,
        )
        if created_at is not None:
            status_history.created_at = created_at
        db_session.add(status_history)
        await db_session.flush()
        await db_session.refresh(status_history)
        return status_history

    return _create_status_history


@pytest.fixture
def service(db_session: AsyncSession) -> UserService:
    """Create UserService instance.

    Args:
        db_session: Database session.

    Returns:
        UserService: UserService instance.

    """
    return UserService(db_session=db_session)
