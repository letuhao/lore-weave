"""Repository-layer shared types.

D-K8-03 optimistic-concurrency errors live here so both the projects
and summaries repos can raise them and the routers can catch them
without importing each repo's module. C9 (D-K19d-γa-01) extended
``current`` to also cover Neo4j :Entity writes; we avoid importing
Entity here to skirt the neo4j_repos ↔ repositories import cycle and
instead type it structurally (the router casts to the type it knows
it put in).
"""

from typing import Any


class VersionMismatchError(Exception):
    """Raised by repository update() methods when the caller's
    expected_version does not match the row's current version.

    Carries the current row so the router can return it in the 412
    response body — the client uses it to refresh its baseline
    without making a second GET.

    ``current`` is typed ``Any`` to accommodate Project / Summary /
    Entity without pulling Entity across the Postgres / Neo4j
    repo-module boundary. Callers that catch this know which type
    they raised and cast accordingly.
    """

    def __init__(self, current: Any) -> None:
        super().__init__("version mismatch")
        self.current = current


__all__ = ["VersionMismatchError"]
