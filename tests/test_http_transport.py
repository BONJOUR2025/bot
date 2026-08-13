"""Откат на curl, когда OpenSSL не может договориться с хостом.

Найдено в бою дважды. Сначала на хранилище фотографий Agbis: рукопожатие
OpenSSL зависает намертво, а curl.exe с той же машины в ту же секунду
получает HTTP 200 за 0.3 с. Потом — на polza.ai, и там хуже: срывается не
всегда, а через раз. LLM-клиент при этом молча откатывался на поиск по
ключевым словам, и снаружи это выглядело как «ИИ поглупел», без единой
ошибки в логе.

Отсюда требования, которые фиксируют тесты: быстрый путь остаётся httpx,
подмена происходит только на транспортной ошибке, а ответ сервера с любым
HTTP-кодом вторым транспортом не переспрашивается — разговор состоялся.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.services import http_transport as ht


class _Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload if payload is not None else {"ok": True}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)


@pytest.fixture
def no_curl(monkeypatch):
    """curl не должен вызываться — если вызвался, тест это заметит."""
    def boom(*a, **kw):
        pytest.fail("curl не должен был вызываться")
    monkeypatch.setattr(ht, "_curl_post", boom)


class TestFastPath:
    def test_httpx_success_is_returned_as_is(self, monkeypatch, no_curl):
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: _Resp(payload={"choices": [1]}))
        assert ht.post_json("https://x/y", {"a": 1}) == {"choices": [1]}

    def test_http_error_is_not_retried_with_curl(self, monkeypatch, no_curl):
        """4xx/5xx — это состоявшийся разговор. Переспрашивать другим стеком
        бессмысленно, а лишний запрос к платному API ещё и стоит денег."""
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: _Resp(status=429, text="rate limited"))
        with pytest.raises(ht.HttpError) as exc:
            ht.post_json("https://x/y", {})
        assert "429" in str(exc.value)

    def test_unexpected_error_propagates(self, monkeypatch, no_curl):
        """Ошибку не транспортного рода глушить нельзя — иначе поломка в коде
        замаскируется под сетевой сбой."""
        def boom(*a, **kw):
            raise ValueError("кривой payload")
        monkeypatch.setattr(httpx, "post", boom)
        with pytest.raises(ValueError):
            ht.post_json("https://x/y", {})


class TestFallback:
    @pytest.fixture
    def httpx_handshake_fails(self, monkeypatch):
        def boom(*a, **kw):
            raise httpx.ConnectTimeout("_ssl.c:975: The handshake operation timed out")
        monkeypatch.setattr(httpx, "post", boom)

    def test_curl_takes_over(self, monkeypatch, httpx_handshake_fails):
        monkeypatch.setattr(ht, "_curl_post", lambda *a, **kw: (200, '{"choices": [2]}'))
        assert ht.post_json("https://x/y", {}) == {"choices": [2]}

    def test_curl_http_error_surfaces(self, monkeypatch, httpx_handshake_fails):
        monkeypatch.setattr(ht, "_curl_post", lambda *a, **kw: (401, "unauthorized"))
        with pytest.raises(ht.HttpError) as exc:
            ht.post_json("https://x/y", {})
        assert "401" in str(exc.value)

    def test_curl_garbage_is_reported_not_swallowed(self, monkeypatch, httpx_handshake_fails):
        monkeypatch.setattr(ht, "_curl_post", lambda *a, **kw: (200, "<html>proxy</html>"))
        with pytest.raises(ht.HttpError) as exc:
            ht.post_json("https://x/y", {})
        assert "JSON" in str(exc.value)

    def test_fallback_is_logged(self, monkeypatch, httpx_handshake_fails, caplog):
        """Частоту подмены нужно уметь измерить, а не угадывать."""
        monkeypatch.setattr(ht, "_curl_post", lambda *a, **kw: (200, "{}"))
        with caplog.at_level("WARNING"):
            ht.post_json("https://x/y", {})
        assert any("curl" in r.message for r in caplog.records)


class TestCurlCommand:
    def test_body_and_response_go_through_files(self, monkeypatch, tmp_path):
        """Не через stdout: JSON бывает крупным, а смешивать его с выводом
        `-w %{http_code}` в одном потоке — напрашиваться на битый разбор."""
        seen = {}

        class _Done:
            stdout, stderr, returncode = b"200", b"", 0

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            out = cmd[cmd.index("-o") + 1]
            with open(out, "w", encoding="utf-8") as f:
                f.write('{"ok": 1}')
            return _Done()

        monkeypatch.setattr("subprocess.run", fake_run)
        status, raw = ht._curl_post("https://x/y", {"поле": "значение"},
                                    {"Authorization": "Bearer SECRET"}, 60, 10)
        assert (status, json.loads(raw)) == (200, {"ok": 1})
        cmd = seen["cmd"]
        i = cmd.index("--data-binary")
        assert cmd[i + 1].startswith("@"), "тело должно уходить файлом, а не аргументом"
        assert "-w" in cmd and "%{http_code}" in cmd

    def test_temp_files_are_cleaned_up(self, monkeypatch):
        import os

        created = []

        class _Done:
            stdout, stderr, returncode = b"200", b"", 0

        def fake_run(cmd, **kw):
            created.append(cmd[cmd.index("-o") + 1])                      # файл ответа
            created.append(cmd[cmd.index("--data-binary") + 1].lstrip("@"))  # файл запроса
            with open(created[0], "w") as f:
                f.write("{}")
            return _Done()

        monkeypatch.setattr("subprocess.run", fake_run)
        ht._curl_post("https://x/y", {}, {}, 60, 10)
        for p in created:
            assert not os.path.exists(p), f"временный файл остался: {p}"
