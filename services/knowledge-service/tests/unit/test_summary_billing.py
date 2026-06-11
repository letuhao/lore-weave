"""E0-3 Phase 2a-2 — BYOK caller-pays for the extraction-triggered summary
pipeline.

The summary pipeline makes TWO provider calls (LLM summarize_level + embed).
When a book collaborator triggered the extraction that enqueued the summary,
both must resolve under the CALLER's key + same-model refs; the STORED
embedding_model_uuid tag (search filter) stays the project's. Empty billing
fields ⇒ owner-triggered ⇒ legacy single-identity path. Resolvers gate on
billing_user_id (the identity), never a ref alone (review-impl MED-1).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.repositories.level_summaries import UpsertOutcome
from app.extraction.pass2_orchestrator import enqueue_chapter_and_maybe_book_summaries
from app.jobs.summary_enqueue import SummarizeMessage
from app.jobs.summary_processor import (
    SummaryProcessorDeps,
    _bill_embed_ref,
    _bill_llm_ref,
    _bill_user,
    process_summarize_message,
)

_OWNER = str(uuid4())
_COLLAB = str(uuid4())


def _msg(**overrides) -> SummarizeMessage:
    base = dict(
        level="chapter",
        node_path="book/part-1/chapter-1",
        node_id=str(uuid4()),
        book_id=str(uuid4()),
        user_id=_OWNER,
        project_id=str(uuid4()),
        job_id=str(uuid4()),
        model_ref="owner-llm",
        embedding_model_uuid="project-emb-tag",
        embedding_dimension=1024,
    )
    base.update(overrides)
    return SummarizeMessage(**base)  # type: ignore[arg-type]


# ── resolver helpers (identity-gated, MED-1) ──────────────────────────


def test_bill_helpers_owner_path():
    m = _msg()  # no billing → owner
    assert _bill_user(m) == _OWNER
    assert _bill_llm_ref(m) == "owner-llm"
    assert _bill_embed_ref(m) == "project-emb-tag"


def test_bill_helpers_collaborator_path():
    m = _msg(
        billing_user_id=_COLLAB,
        billing_llm_model="collab-llm",
        billing_embedding_model="collab-emb",
    )
    assert _bill_user(m) == _COLLAB
    assert _bill_llm_ref(m) == "collab-llm"
    assert _bill_embed_ref(m) == "collab-emb"


def test_bill_helpers_ignore_orphan_ref_without_user():
    """MED-1: a billing ref without billing_user_id is incoherent → ignored."""
    m = _msg(billing_llm_model="orphan-llm", billing_embedding_model="orphan-emb")
    assert _bill_llm_ref(m) == "owner-llm"
    assert _bill_embed_ref(m) == "project-emb-tag"


# ── end-to-end: process_summarize_message resolves under billing ──────


def _wire(mock_repo_cls, deps):
    repo = MagicMock()
    repo.find_cached = AsyncMock(return_value=None)
    repo.upsert_summary = AsyncMock(return_value=UpsertOutcome(
        cache_hit=False, race_winner=True, summary_id=uuid4(),
    ))
    mock_repo_cls.return_value = repo
    deps.embedding_client = MagicMock()
    deps.embedding_client.embed = AsyncMock(return_value=[0.1] * 1024)
    deps.neo4j_session.run = AsyncMock()
    return repo


def _deps() -> SummaryProcessorDeps:
    return SummaryProcessorDeps(
        knowledge_pool=MagicMock(),
        neo4j_session=MagicMock(),
        llm_client=MagicMock(),
        embedding_client=MagicMock(),
        summary_enqueue=AsyncMock(return_value="msg-id"),
    )


@patch("app.jobs.summary_processor.LevelSummariesRepo")
@patch("app.jobs.summary_processor._load_scene_leaf_texts", new_callable=AsyncMock)
@patch("app.jobs.summary_processor._load_top_entities_for_chapter", new_callable=AsyncMock)
@patch("app.jobs.summary_processor.summarize_level", new_callable=AsyncMock)
async def test_collaborator_summary_bills_caller_stores_project_tag(
    mock_summarize, mock_entities, mock_scenes, mock_repo_cls,
):
    from loreweave_extraction import LevelSummary as ExtLevelSummary
    mock_scenes.return_value = ["s1", "s2"]
    mock_entities.return_value = []
    mock_summarize.return_value = ExtLevelSummary(
        summary_text="A meaningful two-sentence summary of the content here.",
        token_usage={},
    )
    deps = _deps()
    repo = _wire(mock_repo_cls, deps)

    msg = _msg(
        billing_user_id=_COLLAB,
        billing_llm_model="collab-llm",
        billing_embedding_model="collab-emb",
    )
    await process_summarize_message(msg, deps)

    # LLM resolves under the collaborator + their LLM ref.
    assert mock_summarize.await_args.kwargs["user_id"] == _COLLAB
    assert mock_summarize.await_args.kwargs["model_ref"] == "collab-llm"
    # Embed GENERATES under the collaborator's embed ref...
    assert deps.embedding_client.embed.await_args.kwargs["model_uuid"] == "collab-emb"
    # ...but the STORED tag stays the project's (search filter integrity).
    assert repo.upsert_summary.await_args.kwargs["embedding_model_uuid"] == "project-emb-tag"


@patch("app.jobs.summary_processor.LevelSummariesRepo")
@patch("app.jobs.summary_processor._load_scene_leaf_texts", new_callable=AsyncMock)
@patch("app.jobs.summary_processor._load_top_entities_for_chapter", new_callable=AsyncMock)
@patch("app.jobs.summary_processor.summarize_level", new_callable=AsyncMock)
async def test_owner_summary_uses_owner_identity(
    mock_summarize, mock_entities, mock_scenes, mock_repo_cls,
):
    from loreweave_extraction import LevelSummary as ExtLevelSummary
    mock_scenes.return_value = ["s1"]
    mock_entities.return_value = []
    mock_summarize.return_value = ExtLevelSummary(
        summary_text="A meaningful two-sentence summary of the content here.",
        token_usage={},
    )
    deps = _deps()
    _wire(mock_repo_cls, deps)

    await process_summarize_message(_msg(), deps)  # no billing
    assert mock_summarize.await_args.kwargs["user_id"] == _OWNER
    assert mock_summarize.await_args.kwargs["model_ref"] == "owner-llm"
    assert deps.embedding_client.embed.await_args.kwargs["model_uuid"] == "project-emb-tag"


# ── redis serde round-trip (additive, back-compat) ────────────────────


def test_redis_roundtrip_carries_billing():
    m = _msg(
        billing_user_id=_COLLAB,
        billing_llm_model="collab-llm",
        billing_embedding_model="collab-emb",
    )
    back = SummarizeMessage.from_redis_fields(m.to_redis_fields())
    assert back.billing_user_id == _COLLAB
    assert back.billing_llm_model == "collab-llm"
    assert back.billing_embedding_model == "collab-emb"


def test_redis_legacy_message_without_billing_defaults_empty():
    """Old messages enqueued before 2a-2 lack the billing keys → "" (owner)."""
    fields = _msg().to_redis_fields()
    for k in ("billing_user_id", "billing_llm_model", "billing_embedding_model"):
        fields.pop(k)
    back = SummarizeMessage.from_redis_fields(fields)
    assert back.billing_user_id == ""
    assert back.billing_llm_model == ""


# ── orchestrator stamps billing onto every enqueued message ───────────


async def test_orchestrator_stamps_billing_on_all_summary_messages():
    enqueued: list[SummarizeMessage] = []

    async def _capture(msg):
        enqueued.append(msg)
        return "id"

    # Lightweight stub — enqueue only reads these four path attributes.
    from types import SimpleNamespace
    hp = SimpleNamespace(
        book_id=str(uuid4()), book_path="book",
        chapter_id=str(uuid4()), chapter_path="book/chapter-1",
    )
    await enqueue_chapter_and_maybe_book_summaries(
        summary_enqueue=_capture,
        hierarchy_paths=hp,
        user_id=_OWNER,
        project_id=str(uuid4()),
        job_id=str(uuid4()),
        model_ref="owner-llm",
        embedding_model_uuid="project-emb-tag",
        embedding_dimension=1024,
        is_last_chapter_of_book=True,
        book_parts=[(str(uuid4()), "book/part-1", "0")],
        billing_user_id=_COLLAB,
        billing_llm_model="collab-llm",
        billing_embedding_model="collab-emb",
    )
    # chapter + 1 part + book = 3 messages, all carrying billing.
    assert len(enqueued) == 3
    for m in enqueued:
        assert m.billing_user_id == _COLLAB
        assert m.billing_llm_model == "collab-llm"
        assert m.billing_embedding_model == "collab-emb"
        assert m.embedding_model_uuid == "project-emb-tag"  # storage tag intact
