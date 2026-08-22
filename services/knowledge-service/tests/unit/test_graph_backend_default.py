"""T54 — the DEFAULT graph backend, asserted where pinning the suite cannot hide it.

`tests/conftest.py` pins `KNOWLEDGE_GRAPH_BACKEND=neo4j` because this suite's doubles are
Neo4j-session shaped. That pin is necessary and it creates a hole: with the environment fixed,
no test in the suite would notice if the default silently reverted to `neo4j` — the exact
shape of defect this plan keeps finding, where a pin makes the thing it pins unobservable.

So these read the provider's own constant and its refusal path, neither of which the pin
touches.
"""

from __future__ import annotations

import pytest

from app.adapters import graph_store_provider as prov


def test_the_process_default_is_AGE():
    """§8.1 (PO 2026-08-22): AGE is the default; Neo4j stays selectable.

    Reads the module constant, NOT `os.environ` — conftest has pinned the environment and an
    assertion against it would be asserting the pin.
    """
    assert prov._DEFAULT_BACKEND == "age", (
        "the graph default is no longer AGE. T54 flipped it deliberately; if this changed, "
        "say so in the plan rather than in a constant."
    )


def test_neo4j_is_still_SELECTABLE_and_not_retired():
    """The counterweight, and it is the whole reason Neo4j survives the cutover.

    T43's shadow harness compares Neo4j against AGE and the two backend benchmarks are the
    only things that can compare engines. A 'retirement' that removed this branch would delete
    the instrument that proves the new default correct.
    """
    class _Sess:  # a stand-in; Neo4jGraphStore only stores it
        pass

    import os
    prev = os.environ.get("KNOWLEDGE_GRAPH_BACKEND")
    os.environ["KNOWLEDGE_GRAPH_BACKEND"] = "neo4j"
    try:
        store = prov.get_graph_store(_Sess())
        assert type(store).__name__ == "Neo4jGraphStore"
    finally:
        if prev is None:
            os.environ.pop("KNOWLEDGE_GRAPH_BACKEND", None)
        else:
            os.environ["KNOWLEDGE_GRAPH_BACKEND"] = prev


def test_age_without_a_DSN_REFUSES_rather_than_falling_back_to_neo4j():
    """The defect T54 exists to fix, in miniature.

    T42/T43 closed green while `KNOWLEDGE_GRAPH_BACKEND=age` raised — the adapter was built,
    conformance-tested, and unselectable. The mirror-image failure is worse: selecting `age`
    and quietly getting Neo4j, so a cutover reports success while nothing moved. It must
    REFUSE, and the message must name the missing DSN.
    """
    class _Sess:
        pass

    import os

    # T54c moved the pool to `db.age_pool` — it is a database handle, and holding it in the
    # adapter module made `neo4j_session` import an adapter to open a session. The provider
    # re-exports the accessor, so patch the pool where it now LIVES rather than where it is
    # re-exported from: patching the alias would leave the real module-level `_POOL` in place
    # and the refusal below could pass for the wrong reason.
    from app.db import age_pool as age_pool_mod

    prev_b = os.environ.get("KNOWLEDGE_GRAPH_BACKEND")
    prev_pool = age_pool_mod._POOL
    os.environ["KNOWLEDGE_GRAPH_BACKEND"] = "age"
    age_pool_mod._POOL = None
    try:
        with pytest.raises(RuntimeError, match="KNOWLEDGE_AGE_DB_URL"):
            prov.get_graph_store(_Sess())
    finally:
        age_pool_mod._POOL = prev_pool
        if prev_b is None:
            os.environ.pop("KNOWLEDGE_GRAPH_BACKEND", None)
        else:
            os.environ["KNOWLEDGE_GRAPH_BACKEND"] = prev_b
