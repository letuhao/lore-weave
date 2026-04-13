import xml.etree.ElementTree as ET
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.repositories.summaries import SummariesRepo
from app.routers import context as context_router
from app.routers.context import get_summaries_repo


@pytest.fixture
def app_with_pool(pool, monkeypatch):
    """Mount the context router on a fresh FastAPI app for this test.

    Uses FastAPI dependency_overrides to substitute a real SummariesRepo
    bound to the test pool, instead of monkey-patching the module-level
    `_knowledge_pool` global (K4a-I4 fix).
    """
    monkeypatch.setattr(settings, "internal_service_token", "ctx_test_token")
    app = FastAPI()
    app.include_router(context_router.router)
    app.dependency_overrides[get_summaries_repo] = lambda: SummariesRepo(pool)
    return app


@pytest.mark.asyncio
async def test_missing_token_returns_401(app_with_pool: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post("/internal/context/build", json={"user_id": str(uuid4())})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_wrong_token_returns_401(app_with_pool: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": str(uuid4())},
            headers={"X-Internal-Token": "nope"},
        )
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_malformed_request_returns_422(app_with_pool: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": "not-a-uuid"},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_empty_body_returns_422(app_with_pool: FastAPI):
    # K4a-I16: empty POST body — Pydantic rejects missing user_id.
    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_message_too_long_returns_422(app_with_pool: FastAPI):
    # K4a-I6: message field capped at 4000 runes.
    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": str(uuid4()), "message": "x" * 4001},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_mode1_without_summary(app_with_pool: FastAPI):
    user_id = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": str(user_id)},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "no_project"
    assert body["recent_message_count"] == 50
    assert body["token_count"] > 0
    # Valid XML with just instructions
    root = ET.fromstring(body["context"])
    assert root.tag == "memory"
    assert root.attrib == {"mode": "no_project"}
    assert root.find("user") is None
    instr = root.find("instructions")
    assert instr is not None
    # K4a-I3: when there is no <user> the instruction must NOT say "above".
    assert "above" not in (instr.text or "").lower()


@pytest.mark.asyncio
async def test_mode1_with_summary(pool, app_with_pool: FastAPI):
    user_id = uuid4()
    repo = SummariesRepo(pool)
    await repo.upsert(user_id, "global", None, "I write fantasy novels set in Ming-dynasty China.")
    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": str(user_id)},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
    assert r.status_code == 200
    body = r.json()
    root = ET.fromstring(body["context"])
    user = root.find("user")
    assert user is not None
    assert "Ming-dynasty" in (user.text or "")
    # K4a-I3: the with-bio instructions mention <user> explicitly.
    instr = root.find("instructions")
    assert instr is not None
    assert "user" in (instr.text or "").lower()


@pytest.mark.asyncio
async def test_mode2_returns_501(app_with_pool: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": str(uuid4()), "project_id": str(uuid4())},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
    assert r.status_code == 501
    # K4a-I8: parse JSON envelope instead of substring-matching raw text.
    body = r.json()
    assert "detail" in body
    assert "Mode 2" in body["detail"] or "K4b" in body["detail"]


@pytest.mark.asyncio
async def test_cross_user_isolation_trusted(pool, app_with_pool: FastAPI):
    # K4a/K2b trust model: the caller's user_id is trusted (chat-service
    # validated their JWT). We verify each user gets THEIR OWN data —
    # user_a's summary is invisible when the request asks for user_b.
    user_a = uuid4()
    user_b = uuid4()
    repo = SummariesRepo(pool)
    await repo.upsert(user_a, "global", None, "A's private bio — must not leak.")

    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": str(user_b)},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
    assert r.status_code == 200
    body = r.json()
    assert "A's private bio" not in body["context"]
    assert "private bio" not in body["context"]
