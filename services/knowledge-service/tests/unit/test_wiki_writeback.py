"""Unit tests for wiki writeback assembly + the glossary client (wiki-llm M5)."""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import respx
from loreweave_grounding.cites import GroundingCite

from app.clients.glossary_client import GlossaryClient
from app.wiki.context import ContextSource, EntityBrief, GenerationContext
from app.wiki.fingerprint import compute_build_inputs
from app.wiki.ir import Source
from app.wiki.parse import parse_article
from app.wiki.verify import WikiVerifyResult
from app.wiki.writeback import (
    build_source_usage,
    build_writeback_body,
    generation_status_for,
)


def _ctx() -> GenerationContext:
    brief = EntityBrief(entity_id="e1", name="姜子牙", kind="character",
                        aliases=["飞熊"], short_description="封神主角")
    items = [
        ContextSource(source=Source(cite_id="G1", kind="glossary", snippet="x"), text="封神主角"),
        ContextSource(source=Source(cite_id="K1", kind="kg", snippet="y"), text="姜子牙 — 师傅 → 元始天尊"),
        ContextSource(source=Source(cite_id="P1", kind="passage", chapter_id="ch1",
                                    block_index=2, chapter_sort_order=3, snippet="z"),
                      text="奉命下山伐纣"),
        ContextSource(source=Source(cite_id="P2", kind="passage", chapter_id="ch1",
                                    block_index=5, chapter_sort_order=3, snippet="z2"),
                      text="封神台点将"),
    ]
    return GenerationContext(brief=brief, items=items)


def _ir():
    sources = [Source(cite_id="G1", kind="glossary", snippet="封神主角"),
               Source(cite_id="P1", kind="passage", chapter_id="ch1", block_index=2,
                      chapter_sort_order=3, snippet="奉命下山伐纣")]
    return parse_article("姜子牙是封神主角 [G1]，奉命下山伐纣 [P1]。", entity_id="e1",
                         display_name="姜子牙", kind="character", language="zh", sources=sources)


def _build_inputs():
    return compute_build_inputs(context=_ctx(), model_ref="m1", prompt_version="p1",
                                pipeline_version="v1", retrieval_params={"mode": "hybrid"})


# ── generation_status_for ──────────────────────────────────────────────────────

def test_generation_status_blocked():
    v = WikiVerifyResult(passed=False, publish_blocked=True,
                         flags=[{"kind": "injection", "dimension": "d", "evidence": "e", "severity": "high"}])
    assert generation_status_for(v) == "blocked"


def test_generation_status_needs_review():
    v = WikiVerifyResult(passed=False, publish_blocked=False,
                         flags=[{"kind": "anachronism", "dimension": "d", "evidence": "e", "severity": "medium"}])
    assert generation_status_for(v) == "needs_review"


def test_generation_status_generated():
    assert generation_status_for(WikiVerifyResult(passed=True, publish_blocked=False, flags=[])) == "generated"


# ── build_source_usage ─────────────────────────────────────────────────────────

def test_source_usage_entity_kg_and_deduped_chapters():
    usage = build_source_usage(_ctx(), _build_inputs())
    types = [(u["source_type"], u["source_id"]) for u in usage]
    assert ("entity", "e1") in types
    assert ("kg", "e1") in types
    # two passages share ch1 → ONE 'block' row per distinct chapter
    block_rows = [u for u in usage if u["source_type"] == "block"]
    assert len(block_rows) == 1 and block_rows[0]["source_id"] == "ch1"
    assert block_rows[0]["source_version"]  # content-hash version present


def test_source_usage_no_kg_row_when_no_kg():
    brief = EntityBrief(entity_id="e2", name="x", short_description="d")
    ctx = GenerationContext(brief=brief, items=[
        ContextSource(source=Source(cite_id="P1", kind="passage", chapter_id="c", block_index=1, snippet="s"),
                      text="t"),
    ])
    bi = compute_build_inputs(context=ctx, model_ref="m", prompt_version="p",
                              pipeline_version="v", retrieval_params={})
    usage = build_source_usage(ctx, bi)
    assert not any(u["source_type"] == "kg" for u in usage)


# ── build_writeback_body ───────────────────────────────────────────────────────

def test_writeback_body_shape():
    verify = WikiVerifyResult(passed=True, publish_blocked=False, flags=[])
    cites = [GroundingCite(source_type="chapter", source_id="ch1", text="奉命下山伐纣", score=0.9)]
    body = build_writeback_body(
        context=_ctx(), ir=_ir(), verify=verify, cites=cites, build_inputs=_build_inputs(),
        model_ref="m1", user_id=uuid4(), grounding_params={"mode": "hybrid", "k": 8},
        prompt_version="p1", pipeline_version="v1",
    )
    assert body["entity_id"] == "e1"
    assert body["generation_status"] == "generated"
    assert body["generated_by"] == "m1"
    assert isinstance(body["body_json"], dict) and body["body_json"]["type"] == "doc"
    prov = body["generation_provenance"]
    assert prov["build_inputs"]["entity_id"] == "e1"
    assert prov["citations"][0]["source_id"] == "ch1"
    assert prov["publish_blocked"] is False
    assert prov["grounding"]["mode"] == "hybrid"
    assert any(u["source_type"] == "entity" for u in body["source_usage"])


def test_writeback_body_blocked_status_carries_flags():
    verify = WikiVerifyResult(passed=False, publish_blocked=True,
                              flags=[{"kind": "injection", "dimension": "d", "evidence": "e", "severity": "high"}])
    body = build_writeback_body(
        context=_ctx(), ir=_ir(), verify=verify, cites=[], build_inputs=_build_inputs(),
        model_ref="m1", user_id="u1", grounding_params={}, prompt_version="p1", pipeline_version="v1",
    )
    assert body["generation_status"] == "blocked"
    assert body["generation_provenance"]["verify_flags"][0]["kind"] == "injection"


# ── GlossaryClient.write_wiki_article ──────────────────────────────────────────

GL = "http://glossary-service:8088"


@pytest_asyncio.fixture
async def gc():
    client = GlossaryClient(base_url=GL, internal_token="t", timeout_s=0.5, retries=1)
    try:
        yield client
    finally:
        await client.aclose()


def _url(book_id):
    return f"{GL}/internal/books/{book_id}/wiki/articles"


@pytest.mark.asyncio
async def test_write_wiki_article_success(gc: GlossaryClient):
    book = uuid4()
    with respx.mock() as mock:
        mock.post(_url(book)).mock(return_value=httpx.Response(
            200, json={"action": "written", "article_id": "a1", "generation_status": "generated"}))
        out = await gc.write_wiki_article(book, body={"entity_id": "e1"})
    assert out["action"] == "written"


@pytest.mark.asyncio
async def test_write_wiki_article_non_200_returns_none(gc: GlossaryClient):
    book = uuid4()
    with respx.mock() as mock:
        mock.post(_url(book)).mock(return_value=httpx.Response(404, json={"error": "x"}))
        assert await gc.write_wiki_article(book, body={"entity_id": "e1"}) is None


@pytest.mark.asyncio
async def test_write_wiki_article_failure_returns_none(gc: GlossaryClient):
    book = uuid4()
    with respx.mock() as mock:
        mock.post(_url(book)).mock(side_effect=httpx.ConnectTimeout("boom"))
        assert await gc.write_wiki_article(book, body={"entity_id": "e1"}) is None
