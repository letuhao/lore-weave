"""P4 — the ground_on_existing effective gate (deploy ceiling AND per-run flag), schema, wiring."""

from __future__ import annotations

import inspect

from app.config import Settings
from app.routers.plan_forge import PlanRunCreate
from app.services import plan_forge_service as pfs


def test_deploy_ceiling_FLIPPED_ON_after_the_ab_eval_passed():
    # OQ-2: the ceiling flips ON once the A/B eval proves grounding helps — it did (2/3 vs 0/3, two
    # runs; A1 injection deterministic). Grounding is now AVAILABLE org-wide, still opt-in + fails-closed
    # (effective = AND(ceiling, per-run flag); the per-user toggle defaults OFF).
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.planforge_ground_on_existing_allowed is True


def test_PlanRunCreate_declares_ground_on_existing_defaulting_false():
    # explicitly declared (never rely on extra='ignore' — the rest-write-mirror-drops-fields bug)
    assert "ground_on_existing" in PlanRunCreate.model_fields
    assert PlanRunCreate(source_markdown="x", mode="rules").ground_on_existing is False
    assert PlanRunCreate(source_markdown="x", mode="rules", ground_on_existing=True).ground_on_existing is True


def test_effective_is_the_AND_of_ceiling_and_flag():
    src = inspect.getsource(pfs.PlanForgeService.create_run)
    # effective = AND(deploy_allows, user_enables) — the ceiling is a MAX, not a per-user knob
    assert "settings.planforge_ground_on_existing_allowed and ground_on_existing" in src
    # and the gather only fires when effective (never on a blind/ceiling-off run)
    assert "if effective_ground:" in src


def test_the_run_records_grounded_on_when_state_was_folded_in():
    src = inspect.getsource(pfs.PlanForgeService.create_run)
    # grounded_on is persisted with the fingerprint (reproducibility) — only when non-empty
    assert "if existing_state is not None and not existing_state.is_empty():" in src
    assert "grounded_on=" in src
    assert "existing_state.grounded_fingerprint" in src


def test_llm_rich_grounding_supersedes_the_arc_only_digest_no_double_listing():
    src = inspect.getsource(pfs.PlanForgeService.create_run)
    # when effective, prepend the structured block; ELSE the O-1 baseline — never both (no double arcs)
    assert "render_existing_state_prompt(existing_state)" in src
    assert "self._ground_llm_source(book_id, text)" in src  # baseline still there for the off path


def test_rules_path_threads_existing_into_propose_spec():
    src = inspect.getsource(pfs.PlanForgeService._finalize_rules_propose)
    assert "propose_spec(doc, existing=existing" in src  # A1 added inject_cast_max=; keep the prefix loose


def test_latest_artifact_for_book_keeps_the_a_prefix_because_it_JOINs():
    """The JOIN to plan_run (which also has an `id`) makes a bare `id` in the SELECT AMBIGUOUS — a
    500 the unit suite can't see (it never hits real SQL; caught only by the live A/B measurement).
    Guard: the JOIN query must select the `a.`-qualified columns, NOT save_artifact's stripped form."""
    from app.db.repositories import plan_runs
    src = inspect.getsource(plan_runs.PlanRunsRepo.latest_artifact_for_book)
    assert "JOIN plan_run r" in src
    assert '_SELECT_ARTIFACT.replace("a.", "")' not in src  # the stripped form is ambiguous under a JOIN
    assert "{_SELECT_ARTIFACT}" in src                       # keep the a.-prefixed columns


def test_grounded_on_is_nullable_end_to_end_never_silently_empty():
    from app.db.models import PlanRun
    # the model default is None (not {}), so a blind run is honestly "not grounded"
    assert PlanRun.model_fields["grounded_on"].default is None
    # the repo select + decode carry it
    from app.db.repositories import plan_runs
    assert "grounded_on" in plan_runs._SELECT_RUN
    assert "grounded_on" in inspect.getsource(plan_runs._row_run)
