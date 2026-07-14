"""WS-5.20/5.21 — coaching_rubrics resolver + server-authoritative dimension coercion.

Real Postgres (the seeded System rubric). Proves: the active rubric resolves; a
server-authoritative Scorecard dimension set is rebuilt from the RUBRIC's keys (model can't
drop/invent); and NO rubric for a code ⇒ None (the caller refuses to score, P5-D5).
"""
import os

import asyncpg
import pytest

from app.services.coaching_rubrics import (
    CoachingRubric, RubricDimension, coerce_dimensions, resolve_active_rubric,
)

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")


@pytest.fixture
async def pool():
    try:
        p = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    except Exception:
        pytest.skip("dev postgres unreachable")
    async with p.acquire() as c:
        await c.execute("""
            CREATE TABLE IF NOT EXISTS coaching_rubrics (
              rubric_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
              code TEXT NOT NULL, version INT NOT NULL DEFAULT 1, label TEXT NOT NULL,
              dimensions JSONB NOT NULL, source_citation TEXT NOT NULL DEFAULT '',
              license TEXT NOT NULL DEFAULT '',
              tier TEXT NOT NULL DEFAULT 'quarantine' CHECK (tier IN ('quarantine','validated')),
              is_active BOOLEAN NOT NULL DEFAULT true, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              UNIQUE (code, version))
        """)
        await c.execute("""
            INSERT INTO coaching_rubrics (code, version, label, dimensions, tier)
            VALUES ('interview_v1', 1, 'Behavioral interview (STAR)',
              '[{"key":"star_structure","label":"STAR structure","anchors":{"1":"none","5":"complete"}},
                {"key":"clarity","label":"Clarity","anchors":{"1":"unclear","5":"crisp"}},
                {"key":"specificity","label":"Specificity","anchors":{"1":"vague","5":"concrete"}}]'::jsonb,
              'quarantine')
            ON CONFLICT (code, version) DO NOTHING
        """)
    yield p
    await p.close()


@pytest.mark.asyncio
async def test_resolves_active_system_rubric(pool):
    r = await resolve_active_rubric(pool, "interview_v1")
    assert isinstance(r, CoachingRubric)
    assert {d.key for d in r.dimensions} == {"star_structure", "clarity", "specificity"}
    assert r.tier == "quarantine"


@pytest.mark.asyncio
async def test_unknown_code_returns_none_so_caller_refuses(pool):
    assert await resolve_active_rubric(pool, "no_such_rubric") is None


def test_coerce_dimensions_is_server_authoritative():
    rubric = CoachingRubric("x", 1, "X", (
        RubricDimension("clarity", "Clarity", {}),
        RubricDimension("specificity", "Specificity", {}),
    ), "quarantine")
    raw = {"dimensions": [
        {"key": "clarity", "score": 4, "note": "clear"},
        {"key": "invented", "score": 5},          # not in rubric → ignored
        # 'specificity' omitted by the model → scored None, not dropped
    ]}
    dims = coerce_dimensions(raw, rubric)
    keys = [d["key"] for d in dims]
    assert keys == ["clarity", "specificity"]     # rubric order, invented dropped
    assert dims[0]["score"] == 4
    assert dims[1]["score"] is None               # omitted → None, dimension kept


def test_coerce_clamps_and_rejects_bool_score():
    rubric = CoachingRubric("x", 1, "X", (RubricDimension("clarity", "Clarity", {}),), "quarantine")
    assert coerce_dimensions({"dimensions": [{"key": "clarity", "score": 9}]}, rubric)[0]["score"] == 5
    assert coerce_dimensions({"dimensions": [{"key": "clarity", "score": True}]}, rubric)[0]["score"] is None


# ── WS-5.23 — coaching-KB citation resolution (no DB needed) ──────────────────
def test_unresolved_citations_blocks_dangling_and_blank():
    from app.services.coaching_rubrics import unresolved_citations
    known = {"STAR method", "GROW model"}
    cites = ["STAR method", "made-up framework", "  ", "GROW model"]
    bad = unresolved_citations(cites, lambda c: c in known)
    assert bad == ["made-up framework", "  "]  # dangling + blank block sign-off


def test_unresolved_citations_fails_closed_on_resolver_error():
    from app.services.coaching_rubrics import unresolved_citations
    def _boom(_c):
        raise RuntimeError("resolver down")
    assert unresolved_citations(["anything"], _boom) == ["anything"]  # error => unresolved
