"""Comprehensive tests for API dependencies."""

import json
import asyncio
from dataclasses import dataclass
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

from tests.conftest import run_async


@dataclass
class FakeResolvedUser:
    id: str = "admin"
    login: str = "admin"
    role_id: str = "owner"
    role_name: str = "Owner"
    permissions: list = None
    bot_buttons: list = None
    display_name: str = "Admin"
    allowed_employee_ids: list = None
    allowed_departments: list = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = ["*"]
        if self.bot_buttons is None:
            self.bot_buttons = ["*"]


class TestGetCurrentUser:
    def test_missing_token_raises_401(self):
        from app.api.dependencies import get_current_user

        async def _run():
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(authorization=None, access_token=None)
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "missing_token"
        run_async(_run())

    def test_bearer_token(self):
        from app.api.dependencies import get_current_user

        fake_user = FakeResolvedUser()
        mock_service = MagicMock()
        mock_service.verify_token.return_value = fake_user

        async def _run():
            with patch("app.api.dependencies.get_access_control_service",
                       return_value=mock_service):
                result = await get_current_user(
                    authorization="Bearer test_token", access_token=None
                )
                assert result.id == "admin"
                mock_service.verify_token.assert_called_once_with("test_token")
        run_async(_run())

    def test_raw_token(self):
        from app.api.dependencies import get_current_user

        fake_user = FakeResolvedUser()
        mock_service = MagicMock()
        mock_service.verify_token.return_value = fake_user

        async def _run():
            with patch("app.api.dependencies.get_access_control_service",
                       return_value=mock_service):
                result = await get_current_user(
                    authorization="raw_token", access_token=None
                )
                mock_service.verify_token.assert_called_once_with("raw_token")
        run_async(_run())

    def test_cookie_token(self):
        from app.api.dependencies import get_current_user

        fake_user = FakeResolvedUser()
        mock_service = MagicMock()
        mock_service.verify_token.return_value = fake_user

        async def _run():
            with patch("app.api.dependencies.get_access_control_service",
                       return_value=mock_service):
                result = await get_current_user(
                    authorization=None, access_token="cookie_token"
                )
                mock_service.verify_token.assert_called_once_with("cookie_token")
        run_async(_run())

    def test_invalid_token_raises_401(self):
        from app.api.dependencies import get_current_user

        mock_service = MagicMock()
        mock_service.verify_token.side_effect = ValueError("invalid_token")

        async def _run():
            with patch("app.api.dependencies.get_access_control_service",
                       return_value=mock_service):
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(
                        authorization="Bearer bad", access_token=None
                    )
                assert exc_info.value.status_code == 401
        run_async(_run())


class TestRequirePermission:
    def test_user_with_permission_passes(self):
        from app.api.dependencies import require_permission

        dep = require_permission("employees")
        fake_user = FakeResolvedUser(permissions=["employees", "payouts"])

        async def _run():
            result = await dep(user=fake_user)
            assert result.id == "admin"
        run_async(_run())

    def test_user_with_wildcard_passes(self):
        from app.api.dependencies import require_permission

        dep = require_permission("anything")
        fake_user = FakeResolvedUser(permissions=["*"])

        async def _run():
            result = await dep(user=fake_user)
            assert result is not None
        run_async(_run())

    def test_user_without_permission_raises_403(self):
        from app.api.dependencies import require_permission

        dep = require_permission("admin_only")
        fake_user = FakeResolvedUser(permissions=["employees"])

        async def _run():
            with pytest.raises(HTTPException) as exc_info:
                await dep(user=fake_user)
            assert exc_info.value.status_code == 403
        run_async(_run())

    def test_empty_permissions_raises_403(self):
        from app.api.dependencies import require_permission

        dep = require_permission("anything")
        fake_user = FakeResolvedUser(permissions=[])

        async def _run():
            with pytest.raises(HTTPException) as exc_info:
                await dep(user=fake_user)
            assert exc_info.value.status_code == 403
        run_async(_run())
