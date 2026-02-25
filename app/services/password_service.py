import secrets
import string
from typing import List, Optional

from app.schemas.password import (
    PasswordEntry,
    PasswordEntryCreate,
    PasswordEntryUpdate,
    PasswordCategory,
    PasswordCategoryCreate,
    PasswordCategoryUpdate,
    PasswordStats,
)
from app.data.password_repository import PasswordRepository


class PasswordService:
    def __init__(self, repo: Optional[PasswordRepository] = None) -> None:
        self._repo = repo or PasswordRepository()

    # ==================== ENTRIES ====================

    async def list_entries(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None,
        favorites_only: bool = False,
    ) -> List[PasswordEntry]:
        """List password entries with optional filters."""
        items = self._repo.list_entries(
            category=category,
            search=search,
            favorites_only=favorites_only,
        )
        return [PasswordEntry(**item) for item in items]

    async def get_entry(self, entry_id: int) -> Optional[PasswordEntry]:
        """Get a single entry by ID."""
        item = self._repo.get_entry(entry_id)
        if item:
            return PasswordEntry(**item)
        return None

    async def create_entry(self, data: PasswordEntryCreate) -> PasswordEntry:
        """Create a new password entry."""
        entry_dict = data.model_dump()
        created = self._repo.create_entry(entry_dict)
        return PasswordEntry(**created)

    async def update_entry(self, entry_id: int, data: PasswordEntryUpdate) -> Optional[PasswordEntry]:
        """Update an existing entry."""
        updates = data.model_dump(exclude_unset=True)
        updated = self._repo.update_entry(entry_id, updates)
        if updated:
            return PasswordEntry(**updated)
        return None

    async def delete_entry(self, entry_id: int) -> bool:
        """Delete an entry."""
        return self._repo.delete_entry(entry_id)

    async def toggle_favorite(self, entry_id: int) -> Optional[PasswordEntry]:
        """Toggle favorite status."""
        updated = self._repo.toggle_favorite(entry_id)
        if updated:
            return PasswordEntry(**updated)
        return None

    # ==================== CATEGORIES ====================

    async def list_categories(self) -> List[PasswordCategory]:
        """List all categories."""
        items = self._repo.list_categories()
        return [PasswordCategory(**item) for item in items]

    async def get_category(self, category_id: int) -> Optional[PasswordCategory]:
        """Get a single category by ID."""
        item = self._repo.get_category(category_id)
        if item:
            return PasswordCategory(**item)
        return None

    async def create_category(self, data: PasswordCategoryCreate) -> PasswordCategory:
        """Create a new category."""
        cat_dict = data.model_dump()
        created = self._repo.create_category(cat_dict)
        return PasswordCategory(**created)

    async def update_category(self, category_id: int, data: PasswordCategoryUpdate) -> Optional[PasswordCategory]:
        """Update a category."""
        updates = data.model_dump(exclude_unset=True)
        updated = self._repo.update_category(category_id, updates)
        if updated:
            return PasswordCategory(**updated)
        return None

    async def delete_category(self, category_id: int, delete_entries: bool = False) -> bool:
        """Delete a category."""
        return self._repo.delete_category(category_id, delete_entries)

    async def reorder_categories(self, order: List[int]) -> None:
        """Reorder categories."""
        self._repo.reorder_categories(order)

    # ==================== STATS & UTILS ====================

    async def get_stats(self) -> PasswordStats:
        """Get vault statistics."""
        stats = self._repo.get_stats()
        return PasswordStats(**stats)

    @staticmethod
    def generate_password(
        length: int = 16,
        use_uppercase: bool = True,
        use_lowercase: bool = True,
        use_digits: bool = True,
        use_symbols: bool = True,
        exclude_ambiguous: bool = False,
    ) -> str:
        """Generate a random password."""
        chars = ""

        if use_lowercase:
            chars += string.ascii_lowercase
        if use_uppercase:
            chars += string.ascii_uppercase
        if use_digits:
            chars += string.digits
        if use_symbols:
            chars += "!@#$%^&*()_+-=[]{}|;:,.<>?"

        if exclude_ambiguous:
            # Remove ambiguous characters
            ambiguous = "0O1lI"
            chars = "".join(c for c in chars if c not in ambiguous)

        if not chars:
            chars = string.ascii_letters + string.digits

        # Ensure at least one character from each selected category
        password = []
        if use_lowercase:
            pool = string.ascii_lowercase
            if exclude_ambiguous:
                pool = "".join(c for c in pool if c not in "l")
            password.append(secrets.choice(pool))
        if use_uppercase:
            pool = string.ascii_uppercase
            if exclude_ambiguous:
                pool = "".join(c for c in pool if c not in "OI")
            password.append(secrets.choice(pool))
        if use_digits:
            pool = string.digits
            if exclude_ambiguous:
                pool = "".join(c for c in pool if c not in "01")
            password.append(secrets.choice(pool))
        if use_symbols:
            password.append(secrets.choice("!@#$%^&*()_+-=[]{}|;:,.<>?"))

        # Fill the rest
        remaining = length - len(password)
        if remaining > 0:
            password.extend(secrets.choice(chars) for _ in range(remaining))

        # Shuffle
        secrets.SystemRandom().shuffle(password)
        return "".join(password)
