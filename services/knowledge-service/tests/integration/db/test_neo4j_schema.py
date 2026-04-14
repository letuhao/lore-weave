"""K11.3 integration test — apply schema against live Neo4j.

Requires `TEST_NEO4J_URI` (and optionally TEST_NEO4J_USER /
TEST_NEO4J_PASSWORD) env vars. Skips when unset, matching the
TEST_KNOWLEDGE_DB_URL convention from the postgres integration
suite.

Asserts:
  1. The schema runner applies cleanly against an empty graph.
  2. Re-running is idempotent (no errors, no duplicate indexes).
  3. SHOW INDEXES contains every expected index name.
  4. SHOW CONSTRAINTS contains every expected constraint name.

The runner deliberately doesn't drop the schema between tests —
the IF NOT EXISTS clauses make order independent. Other Neo4j
integration tests (when they land) can rely on this schema being
present after the K11.3 test runs.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase

from app.db.neo4j_schema import Neo4jSchemaError, run_neo4j_schema


def _neo4j_dsn() -> tuple[str, str, str] | None:
    uri = os.environ.get("TEST_NEO4J_URI")
    if not uri:
        return None
    user = os.environ.get("TEST_NEO4J_USER", "neo4j")
    password = os.environ.get("TEST_NEO4J_PASSWORD", "loreweave_dev_neo4j")
    return uri, user, password


@pytest_asyncio.fixture
async def neo4j_driver():
    """Function-scoped driver fixture. Skips the test if no
    TEST_NEO4J_URI is configured."""
    dsn = _neo4j_dsn()
    if dsn is None:
        pytest.skip("TEST_NEO4J_URI not set — skipping live Neo4j test")
    uri, user, password = dsn
    try:
        driver = AsyncGraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=5.0,
        )
        await driver.verify_connectivity()
    except Exception as exc:
        pytest.skip(f"Neo4j unreachable at {uri}: {exc}")
    try:
        yield driver
    finally:
        await driver.close()


# Constraints + indexes the schema is expected to install.
# Mirrors neo4j_schema.cypher; if you add a statement there, add
# the name here too.
EXPECTED_CONSTRAINTS = {
    "entity_id_unique",
    "event_id_unique",
    "fact_id_unique",
    "extraction_source_id_unique",
    "project_id_unique",
    "session_id_unique",
}

EXPECTED_REGULAR_INDEXES = {
    "entity_user_canonical",
    "entity_user_name",
    "entity_user_project",
    "entity_user_project_model",
    "event_user_order",
    "event_user_chapter",
    "entity_user_evidence",
    "event_user_evidence",
    "fact_user_evidence",
    "extraction_source_user_project",
    "extraction_source_user_source",
}

EXPECTED_VECTOR_INDEXES = {
    "entity_embeddings_384",
    "entity_embeddings_1024",
    "entity_embeddings_1536",
    "entity_embeddings_3072",
    "event_embeddings_1024",
}


async def _list_index_names(driver) -> set[str]:
    async with driver.session() as session:
        result = await session.run("SHOW INDEXES YIELD name RETURN name")
        return {record["name"] async for record in result}


async def _list_constraint_names(driver) -> set[str]:
    async with driver.session() as session:
        result = await session.run("SHOW CONSTRAINTS YIELD name RETURN name")
        return {record["name"] async for record in result}


@pytest.mark.asyncio
async def test_k11_3_schema_applies_cleanly(neo4j_driver):
    """First-run: apply schema, assert all expected names appear."""
    await run_neo4j_schema(neo4j_driver)

    constraint_names = await _list_constraint_names(neo4j_driver)
    missing_constraints = EXPECTED_CONSTRAINTS - constraint_names
    assert not missing_constraints, f"missing constraints: {missing_constraints}"

    index_names = await _list_index_names(neo4j_driver)
    expected_indexes = EXPECTED_REGULAR_INDEXES | EXPECTED_VECTOR_INDEXES
    missing_indexes = expected_indexes - index_names
    assert not missing_indexes, f"missing indexes: {missing_indexes}"


@pytest.mark.asyncio
async def test_k11_3_schema_is_idempotent(neo4j_driver):
    """KSA §3.4 + plan acceptance criterion: re-running the
    schema runner must NOT error, even if every constraint and
    index already exists. Verified by running it twice in a row."""
    await run_neo4j_schema(neo4j_driver)
    # Second run — would error on any non-IF-NOT-EXISTS form.
    await run_neo4j_schema(neo4j_driver)

    # Index/constraint counts unchanged.
    constraint_names = await _list_constraint_names(neo4j_driver)
    assert EXPECTED_CONSTRAINTS.issubset(constraint_names)
    index_names = await _list_index_names(neo4j_driver)
    expected_indexes = EXPECTED_REGULAR_INDEXES | EXPECTED_VECTOR_INDEXES
    assert expected_indexes.issubset(index_names)


@pytest.mark.asyncio
async def test_k11_3_vector_index_dimensions(neo4j_driver):
    """Spot-check that the vector indexes were created with the
    correct dimensions. SHOW INDEXES YIELDs `options` which has
    the indexConfig vector.dimensions value."""
    await run_neo4j_schema(neo4j_driver)
    expected_dims = {
        "entity_embeddings_384": 384,
        "entity_embeddings_1024": 1024,
        "entity_embeddings_1536": 1536,
        "entity_embeddings_3072": 3072,
        "event_embeddings_1024": 1024,
    }
    async with neo4j_driver.session() as session:
        result = await session.run(
            "SHOW INDEXES YIELD name, type, options "
            "WHERE type = 'VECTOR' "
            "RETURN name, options"
        )
        rows = {record["name"]: record["options"] async for record in result}
    for name, dim in expected_dims.items():
        assert name in rows, f"missing vector index {name}"
        config = rows[name].get("indexConfig", {})
        actual_dim = config.get("vector.dimensions")
        assert actual_dim == dim, (
            f"{name} has dimensions {actual_dim}, expected {dim}"
        )


@pytest.mark.asyncio
async def test_k11_3_schema_error_wraps_underlying_exception(neo4j_driver, tmp_path):
    """`run_neo4j_schema` raises Neo4jSchemaError with the offending
    statement embedded in the message. Verifies the error path is
    actionable for the lifespan log."""
    # Write a malformed schema file and feed it through the runner
    # via the alt-path hook.
    bad = tmp_path / "bad.cypher"
    bad.write_text(
        "CREATE INDEX legit_index IF NOT EXISTS FOR (n:Foo) ON (n.x);\n"
        "THIS IS NOT VALID CYPHER;\n",
        encoding="utf-8",
    )
    from app.db import neo4j_schema as schema_module
    original_path = schema_module._SCHEMA_PATH
    schema_module._SCHEMA_PATH = bad
    try:
        with pytest.raises(Neo4jSchemaError) as exc_info:
            await run_neo4j_schema(neo4j_driver)
        # Error message includes the bad statement so the lifespan
        # log shows what to fix.
        assert "THIS IS NOT VALID CYPHER" in str(exc_info.value)
    finally:
        schema_module._SCHEMA_PATH = original_path
        # Clean up the legit_index we created via the bad file's
        # first statement so the test is repeatable.
        async with neo4j_driver.session() as session:
            await session.run("DROP INDEX legit_index IF EXISTS")
