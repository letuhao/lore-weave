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
    run_read,
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
