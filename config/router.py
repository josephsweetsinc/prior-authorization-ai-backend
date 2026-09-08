"""Router initialization and configuration."""

from fastapi import APIRouter

from config.settings import Settings
from endpoints import (
    ambulance_request_router,
    auth_router,
    dashboard_router,
    fax_router,
    main_router,
    notification_router,
    organization_router,
    report_router,
    stats_router,
    user_router,
    websocket_router,
)

settings = Settings.load()


def initialize_routers() -> APIRouter:
    """Initialize and configure all API routers.

    Creates the main API router with version prefix and includes
    all sub-routers (main, project, contact, seo) with their prefixes and tags.

    Returns:
        APIRouter: Configured main API router with all endpoints included.

    """
    main_api_router = APIRouter(prefix=f'/api/{settings.API_VERSION}')
    main_api_router.include_router(main_router, prefix='/health', tags=['main'])
    main_api_router.include_router(user_router, prefix='/user')
    main_api_router.include_router(auth_router, prefix='/auth', tags=['auth'])
    main_api_router.include_router(
        ambulance_request_router,
        prefix='/ambulance-request',
        tags=['ambulance-request'],
    )
    main_api_router.include_router(
        dashboard_router,
        prefix='/dashboard_metrics',
        tags=['dashboard_metrics'],
    )
    main_api_router.include_router(
        organization_router,
        prefix='/organization',
        tags=['organization'],
    )
    main_api_router.include_router(
        notification_router,
        prefix='/notification',
        tags=['notification'],
    )
    main_api_router.include_router(
        stats_router,
        prefix='/stats',
        tags=['stats'],
    )
    main_api_router.include_router(
        report_router,
        prefix='/report',
        tags=['report'],
    )
    main_api_router.include_router(
        websocket_router,
        prefix='/websocket',
        tags=['websocket'],
    )
    main_api_router.include_router(
        fax_router,
        prefix='/fax',
        tags=['fax'],
    )
    return main_api_router
