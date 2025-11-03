from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.auth import (
    AccessConfigResponse,
    AuthUser,
    LoginRequest,
    LoginResponse,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services.access_control_service import (
    AccessControlService,
    ResolvedUser,
    get_access_control_service,
)

from .dependencies import get_current_user, require_permission


ERROR_MAP = {
    "role_exists": (status.HTTP_400_BAD_REQUEST, "role_exists"),
    "role_not_found": (status.HTTP_404_NOT_FOUND, "role_not_found"),
    "role_in_use": (status.HTTP_400_BAD_REQUEST, "role_in_use"),
    "user_exists": (status.HTTP_400_BAD_REQUEST, "user_exists"),
    "login_exists": (status.HTTP_400_BAD_REQUEST, "login_exists"),
    "user_not_found": (status.HTTP_404_NOT_FOUND, "user_not_found"),
    "login_password_required": (status.HTTP_400_BAD_REQUEST, "login_password_required"),
}


def _to_auth_user(resolved: ResolvedUser) -> AuthUser:
    return AuthUser(
        id=resolved.id,
        login=resolved.login,
        role_id=resolved.role_id,
        role_name=resolved.role_name,
        permissions=resolved.permissions,
        bot_buttons=resolved.bot_buttons,
        display_name=resolved.display_name,
    )


def _handle_error(exc: ValueError) -> None:
    code = str(exc)
    status_code, detail = ERROR_MAP.get(code, (status.HTTP_400_BAD_REQUEST, code))
    raise HTTPException(status_code=status_code, detail=detail)


def create_auth_router(service: AccessControlService | None = None) -> APIRouter:
    service = service or get_access_control_service()
    router = APIRouter(prefix="/auth", tags=["Auth"])

    @router.post("/login", response_model=LoginResponse)
    async def login(payload: LoginRequest) -> LoginResponse:
        resolved = service.authenticate(payload.login, payload.password)
        if not resolved:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
        token = service.issue_token(resolved.id)
        return LoginResponse(token=token, user=_to_auth_user(resolved))

    @router.get("/me", response_model=AuthUser)
    async def me(current: ResolvedUser = Depends(get_current_user)) -> AuthUser:
        return _to_auth_user(current)

    @router.post("/logout")
    async def logout() -> dict[str, str]:
        # Stateless tokens are cleared client-side
        return {"status": "ok"}

    @router.get("/access", response_model=AccessConfigResponse)
    async def access_config(
        user: ResolvedUser = Depends(require_permission("access")),
    ) -> AccessConfigResponse:
        users = [UserOut(**item) for item in service.list_users()]
        roles = [RoleOut(**item) for item in service.list_roles()]
        return AccessConfigResponse(
            users=users,
            roles=roles,
            available_permissions=service.available_permissions(),
            available_bot_buttons=service.available_bot_buttons(),
        )

    @router.post("/roles", response_model=RoleOut)
    async def create_role(
        payload: RoleCreate,
        user: ResolvedUser = Depends(require_permission("access")),
    ) -> RoleOut:
        try:
            role = service.create_role(payload.dict())
        except ValueError as exc:
            _handle_error(exc)
        return RoleOut(**role)

    @router.patch("/roles/{role_id}", response_model=RoleOut)
    async def update_role(
        role_id: str,
        payload: RoleUpdate,
        user: ResolvedUser = Depends(require_permission("access")),
    ) -> RoleOut:
        try:
            role = service.update_role(role_id, payload.dict(exclude_unset=True))
        except ValueError as exc:
            _handle_error(exc)
        return RoleOut(**role)

    @router.delete("/roles/{role_id}")
    async def delete_role(
        role_id: str,
        user: ResolvedUser = Depends(require_permission("access")),
    ) -> dict[str, str]:
        try:
            service.delete_role(role_id)
        except ValueError as exc:
            _handle_error(exc)
        return {"status": "deleted"}

    @router.post("/users", response_model=UserOut)
    async def create_user(
        payload: UserCreate,
        user: ResolvedUser = Depends(require_permission("access")),
    ) -> UserOut:
        try:
            record = service.create_user(payload.dict())
        except ValueError as exc:
            _handle_error(exc)
        resolved = service.resolve_user(record.get("id"))
        if not resolved:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="user_resolution_failed")
        return UserOut(**{
            "id": resolved.id,
            "login": resolved.login,
            "role_id": resolved.role_id,
            "role_name": resolved.role_name,
            "permissions": record.get("permissions"),
            "bot_buttons": record.get("bot_buttons"),
            "resolved_permissions": resolved.permissions,
            "resolved_bot_buttons": resolved.bot_buttons,
            "resolved_bot_button_labels": service.button_labels(resolved.bot_buttons),
            "display_name": resolved.display_name,
        })

    @router.patch("/users/{user_id}", response_model=UserOut)
    async def update_user(
        user_id: str,
        payload: UserUpdate,
        user: ResolvedUser = Depends(require_permission("access")),
    ) -> UserOut:
        try:
            record = service.update_user(user_id, payload.dict(exclude_unset=True))
        except ValueError as exc:
            _handle_error(exc)
        resolved = service.resolve_user(user_id)
        if not resolved:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="user_resolution_failed")
        return UserOut(**{
            "id": resolved.id,
            "login": resolved.login,
            "role_id": resolved.role_id,
            "role_name": resolved.role_name,
            "permissions": record.get("permissions"),
            "bot_buttons": record.get("bot_buttons"),
            "resolved_permissions": resolved.permissions,
            "resolved_bot_buttons": resolved.bot_buttons,
            "resolved_bot_button_labels": service.button_labels(resolved.bot_buttons),
            "display_name": resolved.display_name,
        })

    @router.delete("/users/{user_id}")
    async def delete_user(
        user_id: str,
        user: ResolvedUser = Depends(require_permission("access")),
    ) -> dict[str, str]:
        service.delete_user(user_id)
        return {"status": "deleted"}

    return router
