"""Repository-layer shared types (composition-service, M2).

`VersionMismatchError` mirrors knowledge-service: the If-Match update() methods
(work / outline / canon_rule) raise it when the caller's `expected_version`
doesn't match the row's current version, carrying the current row so the router
can return it in the 412 body (client refreshes its baseline without a re-GET).
"""

from __future__ import annotations

from typing import Any


class VersionMismatchError(Exception):
    """Raised by repo update() methods on an If-Match version mismatch.

    Carries the current row (CompositionWork / OutlineNode / CanonRule) so the
    router can return it in the 412 response body. Typed `Any` to avoid coupling
    this shared module to every row model.
    """

    def __init__(self, current: Any) -> None:
        super().__init__("version mismatch")
        self.current = current


class ReferenceViolationError(Exception):
    """Raised when a write references an in-DB node that the caller does not own,
    that lives in a different project, or that would form a parent cycle.

    Repo-layer defense-in-depth (D-COMP-M2-XREF-OWNERSHIP): the in-DB FK only
    checks a node EXISTS, not that it belongs to the caller — so without this a
    scene_link / generation_job / reparent could reference another user's node
    (no data leak, but a broken/cross-user edge) or forge a parent cycle. The
    future M3/M7 router can catch this and map it to 400/404/409.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AlreadyPlannedError(Exception):
    """Raised by commit_decomposed_tree when one of the target chapters already
    has active scenes and the caller did not pass replace=true. Carries the
    offending chapter_ids so the router can return them in the 409 body. The
    check + the insert run in ONE transaction (closes the TOCTOU race that a
    pre-transaction guard left open — D-A3-COMMIT-IDEMPOTENCY)."""

    def __init__(self, chapter_ids: list[Any]) -> None:
        super().__init__("chapters already planned")
        self.chapter_ids = chapter_ids


class ChapterJobInFlightError(Exception):
    """Raised by create_chapter_job_guarded when a chapter-level generate/stitch
    is requested while another active (pending/running) chapter-level job already
    exists for the SAME chapter. Chapter generate and stitch both write the same
    book chapter draft, so a concurrent second job would double-spend the LLM and
    race the persist. A per-(project, chapter) advisory xact lock serializes the
    check+create (a plain SELECT is not a lock — the Cycle-1 decompose-commit
    lesson) so even two no-key concurrent submits can't both pass. Carries the
    active job id so the router can return it in the 409 body (FE shows 'already
    generating'). Same-key idempotent replay is honored BEFORE this guard fires."""

    def __init__(self, active_job_id: Any) -> None:
        super().__init__("a chapter-level generation is already in flight")
        self.active_job_id = active_job_id


def rows_changed(status: str) -> int:
    """Parse an asyncpg command tag like 'UPDATE 1' / 'DELETE 0' safely."""
    try:
        return int(status.rsplit(" ", 1)[-1])
    except ValueError:
        return 0


__all__ = [
    "VersionMismatchError", "ReferenceViolationError", "AlreadyPlannedError",
    "ChapterJobInFlightError", "rows_changed",
]
