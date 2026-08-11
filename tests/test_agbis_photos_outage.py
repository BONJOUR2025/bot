"""Поведение при недоступном хранилище фотографий.

Найдено в бою. Хранилище — компьютер в салоне, доступный через шлюз Agbis;
11 августа он перестал отвечать на TLS-рукопожатие. Наш код при этом отводил
по 60 секунд и на соединение, и на скачивание, а размыкателя не было вовсе:
каждый следующий снимок заново выстаивал ту же минуту. Заказ из трёх
фотографий висел «Загрузка из хранилища…» несколько минут и заканчивался
ничем — пользователь видел бесконечный спиннер вместо причины.
"""
from __future__ import annotations

import time

import pytest

from app.services import agbis_photos as ap


@pytest.fixture(autouse=True)
def clean():
    ap._clear_outage()
    yield
    ap._clear_outage()


@pytest.fixture
def agent(monkeypatch):
    a = ap.StorageAgent(agent_id=1081, host="im-gate.com", port=10460)
    monkeypatch.setattr(ap, "resolve_agent", lambda force=False: a)
    monkeypatch.setattr(ap, "_get_session", lambda ag, force_new=False: "sess-1")
    monkeypatch.setattr(ap, "cache_get", lambda md5: None)
    monkeypatch.setattr(ap, "cache_put", lambda md5, data: None)
    return a


class TestTimeoutSplit:
    def test_connect_is_bounded_much_tighter_than_download(self, monkeypatch):
        """Дозвониться — быстро, качать — долго. Раньше на оба было 60 с, и
        выключенный компьютер стоил минуты ожидания на каждый снимок."""
        seen = {}

        class _Done:
            stdout, stderr, returncode = b"200", b"", 0

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            return _Done()

        monkeypatch.setattr("subprocess.run", fake_run)
        ap._curl_get("https://x/Login", {"a": 1})

        cmd = seen["cmd"]
        connect = int(cmd[cmd.index("--connect-timeout") + 1])
        total = int(cmd[cmd.index("--max-time") + 1])
        assert connect <= 10
        assert total >= 60
        assert connect < total

    def test_session_id_never_reaches_the_command_log(self, monkeypatch):
        """SessionID равнозначен паролю сервисной учётки: он уходит в URL,
        но не должен всплыть в сообщении об ошибке."""
        def fake_run(cmd, **kw):
            class _R:
                stdout, stderr, returncode = b"", b"curl: (28) timeout", 28
            return _R()

        monkeypatch.setattr("subprocess.run", fake_run)
        with pytest.raises(OSError) as exc:
            ap._curl_get("https://x/GetPhoto", {"SessionID": "SECRET-GUID"})
        assert "SECRET-GUID" not in str(exc.value)


class TestCircuitBreaker:
    def test_second_photo_fails_immediately(self, agent, monkeypatch):
        calls = []

        def boom(*a, **kw):
            calls.append(1)
            raise OSError("curl: (28) Operation timed out")

        monkeypatch.setattr(ap, "_download", boom)

        with pytest.raises(ap.PhotoStorageError):
            ap.get_photo("md5-1")
        with pytest.raises(ap.PhotoStorageError):
            ap.get_photo("md5-2")
        with pytest.raises(ap.PhotoStorageError):
            ap.get_photo("md5-3")

        assert len(calls) == 1, "второй и третий снимок не должны ходить в сеть заново"

    def test_the_reason_is_preserved_for_the_ui(self, agent, monkeypatch):
        monkeypatch.setattr(ap, "_download",
                            lambda *a, **kw: (_ for _ in ()).throw(OSError("curl: (28) timeout")))
        with pytest.raises(ap.PhotoStorageError) as e1:
            ap.get_photo("md5-1")
        with pytest.raises(ap.PhotoStorageError) as e2:
            ap.get_photo("md5-2")

        assert "не отвечает" in str(e1.value)
        assert str(e2.value) == str(e1.value)

    def test_message_is_human_not_a_stack_detail(self, agent, monkeypatch):
        """«_ssl.c:975: The handshake operation timed out» оператору не
        говорит ничего — он должен узнать, что проверять."""
        monkeypatch.setattr(ap, "_download",
                            lambda *a, **kw: (_ for _ in ()).throw(
                                OSError("_ssl.c:975: The handshake operation timed out")))
        with pytest.raises(ap.PhotoStorageError) as e:
            ap.get_photo("md5-1")

        assert "_ssl.c" not in str(e.value)
        assert "салоне" in str(e.value)

    def test_outage_expires_so_a_revived_agent_is_picked_up(self, agent, monkeypatch):
        """Включённый обратно компьютер должен подхватиться сам, без
        перезапуска процесса."""
        monkeypatch.setattr(ap, "_OUTAGE_TTL_S", 0.05)
        monkeypatch.setattr(ap, "_download",
                            lambda *a, **kw: (_ for _ in ()).throw(OSError("curl: (28) timeout")))
        with pytest.raises(ap.PhotoStorageError):
            ap.get_photo("md5-1")
        assert ap._outage_reason() is not None

        time.sleep(0.06)
        assert ap._outage_reason() is None

    def test_success_after_expiry_clears_the_outage_for_good(self, agent, monkeypatch):
        """Размыкатель отсекает запрос ДО сети, поэтому «оживает» хранилище
        только после истечения срока. Дошли до байтов — метка снимается
        совсем, а не ждёт следующего таймаута."""
        jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
        monkeypatch.setattr(ap, "_download",
                            lambda *a, **kw: (200, jpeg))
        ap._outage = ("старая ошибка", time.time() - 1)  # срок уже вышел
        assert ap.get_photo("md5-ok") == jpeg
        assert ap._outage is None


class TestMissingPhotoIsNotAnOutage:
    def test_a_missing_photo_does_not_block_its_neighbours(self, agent, monkeypatch):
        """Агент ответил, просто этого снимка у него нет — соседние вполне
        могут найтись, размыкать нельзя."""
        monkeypatch.setattr(ap, "_download",
                            lambda *a, **kw: (200, b"not an image"))
        with pytest.raises(ap.PhotoStorageError):
            ap.get_photo("md5-missing")

        assert ap._outage_reason() is None
