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
