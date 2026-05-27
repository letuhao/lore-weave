"""P3 — tests for hierarchy_writer.py (D2 + D2a) + neo4j_helpers index helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.neo4j_helpers import ensure_summary_indexes, summary_index_name
from app.extraction.hierarchy_writer import HierarchyPaths, upsert_for_chapter


def _paths(scenes: list[tuple[str, str, int]] | None = None) -> HierarchyPaths:
    return HierarchyPaths(
        book_id="b-1",
        book_path="book",
        book_title="Test Book",
        part_id="p-1",
        part_path="book/part-1",
        part_index=1,
        part_title="Part One",
        chapter_id="c-1",
        chapter_path="book/part-1/chapter-1",
        chapter_index=1,
        chapter_title="Chapter Alpha",
        scenes=scenes if scenes is not None else [
            ("s-1", "book/part-1/chapter-1/scene-1", 1),
            ("s-2", "book/part-1/chapter-1/scene-2", 2),
        ],
    )


# ── hierarchy_writer ────────────────────────────────────────────────────────


async def test_upsert_calls_session_run_with_full_chain_cypher():
    """D2: single Cypher MERGE chain Book -> Part -> Chapter -> Scene."""
    session = MagicMock()
    session.run = AsyncMock()
    result = await upsert_for_chapter(session, _paths())
    assert result["chapter_path"] == "book/part-1/chapter-1"
    assert result["scenes_count"] == 2
    assert result["source_label"] == "Scene"
    session.run.assert_awaited_once()
    cypher = session.run.call_args.args[0]
    # MERGE for each level present.
    assert "MERGE (b:Book {path: $book_path})" in cypher
    assert "MERGE (p:Part {path: $part_path})" in cypher
    assert "MERGE (c:Chapter {path: $chapter_path})" in cypher
    assert "MERGE (s:Scene {path: sc.path})" in cypher
    # HAS_CHILD edges connect parent->child.
    assert "MERGE (b)-[:HAS_CHILD]->(p)" in cypher
    assert "MERGE (p)-[:HAS_CHILD]->(c)" in cypher
    assert "MERGE (c)-[:HAS_CHILD]->(s)" in cypher


async def test_upsert_idempotent_re_call_runs_same_cypher():
    """Re-running with the same paths is safe — MERGE is idempotent."""
    session = MagicMock()
    session.run = AsyncMock()
    await upsert_for_chapter(session, _paths())
    cypher_1 = session.run.call_args.args[0]
    await upsert_for_chapter(session, _paths())
    cypher_2 = session.run.call_args.args[0]
    assert cypher_1 == cypher_2


async def test_upsert_legacy_chapter_no_scenes_returns_chapter_source_label():
    """D6 fallback: chapter without scenes -> source_label='Chapter' so
    pass2_writer knows to target :Chapter instead of :Scene for
    :MENTIONED_IN edges."""
    session = MagicMock()
    session.run = AsyncMock()
    result = await upsert_for_chapter(session, _paths(scenes=[]))
    assert result["source_label"] == "Chapter"
    assert result["scenes_count"] == 0
    # Cypher still runs (creates Book/Part/Chapter without Scene branch).
    session.run.assert_awaited_once()
    # UNWIND on empty list is a no-op in Cypher — Scene MERGE simply doesn't fire.
    cypher_kwargs = session.run.call_args.kwargs
    assert cypher_kwargs["scenes"] == []


async def test_upsert_scene_params_serialize_as_dict_list():
    """Cypher UNWIND $scenes — caller must pass list of {scene_id, path, scene_index}."""
    session = MagicMock()
    session.run = AsyncMock()
    paths = _paths(scenes=[("s-1", "book/part-1/chapter-1/scene-1", 1)])
    await upsert_for_chapter(session, paths)
    cypher_kwargs = session.run.call_args.kwargs
    assert cypher_kwargs["scenes"] == [
        {"scene_id": "s-1", "path": "book/part-1/chapter-1/scene-1", "scene_index": 1},
    ]


async def test_upsert_passes_titles_through_to_cypher():
    """Titles round-trip via parameters; null titles allowed (Cypher SET = null)."""
    session = MagicMock()
    session.run = AsyncMock()
    paths = _paths()
    paths.book_title = None
    paths.part_title = None
    paths.chapter_title = "Just Chapter"
    await upsert_for_chapter(session, paths)
    kwargs = session.run.call_args.kwargs
    assert kwargs["book_title"] is None
    assert kwargs["part_title"] is None
    assert kwargs["chapter_title"] == "Just Chapter"


# ── neo4j_helpers index helpers (H1+M7+SR-2) ────────────────────────────────


def test_summary_index_name_strips_dashes_and_lowercases():
    """Format: <level>_summary_emb_p<32hex>_e<32hex> per D2 H1/M7 fix."""
    name = summary_index_name(
        project_id="019e545F-AAAA-BBBB-CCCC-111111111111",
        embedding_model_uuid="019DC3DF-7CC5-7E6A-8B27-1344E148BF7C",
        level="chapter",
    )
    assert name == (
        "chapter_summary_emb_"
        "p019e545faaaabbbbcccc111111111111_"
        "e019dc3df7cc57e6a8b271344e148bf7c"
    )
    # Length sanity — Neo4j supports long index names.
    assert len(name) < 100


def test_summary_index_name_distinct_per_level():
    name_ch = summary_index_name("p1", "e1", "chapter")
    name_pt = summary_index_name("p1", "e1", "part")
    name_bk = summary_index_name("p1", "e1", "book")
    assert name_ch != name_pt != name_bk
    assert name_ch.startswith("chapter_summary_emb_")
    assert name_pt.startswith("part_summary_emb_")
    assert name_bk.startswith("book_summary_emb_")


def test_summary_index_name_namespace_per_embedding_model_uuid():
    """H1 fix: changing embedding_model produces a NEW index family."""
    name_e1 = summary_index_name("proj-a", "model-1", "chapter")
    name_e2 = summary_index_name("proj-a", "model-2", "chapter")
    assert name_e1 != name_e2


def test_summary_index_name_rejects_unknown_level():
    with pytest.raises(ValueError, match="unknown level"):
        summary_index_name("p1", "e1", "bogus")  # type: ignore[arg-type]


async def test_ensure_summary_indexes_creates_3_indexes():
    """ensure_summary_indexes runs CREATE VECTOR INDEX IF NOT EXISTS × 3."""
    session = MagicMock()
    session.run = AsyncMock()
    names = await ensure_summary_indexes(
        session,
        project_id="p-1",
        embedding_model_uuid="e-1",
        embedding_dimension=1024,
    )
    assert set(names.keys()) == {"chapter", "part", "book"}
    assert session.run.await_count == 3
    # Cypher contains the expected pieces for each call.
    cyphers = [call.args[0] for call in session.run.call_args_list]
    for cy in cyphers:
        assert "CREATE VECTOR INDEX" in cy
        assert "IF NOT EXISTS" in cy
        assert "n.summary_embedding" in cy
        assert "`vector.dimensions`: $dim" in cy
    # Each Cypher targets the correct label.
    assert any("FOR (n:Chapter)" in c for c in cyphers)
    assert any("FOR (n:Part)" in c for c in cyphers)
    assert any("FOR (n:Book)" in c for c in cyphers)


async def test_ensure_summary_indexes_rejects_zero_dimension():
    session = MagicMock()
    with pytest.raises(ValueError, match="invalid embedding_dimension"):
        await ensure_summary_indexes(session, "p", "e", 0)
