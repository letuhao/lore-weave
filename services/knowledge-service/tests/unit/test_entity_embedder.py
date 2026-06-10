"""K17 unit tests — entity_embedder producer.

Mocks the repo (find_entities_needing_embedding, set_entity_embedding) + the
embedding/glossary clients to verify, without a live database:

  - happy path: candidates → glossary text → one batch embed → set per entity.
  - glossary read degrades → KG-local name+aliases fallback (still embeds).
  - embed failure → embed_failed=True, no writes.
  - no candidates → no embed/set calls.
  - dim mismatch on a returned vector → that entity skipped.
  - build_embed_text composition.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.clients.embedding_client import EmbeddingError, EmbeddingResult
from app.extraction.entity_embedder import (
    build_embed_text,
    embed_project_entities,
)

_PATCH = "app.extraction.entity_embedder"
USER = uuid4()
PROJECT = uuid4()
BOOK = uuid4()
MODEL = "user-model-uuid"
DIM = 1024


def _entity(eid: str, name: str, gid: str | None = "g-" + "x", version: int = 1):
    return SimpleNamespace(
        id=eid, name=name, aliases=[], version=version, glossary_entity_id=gid,
    )


def _gloss(gid: str, name: str, desc: str | None):
    return SimpleNamespace(
        entity_id=gid, cached_name=name, cached_aliases=[], short_description=desc,
    )


def _embed_result(n: int, dim: int = DIM):
    return EmbeddingResult(embeddings=[[0.1] * dim for _ in range(n)], dimension=dim, model=MODEL)


def _clients(embed_return=None, embed_raise=None, gloss_rows=None, gloss_raise=False):
    ec = MagicMock()
    if embed_raise is not None:
        ec.embed = AsyncMock(side_effect=embed_raise)
    else:
        ec.embed = AsyncMock(return_value=embed_return)
    gc = MagicMock()
    if gloss_raise:
        gc.fetch_entities_by_ids = AsyncMock(side_effect=RuntimeError("glossary down"))
    else:
        gc.fetch_entities_by_ids = AsyncMock(return_value=gloss_rows or [])
    return ec, gc


# ── build_embed_text ────────────────────────────────────────────────────


def test_build_embed_text_composes_name_aliases_desc():
    assert build_embed_text("姜子牙", ["子牙", "太公"], "封神榜执行者") == "姜子牙 子牙 太公 封神榜执行者"
    assert build_embed_text("Kai", None, None) == "Kai"
    assert build_embed_text(None, [], None) == ""


# ── embed_project_entities ───────────────────────────────────────────────


@pytest.mark.asyncio
@patch(f"{_PATCH}.set_entity_embedding", new_callable=AsyncMock)
@patch(f"{_PATCH}.find_entities_needing_embedding", new_callable=AsyncMock)
async def test_happy_path_embeds_each_candidate(mock_find, mock_set):
    mock_find.return_value = [_entity("e1", "Kai", "g1", 2), _entity("e2", "Mira", "g2", 1)]
    mock_set.return_value = True
    ec, gc = _clients(
        embed_return=_embed_result(2),
        gloss_rows=[_gloss("g1", "Kai", "a wanderer"), _gloss("g2", "Mira", "a healer")],
    )

    res = await embed_project_entities(
        MagicMock(), ec, gc,
        user_id=USER, project_id=PROJECT, book_id=BOOK,
        embedding_model=MODEL, embedding_dim=DIM,
    )

    assert res.candidates == 2
    assert res.embedded == 2
    assert res.skipped == 0
    # one batch embed for both texts; glossary text used.
    ec.embed.assert_awaited_once()
    assert ec.embed.call_args.kwargs["texts"] == ["Kai a wanderer", "Mira a healer"]
    # embedding_version stamped = the entity's version.
    versions = sorted(c.kwargs["embedding_version"] for c in mock_set.call_args_list)
    assert versions == [1, 2]


@pytest.mark.asyncio
@patch(f"{_PATCH}.set_entity_embedding", new_callable=AsyncMock)
@patch(f"{_PATCH}.find_entities_needing_embedding", new_callable=AsyncMock)
async def test_glossary_degrades_to_kg_local_text(mock_find, mock_set):
    mock_find.return_value = [_entity("e1", "Kai", "g1", 1)]
    mock_set.return_value = True
    ec, gc = _clients(embed_return=_embed_result(1), gloss_raise=True)

    res = await embed_project_entities(
        MagicMock(), ec, gc,
        user_id=USER, project_id=PROJECT, book_id=BOOK,
        embedding_model=MODEL, embedding_dim=DIM,
    )

    assert res.embedded == 1
    # glossary raised → KG-local fallback: name only.
    assert ec.embed.call_args.kwargs["texts"] == ["Kai"]


@pytest.mark.asyncio
@patch(f"{_PATCH}.set_entity_embedding", new_callable=AsyncMock)
@patch(f"{_PATCH}.find_entities_needing_embedding", new_callable=AsyncMock)
async def test_embed_failure_writes_nothing(mock_find, mock_set):
    mock_find.return_value = [_entity("e1", "Kai", "g1", 1)]
    ec, gc = _clients(embed_raise=EmbeddingError("provider down"), gloss_rows=[_gloss("g1", "Kai", "d")])

    res = await embed_project_entities(
        MagicMock(), ec, gc,
        user_id=USER, project_id=PROJECT, book_id=BOOK,
        embedding_model=MODEL, embedding_dim=DIM,
    )

    assert res.embed_failed is True
    assert res.embedded == 0
    mock_set.assert_not_awaited()


@pytest.mark.asyncio
@patch(f"{_PATCH}.set_entity_embedding", new_callable=AsyncMock)
@patch(f"{_PATCH}.find_entities_needing_embedding", new_callable=AsyncMock)
async def test_no_candidates_no_calls(mock_find, mock_set):
    mock_find.return_value = []
    ec, gc = _clients(embed_return=_embed_result(0))

    res = await embed_project_entities(
        MagicMock(), ec, gc,
        user_id=USER, project_id=PROJECT, book_id=BOOK,
        embedding_model=MODEL, embedding_dim=DIM,
    )

    assert res.candidates == 0
    assert res.embedded == 0
    ec.embed.assert_not_awaited()
    mock_set.assert_not_awaited()


@pytest.mark.asyncio
@patch(f"{_PATCH}.set_entity_embedding", new_callable=AsyncMock)
@patch(f"{_PATCH}.find_entities_needing_embedding", new_callable=AsyncMock)
async def test_dim_mismatch_vector_skipped(mock_find, mock_set):
    mock_find.return_value = [_entity("e1", "Kai", "g1", 1)]
    mock_set.return_value = True
    # embed returns a 512-dim vector but we asked for 1024 → skip that entity.
    ec, gc = _clients(embed_return=_embed_result(1, dim=512), gloss_rows=[_gloss("g1", "Kai", "d")])

    res = await embed_project_entities(
        MagicMock(), ec, gc,
        user_id=USER, project_id=PROJECT, book_id=BOOK,
        embedding_model=MODEL, embedding_dim=DIM,
    )

    assert res.embedded == 0
    assert res.skipped == 1
    mock_set.assert_not_awaited()


@pytest.mark.asyncio
@patch(f"{_PATCH}.find_entities_needing_embedding", new_callable=AsyncMock)
async def test_unsupported_dim_returns_early(mock_find):
    ec, gc = _clients(embed_return=_embed_result(0))
    res = await embed_project_entities(
        MagicMock(), ec, gc,
        user_id=USER, project_id=PROJECT, book_id=BOOK,
        embedding_model=MODEL, embedding_dim=999,  # not in SUPPORTED_VECTOR_DIMS
    )
    assert res.candidates == 0
    mock_find.assert_not_awaited()
