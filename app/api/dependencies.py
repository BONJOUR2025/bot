from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from app.services.access_control_service import (
    ResolvedUser,
    get_access_control_service,
)


def _log_rejected_token(token: str, reason: str, request: Request) -> None:
    """Чей вход отклонён и почему — в connections.log. Без этого «мастера
    выкидывает на ввод пароля» нечем было проверить: в журнале сервера были
    только безымянные 401. id берём из токена без проверки подписи — для
    журнала этого достаточно, доступа это не даёт."""
    try:
        import base64

        from app.utils.logger import log_connection

        user_id = base64.urlsafe_b64decode(token.encode()).decode("utf-8", "replace").split(":", 1)[0][:40]
        ua = request.headers.get("user-agent", "")
        where = "приложение мастера" if "BonjourMasterApp" in ua else ("iOS" if "iPhone" in ua else "браузер")
        log_connection(f"Вход отклонён: пользователь {user_id}, причина {reason}, {where}")
    except Exception:
        pass


async def get_current_user(
    request: Request,
    authorization: str = Header(default=None),
    access_token: str | None = Cookie(default=None),
) -> ResolvedUser:
    service = get_access_control_service()
    token = None
    if authorization:
        token = authorization
        if authorization.startswith("Bearer "):
            token = authorization.split(" ", 1)[1]
    elif access_token:
        token = access_token
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_token")
    try:
        user = service.verify_token(token)
    except ValueError as exc:  # pragma: no cover - mapped to HTTP error
        detail = str(exc) or "invalid_token"
        _log_rejected_token(token, detail, request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
    request.state.user = user
    return user


def require_permission(permission: str):
    async def dependency(user: ResolvedUser = Depends(get_current_user)) -> ResolvedUser:
        if permission not in user.permissions and "*" not in user.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return user

    return dependency


def require_any_permission(*permissions: str):
    """Пропускает, если есть хотя бы одно из прав.

    Для адресов, которыми пользуются несколько разделов панели: например,
    статус amoCRM читают и «Настройки», и расчёт ЗП менеджеров.
    """

    async def dependency(user: ResolvedUser = Depends(get_current_user)) -> ResolvedUser:
        if "*" in user.permissions or any(p in user.permissions for p in permissions):
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    return dependency
