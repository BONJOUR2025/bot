import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from app.services.config_service import ConfigService


def create_config_router(service: ConfigService) -> APIRouter:
    router = APIRouter(prefix="/config", tags=["Config"])

    @router.get("/", response_model=dict)
    async def get_config():
        return service.load()

    @router.post("/", response_model=dict)
    async def replace_config(data: dict):
        return service.save(data)

    @router.patch("/", response_model=dict)
    async def patch_config(data: dict):
        return service.patch(data)

    @router.post("/upload/")
    async def upload_config(file: UploadFile = File(...)):
        try:
            content = await file.read()
            await service.upload(content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"status": "ok"}

    @router.get("/download/", response_class=FileResponse)
    async def download_config():
        if service.path.exists():
            return FileResponse(service.path, filename="config.json")
        data = service.load()
        return Response(
            content=json.dumps(data, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="config.json"'
            },
        )

    return router
