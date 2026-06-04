"""Seed a curated PUBLIC-DOMAIN grounding corpus from committed text fixtures
(LE-PROD slice C).

The demo book's chapters in book-service are ~55-char UI stubs, so P1 retrieval had
nothing to ground on. This ingests the committed verbatim 封神演義 PD text under
``scripts/seed_data/fengshen/`` (see its README) as ONE curated ``source_corpus``
(kind=``fengshen``, license=``public_domain``, ``compose_ephemeral=false`` so the
reaper never GCs it), via the SAME ``ingest_corpus`` embed seam the app uses
(embeds by provider-registry ``model_ref`` — NO hardcoded model name). Idempotent
(content-hashed chunks → re-run is a no-op on unchanged text).

Reproducible (no network at seed time — the text is committed). Runs in the
lore-enrichment container (reads DB + service URLs + token from settings/env).

Usage (inside the container):
    python -m scripts.seed_pd_corpus --book <book_uuid> --user <user_uuid> \
        --embed <embedding_model_ref_uuid> [--project <uuid>] \
        [--dir scripts/seed_data/fengshen] [--name fengshen-pd]

``--project`` defaults to ``--book``; ``--user`` must OWN the embed model_ref.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

import asyncpg

from app.clients.knowledge import KnowledgeClient, KnowledgeServiceError
from app.config import settings
from app.retrieval.store import SourceCorpusStore

_DEFAULT_DIR = Path(__file__).parent / "seed_data" / "fengshen"


def _read_corpus_text(directory: Path) -> tuple[str, int]:
    """Concatenate every ``*.txt`` in ``directory`` (sorted) into one corpus body.
    Returns (text, file_count). Skips the README + empties."""
    files = sorted(p for p in directory.glob("*.txt") if p.is_file())
    parts: list[str] = []
    for p in files:
        t = p.read_text(encoding="utf-8").strip()
        if t:
            parts.append(t)
    return "\n\n".join(parts), len(parts)


async def _run(args: argparse.Namespace) -> int:
    book_id = UUID(args.book)
    project_id = UUID(args.project) if args.project else book_id
    user_id = UUID(args.user)
    embed_ref = UUID(args.embed)
    directory = Path(args.dir)

    text, n_files = _read_corpus_text(directory)
    if not text:
        print(f"FAIL: no .txt fixtures found under {directory}")
        return 1
    corpus_name = f"{args.name}:{book_id}"
    print(f"=== seeding curated PD corpus '{corpus_name}' from {n_files} file(s), {len(text)} chars ===")

    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)

    # Clean rebuild (default): ingest_corpus's _persist_chunks is ON CONFLICT
    # (corpus_id, chunk_index) DO NOTHING, so re-running with CHANGED fixtures would
    # keep stale chunk-index content and only append beyond the old max index — a
    # corrupt mix. A curated PD seed must reflect the fixtures EXACTLY, so drop the
    # existing corpus first (chunks cascade) unless --no-replace. (review-impl #1)
    if args.replace:
        async with pool.acquire() as conn:
            deleted = await conn.fetchval(
                "WITH d AS (DELETE FROM source_corpus "
                "WHERE user_id=$1 AND project_id=$2 AND name=$3 RETURNING corpus_id) "
                "SELECT count(*) FROM d",
                user_id, project_id, corpus_name,
            )
            if deleted:
                print(f"  (replaced existing corpus '{corpus_name}' — clean rebuild)")

    kc = KnowledgeClient(
        knowledge_base_url=settings.knowledge_service_url,
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )

    async def embed_fn(chunk_texts):
        result = await kc.embed(
            user_id=user_id, model_source="user_model",
            model_ref=str(embed_ref), texts=list(chunk_texts),
        )
        return result.embeddings

    try:
        store = SourceCorpusStore(pool)
        try:
            ingest = await store.ingest_corpus(
                user_id=user_id, project_id=project_id,
                name=corpus_name, kind=args.kind, license=args.license,
                text=text, embed_fn=embed_fn, model_ref=str(embed_ref),
                # Curated, NOT a compose paste → the reaper must never GC it.
                provenance_json={"compose_ephemeral": False, "source": "seed_pd_corpus"},
            )
        except KnowledgeServiceError as exc:
            print(f"FAIL: embedding failed ({exc}) — is provider-registry/LM Studio up?")
            return 2
    finally:
        await kc.aclose()
        await pool.close()

    print(
        f"OK — corpus '{corpus_name}': chunks_total={ingest.chunks_total} "
        f"inserted={ingest.chunks_inserted} embedded={ingest.chunks_embedded}"
    )
    if ingest.chunks_embedded == 0:
        print("WARN: 0 chunks embedded — retrieval still starved (check the embed model).")
        return 3
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed a curated public-domain grounding corpus.")
    ap.add_argument("--book", required=True, help="book_id (UUID)")
    ap.add_argument("--user", required=True, help="user_id (UUID) that OWNS the embed model")
    ap.add_argument("--embed", required=True, help="embedding model_ref (provider-registry user_model UUID)")
    ap.add_argument("--project", default=None, help="project_id (UUID); defaults to --book")
    ap.add_argument("--dir", default=str(_DEFAULT_DIR), help="fixture dir of *.txt")
    ap.add_argument("--name", default="fengshen-pd", help="corpus name prefix")
    ap.add_argument("--kind", default="fengshen",
                    help="source_corpus.kind (fengshen|shanhaijing|history|other)")
    ap.add_argument("--license", default="public_domain",
                    help="corpus license (public_domain|licensed|owned|…)")
    ap.add_argument(
        "--no-replace", dest="replace", action="store_false",
        help="append to the existing corpus instead of a clean rebuild (default: replace)",
    )
    ap.set_defaults(replace=True)
    return asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
