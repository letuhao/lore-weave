"""Track 4 — salience/rerank evaluation CLI (measure-before-flip).

Measures whether the P1 learned-salience weight and/or the P2 cross-encoder
rerank actually improve retrieval over the static baseline, on a REAL project
(the 12-chapter POC book) through the REAL Mode-2/3 builder — per the project's
"evaluation over one-off smoke" rule. The P1/P2 flags stay at their defaults
until this eval shows lift.

Run inside the knowledge-service container (needs app.* + service env):

  # 1. seed an access pattern for FOCUS entities via the REAL HTTP endpoint
  #    (exercises the router's P0 telemetry recording end-to-end):
  python -m eval.run_salience_eval seed \
      --user-id=<uuid> --project-id=<uuid> --passes=5

  # 2. measure ranking at w=0 (baseline) vs --weight (candidate), in-process:
  python -m eval.run_salience_eval measure \
      --user-id=<uuid> --project-id=<uuid> --weight=0.3

Query sets are auto-generated from the project's OWN glossary entities (top by
graph evidence) — explicit queries name an entity ("X là ai?"); the seed phase
replays the FOCUS subset so the access log learns a preference the measure
phase can detect. Metrics: mean rank + MRR of the expected entity in the
surfaced order, reported per arm; the JSON report is the flip-decision artifact.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass


# ── pure metric helpers (unit-tested in tests/unit/test_salience_eval_metrics.py) ──


def rank_of(entity_id: str, surfaced: list[str]) -> int | None:
    """1-based rank of entity_id in the surfaced order; None if absent."""
    try:
        return surfaced.index(entity_id) + 1
    except ValueError:
        return None


@dataclass
class ArmReport:
    label: str
    ranks: list[int | None]

    @property
    def mrr(self) -> float:
        if not self.ranks:
            return 0.0
        return sum((1.0 / r) for r in self.ranks if r) / len(self.ranks)

    @property
    def mean_rank(self) -> float | None:
        found = [r for r in self.ranks if r]
        return (sum(found) / len(found)) if found else None

    @property
    def hit_rate(self) -> float:
        if not self.ranks:
            return 0.0
        return sum(1 for r in self.ranks if r) / len(self.ranks)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "queries": len(self.ranks),
            "mrr": round(self.mrr, 4),
            "mean_rank": round(self.mean_rank, 2) if self.mean_rank else None,
            "hit_rate": round(self.hit_rate, 4),
        }


def build_queries(entities: list[dict], focus_n: int) -> tuple[list[dict], list[dict]]:
    """(focus, others) explicit query sets from entity rows {entity_id, name}.
    Each query: {"q": "<name> là ai? Kể chi tiết về <name>.", "expect": entity_id}.
    Focus = the first `focus_n` (seeded heavily → salience should learn them)."""
    queries = [
        {"q": f"{e['name']} là ai? Kể chi tiết về {e['name']}.", "expect": e["entity_id"]}
        for e in entities
        if e.get("name")
    ]
    return queries[:focus_n], queries[focus_n:]


# ── async phases (imports deferred — app.config needs service env) ──────────


async def _load_entities(user_id, project_id, limit: int = 12) -> list[dict]:
    """Top glossary-anchored entities for the project from Neo4j (by evidence),
    joined to their glossary entity_id (the id the context block surfaces)."""
    from app.db.neo4j import init_neo4j_driver, neo4j_session

    await init_neo4j_driver()
    async with neo4j_session() as session:
        res = await session.run(
            """
            MATCH (e:Entity {project_id: $pid})
            WHERE e.glossary_entity_id IS NOT NULL AND e.name IS NOT NULL
            RETURN e.glossary_entity_id AS entity_id, e.name AS name,
                   coalesce(e.evidence_count, 0) AS ev
            ORDER BY ev DESC, name
            LIMIT $limit
            """,
            pid=str(project_id), limit=limit,
        )
        return [dict(r) async for r in res]


async def _seed(args) -> int:
    """Replay FOCUS queries through the real HTTP /internal/context/build so the
    router's P0 recording accrues a genuine access pattern."""
    import httpx

    from app.config import settings

    entities = await _load_entities(args.user_id, args.project_id)
    if not entities:
        print("no glossary-anchored entities in the graph — run extraction first", file=sys.stderr)
        return 1
    focus, _ = build_queries(entities, args.focus)
    base = f"http://localhost:{args.port}"
    async with httpx.AsyncClient(
        timeout=60.0, headers={"X-Internal-Token": settings.internal_service_token}
    ) as client:
        total = 0
        for p in range(args.passes):
            for q in focus:
                r = await client.post(
                    f"{base}/internal/context/build",
                    json={
                        "user_id": str(args.user_id),
                        "project_id": str(args.project_id),
                        "message": q["q"],
                    },
                )
                r.raise_for_status()
                total += 1
            print(f"pass {p + 1}/{args.passes} done")
    await asyncio.sleep(1.0)  # let the fire-and-forget recorder land the last batch
    print(json.dumps({"seeded_builds": total, "focus": [q["expect"] for q in focus]}))
    return 0


