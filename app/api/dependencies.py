from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.services.access_control_service import (
    ResolvedUser,
    get_access_control_service,
)


async def get_current_user(authorization: str = Header(default=None)) -> ResolvedUser:
    service = get_access_control_service()
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_token")
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    try:
        return service.verify_token(token)
    except ValueError as exc:  # pragma: no cover - mapped to HTTP error
        detail = str(exc) or "invalid_token"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def require_permission(permission: str):
    async def dependency(user: ResolvedUser = Depends(get_current_user)) -> ResolvedUser:
        if permission not in user.permissions and "*" not in user.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return user

    return dependency
