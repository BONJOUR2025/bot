from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.task import Task, TaskCreate, TaskUpdate, TaskStats
from app.schemas.task_category import TaskCategory, TaskCategoryCreate, TaskCategoryUpdate
from app.services.task_service import TaskService
from app.services.task_category_service import TaskCategoryService

from .dependencies import require_permission


def create_task_router(task_service: TaskService) -> APIRouter:
    router = APIRouter(
        prefix="/tasks",
        tags=["Tasks"],
        dependencies=[Depends(require_permission("tasks"))],
    )
    cat_service = TaskCategoryService()

    # ── Categories ─────────────────────────────────────────────────
    @router.get("/categories", response_model=List[TaskCategory])
    async def list_categories():
        """Get all task category definitions."""
        return await cat_service.list_categories()

    @router.post("/categories", response_model=TaskCategory)
    async def create_category(data: TaskCategoryCreate):
        """Create a new task category."""
        return await cat_service.create_category(data)

    @router.put("/categories/{cat_id}", response_model=TaskCategory)
    async def update_category(cat_id: int, data: TaskCategoryUpdate):
        """Update a task category."""
        cat = await cat_service.update_category(cat_id, data)
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        return cat

    @router.delete("/categories/{cat_id}")
    async def delete_category(cat_id: int):
        """Delete a task category."""
        deleted = await cat_service.delete_category(cat_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Category not found")
        return {"status": "deleted"}

    # ── Tasks ──────────────────────────────────────────────────────
    @router.get("/", response_model=List[Task])
    async def list_tasks(
        status: Optional[str] = Query(None),
        priority: Optional[str] = Query(None),
        category: Optional[str] = Query(None),
        due_date: Optional[str] = Query(None),
        due_from: Optional[str] = Query(None),
        due_to: Optional[str] = Query(None),
        include_done: bool = Query(True),
        candidate_id: Optional[int] = Query(None),
    ):
        return await task_service.list_tasks(
            status=status,
            priority=priority,
            category=category,
            due_date=due_date,
            due_from=due_from,
            due_to=due_to,
            include_done=include_done,
            candidate_id=candidate_id,
        )

    @router.get("/stats", response_model=TaskStats)
    async def get_stats():
        return await task_service.get_stats()

    @router.get("/today", response_model=List[Task])
    async def get_today_tasks():
        return await task_service.get_today_tasks()

    @router.get("/overdue", response_model=List[Task])
    async def get_overdue_tasks():
        return await task_service.get_overdue_tasks()

    @router.get("/{task_id}", response_model=Task)
    async def get_task(task_id: int):
        task = await task_service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @router.post("/", response_model=Task)
    async def create_task(data: TaskCreate):
        return await task_service.create_task(data)

    @router.put("/{task_id}", response_model=Task)
    async def update_task(task_id: int, data: TaskUpdate):
        task = await task_service.update_task(task_id, data)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @router.delete("/{task_id}")
    async def delete_task(task_id: int):
        deleted = await task_service.delete_task(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"status": "deleted"}

    @router.delete("/")
    async def delete_many(ids: List[int] = Query(...)):
        deleted_count = await task_service.delete_many(ids)
        return {"deleted": deleted_count}

    @router.post("/{task_id}/complete", response_model=Task)
    async def complete_task(task_id: int):
        task = await task_service.complete_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @router.post("/{task_id}/reopen", response_model=Task)
    async def reopen_task(task_id: int):
        task = await task_service.reopen_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    return router
