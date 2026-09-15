"""Раздача приложения «BONJOUR Мастер» на личные телефоны мастеров.

Без авторизации: мастер открывает ссылку в браузере телефона, когда у него
ещё ничего не установлено. Секретов внутри APK нет — это оболочка над
публичным адресом кабинета, а в сам кабинет пускают только по логину и
паролю.
"""
from __future__ import annotations

import html
import secrets
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from app.services import master_app_service

_PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BONJOUR Мастер</title>
<style>
:root { --bg:#f8fafc; --card:#ffffff; --text:#0f172a; --muted:#64748b; --line:#e2e8f0; --btn:#0a0a0a; --btn-text:#f8fafc; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0a0a0a; --card:#141414; --text:#f8fafc; --muted:#94a3b8; --line:#262626; --btn:#f8fafc; --btn-text:#0a0a0a; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; padding:32px 16px; }
main { max-width:28rem; margin:0 auto; }
.logo { width:56px; height:56px; border-radius:14px; background:var(--btn); color:var(--btn-text); display:grid; place-items:center; font-weight:700; font-size:28px; }
h1 { font-size:1.6rem; margin:16px 0 4px; }
.lead { color:var(--muted); margin:0 0 24px; }
.btn { display:block; text-align:center; background:var(--btn); color:var(--btn-text); text-decoration:none; font-weight:600; padding:14px; border-radius:12px; }
.btn:focus-visible { outline:3px solid var(--muted); outline-offset:2px; }
.meta { color:var(--muted); font-size:.85rem; text-align:center; margin:8px 0 28px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; }
ol.card { margin:0; padding:16px 16px 16px 36px; }
li + li { margin-top:10px; }
.off { padding:16px; color:var(--muted); }
</style>
</head>
<body>
<main>
<div class="logo">B</div>
<h1>BONJOUR Мастер</h1>
<p class="lead">Заработок, работы в процессе и запрос аванса — в телефоне.</p>
%BODY%
</main>
</body>
</html>"""

_STEPS = """<a class="btn" href="/api/master-app/%APK%">Скачать приложение</a>
<p class="meta">%META%</p>
<ol class="card">
<li>Нажмите «Скачать приложение» и откройте скачанный файл.</li>
<li>Если телефон спросит — разрешите установку из этого источника и вернитесь назад.</li>
<li>Если Play Защита предупредит о неизвестном приложении — нажмите «Подробнее» → «Всё равно установить».</li>
<li>Откройте «BONJOUR Мастер» и войдите по логину и паролю, которые выдал руководитель.</li>
</ol>"""


def create_master_app_public_router() -> APIRouter:
    router = APIRouter(prefix="/master-app", tags=["Master app"])

    @router.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def install_page() -> HTMLResponse:
        """Страница, на которую ведёт ссылка, отправленная мастеру."""
        data = master_app_service.info()
        if not data["available"]:
            body = '<div class="card off">Приложение ещё не загружено на сервер. Попробуйте позже.</div>'
        else:
            meta = "Только для Android"
            if data.get("version_name"):
                size_mb = data["size"] / (1024 * 1024)
                meta = f"Версия {data['version_name']} · {size_mb:.1f} МБ · только для Android"
            body = (
                _STEPS.replace("%APK%", master_app_service.PUBLIC_APK_NAME)
                .replace("%META%", html.escape(meta))
            )
        return HTMLResponse(_PAGE.replace("%BODY%", body))

    @router.get("/info")
    async def get_info() -> dict:
        return master_app_service.info()

    @router.get("/" + master_app_service.PUBLIC_APK_NAME)
    async def download_apk() -> FileResponse:
        path = master_app_service.apk_path()
        if not path.exists():
            raise HTTPException(status_code=404, detail="master_app_not_uploaded")
        # Content-Encoding: identity — чтобы GZipMiddleware не пережал APK
        # (подробности в app/api/mdm.py::_apk_response).
        return FileResponse(
            path,
            media_type="application/vnd.android.package-archive",
            filename=master_app_service.PUBLIC_APK_NAME,
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
            return master_app_service.save_apk(await file.read())
        except master_app_service.MasterAppValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return router
