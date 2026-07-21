"""DB-safety guard for the composition integration/db test tree.

db-safety-gate: guarded-dir — every DB-touching test under this directory is preceded by
_guard_throwaway(), which refuses a non-throwaway TEST_COMPOSITION_DB_URL before any pool
is opened, so these DROP/TRUNCATE fixtures can never wipe a real service database. (See
CLAUDE.md › "Destructive DB ops in tests" + scripts/db-safety-gate.py.)

WHY a conftest guard (not a per-file line): every module here reads a module-level
`_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")` and opens `asyncpg.create_pool(_DSN)`
inside a *function-scoped* fixture, then DROP/TRUNCATEs tables. The session-scoped, autouse
guard below is set up BEFORE any of those function-scoped pool fixtures (a higher-scoped
fixture is always instantiated first in a test's setup chain), so no destructive statement
in this tree can run until the guard has vetted the DSN. This centralizes the check once,
covers every existing file, and auto-protects any file added to the dir later.

The DSN is read ONLY from the dedicated test var — never a fallback to the production
COMPOSITION_DB_URL, which in any dev shell points at the real loreweave_composition the
DROP/TRUNCATE would wipe (the kg-integration-tests-truncate-shared-dev-db incident class).
"""

import os
import re

import pytest

# A disposable test DB name carries one of these markers; a real service DB
# (loreweave_composition) carries none. Byte-identical to the campaign-service reference
# (services/campaign-service/tests/integration/conftest.py) and scripts/db-safety-gate.py.
_THROWAWAY = re.compile(r"(?i)(test|smoke|audit|scratch|throwaway|tmp|sandbox|ephemeral)")


def _guard_throwaway(dsn: str) -> None:
    db = dsn.rsplit("/", 1)[-1].split("?", 1)[0]
    if not _THROWAWAY.search(db):
        raise RuntimeError(
            f"REFUSING: TEST_COMPOSITION_DB_URL database {db!r} is not a throwaway DB "
            "(the name must contain test/smoke/audit/…). These fixtures DROP/TRUNCATE tables — "
            "point it at a disposable DB, never the real loreweave_composition."
        )


@pytest.fixture(scope="session", autouse=True)
def _guard_composition_test_db():
    """Refuse a non-throwaway TEST_COMPOSITION_DB_URL before ANY db/ test opens a pool.

    Session-scoped + autouse ⇒ set up before every function-scoped pool fixture in this
    tree, so a DSN naming a real service DB raises here and no destructive statement can
    reach it. When the var is unset the guard is a no-op and the individual tests skip via
    their own `pytest.mark.skipif(not _DSN, ...)`."""
    dsn = os.environ.get("TEST_COMPOSITION_DB_URL")
    if dsn:
        _guard_throwaway(dsn)  # refuse a real DB BEFORE any fixture's DROP/TRUNCATE
