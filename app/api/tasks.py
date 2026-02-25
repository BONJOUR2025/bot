from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.task import Task, TaskCreate, TaskUpdate, TaskStats
from app.services.task_service import TaskService


def create_task_router(service: TaskService) -> APIRouter:
    router = APIRouter(prefix="/tasks", tags=["Tasks"])

    @router.get("/", response_model=List[Task])
    async def list_tasks(
        status: Optional[str] = Query(None, description="Filter by status"),
        priority: Optional[str] = Query(None, description="Filter by priority"),
        category: Optional[str] = Query(None, description="Filter by category"),
        due_date: Optional[str] = Query(None, description="Filter by exact due date (YYYY-MM-DD)"),
        due_from: Optional[str] = Query(None, description="Filter tasks due from date"),
        due_to: Optional[str] = Query(None, description="Filter tasks due until date"),
        include_done: bool = Query(True, description="Include completed tasks"),
    ):
        """List all tasks with optional filters."""
        return await service.list_tasks(
            status=status,
            priority=priority,
            category=category,
            due_date=due_date,
            due_from=due_from,
            due_to=due_to,
            include_done=include_done,
        )

    @router.get("/stats", response_model=TaskStats)
    async def get_stats():
        """Get task statistics for dashboard."""
        return await service.get_stats()

    @router.get("/categories", response_model=List[str])
    async def get_categories():
        """Get list of unique task categories."""
        return await service.get_categories()

    @router.get("/today", response_model=List[Task])
    async def get_today_tasks():
        """Get tasks due today."""
        return await service.get_today_tasks()

    @router.get("/overdue", response_model=List[Task])
    async def get_overdue_tasks():
        """Get overdue tasks."""
        return await service.get_overdue_tasks()

    @router.get("/{task_id}", response_model=Task)
    async def get_task(task_id: int):
        """Get a single task by ID."""
        task = await service.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @router.post("/", response_model=Task)
    async def create_task(data: TaskCreate):
        """Create a new task."""
        return await service.create_task(data)

    @router.put("/{task_id}", response_model=Task)
    async def update_task(task_id: int, data: TaskUpdate):
        """Update an existing task."""
        task = await service.update_task(task_id, data)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @router.delete("/{task_id}")
    async def delete_task(task_id: int):
        """Delete a task."""
        deleted = await service.delete_task(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"status": "deleted"}

    @router.delete("/")
    async def delete_many(ids: List[int] = Query(..., description="Task IDs to delete")):
        """Delete multiple tasks."""
        deleted_count = await service.delete_many(ids)
        return {"deleted": deleted_count}

    @router.post("/{task_id}/complete", response_model=Task)
    async def complete_task(task_id: int):
        """Mark a task as completed."""
        task = await service.complete_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @router.post("/{task_id}/reopen", response_model=Task)
    async def reopen_task(task_id: int):
        """Reopen a completed task."""
        task = await service.reopen_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    return router
