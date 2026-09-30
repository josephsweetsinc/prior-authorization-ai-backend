from sqlalchemy import select

from core.dao import BaseDAO
from models.request_access_log import PHIAccessAction, RequestAccessLog


class RequestAccessLogDAO(BaseDAO):
    """DAO for RequestAccessLog model."""

    async def create(
        self,
        *,
        request_id: int,
        user_id: int | None,
        action: PHIAccessAction,
    ) -> RequestAccessLog:
        """Create a new PHI access log entry.

        Args:
            request_id: ID of the request that was accessed.
            user_id: ID of the user who accessed it, if known.
            action: What kind of access this was.

        Returns:
            RequestAccessLog: Created access log instance.

        """
        access_log = RequestAccessLog(
            request_id=request_id,
            user_id=user_id,
            action=action,
        )
        self._session.add(access_log)
        await self._session.flush()
        await self._session.refresh(access_log)
        return access_log

    async def get_by_request_id(
        self,
        request_id: int,
    ) -> list[RequestAccessLog]:
        """Get all access log entries for a request, newest first.

        Args:
            request_id: Request ID.

        Returns:
            list[RequestAccessLog]: Access log entries for the request.

        """
        stmt = (
            select(RequestAccessLog)
            .where(RequestAccessLog.request_id == request_id)
            .order_by(
                RequestAccessLog.created_at.desc(),
                RequestAccessLog.id.desc(),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
