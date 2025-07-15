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

    @router.get("/sales/details")
    async def get_sales_details(
        period: str | None = None,
        period_from: str | None = None,
        period_to: str | None = None,
        creator_ids: str | None = None,
        user_ids: str | None = None,
        folder_ids: str | None = None,
        item_code: str | None = None,
        employee: str | None = None,
        item: str | None = None,
        min_cost: float | None = None,
        max_cost: float | None = None,
        doc_number: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ):
        return await service.get_sales_details(
            period=period,
            period_from=period_from,
            period_to=period_to,
            creator_ids=creator_ids.split(",") if creator_ids else None,
            user_ids=user_ids.split(",") if user_ids else None,
            folder_ids=folder_ids.split(",") if folder_ids else None,
            item_code=item_code,
            employee=employee,
            item=item,
            min_cost=min_cost,
            max_cost=max_cost,
            doc_number=doc_number,
            page=page,
            page_size=page_size,
        )

    @router.post("/sales/details/refresh")
    async def refresh_sales_details():
        await service.refresh_sales_details()
        return {"status": "ok"}

    return router
