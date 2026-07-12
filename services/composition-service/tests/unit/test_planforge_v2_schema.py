"""27 V2-A (Stage 6) — the compiler's schema, and the ONE non-additive change in it.

These are CONTRACT tests over the DDL text + the models that mirror it. The live DDL runs in
the integration suite; what is pinned here is the thing that goes wrong SILENTLY:

  • a CHECK re-added WITHOUT its historical values makes existing rows unwritable
    (`migration-check-constraint-must-backfill-all-historical-blocks` — this repo has shipped it);
  • a model Literal that drifts from the CHECK it mirrors is a 422 on a legal row, or a 500 on a
    write the DB would have taken. Nothing in CI compares the two — so this does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.db.models import PlanArtifactKind, PlanRunStatus

MIGRATE = (Path(__file__).resolve().parents[2] / "app" / "db" / "migrate.py").read_text(
    encoding="utf-8"
)


def _check_values(constraint: str) -> set[str]:
    """The literal set inside `CONSTRAINT <name> CHECK (... IN ('a','b',...))` in the DDL."""
    m = re.search(
        rf"ADD CONSTRAINT {constraint} CHECK \(\s*\w+ IN \((.*?)\)\s*\)",
        MIGRATE,
        re.S,
    )
    assert m, f"{constraint} not found in migrate.py"
    return set(re.findall(r"'([a-z_]+)'", m.group(1)))


def _literal_values(lit) -> set[str]:
    return set(lit.__args__)


# ── A1: the two CHECK swaps must WIDEN, never narrow ──────────────────────────

# Every value the schema accepted BEFORE 27 V2-A. Dropping any one of these in the re-add
# would make historical rows unwritable — the exact bug this repo has shipped before.
V1_STATUSES = {"pending", "proposed", "checkpoint", "validated", "compiled", "failed"}
V1_ARTIFACT_KINDS = {
    "document", "analyze", "spec", "graph", "package", "llm_io", "validation_report",
}


def test_status_check_keeps_every_v1_value_and_adds_planned():
    db = _check_values("plan_run_status_chk")
    assert V1_STATUSES <= db, f"a v1 status was DROPPED by the re-add: {V1_STATUSES - db}"
    assert "planned" in db


def test_artifact_kind_check_keeps_every_v1_kind_and_adds_the_pass_kinds():
    db = _check_values("plan_artifact_kind_chk")
    assert V1_ARTIFACT_KINDS <= db, f"a v1 kind was DROPPED: {V1_ARTIFACT_KINDS - db}"
    for k in (
        "motif_plan", "cast_plan", "world_plan", "beat_plan", "char_arc_plan",
        "scene_plan", "heal_report", "link_report",
    ):
        assert k in db, f"pass artifact kind {k} missing from the CHECK"


# ── the model MIRRORS the CHECK (nothing else compares them) ───────────────────


def test_PlanRunStatus_literal_matches_the_db_check_exactly():
    assert _literal_values(PlanRunStatus) == _check_values("plan_run_status_chk")


def test_PlanArtifactKind_literal_matches_the_db_check_exactly():
    assert _literal_values(PlanArtifactKind) == _check_values("plan_artifact_kind_chk")


# ── A3: the ONE non-additive change (25 M6.1) ─────────────────────────────────


def test_the_old_chapter_required_check_is_dropped_and_replaced_by_name():
    # DA-10: a rule that no longer REQUIRES anything must not keep the name "required".
    assert "DROP CONSTRAINT IF EXISTS outline_chapter_required" in MIGRATE
    assert "ADD CONSTRAINT outline_chapter_written_kinds" in MIGRATE


def test_the_new_check_permits_a_planned_but_unwritten_node():
    """PF-8: the compiler links planned nodes BEFORE any manuscript chapter exists. The old CHECK
    (`chapter_id IS NOT NULL` for chapter/scene) made EVERY skeleton-link insert fail. The new one
    inverts it: chapter_id is now 'written' provenance that only chapter/scene kinds may carry."""
    m = re.search(
        r"ADD CONSTRAINT outline_chapter_written_kinds\s*\n?\s*CHECK \((.*?)\);", MIGRATE, re.S
    )
    assert m
    body = " ".join(m.group(1).split())
    # NULL chapter_id is now legal for ANY kind ⇒ "planned, not yet written" is representable.
    assert body.startswith("chapter_id IS NULL OR")
    assert "kind IN ('chapter', 'scene')" in body


def test_the_check_swap_has_a_PRE_FLIGHT_that_nulls_stray_rows():
    """The new CHECK forbids a chapter_id on any kind other than chapter/scene. No writer sets one
    today — but a single stray historical row makes the ADD CONSTRAINT fail at startup, taking the
    service down. The pre-flight NULLs them in the SAME transaction, so the constraint is PROVEN
    rather than hoped for."""
    i_pre = MIGRATE.find("UPDATE outline_node SET chapter_id = NULL")
    i_add = MIGRATE.find("ADD CONSTRAINT outline_chapter_written_kinds")
    assert i_pre != -1, "no pre-flight before the CHECK swap"
    assert i_pre < i_add, "the pre-flight must run BEFORE the constraint is added"
    pre = MIGRATE[i_pre : i_pre + 200]
    assert "kind NOT IN ('chapter', 'scene')" in pre


# ── A2: provenance + the idempotency the linker depends on ────────────────────


@pytest.mark.parametrize(
    "table,cols",
    [
        ("structure_node", ["plan_run_id", "plan_arc_id"]),
        ("outline_node", ["plan_run_id", "plan_event_id"]),
    ],
)
def test_provenance_columns_exist(table, cols):
    for c in cols:
        assert f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {c}" in MIGRATE


@pytest.mark.parametrize(
    "index", ["uq_structure_node_plan_prov", "uq_outline_node_plan_prov"]
)
def test_provenance_unique_exempts_soft_deleted_rows(index):
    """The partial UNIQUE is what makes the linker idempotent (a re-run re-links the same plan node
    onto the same row instead of duplicating it). It MUST exempt tombstones: without `NOT
    is_archived`, archiving a linked node and re-linking would collide with its own tombstone and
    the re-link would fail forever (`partial-unique-index-must-exempt-soft-delete-tombstones`)."""
    m = re.search(rf"CREATE UNIQUE INDEX IF NOT EXISTS {index}(.*?);", MIGRATE, re.S)
    assert m, f"{index} not found"
    assert "NOT is_archived" in m.group(1)


def test_pass_state_and_genre_tags_are_on_plan_run():
    assert "ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS pass_state JSONB" in MIGRATE
    assert "ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS genre_tags JSONB" in MIGRATE
