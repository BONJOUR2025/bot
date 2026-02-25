from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class PasswordEntry(BaseModel):
    """Password entry response model."""
    id: Optional[int] = None
    title: str
    username: Optional[str] = None
    password: str
    url: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    is_favorite: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PasswordEntryCreate(BaseModel):
    """Schema for creating a password entry."""
    title: str = Field(..., min_length=1, max_length=200)
    username: Optional[str] = Field(None, max_length=200)
    password: str = Field(..., min_length=1, max_length=500)
    url: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=2000)
    is_favorite: bool = False


class PasswordEntryUpdate(BaseModel):
    """Schema for updating a password entry."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    username: Optional[str] = Field(None, max_length=200)
    password: Optional[str] = Field(None, max_length=500)
    url: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)
    is_favorite: Optional[bool] = None


class PasswordCategory(BaseModel):
    """Password category model."""
    id: Optional[int] = None
    name: str
    icon: Optional[str] = None  # emoji or icon name
    color: Optional[str] = None  # hex color
    order: int = 0


class PasswordCategoryCreate(BaseModel):
    """Schema for creating a category."""
    name: str = Field(..., min_length=1, max_length=100)
    icon: Optional[str] = Field(None, max_length=10)
    color: Optional[str] = Field(None, max_length=20)


class PasswordCategoryUpdate(BaseModel):
    """Schema for updating a category."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    icon: Optional[str] = Field(None, max_length=10)
    color: Optional[str] = Field(None, max_length=20)
    order: Optional[int] = None


class PasswordStats(BaseModel):
    """Password vault statistics."""
    total_entries: int = 0
    total_categories: int = 0
    favorites_count: int = 0
    entries_by_category: dict = {}
