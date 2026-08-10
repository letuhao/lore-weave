"""Recall + latency across the candidate vector backends (plan T24).

The plan asked for "Neo4j HNSW vs pgvector vs StreamingDiskANN vs halfvec, same corpus".
**Two of those four cannot be built as written**, which was measured before anything was
designed around it:

    SELECT am.amname, opc.opcname FROM pg_opclass … WHERE amname IN ('diskann','hnsw')

  diskann : vector_cosine_ops, vector_ip_ops, vector_l2_ops        ← `vector` ONLY
  hnsw    : vector_*, halfvec_*, sparsevec_*, bit_*

On pgvectorscale 0.9.0 **StreamingDiskANN cannot index `halfvec` at all** — there is no
`halfvec_cosine_ops` for it. So "diskann vs halfvec" is not a comparison anyone can run,
and had it been run naively (halfvec on HNSW, `vector` on diskann) the resulting number
would have blamed fp16 for a difference between two index ALGORITHMS.

So the cells are factored to isolate one variable each:

    exact          vector   seq scan   ground truth, from the database itself
    diskann        vector   diskann    the shipping choice (T22/T23)
    hnsw           vector   hnsw       ← vs diskann: the INDEX ALGORITHM, precision fixed
    halfvec_hnsw   halfvec  hnsw       ← vs hnsw:    the STORAGE PRECISION, index fixed
    neo4j          —        Neo4j HNSW the incumbent (only with --source neo4j)

`halfvec_hnsw` vs `hnsw` is the only clean fp16 measurement available, and it is a better
experiment than the one the plan named. Note the dim reach differs and that is the reason
halfvec was on the list at all: pgvector's HNSW caps `vector` at 2000 dims but `halfvec` at
4000, so at 2560/3072 the `hnsw` cell cannot exist and halfvec's partner is `exact`.

── GROUND TRUTH IS COMPUTED OUTSIDE THE DATABASE ────────────────────────────────────────
Recall is measured against exact cosine in numpy, not against the `exact` cell. A backend
graded by another query on the same server shares every bug that server has — a wrong
distance operator would score 1.0 against itself. The `exact` cell is still run, and it is
worth exactly one thing: its own recall must be 1.0, which is the harness's positive
control. If it is not, the harness is broken and every other number on the page is void.

── WRITES ───────────────────────────────────────────────────────────────────────────────
This creates and drops tables, so it refuses a DSN that does not name a throwaway database.
Neo4j is read-only.

    python -m app.benchmark.vector_backend_bench \\
        --dsn postgresql://…@localhost:7995/loreweave_vectors_test \\
        --source synthetic --rows 2000,8000,32000 --dim 1024 --k 10 --queries 25

db-safety-gate: file-ok -- refuses a DSN whose database name is not marked throwaway
(_guard_throwaway below) BEFORE any DDL, and never connects to a service database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import statistics
import sys
import time
from typing import Any

import asyncpg
import numpy as np

logger = logging.getLogger(__name__)

# Mirrors tests/integration/db/conftest.py. A real service DB carries none of these.
_THROWAWAY = re.compile(r"(?i)(test|smoke|audit|scratch|throwaway|tmp|sandbox|ephemeral)")

# pgvector's documented HNSW ceilings. Not a guess: `vector` refuses >2000 with
# "column cannot have more than 2000 dimensions for hnsw index" (measured in T21).
_HNSW_MAX_VECTOR = 2000
_HNSW_MAX_HALFVEC = 4000


def _guard_throwaway(dsn: str) -> None:
    db = dsn.rsplit("/", 1)[-1].split("?", 1)[0]
    if not _THROWAWAY.search(db):
        raise SystemExit(
            f"REFUSING: database {db!r} is not a throwaway (the name must contain "
            "test/smoke/audit/scratch/tmp/sandbox/ephemeral). This benchmark CREATEs and "
            "DROPs tables — point it at a disposable database."
        )


def _lit(vec) -> str:
    """pgvector text input. `%.6g` rather than `repr`: full float64 repr triples the bytes
    on the wire for digits no embedding model produces."""
    return "[" + ",".join(f"{float(x):.6g}" for x in vec) + "]"


# ── cells ────────────────────────────────────────────────────────────────────


class Cell:
    """One (storage type, index) pair, with its own table so nothing is shared."""

    def __init__(self, name: str, coltype: str, index: str | None, opclass: str | None) -> None:
        self.name, self.coltype, self.index, self.opclass = name, coltype, index, opclass
        self.table = f"bench_{name}"

    def unsupported_reason(self, dim: int) -> str | None:
        if self.index == "hnsw" and self.coltype == "vector" and dim > _HNSW_MAX_VECTOR:
            return f"pgvector HNSW caps `vector` at {_HNSW_MAX_VECTOR} dims"
        if self.index == "hnsw" and self.coltype == "halfvec" and dim > _HNSW_MAX_HALFVEC:
            return f"pgvector HNSW caps `halfvec` at {_HNSW_MAX_HALFVEC} dims"
        return None


CELLS = [
    Cell("exact", "vector", None, None),
    # The clean fp16 measurement, and the only one that is not confounded. Comparing
    # `halfvec_hnsw` against `hnsw` still mixes storage precision with the index's own
    # randomness — two HNSW graphs built over the same points are not the same graph. With
    # no index on either side, the ONLY difference between this cell and `exact` is that
    # the vectors were rounded to 16 bits, so any recall it loses is fp16 and nothing else.
    Cell("halfvec_exact", "halfvec", None, None),
    Cell("diskann", "vector", "diskann", "vector_cosine_ops"),
    Cell("hnsw", "vector", "hnsw", "vector_cosine_ops"),
    Cell("halfvec_hnsw", "halfvec", "hnsw", "halfvec_cosine_ops"),
]


async def _load_cell(conn: asyncpg.Connection, cell: Cell, corpus, dim: int) -> float:
    """Create, fill, index, ANALYZE. Returns index build seconds (0.0 for `exact`)."""
    await conn.execute(f"DROP TABLE IF EXISTS {cell.table}")
    await conn.execute(
        f"CREATE TABLE {cell.table} (id integer PRIMARY KEY, emb {cell.coltype}({dim}))"
    )
    batch, rows = 500, []
    for i, vec in enumerate(corpus):
        rows.append((i, _lit(vec)))
        if len(rows) >= batch:
            await conn.executemany(
                f"INSERT INTO {cell.table} (id, emb) VALUES ($1, $2::{cell.coltype})", rows
            )
            rows = []
    if rows:
        await conn.executemany(
            f"INSERT INTO {cell.table} (id, emb) VALUES ($1, $2::{cell.coltype})", rows
        )

    build = 0.0
    if cell.index:
        started = time.perf_counter()
        await conn.execute(
            f"CREATE INDEX {cell.table}_idx ON {cell.table} "
            f"USING {cell.index} (emb {cell.opclass})"
        )
        build = time.perf_counter() - started
    await conn.execute(f"ANALYZE {cell.table}")
    return build


async def _query_cell(
    conn: asyncpg.Connection, cell: Cell, queries, k: int, truth: list[set[int]],
    knobs: dict[str, int] | None = None,
) -> dict:
    recalls, latencies = [], []
    for qvec, want in zip(queries, truth):
        started = time.perf_counter()
        # The search-effort knobs are per-transaction, so they are set INSIDE the timed
        # region — a caller pays for them too, and quoting a latency that excluded them
        # would make a recall/latency trade look free.
        async with conn.transaction():
            for guc, value in (knobs or {}).items():
                await conn.execute(f"SET LOCAL {guc} = {int(value)}")
            rows = await conn.fetch(
                f"SELECT id FROM {cell.table} ORDER BY emb <=> $1::{cell.coltype} LIMIT {k}",
                _lit(qvec),
            )
        latencies.append((time.perf_counter() - started) * 1000)
        got = {r["id"] for r in rows}
        recalls.append(len(got & want) / len(want) if want else 0.0)
    return {
        "recall_at_k": round(statistics.fmean(recalls), 4),
        "recall_min": round(min(recalls), 4),
        "p50_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2),
    }


# ── corpora ──────────────────────────────────────────────────────────────────


def _random(rows: int, dim: int, seed: int):
    """Unit-norm Gaussian vectors — the ADVERSARIAL corpus, and it must be read as one.

    In high dimensions random unit vectors have cosine similarities packed tightly around
    zero (concentration of measure), so a "top-10" is a set of near-ties separated by
    noise. Every ANN index scores badly on it, and the score says almost nothing about the
    index: there is no neighbourhood structure for a graph index to exploit, because there
    are no neighbourhoods. Useful as a floor, worthless as a verdict.
    """
    rng = np.random.default_rng(seed)
    m = rng.standard_normal((rows, dim)).astype(np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def _clustered(rows: int, dim: int, seed: int, clusters: int = 64, spread: float = 0.35):
    """The REALISTIC corpus: a mixture of Gaussians on the sphere.

    Text embeddings are not uniform on the sphere — they sit in a comparatively narrow cone
    with strong topical clustering, which is exactly the structure a graph index exploits.
    Benchmarking only on `random` would report a floor as if it were the expected result,
    and would have condemned whichever backend happens to degrade most gracefully into
    noise. Both are run, and both are published.
    """
    rng = np.random.default_rng(seed)
    centres = rng.standard_normal((clusters, dim)).astype(np.float32)
    centres /= np.linalg.norm(centres, axis=1, keepdims=True)
    pick = rng.integers(0, clusters, size=rows)
    m = centres[pick] + spread * rng.standard_normal((rows, dim)).astype(np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


async def _from_neo4j(project_id: str, user_id: str, dim: int, limit: int):
    """Real passage vectors, READ-ONLY. The dev graph holds real books; this only reads."""
    from app.db.neo4j import init_neo4j_driver, neo4j_session
    from app.db.neo4j_repos.passages import find_passages_by_vector

    await init_neo4j_driver()
    probe = [0.0] * dim
    probe[0] = 1.0
    async with neo4j_session() as session:
        hits = await find_passages_by_vector(
            session, user_id=user_id, project_id=project_id, query_vector=probe, dim=dim,
            embedding_model=None, source_type="chapter", limit=limit,
            oversample_factor=1, include_vectors=True,
        )
    vecs = [h.vector for h in hits if h.vector]
    if not vecs:
        raise SystemExit(f"no passages with {dim}-dim vectors for project {project_id}")
    m = np.asarray(vecs, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def _make_queries(corpus, n: int, seed: int, jitter: float = 0.25):
    """Queries drawn from the CORPUS distribution — a corpus point plus noise.

    The first version of this harness drew uniform random query vectors against a clustered
    corpus, and every backend scored 0.2–0.7 recall@10. That was the harness, not the
    backends: a uniform random query in 1024 dimensions is near-orthogonal to the entire
    corpus, so its "true top-10" is ten near-ties separated by float noise, and no index can
    reproduce an ordering that is itself arbitrary. The numbers looked like a devastating
    verdict on pgvector and were measuring nothing.

    A real query is a sentence that lands near the passages it is about — "find me the
    chapter where X happens" embeds into X's neighbourhood. Perturbing a corpus point
    reproduces that: a genuine nearest neighbour exists, with a real margin, and recall
    becomes a question with an answer.
    """
    rng = np.random.default_rng(seed + 1)
    picks = rng.choice(len(corpus), size=min(n, len(corpus)), replace=False)
    q = corpus[picks] + jitter * rng.standard_normal(
        (len(picks), corpus.shape[1])
    ).astype(np.float32)
    return q / np.linalg.norm(q, axis=1, keepdims=True)


# ── run ──────────────────────────────────────────────────────────────────────


async def _run_one(pool, corpus, dim: int, k: int, n_queries: int, seed: int,
                   knobs: dict[str, dict[str, int]]) -> dict:
    queries = _make_queries(corpus, n_queries, seed)

    # Ground truth OUTSIDE the database — see the module docstring. Corpus is unit-norm, so
    # the dot product IS cosine similarity.
    sims = queries @ corpus.T
    truth = [set(np.argsort(-row)[:k].tolist()) for row in sims]

    results: dict[str, Any] = {}
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE")
        for cell in CELLS:
            reason = cell.unsupported_reason(dim)
            if reason:
                results[cell.name] = {"skipped": reason}
                print(f"  {cell.name:<14} SKIPPED — {reason}", file=sys.stderr)
                continue
            build = await _load_cell(conn, cell, corpus, dim)
            measured = await _query_cell(conn, cell, queries, k, truth, knobs.get(cell.index))
            measured["knobs"] = knobs.get(cell.index) or {}
            measured["index_build_s"] = round(build, 2)
            measured["table_bytes"] = await conn.fetchval(
                f"SELECT pg_total_relation_size('{cell.table}')"
            )
            results[cell.name] = measured
            print(
                f"  {cell.name:<14} recall@{k}={measured['recall_at_k']:.4f} "
                f"(min {measured['recall_min']:.4f})  p50={measured['p50_ms']}ms  "
                f"build={measured['index_build_s']}s  size={measured['table_bytes'] // 1024}kB",
                file=sys.stderr,
            )
            await conn.execute(f"DROP TABLE IF EXISTS {cell.table}")
    return results


async def _main(args) -> int:
    logging.basicConfig(level=logging.WARNING)
    _guard_throwaway(args.dsn)
    pool = await asyncpg.create_pool(args.dsn, min_size=1, max_size=2, command_timeout=600)
    # Both index families get an explicit effort setting, reported alongside every number.
    # Their DEFAULTS are not comparable (diskann searches a list of 100, HNSW an ef of 40),
    # so a table that omitted them would read as "algorithm A beats algorithm B" when it
    # might only say "A was allowed to work harder".
    knobs = {
        "diskann": {"diskann.query_search_list_size": args.diskann_search_list,
                    "diskann.query_rescore": args.diskann_rescore},
        "hnsw": {"hnsw.ef_search": args.hnsw_ef_search},
    }
    out: dict[str, Any] = {
        "dim": args.dim, "k": args.k, "queries": args.queries,
        "corpus": args.corpus if args.source == "synthetic" else "neo4j-real",
        "knobs": knobs, "runs": [],
    }
    try:
        for rows in [int(r) for r in args.rows.split(",")]:
            if args.source == "synthetic":
                corpus = (_clustered if args.corpus == "clustered" else _random)(
                    rows, args.dim, args.seed
                )
            else:
                corpus = await _from_neo4j(args.project_id, args.user_id, args.dim, rows)
                rows = len(corpus)
            print(f"\nrows={rows} dim={args.dim} k={args.k} corpus={out['corpus']}",
                  file=sys.stderr)
            out["runs"].append({
                "rows": rows,
                "cells": await _run_one(pool, corpus, args.dim, args.k, args.queries,
                                        args.seed, knobs),
            })
    finally:
        await pool.close()

    # The positive control. A harness whose EXACT cell does not score 1.0 is measuring
    # something other than recall, and every other number it printed is void — so this is
    # reported as a verdict, not left for a reader to notice.
    broken = [r["rows"] for r in out["runs"]
              if r["cells"].get("exact", {}).get("recall_at_k", 0) < 1.0]
    out["control_ok"] = not broken
    if broken:
        print(f"\nCONTROL FAILED: exact recall < 1.0 at rows={broken} — results are void",
              file=sys.stderr)
    print(json.dumps(out, indent=2))
    return 1 if broken else 0


def _build_parser():
    p = argparse.ArgumentParser(prog="vector_backend_bench")
    p.add_argument("--dsn", required=True, help="throwaway Postgres with pgvector+vectorscale")
    p.add_argument("--source", default="synthetic", choices=["synthetic", "neo4j"])
    p.add_argument("--corpus", default="clustered", choices=["clustered", "random"],
                   help="clustered = realistic embedding structure; random = adversarial floor")
    p.add_argument("--diskann-search-list", type=int, default=100, help="server default 100")
    p.add_argument("--diskann-rescore", type=int, default=50, help="server default 50")
    p.add_argument("--hnsw-ef-search", type=int, default=40, help="server default 40")
    p.add_argument("--rows", default="5000", help="comma-separated corpus sizes to sweep")
    p.add_argument("--dim", type=int, default=1024)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--queries", type=int, default=25)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--project-id")
    p.add_argument("--user-id")
    return p


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(_build_parser().parse_args())))
