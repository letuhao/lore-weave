"""The `OntologyStore` port (plan T15).

Read access to the graph ontology — which node kinds, edge types, fact types and
vocabularies a project's extraction and validation run against. The second port, and
deliberately the smallest: it exists to prove the pattern on a low-blast-radius surface
before the `GraphStore` and `TruthStore` ports touch everything.

**A different backend on purpose.** `VectorStore` fronts Neo4j; this fronts Postgres
(`kg_graph_schemas`). If both ports had the same backend, "the pattern works" would be a
claim about Neo4j rather than about the pattern.

── SCOPE: READS ONLY, AND WHY THAT IS NOT A HALF-MEASURE ────────────────────────────────
Ontology WRITES are effects — `adopt_effect`, `schema_edit_effect`, `sync_effect`,
`triage_schema_write_effect` — each with its own transaction, confirm-token and
optimistic-concurrency semantics (KM6 reads `(schema_id, schema_version)` at confirm time
to detect drift since mint). Wrapping those behind a port means porting the transaction
model, not the queries, and the port would end up exposing a connection to keep them
atomic — which is the abstraction failing. They stay where they are.

What that buys is exactly the win the phase is for: the resolver, the routers, the MCP
server and the extraction path all READ the ontology, and none of them needs a database
after this.

── TENANCY IS PART OF THE CONTRACT, NOT THE BACKEND ─────────────────────────────────────
Visibility is scope-keyed: system rows are visible to everyone, user rows only to their
owner, project rows only to a caller that supplies the project id it was grant-checked
for. An implementation that returned another user's `user`-tier schema is broken even if
every signature matches, so the fake enforces it too — see `fake_ontology_store.py`.

`project_id` is caller-supplied and NOT grant-checked here: every caller must do that
first, exactly as they must for the other knowledge repos. Stated on the port because it
is the one rule an implementation cannot enforce, and a rule that lives only in one
adapter's docstring is a rule the next adapter will not know about.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.db.ontology_models import GraphSchema, ResolvedSchema

__all__ = ["OntologyStore"]


@runtime_checkable
class OntologyStore(Protocol):
    """Implementations: `adapters/postgres_ontology_store.py`,
    `adapters/fake_ontology_store.py`."""

    async def list_visible(
        self,
        user_id: UUID,
        *,
        project_id: str | None = None,
        scope: str | None = None,
        include_deprecated: bool = False,
    ) -> list[GraphSchema]:
        """Every schema this caller may see: all system templates, the caller's own user
        templates, and — when `project_id` is given — that project's schema.

        Deprecated rows are excluded by default: a deprecated template is still readable
        by id (an adopted project keeps working) but must not appear in a picker, or a
        user adopts something already withdrawn."""
        ...

    async def get_tree(
        self,
        user_id: UUID,
        schema_id: UUID,
        *,
        project_id: str | None = None,
        include_deprecated: bool = False,
    ) -> GraphSchema | None:
        """One schema with its node kinds, edge types, fact types and vocabularies
        attached. `None` when the id does not exist OR is not visible to this caller —
        the two are deliberately indistinguishable, so probing ids cannot enumerate
        another tenant's templates."""
        ...

    async def get_system_template_by_code(self, code: str) -> GraphSchema | None:
        """A system template by its stable code (e.g. `general`). No tenancy argument
        because system templates are visible to everyone by definition."""
        ...

    async def active_project_schema(self, project_id: str) -> GraphSchema | None:
        """The project's single active project-scoped schema, or `None` if it never
        adopted one. Carries `(schema_id, schema_version)`, which the confirm-token
        concurrency check compares against mint time to detect drift."""
        ...

    async def template_summary(self, source_schema_id: UUID, user_id: UUID) -> dict | None:
        """Name/code plus live child counts for an adoptable template, for the adopt
        preview. `None` when not visible — same non-enumerable rule as `get_tree`."""
        ...

    async def resolve_for_project(
        self, project_id: str, *, fallback_code: str = "general",
    ) -> ResolvedSchema:
        """The EFFECTIVE ontology for a project: its adopted schema, or the system
        fallback when it never adopted.

        This is the hot path — extraction and validation resolve per run — and the one
        method that must never return `None`. A project with no ontology still has to
        extract something, so the fallback is part of the contract rather than a
        convenience."""
        ...
