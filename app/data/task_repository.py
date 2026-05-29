import json
import os
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any

from app.utils.logger import log


DEFAULT_TASKS_FILE = "tasks.json"


class TaskRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or DEFAULT_TASKS_FILE
        log(f"📂 Loading tasks from {self._file}")
        self._data: List[Dict[str, Any]] = self._load()
        log(f"✅ Loaded tasks: {len(self._data)}")
        self._counter = 0
        for item in self._data:
            raw_id = item.get("id")
            if raw_id is not None and str(raw_id).isdigit():
                self._counter = max(self._counter, int(raw_id))

    def reload(self) -> None:
        """Reload tasks from disk."""
        self._data = self._load()
        self._counter = 0
        for item in self._data:
            raw_id = item.get("id")
            if raw_id is not None and str(raw_id).isdigit():
                self._counter = max(self._counter, int(raw_id))

    def _load(self) -> List[Dict[str, Any]]:
        if not self._file or not os.path.exists(self._file):
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for task in data:
                if "id" in task:
                    task["id"] = int(task["id"])
            return data
        except Exception as e:
            log(f"❌ Failed reading {self._file}: {e}")
            return []

    def _save(self) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _generate_id(self) -> int:
        self._counter += 1
        return self._counter

    def list(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        due_date: Optional[str] = None,
        due_from: Optional[str] = None,
        due_to: Optional[str] = None,
        include_done: bool = True,
    ) -> List[Dict[str, Any]]:
        """List tasks with optional filters."""
        self._data = self._load()  # always fresh from disk (two-process setup)
        result = []

        due_from_dt = date.fromisoformat(due_from) if due_from else None
        due_to_dt = date.fromisoformat(due_to) if due_to else None
        due_date_dt = date.fromisoformat(due_date) if due_date else None

        for item in self._data:
            if not include_done and item.get("status") == "done":
                continue
            if status and item.get("status") != status:
                continue
            if priority and item.get("priority") != priority:
                continue
            if category and item.get("category") != category:
                continue

            task_due = item.get("due_date")
            if task_due:
                try:
                    task_due_dt = date.fromisoformat(task_due)
                except (ValueError, TypeError):
                    task_due_dt = None
            else:
                task_due_dt = None

            if due_date_dt and task_due_dt != due_date_dt:
                continue
            if due_from_dt and task_due_dt and task_due_dt < due_from_dt:
                continue
            if due_to_dt and task_due_dt and task_due_dt > due_to_dt:
                continue

            result.append(item)

        # Sort by due_date (nulls last), then by priority
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

        def sort_key(t):
            due = t.get("due_date") or "9999-12-31"
            prio = priority_order.get(t.get("priority", "medium"), 2)
            return (due, prio, t.get("created_at", ""))

        result.sort(key=sort_key)
        return result

    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get a single task by ID."""
        for item in self._data:
            if item.get("id") == task_id:
                return item
        return None

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new task."""
        self._data = self._load()  # sync with disk before mutating
        self._counter = max((int(t["id"]) for t in self._data if str(t.get("id", "")).isdigit()), default=0)
        data["id"] = self._generate_id()
        data["created_at"] = datetime.now().isoformat()
        data["updated_at"] = datetime.now().isoformat()
        if "status" not in data:
            data["status"] = "todo"
        if "priority" not in data:
            data["priority"] = "medium"
        if "tags" not in data:
            data["tags"] = []
        if "reminder_sent" not in data:
            data["reminder_sent"] = False
        self._data.append(data)
        self._save()
        return data

    def update(self, task_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing task."""
        self._data = self._load()  # sync with disk before mutating
        for item in self._data:
            if item.get("id") == task_id:
                # Track completion time
                if updates.get("status") == "done" and item.get("status") != "done":
                    updates["completed_at"] = datetime.now().isoformat()
                elif updates.get("status") and updates.get("status") != "done":
                    updates["completed_at"] = None

                updates["updated_at"] = datetime.now().isoformat()
                item.update({k: v for k, v in updates.items() if v is not None})
                self._save()
                return item
        return None

    def delete(self, task_id: int) -> bool:
        """Delete a task."""
        self._data = self._load()  # sync with disk before mutating
        before = len(self._data)
        self._data = [t for t in self._data if t.get("id") != task_id]
        if len(self._data) != before:
            self._save()
            return True
        return False

    def delete_many(self, ids: List[int]) -> int:
        """Delete multiple tasks. Returns count of deleted."""
        self._data = self._load()  # sync with disk before mutating
        before = len(self._data)
        self._data = [t for t in self._data if t.get("id") not in ids]
        deleted = before - len(self._data)
        if deleted > 0:
            self._save()
        return deleted

    def get_stats(self) -> Dict[str, int]:
        """Get task statistics."""
        today = date.today()
        week_end = today + timedelta(days=7)

        stats = {
            "total": len(self._data),
            "todo": 0,
            "in_progress": 0,
            "done": 0,
            "overdue": 0,
            "due_today": 0,
            "due_this_week": 0,
        }

        for task in self._data:
            status = task.get("status", "todo")
            if status == "todo":
                stats["todo"] += 1
            elif status == "in_progress":
                stats["in_progress"] += 1
            elif status == "done":
                stats["done"] += 1

            # Check due dates for non-done tasks
            if status != "done":
                due_str = task.get("due_date")
                if due_str:
                    try:
                        due = date.fromisoformat(due_str)
                        if due < today:
                            stats["overdue"] += 1
                        elif due == today:
                            stats["due_today"] += 1
                        elif due <= week_end:
                            stats["due_this_week"] += 1
                    except (ValueError, TypeError):
                        pass

        return stats

    def get_categories(self) -> List[str]:
        """Get list of unique categories."""
        categories = set()
        for task in self._data:
            cat = task.get("category")
            if cat:
                categories.add(cat)
        return sorted(categories)

    def get_due_reminders(self) -> List[Dict[str, Any]]:
        """Get tasks that need reminders sent."""
        now = datetime.now()
        result = []

        for task in self._data:
            if task.get("reminder_sent") or task.get("status") == "done":
                continue

            reminder_minutes = task.get("reminder_minutes")
            if not reminder_minutes:
                continue

            due_date_str = task.get("due_date")
            due_time_str = task.get("due_time")
            if not due_date_str:
                continue

            try:
                due_date = date.fromisoformat(due_date_str)
                if due_time_str:
                    due_time = datetime.strptime(due_time_str, "%H:%M:%S").time()
                else:
                    due_time = datetime.strptime("09:00:00", "%H:%M:%S").time()

                due_datetime = datetime.combine(due_date, due_time)
                reminder_time = due_datetime - timedelta(minutes=reminder_minutes)

                if now >= reminder_time:
                    result.append(task)
            except (ValueError, TypeError):
                pass

        return result

    def mark_reminder_sent(self, task_id: int) -> None:
        """Mark a task's reminder as sent."""
        for task in self._data:
            if task.get("id") == task_id:
                task["reminder_sent"] = True
                self._save()
                break
