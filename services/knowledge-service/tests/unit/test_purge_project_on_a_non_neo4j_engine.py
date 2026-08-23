"""T17/§10.1 — index administration refuses by NAME, and `purge_project` survives the refusal.

`purge_project` is a general repo function: it runs on whatever session it is handed, and since
T54c that follows the configured backend — which since T54 defaults to **AGE**. Its node purge is
portable Cypher, but its second half sweeps per-project summary vector indexes, and
`SHOW VECTOR INDEXES` is Neo4j index administration, not Cypher. AGE wraps every statement in
`SELECT * FROM cypher(...)`, where it is a SQL parse error — measured on iso:

    PostgresSyntaxError: syntax error at or near "SHOW"

The raise was already happening. What it was not doing was saying anything: the caller
(`routers/public/projects.py`) wraps the whole purge in `except Exception` and logs
*"graph orphaned, re-sweep owed"*. So on the default backend every project delete reported an
orphaned graph whose nodes had in fact just been deleted — and that message was indistinguishable
from a purge that genuinely failed.

Rule 9: an adapter that cannot honour an operation RAISES, naming its spec section.
"""

from __future__ import annotations

import pytest

from app.db.neo4j_repos.project_graph import purge_project
from app.db.neo4j_repos.vector_indexes import (
    drop_summary_index,
    list_summary_vector_indexes,
)


class _Session:
    """A session that DECLARES its engine, which is what `engine_of` reads (§10.1)."""

    def __init__(self, engine: str, *, counts: int = 0) -> None:
        self.engine = engine
        self._counts = counts
        self.ran: list[str] = []

    async def run(self, cypher: str, /, **params):
        self.ran.append(cypher)
        return _Rows([{"n": self._counts}] if "count(n)" in cypher else [])


class _Rows:
    def __init__(self, rows): self._rows = rows
    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r
        return gen()


@pytest.mark.asyncio
async def test_index_admin_refuses_by_name_on_a_non_neo4j_session():
    with pytest.raises(NotImplementedError) as exc:
        await list_summary_vector_indexes(_Session("age"))
    msg = str(exc.value)
    assert "list_summary_vector_indexes" in msg, "the refusal must name the operation"
    assert "'age'" in msg, "the refusal must name the engine it was handed"
    assert "§3.1" in msg, "rule 9 — a refusal cites the section that decided it"


@pytest.mark.asyncio
async def test_the_refusal_is_not_specific_to_one_helper():
    with pytest.raises(NotImplementedError):
        await drop_summary_index(_Session("age"), "l1_summary_emb_pabc_edef")


@pytest.mark.asyncio
async def test_purge_reports_the_skip_instead_of_failing_the_whole_purge():
    """The node purge already happened; saying it did is the point."""
    out = await purge_project(_Session("age", counts=7), "0" * 8 + "-0000-0000-0000-" + "0" * 12)
    assert out["nodes_deleted"] == 7, "the portable half must still be reported"
    assert out["indexes_dropped"] == 0
    assert "Neo4j-only capability" in out["indexes_skipped"], (
        "the caller logs 'graph orphaned' on any exception, so the skip has to come back as a "
        "VALUE rather than as a raise"
    )


@pytest.mark.asyncio
async def test_a_neo4j_session_is_NOT_refused():
    """The control arm (rule 3).

    Every assertion above is satisfiable by a guard that refuses everything, which would break
    the engine this capability actually exists for. Derived from the opposite case to the one
    that motivated the guard: a Neo4j session must reach the driver, not the refusal.
    """
    session = _Session("neo4j")
    out = await purge_project(session, "0" * 8 + "-0000-0000-0000-" + "0" * 12)
    assert "indexes_skipped" not in out, "a Neo4j session must not be refused"
    assert any("SHOW VECTOR INDEXES" in c for c in session.ran), (
        "the Neo4j path must actually issue the index-admin command"
    )


