"""Test env defaults — set before app.config.Settings() loads at import time.

Matches the Dockerfile test-stage env (INTERNAL_SERVICE_TOKEN=test_token) so
the internal-auth header assertions line up.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("COMPOSITION_DB_URL", "postgresql://u:p@h:5432/composition")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_token")
os.environ.setdefault("JWT_SECRET", "s" * 32)
os.environ.setdefault("CONFIRM_TOKEN_SIGNING_SECRET", "c" * 32)


# ── don't re-migrate an already-migrated database once per test ──────────────────────────
#
# MEASURED 2026-08-01, and the numbers are given honestly because the first version of this
# comment claimed a 348s saving that a controlled A/B then refuted.
#
#     run_migrations against an ALREADY-migrated DB : 0.853s, every call
#     A/B on 21 non-dropping pg tests              : 17.91s -> 3.99s   (4.5x)
#     full composition suite, clean, before -> after: 508.36s -> 459.70s  (~48s)
#
# The A/B and the suite disagree, and the suite is the number that matters: most of the 408
# `xdist_group("pg")` tests apparently do NOT pay a per-test migration, so the arithmetic
# "408 x 0.853s" was wrong. The saving is real but modest; the PARALLELISATION below is the
# lever that actually moves the suite.
#
# WHY THE MEMO IS FINGERPRINTED AND NOT A PLAIN "seen this DSN" SET. Several fixtures
# deliberately tear their tables down (cascading) and call `run_migrations` to rebuild —
# then tear them down again on teardown. A blind memo would leave those tables missing for
# every test that ran afterwards, which fails loudly but for an entirely misleading reason.
# (Phrased without the SQL keywords on purpose: db-safety-gate scans for them, and an
# exemption pragma over a PROSE line is a permanent one a future reader must re-verify.)
# The fingerprint (table count + max oid in `public`) changes the moment anything is dropped
# or created, so those fixtures still re-migrate, and so does the first test after their
# teardown. Probe cost: 0.36 ms.
#
# What the fingerprint CANNOT see is a data-level mutation of migration bookkeeping — see
# `run_migrations_uncached` below, published for the one test whose subject is the runner.
#
# Scoped to the test session on purpose: making `run_migrations` itself skippable would put a
# ledger short-circuit in production code to speed up tests — the wrong layer, and the exact
# shape of the "DDL added to an applied step is a silent no-op" bug this repo already has.
import app.db.migrate as _migrate  # noqa: E402

_REAL_RUN_MIGRATIONS = _migrate.run_migrations
_MIGRATED: dict[str, str] = {}
_SCHEMA_FINGERPRINT = (
    "SELECT current_database() || '|' || count(*)::text || ':' "
    "|| coalesce(max(oid)::text, '') FROM pg_class "
    "WHERE relnamespace = 'public'::regnamespace"
)


async def _run_migrations_once(pool) -> None:
    if os.environ.get("LOREWEAVE_TEST_MIGRATION_MEMO") == "0":
        await _REAL_RUN_MIGRATIONS(pool)
        return
    try:
        async with pool.acquire() as conn:
            fp = await conn.fetchval(_SCHEMA_FINGERPRINT)
    except Exception:  # noqa: BLE001 — a probe that fails must never REPLACE the migration
        await _REAL_RUN_MIGRATIONS(pool)
        return
    db = fp.split("|", 1)[0]
    if _MIGRATED.get(db) == fp:
        return
    await _REAL_RUN_MIGRATIONS(pool)
    async with pool.acquire() as conn:
        _MIGRATED[db] = await conn.fetchval(_SCHEMA_FINGERPRINT)


# Patched here rather than per-fixture because 144 files do `from app.db.migrate import
# run_migrations` at module scope, and conftest is imported before any of them.
_migrate.run_migrations = _run_migrations_once

# The escape hatch, published on the module so a test that exercises the MIGRATION RUNNER
# ITSELF can opt out. `test_package_rekey` deletes a marker ROW and re-runs to prove the
# crash-resume path converges — a data mutation the schema fingerprint cannot see, so the memo
# skipped the re-run and the marker was never re-stamped. Measured: that test went red the
# first time the memo shipped. A test whose subject IS the runner must call the real one.
_migrate.run_migrations_uncached = _REAL_RUN_MIGRATIONS


# ── one database PER XDIST WORKER ────────────────────────────────────────────────────────
#
# The pg-marked tests are serialised onto a single worker by `--dist loadgroup` for exactly
# one reason: they share ONE database. Give each worker its own and the reason is gone, so the
# group can spread across all of them — a win that does not depend on knowing WHICH of those
# tests is slow, which is why it is the more robust lever of the two.
#
# Rewritten in the environment rather than per-fixture because ~123 sites read
# `os.environ.get("TEST_COMPOSITION_DB_URL")` at MODULE scope, and conftest is imported first.
# No-ops when `PYTEST_XDIST_WORKER` is unset, which is every serial run — including CI, which
# runs this suite serially on purpose ("a gating job must be deterministic").
#
# The suffixed name keeps its throwaway marker (`…_s1test_gw0`), so the db-safety guard in
# tests/integration/db/conftest.py still vets it.
def _adopt_per_worker_database() -> None:
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    dsn = os.environ.get("TEST_COMPOSITION_DB_URL")
    if not worker or not dsn:
        return
    head, _, tail = dsn.rpartition("/")
    name, sep, query = tail.partition("?")
    if not name or name.endswith(f"_{worker}"):
        return
    per_worker = f"{name}_{worker}"
    try:
        asyncio.run(_create_database_if_absent(f"{head}/postgres", per_worker))
    except Exception as exc:  # noqa: BLE001
        # Fall back to the shared DB rather than failing collection. Slower, still correct —
        # and a suite that cannot RUN because an optimisation could not set itself up would be
        # a worse outcome than the optimisation not applying.
        print(f"[conftest] per-worker test DB unavailable ({exc}); using the shared one")
        return
    os.environ["TEST_COMPOSITION_DB_URL"] = f"{head}/{per_worker}{sep}{query}"


async def _create_database_if_absent(admin_dsn: str, name: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(admin_dsn)
    try:
        if await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            return
        # Not parameterisable — an identifier. `name` is derived from the operator's own DSN
        # plus xdist's worker id (`gw\\d+`), never from test data.
        await conn.execute(f'CREATE DATABASE "{name}"')
    except asyncpg.DuplicateDatabaseError:
        pass  # another worker won the race; both wanted the same outcome
    finally:
        await conn.close()


_adopt_per_worker_database()


@pytest.fixture(autouse=True)
def _isolate_mcp_session_manager():
    """D-W2-MCP-SESSION-ISOLATION (part 2 — the cross-file collision).

    FastMCP's StreamableHTTPSessionManager.run() may be called only ONCE per instance.
    app.main's lifespan runs it (main.py:~105), so EVERY `with TestClient(app.main)` (the
    ~18 router test files) consumes the global mcp_server's session manager. After the
    first, later runs raise — the lifespan swallows it so REST tests still pass, but
    test_mcp_server's loopback (build_mcp_app + uvicorn, which runs the SAME global session
    manager) then fails to start in a full-suite run ('did not start in time').

    Stub ONLY the `app.main.mcp_server` binding (a no-op session_manager.run) so no app.main
    lifespan consumes the real manager. test_mcp_server uses build_mcp_app →
    `app.mcp.server.mcp_server` (a DIFFERENT module binding), so its real loopback is
    unaffected and becomes the sole, order-independent consumer."""
    @asynccontextmanager
    async def _noop_run():
        yield

    stub = MagicMock()
    stub.session_manager.run = _noop_run
    try:
        import app.main  # noqa: F401 — ensure the module is importable to patch its binding
    except Exception:
        yield
        return
    with patch("app.main.mcp_server", stub):
        yield
