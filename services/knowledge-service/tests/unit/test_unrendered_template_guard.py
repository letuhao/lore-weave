"""T79/T83 — a dialect token must never reach the driver, and the RENDER must be wired.

`{NOW}` (spec §10.2) is substituted for the session's engine. **T83 moved that substitution
from the call sites into `run_read`/`run_read_any_owner`/`run_write`**, and the reason is worth
keeping: with 51 call sites each saying `render(TEMPLATE, "neo4j")`, the dialect ratchet read
zero while the layer named one engine 51 times, and a real repo function run against AGE failed
on `function datetime does not exist`.

⚠️ **That move CHANGED WHAT THESE TESTS CAN PROVE, and pretending otherwise would leave a
criterion that cannot fail.** Before, the entry points refused an unrendered template; now they
render it, so "refuses" is no longer true of them and asserting it would be asserting the old
design. What replaced it is stronger and is what is pinned below:

  * each entry point RENDERS, keyed on `engine_of(session)` — not on a literal, and not on a
    default that would silently make every session Neo4j;
  * `assert_rendered` still has teeth in the ONE place the chokepoint does not reach:
    `maintenance.invalidate_stale_quarantined_facts` bypasses the helpers because its `user_id`
    is legitimately `None`, and renders for itself.

Bite B (deleting `assert_rendered` from all three entry points) is what showed the guard was
undefended in T79; bites B1/B2/B3 still pin the pieces that remain load-bearing.
"""

from __future__ import annotations

import pytest

from app.db.cypher_dialect import UnrenderedTemplateError, assert_rendered, render
from app.db.neo4j_helpers import run_read, run_read_any_owner, run_write

#: Carries `$user_id` so `assert_user_id_param` is satisfied — otherwise a test could pass for
#: the wrong reason, on the tenancy check rather than on the token check.
_UNRENDERED = "MATCH (e:Entity {user_id: $user_id}) SET e.updated_at = {NOW} RETURN e"
_RENDERED = render(_UNRENDERED, "neo4j")

#: `run_read_any_owner` REFUSES any cypher mentioning `$user_id` — it exists for the globally
#: unique lookups that legitimately have no tenant filter — so it gets its own template.
#: Without this the test would pass on the tenancy refusal and never reach the token check.
_UNRENDERED_ANY = "MATCH (e:Entity {id: $id}) SET e.updated_at = {NOW} RETURN e"
_RENDERED_ANY = render(_UNRENDERED_ANY, "neo4j")


class _ExplodingSession:
    """Any `run` reaching this session means the guard did not stop the query."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, cypher: str, **params):  # noqa: ANN003
        self.calls.append(cypher)
        raise AssertionError(
            f"an UNRENDERED template reached the driver: {cypher!r}. The database would read "
            f"`{{NOW}}` as a map literal and fail somewhere else entirely"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["run_read", "run_read_any_owner", "run_write"])
async def test_every_entry_point_RENDERS_for_the_sessions_engine(entry):
    """The property that replaced "refuses". Each entry point is checked separately so losing
    the render from just one is caught."""
    for engine, expected in (("neo4j", "datetime()"), ("age", "timestamp()")):
        seen: list[str] = []

        class _Recording:
            def __init__(self) -> None:
                self.engine = engine

            async def run(self, cypher: str, **params):  # noqa: ANN003
                seen.append(cypher)
                return "ok"

        session = _Recording()
        if entry == "run_read":
            await run_read(session, _UNRENDERED, user_id="u-1")
        elif entry == "run_read_any_owner":
            await run_read_any_owner(session, _UNRENDERED_ANY)
        else:
            await run_write(session, _UNRENDERED, user_id="u-1")
        assert seen and "{NOW}" not in seen[0], (
            f"{entry} handed the driver an unrendered template — the database reads `{{NOW}}` "
            f"as a map literal and fails somewhere else entirely"
        )
        assert expected in seen[0], (
            f"{entry} rendered for the wrong engine: expected {expected!r} for engine "
            f"{engine!r}, got {seen[0]!r}"
        )


@pytest.mark.asyncio
async def test_a_session_that_declares_NO_engine_is_treated_as_neo4j():
    """A Bolt `AsyncSession` and its transaction have no `engine` attribute, and cannot be
    anything but Neo4j — so the fallback is a fact about the type, not a default hiding a
    missing declaration. A mock answers every attribute, which is why only a `str` counts."""
    from unittest.mock import MagicMock

    from app.db.neo4j_helpers import engine_of

    assert engine_of(object()) == "neo4j"
    assert engine_of(MagicMock()) == "neo4j", (
        "a MagicMock's auto-attribute was read as an engine declaration — every mock-session "
        "unit test would then hand `render` a mock and raise"
    )

    class _Age:
        engine = "age"

    assert engine_of(_Age()) == "age"


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["run_read", "run_read_any_owner", "run_write"])
async def test_every_entry_point_still_PASSES_a_rendered_template(entry):
    """Non-vacuity, on the other direction: a guard that rejected everything would make the
    tests above pass while breaking every query in the service."""
    seen: list[str] = []

    class _Recording:
        async def run(self, cypher: str, **params):  # noqa: ANN003
            seen.append(cypher)
            return "ok"

    session = _Recording()
    if entry == "run_read":
        out = await run_read(session, _RENDERED, user_id="u-1")
    elif entry == "run_read_any_owner":
        out = await run_read_any_owner(session, _RENDERED_ANY)
    else:
        out = await run_write(session, _RENDERED, user_id="u-1")
    expected = _RENDERED_ANY if entry == "run_read_any_owner" else _RENDERED
    assert out == "ok" and seen == [expected]
    assert "datetime()" in seen[0], "render() did not substitute the token on the way through"


@pytest.mark.asyncio
async def test_the_quarantine_sweep_is_guarded_even_though_it_BYPASSES_run_write():
    """`invalidate_stale_quarantined_facts` calls `session.run` directly — it is the one repo
    function whose `user_id` is legitimately `None`, so it cannot use `run_write`. That also
    puts it outside the chokepoint these tests pin, which is exactly the kind of exception a
    guard quietly fails to cover."""
    import app.db.neo4j_repos.maintenance as m

    assert "assert_rendered(cypher)" in _source(m.invalidate_stale_quarantined_facts), (
        "the one repo call that bypasses run_write lost its explicit assert_rendered; a token "
        "left in _QUARANTINE_CLEANUP_CYPHER would reach the driver unchecked"
    )


def _source(fn) -> str:
    import inspect

    return inspect.getsource(fn)


def test_assert_rendered_names_the_token_and_ignores_a_MAP_LITERAL():
    """Cypher is full of braces — `MERGE (e:Entity {id: $id})`, `duration({hours: $h})`. A
    guard that fired on any `{` would be unsatisfiable, so it must key on the token itself.
    Validated on a case it was not derived from: a map literal whose key is literally `NOW`."""
    assert_rendered("MERGE (e:Entity {id: $id, user_id: $user_id}) RETURN e")
    assert_rendered("MATCH (f:Fact) WHERE f.at < $cutoff RETURN f")
    assert_rendered("RETURN {NOWISH: 1} AS m")
    with pytest.raises(UnrenderedTemplateError):
        assert_rendered("SET e.updated_at = {NOW}")
