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


def rows_changed(status: str) -> int:
    """Parse an asyncpg command tag like 'UPDATE 1' / 'DELETE 0' safely."""
    try:
        return int(status.rsplit(" ", 1)[-1])
    except ValueError:
        return 0


__all__ = ["VersionMismatchError", "ReferenceViolationError", "rows_changed"]
