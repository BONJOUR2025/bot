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
        date_from: str | None = None,
        date_to: str | None = None,
        creater_ids: str | None = None,
        user_ids: str | None = None,
        folder_ids: str | None = None,
        code_substr: str | None = None,
        name_substr: str | None = None,
        min_kredit: float | None = None,
        max_kredit: float | None = None,
        doc_num_substr: str | None = None,
        item_type: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ):
        return await service.get_sales_details(
            date_from=date_from,
            date_to=date_to,
            creater_ids=creater_ids.split(",") if creater_ids else None,
            user_ids=user_ids.split(",") if user_ids else None,
            folder_ids=folder_ids.split(",") if folder_ids else None,
            code_substr=code_substr,
            name_substr=name_substr,
            min_kredit=min_kredit,
            max_kredit=max_kredit,
            doc_num_substr=doc_num_substr,
            item_type=item_type,
            page=page,
            page_size=page_size,
        )

    @router.post("/sales/details/refresh")
    async def refresh_sales_details():
        await service.refresh_sales_details()
        return {"status": "ok"}

    @router.get("/sales/rating")
    async def get_sales_rating(
        date_from: str | None = None,
        date_to: str | None = None,
        creater_ids: str | None = None,
        user_ids: str | None = None,
        folder_ids: str | None = None,
        item_type: str | None = None,
    ):
        return await service.get_sales_rating(
            date_from=date_from,
            date_to=date_to,
            creater_ids=creater_ids.split(",") if creater_ids else None,
            user_ids=user_ids.split(",") if user_ids else None,
            folder_ids=folder_ids.split(",") if folder_ids else None,
            item_type=item_type,
        )

    @router.get("/detailed")
    async def get_detailed(
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        return await service.get_employee_detailed(
            date_from=date_from, date_to=date_to
        )

    return router
