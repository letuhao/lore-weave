"""Which graph engine this process is configured for — one home, read by four layers.

⚠️ **This module exists because the answer was living inside `graph_store_provider`, and by
T54c three separate layers needed it**: the adapter provider (which `GraphStore` to build),
`db.neo4j.graph_session` (which session to open for the repo layer), and the AGE session
itself. Importing an ADAPTER module to learn a piece of CONFIGURATION is the wrong direction,
and `port-adoption-gate` said so immediately — its GraphStore-adopter count rose from 19 to 21
on two imports that touch no store at all. A number that counts "modules using the port" must
not count modules reading an environment variable.

The constant is also the kind that drifts when duplicated: `_DEFAULT_BACKEND = "age"` in the
provider and a bare `"age"` in a session factory are one edit away from disagreeing, and the
symptom would be half the service on each engine — which is precisely what T54b measured on
dev and reverted.

── UPGRADE SAFETY: WHAT AN EXISTING DEPLOYMENT GETS WHEN IT SETS NOTHING ─────────────────

`DEFAULT_BACKEND` is `age` and stays `age` (§8.1, PO 2026-08-22). But a bare
`os.environ.get(BACKEND_ENV, "age")` answers a question nobody asked: it tells a
deployment that has only ever run Neo4j, and has no AGE database at all, that it is an AGE
deployment. What that deployment then does is not fail — it warns once at startup and
serves an EMPTY graph, because an unprovisioned store and a store with no rows are the same
two hundred bytes of JSON. Shipping that to main would break every existing installation in
the quietest possible way.

So an UNSET variable is resolved from what the deployment has actually provisioned:

    KNOWLEDGE_AGE_DB_URL set   -> age     (the default, honoured)
    else NEO4J_URI set         -> neo4j   (it has a graph; keep serving it)
    else                       -> age     (a fresh install; DEFAULT_BACKEND)

This is NOT "choosing an engine by configuration drift", which is the thing T54 forbids —
that phrase is about a CANDIDATE becoming the default without the shadow comparison
deciding it. An explicit `KNOWLEDGE_GRAPH_BACKEND` always wins, unchanged. The inference
only answers the case where the old code would have named a store the operator never
created, and it refuses to invent one either way: `resolve_unset_backend` returns
`DEFAULT_BACKEND` when it can see nothing, so a fresh install still lands on AGE and the
missing-DSN guard still fires.

── ADDING AN ENGINE ─────────────────────────────────────────────────────────────────────

`BACKENDS` is a registry, not a `Literal`. A new engine is one entry plus a branch in
`graph_store_provider.get_graph_store`; nothing here enumerates engines again. `kuzu` is
registered as EVALUATION so the name resolves and the reason it is not selectable is a
sentence rather than a `KeyError` — see its `note`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

__all__ = [
    "BACKEND_ENV", "BACKENDS", "DEFAULT_BACKEND", "Backend", "BackendSpec",
    "configured_backend", "known_backends", "resolve_unset_backend",
]

#: A backend NAME. Deliberately not a `Literal`: the set is the registry below, and a
#: closed type would have to be edited in lockstep with it — the same duplication this
#: module was created to remove.
Backend = str

BACKEND_ENV = "KNOWLEDGE_GRAPH_BACKEND"


@dataclass(frozen=True)
class BackendSpec:
    """One engine, and how a deployment proves it HAS that engine.

    `provision_env` is the variable whose presence means "this store exists here". It is
    what makes the unset-variable case answerable without guessing: a deployment that has
    never set `KNOWLEDGE_AGE_DB_URL` does not have an AGE database, whatever the default
    says.
    """

    name: str
    provision_env: str
    #: "production" — selectable by a real deployment. "evaluation" — the adapter exists
    #: and is exercised by a harness, but selecting it for a service is not supported.
    status: str
    note: str

    @property
    def selectable(self) -> bool:
        return self.status == "production"


BACKENDS: dict[str, BackendSpec] = {
    "neo4j": BackendSpec(
        name="neo4j",
        provision_env="NEO4J_URI",
        status="production",
        note="The original engine, and NOT retired: T43's shadow harness compares "
             "Neo4j against AGE and the two backend benchmarks are the only things that "
             "can compare engines. Deleting it would remove the instrument that proves "
             "the AGE adapter correct.",
    ),
    "age": BackendSpec(
        name="age",
        provision_env="KNOWLEDGE_AGE_DB_URL",
        status="production",
        note="Apache AGE over Postgres. The default for a fresh install (§8.1, PO "
             "2026-08-22).",
    ),
    "kuzu": BackendSpec(
        name="kuzu",
        provision_env="KNOWLEDGE_KUZU_PATH",
        status="evaluation",
        note="EVALUATION ONLY, and the reason is structural rather than a missing "
             "feature: `KuzuGraphStore` takes an open Kuzu CONNECTION, not a "
             "`CypherSession`. The file lock means the process may hold exactly one, so "
             "ownership belongs to whoever opened it — `get_graph_store(session)` has no "
             "session to give it. Registered so the name resolves to this sentence "
             "instead of a KeyError, and so `port-adoption-gate`'s evaluation-only "
             "declaration has a home in code.",
    ),
}

#: §8.1 (PO 2026-08-22) — **AGE is the default.** Unchanged, and deliberately still a
#: constant: `test_graph_backend_default.py` reads it directly, because the suite pins the
#: environment and an assertion against `os.environ` would be asserting the pin.
DEFAULT_BACKEND: Backend = "age"


def known_backends() -> tuple[str, ...]:
    return tuple(BACKENDS)


def _selectable() -> tuple[str, ...]:
    return tuple(n for n, s in BACKENDS.items() if s.selectable)


def resolve_unset_backend(env: Mapping[str, str] | None = None) -> Backend:
    """The engine for a deployment that never set `KNOWLEDGE_GRAPH_BACKEND`.

    Reads only PROVISIONING variables, never the backend variable itself — the caller has
    already established it is unset. Takes `env` so a test can drive an old deployment's
    environment without mutating the process.
    """
    e = os.environ if env is None else env

    def has(spec: BackendSpec) -> bool:
        return bool((e.get(spec.provision_env) or "").strip())

    # AGE first: when a deployment has provisioned AGE, the sealed default applies and this
    # inference must not second-guess it, even on a box that also still runs Neo4j.
    if has(BACKENDS["age"]):
        return "age"
    # It has a graph and it is not AGE. Keep serving it. This single line is what stops the
    # main-branch upgrade from pointing every existing installation at a database it has
    # never created.
    if has(BACKENDS["neo4j"]):
        return "neo4j"
    # Nothing provisioned: a fresh install, or a Track-1 dev box with no graph at all. The
    # default answers, and the missing-DSN guard downstream is what reports it.
    return DEFAULT_BACKEND


def configured_backend(override: str | None = None,
                       env: Mapping[str, str] | None = None) -> Backend:
    """The engine this process should use, or `override` when a caller pins one.

    Raises on anything else rather than falling back. A backend that silently is not the one
    you selected is the defect T54 exists to fix: T42/T43 closed green while `age` could not
    be selected at all, and T54b then found half the service reading an empty AGE graph
    without a single error.
    """
    e = os.environ if env is None else env
    raw = override if override is not None else e.get(BACKEND_ENV)

    if raw is None:
        return resolve_unset_backend(e)

    chosen = raw.strip().lower()
    if not chosen:
        # EMPTY IS UNSET, and this is the one place the container world overrules the
        # "refuse rather than guess" reflex. The previous code raised here. In Compose,
        # Kubernetes and every CI runner, an unset variable interpolates to the EMPTY
        # STRING — `KNOWLEDGE_GRAPH_BACKEND: ${KNOWLEDGE_GRAPH_BACKEND:-}` is precisely how
        # a compose file says "the operator did not choose". Refusing there would turn the
        # ordinary case into a startup failure and push deployments back onto a hardcoded
        # default, which is the hazard this module exists to remove.
        #
        # Nothing is guessed by falling through: `resolve_unset_backend` reads what the
        # deployment has PROVISIONED. A garbage value is still refused below — the
        # distinction that matters is "absent" vs "wrong", not "absent" vs "blank".
        return resolve_unset_backend(e)
    spec = BACKENDS.get(chosen)
    if spec is None:
        raise ValueError(
            f"{BACKEND_ENV}={chosen!r} is not a graph backend — expected one of "
            f"{', '.join(known_backends())}. Refusing to guess."
        )
    if not spec.selectable:
        raise ValueError(
            f"{BACKEND_ENV}={chosen!r} is registered but not selectable for a service. "
            f"{spec.note}"
        )
    return spec.name
