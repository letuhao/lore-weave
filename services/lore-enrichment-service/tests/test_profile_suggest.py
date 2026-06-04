"""AI-suggest profile service tests (C3 / slice 0d, T6).

Pure — the LLM seam is an injected ``async (prompt) -> str``. Covers prompt
assembly (book metadata + samples + KG summary), JSON parsing (incl. fenced),
malformed-override salvage (drop bad kinds, never raise), and the no-JSON error.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.clients.book import BookProjection
from app.services.profile_suggest import (
    ProfileSuggestError,
    SuggestedProfile,
    build_suggest_prompt,
    suggest_profile,
)


def _book(**kw) -> BookProjection:
    base = dict(
        book_id=uuid4(), title="Neon Saigon", original_language="vi",
        description="A near-future cyberpunk thriller.", summary_excerpt="",
        genre_tags=["cyberpunk", "thriller"], chapter_count=42,
    )
    base.update(kw)
    return BookProjection(**base)


# ── prompt assembly ───────────────────────────────────────────────────────────

def test_prompt_includes_metadata_and_kg_and_samples():
    p = build_suggest_prompt(
        book=_book(), sample_texts=["chương một văn bản"],
        kg_summary="Top entities: Mr. Hai, District 9.",
        kinds=("character", "location"),
    )
    assert "Neon Saigon" in p
    assert "cyberpunk" in p
    assert "chương một văn bản" in p
    assert "District 9" in p
    assert "character" in p and "location" in p
    assert "JSON" in p  # JSON-only instruction


def test_prompt_bounds_kg_blob():
    # a huge knowledge-graph context must not bloat the prompt unbounded.
    huge = "x" * 50_000
    p = build_suggest_prompt(book=_book(), sample_texts=[], kg_summary=huge, kinds=("character",))
    assert p.count("x") <= 2000  # _KG_CHARS cap


def test_prompt_book_only_when_kg_empty():
    p = build_suggest_prompt(
        book=_book(), sample_texts=[], kg_summary="", kinds=("character",)
    )
    assert "Neon Saigon" in p
    # no KG block heading when summary is empty
    assert "knowledge graph" not in p.lower() or "Top entities" not in p


# ── suggest_profile ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_suggest_parses_clean_json():
    async def complete(_prompt: str) -> str:
        return (
            '{"worldview": "near-future cyberpunk Saigon", "language": "vi", '
            '"era_policy": "no pre-2040 anachronisms", "voice": "noir", '
            '"dimension_overrides": {"character": {"add": [{"id": "implants", '
            '"label": "Cyberware"}]}}}'
        )
    out = await suggest_profile(book=_book(), sample_texts=[], kg_summary="", complete=complete)
    assert isinstance(out, SuggestedProfile)
    assert out.worldview == "near-future cyberpunk Saigon"
    assert out.language == "vi"
    assert out.era_policy == "no pre-2040 anachronisms"
    assert out.voice == "noir"
    assert out.dimension_overrides["character"]["add"][0]["id"] == "implants"
    assert out.profile_source == "ai_suggested"


@pytest.mark.asyncio
async def test_suggest_handles_fenced_json():
    async def complete(_prompt: str) -> str:
        return '```json\n{"worldview": "x", "language": "en"}\n```'
    out = await suggest_profile(book=_book(), sample_texts=[], kg_summary="", complete=complete)
    assert out.worldview == "x" and out.language == "en"


@pytest.mark.asyncio
async def test_suggest_drops_malformed_overrides_but_keeps_good_ones():
    async def complete(_prompt: str) -> str:
        # 'character' is valid; 'item' has a malformed add (no id) → dropped.
        return (
            '{"worldview": "w", "language": "en", "dimension_overrides": '
            '{"character": {"add": [{"id": "rank", "label": "Rank"}]}, '
            '"item": {"add": [{"label": "no id here"}]}}}'
        )
    out = await suggest_profile(book=_book(), sample_texts=[], kg_summary="", complete=complete)
    assert "character" in out.dimension_overrides
    assert "item" not in out.dimension_overrides  # malformed kind dropped, no raise


@pytest.mark.asyncio
async def test_suggest_no_json_raises():
    async def complete(_prompt: str) -> str:
        return "I'm sorry, I cannot help with that."
    with pytest.raises(ProfileSuggestError):
        await suggest_profile(book=_book(), sample_texts=[], kg_summary="", complete=complete)


@pytest.mark.asyncio
async def test_suggest_defaults_language_auto_when_absent():
    async def complete(_prompt: str) -> str:
        return '{"worldview": "w"}'
    out = await suggest_profile(book=_book(), sample_texts=[], kg_summary="", complete=complete)
    assert out.language == "auto"
    assert out.dimension_overrides == {}
