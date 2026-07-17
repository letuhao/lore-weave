"""P4 — the ground_on_existing effective gate (deploy ceiling AND per-run flag), schema, wiring."""

from __future__ import annotations

import inspect

from app.config import Settings
from app.routers.plan_forge import PlanRunCreate
from app.services import plan_forge_service as pfs


def test_deploy_ceiling_defaults_OFF_so_a_behaviour_change_fails_closed():
    # OQ-2: the richer grounding is gated behind an A/B eval; the default fails CLOSED.
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.planforge_ground_on_existing_allowed is False


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
    assert "propose_spec(doc, existing=existing)" in src


def test_grounded_on_is_nullable_end_to_end_never_silently_empty():
    from app.db.models import PlanRun
    # the model default is None (not {}), so a blind run is honestly "not grounded"
    assert PlanRun.model_fields["grounded_on"].default is None
    # the repo select + decode carry it
    from app.db.repositories import plan_runs
    assert "grounded_on" in plan_runs._SELECT_RUN
    assert "grounded_on" in inspect.getsource(plan_runs._row_run)
