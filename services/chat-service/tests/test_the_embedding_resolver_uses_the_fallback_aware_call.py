"""D-A-TOOL-REACHES-THE-WIRE-WITHOUT-ITS-DOMAINS-GUIDANCE.

`_resolve_embedding_model` (tool_discovery.py) is the ONE chokepoint both the intent-skill
router (skill_router.py) and the semantic tool search go through to find an embedding-capable
model. It called `get_default_model("embedding", user_id)` — 404s unless the user EXPLICITLY set
an 'embedding' default. Measured 2026-08-28 against the live deployment: zero accounts, ever, had
one set, while 7 active embedding-capable models existed across the platform (including two on
this loop's own test account) — so the intent router, the SOLE fallback for domain-skill
injection once `lazy_skill_bodies` (the default) is on, has never fired for anyone.

FIXED: `_resolve_embedding_model` now calls `resolve_embedding_model`, which falls back
server-side to the user's best active embedding-capable model (provider-registry's
`internalResolveEmbeddingModel`, mirroring the pre-existing `internalResolvePlannerModel`
fallback pattern) when no explicit default is set.
"""
from __future__ import annotations

import ast
import pathlib

SRC_PATH = pathlib.Path(__file__).resolve().parents[1].joinpath(
    "app", "services", "tool_discovery.py")
SRC = SRC_PATH.read_text(encoding="utf-8")


def _resolver_body() -> str:
    """The function's CODE only — excludes the docstring, which names the OLD call for
    context and would otherwise trip test_the_chokepoint_does_NOT_call_the_strict_no_
    fallback_method on its own explanatory prose rather than on real code."""
    tree = ast.parse(SRC)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_resolve_embedding_model")
    stmts = fn.body[1:] if ast.get_docstring(fn) else fn.body
    return "\n".join(ast.get_source_segment(SRC, st) or "" for st in stmts)


def test_the_chokepoint_calls_the_fallback_aware_method():
    body = _resolver_body()
    assert "resolve_embedding_model(user_id)" in body, (
        "_resolve_embedding_model no longer calls the fallback-aware client method"
    )


def test_the_chokepoint_does_NOT_call_the_strict_no_fallback_method():
    """The strict method is still correct for OTHER capabilities (chat, rerank, planner,
    distill, critic) — it must simply never be reached from HERE again, or the fix silently
    regresses to the 404-unless-explicitly-set behaviour this row measured as dead for
    every account."""
    body = _resolver_body()
    assert 'get_default_model("embedding"' not in body
    assert "get_default_model('embedding'" not in body
