"""Repository-layer shared types.

D-K8-03 optimistic-concurrency errors live here so both the projects
and summaries repos can raise them and the routers can catch them
without importing each repo's module.
"""

from app.db.models import Project, Summary


class VersionMismatchError(Exception):
    """Raised by repository update() methods when the caller's
    expected_version does not match the row's current version.

    Carries the current row so the router can return it in the 412
    response body — the client uses it to refresh its baseline
    without making a second GET.
    """

    def __init__(self, current: Project | Summary) -> None:
        super().__init__("version mismatch")
        self.current = current


__all__ = ["VersionMismatchError"]
