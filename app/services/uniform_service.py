from typing import List, Optional, Dict

from app.core.types import Employee

from app.schemas.uniform import Uniform, UniformCreate, UniformUpdate
from app.data.uniform_repository import UniformRepository


class UniformService:
    def __init__(self, repo: Optional[UniformRepository] = None) -> None:
        self._repo = repo or UniformRepository()

    DEFAULT_KIT = ["Футболка", "Толстовка", "Кепка"]

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

    async def calculate_kit(self, employees: List[Employee]) -> Dict[str, Dict[str, int]]:
        result: Dict[str, Dict[str, int]] = {}
        for emp in employees:
            size = emp.clothing_size or ""
            for item in self.DEFAULT_KIT:
                if item not in result:
                    result[item] = {}
                result[item][size] = result[item].get(size, 0) + 1
        return result