async def _measure(args) -> int:
    """Run every query through the REAL builder in-process, once per arm
    (w=0 baseline vs w=args.weight), and report rank metrics per arm."""
    import asyncpg

    from app.clients.embedding_client import init_embedding_client
    from app.clients.glossary_client import GlossaryClient
    from app.config import settings
    from app.context.builder import build_context
    from app.db.pool import init_knowledge_pool
    from app.db.repositories.entity_access import EntityAccessRepo
    from app.db.repositories.projects import ProjectsRepo
    from app.db.repositories.summaries import SummariesRepo

    await init_knowledge_pool()
    from app.db.pool import get_knowledge_pool

    pool = get_knowledge_pool()
    summaries = SummariesRepo(pool)
    projects = ProjectsRepo(pool)
    glossary = GlossaryClient(
        base_url=settings.glossary_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.glossary_client_timeout_s,
    )
    embedding = init_embedding_client()
    access_repo = EntityAccessRepo(pool)

    entities = await _load_entities(args.user_id, args.project_id)
    focus, others = build_queries(entities, args.focus)
    all_queries = focus + others
    if not all_queries:
        print("no queries buildable — empty graph?", file=sys.stderr)
        return 1

    async def run_arm(label: str, weight: float) -> ArmReport:
        settings.salience_access_weight = weight  # in-process flip; restored by next arm
        ranks: list[int | None] = []
        for q in all_queries:
            built = await build_context(
                summaries, projects, glossary,
                user_id=args.user_id, project_id=args.project_id,
                message=q["q"], embedding_client=embedding,
                entity_access_repo=access_repo,
            )
            ranks.append(rank_of(q["expect"], built.surfaced_entity_ids))
        return ArmReport(label=label, ranks=ranks)

    baseline = await run_arm("baseline w=0", 0.0)
    candidate = await run_arm(f"salience w={args.weight}", args.weight)
    settings.salience_access_weight = 0.0

    report = {
        "project_id": str(args.project_id),
        "queries": len(all_queries),
        "focus_entities": [q["expect"] for q in focus],
        "arms": [baseline.to_dict(), candidate.to_dict()],
        "verdict": (
            "LIFT" if candidate.mrr > baseline.mrr
            else "TIE" if candidate.mrr == baseline.mrr
            else "REGRESSION"
        ),
    }
    print(json.dumps(report, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Track 4 salience eval (seed / measure)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    from uuid import UUID

    def common(p):
        p.add_argument("--user-id", type=UUID, required=True)
        p.add_argument("--project-id", type=UUID, required=True)
        p.add_argument("--focus", type=int, default=4, help="how many top entities form the seeded FOCUS set")

    p_seed = sub.add_parser("seed", help="replay focus queries via HTTP to accrue P0 telemetry")
    common(p_seed)
    p_seed.add_argument("--passes", type=int, default=5)
    p_seed.add_argument("--port", type=int, default=8092)

    p_meas = sub.add_parser("measure", help="rank metrics: baseline w=0 vs --weight")
    common(p_meas)
    p_meas.add_argument("--weight", type=float, default=0.3)

    args = ap.parse_args()
    if args.cmd == "seed":
        return asyncio.run(_seed(args))
    return asyncio.run(_measure(args))


if __name__ == "__main__":
    sys.exit(main())
