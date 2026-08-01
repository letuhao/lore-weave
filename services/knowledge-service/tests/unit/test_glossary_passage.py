"""Glossary → :Passage producer — the rendering contract and every degrade path.

`source_type='glossary'` was a declared KNOWN_SOURCE_TYPES member with no producer, so
authored lore was never semantically retrievable and a book whose glossary was built
before chapter 1 had an EMPTY lore lens. These prove the producer builds real content
and, just as importantly, that it never claims success when it indexed nothing.
"""
from __future__ import annotations

import json

import pytest

from app.clients.embedding_client import EmbeddingError
from app.extraction.glossary_passage import (
    MAX_PASSAGE_CHARS,
    render_glossary_passage,
    sync_glossary_entity_passage,
)


# ── rendering ────────────────────────────────────────────────────────────────

def test_render_carries_the_attribute_VALUES_not_just_identity():
    """The whole bug: a passage built from name+kind alone is the empty-lore state
    with extra steps."""
    text = render_glossary_passage(
        name="Chân Linh", kind="power_system", aliases=["Mỏ neo bản thể"],
        short_description="Tầng sâu nhất của thần hồn.",
        attributes=[
            {"code": "effects", "label": "Effects", "field_type": "textarea",
             "value": "Bất biến qua trùng sinh."},
            {"code": "rank", "label": "Rank", "field_type": "text", "value": "Tối thượng"},
        ],
    )
    assert "Chân Linh (power_system)" in text
    assert "Bất biến qua trùng sinh." in text
    assert "Effects:" in text and "Rank:" in text


def test_render_flattens_a_tags_value_instead_of_embedding_json_brackets():
    """A `tags` value is stored as a JSON-encoded array string. Embedding the literal
    `["a","b"]` puts brackets and escapes into the vector."""
    text = render_glossary_passage(
        name="X", kind="item", aliases=None, short_description=None,
        attributes=[{"code": "materials", "label": "Materials", "field_type": "tags",
                     "value": json.dumps(["Hắc Thiết", "Tinh Thạch"], ensure_ascii=False)}],
    )
    assert "Hắc Thiết, Tinh Thạch" in text
    assert "[" not in text and '\\"' not in text


def test_render_drops_every_restatement_of_the_name_whatever_its_code():
    """The identity field is not always `name` — `terminology` calls it `term`. A
    code-based skip list is the same schema-blindness that put character fields on
    every kind, so the drop is by VALUE."""
    text = render_glossary_passage(
        name="Luyện khí", kind="terminology", aliases=None,
        short_description="Terminology: Luyện khí",   # a generated stub, pure restatement
        attributes=[
            {"code": "term", "label": "Term", "field_type": "text", "value": "Luyện khí"},
            {"code": "category", "label": "Category", "field_type": "text",
             "value": "Kỹ thuật tu luyện"},
        ],
    )
    assert text.count("Luyện khí") == 1          # the header, and nowhere else
    assert "Terminology:" not in text            # the stub never reaches the vector
    assert "Category: Kỹ thuật tu luyện" in text


def test_render_prefers_the_full_description_over_its_truncated_summary():
    """short_description is DERIVED from `description`, so emitting both duplicates the
    prose — and the derived form is truncated, so equality would not catch it."""
    full = "Thiếu chủ dòng chính Lâm gia, mang Vô Cấu Chân Linh bất biến qua trùng sinh."
    text = render_glossary_passage(
        name="Lâm Uyên", kind="character", aliases=["Thiếu chủ"],
        short_description="Thiếu chủ dòng chính Lâm gia, mang Vô Cấu…",
        attributes=[{"code": "description", "label": "Description",
                     "field_type": "textarea", "value": full}],
    )
    assert full in text
    assert "…" not in text


def test_render_falls_back_to_the_summary_when_there_are_no_attributes():
    """An entity with nothing authored yet still deserves a retrievable line."""
    text = render_glossary_passage(
        name="Tô gia", kind="organization", aliases=None,
        short_description="Một gia tộc tu chân quyền thế.", attributes=[],
    )
    assert "Một gia tộc tu chân quyền thế." in text


def test_render_truncates_rather_than_silently_growing_unbounded():
    text = render_glossary_passage(
        name="X", kind="item", aliases=None, short_description=None,
        attributes=[{"code": "description", "label": "D", "field_type": "textarea",
                     "value": "a" * (MAX_PASSAGE_CHARS * 2)}],
    )
    assert len(text) == MAX_PASSAGE_CHARS


# ── degrade paths ────────────────────────────────────────────────────────────

class _FakeEmbed:
    def __init__(self, vectors=None, raises=False):
        self._vectors, self._raises, self.calls = vectors, raises, 0

    async def embed(self, **_kw):
        self.calls += 1
        if self._raises:
            raise EmbeddingError("provider down")
        return type("R", (), {"embeddings": self._vectors})()


class _FakeSession:
    """Records upserts; `existing_hash` simulates an already-indexed passage."""

    def __init__(self, existing_hash: str | None = None):
        self.existing_hash, self.queries = existing_hash, []

    async def run(self, _cypher, **params):
        self.queries.append(params)
        holder = self

        class _Result:
            async def single(self):
                return {"h": holder.existing_hash} if holder.existing_hash else None

        return _Result()


async def _sync(session, embed, **over):
    kwargs = dict(
        user_id="u", project_id="p", glossary_entity_id="e", text="Chân Linh\nEffects: x",
        embedding_model="bge-m3", embedding_dim=1024,
    )
    kwargs.update(over)
    return await sync_glossary_entity_passage(session, embed, **kwargs)


@pytest.mark.asyncio
async def test_no_embedding_model_is_REPORTED_not_swallowed():
    """A project with no embedding model has UN-INDEXED lore. Returning a success-ish
    None would hide exactly the state the author needs to act on."""
    embed = _FakeEmbed()
    assert await _sync(_FakeSession(), embed, embedding_model=None) == "no_embedding_model"
    assert embed.calls == 0


@pytest.mark.asyncio
async def test_unsupported_dim_is_reported_and_never_embeds():
    embed = _FakeEmbed()
    assert await _sync(_FakeSession(), embed, embedding_dim=7) == "unsupported_dim"
    assert embed.calls == 0


@pytest.mark.asyncio
async def test_a_provider_failure_degrades_instead_of_raising():
    """The :Entity SSOT sync must never fail because indexing did."""
    assert await _sync(_FakeSession(), _FakeEmbed(raises=True)) == "embed_failed"


@pytest.mark.asyncio
async def test_unchanged_content_does_not_re_embed():
    """glossary.entity_updated is at-least-once and the backfill walks every entity —
    without the hash check both pay a provider call per entity per run."""
    import hashlib
    text = "Chân Linh\nEffects: x"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    embed = _FakeEmbed(vectors=[[0.1] * 1024])
    assert await _sync(_FakeSession(existing_hash=digest), embed, text=text) == "unchanged"
    assert embed.calls == 0


@pytest.mark.asyncio
async def test_a_dim_mismatch_from_the_provider_is_caught_before_the_write():
    embed = _FakeEmbed(vectors=[[0.1] * 384])
    assert await _sync(_FakeSession(), embed, embedding_dim=1024) == "unsupported_dim"


@pytest.mark.asyncio
async def test_empty_text_never_writes_a_hollow_passage():
    assert await _sync(_FakeSession(), _FakeEmbed(), text="   ") == "empty"
