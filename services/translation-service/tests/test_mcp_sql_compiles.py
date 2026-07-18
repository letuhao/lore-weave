"""Every raw SQL constant in the MCP server must COMPILE against the real schema.

The bug this exists to prevent, found by the Track D capability sweep
(`scripts/eval/tool_liveness/sweep.py`):

    translation_list_versions  →  column ct.model_source does not exist

`_VERSIONS_SQL` selected `ct.model_source` / `ct.model_ref` off `chapter_translations`.
Those columns live on `translation_jobs` — the model is a property of the JOB that produced
a version. Postgres rejects the whole statement at parse time, so the tool failed on EVERY
real chapter, always, since it was written.

Nothing caught it. This service's `test_mcp_server.py` asserts the tool's NAME and TIER;
it never runs the tool's SQL. A tool can be correctly tiered, scoped, schema-mirrored and
drift-locked and still be incapable of executing — which is exactly the gap the liveness
work exists to close.

`PREPARE` parses + plans a statement without running it: no rows read, no side effects,
and a wrong column name is a hard error. That makes it the cheapest possible gate for this
whole bug class.

Requires a reachable Postgres (`TRANSLATION_TEST_PG_DSN`), like the other pg-backed tests
here.
"""
from __future__ import annotations

import os
import re

import asyncpg
import pytest

pytestmark = pytest.mark.xdist_group("pg")

_DSN = os.environ.get(
    "TRANSLATION_TEST_PG_DSN",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_translation",
)

# `$1`-style placeholders need a declared type for PREPARE. Every SQL constant here takes
# a single uuid; widen this map if that stops being true.
_PARAM_TYPES = {"_VERSIONS_SQL": "uuid", "_COVERAGE_SQL": "uuid"}


def _sql_constants() -> dict[str, str]:
    """Every module-level `_..._SQL = \"\"\"...\"\"\"` in the MCP server."""
    from app.mcp import server as mcp_server

    return {
        name: value
        for name, value in vars(mcp_server).items()
        if name.endswith("_SQL") and isinstance(value, str) and value.strip()
    }


def test_there_are_sql_constants_to_check():
    """A gate that inspects nothing is a rubber stamp."""
    assert _sql_constants(), "no _*_SQL constants found — this gate is inert"


@pytest.mark.asyncio
async def test_every_mcp_sql_constant_compiles_against_the_live_schema():
    try:
        conn = await asyncpg.connect(_DSN, timeout=3)
    except Exception:
        pytest.skip(f"no reachable Postgres at TRANSLATION_TEST_PG_DSN ({_DSN})")
    try:
        for name, sql in sorted(_sql_constants().items()):
            n_params = len(set(re.findall(r"\$(\d+)", sql)))
            ptype = _PARAM_TYPES.get(name, "uuid")
            decl = f"({', '.join([ptype] * n_params)})" if n_params else ""
            stmt = f"PREPARE tle_{name.strip('_').lower()}{decl} AS {sql}"
            try:
                await conn.execute(stmt)
            except asyncpg.PostgresError as exc:
                pytest.fail(
                    f"{name} does not compile against the live schema: {exc}\n"
                    f"(a `column x.y does not exist` here means the tool fails on EVERY "
                    f"call — see translation_list_versions)"
                )
            finally:
                await conn.execute(f"DEALLOCATE ALL")
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_versions_sql_reads_the_model_from_the_job_not_the_translation():
    """The specific regression. `model_source`/`model_ref` are columns of
    `translation_jobs`; a hand-edited version has a NULL `job_id` and therefore no model,
    so the join must be LEFT, not INNER."""
    from app.mcp.server import _VERSIONS_SQL

    assert "tj.model_source" in _VERSIONS_SQL and "tj.model_ref" in _VERSIONS_SQL
    assert "ct.model_source" not in _VERSIONS_SQL, "these columns do not exist on ct"
    assert "LEFT JOIN translation_jobs tj" in _VERSIONS_SQL, (
        "INNER JOIN would silently drop every hand-edited version (NULL job_id)"
    )
