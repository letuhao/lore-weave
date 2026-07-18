"""BookClient.get_chapter_revision_text — the 404-vs-transient contract.

Load-bearing for D-CM3B-DEAD-REVISION-LOOP: the chapters_pending drain marks a
pending row processed when this returns None, so None must mean PERMANENTLY GONE
(404) only — a transient 5xx / network error must RAISE so the job retries
instead of dropping canon.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.clients import BookClient


def _client_with(handler):
    bc = BookClient("http://book-service:8082", "tok", 5.0)
    bc._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"X-Internal-Token": "tok"},
    )
    return bc


@pytest.mark.asyncio
async def test_revision_text_404_returns_none_permanent_gone():
    bc = _client_with(lambda req: httpx.Response(404))
    try:
        assert await bc.get_chapter_revision_text(uuid4(), "ch", "rev") is None
    finally:
        await bc.aclose()


@pytest.mark.asyncio
async def test_revision_text_5xx_raises_transient_not_none():
    # A 5xx must NOT be swallowed to None (that would drain the pending row on a
    # blip and lose canon) — it raises so the job fails + retries.
    bc = _client_with(lambda req: httpx.Response(503))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await bc.get_chapter_revision_text(uuid4(), "ch", "rev")
    finally:
        await bc.aclose()


@pytest.mark.asyncio
async def test_revision_text_network_error_propagates():
    def boom(req):
        raise httpx.ConnectError("connection refused")

    bc = _client_with(boom)
    try:
        with pytest.raises(httpx.ConnectError):
            await bc.get_chapter_revision_text(uuid4(), "ch", "rev")
    finally:
        await bc.aclose()


@pytest.mark.asyncio
async def test_revision_text_200_returns_text():
    bc = _client_with(lambda req: httpx.Response(200, json={"text_content": "hello"}))
    try:
        assert await bc.get_chapter_revision_text(uuid4(), "ch", "rev") == "hello"
    finally:
        await bc.aclose()


# ── L7 Milestone B — KnowledgeClient.resolve_extraction_schema ─────────


from app.clients import KnowledgeClient


def _knowledge_with(handler):
    kc = KnowledgeClient("http://knowledge-service:8086", "tok", 5.0)
    kc._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"X-Internal-Token": "tok"},
    )
    return kc


@pytest.mark.asyncio
async def test_recall_facts_range_failclosed_branches():
    """P2 (D-REFLECTION-FACTS-RECALL-FAIL-CLOSED) — the client-level contract for all four branches:
    empty 200 → [] in BOTH modes; non-200 & transport error → RAISE only when fail_closed=True, else []."""
    from app.clients import KnowledgeUnavailable

    async def run(handler, *, fail_closed):
        kc = _knowledge_with(handler)
        try:
            return await kc.recall_facts_range(
                user_id="u", book_id="b", date_from="2026-07-06", date_to="2026-07-12",
                fail_closed=fail_closed,
            )
        finally:
            await kc.aclose()

    ok_empty = lambda req: httpx.Response(200, json={"facts": []})
    ok_facts = lambda req: httpx.Response(200, json={"facts": [{"content": "x"}]})
    err_500 = lambda req: httpx.Response(500, json={"error": "boom"})

    def boom(req):
        raise httpx.ConnectError("down")

    # empty 200 is NOT an error — [] in both modes.
    assert await run(ok_empty, fail_closed=False) == []
    assert await run(ok_empty, fail_closed=True) == []
    # a genuine 200 with facts returns them.
    assert await run(ok_facts, fail_closed=True) == [{"content": "x"}]
    # best-effort (rollup): non-200 and transport error → [] (the intended degrade).
    assert await run(err_500, fail_closed=False) == []
    assert await run(boom, fail_closed=False) == []
    # fail-closed (reflection): non-200 and transport error → RAISE.
    with pytest.raises(KnowledgeUnavailable):
        await run(err_500, fail_closed=True)
    with pytest.raises(KnowledgeUnavailable):
        await run(boom, fail_closed=True)


@pytest.mark.asyncio
async def test_resolve_schema_no_project_short_circuits_no_http():
    """project_id=None → None without any HTTP call (chat/global path)."""
    called = {"n": 0}

    def handler(req):
        called["n"] += 1
        return httpx.Response(200, json={"has_schema": False})

    kc = _knowledge_with(handler)
    try:
        assert await kc.resolve_extraction_schema(user_id=uuid4(), project_id=None) is None
        assert called["n"] == 0
    finally:
        await kc.aclose()


@pytest.mark.asyncio
async def test_resolve_schema_builds_advisory_extraction_schema():
    payload = {
        "has_schema": True,
        "entity_kinds": ["cultivator"],
        "edge_predicates": ["disciple_of", "pursues"],
        "event_kinds": [],
        "fact_types": ["realm"],
        "allow_free_edges": True,  # advisory
        "label": "p1@v3",
        "schema_version": 3,
    }
    kc = _knowledge_with(lambda req: httpx.Response(200, json=payload))
    try:
        schema = await kc.resolve_extraction_schema(user_id=uuid4(), project_id=uuid4())
    finally:
        await kc.aclose()
    assert schema is not None
    assert schema.entity_kinds == ("cultivator",)
    assert schema.edge_predicates == ("disciple_of", "pursues")
    assert schema.fact_types == ("realm",)
    assert schema.allow_free_edges is True  # never pre-drops on the SDK path
    assert schema.schema_version == 3


@pytest.mark.asyncio
async def test_resolve_schema_has_schema_false_returns_none():
    kc = _knowledge_with(lambda req: httpx.Response(200, json={"has_schema": False}))
    try:
        assert await kc.resolve_extraction_schema(user_id=uuid4(), project_id=uuid4()) is None
    finally:
        await kc.aclose()


@pytest.mark.asyncio
async def test_resolve_schema_non_200_returns_none():
    kc = _knowledge_with(lambda req: httpx.Response(503))
    try:
        assert await kc.resolve_extraction_schema(user_id=uuid4(), project_id=uuid4()) is None
    finally:
        await kc.aclose()
