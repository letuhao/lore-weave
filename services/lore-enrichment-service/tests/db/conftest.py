"""DB integration-test fixtures (RAID C2).

db-safety-gate: guarded-dir — the `pool` fixture here refuses a non-throwaway DSN
via _guard_throwaway() BEFORE it runs `run_down_migrations` (which DROPs every C2
table), and every DB test under this directory takes its connection from that one
guarded pool. So this tree can never drop a real service database. (See CLAUDE.md ›
"Destructive DB ops in tests" + scripts/db-safety-gate.py.)

Connects to a real Postgres using TEST_LORE_ENRICHMENT_DB_URL — the dedicated test
var ONLY. If the DB is unreachable/unset the test SKIPs, so `pytest` stays runnable
on a dev host without Docker, while verify-cycle-2.sh provides the real compose
Postgres so the H0 round-trip actually exercises constraints + triggers (no
mock-only false-green).

⚠️ HISTORY (K29, 2026-07-24) — this file previously fell back to the PRODUCTION
`LORE_ENRICHMENT_DB_URL` and had no throwaway guard, even though its own docstring
claimed to mirror knowledge-service (which has both). The root conftest's
`os.environ.setdefault` placeholder does NOT protect: setdefault is a no-op when the
var is already exported, which it is in any compose/dev shell. Running `pytest
tests/db` there pointed the fixture at the real `loreweave_lore_enrichment` and
DROPped all 12 tables — reproduced against a decoy DB: 39 tests PASSED green while
the seeded row was destroyed. Exactly the data-loss class CLAUDE.md documents.
Do not reintroduce a production-DSN fallback here.
"""

from __future__ import annotations

import os
import re

import asyncpg
import pytest
import pytest_asyncio

from app.db.migrate import run_down_migrations, run_migrations

# A disposable test DB name carries one of these markers; a real service DB
# (loreweave_lore_enrichment) carries none. Mirrors knowledge-service +
# campaign-service tests/integration conftest.
_THROWAWAY = re.compile(r"(?i)(test|smoke|audit|scratch|throwaway|tmp|sandbox|ephemeral)")


def pytest_collection_modifyitems(items):
    """K27 (2026-07-24) — serialize every test in THIS directory onto one xdist
    worker. Each `pool` fixture down-migrates + up-migrates the SAME shared throwaway
    Postgres, so two workers running these concurrently interleave DROP/CREATE DDL
    and corrupt each other (35 errors under `-n auto --dist loadgroup` before this).
    Per CLAUDE.md › Test Parallelization, a DB-touching test carries
    `xdist_group("pg")`; stamping it here covers all 8 files + any future one in one
    place. Scoped by fspath so it only marks tests under this db/ tree."""
    here = os.path.dirname(os.path.abspath(__file__))
    for item in items:
        if str(item.fspath).startswith(here):
            item.add_marker(pytest.mark.xdist_group("pg"))


def _dsn() -> str | None:
    # ONLY the dedicated test var — never fall back to the production
    # LORE_ENRICHMENT_DB_URL, which in any dev shell (and in-container) points at
    # the real loreweave_lore_enrichment that run_down_migrations would DROP.
    return os.environ.get("TEST_LORE_ENRICHMENT_DB_URL")


def _guard_throwaway(dsn: str) -> None:
    db = dsn.rsplit("/", 1)[-1].split("?", 1)[0]
    if not _THROWAWAY.search(db):
        raise RuntimeError(
            f"REFUSING: TEST_LORE_ENRICHMENT_DB_URL database {db!r} is not a throwaway "
            "DB (the name must contain test/smoke/audit/…). This fixture DROPs every "
            "table — point it at a disposable DB, never the real loreweave_lore_enrichment."
        )


@pytest_asyncio.fixture
async def pool():
    """Function-scoped pool against a real Postgres. Skips when no reachable
    DSN. Starts each test from a clean schema: down-migrate then up-migrate so
    the round-trip itself is exercised on every run."""
    dsn = _dsn()
    # The root conftest sets a throwaway localhost DSN for import-time fail-fast;
    # treat that placeholder as "no real DB" so unit-only runs skip cleanly.
    if not dsn or "test:test@localhost" in dsn:
        pytest.skip("no real TEST_LORE_ENRICHMENT_DB_URL set")
    _guard_throwaway(dsn)  # refuse a real DB BEFORE any destructive statement
    try:
        p = await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=5)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"DB unreachable: {exc}")
    # Clean slate, then apply — proves down→up works as a fixture side effect.
    await run_down_migrations(p)
    await run_migrations(p)
    try:
        yield p
    finally:
        await p.close()
