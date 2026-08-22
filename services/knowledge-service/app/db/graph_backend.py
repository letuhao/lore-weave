"""Which graph engine this process is configured for — one home, read by three layers.

⚠️ **This module exists because the answer was living inside `graph_store_provider`, and by
T54c three separate layers needed it**: the adapter provider (which `GraphStore` to build),
`db.neo4j.neo4j_session` (which session to open for the repo layer), and the AGE session
itself. Importing an ADAPTER module to learn a piece of CONFIGURATION is the wrong direction,
and `port-adoption-gate` said so immediately — its GraphStore-adopter count rose from 19 to 21
on two imports that touch no store at all. A number that counts "modules using the port" must
not count modules reading an environment variable.

The constant is also the kind that drifts when duplicated: `_DEFAULT_BACKEND = "age"` in the
provider and a bare `"age"` in a session factory are one edit away from disagreeing, and the
symptom would be half the service on each engine — which is precisely what T54b measured on
dev and reverted.
"""

from __future__ import annotations

import os
from typing import Literal

__all__ = ["BACKEND_ENV", "DEFAULT_BACKEND", "Backend", "configured_backend"]

Backend = Literal["neo4j", "age"]

BACKEND_ENV = "KNOWLEDGE_GRAPH_BACKEND"

#: T54 (§8.1/§8.2, PO 2026-08-22) — **AGE is the default.** Neo4j stays selectable and is not
#: retired: T43's shadow harness compares Neo4j↔AGE and the two backend benchmarks are the only
#: things that can compare engines, so deleting it would remove the instrument that proves the
#: AGE adapter correct. `port-adoption-gate`'s vector-bypass floor of 2 exists for the same
#: reason.
DEFAULT_BACKEND: Backend = "age"


def configured_backend(override: str | None = None) -> Backend:
    """The engine this process should use, or `override` when a caller pins one.

    Raises on anything else rather than falling back. A backend that silently is not the one
    you selected is the defect T54 exists to fix: T42/T43 closed green while `age` could not be
    selected at all, and T54b then found half the service reading an empty AGE graph without a
    single error.
    """
    chosen = (override or os.environ.get(BACKEND_ENV, DEFAULT_BACKEND)).strip().lower()
    if chosen not in ("neo4j", "age"):
        raise ValueError(
            f"{BACKEND_ENV}={chosen!r} is not a graph backend — expected 'neo4j' or 'age'. "
            f"Refusing to guess."
        )
    return chosen  # type: ignore[return-value]
