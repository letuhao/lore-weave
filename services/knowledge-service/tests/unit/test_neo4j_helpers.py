"""K11.4 unit tests — multi-tenant Cypher helpers.

Acceptance:
  - Cypher without `$user_id` raises CypherSafetyError
  - Cypher with `$user_id` runs normally
  - user_id is passed as a bound parameter, never string-interpolated
  - run_read / run_write refuse to accept user_id inside **params
"""

from __future__ import annotations

import pytest

from app.db.neo4j_helpers import (
    CypherSafetyError,
    assert_user_id_param,
    purge_project,
    run_read,
    run_read_any_owner,
    run_write,
)


# ── assert_user_id_param ──────────────────────────────────────────────


def test_accepts_cypher_with_user_id_filter():
    assert_user_id_param(
        "MATCH (e:Entity {user_id: $user_id}) RETURN e"
    )


def test_accepts_cypher_with_user_id_in_where():
    assert_user_id_param(
        "MATCH (e:Entity) WHERE e.user_id = $user_id RETURN e"
    )


def test_accepts_multi_line_cypher():
    assert_user_id_param(
        """
        MATCH (e:Entity)
        WHERE e.user_id = $user_id
          AND e.kind = $kind
        RETURN e
        """
    )


def test_rejects_cypher_missing_user_id():
    with pytest.raises(CypherSafetyError, match="multi-tenant"):
        assert_user_id_param("MATCH (e:Entity) RETURN e")


def test_rejects_cypher_with_unbound_user_id_literal():
    # A literal `user_id` without the `$` prefix is NOT a bound
    # parameter — it's a property reference. Must still be rejected
    # because `$user_id` is absent.
    with pytest.raises(CypherSafetyError):
        assert_user_id_param("MATCH (e:Entity {user_id: 'abc'}) RETURN e")


def test_rejects_empty_cypher():
    with pytest.raises(CypherSafetyError, match="empty"):
        assert_user_id_param("")


def test_rejects_whitespace_cypher():
    with pytest.raises(CypherSafetyError, match="empty"):
        assert_user_id_param("   \n\t  ")


def test_rejects_non_string_cypher():
    with pytest.raises(CypherSafetyError, match="must be str"):
        assert_user_id_param(123)  # type: ignore[arg-type]


def test_case_sensitive_user_id_token():
    # Cypher parameter names are case-sensitive. `$User_Id` is a
    # different parameter and should not satisfy the check.
    with pytest.raises(CypherSafetyError):
        assert_user_id_param("MATCH (e {user_id: $User_Id}) RETURN e")


# ── R1: word-boundary bypass ──────────────────────────────────────────


@pytest.mark.parametrize(
    "bypass_attempt",
    [
        "MATCH (e {foo: $user_id_extra}) RETURN e",
        "MATCH (e) WHERE e.x = $user_ids RETURN e",
        "MATCH (e {foo: $user_id2}) RETURN e",
        "MATCH (e {foo: $user_identity}) RETURN e",
    ],
)
def test_substring_match_does_not_satisfy_check(bypass_attempt):
    # $user_id_extra / $user_ids / $user_id2 / $user_identity must NOT
    # satisfy the $user_id rule — substring match would be a silent
    # bypass where the real parameter is never bound.
    with pytest.raises(CypherSafetyError, match="multi-tenant"):
        assert_user_id_param(bypass_attempt)


# ── R2: string-literal bypass ─────────────────────────────────────────


@pytest.mark.parametrize(
    "bypass_attempt",
    [
        "CREATE (e {note: '$user_id is cool'}) RETURN e",
        'CREATE (e {note: "$user_id"}) RETURN e',
        "MATCH (e) WHERE e.name = '$user_id' RETURN e",
        # Nested quotes with escapes — must still strip the whole span.
        r"CREATE (e {note: 'escaped \'$user_id\' here'}) RETURN e",
    ],
)
def test_user_id_inside_string_literal_does_not_satisfy_check(bypass_attempt):
    # A `$user_id` inside a quoted literal is treated as text by
    # Cypher — it binds no parameter. The assertion must see through
    # the literal and reject the query.
    with pytest.raises(CypherSafetyError, match="multi-tenant"):
        assert_user_id_param(bypass_attempt)


def test_real_param_outside_string_literal_still_accepted():
    # Regression guard: stripping literals must not eat the real
    # parameter on queries that legitimately carry both.
    assert_user_id_param(
        "MATCH (e {user_id: $user_id}) "
        "WHERE e.note <> 'ignore $user_id in this comment-ish text' "
        "RETURN e"
    )


