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
    def __init__(self, spec=None):
        self._spec = spec if spec is not None else _EMPTY_SPEC

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
        return SimpleNamespace(content=self._spec)

    async def list_artifact_refs(self, book_id, run_id):
        return []


def _service(monkeypatch, spec=None, coverage_gaps=None) -> PlanForgeService:
    svc = PlanForgeService(_StubRuns(spec), jobs=AsyncMock(), works=AsyncMock())
    svc._resolve_model_ref = AsyncMock(return_value=uuid4())
    svc.refine = AsyncMock(return_value=("sync", {"status": "applied"}))
    # The coverage engine is stubbed at the boundary: it reports ONE warn gap, which
    # is exactly the condition under which the old code discarded the hard rules.
    if coverage_gaps is None:
        coverage_gaps = [{"id": "chars_missing", "severity": "warn", "detail": "add the cast"}]
    monkeypatch.setattr(
        "app.services.plan_forge_service.run_self_check_on_document",
        lambda spec, doc, cfg: {"fidelity": {"score": 0.5},
                                 "ranked_gaps": coverage_gaps},
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


# ── #323 Codex review ─────────────────────────────────────────────────────────
# P2 — consistency-audit criticals are STRINGS (elaborate.consistency_audit
# appends "Title: <diagnostic>"), but self_check consumed them as dicts
# (`c.get("field")` / `c.get("issue")`). The parent only reached that loop
# when coverage produced nothing, so the crash was rare; #323 made the loop
# unconditional, so a run WITH ranked gaps AND an audit critical now aborts
# self_check (and handoff_autofix with it) instead of returning the coverage
# gaps. The string diagnostic must surface as the gap message.
_AUDIT_SPEC = {
    "arcs": [{"id": "arc_1", "title": "Arc One"}, {"id": "arc_2", "title": "Arc Two"}],
    "events": [
        {"id": "ev_1", "arc_id": "arc_2", "title": "Arc Two Event",
         "synopsis": "The THR is giải thích here, far too early"},
    ],
    "layers": {},
    "charter": {"forbids": ["explain"]},
}


@pytest.mark.asyncio
async def test_audit_critical_string_does_not_crash_self_check(monkeypatch):
    svc = _service(monkeypatch, spec=_AUDIT_SPEC)
    out = await svc.self_check(_USER, _BOOK, _RUN)
    critical = [g for g in out["gaps"] if g["severity"] == "error"]
    assert any("THR explained too early" in g["message"] for g in critical), (
        "consistency_audit returns strings; self_check must surface the string "
        "diagnostic as the gap message instead of crashing on c.get() (#323)"
    )
    # The coverage advice is still there — the audit critical must not displace it.
    assert any(g["path"] == "chars_missing" for g in out["gaps"])


# P2 — `every_arc_has_events` is advisory, so #323's hard-only filter dropped
# it. With no per-run fidelity rubric the coverage engine reports no ranked
# gaps, the hard gates pass (arcs and events exist — just all in arc_2), and
# self_check answered `gaps: []` ("No gaps") for a plan whose arc_1 cannot
# compile (E4 zero-nodes-linked). The parent's `if not gaps:` fallback DID
# surface the empty arc. The general advisory failures with a real spec target
# must be preserved behind the blockers.
_EMPTY_ARC_SPEC = {
    "arcs": [{"id": "arc_1", "title": "Arc One"}, {"id": "arc_2", "title": "Arc Two"}],
    "events": [
        {"id": "ev_1", "arc_id": "arc_2", "title": "Arc Two Event", "synopsis": "s1"},
    ],
    "layers": {},
}


@pytest.mark.asyncio
async def test_advisory_empty_arc_gap_preserved_without_rubric(monkeypatch):
    # No rubric -> the stubbed coverage engine reports no ranked gaps at all.
    svc = _service(monkeypatch, spec=_EMPTY_ARC_SPEC, coverage_gaps=[])
    out = await svc.self_check(_USER, _BOOK, _RUN)
    advisory = [g for g in out["gaps"] if g["severity"] == "warn"]
    assert any(
        g["path"] == "events" and "arc_1" in g["message"] for g in advisory
    ), (
        "a spec with all events in arc_2 must still report the empty arc_1 as a "
        "warn gap on the real 'events' section — not gaps: [] (#323)"
    )
