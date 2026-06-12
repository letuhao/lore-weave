"""Seed a book's chapter-grounding corpus (LE-PROD slice C).

Production retrieval was starved on the demo book: its chapters (real 封神演义 prose
in book-service/MinIO) were never ingested as a ``source_corpus``, so P1 retrieval
found ~1 weak chunk and the LLM honestly returned "检索片段未提及" / parroted it.
This grounds a book by running EVERY chapter through the SAME ``ingest_book_chapters``
seam the author's ``/ground`` UI uses (one corpus ``book-chapters:{book_id}``,
idempotent — safe to re-run; a fresh stack is reproducibly grounded by re-running).

Runs in the lore-enrichment-service/worker container (reads DB + service URLs +
internal token from settings/env; embeds via provider-registry by ``model_ref`` —
NO hardcoded model name). NOT a request path — dev/demo seeding tooling.

Usage (inside the container):
    python -m scripts.seed_book_grounding --book <book_uuid> --user <user_uuid> \
        --embed <embedding_model_ref_uuid> [--project <uuid>] [--target-chars 800]

``--project`` defaults to ``--book`` (the demo's project_id == book_id). ``--user``
must OWN the embedding model_ref (BYOK).
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

import asyncpg

from app.clients.book import BookServiceError
from app.clients.knowledge import KnowledgeServiceError
from app.config import settings
from app.services.book_grounding import (
    NoChapterTextError,
    book_corpus_name,
    ingest_book_chapters,
)


async def _run(args: argparse.Namespace) -> int:
    book_id = UUID(args.book)
    project_id = UUID(args.project) if args.project else book_id
    user_id = UUID(args.user)
    embed_ref = UUID(args.embed)

    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
    try:
        print(f"=== seeding grounding for book {book_id} (corpus '{book_corpus_name(book_id)}') ===")
        try:
            res = await ingest_book_chapters(
                pool,
                user_id=user_id,
                project_id=project_id,
                book_id=book_id,
                embedding_model_ref=embed_ref,
                chapter_ids=None,  # ALL chapters (the seed/bulk path)
                target_chars=args.target_chars,
            )
        except NoChapterTextError as exc:
            print(f"FAIL: {exc} — the book has no chapter text to ground on")
            return 1
        except BookServiceError as exc:
            print(f"FAIL: book read failed ({exc})")
            return 2
        except KnowledgeServiceError as exc:
            print(f"FAIL: embedding failed ({exc}) — is provider-registry/LM Studio up?")
            return 2
        print(
            f"OK — ingested {res.chapters_ingested} chapter(s): "
            f"chunks_total={res.chunks_total} inserted={res.chunks_inserted} "
            f"embedded={res.chunks_embedded}"
        )
        if res.chunks_embedded == 0:
            print("WARN: 0 chunks embedded — retrieval will still be starved (check the embed model).")
            return 3
        return 0
    finally:
        await pool.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed a book's chapter-grounding corpus.")
    ap.add_argument("--book", required=True, help="book_id (UUID)")
    ap.add_argument("--user", required=True, help="user_id (UUID) that OWNS the embed model")
    ap.add_argument("--embed", required=True, help="embedding model_ref (provider-registry user_model UUID)")
    ap.add_argument("--project", default=None, help="project_id (UUID); defaults to --book")
    ap.add_argument("--target-chars", type=int, default=800, dest="target_chars")
    return asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
