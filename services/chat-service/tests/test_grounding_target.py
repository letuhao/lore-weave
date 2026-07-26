"""Track B B1(2) — resolve_grounding_target: the multi-vs-single decision that
threads a session's project SET into the context build.

The ONE new branch the multi-KG path adds over the legacy single-project link:
  * ≥2 ids  → multi union, NO single project_id (salience-misattribution guard)
  * 1 id    → single (salience learns)
  * 0 ids   → legacy single project_id column
"""
from __future__ import annotations

from uuid import uuid4

from app.services.stream_service import resolve_grounding_target


def test_two_or_more_ids_returns_set_and_no_single_project_id():
    """≥2 → (None, [ids]). The single project_id is dropped so the router's
    salience write-back (keyed on req.project_id) can't misattribute the
    multi-union's surfaced entities to one project."""
    a, b = str(uuid4()), str(uuid4())
    row = {"project_ids": [a, b], "project_id": str(uuid4())}
    pid, pids = resolve_grounding_target(row, row["project_id"])
    assert pid is None
    assert pids == [a, b]


def test_single_id_set_is_single_project_path():
    """A set of one is not multi — return it as the single project_id so
    single-project salience still learns."""
    a = str(uuid4())
    row = {"project_ids": [a], "project_id": None}
    pid, pids = resolve_grounding_target(row, None)
    assert pid == a
    assert pids is None


def test_empty_set_falls_back_to_legacy_project_id():
    legacy = str(uuid4())
    row = {"project_ids": [], "project_id": legacy}
    pid, pids = resolve_grounding_target(row, legacy)
    assert pid == legacy
    assert pids is None


def test_no_project_at_all():
    row = {"project_ids": [], "project_id": None}
    pid, pids = resolve_grounding_target(row, None)
    assert pid is None
    assert pids is None


def test_none_row_is_no_project():
    pid, pids = resolve_grounding_target(None, None)
    assert pid is None
    assert pids is None


def test_ids_are_stringified():
    """UUID objects off asyncpg are coerced to str for the JSON body."""
    from uuid import UUID
    a, b = uuid4(), uuid4()
    row = {"project_ids": [a, b], "project_id": None}
    pid, pids = resolve_grounding_target(row, None)
    assert pids == [str(a), str(b)]
    assert all(isinstance(x, str) for x in pids)
