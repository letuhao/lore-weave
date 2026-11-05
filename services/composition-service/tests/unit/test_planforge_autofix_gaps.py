"""#302 defect #2 — self_check must surface the HARD COMPILE GATES unconditionally,
with a real spec path refine can target, or the autofix button cannot fix the exact
thing blocking the compile.

The old `if not gaps:` gating in `PlanForgeService.self_check` added the hard rules
ONLY when own-document coverage produced nothing — which is never true on a real
braindump. So a run whose spec had zero events showed the author coverage advice
while `compile` refused on `spec_has_events`, and "Fix the top gaps automatically"
fixed everything except the blocker. Worse, the hard-rule gap carried the RULE ID in
`path` (`spec_has_events`), so refine was pointed at a spec location that does not
exist.

These tests pin, on a spec that fails `spec_has_arc`/`spec_has_events` WHILE its
document coverage also reports a gap:
  • the blocking rules are PRESENT despite non-empty coverage gaps (the regression);
  • they rank FIRST, severity `error` (compile refuses on exactly these);
  • `path` is the real spec section (`arcs` / `events`), not the rule id;
  • `handoff_autofix` therefore aims `focus_paths` at those real paths.
Coverage is stubbed at the module boundary (run_self_check_on_document) — its
engine is PF-19's own suite, not the subject here.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.plan_forge_service import PlanForgeService

_USER, _BOOK, _RUN = uuid4(), uuid4(), uuid4()

# A spec that fails BOTH general hard gates — the issue's measured shape (a
# rules-mode Propose that wrote zero events).
_EMPTY_SPEC = {"arcs": [], "events": [], "layers": {}}


class _StubRuns:
    async def get_for_book(self, book_id, run_id):
        return SimpleNamespace(
            id=run_id, book_id=book_id, status="ready", mode="llm", model_ref=None,
            source_checksum="abc", is_archived=False, created_by=_USER,
            source_markdown="# Braindump\n\nsome real notes", active_job_id=None,
            grounded_on=None, error_detail=None, checkpoint_state=None, genre_tags=[],
            pass_state={}, created_at=None, updated_at=None,
        )

    async def latest_artifact(self, book_id, run_id, kind):
        if kind == "preflight":
            return None
        return SimpleNamespace(content=_EMPTY_SPEC)

    async def list_artifact_refs(self, book_id, run_id):
        return []


def _service(monkeypatch) -> PlanForgeService:
    svc = PlanForgeService(_StubRuns(), jobs=AsyncMock(), works=AsyncMock())
    svc._resolve_model_ref = AsyncMock(return_value=uuid4())
    svc.refine = AsyncMock(return_value=("sync", {"status": "applied"}))
    # The coverage engine is stubbed at the boundary: it reports ONE warn gap, which
    # is exactly the condition under which the old code discarded the hard rules.
    monkeypatch.setattr(
        "app.services.plan_forge_service.run_self_check_on_document",
        lambda spec, doc, cfg: {"fidelity": {"score": 0.5},
                                 "ranked_gaps": [{"id": "chars_missing", "severity": "warn",
                                                  "detail": "add the cast"}]},
    )
    return svc


@pytest.mark.asyncio
async def test_hard_gates_surface_despite_coverage_gaps(monkeypatch):
    svc = _service(monkeypatch)
    out = await svc.self_check(_USER, _BOOK, _RUN)
    gaps = out["gaps"]

    blocking = [g for g in gaps if g["path"] in ("arcs", "events")]
    assert blocking, (
        "hard compile gates missing from self_check gaps while coverage reported "
        "advice — the autofix button fixes everything except the compile blocker (#302)"
    )
    # They rank FIRST (autofix takes the top-5) and carry error severity: these are
    # the rules compile refuses on, not advice.
    assert gaps[0]["path"] == "arcs" and gaps[0]["severity"] == "error"
    assert gaps[1]["path"] == "events" and gaps[1]["severity"] == "error"
    # The rule ID is NOT in the path — refine gets a spec location it can act on.
    assert all(g["path"] != "spec_has_events" and g["path"] != "spec_has_arc" for g in gaps)
    # The coverage advice is still there, behind the blockers.
    assert any(g["path"] == "chars_missing" for g in gaps)


@pytest.mark.asyncio
async def test_autofix_focus_paths_are_real_spec_sections(monkeypatch):
    svc = _service(monkeypatch)
    await svc.handoff_autofix(_USER, _BOOK, _RUN, model_ref=None, max_rounds=1)

    svc.refine.assert_awaited_once()
    revision = svc.refine.await_args.kwargs["revision"]
    assert revision["focus_paths"][:2] == ["arcs", "events"], (
        "autofix must aim refine at the real spec sections the blocking rules name — "
        "not at a rule id like spec_has_events (#302)"
    )
