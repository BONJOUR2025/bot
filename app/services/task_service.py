from datetime import datetime, date
from typing import List, Optional

from app.schemas.task import Task, TaskCreate, TaskUpdate, TaskStats
from app.data.task_repository import TaskRepository


class TaskService:
    def __init__(self, repo: Optional[TaskRepository] = None) -> None:
        self._repo = repo or TaskRepository()

    async def list_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        due_date: Optional[str] = None,
        due_from: Optional[str] = None,
        due_to: Optional[str] = None,
        include_done: bool = True,
    ) -> List[Task]:
        """List tasks with optional filters."""
        items = self._repo.list(
            status=status,
            priority=priority,
            category=category,
            due_date=due_date,
            due_from=due_from,
            due_to=due_to,
            include_done=include_done,
        )
        return [Task(**item) for item in items]

    async def get_task(self, task_id: int) -> Optional[Task]:
        """Get a single task by ID."""
        item = self._repo.get(task_id)
        if item:
            return Task(**item)
        return None

    async def create_task(self, data: TaskCreate, created_by: Optional[str] = None) -> Task:
        """Create a new task."""
        task_dict = data.model_dump()

        # Convert date/time to ISO format strings
        if task_dict.get("due_date"):
            task_dict["due_date"] = task_dict["due_date"].isoformat()
        if task_dict.get("due_time"):
            task_dict["due_time"] = task_dict["due_time"].isoformat()

        if created_by:
            task_dict["created_by"] = created_by

        created = self._repo.create(task_dict)
        return Task(**created)

    async def update_task(self, task_id: int, data: TaskUpdate) -> Optional[Task]:
        """Update an existing task."""
        updates = data.model_dump(exclude_unset=True)

        # Convert date/time to ISO format strings
        if "due_date" in updates and updates["due_date"]:
            updates["due_date"] = updates["due_date"].isoformat()
        if "due_time" in updates and updates["due_time"]:
            updates["due_time"] = updates["due_time"].isoformat()

        updated = self._repo.update(task_id, updates)
        if updated:
            return Task(**updated)
        return None

    async def delete_task(self, task_id: int) -> bool:
        """Delete a task."""
        return self._repo.delete(task_id)

    async def delete_many(self, ids: List[int]) -> int:
        """Delete multiple tasks."""
        return self._repo.delete_many(ids)

    async def get_stats(self) -> TaskStats:
        """Get task statistics."""
        stats = self._repo.get_stats()
        return TaskStats(**stats)

    async def get_categories(self) -> List[str]:
        """Get list of unique categories."""
        return self._repo.get_categories()

    async def get_today_tasks(self) -> List[Task]:
        """Get tasks due today."""
        today = date.today().isoformat()
        items = self._repo.list(due_date=today, include_done=False)
        return [Task(**item) for item in items]

    async def get_overdue_tasks(self) -> List[Task]:
        """Get overdue tasks."""
        today = date.today()
        all_tasks = self._repo.list(include_done=False)
        overdue = []
        for item in all_tasks:
            due_str = item.get("due_date")
            if due_str:
                try:
                    due = date.fromisoformat(due_str)
                    if due < today:
                        overdue.append(Task(**item))
                except (ValueError, TypeError):
                    pass
        return overdue

    async def complete_task(self, task_id: int) -> Optional[Task]:
        """Mark a task as done."""
        return await self.update_task(task_id, TaskUpdate(status="done"))

    async def reopen_task(self, task_id: int) -> Optional[Task]:
        """Reopen a completed task."""
        return await self.update_task(task_id, TaskUpdate(status="todo"))
