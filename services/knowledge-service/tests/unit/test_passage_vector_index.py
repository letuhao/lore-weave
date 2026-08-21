"""T25 ③ step 5 — the benchmarks own `passage_embeddings_<dim>`.

The two backend benchmarks are `port-adoption-gate`'s vector-bypass FLOOR: they measure the
Neo4j backend on purpose and are the only things that can compare it with pgvector. Both
inherited their index from `neo4j_schema.cypher`, which ③ deletes.

Measured on iso (T25n) rather than assumed: a missing index RAISES
`Neo.ClientError.Procedure.ProcedureCallFailed`, it does not return an empty list. The
first draft of this docstring claimed the opposite. The benchmarks would therefore break
loudly — the better failure, and still a broken comparison.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.db.neo4j_repos.vector_indexes import (
    ensure_passage_vector_index,
    passage_index_name,
)
from app.domain.passage_contract import SUPPORTED_PASSAGE_DIMS

_SCHEMA = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "db" / "neo4j_schema.cypher"
)


class _RecordingSession:
    """Captures the Cypher rather than running it. The DDL's ACCEPTABILITY is proven live
    against a real Neo4j (T25n); what a unit test can prove is the name and the guard."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def run(self, cypher: str, **params):  # noqa: D102 - test double
        self.calls.append((cypher, params))
        return None


def test_the_benchmark_index_name_is_the_one_the_schema_declares():
    """One index, not two beside each other.

    ⚠️ This test is EXPECTED to fail on the commit that deletes the passage vector DDL, and
    that is its second job: whoever deletes it has to confront that the benchmarks became the
    only definition of the name, rather than discovering it from an empty recall number.
    """
    declared = set(
        re.findall(r"CREATE VECTOR INDEX (passage_embeddings_\d+)", _SCHEMA.read_text())
    )
    assert declared, "the schema declares no passage vector index at all"
    for dim in SUPPORTED_PASSAGE_DIMS:
        if passage_index_name(dim) not in declared:
            pytest.fail(
                f"{passage_index_name(dim)} is not declared in neo4j_schema.cypher "
                f"(declared: {sorted(declared)}) — the benchmark would create a SECOND "
                f"index beside the real one instead of ensuring it"
            )


@pytest.mark.asyncio
async def test_it_creates_the_index_idempotently_for_every_supported_dim():
    for dim in SUPPORTED_PASSAGE_DIMS:
        s = _RecordingSession()
        name = await ensure_passage_vector_index(s, dim)
        assert name == f"passage_embeddings_{dim}"
        (cypher, params), = s.calls
        assert "IF NOT EXISTS" in cypher, "re-running a benchmark must not fail on an existing index"
        assert f"p.embedding_{dim}" in cypher, "the index must be on the dimension's own property"
        assert params == {"dim": dim}


@pytest.mark.asyncio
async def test_an_unsupported_dim_is_REFUSED_rather_than_templated_into_a_name():
    """Cypher has no parameter form for an index name, so the dimension is interpolated.

    `SUPPORTED_PASSAGE_DIMS` is therefore the injection barrier, exactly as
    `passage_contract` records for the Postgres side — and a caller passing something else
    must be refused here rather than trusted to have checked.
    """
    s = _RecordingSession()
    with pytest.raises(ValueError, match="not a supported passage dimension"):
        await ensure_passage_vector_index(s, 999)
    assert s.calls == [], "a rejected dimension must not reach the database at all"


@pytest.mark.asyncio
async def test_a_string_dim_that_looks_numeric_is_also_refused():
    """`"1024" in (384, 1024, …)` is False, so this passes today by the same guard — pinned
    because a future `int(dim)` coercion added for convenience would open the hole again."""
    s = _RecordingSession()
    with pytest.raises(ValueError):
        await ensure_passage_vector_index(s, "1024")  # type: ignore[arg-type]
    assert s.calls == []
