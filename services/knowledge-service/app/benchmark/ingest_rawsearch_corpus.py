"""P3-EVAL E0b — in-container chapter→Passage ingest for the raw-search eval.

Embeds the eval corpus chapters as ``:Passage{source_type:'chapter'}``
nodes by reusing the production ``ingest_chapter_passages`` pipeline
(embedding-only — NOT the LLM extraction path). Runs INSIDE the
knowledge-service container (where neo4j/embedding/book-client + env are
available), invoked by the host seed:

    cat chapters.json | docker exec -i infra-knowledge-service-1 \
        python -m app.benchmark.ingest_rawsearch_corpus \
        --book-id … --project-id … --user-id … \
        --embedding-model <user_model_uuid> --embedding-dim 1024

stdin is a JSON list of ``{"chapter_id": "...", "chapter_index": N}``.
The host knows the ids (from the chapter-create responses); this module
just loops and ingests. Best-effort per chapter — one failure logs and
continues. Prints a JSON summary to stdout.

Lives under ``app/benchmark/`` (not ``eval/``) because the Dockerfile
ships ``app/`` only; ``eval/`` is host-side and absent from the image.
"""

from __future__ import annotations

from typing import Any


async def _run(args: Any) -> int:
    # Imports inside the function: app.config builds Settings() at module
    # load and needs env vars (KNOWLEDGE_DB_URL etc.) present — same
    # pattern as eval/run_benchmark.py so `--help` works without a stack.
    import json as _json
    import logging as _logging
    import sys as _sys
    from uuid import UUID as _UUID

    from app.clients.book_client import get_book_client
    from app.clients.embedding_client import init_embedding_client
    from app.db.neo4j import init_neo4j_driver, neo4j_session
    from app.extraction.passage_ingester import ingest_chapter_passages

    _logging.basicConfig(level=_logging.INFO)
    logger = _logging.getLogger("P3-EVAL.ingest")

    raw = _sys.stdin.read().strip()
    if not raw:
        print(_json.dumps({"error": "no chapters on stdin"}))
        return 1
    chapters = _json.loads(raw)

    book_id = _UUID(args.book_id)
    project_id = _UUID(args.project_id)
    user_id = _UUID(args.user_id)

    await init_neo4j_driver()
    embedding_client = init_embedding_client()
    book_client = get_book_client()

    ingested = 0
    passages_total = 0
    errors: list[str] = []
    async with neo4j_session() as session:
        for ch in chapters:
            cid = ch["chapter_id"]
            idx = ch.get("chapter_index")
            try:
                res = await ingest_chapter_passages(
                    session,
                    book_client,
                    embedding_client,
                    user_id=user_id,
                    project_id=project_id,
                    book_id=book_id,
                    chapter_id=_UUID(cid),
                    chapter_index=idx,
                    embedding_model=args.embedding_model,
                    embedding_dim=args.embedding_dim,
                    model_source=args.model_source,
                    revision_id=None,  # draft text (chapter_blocks)
                )
                if res.chunks_created > 0:
                    ingested += 1
                    passages_total += res.chunks_created
                else:
                    errors.append(f"{cid}: 0 chunks created")
                logger.info(
                    "chapter %s idx=%s -> %d passages", cid, idx, res.chunks_created,
                )
            except Exception as exc:  # noqa: BLE001 — best-effort per chapter
                errors.append(f"{cid}: {exc}")
                logger.warning("ingest failed for chapter %s: %s", cid, exc)

    print(_json.dumps({
        "chapters_ingested": ingested,
        "chapters_total": len(chapters),
        "passages_total": passages_total,
        "errors": errors[:20],
    }, ensure_ascii=False))
    return 0 if passages_total > 0 else 1


def _build_parser() -> Any:
    import argparse
    p = argparse.ArgumentParser(prog="ingest_rawsearch_corpus")
    p.add_argument("--book-id", required=True)
    p.add_argument("--project-id", required=True)
    p.add_argument("--user-id", required=True)
    p.add_argument("--embedding-model", required=True,
                   help="provider-registry user_model UUID of the embed model")
    p.add_argument("--embedding-dim", required=True, type=int)
    p.add_argument("--model-source", default="user_model",
                   choices=["user_model", "platform_model"])
    return p


def _main() -> int:
    import asyncio
    return asyncio.run(_run(_build_parser().parse_args()))


if __name__ == "__main__":
    import sys
    sys.exit(_main())
