from .ambulance_request import ambulance_request_router
from .auth import auth_router
from .dashboard import dashboard_router
from .fax import fax_router
from .main import main_router
from .notification import notification_router
from .organization import organization_router
from .reports import report_router
from .stats import stats_router
from .user import user_router
from .websocket import websocket_router

__all__ = [
    'ambulance_request_router',
    'auth_router',
    'dashboard_router',
    'fax_router',
    'main_router',
    'notification_router',
    'organization_router',
    'report_router',
    'stats_router',
    'user_router',
    'websocket_router',
]
