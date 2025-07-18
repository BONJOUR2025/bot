from typing import List, Optional

from app.schemas.uniform import Uniform, UniformCreate, UniformUpdate
from app.data.uniform_repository import UniformRepository


class UniformService:
    def __init__(self, repo: Optional[UniformRepository] = None) -> None:
        self._repo = repo or UniformRepository()

    async def list_uniforms(self, employee_id: Optional[str] = None) -> List[Uniform]:
        rows = self._repo.list(employee_id)
        return [Uniform(**r) for r in rows]

    async def create_uniform(self, data: UniformCreate) -> Uniform:
        created = self._repo.create(data.model_dump())
        return Uniform(**created)

    async def update_uniform(self, item_id: str, data: UniformUpdate) -> Optional[Uniform]:
        updated = self._repo.update(item_id, data.model_dump(exclude_none=True))
        return Uniform(**updated) if updated else None

    async def delete_uniform(self, item_id: str) -> None:
        self._repo.delete(item_id)
