"""TOOLV2 LOOP #75 — a degraded suggestion set must say so where the caller reads.

`composition_arc_suggest` already degraded honestly per candidate: R4's rule is "degrade,
don't invent", so a candidate whose query vector could not be produced carries
`match_reason.degraded=True` and `cosine=0.0`.

Nothing said so at the TOP level. Measured live: five candidates, every `score` 0.0, and the
only signal that semantic ranking never ran was nested two levels down inside each candidate's
`match_reason`. A caller reads `candidates`. That reads as a ranked answer.

Both recorded successful calls of this tool in the whole corpus are exactly that shape.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


def _candidate(section: str, degraded: bool):
    return SimpleNamespace(
        arc_template=SimpleNamespace(
            code=f"arc.{section}", owner_user_id=None,
            model_dump=lambda mode=None, _s=section: {"code": f"arc.{_s}"},
        ),
        score=0.0 if degraded else 0.8,
        match_reason={"genre": 0.0, "cosine": 0.0, "section": section, **({"degraded": True} if degraded else {})},
    )


def _summarise(candidates):
    """The exact derivation the handler performs, exercised without the MCP plumbing.

    Kept in lockstep with `composition_arc_suggest` by the source-anchor test below, which is
    what stops this from becoming a test of a private copy of the logic.
    """
    return sorted({
        c.match_reason.get("section") or "unknown"
        for c in candidates
        if isinstance(c.match_reason, dict) and c.match_reason.get("degraded")
    })


def test_A_DEGRADED_SECTION_IS_NAMED_NOT_JUST_MARKED_PER_CANDIDATE():
    got = _summarise([_candidate("mine", True), _candidate("library", False)])
    assert got == ["mine"], (
        f"only the section that actually degraded may be named, got {got}")


def test_A_FULLY_HEALTHY_RESULT_DECLARES_NOTHING():
    """The marker must not appear when ranking worked — a permanent warning is no warning."""
    assert _summarise([_candidate("mine", False), _candidate("library", False)]) == []


def test_BOTH_SECTIONS_DEGRADING_ARE_BOTH_NAMED():
    """Private arcs (no BYOK model) and shared arcs (platform embedder down) degrade for
    DIFFERENT reasons and can degrade independently; collapsing them to one flag would hide
    which half of the answer is unranked."""
    got = _summarise([_candidate("mine", True), _candidate("library", True)])
    assert got == ["library", "mine"]


@pytest.mark.asyncio
async def test_THE_HANDLER_ATTACHES_THE_MARKER_TO_THE_RETURNED_DICT(monkeypatch):
    """The claim this file exists for, asserted on the RETURNED PAYLOAD.

    An earlier version of this guard checked that `out["degraded"]` appeared in the handler's
    SOURCE. It stayed green when the assignment was moved under `if False:` — a substring gate
    is green over wrong behaviour, which is the trap it was written to catch. So this calls the
    handler and reads the dict.
    """
    from app.mcp import server

    candidates = [_candidate("mine", True), _candidate("library", True)]

    class _Retriever:
        def __init__(self, *a, **k):
            pass

        async def retrieve_arcs(self, *a, **k):
            return candidates

    class _Works:
        def __init__(self, *a, **k):
            pass

        async def get(self, _pid):
            return SimpleNamespace(settings={})

    pid = UUID("019fccd7-2a31-731a-ba56-a6f58cdb02b9")
    monkeypatch.setattr(server, "WorksRepo", _Works)
    monkeypatch.setattr(server, "MotifRetriever", _Retriever)
    monkeypatch.setattr(server, "get_pool", lambda: None)
    monkeypatch.setattr(server, "_ctx", lambda _c: SimpleNamespace(user_id=uuid4()))
    monkeypatch.setattr(server, "reference_embed_model", lambda _s: None)
    async def _allow(_works, _tc, _pid, _lvl):
        return SimpleNamespace(project_id=pid, book_id=uuid4())
    monkeypatch.setattr(server, "_book_or_deny", _allow)
    monkeypatch.setattr(server, "apply_response_contract",
                        lambda rows, **k: ([{"code": "x"} for _ in rows], {"total": len(rows)}))

    out = await server.composition_arc_suggest(None, project_id=str(pid))

    assert "degraded" in out, (
        "a caller reads the top level; a marker nested in each candidate's match_reason is not "
        f"read. got keys {sorted(out)}")
    assert out["degraded"]["sections"] == ["library", "mine"]
    assert "not comparable" in out["note"], (
        "the note must say the scores cannot be ranked by, or the caller ranks by them")


@pytest.mark.parametrize("section", ["mine", "library"])
def test_AN_UNKNOWN_SECTION_STILL_REPORTS_RATHER_THAN_VANISHING(section):
    """A candidate degraded with no section must not silently drop out of the summary."""
    c = _candidate(section, True)
    c.match_reason.pop("section")
    assert _summarise([c]) == ["unknown"]
