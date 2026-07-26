"""PLAN-ARTIFACT CONTRACT guard (anti-drift) — the BE half.

A pass artifact is a contract that spans two services in two languages: the composition-service
PRODUCES it (`plan_pass_adapters`) and the browser CONSUMES it (`frontend/src/features/plan-forge`).
Nothing machine-checked connected the two, and that gap shipped four real bugs in one track:

  • `beat_plan` — the FE bound to `content.beats`; the producer has NEVER emitted that key (its
    output is {chapters, tension_curve, unmapped_beats}). The blocking checkpoint rendered
    "No beats in this plan yet." on every real run, and an author's edit was written to a field no
    pass reads — while still staling `scenes` and forcing a paid re-run.
  • `cast_plan` — the FE exposed a `trait` column the producer has never emitted, hiding the
    `archetype`/`summary` that actually answer "who is this character?".
  • Both unit suites were GREEN the whole time, because each side asserted the SAME invented shape.
    Tests that encode the consumer's assumption cannot detect that the assumption is wrong.
  • The remaining four kinds fell through to a raw-JSON view, so nobody ever compared them.

So this guard does NOT declare the shapes by hand — a hand-written schema is just a third place to
be wrong. It RUNS THE REAL ADAPTERS (stubbing only the LLM-calling engine underneath, with the
engines' own dataclasses) and snapshots what they actually emit into
`contracts/plan-artifacts.contract.json`, which the FE guard reads.

To intentionally change an artifact shape: change the adapter, then regenerate with
    WRITE_PLAN_ARTIFACT_CONTRACT=1 pytest tests/unit/test_plan_artifact_contract.py
and commit the new JSON alongside the matching FE change. The FE test fails until both agree.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.engine.plan import ChapterPlan, ChapterScenes, DecomposeResult, ScenePlan
from app.services.plan_pass_adapters import PASS_ADAPTERS, PassContext
from app.services.plan_pass_service import PASS_REGISTRY

#: repo-root `contracts/`, NOT `services/contracts/`. parents[4] is the repo root from
#: services/composition-service/tests/unit/. Getting this wrong is self-concealing: the writer and
#: the reader agree on the wrong path, so the BE test passes while the FE guard finds nothing.
CONTRACT_PATH = (
    Path(__file__).resolve().parents[4] / "contracts" / "plan-artifacts.contract.json"
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ── the stubs: ONLY the LLM-calling engine entry points ─────────────────────────────────────────
# Everything below the adapter is faked; the adapter itself — the code that decides the artifact's
# KEYS — is the real thing. That is what makes this snapshot producer-derived rather than declared.

class _Motif:
    code, name, summary, why, arc_role = "m1", "Motif", "s", "w", "central spine"


class _Char:
    name, role, archetype, summary, is_new = "Elara", "protagonist", "cartographer", "sum", False
    traits: list[str] = []
    relationships: list[Any] = []


class _WorldEntity:
    name, kind, summary, is_new = "Oakhaven", "location", "sum", False
    traits: list[str] = []
    relationships: list[Any] = []


class _CharArc:
    name, role, arc, introduce_at_chapter = "Elara", "protagonist", "grows", 2


def _chapter_plan() -> ChapterPlan:
    return ChapterPlan(chapter_id="e1", title="Ch", sort_order=1, beat_role="hook", intent="i")


def _decompose_result() -> DecomposeResult:
    return DecomposeResult(
        arc_title="Arc",
        chapters=[ChapterScenes(
            chapter=_chapter_plan(),
            scenes=[ScenePlan(
                title="S", synopsis="syn", tension=40,
                present_entity_ids=[uuid4()], present_entity_names_unresolved=["X"], suggested_k=2,
            )],
            warning=None,
            exit_state=None,
        )],
        unmapped_beats=["climax"],
        motif_coverage={},
    )


class _HealReport:
    findings: list[Any] = []
    edits_applied = 0


def _install_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.engine.cast_plan as cast_plan
    import app.engine.character_plan as character_plan
    import app.engine.grounded_plan as grounded_plan
    import app.engine.motif_plan as motif_plan
    import app.engine.plan_heal as plan_heal
    import app.engine.world_plan as world_plan

    async def _sel(*a: Any, **k: Any) -> list[Any]:
        return [_Motif()]

    async def _cast(*a: Any, **k: Any) -> list[Any]:
        return [_Char()]

    async def _world(*a: Any, **k: Any) -> list[Any]:
        return [_WorldEntity()]

    async def _beats(*a: Any, **k: Any) -> tuple[Any, list[str], list[Any]]:
        from app.engine.arc_plan import shape_tension_curve
        chs = [_chapter_plan()]
        return chs, ["climax"], shape_tension_curve([c.beat_role for c in chs])

    async def _arcs(*a: Any, **k: Any) -> list[Any]:
        return [_CharArc()]

    async def _decompose(*a: Any, **k: Any) -> DecomposeResult:
        return _decompose_result()

    async def _heal(*a: Any, **k: Any) -> tuple[DecomposeResult, Any]:
        return _decompose_result(), _HealReport()

    monkeypatch.setattr(motif_plan, "select_arc_motifs", _sel)
    monkeypatch.setattr(cast_plan, "propose_cast", _cast)
    monkeypatch.setattr(cast_plan, "cast_attributes", lambda c: {"role": c.role})
    monkeypatch.setattr(world_plan, "propose_world", _world)
    monkeypatch.setattr(world_plan, "world_attributes", lambda e: {"kind": e.kind})
    monkeypatch.setattr(grounded_plan, "map_beats_and_shape", _beats)
    monkeypatch.setattr(character_plan, "plan_character_arcs", _arcs)
    monkeypatch.setattr(grounded_plan, "grounded_decompose", _decompose)
    monkeypatch.setattr(plan_heal, "run_plan_self_heal", _heal)


def _ctx() -> PassContext:
    """A context every pass can read: a package with the fields `PassContext` exposes, plus
    upstream artifacts keyed BY PASS (pass 7 re-emits scene_plan, so kind is not a unique key)."""
    scenes_artifact = {
        "arc_title": "Arc",
        "chapters": [{
            "chapter": {"chapter_id": "e1", "title": "Ch", "sort_order": 1,
                        "beat_role": "hook", "intent": "i"},
            "scenes": [{"title": "S", "synopsis": "syn", "tension": 40,
                        "present_entity_ids": [], "present_entity_names_unresolved": [],
                        "suggested_k": 2}],
            "warning": None, "exit_state": None,
        }],
        "unmapped_beats": [], "motif_coverage": {},
    }
    return PassContext(
        llm=object(), user_id=str(uuid4()), book_id=uuid4(), project_id=uuid4(),
        model_source="user_model", model_ref=str(uuid4()),
        package={
            "premise": "p", "arc_title": "Arc",
            "beats": [{"key": "hook", "label": "Hook", "purpose": "open"}],
            "chapters": [{"title": "Ch", "ordinal": 1, "event_id": "e1"}],
        },
        inputs={
            "motifs": {"motifs": [{"name": "M", "arc_role": "central spine"}]},
            "cast": {"cast": [{"name": "Elara"}]},
            "beats": {"chapters": [{"ordinal": 1, "beat_role": "hook"}],
                      "tension_curve": [{"chapter_index": 1, "beat_role": "hook",
                                         "tension_target": 65}]},
            "character_arcs": {"character_arcs": [{"name": "Elara"}]},
            "scenes": scenes_artifact,
        },
        retriever=object(),
    )


def _row_fields(rows: Any) -> list[str]:
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return []
    return sorted(rows[0].keys())


async def _capture() -> dict[str, Any]:
    """Run every adapter and record the shape it ACTUALLY produced."""
    out: dict[str, Any] = {}
    ctx = _ctx()
    for pass_id, adapter in PASS_ADAPTERS.items():
        body = await adapter(ctx)
        kind = PASS_REGISTRY[pass_id].output_kind
        entry: dict[str, Any] = {
            "produced_by_pass": pass_id,
            "top_level_fields": sorted(body.keys()),
        }
        # The editable list + its row fields — what an FE editor binds to.
        for field in ("cast", "motifs", "entities", "character_arcs", "chapters"):
            if isinstance(body.get(field), list):
                entry["list_field"] = field
                entry["row_fields"] = _row_fields(body[field])
                break
        # scene_plan nests scenes under chapters; the FE editor must know both levels.
        if kind == "scene_plan":
            chapters = body.get("chapters") or []
            if chapters and isinstance(chapters[0], dict):
                entry["nested_list_field"] = "scenes"
                entry["nested_row_fields"] = _row_fields(chapters[0].get("scenes"))
        # A pass may re-emit a kind an earlier pass produced (self_heal → scene_plan). Union the
        # top-level fields so the contract describes what a consumer may EVER see for that kind.
        if kind in out:
            merged = sorted(set(out[kind]["top_level_fields"]) | set(entry["top_level_fields"]))
            out[kind]["top_level_fields"] = merged
            out[kind]["produced_by_pass"] = f"{out[kind]['produced_by_pass']},{pass_id}"
        else:
            out[kind] = entry
    return out


async def test_plan_artifact_contract_matches_the_producers(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_stubs(monkeypatch)
    artifacts = await _capture()
    payload = {
        "_comment": (
            "GENERATED — do not hand-edit. Snapshot of what plan_pass_adapters ACTUALLY emits, "
            "read by the frontend plan-forge contract test. Regenerate with "
            "WRITE_PLAN_ARTIFACT_CONTRACT=1 pytest tests/unit/test_plan_artifact_contract.py"
        ),
        "artifacts": artifacts,
    }

    if os.getenv("WRITE_PLAN_ARTIFACT_CONTRACT"):
        CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")

    assert CONTRACT_PATH.exists(), (
        f"{CONTRACT_PATH} is missing — regenerate with WRITE_PLAN_ARTIFACT_CONTRACT=1"
    )
    committed = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert committed["artifacts"] == artifacts, (
        "plan-artifact shapes drifted from the committed contract. If the change is intentional, "
        "regenerate with WRITE_PLAN_ARTIFACT_CONTRACT=1 AND update the frontend consumers "
        "(PassArtifactView / PassArtifactEditor / ScenePlanEditor) in the same commit."
    )


async def test_every_reviewable_kind_is_in_the_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """A kind an author can review must be described, or the FE guard silently skips it."""
    _install_stubs(monkeypatch)
    artifacts = await _capture()
    declared = {spec.output_kind for spec in PASS_REGISTRY.values()}
    assert declared == set(artifacts), f"missing from contract: {declared - set(artifacts)}"


async def test_the_two_regressions_this_guard_exists_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the exact shapes the FE got wrong, so a revert cannot pass silently."""
    _install_stubs(monkeypatch)
    artifacts = await _capture()

    beat = artifacts["beat_plan"]
    assert beat["list_field"] == "chapters", "the FE bound to a `beats` key that never existed"
    assert "beats" not in beat["top_level_fields"]
    assert "tension_curve" in beat["top_level_fields"]
    assert "available_beats" in beat["top_level_fields"], "the closed set the editor's picker needs"

    cast = artifacts["cast_plan"]
    assert "trait" not in cast["row_fields"], "the FE exposed a `trait` the producer never emits"
    assert {"archetype", "summary"} <= set(cast["row_fields"])
