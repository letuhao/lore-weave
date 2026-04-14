"""K11.2 — Neo4j async driver wiring.

Lifecycle:

  1. `init_neo4j_driver()` — called from the FastAPI lifespan startup
     hook. Reads `settings.neo4j_uri`. If empty: silently no-op (Track
     1 dev path, Neo4j not configured). If set: instantiates the async
     driver, runs a connectivity ping, and stashes the driver in a
     module-level singleton. Raises `Neo4jStartupError` on any
     unreachable / auth / timeout failure (per K11.2 spec: "Startup
     fails if Neo4j unreachable").

  2. `get_neo4j_driver()` — returns the singleton, or raises
     `Neo4jNotConfiguredError` if the lifespan never initialised one.
     Used by repo code (K11.5+) and FastAPI dependency injection.

  3. `close_neo4j_driver()` — called from the FastAPI lifespan
     shutdown hook. Idempotent on no-init.

Multi-tenant safety: this module deliberately exports a thin driver
handle, NOT raw sessions. K11.4's `run_read` / `run_write` helpers
take the session and enforce the `$user_id` parameter rule before
the cypher hits the wire. Repo code MUST go through K11.4 — there
is no `session.run(...)` in this module's public surface.

Test note: K11.2 ships with no integration tests of its own — the
K11.3 schema runner test exercises the connect-init-ping-close
lifecycle via the live Neo4j instance once the schema is in place.
This is the same pattern as the postgres pool module which has no
direct unit tests; the K1 migrations test indirectly verifies it.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "Neo4jNotConfiguredError",
    "Neo4jStartupError",
    "close_neo4j_driver",
    "get_neo4j_driver",
    "init_neo4j_driver",
    "neo4j_session",
]


class Neo4jStartupError(RuntimeError):
    """Raised when Neo4j is configured (NEO4J_URI is set) but the
    driver cannot reach the server during the startup ping. The
    FastAPI lifespan should propagate this so uvicorn fails to bind
    the port — Track 2 cannot run with a broken graph backend."""


class Neo4jNotConfiguredError(RuntimeError):
    """Raised when repo code asks for the Neo4j driver but it was
    never initialised (NEO4J_URI is empty). This is the Track 1
    code path — the caller should treat the absence as "Track 2
    feature disabled" and degrade gracefully or skip."""


# Module-level singleton. None means either "not yet initialised"
# OR "Track 1 mode, Neo4j intentionally absent". The two cases are
# distinguished by `_init_attempted` so a stray `get_neo4j_driver`
# call before the lifespan hook ran can be distinguished from a
# legitimate Track 1 skip.
_driver: AsyncDriver | None = None
_init_attempted: bool = False


async def init_neo4j_driver() -> None:
    """Initialise the Neo4j async driver from settings. No-op if
    `settings.neo4j_uri` is empty (Track 1 dev). Raises
    `Neo4jStartupError` on any connection failure when configured.

    Called once from the FastAPI lifespan startup hook. Subsequent
    calls are idempotent — re-running with the same configuration
    keeps the existing driver, re-running with a different URI is
    a programmer error (we don't try to be clever about it).
    """
    global _driver, _init_attempted
    _init_attempted = True

    if not settings.neo4j_uri:
        logger.info("K11.2: NEO4J_URI not set — skipping driver init (Track 1 mode)")
        return

    if _driver is not None:
        logger.debug("K11.2: driver already initialised, skipping re-init")
        return

    logger.info(
        "K11.2: initialising Neo4j driver uri=%s user=%s timeout=%.1fs",
        settings.neo4j_uri,
        settings.neo4j_user,
        settings.neo4j_connection_timeout_s,
    )
    try:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=settings.neo4j_connection_timeout_s,
            connection_acquisition_timeout=settings.neo4j_connection_timeout_s,
        )
        # Connectivity ping — the spec is "Startup fails if Neo4j
        # unreachable", so we pay the round-trip now rather than
        # discovering at first query time. `verify_connectivity` is
        # the official driver hook for this exact purpose.
        await driver.verify_connectivity()
    except Exception as exc:
        # Don't leak partial driver state on failure — close anything
        # we opened, then re-raise as Neo4jStartupError so the lifespan
        # hook gets a typed error to log against.
        logger.error("K11.2: Neo4j connectivity check failed: %s", exc)
        try:
            if "driver" in locals():
                await driver.close()
        except Exception:  # pragma: no cover — best-effort cleanup
            pass
        raise Neo4jStartupError(
            f"Neo4j unreachable at {settings.neo4j_uri}: {exc}"
        ) from exc

    _driver = driver
    logger.info("K11.2: Neo4j driver initialised and connectivity verified")


def get_neo4j_driver() -> AsyncDriver:
    """Return the initialised driver. Raises if the lifespan never
    set one up (either because `neo4j_uri` was empty or the hook
    didn't run). Repo code should treat the typed exception as
    "Track 2 feature unavailable" rather than crashing."""
    if _driver is None:
        if not _init_attempted:
            raise Neo4jNotConfiguredError(
                "Neo4j driver not initialised — lifespan startup hook did not run",
            )
        raise Neo4jNotConfiguredError(
            "Neo4j driver not configured (NEO4J_URI is empty) — Track 1 mode",
        )
    return _driver


def neo4j_session(**kwargs: Any) -> AsyncSession:
    """Open a new async session against the configured driver.
    Thin wrapper around `driver.session(...)` — exists so call
    sites can write `async with neo4j_session() as s:` without
    importing both the driver and the get-driver helper.

    Repo code must wrap the session's `run(...)` in K11.4's
    `run_read` / `run_write` helpers, NOT call it directly.
    """
    return get_neo4j_driver().session(**kwargs)


async def close_neo4j_driver() -> None:
    """Close the singleton driver. Idempotent — safe to call from
    the FastAPI lifespan shutdown hook even when init was skipped
    (Track 1 mode)."""
    global _driver, _init_attempted
    if _driver is not None:
        logger.info("K11.2: closing Neo4j driver")
        await _driver.close()
        _driver = None
    _init_attempted = False
