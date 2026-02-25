import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.utils.logger import log


DEFAULT_PASSWORDS_FILE = "passwords.json"


class PasswordRepository:
    """Repository for storing password entries and categories."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or DEFAULT_PASSWORDS_FILE
        log(f"📂 Loading passwords from {self._file}")
        self._data: Dict[str, Any] = self._load()
        self._ensure_structure()
        log(f"✅ Loaded passwords: {len(self._data.get('entries', []))}, categories: {len(self._data.get('categories', []))}")

    def _ensure_structure(self) -> None:
        """Ensure data has correct structure."""
        if "entries" not in self._data:
            self._data["entries"] = []
        if "categories" not in self._data:
            self._data["categories"] = []
        if "entry_counter" not in self._data:
            self._data["entry_counter"] = 0
        if "category_counter" not in self._data:
            self._data["category_counter"] = 0

        # Update counters based on existing data
        for entry in self._data["entries"]:
            if entry.get("id") and isinstance(entry["id"], int):
                self._data["entry_counter"] = max(self._data["entry_counter"], entry["id"])
        for cat in self._data["categories"]:
            if cat.get("id") and isinstance(cat["id"], int):
                self._data["category_counter"] = max(self._data["category_counter"], cat["id"])

    def reload(self) -> None:
        """Reload from disk."""
        self._data = self._load()
        self._ensure_structure()

    def _load(self) -> Dict[str, Any]:
        if not self._file or not os.path.exists(self._file):
            return {"entries": [], "categories": [], "entry_counter": 0, "category_counter": 0}
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {"entries": [], "categories": []}
        except Exception as e:
            log(f"❌ Failed reading {self._file}: {e}")
            return {"entries": [], "categories": [], "entry_counter": 0, "category_counter": 0}

    def _save(self) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ==================== ENTRIES ====================

    def _generate_entry_id(self) -> int:
        self._data["entry_counter"] += 1
        return self._data["entry_counter"]

    def list_entries(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None,
        favorites_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """List password entries with optional filters."""
        result = []
        search_lower = search.lower() if search else None

        for entry in self._data["entries"]:
            if category and entry.get("category") != category:
                continue
            if favorites_only and not entry.get("is_favorite"):
                continue
            if search_lower:
                title = (entry.get("title") or "").lower()
                username = (entry.get("username") or "").lower()
                url = (entry.get("url") or "").lower()
                notes = (entry.get("notes") or "").lower()
                if not any(search_lower in field for field in [title, username, url, notes]):
                    continue
            result.append(entry)

        # Sort: favorites first, then by title
        result.sort(key=lambda e: (not e.get("is_favorite", False), (e.get("title") or "").lower()))
        return result

    def get_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """Get a single entry by ID."""
        for entry in self._data["entries"]:
            if entry.get("id") == entry_id:
                return entry
        return None

    def create_entry(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new password entry."""
        data["id"] = self._generate_entry_id()
        data["created_at"] = datetime.now().isoformat()
        data["updated_at"] = datetime.now().isoformat()
        if "is_favorite" not in data:
            data["is_favorite"] = False
        self._data["entries"].append(data)
        self._save()
        return data

    def update_entry(self, entry_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing entry."""
        for entry in self._data["entries"]:
            if entry.get("id") == entry_id:
                updates["updated_at"] = datetime.now().isoformat()
                entry.update({k: v for k, v in updates.items() if v is not None})
                self._save()
                return entry
        return None

    def delete_entry(self, entry_id: int) -> bool:
        """Delete an entry."""
        before = len(self._data["entries"])
        self._data["entries"] = [e for e in self._data["entries"] if e.get("id") != entry_id]
        if len(self._data["entries"]) != before:
            self._save()
            return True
        return False

    def delete_entries_by_category(self, category: str) -> int:
        """Delete all entries in a category. Returns count of deleted."""
        before = len(self._data["entries"])
        self._data["entries"] = [e for e in self._data["entries"] if e.get("category") != category]
        deleted = before - len(self._data["entries"])
        if deleted > 0:
            self._save()
        return deleted

    def toggle_favorite(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """Toggle favorite status."""
        for entry in self._data["entries"]:
            if entry.get("id") == entry_id:
                entry["is_favorite"] = not entry.get("is_favorite", False)
                entry["updated_at"] = datetime.now().isoformat()
                self._save()
                return entry
        return None

    # ==================== CATEGORIES ====================

    def _generate_category_id(self) -> int:
        self._data["category_counter"] += 1
        return self._data["category_counter"]

    def list_categories(self) -> List[Dict[str, Any]]:
        """List all categories sorted by order."""
        cats = list(self._data["categories"])
        cats.sort(key=lambda c: (c.get("order", 0), c.get("name", "")))
        return cats

    def get_category(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Get a single category by ID."""
        for cat in self._data["categories"]:
            if cat.get("id") == category_id:
                return cat
        return None

    def get_category_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a category by name."""
        for cat in self._data["categories"]:
            if cat.get("name") == name:
                return cat
        return None

    def create_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new category."""
        data["id"] = self._generate_category_id()
        if "order" not in data:
            data["order"] = len(self._data["categories"])
        self._data["categories"].append(data)
        self._save()
        return data

    def update_category(self, category_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a category."""
        for cat in self._data["categories"]:
            if cat.get("id") == category_id:
                old_name = cat.get("name")
                cat.update({k: v for k, v in updates.items() if v is not None})
                # If name changed, update entries with this category
                if "name" in updates and updates["name"] != old_name:
                    for entry in self._data["entries"]:
                        if entry.get("category") == old_name:
                            entry["category"] = updates["name"]
                self._save()
                return cat
        return None

    def delete_category(self, category_id: int, delete_entries: bool = False) -> bool:
        """Delete a category. Optionally delete all entries in it."""
        cat = self.get_category(category_id)
        if not cat:
            return False

        cat_name = cat.get("name")

        if delete_entries:
            self._data["entries"] = [e for e in self._data["entries"] if e.get("category") != cat_name]
        else:
            # Move entries to uncategorized
            for entry in self._data["entries"]:
                if entry.get("category") == cat_name:
                    entry["category"] = None

        self._data["categories"] = [c for c in self._data["categories"] if c.get("id") != category_id]
        self._save()
        return True

    def reorder_categories(self, order: List[int]) -> None:
        """Reorder categories by list of IDs."""
        for idx, cat_id in enumerate(order):
            for cat in self._data["categories"]:
                if cat.get("id") == cat_id:
                    cat["order"] = idx
                    break
        self._save()

    # ==================== STATS ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get vault statistics."""
        entries = self._data["entries"]
        categories = self._data["categories"]

        entries_by_category = {}
        for entry in entries:
            cat = entry.get("category") or "Без категории"
            entries_by_category[cat] = entries_by_category.get(cat, 0) + 1

        return {
            "total_entries": len(entries),
            "total_categories": len(categories),
            "favorites_count": sum(1 for e in entries if e.get("is_favorite")),
            "entries_by_category": entries_by_category,
        }
