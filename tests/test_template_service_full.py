"""Comprehensive tests for TemplateService."""

import json
import asyncio

import pytest

from app.data.template_repository import TemplateRepository
from app.services.template_service import TemplateService
from tests.conftest import run_async


def _make_service(tmp_path, data=None):
    p = tmp_path / "templates.json"
    if data is None:
        data = [{"id": "1", "name": "Приветствие", "text": "Привет!"}]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    repo = TemplateRepository(path=p)
    return TemplateService(repo=repo)


class TestTemplateServiceList:
    def test_list(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.list_templates()
            assert len(result) == 1
            assert result[0]["name"] == "Приветствие"
        run_async(_run())

    def test_list_empty(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        async def _run():
            result = await svc.list_templates()
            assert result == []
        run_async(_run())


class TestTemplateServiceCreate:
    def test_create(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        async def _run():
            result = await svc.create_template("Новый", "Текст шаблона")
            assert result["name"] == "Новый"
            assert result["text"] == "Текст шаблона"
            assert "id" in result
        run_async(_run())


class TestTemplateServiceDelete:
    def test_delete(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            await svc.delete_template("1")
            result = await svc.list_templates()
            assert len(result) == 0
        run_async(_run())
