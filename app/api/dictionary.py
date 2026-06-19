from fastapi import APIRouter, Depends

from app.services.dictionary_service import DictionaryService

from .dependencies import require_permission


def create_dictionary_router(service: DictionaryService) -> APIRouter:
    router = APIRouter(
        prefix="/dictionary",
        tags=["Dictionary"],
        dependencies=[Depends(require_permission("settings"))],
    )

    @router.get("/", response_model=dict)
    async def get_dictionary():
        return service.load()

    @router.patch("/", response_model=dict)
    async def patch_dictionary(data: dict):
        return service.patch(data)

    return router
