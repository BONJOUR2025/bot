from fastapi import APIRouter

from app.services.dictionary_service import DictionaryService


def create_dictionary_router(service: DictionaryService) -> APIRouter:
    router = APIRouter(prefix="/dictionary", tags=["Dictionary"])

    @router.get("/", response_model=dict)
    async def get_dictionary():
        return service.load()

    @router.patch("/", response_model=dict)
    async def patch_dictionary(data: dict):
        return service.patch(data)

    return router
