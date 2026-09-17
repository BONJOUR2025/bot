"""Раздача приложения «BONJOUR Салон» администраторам точек.

Устроено как раздача приложения мастера (master_app.py) и делит с ним
страницу установки и механику файлов: отличаются название, кому показывать
логины и какой APK лежит на диске. Без авторизации — администратор открывает
ссылку в браузере телефона, когда у него ещё ничего не установлено; секретов
внутри APK нет, в кабинет пускают только по логину и паролю.
"""
from __future__ import annotations

import secrets
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from app.api.master_app import install_page_html
from app.services.device_app_service import SALON_APP, AppValidationError

_STEPS = [
    "Нажмите «Скачать приложение» или наведите камеру телефона на QR-код и откройте скачанный файл.",
    "Если телефон спросит — разрешите установку из этого источника и вернитесь назад.",
    "Если Play Защита предупредит о неизвестном приложении — нажмите «Подробнее» → «Всё равно установить».",
    "Откройте «BONJOUR Салон» и войдите по логину и паролю, которые выдал руководитель.",
]


def create_salon_app_public_router() -> APIRouter:
    router = APIRouter(prefix="/salon-app", tags=["Salon app"])

    @router.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def install_page() -> HTMLResponse:
        """Страница, на которую ведёт ссылка, отправленная администратору."""
        return HTMLResponse(install_page_html(
            SALON_APP,
            title="BONJOUR Салон",
            lead="Зарплата, график, авансы и имущество — в телефоне.",
            steps=_STEPS,
        ))

    @router.get("/info")
    async def get_info() -> dict:
        return SALON_APP.info()

    @router.get("/logins")
    async def list_point_logins() -> list[dict]:
        """Логины администраторов точек для выпадающего списка на входе.

        Публично, как и у мастеров: список нужен до входа. Показываются только
        те, кто закреплён за действующей точкой и может войти по паролю.
        """
        from app.services.access_control_service import get_access_control_service

        return get_access_control_service().point_login_options()

    @router.get("/" + SALON_APP.public_apk_name)
    async def download_apk() -> FileResponse:
        path = SALON_APP.apk_path()
        if not path.exists():
            raise HTTPException(status_code=404, detail="salon_app_not_uploaded")
        # Content-Encoding: identity — чтобы GZipMiddleware не пережал APK
        # (подробности в app/api/mdm.py::_apk_response).
        return FileResponse(
            path,
            media_type="application/vnd.android.package-archive",
            filename=SALON_APP.public_apk_name,
            headers={"Content-Encoding": "identity"},
        )

    @router.get("/archive/{version_name}.apk")
    async def download_archived_apk(version_name: str) -> FileResponse:
        """Сборка конкретной версии — для проверки обновления со старой."""
        path = SALON_APP.archived_apk_path(version_name)
        if path is None or not path.exists():
            raise HTTPException(status_code=404, detail="version_not_found")
        return FileResponse(
            path,
            media_type="application/vnd.android.package-archive",
            filename=path.name,
            headers={"Content-Encoding": "identity"},
        )

    @router.post("/upload")
    async def upload_from_ci(
        file: UploadFile = File(...),
        x_upload_token: Optional[str] = Header(default=None, alias="X-Upload-Token"),
    ) -> dict:
        """Сборка кладёт свежий APK сама, тем же токеном, что и агент MDM."""
        from app.services.mdm_service import current_upload_token

        expected = current_upload_token()
        if not expected:
            raise HTTPException(status_code=503, detail="upload_not_configured")
        if not x_upload_token or not secrets.compare_digest(expected, x_upload_token):
            raise HTTPException(status_code=401, detail="invalid_upload_token")
        try:
            return SALON_APP.save_apk(await file.read())
        except AppValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return router
