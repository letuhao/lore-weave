"""F3 slice 4 — exact-quote citations on KG evidence.

The EVIDENCED_BY edge now carries the verbatim supporting quote (evidence-
grounding, like the glossary `evidences.original_text`). Assert the write
primitive passes/coalesces the quote, the writer extracts it forward-
compatibly from a candidate, and the read primitive surfaces it.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.graph_repos import provenance as pm
from app.db.graph_repos.provenance import add_evidence, list_evidence_for_target
from app.extraction.pass2_writer import _evidence_quote

_USER = str(uuid4())


def _result(record):
    r = MagicMock()
    r.single = AsyncMock(return_value=record)
    return r


def test_add_evidence_cypher_stores_and_coalesces_quote():
    cy = pm._ADD_EVIDENCE_CYPHER["Fact"]
    # RESTATED (T75): the branches merged into one SET (§10.1). ONE expression now covers
    # both arms — on create the stored side is null so the parameter wins, and on match a
    # quoteless re-run never wipes an existing quote. That is strictly the same rule; it
    # simply cannot be read off a branch keyword any more.
    assert "e.quote = coalesce($quote, e.quote)" in cy
    assert "ON CREATE SET" not in cy and "ON MATCH SET" not in cy, (
        "the merge is supposed to have removed both branch keywords"
    )


@pytest.mark.asyncio
@patch("app.db.graph_repos.provenance.run_read", new_callable=AsyncMock)
@patch("app.db.graph_repos.provenance.run_write", new_callable=AsyncMock)
async def test_add_evidence_passes_quote(mock_run, mock_read):
    # T75: add_evidence now READS first — a pre-MATCH count in the same transaction that
    # replaces the `_just_created` marker. n=0 means "this citation is new".
    mock_read.return_value = _result({"n": 0})
    mock_run.return_value = _result(
        {"evidence_count": 1, "mention_count": 1, "created": True}
    )
    await add_evidence(
        MagicMock(), user_id=_USER, target_label="Fact", target_id="f1",
        source_id="s1", extraction_model="m", confidence=0.9, job_id="j1",
        quote="张若尘 reaches 黄极境",
    )
    assert mock_run.await_args_list[0].kwargs["quote"] == "张若尘 reaches 黄极境"


@pytest.mark.asyncio
@patch("app.db.graph_repos.provenance.run_read", new_callable=AsyncMock)
@patch("app.db.graph_repos.provenance.run_write", new_callable=AsyncMock)
async def test_add_evidence_blank_quote_normalizes_to_none(mock_run, mock_read):
    mock_read.return_value = _result({"n": 0})
    mock_run.return_value = _result(
        {"evidence_count": 1, "mention_count": 1, "created": True}
    )
    await add_evidence(
        MagicMock(), user_id=_USER, target_label="Entity", target_id="e1",
        source_id="s1", extraction_model="m", confidence=0.9, job_id="j1",
        quote="",
    )
    assert mock_run.await_args_list[0].kwargs["quote"] is None


def test_writer_extracts_quote_forward_compatibly():
    """The writer reads a candidate's quote via getattr (quote / evidence_text),
    so it's ready the moment an extractor surfaces one — without a hard SDK dep."""
    assert _evidence_quote(SimpleNamespace(quote="exact span"), None) == "exact span"
    assert _evidence_quote(SimpleNamespace(evidence_text="alt span"), None) == "alt span"
    # candidate with neither field → None (today's behaviour)
    assert _evidence_quote(SimpleNamespace(confidence=0.9), None) is None
    # blank quote → None
    assert _evidence_quote(SimpleNamespace(quote="   "), None) is None


def test_list_evidence_cypher_projects_quote_tenant_scoped():
    cy = pm._LIST_EVIDENCE_CYPHER["Fact"]
    assert "e.quote AS quote" in cy
    assert "target.user_id = $user_id" in cy
    assert "src.user_id = $user_id" in cy
    assert "LIMIT $limit" in cy


@pytest.mark.asyncio
@patch("app.db.graph_repos.provenance.run_read", new_callable=AsyncMock)
async def test_list_evidence_for_target_surfaces_quote(mock_run):
    rows = [{
        "source_id": "src-hash", "source_type": "chapter", "raw_source_id": "ch5",
        "job_id": "j1", "extraction_model": "m", "confidence": 0.9,
        "quote": "the exact supporting span",
    }]

    class _AsyncIter:
        def __aiter__(self):
            async def gen():
                for r in rows:
                    yield r
            return gen()

    mock_run.return_value = _AsyncIter()
    cites = await list_evidence_for_target(
        MagicMock(), user_id=_USER, target_label="Fact", target_id="f1",
    )
    assert len(cites) == 1
    assert cites[0].quote == "the exact supporting span"
    assert cites[0].raw_source_id == "ch5"
