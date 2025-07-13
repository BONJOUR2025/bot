from typing import List, Dict, Any
from app.data.template_repository import TemplateRepository

class TemplateService:
    def __init__(self, repo: TemplateRepository | None = None) -> None:
        self._repo = repo or TemplateRepository()

    async def list_templates(self) -> List[Dict[str, Any]]:
        return self._repo.list()

    async def create_template(self, name: str, text: str) -> Dict[str, Any]:
        return self._repo.create(name, text)

    async def delete_template(self, tpl_id: str) -> None:
        self._repo.delete(tpl_id)
