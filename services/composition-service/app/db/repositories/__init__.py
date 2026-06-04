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


def rows_changed(status: str) -> int:
    """Parse an asyncpg command tag like 'UPDATE 1' / 'DELETE 0' safely."""
    try:
        return int(status.rsplit(" ", 1)[-1])
    except ValueError:
        return 0


__all__ = ["VersionMismatchError", "rows_changed"]
