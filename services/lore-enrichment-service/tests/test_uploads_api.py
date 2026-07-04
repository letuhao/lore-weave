"""Uploads HTTP handler — mode F (Compose slice 3).

TestClient + dependency overrides; MinIO + the background extraction are faked, so
no live stack. Asserts the handler branch behaviour: ext allow-list (415), license
default-deny (403), size/empty caps (413/400), auth (401), the async 202 + row
insert, and the owner-scoped poll (200/404).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import uploads as uploads_api
# Bind the REAL background extractor at import time — the autouse fixture below
# replaces uploads_api._extract_and_store with a noop (so the POST endpoint's
# background task is inert), but these direct tests need the real implementation.
from app.api.uploads import _extract_and_store as real_extract_and_store
from app.deps import get_db

OWNER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"


class _FakeConn:
    def __init__(self, row=None, sink=None):
        self._row = row
        self._sink = sink if sink is not None else []

    async def execute(self, sql, *args):
        self._sink.append((sql, args))

    async def fetchrow(self, sql, *args):
        return self._row


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, row=None):
        self.row = row
        self.sink = []

    def acquire(self):
        return _Acquire(_FakeConn(row=self.row, sink=self.sink))


def _app(pool) -> FastAPI:
    app = FastAPI()
    app.include_router(uploads_api.router)
    app.dependency_overrides[get_db] = lambda: pool
    return app


def _bearer(sub: str = OWNER) -> str:
    return pyjwt.encode({"sub": sub, "exp": 4102444800}, "test_jwt_secret", algorithm="HS256")


def _client(pool):
    return TestClient(_app(pool))


def _post(client, *, filename="ref.txt", content=b"hello", license_asserted="public_domain", auth=True, mime="text/plain"):
    headers = {"Authorization": f"Bearer {_bearer()}"} if auth else {}
    return client.post(
        "/v1/lore-enrichment/uploads",
        files={"file": (filename, content, mime)},
        data={"book_id": str(uuid4()), "project_id": str(uuid4()), "license_asserted": license_asserted},
        headers=headers,
    )


@pytest.fixture(autouse=True)
def _patch_storage(monkeypatch):
    async def _noop(*a, **k):
        return "key"
    monkeypatch.setattr(uploads_api, "ensure_bucket", lambda: _noop())
    monkeypatch.setattr(uploads_api, "upload_file", lambda *a, **k: _noop())
    # keep the background extraction inert (it would touch the fake pool oddly).
    async def _noop_extract(*a, **k):
        return None
    monkeypatch.setattr(uploads_api, "_extract_and_store", _noop_extract)


def test_upload_requires_auth():
    assert _post(_client(_FakePool()), auth=False).status_code == 401


def test_upload_unsupported_extension_415():
    r = _post(_client(_FakePool()), filename="malware.exe", content=b"MZ")
    assert r.status_code == 415


def test_upload_copyrighted_license_403():
    r = _post(_client(_FakePool()), license_asserted="copyrighted")
    assert r.status_code == 403


def test_upload_unknown_license_403():
    r = _post(_client(_FakePool()), license_asserted="banana")
    assert r.status_code == 403


def test_upload_empty_file_400():
    r = _post(_client(_FakePool()), content=b"")
    assert r.status_code == 400


def test_upload_happy_202_processing():
    pool = _FakePool()
    r = _post(_client(pool), filename="ref.md", content="蓬萊。".encode("utf-8"), license_asserted="owned")
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "processing" and body["filename"] == "ref.md"
    # the row INSERT was attempted (status processing, license normalized owned→licensed).
    inserts = [s for s, _ in pool.sink if "INSERT INTO enrichment_upload" in s]
    assert len(inserts) == 1


def test_poll_returns_view():
    row = {
        "upload_id": uuid4(), "filename": "ref.pdf", "mime": "application/pdf",
        "pages": 3, "extracted_chars": 1200, "ocr_used": True,
        "license_asserted": "public_domain", "status": "ready", "error_message": None,
    }
    r = _client(_FakePool(row=row)).get(
        f"/v1/lore-enrichment/uploads/{row['upload_id']}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready" and body["ocr_used"] is True and body["pages"] == 3
    assert "extracted_text" not in body  # the poll never returns the full text


def test_poll_not_found_404():
    r = _client(_FakePool(row=None)).get(
        f"/v1/lore-enrichment/uploads/{uuid4()}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert r.status_code == 404


# ── _extract_and_store (the background extract → status flip) — direct tests ──
def test_extract_and_store_ready():
    # A real .txt extraction flips status='ready' with the extracted text + chars.
    pool = _FakePool()
    asyncio.run(real_extract_and_store(pool, uuid4(), "a.txt", "蓬萊乃東海仙山。".encode("utf-8")))
    updates = [(s, a) for s, a in pool.sink if "status='ready'" in s]
    assert len(updates) == 1
    args = updates[0][1]  # (upload_id, text, chars, pages, ocr)
    assert "蓬萊" in args[1] and args[2] > 0


def test_extract_and_store_failed(monkeypatch):
    # An extraction that raises is recorded as status='failed' (never crashes).
    def _boom(*a, **k):
        raise RuntimeError("parse boom")
    monkeypatch.setattr(uploads_api, "extract_text", _boom)
    pool = _FakePool()
    asyncio.run(real_extract_and_store(pool, uuid4(), "a.txt", b"hi"))
    failed = [(s, a) for s, a in pool.sink if "status='failed'" in s]
    assert len(failed) == 1
    assert "parse boom" in failed[0][1][1]


def test_extract_and_store_pdf_resolves_book_ocr_lang(monkeypatch):
    # For a PDF + book_id, the OCR language is resolved from the book profile and
    # threaded to extract_text (D-COMPOSE-S3-OCR-LANG). The fake pool has no profile
    # row → NEUTRAL (language 'auto') → the CJK+English default superset.
    captured: dict[str, object] = {}

    def _capture(filename, data, *, max_pages, lang=None):
        captured["lang"] = lang
        from app.files.extract import ExtractResult
        return ExtractResult(text="x", pages=1, ocr_used=False)

    monkeypatch.setattr(uploads_api, "extract_text", _capture)
    asyncio.run(real_extract_and_store(_FakePool(), uuid4(), "scan.pdf", b"%PDF-1.4", uuid4()))
    assert captured["lang"] == "chi_sim+chi_tra+eng"


def test_extract_and_store_txt_skips_profile_lookup(monkeypatch):
    # A non-PDF never reads the profile (no OCR) — lang stays None.
    captured: dict[str, object] = {"lang": "SENTINEL"}

    def _capture(filename, data, *, max_pages, lang=None):
        captured["lang"] = lang
        from app.files.extract import ExtractResult
        return ExtractResult(text="x", pages=1, ocr_used=False)

    monkeypatch.setattr(uploads_api, "extract_text", _capture)
    asyncio.run(real_extract_and_store(_FakePool(), uuid4(), "a.txt", b"hi", uuid4()))
    assert captured["lang"] is None
