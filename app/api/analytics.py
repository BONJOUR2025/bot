from fastapi import APIRouter

from app.services.analytics import AnalyticsService


def create_analytics_router(service: AnalyticsService) -> APIRouter:
    router = APIRouter(prefix="/analytics", tags=["Analytics"])

    @router.get("/sales")
    async def get_sales():
        return await service.get_sales()

    @router.post("/sales/refresh")
    async def refresh_sales():
        return await service.refresh_sales()

    return router
