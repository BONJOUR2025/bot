from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.schemas.password import (
    PasswordEntry,
    PasswordEntryCreate,
    PasswordEntryUpdate,
    PasswordCategory,
    PasswordCategoryCreate,
    PasswordCategoryUpdate,
    PasswordStats,
)
from app.services.password_service import PasswordService

from .dependencies import require_permission

PASSWORDS_PERMISSION = "passwords"


class GeneratePasswordRequest(BaseModel):
    length: int = 16
    use_uppercase: bool = True
    use_lowercase: bool = True
    use_digits: bool = True
    use_symbols: bool = True
    exclude_ambiguous: bool = False


class GeneratePasswordResponse(BaseModel):
    password: str


class ReorderCategoriesRequest(BaseModel):
    order: List[int]


def create_password_router(service: PasswordService) -> APIRouter:
    router = APIRouter(
        prefix="/passwords",
        tags=["Passwords"],
        dependencies=[Depends(require_permission(PASSWORDS_PERMISSION))],
    )

    # ==================== ENTRIES ====================

    @router.get("/entries", response_model=List[PasswordEntry])
    async def list_entries(
        category: Optional[str] = Query(None, description="Filter by category name"),
        search: Optional[str] = Query(None, description="Search in title, username, url, notes"),
        favorites_only: bool = Query(False, description="Show only favorites"),
    ):
        """List all password entries with optional filters."""
        return await service.list_entries(
            category=category,
            search=search,
            favorites_only=favorites_only,
        )

    @router.get("/entries/{entry_id}", response_model=PasswordEntry)
    async def get_entry(entry_id: int):
        """Get a single password entry."""
        entry = await service.get_entry(entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        return entry

    @router.post("/entries", response_model=PasswordEntry)
    async def create_entry(data: PasswordEntryCreate):
        """Create a new password entry."""
        return await service.create_entry(data)

    @router.put("/entries/{entry_id}", response_model=PasswordEntry)
    async def update_entry(entry_id: int, data: PasswordEntryUpdate):
        """Update an existing password entry."""
        entry = await service.update_entry(entry_id, data)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        return entry

    @router.delete("/entries/{entry_id}")
    async def delete_entry(entry_id: int):
        """Delete a password entry."""
        deleted = await service.delete_entry(entry_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Entry not found")
        return {"status": "deleted"}

    @router.post("/entries/{entry_id}/toggle-favorite", response_model=PasswordEntry)
    async def toggle_favorite(entry_id: int):
        """Toggle favorite status of an entry."""
        entry = await service.toggle_favorite(entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        return entry

    # ==================== CATEGORIES ====================

    @router.get("/categories", response_model=List[PasswordCategory])
    async def list_categories():
        """List all categories."""
        return await service.list_categories()

    @router.get("/categories/{category_id}", response_model=PasswordCategory)
    async def get_category(category_id: int):
        """Get a single category."""
        cat = await service.get_category(category_id)
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        return cat

    @router.post("/categories", response_model=PasswordCategory)
    async def create_category(data: PasswordCategoryCreate):
        """Create a new category."""
        return await service.create_category(data)

    @router.put("/categories/{category_id}", response_model=PasswordCategory)
    async def update_category(category_id: int, data: PasswordCategoryUpdate):
        """Update a category."""
        cat = await service.update_category(category_id, data)
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        return cat

    @router.delete("/categories/{category_id}")
    async def delete_category(
        category_id: int,
        delete_entries: bool = Query(False, description="Also delete entries in this category"),
    ):
        """Delete a category. Optionally delete all entries in it."""
        deleted = await service.delete_category(category_id, delete_entries)
        if not deleted:
            raise HTTPException(status_code=404, detail="Category not found")
        return {"status": "deleted"}

    @router.post("/categories/reorder")
    async def reorder_categories(data: ReorderCategoriesRequest):
        """Reorder categories by providing list of category IDs."""
        await service.reorder_categories(data.order)
        return {"status": "ok"}

    # ==================== STATS & UTILS ====================

    @router.get("/stats", response_model=PasswordStats)
    async def get_stats():
        """Get vault statistics."""
        return await service.get_stats()

    @router.post("/generate", response_model=GeneratePasswordResponse)
    async def generate_password(data: GeneratePasswordRequest):
        """Generate a random password."""
        password = PasswordService.generate_password(
            length=data.length,
            use_uppercase=data.use_uppercase,
            use_lowercase=data.use_lowercase,
            use_digits=data.use_digits,
            use_symbols=data.use_symbols,
            exclude_ambiguous=data.exclude_ambiguous,
        )
        return GeneratePasswordResponse(password=password)

    return router
