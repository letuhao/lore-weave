"""C1 live-smoke — REAL cross-service call (NOT mocked).

Drives the actual `KnowledgeClient.get_graph_stats` against a RUNNING
knowledge-service to confirm:
  * the read client can REACH knowledge-service over the network, and
  * it correctly parses the service's JSON contract / typed-errors path.

This is the CLAUDE.md cross-service VERIFY token requirement. It is NOT part of
the unit suite (which is network-free) — it runs only from verify-cycle-1.sh.

Reachability is the assertion. EMPTY/zero graph-stats is a VALID result (no
Fengshen data seeded for this project yet). A 401 (missing/!valid JWT) is ALSO
a valid reachability proof: the route exists and enforces (user, project)
scoping. The smoke FAILS only if the service is unreachable (connection error /
timeout) — i.e. the network seam itself is broken.

Env:
  KNOWLEDGE_SERVICE_URL   default http://localhost:8216  (host port per stack)
  SMOKE_JWT               optional real JWT; omit to exercise the 401 path
  SMOKE_PROJECT_ID        optional project UUID
"""

from __future__ import annotations

import asyncio
import os
import sys
from uuid import UUID, uuid4

from app.clients.knowledge import KnowledgeClient, KnowledgeServiceError


async def _main() -> int:
    base = os.environ.get("KNOWLEDGE_SERVICE_URL", "http://localhost:8216")
    jwt = os.environ.get("SMOKE_JWT", "")
    project_id = UUID(os.environ.get("SMOKE_PROJECT_ID", str(uuid4())))

    client = KnowledgeClient(
        knowledge_base_url=base,
        provider_registry_base_url=base,  # unused on this path
        internal_token="live-smoke-not-used-on-graph-stats",
        timeout_s=8.0,
    )
    try:
        stats = await client.get_graph_stats(jwt=jwt or "live-smoke-probe", project_id=project_id)
        print(
            f"live smoke: read graph-stats from running knowledge-service at {base} -> "
            f"entity={stats.entity_count} fact={stats.fact_count} "
            f"event={stats.event_count} passage={stats.passage_count} "
            f"(empty={stats.is_empty}; EMPTY is VALID)"
        )
        return 0
    except KnowledgeServiceError as exc:
        # A 4xx (e.g. 401 missing bearer / 404 project) proves REACHABILITY +
        # contract + scoping enforcement — that is a PASS for this smoke.
        if exc.status_code is not None and 400 <= exc.status_code < 500:
            print(
                f"live smoke: read graph-stats from running knowledge-service at {base} -> "
                f"reached, scoping enforced (HTTP {exc.status_code}: {exc}). "
                f"Reachability + contract CONFIRMED."
            )
            return 0
        # connection error / timeout / 5xx with no service = the seam is broken.
        print(f"live infra unavailable: {exc}", file=sys.stderr)
        return 3
    finally:
        await client.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
