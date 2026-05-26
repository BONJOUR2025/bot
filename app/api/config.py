import json
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from app.services.config_service import ConfigService

log = logging.getLogger(__name__)


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

    @router.post("/test-notification")
    async def test_notification():
        """Send a test notification and return detailed result for debugging."""
        from app.services.notify import send_notification

        cfg = service.load()
        chat_id = str(cfg.get("notification_chat_id") or "").strip()
        from app.config import TOKEN

        log.info("test-notification: chat_id=%r token_set=%s", chat_id, bool(TOKEN))

        if not chat_id:
            return {"ok": False, "error": "notification_chat_id не заполнен в настройках"}
        if not TOKEN:
            return {"ok": False, "error": "Telegram bot token не настроен"}

        ok = await send_notification("✅ <b>Тест уведомлений</b>\nЕсли вы видите это сообщение — уведомления работают.")
        if ok:
            return {"ok": True, "message": f"Сообщение отправлено на chat_id={chat_id}"}
        else:
            return {"ok": False, "error": f"Не удалось отправить. Проверьте логи сервера и убедитесь что chat_id={chat_id} верный и бот не заблокирован."}

    @router.get("/message-templates")
    async def get_message_templates():
        return service.load().get("message_templates", [])

    @router.put("/message-templates")
    async def save_message_templates(templates: list):
        service.patch({"message_templates": templates})
        return templates

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
            headers={"Content-Disposition": 'attachment; filename="config.json"'},
        )

    return router
