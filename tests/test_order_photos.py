"""Tests for FirebirdService.get_order_photos.

Firebird is stubbed at _connect(), same pattern as test_daily_cash_balances.py.
What matters here: the thumbnail comes back embedded in this one query as a
data URI rather than as a separate per-photo endpoint. That is a deliberate
fix for a real production incident — an order with dozens of photos meant
dozens of independent <img> tags, each opening its own Firebird attachment,
which is the exact concurrent-connection pattern that took the server down
on 2026-07-18. See the docstring on get_order_photos for the full story.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.services import firebird_service as fb
from app.services.firebird_service import FirebirdService

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"x" * 20
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"x" * 20


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._cursor = _FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


@pytest.fixture
def stub_rows(monkeypatch):
    def install(rows):
        conn = _FakeConn(rows)
        monkeypatch.setattr(fb, "_connect", lambda *a, **k: conn)
        monkeypatch.setattr(fb, "FIREBIRD_AVAILABLE", True)
        return conn
    return install


def _row(pid, dos_id, item, small=JPEG_BYTES, is_main=1, has_normal=0,
         md5="ABC123", fmt="jpeg", when=None):
    return (pid, dos_id, when or dt.datetime(2026, 8, 5, 11, 32), md5, is_main,
            fmt, item, small, has_normal)


class TestThumbnailInline:
    def test_thumbnail_is_a_data_uri_in_the_same_row(self, stub_rows):
        stub_rows([_row(1, 100, "Кроссовки")])
        photos = FirebirdService().get_order_photos(123, "22075-8")
        assert len(photos) == 1
        assert photos[0]["thumb"].startswith("data:image/jpeg;base64,")

    def test_png_thumbnail_gets_the_right_mime_type(self, stub_rows):
        stub_rows([_row(1, 100, "Сумка", small=PNG_BYTES)])
        photos = FirebirdService().get_order_photos(123, "1")
        assert photos[0]["thumb"].startswith("data:image/png;base64,")

    def test_missing_thumbnail_is_none_not_a_broken_uri(self, stub_rows):
        stub_rows([_row(1, 100, "Туфли", small=None)])
        photos = FirebirdService().get_order_photos(123, "1")
        assert photos[0]["thumb"] is None

    def test_blob_reader_object_is_read_not_passed_through(self, stub_rows):
        """fdb hands back a BlobReader, not raw bytes — the field name it
        exposes is .read(), same as the pattern used elsewhere in this file
        for NORMAL/SMALL blobs."""
        class _BlobReader:
            def read(self):
                return JPEG_BYTES

        stub_rows([_row(1, 100, "Кроссовки", small=_BlobReader())])
        photos = FirebirdService().get_order_photos(123, "1")
        assert photos[0]["thumb"].startswith("data:image/jpeg;base64,")

    def test_no_separate_thumb_lookup_method_remains(self):
        """The whole point of embedding thumbnails is to remove the N+1
        per-photo Firebird round trip; the old method must actually be gone,
        not just unused."""
        assert not hasattr(FirebirdService, "get_order_photo_thumb")


class TestGrouping:
    def test_photos_from_the_same_item_share_dos_id(self, stub_rows):
        stub_rows([
            _row(1, 100, "Кроссовки"),
            _row(2, 100, "Кроссовки"),
            _row(3, 200, "Сумка"),
        ])
        photos = FirebirdService().get_order_photos(123, "1")
        dos_ids = [p["dos_id"] for p in photos]
        assert dos_ids == [100, 100, 200]

    def test_item_name_strips_the_agbis_disclaimer_suffix(self, stub_rows):
        stub_rows([_row(1, 100, "Кроссовки ***ВНИМАНИЕ!!!Окончательная стоимость...")])
        photos = FirebirdService().get_order_photos(123, "1")
        assert photos[0]["item"] == "Кроссовки"

    def test_is_main_and_in_db_flags(self, stub_rows):
        stub_rows([_row(1, 100, "Кроссовки", is_main=1, has_normal=0)])
        photos = FirebirdService().get_order_photos(123, "1")
        assert photos[0]["is_main"] is True
        assert photos[0]["in_db"] is False

    def test_connection_is_closed(self, stub_rows):
        conn = stub_rows([_row(1, 100, "Кроссовки")])
        FirebirdService().get_order_photos(123, "1")
        assert conn.closed is True


class TestFailureModes:
    def test_returns_empty_list_when_driver_missing(self, monkeypatch):
        monkeypatch.setattr(fb, "FIREBIRD_AVAILABLE", False)
        assert FirebirdService().get_order_photos(123, "1") == []

    def test_query_error_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(fb, "FIREBIRD_AVAILABLE", True)

        def boom(*a, **k):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(fb, "_connect", boom)
        assert FirebirdService().get_order_photos(123, "1") == []
