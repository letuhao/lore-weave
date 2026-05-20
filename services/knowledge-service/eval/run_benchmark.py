"""K17.9 — golden-set benchmark CLI shell.

D-EMB-EVAL-PKG-01: the runtime portion of the harness moved into
``app/benchmark/`` so it ships with the service. This file is the
thin standalone CLI that orchestrates load-fixture → run → persist
against the real compose stack — invoked as
``python -m eval.run_benchmark --project-id=... --embedding-model=...``.

Imports from ``app.benchmark.*`` so behaviour matches the in-process
benchmark endpoint exactly. Exits 0 when the report passes every
threshold, 1 otherwise — lets CI consume the result.
"""

from __future__ import annotations

from typing import Any


async def _run_cli(args: Any) -> int:
    """Orchestrate load → run → persist.

    Imports are deliberately inside the function body — ``app.config``
    constructs ``Settings()`` at module load and requires env vars like
    ``KNOWLEDGE_DB_URL`` / ``INTERNAL_SERVICE_TOKEN`` to be set. Hoisting
    those to module level would make simply running ``--help`` against
    this script fail without the full service config.
    """
    import json as _json
    import logging as _logging
    from uuid import UUID as _UUID

    import asyncpg

    from app.benchmark.core import (
        AsyncBenchmarkRunner,
        _default_golden_path,
        _default_run_id,
        load_golden_set,
    )
    from app.benchmark.fixture_loader import load_golden_set_as_passages
    from app.benchmark.mode3_query_runner import Mode3QueryRunner
    from app.benchmark.persist import persist_benchmark_report
    from app.clients.embedding_client import init_embedding_client
    from app.config import settings
    from app.db.neo4j import init_neo4j_driver, neo4j_session

    _logging.basicConfig(level=_logging.INFO)
    logger = _logging.getLogger("K17.9.cli")

    golden = load_golden_set(args.golden or _default_golden_path())
    # D-EMB-MODEL-REF-01 — --embedding-model is now a provider-registry
    # user_model UUID, so the dimension can't be derived from it; the
    # caller passes it explicitly via --embedding-dim.
    embedding_dim = args.embedding_dim

    await init_neo4j_driver()
    embedding_client = init_embedding_client()
    pool = await asyncpg.create_pool(settings.knowledge_db_url)
    assert pool is not None

    try:
        async with neo4j_session() as session:
            logger.info(
                "loading %d fixture entities for model=%s...",
                len(golden.entities), args.embedding_model,
            )
            loaded = await load_golden_set_as_passages(
                session, embedding_client, golden,
                user_id=args.user_id,
                project_id=args.project_id,
                user_uuid=_UUID(args.user_id),
                model_source=args.model_source,
                embedding_model=args.embedding_model,
                embedding_dim=embedding_dim,
            )
            logger.info("loaded %d/%d passages", loaded, len(golden.entities))

            runner = Mode3QueryRunner(
                session, embedding_client,
                user_id=args.user_id,
                project_id=args.project_id,
                user_uuid=_UUID(args.user_id),
                model_source=args.model_source,
                embedding_model=args.embedding_model,
                embedding_dim=embedding_dim,
            )
            report = await AsyncBenchmarkRunner(golden, runner).run(runs=args.runs)

        run_id = args.run_id or _default_run_id()
        provider_id = _UUID(args.embedding_provider_id) if args.embedding_provider_id else None
        await persist_benchmark_report(
            pool,
            project_id=_UUID(args.project_id),
            embedding_provider_id=provider_id,
            embedding_model=args.embedding_model,
            run_id=run_id,
            report=report,
        )
    finally:
        await pool.close()

    import sys
    sys.stdout.write(_json.dumps(report.to_json(), indent=2) + "\n")
    passed = report.passes_thresholds()
    logger.info("benchmark %s (run_id=%s)", "PASSED" if passed else "FAILED", run_id)
    return 0 if passed else 1


def _build_arg_parser() -> Any:
    import argparse
    p = argparse.ArgumentParser(prog="run_benchmark")
    p.add_argument("--user-id", required=True, help="UUID of the benchmark test user")
    p.add_argument("--project-id", required=True, help="UUID of the benchmark project")
    p.add_argument(
        "--embedding-model", required=True,
        help="provider-registry user_model UUID of the embedding model",
    )
    p.add_argument(
        "--embedding-dim", required=True, type=int,
        help="vector dimension of the embedding model (e.g. 1024 for bge-m3)",
    )
    p.add_argument(
        "--model-source", default="user_model",
        choices=["user_model", "platform_model"],
    )
    p.add_argument("--embedding-provider-id", default=None, help="optional UUID")
    p.add_argument(
        "--run-id", default=None,
        help="default: benchmark-<utc-timestamp>; set to re-use for reruns",
    )
    p.add_argument("--runs", type=int, default=3, help="default 3 per L-CH-09")
    p.add_argument(
        "--golden", default=None,
        help="yaml path (default: app/benchmark/golden_set.yaml)",
    )
    return p


def _main() -> int:
    import asyncio
    args = _build_arg_parser().parse_args()
    return asyncio.run(_run_cli(args))


if __name__ == "__main__":
    import sys
    sys.exit(_main())
