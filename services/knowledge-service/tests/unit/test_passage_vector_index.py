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

from app.db.graph_repos.vector_indexes import (
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


def _reads_passages_from_neo4j() -> list[str]:
    """Deployment declarations whose passage READ PRIMARY is not `postgres`. Derived.

    The same predicate `port-adoption-gate` prints as `passage read-primary declarations`,
    re-derived here so the test and the gate cannot disagree about what the tree says. An
    interpolation `${KNOWLEDGE_VECTOR_READ_PRIMARY:-neo4j}` counts as its DEFAULT, because
    that is what a deployment setting nothing receives — dev sets nothing, which is exactly
    how it ended up serving passages from an index whose DDL had been deleted.
    """
    import glob as _glob

    root = pathlib.Path(__file__).resolve().parents[4]
    out: list[str] = []
    for pat in ("infra/*.env", "infra/.env", "infra/.env.*", "infra/*.yml", "infra/*.yaml"):
        for path in _glob.glob(str(root / pat)):
            try:
                text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in re.finditer(
                    r"KNOWLEDGE_VECTOR_READ_PRIMARY\s*[:=]\s*[\"']?"
                    r"(?:\$\{KNOWLEDGE_VECTOR_READ_PRIMARY:-)?([A-Za-z0-9_]+)", text):
                if m.group(1).strip().lower() != "postgres":
                    out.append(f"{pathlib.Path(path).name}={m.group(1)}")
    return out


def test_the_PASSAGE_vector_ddl_tracks_the_DECLARATIONS_that_need_it():
    """§9.2's coupling, applied to the PASSAGE family — and this test has been wrong twice.

    v1 demanded the DDL survive. v2 (T25o) inverted it to demand the DDL be ABSENT, on the
    claim that "dev and iso both read them from pgvector now, so this DDL had no reader
    left." **That claim was about configuration nobody had checked**, and T25z measured it
    false: dev declares no `KNOWLEDGE_VECTOR_READ_PRIMARY`, so it runs the compose default
    `neo4j`, and `passage_embeddings_1024` showed **readCount 4090, lastRead 08-23** — two
    days AFTER the DDL that creates it had been deleted. The index survived only as residue
    in an existing database; the next Neo4j rebuild was a `ProcedureCallFailed` 500.

    So this is v3, and it asserts neither answer. It DERIVES the coupling, the way the
    entity test beside it does, so the same test permits the deletion the day the last
    deployment moves to postgres AND requires the DDL while one has not. A criterion that
    outlives its reason is what produced v2.

    ⚠️ Only `_1024` is coupled. The other four dimensions read `readCount 0, lastRead NULL`
    on both stacks — T25u's own criterion for deleting the event family — so they stay gone.
    """
    schema = _declarations(_SCHEMA.read_text())
    declared = re.findall(r"CREATE VECTOR INDEX (passage_embeddings_\d+)", schema)
    readers = _reads_passages_from_neo4j()

    if readers:
        assert "passage_embeddings_1024" in declared, (
            f"{readers} still read passages from neo4j and no passage_embeddings_1024 index "
            f"is declared. A missing vector index RAISES (52U00/52N37), so this is a 500 in "
            f"waiting — measured on the dev graph at readCount 4090 (T25z)"
        )
    else:
        assert declared == [], (
            f"every deployment declares postgres for passage reads and {declared} is still "
            f"declared. §9.2's coupling: the DDL goes when the path nobody can take goes"
        )

    stale = [d for d in declared if d != "passage_embeddings_1024"]
    assert stale == [], (
        f"{stale} declared, but only _1024 has readers — the other dimensions read "
        f"readCount 0 / lastRead NULL on both stacks, which is T25u's own criterion for "
        f"deleting a family. Restoring them adds indexes over properties nothing writes"
    )


def _declarations(schema: str) -> str:
    """The schema with Cypher comments stripped.

    Found by a bite that FAILED to bite: commenting out all five
    `CREATE VECTOR INDEX entity_embeddings_*` lines left the survival test GREEN, because
    `re.findall` over the raw file matches just as happily inside `// CREATE VECTOR ...`.
    A test that cannot tell a declaration from a note about one is not guarding the DDL, and
    the version of this test before the split had the same hole.
    """
    return chr(10).join(
        line for line in schema.splitlines() if not line.lstrip().startswith("//")
    )


def _neo4j_still_serves_entity_reads() -> bool:
    """Does the Neo4j entity FALLBACK still exist? Derived, not assumed.

    `Neo4jVectorStore` is the only reader of `entity_embeddings_*` — the benchmarks and the
    shadow harness touch PASSAGE vectors only, measured. So the fallback exists exactly while
    that adapter still calls `find_entities_by_vector`.
    """
    import ast as _ast

    src = (pathlib.Path(__file__).resolve().parents[2] / "app" / "adapters"
           / "neo4j_vector_store.py").read_text(encoding="utf-8")
    return any(isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)
               and n.func.id == "find_entities_by_vector" for n in _ast.walk(_ast.parse(src)))


