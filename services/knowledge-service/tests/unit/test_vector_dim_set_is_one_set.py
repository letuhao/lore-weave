"""T17 — entity and passage vectors share ONE closed dim set, proven from the DDL.

`SUPPORTED_VECTOR_DIMS` used to be a second literal of the same tuple, living in
`db/graph_repos/entities.py`. That is not harmless duplication, because the two sets were
never independent: `ensure_vector_schema` iterates the PASSAGE set and creates BOTH tables
from it —

    for dim in dims or SUPPORTED_PASSAGE_DIMS:
        ptable, etable = passage_table(dim), entity_table(dim)

so a dim in the entity set but not in the passage set validates at the embedder
(`SUPPORTED_VECTOR_DIMS` is what `entity_embedder.py` checks against) and then has no
`entity_vectors_{dim}` table to be written to. The failure is a write, not a config error.

This asserts the property that makes that unreachable, from the DDL the adapter actually
emits rather than from the constants agreeing with each other — two names bound to one object
would make an `is` check true by construction, and prove nothing about the writer.
"""

from __future__ import annotations

import re

import pytest

from app.adapters.pg_vector_store import ensure_vector_schema
from app.domain.passage_contract import SUPPORTED_PASSAGE_DIMS, SUPPORTED_VECTOR_DIMS


class _RecordingConn:
    def __init__(self, sink: list[str]) -> None:
        self._sink = sink

    async def execute(self, sql: str, *args):  # noqa: D102 - test double
        self._sink.append(sql)
        return None


class _RecordingPool:
    """Captures the DDL instead of running it; the DDL's acceptability is proven live."""

    def __init__(self) -> None:
        self.sql: list[str] = []

    def acquire(self):  # noqa: D102 - test double
        sink = self.sql

        class _Ctx:
            async def __aenter__(self):
                return _RecordingConn(sink)

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


@pytest.mark.asyncio
async def test_every_dim_the_embedder_accepts_gets_an_entity_table():
    pool = _RecordingPool()
    await ensure_vector_schema(pool)
    created = set(re.findall(r"entity_vectors_(\d+)", "\n".join(pool.sql)))

    missing = [d for d in SUPPORTED_VECTOR_DIMS if str(d) not in created]
    assert not missing, (
        f"dims {missing} are accepted by the entity embedder but no entity_vectors_<dim> "
        f"table is created for them — an embedding that validates and has nowhere to go"
    )


@pytest.mark.asyncio
async def test_no_entity_table_is_created_for_a_dim_the_embedder_would_reject():
    """The other direction, so the property is not satisfiable by creating every table.

    A one-sided check passes just as well if the writer creates tables for dims nothing may
    ever use — which is a different bug (dead tables) wearing this one's clothes.
    """
    pool = _RecordingPool()
    await ensure_vector_schema(pool)
    created = {int(d) for d in re.findall(r"entity_vectors_(\d+)", "\n".join(pool.sql))}

    assert created <= set(SUPPORTED_VECTOR_DIMS), (
        f"entity tables exist for {sorted(created - set(SUPPORTED_VECTOR_DIMS))}, which the "
        f"embedder rejects"
    )


def test_the_two_names_are_one_set_so_a_re_split_is_visible():
    """A regression guard, and honest about being one: it can only fail if someone gives
    `SUPPORTED_VECTOR_DIMS` its own literal again — which is exactly the change that made
    the two tests above capable of failing."""
    assert SUPPORTED_VECTOR_DIMS is SUPPORTED_PASSAGE_DIMS
