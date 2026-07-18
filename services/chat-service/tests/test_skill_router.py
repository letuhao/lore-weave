"""Tests for skill_router (Part F / F2, docs/plans/2026-07-07-intent-skill-
router.md) — the embedding-similarity Intent→Skill Router, unit-tested in
isolation from `resolve_skills_to_inject_async` (see test_skill_registry.py's
`TestResolveSkillsToInjectAsyncRouter` for the wiring-level tests)."""
from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, patch

import pytest

from app.client.embedding_client import EmbeddingResult
from app.services import skill_router as router
from app.services.skill_registry import SYSTEM_SKILLS


def _fake_embed_fixed_map(text_vectors: dict[str, list[float]], default: list[float]):
    """Mirrors test_tool_discovery.py's helper of the same name — maps known
    texts to fixed vectors; any unmapped text (the fresh per-call intent
    string) gets `default`."""

    async def _embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[text_vectors.get(t, default) for t in texts],
            dimension=len(default),
            model="fake-embed-model",
        )

    return _embed


class TestRouteAdditionalSkills:
    def setup_method(self, _method):
        router.reset_skill_vector_cache()

    @pytest.mark.asyncio
    async def test_blank_intent_returns_no_additions_without_embedding(self):
        mock_client = AsyncMock()
        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            additions = await router.route_additional_skills(
                intent_text="   ",
                active_surface={"chat"},
                already_selected=["universal", "knowledge"],
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert additions == []
        mock_client.embed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_additive_union_adds_a_skill_the_static_path_missed(self):
        """A translation-shaped intent on the book surface, where `translation`
        is visible but never auto-injected — the router should surface it
        without touching the static defaults already in `already_selected`."""
        translation_text = router._skill_embedding_text("translation")
        text_vectors = {translation_text: [1.0, 0.0]}
        # Every OTHER skill's own text embeds orthogonally so only translation
        # clears the threshold against the intent vector below.
        fake_embed = _fake_embed_fixed_map(text_vectors, default=[0.0, 1.0])
        mock_client = AsyncMock()

        async def _embed(*, user_id, model_source, model_ref, texts):
            # The single fresh per-call INTENT text is never one of the fixed
            # skill texts — map it to the SAME vector as translation's so it
            # scores a perfect match, while every other skill's own already-
            # cached vector stays orthogonal (default=[0.0, 1.0]).
            if texts == [_intent]:
                return EmbeddingResult(embeddings=[[1.0, 0.0]], dimension=2, model="fake")
            return await fake_embed(user_id=user_id, model_source=model_source, model_ref=model_ref, texts=texts)

        _intent = "please translate chapter 3 into vietnamese"
        mock_client.embed.side_effect = _embed

        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            additions = await router.route_additional_skills(
                intent_text=_intent,
                active_surface={"book"},
                already_selected=["glossary", "knowledge"],
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert additions == ["translation"]
        # Never re-adds anything already selected, even if it also scores high.
        assert "glossary" not in additions and "knowledge" not in additions

    @pytest.mark.asyncio
    async def test_never_removes_or_duplicates_already_selected(self):
        mock_client = AsyncMock()
        mock_client.embed.side_effect = _fake_embed_fixed_map({}, default=[1.0, 0.0])
        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            additions = await router.route_additional_skills(
                intent_text="anything at all",
                active_surface={"book", "editor"},
                already_selected=list(SYSTEM_SKILLS.keys()),  # everything already selected
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        # Nothing left to add — every candidate is already in already_selected.
        assert additions == []

    @pytest.mark.asyncio
    async def test_surfaces_filtering_never_suggests_an_invisible_skill(self):
        """`glossary` (surfaces={"book","editor"}) must never be suggested on
        the plain chat surface, no matter how high its cosine score is — the
        router narrows WITHIN `surfaces`, it never widens it."""
        mock_client = AsyncMock()
        # Every skill vector (including glossary's) is a perfect match for the
        # intent vector — the ONLY thing that can exclude glossary here is the
        # surface filter.
        mock_client.embed.side_effect = _fake_embed_fixed_map({}, default=[1.0, 0.0])
        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            additions = await router.route_additional_skills(
                intent_text="anything",
                active_surface={"chat"},
                already_selected=["universal"],
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert "glossary" not in additions
        assert "plan_forge" not in additions
        assert "book" not in additions
        # settings/jobs ARE visible on chat — confirm the filter isn't
        # over-excluding, only under-including invisible skills.
        assert "settings" in additions
        assert "jobs" in additions

    @pytest.mark.asyncio
    async def test_below_threshold_score_is_not_added(self):
        mock_client = AsyncMock()

        async def _embed(*, user_id, model_source, model_ref, texts):
            # Every SKILL vector is [1.0, 0.0]; the INTENT vector (the lone
            # single-text call) is the orthogonal [0.0, 1.0] — cosine
            # similarity 0.0 against every skill, well under
            # ROUTER_CONFIDENCE_THRESHOLD.
            vec = [0.0, 1.0] if texts == ["something ambiguous"] else [1.0, 0.0]
            return EmbeddingResult(
                embeddings=[vec for _ in texts], dimension=2, model="fake",
            )

        mock_client.embed.side_effect = _embed
        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            additions = await router.route_additional_skills(
                intent_text="something ambiguous",
                active_surface={"book", "editor", "studio", "chat"},
                already_selected=["universal"],
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert additions == []

    @pytest.mark.asyncio
    async def test_embedding_client_exception_falls_back_to_empty_additions(self):
        """MANDATORY fallback: an embedding-client failure must yield NO
        additions — never an error, never a partial/garbage result."""
        mock_client = AsyncMock()
        mock_client.embed.side_effect = TimeoutError("provider-registry unreachable")
        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            additions = await router.route_additional_skills(
                intent_text="translate my chapter",
                active_surface={"book", "editor"},
                already_selected=[],
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert additions == []

    @pytest.mark.asyncio
    async def test_skill_vector_embed_succeeds_but_intent_embed_fails_still_falls_back(self):
        calls = {"n": 0}

        async def flaky_embed(*, user_id, model_source, model_ref, texts):
            calls["n"] += 1
            if calls["n"] == 1:
                return EmbeddingResult(
                    embeddings=[[1.0, 0.0] for _ in texts], dimension=2, model="fake",
                )
            raise TimeoutError("intent embed timed out")

        mock_client = AsyncMock()
        mock_client.embed.side_effect = flaky_embed
        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            additions = await router.route_additional_skills(
                intent_text="translate my chapter",
                active_surface={"book", "editor"},
                already_selected=[],
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert additions == []

    @pytest.mark.asyncio
    async def test_skill_vectors_are_cached_only_intent_reembedded_on_a_second_call(self):
        embed_calls: list[list[str]] = []

        async def fake_embed(*, user_id, model_source, model_ref, texts):
            embed_calls.append(list(texts))
            return EmbeddingResult(
                embeddings=[[1.0, 0.0] for _ in texts], dimension=2, model="fake",
            )

        mock_client = AsyncMock()
        mock_client.embed.side_effect = fake_embed
        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            await router.route_additional_skills(
                intent_text="one",
                active_surface={"book", "editor", "studio", "chat"},
                already_selected=[],
                user_id="u1", model_source="user_model", model_ref="m1",
            )
            await router.route_additional_skills(
                intent_text="two",
                active_surface={"book", "editor", "studio", "chat"},
                already_selected=[],
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        # Call 1: skill-vector batch embed (one call, N texts) + intent embed = 2.
        # Call 2: skill-vector cache HIT (SYSTEM_SKILLS signature unchanged) →
        # only the fresh intent embed = 1 more call. Total 3, not 4.
        assert len(embed_calls) == 3
        assert len(embed_calls[0]) == len(SYSTEM_SKILLS)  # the batch call
        assert embed_calls[1] == ["one"]
        assert embed_calls[2] == ["two"]


class TestRouterConfidenceThresholdBounds:
    """Cheap sanity-bound (review-impl finding): `ROUTER_CONFIDENCE_THRESHOLD`
    must sit strictly inside (0.0, 1.0) — a future accidental edit to 0.0
    (inject every skill, unconditionally) or 1.0 (permanent no-op, nothing
    ever clears a perfect-cosine-1.0 bar) would otherwise silently pass every
    existing mocked-score test in this file (they all fix the scores they
    feed in, so they never actually exercise the constant's own value)."""

    def test_threshold_sits_strictly_between_0_and_1(self):
        assert 0.0 < router.ROUTER_CONFIDENCE_THRESHOLD < 1.0


class TestSkillVectorCacheSignatureIsCodeTupleOnly:
    """Accepted tradeoff (review-impl finding, NOT a bug): the skill-vector
    cache signature (`_skill_catalog_signature()`) is the sorted tuple of
    SKILL CODES only — never a hash of each skill's description text. A
    description-only edit to an existing `SkillDef` (code unchanged) does NOT
    invalidate the cache, so the router keeps scoring against the STALE
    embedded text until the process restarts or `SYSTEM_SKILLS` gains/loses a
    code. Acceptable because `SYSTEM_SKILLS` is a small, rarely-edited static
    registry (~11-15 skills), not a live per-user catalog (see the module
    docstring's own rationale). This test documents the tradeoff explicitly so
    it reads as a deliberate decision, not an untested oversight."""

    def setup_method(self, _method):
        router.reset_skill_vector_cache()

    @pytest.mark.asyncio
    async def test_description_only_change_does_not_trigger_a_fresh_skill_vector_embed(self):
        embed_calls: list[list[str]] = []

        async def fake_embed(*, user_id, model_source, model_ref, texts):
            embed_calls.append(list(texts))
            return EmbeddingResult(
                embeddings=[[1.0, 0.0] for _ in texts], dimension=2, model="fake",
            )

        mock_client = AsyncMock()
        mock_client.embed.side_effect = fake_embed

        original = SYSTEM_SKILLS["universal"]
        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            await router.route_additional_skills(
                intent_text="one", active_surface={"chat"}, already_selected=[],
                user_id="u1", model_source="user_model", model_ref="m1",
            )
            # Mutate ONLY the description of an existing skill — its `code` is
            # unchanged, so `_skill_catalog_signature()` (sorted codes only)
            # must NOT invalidate the cache.
            SYSTEM_SKILLS["universal"] = dataclasses.replace(
                original, description="A totally different description text.",
            )
            try:
                await router.route_additional_skills(
                    intent_text="two", active_surface={"chat"}, already_selected=[],
                    user_id="u1", model_source="user_model", model_ref="m1",
                )
            finally:
                SYSTEM_SKILLS["universal"] = original

        # Only ONE batch call (N-texts) — the second route_additional_skills
        # call hit the cache and only re-embedded the fresh per-call intent
        # text, never a new skill-vector batch reflecting the mutated
        # description.
        batch_calls = [c for c in embed_calls if len(c) == len(SYSTEM_SKILLS)]
        assert len(batch_calls) == 1
