import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config.database import async_session_maker
from models import User
from schemas.websocket import WebSocketInfoResponse
from services import UserService
from services.auth import AuthService
from services.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

websocket_router = APIRouter()

_SLICE_LOGGING: int = 50


@websocket_router.get(
    '/notifications/info',
    summary='WebSocket connection information',
    description='Get information about WebSocket endpoint.',
    response_model=WebSocketInfoResponse,
    tags=['websocket'],
)
async def get_websocket_info() -> WebSocketInfoResponse:
    """Get information about WebSocket endpoint for real-time notifications.

    **Note:** WebSocket connections cannot be tested in Swagger UI.
    Use a WebSocket client to connect.

    **Connection details:**
    - URL: `ws://localhost:8000/Prod/api/v1/websocket/notifications`
    - Authentication: `Authorization: Bearer <your_jwt_token>` header
    - Protocol: WebSocket (ws:// or wss://)

    **Example message format:**
    ```json
    {
      "type": "notification",
      "data": {
        "id": 123,
        "user_id": 9,
        "category": "status_update",
        "title": "Request #12 Status Update",
        "message": "Request #12 has been approved",
        "request_id": 12,
        "is_read": false,
        "created_at": "2026-01-13T16:34:38Z"
      }
    }
    ```

    Returns:
        WebSocketInfoResponse: Information about WebSocket endpoint.

    """
    return WebSocketInfoResponse(
        websocket_url='ws://localhost:8000/Prod/api/v1/websocket/notifications',
        authentication='Authorization: Bearer <your_jwt_token>',
        description=(
            'WebSocket endpoint for receiving real-time notifications. '
            'All authenticated users (admins and providers) can connect. '
            'Notifications are sent immediately when created. '
            'If user is not connected, notifications are saved in database '
            'and can be retrieved via GET /api/v1/notification/ endpoint.'
        ),
        example_message={
            'type': 'notification',
            'data': {
                'id': 123,
                'user_id': 9,
                'category': 'status_update',
                'title': 'Request #12 Status Update',
                'message': 'Request #12 has been approved',
                'request_id': 12,
                'is_read': False,
                'created_at': '2026-01-13T16:34:38Z',
            },
        },
    )


def _extract_token_from_header(authorization: str | None) -> str | None:
    """Extract Bearer token from Authorization header.

    Args:
        authorization: Authorization header value (e.g., "Bearer token").

    Returns:
        Token string or None if not found.

    """
    if not authorization:
        return None
    if authorization.startswith('Bearer '):
        return authorization[7:]
    return None


@websocket_router.websocket('/notifications')
async def websocket_notifications(
    websocket: WebSocket,
) -> None:
    """WebSocket endpoint for real-time notifications.

    Connects authenticated users (admins and providers) to receive
    real-time notifications.

    **Authentication (choose one):**
    - Header: `Authorization: Bearer <your_jwt_token>`
    - Query parameter: `?token=<your_jwt_token>` (для браузерного WebSocket API)

    **Testing in Postman:**
    1. Create a new WebSocket request
    2. URL: `ws://localhost:8000/Prod/api/v1/websocket/notifications`
    3. Add header: `Authorization: Bearer <your_jwt_token>`
    4. Click "Connect"
    5. You will receive notifications as they are created

    **Note:** WebSocket connections cannot be tested in Swagger UI.

    Args:
        websocket: WebSocket connection.

    """
    # Accept the connection first to avoid 403 rejection
    await websocket.accept()

    user: User | None = None
    try:
        token = websocket.query_params.get('token')
        if not token:
            await websocket.close(
                code=1008,
                reason='Authorization required (header or ?token=<jwt>)',
            )
            return

        async with async_session_maker() as session:
            auth_service = AuthService(db_session=session)
            user_service = UserService(db_session=session)

            try:
                user_id = await auth_service.validate_token_for_user(token)
                user = await user_service.get_user_by_id(user_id)
            except Exception as e:
                logger.warning('WebSocket authentication failed: %s', e)
                await websocket.close(code=1008, reason='Authentication failed')
                return

            if not user:
                await websocket.close(code=1008, reason='User not found')
                return

        websocket_manager.active_connections[user.id] = websocket
        logger.info('WebSocket connected for user %s', user.id)

        while True:
            data = await websocket.receive_text()
            logger.debug('Received message from user %s: %s', user.id, data)


    except WebSocketDisconnect:
        if user:
            websocket_manager.disconnect(user.id)
        logger.info(
            'WebSocket disconnected for user %s', user.id if user else 'unknown'
        )
    except Exception:
        logger.exception('WebSocket error')
        if user:
            websocket_manager.disconnect(user.id)
        try:
            await websocket.close(code=1011, reason='Internal server error')
        except Exception:
            logger.exception('Failed to close WebSocket connection')
            # Connection might already be closed
