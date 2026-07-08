"""P3-EVAL E4b — semantic brute-force (flat-kNN) baseline.

Measures how much the Neo4j ANN vector index loses versus an EXACT
cosine scan over every chapter passage in the project. For each query:

  - index_topk : `find_passages_by_vector(limit=k)` — the same call the
    raw-search semantic leg makes (Neo4j vector index ordering).
  - flat_topk  : fetch ALL chapter passages WITH vectors, compute exact
    cosine in Python, rank → the ground-truth top-k.
  - ann_recall@k = |index_topk ∩ flat_topk| / k   (passage-id identity)

Runs INSIDE the knowledge-service container (needs neo4j + embedding
client). Invoked by the host runner:

    echo '["query one","query two"]' | docker exec -i infra-knowledge-service-1 \
        python -m app.benchmark.flat_knn_rawsearch \
        --project-id … --user-id … --embedding-model … --embedding-dim 1024 --k 10

stdin = JSON list of query strings. Prints a JSON summary to stdout.
Lives under app/benchmark/ (ships in the image; eval/ does not).
"""

from __future__ import annotations

from typing import Any

from loreweave_vecmath import cosine_similarity as _cosine

# Pull "effectively all" passages for a 40-chapter eval corpus. The vector
# index oversamples (limit × oversample_factor) before tenant post-filter,
# so a high limit + factor returns the full candidate set to rank exactly.
_FETCH_ALL_LIMIT = 5000


async def _run(args: Any) -> int:
    import json as _json
    import logging as _logging
    import sys as _sys
    from uuid import UUID as _UUID

    from app.clients.embedding_client import init_embedding_client
    from app.db.neo4j import init_neo4j_driver, neo4j_session
    from app.db.neo4j_repos.passages import find_passages_by_vector

    _logging.basicConfig(level=_logging.WARNING)

    raw = _sys.stdin.read().strip()
    queries: list[str] = _json.loads(raw) if raw else []
    if not queries:
        print(_json.dumps({"error": "no queries on stdin"}))
        return 1

    user_id = args.user_id
    project_id = args.project_id
    k = args.k

    await init_neo4j_driver()
    embed = init_embedding_client()

    per_query: list[dict] = []
    async with neo4j_session() as session:
        for q in queries:
            res = await embed.embed(
                user_id=_UUID(user_id), model_source=args.model_source,
                model_ref=args.embedding_model, texts=[q],
            )
            qvec = res.embeddings[0]

            # Ground truth: exact cosine over all passages.
            all_hits = await find_passages_by_vector(
                session, user_id=user_id, project_id=project_id,
                query_vector=qvec, dim=args.embedding_dim,
                embedding_model=args.embedding_model, source_type="chapter",
                limit=_FETCH_ALL_LIMIT, oversample_factor=1, include_vectors=True,
            )
            scored = sorted(
                ((_cosine(qvec, h.vector or []), h.passage.id) for h in all_hits),
                key=lambda t: t[0], reverse=True,
            )
            flat_topk = {pid for _, pid in scored[:k]}

            # Index ordering: the same call the semantic leg uses.
            idx_hits = await find_passages_by_vector(
                session, user_id=user_id, project_id=project_id,
                query_vector=qvec, dim=args.embedding_dim,
                embedding_model=args.embedding_model, source_type="chapter",
                limit=k, include_vectors=False,
            )
            index_topk = {h.passage.id for h in idx_hits}

            denom = min(k, len(flat_topk)) or 1
            ann_recall = len(index_topk & flat_topk) / denom
            per_query.append({
                "q": q, "candidates": len(all_hits),
                "ann_recall_at_k": round(ann_recall, 4),
            })

    recalls = [r["ann_recall_at_k"] for r in per_query]
    mean_recall = round(sum(recalls) / len(recalls), 4) if recalls else 0.0
    print(_json.dumps({
        "k": k, "queries": len(queries),
        "mean_ann_recall_at_k": mean_recall,
        "per_query": per_query,
    }, ensure_ascii=False))
    return 0


def _build_parser() -> Any:
    import argparse
    p = argparse.ArgumentParser(prog="flat_knn_rawsearch")
    p.add_argument("--project-id", required=True)
    p.add_argument("--user-id", required=True)
    p.add_argument("--embedding-model", required=True)
    p.add_argument("--embedding-dim", required=True, type=int)
    p.add_argument("--model-source", default="user_model",
                   choices=["user_model", "platform_model"])
    p.add_argument("--k", type=int, default=10)
    return p


def _main() -> int:
    import asyncio
    return asyncio.run(_run(_build_parser().parse_args()))


if __name__ == "__main__":
    import sys
    sys.exit(_main())
