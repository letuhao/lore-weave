"""T79 — a dialect token must never reach the driver, and the guard must be WIRED.

`{NOW}` (spec §10.2) is substituted by `render(template, engine)` at the call site that knows
the engine. The scheme has exactly one failure mode and it is the quiet one: a template gains
the token and its call site never gains the `render()`. Neo4j then receives a literal `{NOW}`,
which is a **map literal** in Cypher rather than a syntax error at the point of the mistake, so
the message comes back about something else entirely. It already happened twice during T64 —
`.format()` running after `render()` (`KeyError: 'datetime()'`), and `{NOW}` inside an f-string
needing `{{NOW}}` (68 collection errors).

⚠️ **This file exists because bite B found the guard undefended.** Bite A — dropping the
`render()` from one call site — went red in 15 places, so the guard demonstrably works. Bite B
then deleted `assert_rendered` from all three `run_*` entry points and **the whole suite stayed
green**: nothing pinned the call. A guard that works but is not pinned is one edit from being
removed by someone tidying up, and the failure it prevents is invisible until production.

So these tests go through the REAL entry points with a fake session. Calling `assert_rendered`
directly would prove the function works, not that anything calls it — which is precisely the
distinction `port-adoption-gate`'s own selftest got wrong one cycle earlier.
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
async def test_every_entry_point_REFUSES_an_unrendered_template(entry):
    """Bite B removed the call from all three at once and nothing noticed. Each is checked
    separately so removing it from just one is caught too."""
    session = _ExplodingSession()
    with pytest.raises(UnrenderedTemplateError) as exc:
        if entry == "run_read":
            await run_read(session, _UNRENDERED, user_id="u-1")
        elif entry == "run_read_any_owner":
            await run_read_any_owner(session, _UNRENDERED_ANY)
        else:
            await run_write(session, _UNRENDERED, user_id="u-1")
    assert "§10.2" in str(exc.value), (
        "the error must name the spec section that defines the token — rule 9"
    )
    assert not session.calls, "the guard raised only AFTER handing the query to the driver"


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
