"""E0-4a router-level grant mapping — the executable guard on the need-mapping.

Owner-run tests can't catch a mis-mapped route (they pass at every tier), so this
drives the conftest ``grant_stub`` to a specific level and asserts the route's
need (none→404 anti-oracle, under-tier→403) for the surfaces the migrated tests
don't already cover (coverage / settings / extraction), plus the D-E0-4-F shared
per-book read view (the read SQL must NOT filter by owner_user_id).
"""
from __future__ import annotations

from uuid import UUID, uuid4

from tests.conftest import FakeRecord
from app.grant_client import GrantLevel

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BOOK_ID = str(uuid4())
JOB_ID = str(uuid4())


# ── coverage (view) ───────────────────────────────────────────────────────────

def test_coverage_404_for_non_grantee(client, fake_pool, grant_stub):
    grant_stub.level = GrantLevel.NONE
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    assert resp.status_code == 404


def test_coverage_shared_view_drops_owner_predicate(client, fake_pool, grant_stub):
    # D-E0-4-F: a grantee sees the WHOLE book's coverage — the query must scope by
    # book_id only (no owner_user_id), else a collaborator would see a partial matrix.
    grant_stub.level = GrantLevel.EDIT
    fake_pool.fetch.return_value = []
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/coverage")
    assert resp.status_code == 200
    sql = fake_pool.fetch.call_args.args[0]
    assert "owner_user_id" not in sql
    assert "book_id" in sql


# ── list jobs (view, shared) ──────────────────────────────────────────────────

def test_list_jobs_404_for_non_grantee(client, fake_pool, grant_stub):
    grant_stub.level = GrantLevel.NONE
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/jobs")
    assert resp.status_code == 404


def test_list_jobs_shared_view_drops_owner_predicate(client, fake_pool, grant_stub):
    grant_stub.level = GrantLevel.VIEW
    fake_pool.fetch.return_value = []
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/jobs")
    assert resp.status_code == 200
    sql = fake_pool.fetch.call_args.args[0]
    assert "owner_user_id" not in sql
    assert "book_id" in sql


# ── book settings (view read / edit write) ────────────────────────────────────

def test_get_book_settings_404_for_non_grantee(client, fake_pool, grant_stub):
    grant_stub.level = GrantLevel.NONE
    resp = client.get(f"/v1/translation/books/{BOOK_ID}/settings")
    assert resp.status_code == 404


def test_put_book_settings_403_for_view_grantee(client, fake_pool, grant_stub):
    grant_stub.level = GrantLevel.VIEW  # write needs edit
    resp = client.put(f"/v1/translation/books/{BOOK_ID}/settings", json={"target_language": "vi"})
    assert resp.status_code == 403


# ── extraction (edit create, gate runs before the source_language fetch) ───────

def test_extract_glossary_404_for_non_grantee(client, fake_pool, grant_stub):
    grant_stub.level = GrantLevel.NONE
    resp = client.post(
        f"/v1/extraction/books/{BOOK_ID}/extract-glossary",
        json={"chapter_ids": [str(uuid4())], "extraction_profile": {}},
    )
    assert resp.status_code == 404


def test_extract_glossary_403_for_view_grantee(client, fake_pool, grant_stub):
    grant_stub.level = GrantLevel.VIEW  # create needs edit
    resp = client.post(
        f"/v1/extraction/books/{BOOK_ID}/extract-glossary",
        json={"chapter_ids": [str(uuid4())], "extraction_profile": {}},
    )
    assert resp.status_code == 403


def test_extraction_cancel_404_for_non_grantee(client, fake_pool, grant_stub):
    grant_stub.level = GrantLevel.NONE
    fake_pool.fetchrow.return_value = FakeRecord({"status": "running", "book_id": UUID(BOOK_ID)})
    resp = client.post(f"/v1/extraction/jobs/{JOB_ID}/cancel")
    assert resp.status_code == 404


def test_extraction_get_job_404_for_non_grantee(client, fake_pool, grant_stub):
    grant_stub.level = GrantLevel.NONE
    fake_pool.fetchrow.return_value = FakeRecord({"book_id": UUID(BOOK_ID)})
    resp = client.get(f"/v1/extraction/jobs/{JOB_ID}")
    assert resp.status_code == 404
