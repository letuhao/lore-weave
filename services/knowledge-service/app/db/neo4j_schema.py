"""K11.3 — Neo4j schema runner.

Loads the `neo4j_schema.cypher` companion file and executes each
statement against the configured Neo4j driver. Idempotent — every
statement in the .cypher file uses `IF NOT EXISTS` so re-running
this is safe and is the expected behaviour on every startup.

Called from the FastAPI lifespan startup hook RIGHT AFTER
`init_neo4j_driver()` so a missing index/constraint surfaces as a
startup failure rather than a runtime query plan surprise.

Multi-statement Cypher: the bolt protocol can only handle one
Cypher statement per `session.run(...)`. Splitting on `;` is
sufficient because the schema file deliberately avoids semicolons
inside string literals or comments — the runner's split logic is
not a SQL parser.

The `K11.4` user_id-safety wrapper is NOT used here because schema
statements are global (no user filter applies). The wrapper would
raise if asked to execute one of these. Schema runs are the one
documented exception to the "every Cypher goes through K11.4"
rule, and they live in this module ONLY so the exception surface
is small and reviewable.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

__all__ = [
    "Neo4jSchemaError",
    "load_schema_statements",
    "run_neo4j_schema",
]

# Path is module-relative so the file ships in the same directory
# as this runner. Both files are in the package source tree, no
# resource hackery needed.
_SCHEMA_PATH = Path(__file__).parent / "neo4j_schema.cypher"


class Neo4jSchemaError(RuntimeError):
    """Raised when a schema statement fails to apply. Wraps the
    underlying neo4j driver exception with the statement text so
    the lifespan log shows exactly which Cypher tripped."""


# Strip `// line comments` from a chunk before parsing. Block
# comments (`/* ... */`) are not used in our schema file but
# could be added here if needed.
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")


def load_schema_statements(path: Path | None = None) -> list[str]:
    """Read the schema file and return a list of Cypher statements
    ready to feed into `session.run(...)` one at a time.

    Pure function, no I/O against Neo4j. Unit-testable offline.

    Splitting strategy: strip line comments, then split on `;`,
    then strip whitespace, then drop empty fragments. This is
    intentionally simple — the schema file is hand-curated and
    does not put `;` inside string literals or other contexts
    where naive splitting would break.
    """
    src_path = path or _SCHEMA_PATH
    # utf-8-sig: tolerate a BOM if a Windows editor saved one in.
    # The first statement would otherwise carry a leading \ufeff
    # and Neo4j would reject it as a syntax error.
    raw = src_path.read_text(encoding="utf-8-sig")
    no_comments = _LINE_COMMENT_RE.sub("", raw)
    fragments = (s.strip() for s in no_comments.split(";"))
    return [s for s in fragments if s]


async def run_neo4j_schema(driver: AsyncDriver) -> None:
    """Apply the K11.3 schema to the given driver. Idempotent.

    Iterates the parsed statements and runs each one against a
    fresh session. A single session would also work but separate
    sessions give cleaner error reporting when one statement
    fails — the bolt error message points unambiguously at the
    Cypher we just submitted.

    Raises `Neo4jSchemaError` on the first failure with the
    offending statement embedded so the lifespan log shows
    exactly what to fix.
    """
    statements = load_schema_statements()
    logger.info(
        "K11.3: applying Neo4j schema (%d statements from %s)",
        len(statements),
        _SCHEMA_PATH.name,
    )
    for i, statement in enumerate(statements, start=1):
        async with driver.session() as session:
            try:
                await session.run(statement)
            except Exception as exc:
                logger.error(
                    "K11.3: statement %d/%d failed: %s\n--- cypher ---\n%s",
                    i,
                    len(statements),
                    exc,
                    statement,
                )
                raise Neo4jSchemaError(
                    f"schema statement {i}/{len(statements)} failed: {exc}\n"
                    f"cypher:\n{statement}",
                ) from exc
    logger.info("K11.3: Neo4j schema applied successfully")
