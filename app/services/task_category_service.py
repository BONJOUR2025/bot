from typing import List, Optional

from app.schemas.task_category import TaskCategory, TaskCategoryCreate, TaskCategoryUpdate
from app.data.task_category_repository import TaskCategoryRepository


class TaskCategoryService:
    def __init__(self, repo: Optional[TaskCategoryRepository] = None) -> None:
        self._repo = repo or TaskCategoryRepository()

    async def list_categories(self) -> List[TaskCategory]:
        return [TaskCategory(**c) for c in self._repo.list()]

    async def get_category(self, cat_id: int) -> Optional[TaskCategory]:
        c = self._repo.get(cat_id)
        return TaskCategory(**c) if c else None

    async def create_category(self, data: TaskCategoryCreate) -> TaskCategory:
        created = self._repo.create(data.model_dump())
        return TaskCategory(**created)

    async def update_category(self, cat_id: int, data: TaskCategoryUpdate) -> Optional[TaskCategory]:
        updated = self._repo.update(cat_id, data.model_dump(exclude_unset=True))
        return TaskCategory(**updated) if updated else None

    async def delete_category(self, cat_id: int) -> bool:
        return self._repo.delete(cat_id)
