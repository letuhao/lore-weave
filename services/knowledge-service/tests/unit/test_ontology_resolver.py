"""Unit tests for lane LA OntologyResolver (app/ontology/resolver.py).

No DB. Uses a counting fake GraphSchemasRepo (to prove cache hit/invalidate)
and a fake ProjectsRepo + FakeGlossaryOntologyClient (to prove node-kind source
selection: book vs user-standards) without glossary or Postgres.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.clients.glossary_ontology_client import FakeGlossaryOntologyClient
from app.db.ontology_models import ResolvedSchema, SchemaNodeKind
from app.ontology.resolver import OntologyResolver

pytestmark = pytest.mark.asyncio


def _schema(project_id: str) -> ResolvedSchema:
    return ResolvedSchema(
        project_id=project_id,
        schema_version=1,
        allow_free_edges=True,
        node_kinds=[
            SchemaNodeKind(schema_node_kind_id=uuid4(), schema_id=uuid4(), kind_code="character", strength="required"),
            SchemaNodeKind(schema_node_kind_id=uuid4(), schema_id=uuid4(), kind_code="technique", strength="required"),
            SchemaNodeKind(schema_node_kind_id=uuid4(), schema_id=uuid4(), kind_code="item", strength="optional"),
        ],
    )


class _CountingSchemasRepo:
    """Stand-in for GraphSchemasRepo.resolve_for_project that counts calls."""

    def __init__(self) -> None:
        self.calls = 0

    async def resolve_for_project(self, project_id: str, *, fallback_code: str = "general") -> ResolvedSchema:
        self.calls += 1
        return _schema(project_id)


class _FakeProjectsRepo:
    """Stand-in for ProjectsRepo.project_meta returning (owner, book_id)."""

    def __init__(self, meta: dict[UUID, tuple[UUID, UUID | None]]) -> None:
        self._meta = meta

    async def project_meta(self, project_id: UUID):
        return self._meta.get(project_id)


def _resolver(schemas, projects, glossary, *, ttl_s: float = 30.0) -> OntologyResolver:
    return OntologyResolver(schemas=schemas, projects=projects, glossary=glossary, ttl_s=ttl_s)


# ── cache ──────────────────────────────────────────────────────────────
async def test_resolve_caches_within_ttl():
    schemas = _CountingSchemasRepo()
    r = _resolver(schemas, _FakeProjectsRepo({}), FakeGlossaryOntologyClient())
    a = await r.resolve("proj-1")
    b = await r.resolve("proj-1")
    assert a is b  # same cached object
    assert schemas.calls == 1  # second call served from cache


async def test_invalidate_forces_refresh():
    schemas = _CountingSchemasRepo()
    r = _resolver(schemas, _FakeProjectsRepo({}), FakeGlossaryOntologyClient())
    await r.resolve("proj-1")
    r.invalidate("proj-1")
    await r.resolve("proj-1")
    assert schemas.calls == 2


async def test_ttl_zero_never_caches():
    schemas = _CountingSchemasRepo()
    r = _resolver(schemas, _FakeProjectsRepo({}), FakeGlossaryOntologyClient(), ttl_s=0.0)
    await r.resolve("proj-1")
    await r.resolve("proj-1")
    assert schemas.calls == 2


async def test_cache_is_per_project():
    schemas = _CountingSchemasRepo()
    r = _resolver(schemas, _FakeProjectsRepo({}), FakeGlossaryOntologyClient())
    await r.resolve("proj-1")
    await r.resolve("proj-2")
    assert schemas.calls == 2  # distinct keys, no cross-pollination


# ── node-kind source selection ──────────────────────────────────────────
async def test_node_kind_source_book_when_project_has_book():
    owner = uuid4()
    book = uuid4()
    pid = uuid4()
    projects = _FakeProjectsRepo({pid: (owner, book)})
    glossary = FakeGlossaryOntologyClient(
        book_kinds={str(book): ["character", "technique"]},  # missing `item`
        user_kinds={str(owner): ["character", "technique", "item"]},  # would satisfy all
    )
    r = _resolver(_CountingSchemasRepo(), projects, glossary)
    rk = await r.resolve_node_kinds(str(pid))
    assert rk.source == "book"
    assert rk.book_id == book
    assert rk.glossary_codes == frozenset({"character", "technique"})
    # `item` is optional + missing from the BOOK source (not the user one).
    assert rk.missing() == frozenset({"item"})
    assert rk.missing(strength="required") == frozenset()
    assert rk.missing(strength="optional") == frozenset({"item"})


async def test_node_kind_source_user_standards_when_no_book():
    owner = uuid4()
    pid = uuid4()
    projects = _FakeProjectsRepo({pid: (owner, None)})  # no book → user standards
    glossary = FakeGlossaryOntologyClient(
        user_kinds={str(owner): ["character"]},  # missing required `technique`
    )
    r = _resolver(_CountingSchemasRepo(), projects, glossary)
    rk = await r.resolve_node_kinds(str(pid))
    assert rk.source == "user_standards"
    assert rk.book_id is None
    assert rk.glossary_codes == frozenset({"character"})
    # required `technique` missing → adopt-gate (LC) would block on this.
    assert rk.missing(strength="required") == frozenset({"technique"})


async def test_node_kind_source_unavailable_on_glossary_down():
    owner = uuid4()
    book = uuid4()
    pid = uuid4()
    projects = _FakeProjectsRepo({pid: (owner, book)})
    glossary = FakeGlossaryOntologyClient(unavailable=True)
    r = _resolver(_CountingSchemasRepo(), projects, glossary)
    rk = await r.resolve_node_kinds(str(pid))
    assert rk.source == "unavailable"
    assert rk.glossary_codes is None
    # glossary-down can't prove absence → nothing reported missing (no false gate).
    assert rk.missing() == frozenset()
    assert rk.missing(strength="required") == frozenset()


async def test_unknown_project_yields_no_glossary_crosscheck():
    # project_meta returns None (project not found) → source unavailable, but
    # the schema's expected kinds still come through.
    r = _resolver(_CountingSchemasRepo(), _FakeProjectsRepo({}), FakeGlossaryOntologyClient())
    rk = await r.resolve_node_kinds(str(uuid4()))
    assert rk.source == "unavailable"
    assert rk.glossary_codes is None
    assert rk.expected_codes == frozenset({"character", "technique", "item"})


async def test_non_uuid_project_id_has_no_meta():
    # a synthetic test project id (not a UUID) has no owner/book → unavailable.
    r = _resolver(_CountingSchemasRepo(), _FakeProjectsRepo({}), FakeGlossaryOntologyClient())
    rk = await r.resolve_node_kinds("synthetic-proj")
    assert rk.source == "unavailable"
    assert rk.expected_codes == frozenset({"character", "technique", "item"})