def test_the_ENTITY_vector_ddl_tracks_the_FALLBACK_that_needs_it():
    """§9.2 couples the entity DDL's life to the Neo4j entity path, so this asserts BOTH arms.

    While the fallback exists, deleting the DDL breaks entity search exactly where the design
    sends it — T25t measured it on iso: with the index present the query returns 5 hits,
    without it `52U00 / 52N37 ProcedureCallFailed`.

    ⚠️ The previous version demanded the DDL UNCONDITIONALLY, and that is a criterion which
    outlives its reason: the day the fallback is removed, the test would fail the removal and
    someone would have to edit this file to let T25 finish. Now the coupling is derived, so
    the same test permits the removal AND requires the DDL to go with it — a schema carrying
    an index for a path nobody can take is what T25u deleted on the event family.

    T25n's cure does NOT transfer here, and that is measured rather than assumed: passages
    left the service for Postgres and only the BENCHMARKS stayed on Neo4j, so they were given
    `ensure_passage_vector_index` and own their index. The entity reader is a SERVICE
    fallback; a service cannot create an index per read.
    """
    schema = _SCHEMA.read_text()
    found = re.findall(r"CREATE VECTOR INDEX (entity_embeddings_\d+)", _declarations(schema))
    if _neo4j_still_serves_entity_reads():
        assert found, (
            "no entity_embeddings_* index is declared any more, but `Neo4jVectorStore` still "
            "calls `find_entities_by_vector` — a Neo4j-backend deployment serves entity reads "
            "from Neo4j and a missing vector index RAISES, so this is a 500 in waiting"
        )
    else:
        assert not found, (
            f"the Neo4j entity fallback is GONE and {found} is still declared. §9.2 ties the "
            f"DDL's exit to that path being unreachable; an index for a path nobody can take "
            f"is exactly what T25u deleted on the event family"
        )


def test_the_EVENT_vector_ddl_must_NOT_come_back():
    """The other half of that sentence, and it is the opposite answer (T25 ④).

    This test used to demand `event_embeddings_*` SURVIVE, for the entity family's reason —
    its docstring said "nothing else in the tree says these two families have different
    fates, so this test does". The workload says it: `(:Event).embedding_1024` has **no
    producer and no reader in any language**, and on the live graphs 1186 events carry 0
    embeddings (dev) and 110 carry 0 (iso). An index over a property nothing writes protects
    no read path, so the coupling was the NAME, not the fact.

    Asserting the absence rather than deleting the test: a family that came back would come
    back silently, and the next reader of `neo4j_schema.cypher` has no way to know it was
    considered and rejected.
    """
    schema = _SCHEMA.read_text()
    found = re.findall(r"CREATE VECTOR INDEX (event_embeddings_\d+)", _declarations(schema))
    assert not found, (
        f"{found} is declared again — nothing writes `(:Event).embedding_<dim>`, so this "
        f"indexes a property that does not exist. If an event embedder has since been "
        f"built, delete this test and say so; do not restore the index alone."
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