@pytest.mark.asyncio
async def test_a_REAL_index_failure_still_propagates():
    """The catch must stay narrow, and this is what stops it widening.

    `except NotImplementedError` and `except Exception` are one word apart, and the wider one
    reads as more robust. It is not: it would swallow a genuine Neo4j index-admin failure and
    report `indexes_dropped: 0` as though the sweep had run, which is the silent-success defect
    the narrow catch exists to avoid.
    """
    class _Boom(_Session):
        async def run(self, cypher: str, /, **params):
            if "SHOW VECTOR INDEXES" in cypher:
                raise RuntimeError("neo4j: index admin unavailable")
            return await super().run(cypher, **params)

    with pytest.raises(RuntimeError, match="index admin unavailable"):
        await purge_project(_Boom("neo4j", counts=3), "0" * 8 + "-0000-0000-0000-" + "0" * 12)


# ── fulltext search: the same capability gap, but this one reaches USERS ──────────────────


@pytest.mark.asyncio
async def test_fulltext_search_refuses_by_name_on_a_non_neo4j_session():
    """`CALL db.index.fulltext.queryNodes` is Neo4j-only, and this path is NOT engine-routed.

    The two vector readers are reached only through `Neo4jVectorStore`, which is engine-scoped
    by construction. `find_passages_by_fulltext` is different: `search/retriever.py` calls it on
    a `neo4j_session()`, which since T54c follows the CONFIGURED backend — AGE by default. So on
    a default deployment it ran and raised `PostgresSyntaxError: syntax error at or near "."`,
    measured on iso.
    """
    from app.db.neo4j_repos.passages import find_passages_by_fulltext

    with pytest.raises(NotImplementedError) as exc:
        await find_passages_by_fulltext(
            _Session("age"), user_id="u", project_id="p", query="q",
            source_type="chapter", limit=5, include_drafts=False,
        )
    msg = str(exc.value)
    assert "find_passages_by_fulltext" in msg
    assert "fulltext search" in msg, "the refusal must name the CAPABILITY, not just the caller"
    assert "'age'" in msg and "§3.1" in msg


@pytest.mark.asyncio
async def test_fulltext_search_is_NOT_refused_on_neo4j():
    """Control arm — a guard that refuses everything would silently kill CJK search on Neo4j."""
    from app.db.neo4j_repos.passages import find_passages_by_fulltext

    session = _Session("neo4j")
    try:
        await find_passages_by_fulltext(
            session, user_id="u", project_id="p", query="q",
            source_type="chapter", limit=5, include_drafts=False,
        )
    except NotImplementedError:  # pragma: no cover - the assertion below is the point
        pytest.fail("a Neo4j session must reach the driver, not the refusal")
    except Exception:
        pass  # the stub session is not a real driver; only the REFUSAL is under test here
    assert session.ran, "the Neo4j path must actually issue a query"


# ── summary blend: the third site, and the one on the context hot path ────────────────────


@pytest.mark.asyncio
async def test_summary_index_search_refuses_by_name_on_a_non_neo4j_session():
    """`query_summary_index` reaches `CALL db.index.vector.queryNodes` and runs on a
    backend-following session via `context/modes/full.py::_safe_summary_blend`.

    Measured on iso before the guard: `PostgresSyntaxError: syntax error at or near "."`,
    swallowed by `except Exception` into a WARNING with a stack trace reading
    *"summary_blend failed — degrading"*, on every Mode 3 request.
    """
    from app.db.neo4j_repos.vector_indexes import query_summary_index

    with pytest.raises(NotImplementedError) as exc:
        await query_summary_index(
            _Session("age"), project_id="p", embedding_model_uuid="e",
            level="chapter", query_embedding=[0.1] * 8, top_k=3,
        )
    msg = str(exc.value)
    assert "query_summary_index" in msg and "vector index search" in msg
    assert "'age'" in msg and "§3.1" in msg


@pytest.mark.asyncio
async def test_summary_index_search_is_NOT_refused_on_neo4j():
    """Control arm — the summary blend must still run on the engine that has the indexes."""
    from app.db.neo4j_repos.vector_indexes import query_summary_index

    session = _Session("neo4j")
    try:
        await query_summary_index(
            session, project_id="p", embedding_model_uuid="e",
            level="chapter", query_embedding=[0.1] * 8, top_k=3,
        )
    except NotImplementedError:  # pragma: no cover
        pytest.fail("a Neo4j session must reach the driver, not the refusal")
    except Exception:
        pass  # the stub is not a real driver; only the REFUSAL is under test
    assert session.ran, "the Neo4j path must actually issue the query"
