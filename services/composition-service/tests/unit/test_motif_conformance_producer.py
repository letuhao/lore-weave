"""D-MOTIF-CONFORMANCE-ENGINE-WIRING — producer wiring (fakes only, no DB).

Proves maybe_conformance_patch:
  - is OFF by default (motif_conformance_enabled=False → None, zero hot-path cost);
  - judges a bound, high-tension scene → returns a {"motif_conformance": dim} patch;
  - returns None when the scene has no bound motif (nothing to conform to);
  - respects the sampling gate (a low-tension non-high-weight scene at 0% → None);
  - stamps `calibrated` from config (the honest-label flag);
  - is degrade-safe — a judge failure still yields an advisory dim, never raises.
"""

from __future__ import annotations

import uuid

import pytest

from app.config import settings
from app.db.models import Motif, MotifApplication
from app.db.repositories.motif_repo import MotifRepo
from app.engine import motif_conformance_producer as prod
from app.packer.profile import NEUTRAL

USER = str(uuid.uuid4())
PROJECT = str(uuid.uuid4())
NODE = str(uuid.uuid4())
MOTIF_ID = uuid.uuid4()


class _FakeJob:
    def __init__(self, content, status="completed"):
        self.status = status
        self.result = {"messages": [{"content": content}]}


class _FakeJudge:
    """Returns one canned conformance verdict (or a non-completed job)."""

    def __init__(self, content='{"beat_realized": true, "tension_band_match": false, "reason": "ok"}',
                 status="completed"):
        self._content = content
        self._status = status
        self.calls = 0

    async def submit_and_wait(self, **kwargs):
        self.calls += 1
        return _FakeJob(self._content, self._status)


class _Rng:
    def __init__(self, v):
        self._v = v

    def random(self):
        return self._v


def _motif() -> Motif:
    return Motif(
        id=MOTIF_ID, owner_user_id=None, code="cultivation.face_slap", name="Face-Slap",
        beats=[{"key": "reversal", "label": "Reversal", "intent": "the mocker is publicly broken",
                "tension_target": 5, "order": 1}],
        roles=[{"key": "protagonist", "actant": "subject", "label": "the underestimated one"},
               {"key": "arrogant", "actant": "opponent", "label": "the arrogant genius"}],
        tension_target=4,
    )


def _app(beat_key="reversal") -> MotifApplication:
    return MotifApplication(
        id=uuid.uuid4(), created_by=uuid.UUID(USER), project_id=uuid.UUID(PROJECT),
        book_id=uuid.uuid4(), motif_id=MOTIF_ID, motif_version=1,
        outline_node_id=uuid.UUID(NODE), role_bindings={}, annotations={"beat_key": beat_key},
    )


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    # default-on for these tests; the disabled-path test flips it back off.
    monkeypatch.setattr(settings, "motif_conformance_enabled", True, raising=False)
    monkeypatch.setattr(settings, "motif_conformance_calibrated", False, raising=False)
    monkeypatch.setattr(settings, "motif_conformance_sample_random_pct", 20, raising=False)
    # patch the two DB-touching seams so no Postgres is needed.
    async def _fake_resolve(pool, p, n):
        return _app()
    monkeypatch.setattr(prod, "resolve_bound_application", _fake_resolve)

    async def _fake_get_visible(self, caller_id, motif_id):
        return _motif()
    monkeypatch.setattr(MotifRepo, "get_visible", _fake_get_visible)


async def _run(judge, *, tension=90, beat_role="reversal", rng=None):
    return await prod.maybe_conformance_patch(
        object(), judge, user_id=USER, project_id=PROJECT, profile=NEUTRAL,
        final_text="The arrogant heir was thrown from the dais before the whole sect.",
        outline_node_id=NODE, beat_role=beat_role, tension=tension,
        model_source="user_model", model_ref="m-ref", rng=rng,
    )


async def test_off_by_default_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "motif_conformance_enabled", False, raising=False)
    judge = _FakeJudge()
    assert await _run(judge) is None
    assert judge.calls == 0  # zero hot-path cost when disabled


async def test_judges_bound_high_tension_scene():
    judge = _FakeJudge()
    patch = await _run(judge, tension=90)
    assert judge.calls == 1
    assert patch is not None and "motif_conformance" in patch
    dim = patch["motif_conformance"]
    assert dim["beat_realized"] is True
    assert dim["tension_band_match"] is False
    assert dim["motif_id"] == str(MOTIF_ID)
    assert dim["beat_key"] == "reversal"
    assert dim["calibrated"] is False  # honest label until a human flips it


async def test_no_bound_motif_returns_none(monkeypatch):
    async def _none(pool, u, p, n):
        return None
    monkeypatch.setattr(prod, "resolve_bound_application", _none)
    judge = _FakeJudge()
    assert await _run(judge) is None
    assert judge.calls == 0


async def test_sampling_declines_low_tension_filler():
    # low tension + non-high-weight beat + rng above the sample cut → not judged.
    judge = _FakeJudge()
    patch = await _run(judge, tension=10, beat_role="filler", rng=_Rng(0.99))
    assert patch is None and judge.calls == 0


async def test_calibrated_flag_from_config(monkeypatch):
    monkeypatch.setattr(settings, "motif_conformance_calibrated", True, raising=False)
    patch = await _run(_FakeJudge(), tension=90)
    assert patch["motif_conformance"]["calibrated"] is True


async def test_judge_degrade_still_advisory_dim():
    # a non-completed judge job → judge_motif_conformance degrades to an empty verdict
    # + error; the producer still returns the advisory dim (shown, not dropped).
    patch = await _run(_FakeJudge(status="failed"), tension=90)
    assert patch is not None
    dim = patch["motif_conformance"]
    assert dim["beat_realized"] is None
    assert "error" in dim


async def test_resolution_failure_degrades_to_none(monkeypatch):
    async def _boom(pool, u, p, n):
        raise RuntimeError("db down")
    monkeypatch.setattr(prod, "resolve_bound_application", _boom)
    # must NOT raise — advisory degrade.
    assert await _run(_FakeJudge(), tension=90) is None
