"""The material packet survives a reload — and says when it has gone stale.

Why it is persisted at all: the search SPENDS the author's budget. Throwing the result away when they
close the panel means re-opening pays for it again, and a review surface you cannot leave and come
back to is not a review surface.

Why `stale` matters more than the persistence: the packet is computed FROM a spec. A keep, a refine
or a re-propose moves the spec on, and a packet about a plan that no longer exists is the same class
of lie as every other one this cycle removed. It is still returned — those are the author's own words
— but it is labelled.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.plan_forge_service import PlanForgeService


class _Runs:
    def __init__(self, spec_id, packet=None, packet_spec_id=None):
        self.spec_id = spec_id
        self.packet = packet
        self.packet_spec_id = packet_spec_id
        self.saved: list[tuple[str, dict]] = []

    async def get_for_book(self, book_id, run_id):
        return SimpleNamespace(id=run_id, source_markdown="# doc\nsome prose\n")

    async def latest_artifact(self, book_id, run_id, kind):
        if kind == "spec":
            return SimpleNamespace(id=self.spec_id, content={"meta": {}, "layers": {}},
                                   created_at=datetime.now(timezone.utc))
        if kind == "material_review" and self.packet is not None:
            body = {**self.packet, "spec_artifact_id": str(self.packet_spec_id)}
            return SimpleNamespace(id=uuid4(), content=body,
                                   created_at=datetime.now(timezone.utc))
        return None

    async def save_artifact(self, created_by, run_id, kind, content):
        self.saved.append((kind, content))
        return SimpleNamespace(id=uuid4())


def _svc(runs):
    svc = PlanForgeService.__new__(PlanForgeService)
    svc._runs = runs  # type: ignore[attr-defined]
    return svc


async def test_a_run_that_was_never_checked_returns_NOTHING_not_an_empty_packet():
    """"Never checked" and "checked and found nothing" are different facts. A `{}` collapses them,
    and the panel would render "nothing missing" for a plan nobody ever looked at."""
    out = await _svc(_Runs(spec_id=uuid4())).get_material_review(uuid4(), uuid4(), uuid4())
    assert out is None


async def test_a_packet_computed_from_THIS_spec_is_not_stale():
    sid = uuid4()
    runs = _Runs(spec_id=sid, packet={"review": [], "ask": []}, packet_spec_id=sid)
    out = await _svc(runs).get_material_review(uuid4(), uuid4(), uuid4())
    assert out["stale"] is False
    assert out["computed_at"], "the author should be able to see HOW OLD the answer is"


async def test_a_packet_from_an_OLDER_spec_is_returned_but_LABELLED():
    """Not hidden: the candidates are still the author's own words and still worth seeing. Labelled:
    silently reviewing a plan that has moved on is the lie."""
    runs = _Runs(spec_id=uuid4(), packet={"review": [{"kind": "mechanics"}]},
                 packet_spec_id=uuid4())
    out = await _svc(runs).get_material_review(uuid4(), uuid4(), uuid4())
    assert out["stale"] is True
    assert out["review"] == [{"kind": "mechanics"}], "a stale packet is still shown"


async def test_the_READ_never_searches_and_never_spends():
    """The panel does this on mount. If it could spend, opening the planner would bill the author."""
    runs = _Runs(spec_id=uuid4(), packet={"review": []}, packet_spec_id=uuid4())
    svc = _svc(runs)
    svc._llm = None  # type: ignore[attr-defined]  # any LLM use would raise
    out = await svc.get_material_review(uuid4(), uuid4(), uuid4())
    assert out is not None and runs.saved == [], "the free read wrote or spent something"


async def test_the_SEARCH_persists_its_packet_stamped_with_the_spec():
    """Without the stamp there is no way to tell a fresh packet from one about an older plan."""
    import app.services.plan_forge_service as mod

    sid = uuid4()
    runs = _Runs(spec_id=sid)
    svc = _svc(runs)
    svc._llm = object()  # type: ignore[attr-defined]

    async def _fake_engine(*_a, **_k):
        return {"version": 1, "recovered": [], "review": [], "ask": [], "unavailable": [],
                "read": {}}

    async def _fake_resolve(self, created_by, model_ref):
        return uuid4()

    orig_engine, orig_resolve = mod.engine_find_missing_material, PlanForgeService._resolve_model_ref
    mod.engine_find_missing_material = _fake_engine
    PlanForgeService._resolve_model_ref = _fake_resolve  # type: ignore[assignment]
    try:
        out = await svc.find_missing_material(uuid4(), uuid4(), uuid4())
    finally:
        mod.engine_find_missing_material = orig_engine
        PlanForgeService._resolve_model_ref = orig_resolve  # type: ignore[assignment]

    assert out["spec_artifact_id"] == str(sid)
    assert [k for k, _ in runs.saved] == ["material_review"]
    assert runs.saved[0][1]["spec_artifact_id"] == str(sid)


def test_the_artifact_kind_is_in_BOTH_closed_sets():
    """The Literal and the DB CHECK are in different files and drifted once before — a kind missing
    from the Literal made every package-reading pass unrunnable, invisibly."""
    import pathlib

    from app.db.models import PlanArtifactKind
    from typing import get_args

    assert "material_review" in get_args(PlanArtifactKind)
    sql = pathlib.Path(mod_path()).read_text(encoding="utf-8")
    assert "'material_review'" in sql, "the DB CHECK would reject every write"


def mod_path() -> str:
    import app.db.migrate as m
    return m.__file__
