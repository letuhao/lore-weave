"""The `OntologyStore` port contract (plan T15).

Same two-part shape as the `VectorStore` suite: the RULES against the fake, plus structural
conformance for both implementations. The rules here are visibility rules, and they are the
whole reason this port is worth having — a store that returned another user's `user`-tier
template would satisfy every signature and leak templates across tenants.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.adapters.fake_ontology_store import FakeOntologyStore
from app.adapters.postgres_ontology_store import PostgresOntologyStore
from app.db.ontology_models import GraphSchema
from app.ports.ontology_store import OntologyStore

_OWNER = uuid4()
_OTHER = uuid4()
_PROJECT = "proj-1"
_NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def _schema(scope: str, code: str, *, scope_id: str | None = None,
            deprecated: bool = False, version: int = 1, updated: datetime = _NOW) -> GraphSchema:
    return GraphSchema(
        schema_id=uuid4(), scope=scope, scope_id=scope_id, code=code, name=code.title(),
        schema_version=version, deprecated_at=_NOW if deprecated else None,
        created_at=_NOW, updated_at=updated,
    )


# ── visibility ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_another_users_template_is_never_listed():
    store = FakeOntologyStore([
        _schema("system", "general"),
        _schema("user", "mine", scope_id=str(_OWNER)),
        _schema("user", "theirs", scope_id=str(_OTHER)),
    ])
    codes = [s.code for s in await store.list_visible(_OWNER)]
    assert codes == ["general", "mine"]


@pytest.mark.asyncio
async def test_a_project_schema_appears_only_when_that_project_is_named():
    store = FakeOntologyStore([
        _schema("system", "general"),
        _schema("project", "adopted", scope_id=_PROJECT),
    ])
    assert [s.code for s in await store.list_visible(_OWNER)] == ["general"]
    # Order is `ORDER BY scope, code` — ALPHABETICAL by scope, so "project" sorts before
    # "system". Not a tier order, which is what it looks like at a glance; asserted so a
    # consumer that reads position 0 as "the most specific schema" finds out here.
    assert [s.code for s in await store.list_visible(_OWNER, project_id=_PROJECT)] == [
        "adopted", "general",
    ]


@pytest.mark.asyncio
async def test_a_different_projects_schema_stays_hidden():
    store = FakeOntologyStore([_schema("project", "theirs", scope_id="proj-2")])
    assert await store.list_visible(_OWNER, project_id=_PROJECT) == []


@pytest.mark.asyncio
async def test_an_invisible_schema_reads_as_ABSENT_not_as_an_error():
    """If 'not visible' raised and 'not found' returned None, a caller could enumerate
    another tenant's schema ids by watching which ones raise."""
    theirs = _schema("user", "theirs", scope_id=str(_OTHER))
    store = FakeOntologyStore([theirs])
    assert await store.get_tree(_OWNER, theirs.schema_id) is None
    assert await store.get_tree(_OWNER, uuid4()) is None


@pytest.mark.asyncio
async def test_deprecated_templates_are_hidden_from_pickers_but_readable_by_id():
    """A deprecated template must keep working for a project that already adopted it, and
    must not appear in a picker — or a user adopts something already withdrawn."""
    old = _schema("system", "retired", deprecated=True)
    store = FakeOntologyStore([_schema("system", "general"), old])
    assert [s.code for s in await store.list_visible(_OWNER)] == ["general"]
    assert [s.code for s in await store.list_visible(_OWNER, include_deprecated=True)] == [
        "general", "retired",
    ]
    assert await store.get_tree(_OWNER, old.schema_id) is None
    assert await store.get_tree(_OWNER, old.schema_id, include_deprecated=True) is not None


@pytest.mark.asyncio
async def test_only_system_and_own_templates_are_adoptable():
    system, mine, theirs = (
        _schema("system", "general"),
        _schema("user", "mine", scope_id=str(_OWNER)),
        _schema("user", "theirs", scope_id=str(_OTHER)),
    )
    store = FakeOntologyStore([system, mine, theirs])
    assert await store.template_summary(system.schema_id, _OWNER) is not None
    assert await store.template_summary(mine.schema_id, _OWNER) is not None
    assert await store.template_summary(theirs.schema_id, _OWNER) is None


