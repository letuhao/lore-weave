"""T46/§6.3c — the AGE graph and the vector tables must share ONE database.

The PO chose (2026-08-23) to keep AGE on its own `knowledge-pg` instance rather than move it
onto the shared `postgres`. That decision has a half a deployment can get wrong: moving ONE of
the two DSNs looks like a tidy-up and quietly breaks §3.3c's join.

⚠️ **The failure is silent, which is the entire reason this is a check.** T25r's resolver reads
the graph for the ids a vector search returned. Point it at a database with no graph — or worse
an EMPTY one — and it answers nothing; `glossary.py` maps that to `0.0` and multiplies every
score by it, so two-layer entity ranking degrades to raw cosine order. Correct-looking, wrong,
and no error anywhere.

So the cases below are mostly about what must NOT be treated as the same database.
"""

from __future__ import annotations

import logging

import pytest

from app.main import _same_database, _warn_if_graph_and_vectors_are_split

_PG = "postgresql://u:p@knowledge-pg:5432/loreweave_knowledge_vectors"


@pytest.mark.parametrize("other,same", [
    (_PG, True),
    # Credentials are NOT identity: the same database reached with a different role is still
    # the same database, and treating it as a split would fire on every rotated password.
    ("postgresql://other:secret@knowledge-pg:5432/loreweave_knowledge_vectors", True),
    # The default port is implied — `:5432` and no port are one address, not two.
    ("postgresql://u:p@knowledge-pg/loreweave_knowledge_vectors", True),
    ("postgresql://U:P@KNOWLEDGE-PG:5432/loreweave_knowledge_vectors", True),
    # ...and the three ways it is genuinely a different database:
    ("postgresql://u:p@postgres:5432/loreweave_knowledge_vectors", False),      # host
    ("postgresql://u:p@knowledge-pg:5433/loreweave_knowledge_vectors", False),  # port
    ("postgresql://u:p@knowledge-pg:5432/loreweave_knowledge", False),          # database
])
def test_same_database_compares_the_ADDRESS_not_the_credentials(other, same):
    assert _same_database(_PG, other) is same


def test_a_SPLIT_is_reported_as_an_error(caplog):
    """The message must name the consequence, not just the mismatch. An operator reading
    'DSNs differ' has no reason to act; one reading 'entity ranking falls back to raw cosine'
    does."""
    with caplog.at_level(logging.ERROR):
        _warn_if_graph_and_vectors_are_split_with(
            age="postgresql://u:p@knowledge-pg:5432/loreweave_knowledge_vectors",
            vec="postgresql://u:p@postgres:5432/loreweave_knowledge_vectors")
    assert any("raw cosine order" in r.message for r in caplog.records), caplog.text


def test_the_MATCHING_case_is_silent(caplog):
    """A check that logs on the healthy path trains its reader to ignore it."""
    with caplog.at_level(logging.ERROR):
        _warn_if_graph_and_vectors_are_split_with(age=_PG, vec=_PG)
    assert not caplog.records


def test_a_MISSING_dsn_is_the_other_check_s_business(caplog):
    """`init_age_pool` already reports an unset AGE DSN. Reporting it twice, in different
    words, is how an operator learns to skim both."""
    with caplog.at_level(logging.ERROR):
        _warn_if_graph_and_vectors_are_split_with(age="", vec=_PG)
        _warn_if_graph_and_vectors_are_split_with(age=_PG, vec="")
    assert not caplog.records


def _warn_if_graph_and_vectors_are_split_with(*, age: str, vec: str) -> None:
    """Drive the real function with a given environment, restoring it afterwards."""
    import os

    prev = (os.environ.get("KNOWLEDGE_AGE_DB_URL"), os.environ.get("KNOWLEDGE_VECTOR_DB_URL"))
    os.environ["KNOWLEDGE_AGE_DB_URL"] = age
    os.environ["KNOWLEDGE_VECTOR_DB_URL"] = vec
    try:
        _warn_if_graph_and_vectors_are_split()
    finally:
        for key, value in zip(("KNOWLEDGE_AGE_DB_URL", "KNOWLEDGE_VECTOR_DB_URL"), prev):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
