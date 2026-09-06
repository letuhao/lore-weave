"""An existing deployment that sets nothing must keep the graph it already has.

🔴 THE SHIP HAZARD THIS CLOSES. `DEFAULT_BACKEND` is `age`, and every reader used to spell
the fallback itself: `os.environ.get("KNOWLEDGE_GRAPH_BACKEND", "age")`, in three places.
An installation that has only ever run Neo4j, and therefore has no `KNOWLEDGE_AGE_DB_URL`
at all, would upgrade to main and be told it is an AGE deployment.

What follows is the quiet part. It does not crash: `init_age_pool()` returns falsy, startup
logs ONE warning, and graph reads refuse — while an unprovisioned store and a store with no
rows are the same two hundred bytes of JSON to everything downstream. The failure looks like
"this book has no knowledge yet".

So an UNSET variable is now resolved from what the deployment has PROVISIONED. The cases
below are the upgrade matrix; `test_graph_backend_default.py` still pins the constant, and
these do not contradict it — `DEFAULT_BACKEND` is unchanged and is what a fresh install
still gets.

⚠️ Every case passes an explicit `env` mapping. `tests/conftest.py` pins
`KNOWLEDGE_GRAPH_BACKEND=neo4j` for the whole suite, so a test reading `os.environ` here
would be asserting the pin — the exact hole the sibling module's docstring calls out.
"""

from __future__ import annotations

import pytest

from app.db.graph_backend import (
    BACKENDS,
    DEFAULT_BACKEND,
    configured_backend,
    known_backends,
    resolve_unset_backend,
)

_NEO4J_ONLY = {"NEO4J_URI": "bolt://neo4j:7687"}
_AGE_ONLY = {"KNOWLEDGE_AGE_DB_URL": "postgresql://u@knowledge-pg:5432/k"}
_BOTH = {**_NEO4J_ONLY, **_AGE_ONLY}


# ── the upgrade matrix ───────────────────────────────────────────────────────


def test_an_existing_neo4j_deployment_that_sets_NOTHING_keeps_neo4j():
    """THE CASE THIS FILE EXISTS FOR. Nothing else in the suite covers the shape of a
    real installation upgrading: a Neo4j URI, no AGE DSN, no backend variable."""
    assert resolve_unset_backend(_NEO4J_ONLY) == "neo4j", (
        "an installation with only Neo4j provisioned was told it is an AGE deployment — "
        "it has no AGE database, so graph reads refuse and every book reads as empty"
    )


def test_a_deployment_that_provisioned_AGE_gets_age():
    assert resolve_unset_backend(_AGE_ONLY) == "age"


def test_when_BOTH_are_provisioned_the_sealed_default_wins():
    """The inference must not second-guess §8.1 on a box that has both. It exists only to
    avoid naming a store the operator never created — and here they created it."""
    assert resolve_unset_backend(_BOTH) == "age" == DEFAULT_BACKEND


def test_a_fresh_install_with_nothing_provisioned_still_gets_the_DEFAULT():
    """No inference to make, so no invention: the constant answers, and the missing-DSN
    guard downstream is what reports it. A fallback to `neo4j` here would quietly undo the
    PO's decision for every new install."""
    assert resolve_unset_backend({}) == DEFAULT_BACKEND == "age"


# ── explicit configuration always wins ───────────────────────────────────────


@pytest.mark.parametrize("chosen,env", [
    ("neo4j", _AGE_ONLY),   # pinned to neo4j on a box that HAS age
    ("age", _NEO4J_ONLY),   # pinned to age on a box that HAS neo4j
])
def test_an_explicit_choice_overrides_what_is_provisioned(chosen, env):
    """The inference is for the UNSET case only. An operator who names a backend gets it,
    even against the evidence — being able to point a service at a store you are still
    filling is the whole migration workflow."""
    assert configured_backend(env={**env, "KNOWLEDGE_GRAPH_BACKEND": chosen}) == chosen


def test_the_variable_being_set_is_what_counts_not_its_agreement_with_the_evidence():
    """A pinned backend with NOTHING provisioned still resolves — it must fail at the DSN
    guard with a message about the DSN, not here with a message about inference."""
    assert configured_backend(env={"KNOWLEDGE_GRAPH_BACKEND": "age"}) == "age"


# ── refusals: the registry answers, and it never guesses ─────────────────────


def test_an_unknown_backend_is_refused_and_the_message_names_the_registry():
    with pytest.raises(ValueError) as e:
        configured_backend(env={"KNOWLEDGE_GRAPH_BACKEND": "mongo"})
    for name in known_backends():
        assert name in str(e.value), "the refusal must list what IS available"


def test_an_EMPTY_value_is_treated_as_UNSET_and_infers():
    """The container case, and the one place "refuse rather than guess" is overruled.

    `KNOWLEDGE_GRAPH_BACKEND: ${KNOWLEDGE_GRAPH_BACKEND:-}` is how a compose file says "the
    operator did not choose", and Kubernetes and CI runners do the same. The previous code
    RAISED on empty; keeping that would turn the ordinary deployment into a startup failure
    and push people back onto a hardcoded default — the hazard this whole change removes.

    Nothing is guessed: the empty case falls through to the same provisioning evidence.
    """
    assert configured_backend(env={"KNOWLEDGE_GRAPH_BACKEND": "", **_NEO4J_ONLY}) == "neo4j"
    assert configured_backend(env={"KNOWLEDGE_GRAPH_BACKEND": "", **_AGE_ONLY}) == "age"
    assert configured_backend(env={"KNOWLEDGE_GRAPH_BACKEND": ""}) == DEFAULT_BACKEND


def test_a_WRONG_value_is_still_refused_even_though_a_blank_one_is_not():
    """The distinction that matters is absent-vs-wrong, not absent-vs-blank. Relaxing the
    empty case must not relax this one, or a typo (`age `, `Neo4J`, `agee`) would silently
    resolve to whatever the deployment happens to have."""
    with pytest.raises(ValueError):
        configured_backend(env={"KNOWLEDGE_GRAPH_BACKEND": "agee", **_AGE_ONLY})


def test_an_EVALUATION_backend_is_registered_but_refused_WITH_ITS_REASON():
    """`kuzu` resolves to a sentence rather than a KeyError. The reason is structural —
    `KuzuGraphStore` takes an open connection, not a `CypherSession` — so an operator who
    tries it learns why instead of filing a bug."""
    with pytest.raises(ValueError) as e:
        configured_backend(env={"KNOWLEDGE_GRAPH_BACKEND": "kuzu"})
    assert "not selectable" in str(e.value)
    assert "CypherSession" in str(e.value), "the refusal must carry the structural reason"


# ── the registry itself ──────────────────────────────────────────────────────


def test_every_registered_backend_names_the_env_that_provisions_it():
    """`resolve_unset_backend` is only as honest as this field: a backend whose
    `provision_env` is blank cannot be detected, so it would silently never be inferred."""
    blank = [n for n, s in BACKENDS.items() if not s.provision_env.strip()]
    assert not blank, f"registered backends with no provisioning env: {blank}"


def test_the_two_production_backends_are_still_the_two_that_ship():
    """A floor, not a ceiling — adding an engine is expected. This catches the opposite:
    a backend quietly losing `production` status, which would make every deployment
    pinned to it refuse to start."""
    production = {n for n, s in BACKENDS.items() if s.selectable}
    assert {"neo4j", "age"} <= production, (
        f"a shipping backend stopped being selectable: {production}"
    )
