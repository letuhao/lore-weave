import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.models import ProjectCreate
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.summaries import SummariesRepo
from app.routers import context as context_router
from app.routers.context import (
    get_glossary_client,
    get_projects_repo,
    get_summaries_repo,
)


@pytest.fixture
def fake_glossary_client():
    """A mock glossary client used as a default dependency override.

    Individual tests replace `select_for_context` for their own needs.
    """
    client = AsyncMock()
    client.select_for_context = AsyncMock(return_value=[])
    return client


@pytest.fixture
def app_with_pool(pool, monkeypatch, fake_glossary_client):
    """Mount the context router on a fresh FastAPI app for this test.

    Uses FastAPI dependency_overrides for ALL deps so tests never touch
    module-level globals (K4a-I4 / K4b consistency).
    """
    monkeypatch.setattr(settings, "internal_service_token", "ctx_test_token")
    app = FastAPI()
    app.include_router(context_router.router)
    app.dependency_overrides[get_summaries_repo] = lambda: SummariesRepo(pool)
    app.dependency_overrides[get_projects_repo] = lambda: ProjectsRepo(pool)
    app.dependency_overrides[get_glossary_client] = lambda: fake_glossary_client
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
async def test_mode2_missing_project_returns_404(app_with_pool: FastAPI):
    """K4b: project_id that doesn't exist (or belongs to another user)
    returns 404 — the dispatcher can't distinguish the two cases to
    avoid a project-enumeration oracle."""
    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": str(uuid4()), "project_id": str(uuid4())},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
    assert r.status_code == 404
    assert r.json()["detail"] == "project not found"


@pytest.mark.asyncio
async def test_mode2_cross_user_project_returns_404(pool, app_with_pool: FastAPI):
    """User B cannot read user A's project."""
    user_a = uuid4()
    user_b = uuid4()
    projects = ProjectsRepo(pool)
    p = await projects.create(
        user_a,
        ProjectCreate(name="Secret Novel", project_type="book"),
    )

    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": str(user_b), "project_id": str(p.project_id)},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_mode2_happy_path(pool, app_with_pool: FastAPI, fake_glossary_client):
    from app.clients.glossary_client import GlossaryEntityForContext

    user_id = uuid4()
    projects = ProjectsRepo(pool)
    summaries = SummariesRepo(pool)

    p = await projects.create(
        user_id,
        ProjectCreate(
            name="Book 1",
            project_type="book",
            book_id=uuid4(),
            instructions="Be terse.",
        ),
    )
    await summaries.upsert(user_id, "global", None, "I am a novelist.")
    await summaries.upsert(user_id, "project", p.project_id, "Book 1 of 5.")

    fake_glossary_client.select_for_context = AsyncMock(return_value=[
        GlossaryEntityForContext(
            entity_id=str(uuid4()),
            cached_name="Alice",
            cached_aliases=["Al"],
            short_description="A wandering swordsman.",
            kind_code="character",
            is_pinned=True,
            tier="pinned",
            rank_score=1.0,
        ),
    ])

    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={
                "user_id": str(user_id),
                "project_id": str(p.project_id),
                "message": "who is Alice?",
            },
            headers={"X-Internal-Token": "ctx_test_token"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "static"
    root = ET.fromstring(body["context"])
    assert root.tag == "memory"
    assert root.attrib == {"mode": "static"}

    # L0
    assert root.find("user") is not None
    assert "novelist" in (root.find("user").text or "")
    # project
    proj = root.find("project")
    assert proj is not None
    assert proj.attrib["name"] == "Book 1"
    assert "terse" in (proj.find("instructions").text or "")
    assert "Book 1 of 5" in (proj.find("summary").text or "")
    # glossary
    gloss = root.find("glossary")
    assert gloss is not None
    alice = gloss.find("entity")
    assert alice is not None
    assert alice.find("name").text == "Alice"
    assert alice.attrib["kind"] == "character"
    assert alice.attrib["tier"] == "pinned"

    # verify client was called with the right args. K4.3 extracts
    # "Alice" from "who is Alice?" and issues one call per candidate,
    # so we expect the query to be "Alice" (not the raw message).
    assert fake_glossary_client.select_for_context.called
    all_calls = fake_glossary_client.select_for_context.call_args_list
    queries = {c.kwargs["query"] for c in all_calls}
    assert "Alice" in queries
    for call in all_calls:
        assert call.kwargs["user_id"] == user_id
        assert call.kwargs["book_id"] == p.book_id


@pytest.mark.asyncio
async def test_mode2_project_without_book_omits_glossary(pool, app_with_pool: FastAPI, fake_glossary_client):
    user_id = uuid4()
    projects = ProjectsRepo(pool)
    p = await projects.create(
        user_id, ProjectCreate(name="No Book", project_type="general")
    )

    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": str(user_id), "project_id": str(p.project_id)},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "static"
    root = ET.fromstring(body["context"])
    assert root.find("glossary") is None
    # glossary client should NOT have been called
    fake_glossary_client.select_for_context.assert_not_called()


@pytest.mark.asyncio
async def test_mode2_glossary_service_down_still_renders(pool, app_with_pool: FastAPI, fake_glossary_client):
    """If the glossary client returns [] (e.g. timeout path), Mode 2
    still emits a valid block without <glossary>."""
    user_id = uuid4()
    projects = ProjectsRepo(pool)
    p = await projects.create(
        user_id,
        ProjectCreate(name="Book 2", project_type="book", book_id=uuid4()),
    )
    # Client already defaults to returning [] — simulate down.
    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": str(user_id), "project_id": str(p.project_id)},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
    assert r.status_code == 200
    root = ET.fromstring(r.json()["context"])
    assert root.find("glossary") is None
    assert root.find("project") is not None


@pytest.mark.asyncio
async def test_mode3_extraction_enabled_returns_full_block(pool, app_with_pool: FastAPI):
    """K18.8 — dispatcher now flipped. extraction_enabled=true routes
    to Mode 3 and returns a `<memory mode="full">` block. Pre-K18.8
    this test asserted 501; we now assert Mode 3 renders cleanly even
    with zero extracted data (empty L2, empty L3) because the build
    pipeline degrades gracefully to a facts-less block."""
    user_id = uuid4()
    projects = ProjectsRepo(pool)
    p = await projects.create(
        user_id, ProjectCreate(name="Full Mode", project_type="book")
    )
    # Flip extraction_enabled directly (no public API for this in K1).
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE knowledge_projects SET extraction_enabled=true WHERE project_id=$1",
            p.project_id,
        )

    async with AsyncClient(transport=ASGITransport(app=app_with_pool), base_url="http://test") as c:
        r = await c.post(
            "/internal/context/build",
            json={"user_id": str(user_id), "project_id": str(p.project_id)},
            headers={"X-Internal-Token": "ctx_test_token"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "full"
    assert '<memory mode="full">' in body["context"]
    # Fresh project with no extraction = 20-message history limit
    # (Mode 3 tighter than Mode 2's 50).
    assert body["recent_message_count"] == 20


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