# ── resolution ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_falls_back_to_the_system_template_and_never_returns_none():
    """The hot path. A project with no ontology still has to extract something, so the
    fallback is part of the contract rather than a convenience."""
    store = FakeOntologyStore([_schema("system", "general", version=7)])
    resolved = await store.resolve_for_project("never-adopted")
    assert resolved is not None
    assert resolved.project_id == "never-adopted"
    assert resolved.schema_version == 7


@pytest.mark.asyncio
async def test_resolve_prefers_the_projects_adopted_schema_over_the_fallback():
    store = FakeOntologyStore([
        _schema("system", "general", version=7),
        _schema("project", "adopted", scope_id=_PROJECT, version=3),
    ])
    assert (await store.resolve_for_project(_PROJECT)).schema_version == 3


@pytest.mark.asyncio
async def test_resolve_with_no_schema_and_no_fallback_warns_instead_of_going_quiet(caplog):
    """An empty ontology extracts nothing, which looks exactly like a model that found
    nothing. The WARN is the only thing distinguishing them."""
    store = FakeOntologyStore([])
    with caplog.at_level("WARNING"):
        resolved = await store.resolve_for_project(_PROJECT)
    assert resolved.schema_version == 0
    assert any("resolving EMPTY" in r.getMessage() for r in caplog.records), caplog.text


@pytest.mark.asyncio
async def test_active_project_schema_breaks_ties_the_same_way_the_repo_does():
    """One-active is an invariant adopt maintains; both stores carry the same defensive
    tiebreaker, so a fixture that violates it resolves identically in test and prod."""
    older = _schema("project", "old", scope_id=_PROJECT, version=1, updated=_NOW - timedelta(days=1))
    newer = _schema("project", "new", scope_id=_PROJECT, version=2, updated=_NOW)
    store = FakeOntologyStore([older, newer])
    active = await store.active_project_schema(_PROJECT)
    assert active is not None and active.schema_version == 2


@pytest.mark.asyncio
async def test_a_deprecated_project_schema_is_not_active():
    store = FakeOntologyStore([
        _schema("project", "withdrawn", scope_id=_PROJECT, deprecated=True),
    ])
    assert await store.active_project_schema(_PROJECT) is None


# ── structural conformance ───────────────────────────────────────────────────


@pytest.mark.parametrize("impl", [FakeOntologyStore, PostgresOntologyStore])
def test_implementations_match_the_port_signatures(impl):
    """`isinstance(x, OntologyStore)` checks method NAMES only. An adapter whose
    `list_visible` took `owner` instead of `user_id` would satisfy it and fail at the
    call site."""
    for name in ("list_visible", "get_tree", "get_system_template_by_code",
                 "active_project_schema", "template_summary", "resolve_for_project"):
        port_sig = inspect.signature(getattr(OntologyStore, name))
        impl_sig = inspect.signature(getattr(impl, name))
        assert list(impl_sig.parameters) == list(port_sig.parameters), (
            f"{impl.__name__}.{name} parameters {list(impl_sig.parameters)} "
            f"!= port {list(port_sig.parameters)}"
        )
        for pname, pparam in port_sig.parameters.items():
            iparam = impl_sig.parameters[pname]
            assert iparam.kind == pparam.kind, f"{impl.__name__}.{name}({pname}) kind differs"
            assert iparam.default == pparam.default, (
                f"{impl.__name__}.{name}({pname}) defaults to {iparam.default!r}, "
                f"port says {pparam.default!r}"
            )


def test_both_implementations_satisfy_the_protocol_at_runtime():
    assert isinstance(FakeOntologyStore(), OntologyStore)
    assert isinstance(PostgresOntologyStore(None), OntologyStore)