# ── R3: $user_id with trailing punctuation ────────────────────────────


@pytest.mark.parametrize(
    "cypher",
    [
        "MATCH (e {user_id: $user_id}) RETURN e",     # closing brace
        "MATCH (e {user_id: $user_id,name:$n}) RETURN e",  # comma
        "MATCH (e) WHERE e.user_id = $user_id RETURN e",    # space
        "MATCH (e) WHERE e.user_id=$user_id RETURN e",      # no space
        "MATCH (e) WHERE e.user_id IN [$user_id] RETURN e", # bracket
        "MATCH (e {user_id: $user_id}) RETURN e;",          # trailing semicolon
    ],
)
def test_user_id_with_various_trailing_punctuation(cypher):
    assert_user_id_param(cypher)


# ── run_read / run_write ──────────────────────────────────────────────


class _FakeSession:
    """Records calls to `.run(cypher, **params)`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def run(self, cypher: str, /, **params):
        self.calls.append((cypher, dict(params)))
        return "result"


@pytest.mark.asyncio
async def test_run_read_injects_user_id_as_bound_param():
    session = _FakeSession()
    cypher = "MATCH (e:Entity) WHERE e.user_id = $user_id RETURN e"
    result = await run_read(session, cypher, user_id="u-1")
    assert result == "result"
    assert len(session.calls) == 1
    called_cypher, called_params = session.calls[0]
    assert called_cypher == cypher  # string never mutated
    assert called_params == {"user_id": "u-1"}


@pytest.mark.asyncio
async def test_run_read_passes_extra_params():
    session = _FakeSession()
    await run_read(
        session,
        "MATCH (e:Entity {user_id: $user_id, kind: $kind}) RETURN e",
        user_id="u-1",
        kind="character",
    )
    assert session.calls[0][1] == {"user_id": "u-1", "kind": "character"}


@pytest.mark.asyncio
async def test_run_read_rejects_unsafe_cypher_without_running():
    session = _FakeSession()
    with pytest.raises(CypherSafetyError):
        await run_read(session, "MATCH (e:Entity) RETURN e", user_id="u-1")
    assert session.calls == []  # driver never touched


@pytest.mark.asyncio
async def test_run_write_same_contract_as_read():
    session = _FakeSession()
    cypher = "MATCH (e:Entity {user_id: $user_id}) SET e.name = $name"
    await run_write(session, cypher, user_id="u-1", name="Kai")
    assert session.calls[0][1] == {"user_id": "u-1", "name": "Kai"}


@pytest.mark.asyncio
async def test_run_write_rejects_unsafe_cypher_without_running():
    session = _FakeSession()
    with pytest.raises(CypherSafetyError):
        await run_write(session, "CREATE (e:Entity {name: $name})", user_id="u-1", name="x")
    assert session.calls == []


# ── purge_project (D-KNOWLEDGE-PROJECT-DELETE-NEO4J-ORPHAN) ────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def __aiter__(self):
        self._it = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _PurgeSession:
    """Scripts the count + SHOW VECTOR INDEXES results; records every run()."""

    def __init__(self, count: int, index_names: list[str]) -> None:
        self.count = count
        self.index_names = index_names
        self.calls: list[tuple[str, dict]] = []

    async def run(self, cypher: str, /, **params):
        self.calls.append((cypher, dict(params)))
        if "count(n)" in cypher:
            return _FakeResult([{"n": self.count}])
        if cypher.strip().upper().startswith("SHOW VECTOR INDEXES"):
            return _FakeResult([{"name": n} for n in self.index_names])
        return _FakeResult([])


_PROJ = "019ed678-f3b3-79c7-b421-e56ba55d48d3"
_PROJ_HEX = _PROJ.replace("-", "")  # 32 hex
_EMB_HEX = "a" * 32
_OTHER_HEX = "b" * 32


@pytest.mark.asyncio
async def test_purge_project_deletes_nodes_and_only_its_summary_indexes():
    indexes = [
        f"chapter_summary_emb_p{_PROJ_HEX}_e{_EMB_HEX}",   # THIS project → drop
        f"book_summary_emb_p{_PROJ_HEX}_e{_EMB_HEX}",      # THIS project → drop
        f"part_summary_emb_p{_OTHER_HEX}_e{_EMB_HEX}",     # OTHER project → keep
        "entity_embeddings_1024",                          # SHARED dimension idx → keep
        "passage_embeddings_384",                          # SHARED → keep
    ]
    session = _PurgeSession(count=60, index_names=indexes)
    out = await purge_project(session, _PROJ)

    assert out == {"nodes_deleted": 60, "indexes_dropped": 2}
    # the node delete ran, project_id-scoped + bound (never interpolated)
    delete_calls = [c for c in session.calls if "DETACH DELETE" in c[0]]
    assert len(delete_calls) == 1
    assert delete_calls[0][1] == {"pid": _PROJ}
    # ONLY this project's two summary indexes were dropped — shared + other-project untouched
    dropped = [c[0] for c in session.calls if c[0].startswith("DROP INDEX")]
    assert any(f"p{_PROJ_HEX}_e{_EMB_HEX}" in q for q in dropped)
    assert all(_OTHER_HEX not in q for q in dropped)
    assert all("entity_embeddings" not in q and "passage_embeddings" not in q for q in dropped)
    assert len(dropped) == 2


@pytest.mark.asyncio
async def test_purge_project_skips_delete_when_no_nodes():
    # an empty project (0 nodes) must NOT issue a DETACH DELETE (no-op), but still
    # reconcile indexes (none here).
    session = _PurgeSession(count=0, index_names=[])
    out = await purge_project(session, _PROJ)
    assert out == {"nodes_deleted": 0, "indexes_dropped": 0}
    assert [c for c in session.calls if "DETACH DELETE" in c[0]] == []


# ── run_read_any_owner — the unfiltered escape hatch ────────────────────────────
#
# `get_entity_by_id_any_owner` needs a lookup with NO tenant filter (Entity.id is globally
# unique, and its caller grant-checks the returned project before exposing anything). It
# was calling `run_read`, whose `user_id` is REQUIRED and whose `assert_user_id_param`
# demands the cypher reference `$user_id`. Its cypher does neither, so every call raised
#
#     TypeError: run_read() missing 1 required positional argument: 'user_id'
#
# and `kg_entity_edge_timeline` — the only consumer — could never work. Nothing caught it:
# no test called the tool, and the wire gates only read `tools/list` metadata. A
# deterministic capability sweep found it.


class _FakeSession:
    def __init__(self):
        self.calls = []

    async def run(self, cypher, **params):
        self.calls.append((cypher, params))
        return "result"


@pytest.mark.asyncio
async def test_run_read_any_owner_runs_a_cypher_with_no_user_id():
    """The regression: this exact shape used to raise TypeError."""
    session = _FakeSession()
    out = await run_read_any_owner(session, "MATCH (e:Entity {id: $id}) RETURN e", id="abc")
    assert out == "result"
    cypher, params = session.calls[0]
    assert params == {"id": "abc"}, "no user_id is injected — that is the point"


@pytest.mark.asyncio
async def test_run_read_any_owner_refuses_a_cypher_that_has_a_tenant_filter():
    """Inverted assertion, on purpose. A cypher carrying `$user_id` MEANT to be filtered,
    and must go through run_read() where the filter is enforced — not merely present. This
    stops the unfiltered path from silently absorbing a query that wanted tenancy."""
    session = _FakeSession()
    with pytest.raises(CypherSafetyError, match="use run_read"):
        await run_read_any_owner(
            session, "MATCH (e:Entity {user_id: $user_id}) RETURN e", user_id="u1")
    assert session.calls == [], "must refuse BEFORE touching the driver"


@pytest.mark.asyncio
async def test_run_read_any_owner_rejects_an_empty_cypher():
    session = _FakeSession()
    for bad in ("", "   ", None):
        with pytest.raises(CypherSafetyError):
            await run_read_any_owner(session, bad)


@pytest.mark.asyncio
async def test_get_entity_by_id_any_owner_no_longer_raises_typeerror():
    """The end-to-end regression for kg_entity_edge_timeline's dependency."""
    from app.db.neo4j_repos import entities as entities_repo

    class _Result:
        async def single(self):
            return None

    class _Session(_FakeSession):
        async def run(self, cypher, **params):
            self.calls.append((cypher, params))
            return _Result()

    session = _Session()
    assert await entities_repo.get_entity_by_id_any_owner(session, "eid-1") is None
    cypher, params = session.calls[0]
    assert "$user_id" not in cypher and params == {"id": "eid-1"}
