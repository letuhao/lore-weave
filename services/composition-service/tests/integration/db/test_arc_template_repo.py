"""D-WAVE2-DB-ROUNDTRIP-TEST — ArcTemplateRepo behavior on real Postgres.

The unit test (tests/unit/test_arc_template_repo.py) proves the SQL strings via a fake
conn; this proves the queries actually EXECUTE — most importantly `list_for_caller`'s
conditional `$1` binding across all four scopes (the system/public scopes bind NO
caller_id, so a misnumbered placeholder = the R-NODE-P1 `scope=system` 500), plus the
create round-trip (source/status/imported_derived columns) and the clone B-3 taint.
Gated on TEST_COMPOSITION_DB_URL; the fixture drops the motif tables on setup/teardown.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.models import ArcTemplateCreateArgs
from app.db.repositories.arc_template_repo import ArcTemplateRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # MANDATORY (CLAUDE.md test-parallelization): this file DROPs/re-migrates tables on the
    # shared dev PG. Without the group, xdist schedules it on a DIFFERENT worker than the
    # other real-DB files and they drop each other's tables mid-run — the counts then lie.
    pytest.mark.xdist_group("pg"),
]

_MOTIF_TABLES = [
    "consumed_tokens", "motif_application", "motif_link",
    "import_source", "arc_template", "motif",
]


@pytest.fixture
async def repo():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)

    async def _drop():
        async with p.acquire() as c:
            for t in _MOTIF_TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")

    try:
        await _drop()
        await run_migrations(p)
        yield ArcTemplateRepo(p), p
    finally:
        await _drop()
        await p.close()


def _args(**kw) -> ArcTemplateCreateArgs:
    base = dict(code="three_year_pact", name="Three-Year Pact")
    base.update(kw)
    return ArcTemplateCreateArgs(**base)


async def test_arc_create_columns_roundtrip(repo):
    r, pool = repo
    u = uuid.uuid4()
    arc = await r.create(u, _args(code="imp.arc"), source="imported", status="draft",
                         imported_derived=True)
    assert arc.owner_user_id == u and arc.source == "imported"
    assert arc.status == "draft" and arc.imported_derived is True
    # default path unchanged.
    auth = await r.create(u, _args(code="auth.arc"))
    assert auth.source == "authored" and auth.imported_derived is False


async def test_arc_list_for_caller_every_scope(repo):
    """The conditional `$1` binding holds for ALL scopes — system/public bind no caller
    (the IndeterminateDatatypeError 500 class), user/all do. Each scope returns the right
    rows + a genre filter under a caller-less scope numbers correctly."""
    r, _ = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    await r.create(u1, _args(code="mine", genre_tags=["xianxia"]))
    pub = await r.create(u2, _args(code="pub", visibility="public", genre_tags=["xianxia"]))
    await r.create(u2, _args(code="foreign_priv"))  # u2's private — invisible to u1

    # system scope (no caller bind) + a genre filter must not raise + filters correctly.
    sysrows = await r.list_for_caller(u1, scope="system", genre="xianxia")
    assert all(a.owner_user_id is None for a in sysrows)
    pubrows = await r.list_for_caller(u1, scope="public")
    assert pub.id in {a.id for a in pubrows}
    minerows = await r.list_for_caller(u1, scope="user")
    assert {a.code for a in minerows} == {"mine"}
    allrows = await r.list_for_caller(u1, scope="all")
    codes = {a.code for a in allrows}
    assert "mine" in codes and "pub" in codes and "foreign_priv" not in codes  # IDOR


async def test_arc_clone_propagates_b3_taint(repo):
    """An adopt of an imported arc stays tainted (publish-strip fires on the clone);
    adopt-of-authored stays false (the strip isn't over-broad)."""
    r, _ = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    imp = await r.create(u1, _args(code="imp", visibility="public"), source="imported",
                         imported_derived=True)
    auth = await r.create(u1, _args(code="auth", visibility="public"))

    cloned_imp = await r.clone(u2, imp.id, target_owner=u2)
    assert cloned_imp.imported_derived is True          # taint propagated
    assert cloned_imp.source_ref == f"lineage:{imp.id}"
    cloned_auth = await r.clone(u2, auth.id, target_owner=u2)
    assert cloned_auth.imported_derived is False         # not over-broad


async def test_retrieve_arcs_projects_renamed_columns_via_alias(repo):
    """25 M5.2 (BA10 alias) guard-by-EFFECT: retrieve_arcs' _ARC_RETRIEVE_COLS reads the
    RENAMED arc_template columns (tracks/roster) ALIASED back to the model field names
    (threads/arc_roster). A reader that forgets the alias 500s on the renamed schema — the
    exact motif_retrieve.retrieve_arcs bug this session fixed. The unit test (test_arc_
    retrieve.py) mocks the pool with rows already shaped as threads/arc_roster, so it CANNOT
    catch an unaliased column; this runs the REAL SELECT against the renamed columns. Any
    future arc_template reader that drops the alias reds here (the coverage gap that let the
    500 ship until the adversarial review caught it)."""
    from app.db.repositories.motif_retrieve import MotifRetriever
    from app.db.models import ArcRosterEntry, ArcThread

    r, pool = repo
    u = uuid.uuid4()
    await r.create(u, _args(
        code="alias.arc", genre_tags=["xianxia"],
        threads=[ArcThread(key="main", label="Main Line")],
        arc_roster=[ArcRosterEntry(key="protagonist", label="Hero")],
    ))
    # premise/genre omitted ⇒ no embedder call; the arc ranks on genre order and is returned
    # (retrieve_arcs never drops an arc for being unembedded). caller=owner ⇒ visible.
    cands = await MotifRetriever(pool).retrieve_arcs(u, limit=5)
    got = {c.arc_template.code: c.arc_template for c in cands}
    assert "alias.arc" in got                          # the SELECT executed (no 500) + visible
    arc = got["alias.arc"]
    # the renamed DB columns round-trip to the model field names THROUGH the alias.
    assert [t["key"] for t in arc.threads] == ["main"]
    assert [e["key"] for e in arc.arc_roster] == ["protagonist"]
