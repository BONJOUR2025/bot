from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    login: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthUser(BaseModel):
    id: str
    login: str
    role_id: Optional[str] = None
    role_name: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)
    bot_buttons: List[str] = Field(default_factory=list)
    display_name: Optional[str] = None
    allowed_employee_ids: Optional[List[str]] = None
    allowed_departments: Optional[List[str]] = None


class LoginResponse(BaseModel):
    token: str
    user: AuthUser


class RoleOut(BaseModel):
    id: str
    name: str
    permissions: List[str]
    bot_buttons: List[str]


class RoleCreate(BaseModel):
    id: Optional[str] = None
    name: str
    permissions: Optional[List[str]] = None
    bot_buttons: Optional[List[str]] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[List[str]] = None
    bot_buttons: Optional[List[str]] = None


class UserOut(BaseModel):
    id: str
    login: str
    role_id: Optional[str] = None
    role_name: Optional[str] = None
    permissions: Optional[List[str]] = None
    bot_buttons: Optional[List[str]] = None
    resolved_permissions: List[str] = Field(default_factory=list)
    resolved_bot_buttons: List[str] = Field(default_factory=list)
    resolved_bot_button_labels: List[str] = Field(default_factory=list)
    display_name: Optional[str] = None
    allowed_employee_ids: Optional[List[str]] = None
    allowed_departments: Optional[List[str]] = None
    resolved_employee_names: List[str] = Field(default_factory=list)
    resolved_departments: List[str] = Field(default_factory=list)


class UserCreate(BaseModel):
    id: Optional[str] = None
    login: str
    password: str
    role_id: Optional[str] = None
    permissions: Optional[List[str]] = None
    bot_buttons: Optional[List[str]] = None
    allowed_employee_ids: Optional[List[str]] = None
    allowed_departments: Optional[List[str]] = None


class UserUpdate(BaseModel):
    login: Optional[str] = None
    password: Optional[str] = None
    role_id: Optional[str] = None
    permissions: Optional[List[str]] = None
    bot_buttons: Optional[List[str]] = None
    allowed_employee_ids: Optional[List[str]] = None
    allowed_departments: Optional[List[str]] = None


class AccessConfigResponse(BaseModel):
    users: List[UserOut]
    roles: List[RoleOut]
    available_permissions: List[dict]
    available_bot_buttons: List[dict]
    available_employees: List[dict]
    available_departments: List[str]
