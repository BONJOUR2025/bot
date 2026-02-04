from typing import List, Optional, Dict, Any
from datetime import datetime

from app.data.adjustment_repository import AdjustmentRepository


class AdjustmentService:
    def __init__(self) -> None:
        self._repo = AdjustmentRepository()

    def list(self) -> List[Dict[str, Any]]:
        return self._repo.list()

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if 'date' not in data or not data['date']:
            data['date'] = datetime.today().date().isoformat()
        return self._repo.create(data)

    def update(self, adj_id: str,
               updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._repo.update(adj_id, updates)

    def delete(self, adj_id: str) -> None:
        self._repo.delete(adj_id)
