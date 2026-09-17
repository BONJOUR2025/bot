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
main { max-width:52rem; margin:0 auto; }
.head { display:flex; gap:16px; align-items:center; margin-bottom:28px; }
.logo { flex:none; width:56px; height:56px; border-radius:14px; background:var(--btn); color:var(--btn-text); display:grid; place-items:center; font-weight:700; font-size:28px; }
h1 { font-size:1.6rem; line-height:1.2; margin:0 0 2px; }
.lead { color:var(--muted); margin:0; }
.grid { display:grid; gap:24px; grid-template-columns:minmax(0, 1fr); }
@media (min-width: 720px) { .grid { grid-template-columns:minmax(0, 1fr) 16rem; align-items:start; } }
.btn { display:block; text-align:center; background:var(--btn); color:var(--btn-text); text-decoration:none; font-weight:600; padding:14px; border-radius:12px; }
.btn:focus-visible { outline:3px solid var(--muted); outline-offset:2px; }
.meta { color:var(--muted); font-size:.85rem; text-align:center; margin:8px 0 20px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; }
ol.card { margin:0; padding:16px 16px 16px 36px; }
li + li { margin-top:10px; }
.off { padding:16px; color:var(--muted); }
.qr { margin:0; padding:16px; text-align:center; }
/* Код всегда тёмным по белому, и в тёмной теме тоже: камеры хуже читают
   инвертированный QR, а белое поле заодно даёт ему нужную «тихую зону». */
.qr__code { background:#ffffff; border-radius:8px; padding:8px; line-height:0; }
.qr__code svg { width:100%; height:auto; max-width:14rem; }
.qr figcaption { color:var(--muted); font-size:.85rem; margin-top:12px; }
</style>
</head>
<body>
<main>
<header class="head">
<div class="logo">B</div>
<div>
<h1>BONJOUR Мастер</h1>
<p class="lead">Заработок, работы в процессе и запрос аванса — в телефоне.</p>
</div>
</header>
%BODY%
</main>
</body>
</html>"""

_AVAILABLE = """<div class="grid">
<section>
<a class="btn" href="/api/master-app/%APK%">Скачать приложение</a>
<p class="meta">%META%</p>
<ol class="card">
<li>Нажмите «Скачать приложение» или наведите камеру телефона на QR-код и откройте скачанный файл.</li>
<li>Если телефон спросит — разрешите установку из этого источника и вернитесь назад.</li>
<li>Если Play Защита предупредит о неизвестном приложении — нажмите «Подробнее» → «Всё равно установить».</li>
<li>Откройте «BONJOUR Мастер» и войдите по логину и паролю, которые выдал руководитель.</li>
</ol>
</section>
%QR%
</div>"""

_QR = """<figure class="card qr">
<div class="qr__code" role="img" aria-label="QR-код ссылки на скачивание приложения">%SVG%</div>
<figcaption>Наведите камеру телефона — скачивание начнётся сразу</figcaption>
</figure>"""


def _qr_svg(url: str) -> Optional[str]:
    """QR с прямой ссылкой на APK, готовым SVG для вставки в страницу.

    Нужен, когда страницу открывают на компьютере — например, руководитель
    показывает её мастерам на смене: навёл камеру, и файл уже качается.

    Без библиотеки страница работает без кода, а не падает: деплой не ставит
    зависимости из requirements.txt, и на новой машине segno может не
    оказаться. make_qr, а не make: на короткой строке make выбрал бы Micro QR,
    а его камеры телефонов не читают.
    """
    try:
        import segno
    except ImportError:
        return None
    return segno.make_qr(url, error="m").svg_inline(
        scale=8, border=2, dark="#0a0a0a", light="#ffffff", omitsize=True,
    )


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
            svg = _qr_svg(master_app_service.apk_url())
            body = (
                _AVAILABLE.replace("%APK%", master_app_service.PUBLIC_APK_NAME)
                .replace("%META%", html.escape(meta))
                .replace("%QR%", _QR.replace("%SVG%", svg) if svg else "")
            )
        return HTMLResponse(_PAGE.replace("%BODY%", body))

    @router.get("/info")
    async def get_info() -> dict:
        return master_app_service.info()

    @router.get("/logins")
    async def list_master_logins() -> list[dict]:
        """Логины мастеров для выпадающего списка на входе в приложение.

        Публично, как и всё здесь: список нужен до входа. Цена принята
        сознательно — кто знает адрес, увидит имена мастеров, но без пароля
        это ничего не даёт. Отдаются только логин и имя.
        """
        from app.services.access_control_service import get_access_control_service

        return get_access_control_service().master_login_options()

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

    @router.get("/archive/{version_name}.apk")
    async def download_archived_apk(version_name: str) -> FileResponse:
        """Сборка конкретной версии — для проверки обновления со старой."""
        path = master_app_service.archived_apk_path(version_name)
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
            return master_app_service.save_apk(await file.read())
        except master_app_service.MasterAppValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return router
