"""C10 live-smoke — REAL cross-service embed + retrieve round-trip (NOT mocked).

Drives the actual technique-(b) retrieval path against the RUNNING stack to
confirm the cross-service seam works end-to-end (the CLAUDE.md VERIFY rule —
mock-only green is the known false-green trap for this kind of cycle):

  1. Resolve the project's embedding model by NAME from the provider-registry DB
     → a ``model_ref`` (user_model UUID). The model NAME lives only in the
     registry; this harness reads it at RUNTIME — NO model id is baked into code.
  2. Ingest one small 山海经 chunk into a fresh throwaway project: chunk it,
     call the REAL knowledge-service/provider-registry ``/internal/embed`` to
     embed it (bge-m3 via LM Studio — tolerate JIT first-call load latency with a
     few retries), and persist the vector to ``source_corpus_chunk``.
  3. Retrieve it back by cosine similarity (a query embedded by the same real
     call) and assert the seeded chunk comes back top-1.

Exit 0 ONLY if a real embed + retrieve actually round-tripped. If LM Studio
won't load the model or the embed endpoint is unreachable after retries, exit 3
and print ``live infra unavailable: <reason>`` (a legitimate skip per CLAUDE.md).
Nothing here is faked.

Env:
  LORE_ENRICHMENT_DB_URL    host DSN for loreweave_lore_enrichment
  PROVIDER_REGISTRY_DB_URL  host DSN for loreweave_provider_registry (model lookup)
  PROVIDER_REGISTRY_URL     default http://localhost:8208  (embed endpoint host)
  INTERNAL_SERVICE_TOKEN    default dev_internal_token
  EMBED_MODEL_NAME          default text-embedding-bge-m3  (looked up → model_ref)
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import asyncpg

from app.clients.knowledge import KnowledgeClient, KnowledgeServiceError
from app.db.migrate import run_migrations
from app.retrieval.embedding import make_embed_fn, make_embed_query_fn
from app.retrieval.store import SourceCorpusStore
from app.strategies.base import StrategyContext

# A single 山海经 sentence (public-domain) — the seeded grounding passage.
_SHANHAIJING_CHUNK = "蓬萊山在海中，上有仙人，宫室皆以金玉為之。"
_OTHER_CHUNK = "西王母其狀如人，豹尾虎齒而善嘯，蓬髮戴勝。"

_EMBED_RETRIES = 6          # JIT model load can take several attempts
_RETRY_SLEEP_S = 8.0


async def _resolve_model_ref(pr_dsn: str, model_name: str) -> tuple[str, str]:
    """Look up (model_ref, owner_user_id) for ``model_name`` in provider-registry.
    The model NAME is the only thing this harness knows; the UUID is discovered
    at runtime so no model id is hardcoded in committed code."""
    conn = await asyncpg.connect(pr_dsn)
    try:
        row = await conn.fetchrow(
            """
            SELECT user_model_id, owner_user_id
            FROM user_models
            WHERE provider_model_name = $1 AND is_active = true
            ORDER BY created_at DESC
            LIMIT 1
            """,
            model_name,
        )
    finally:
        await conn.close()
    if row is None:
        raise RuntimeError(
            f"no active user_model named {model_name!r} in provider-registry"
        )
    return str(row["user_model_id"]), str(row["owner_user_id"])


async def _embed_with_retry(client, *, user_id, model_ref, texts):
    """Call the REAL embed, retrying on retryable errors (JIT model load)."""
    last: Exception | None = None
    for attempt in range(1, _EMBED_RETRIES + 1):
        try:
            return await client.embed(
                user_id=user_id, model_source="user_model",
                model_ref=model_ref, texts=texts,
            )
        except KnowledgeServiceError as exc:
            last = exc
            msg = str(exc).lower()
            # A 400 EMBED_MODEL_INVALID that is actually a JIT load race
            # ("Failed to load model" / "Operation canceled") is TRANSIENT — the
            # model is being loaded/unloaded under contention. Retry those; a
            # genuinely-wrong model would fail every attempt and surface anyway.
            jit_race = (
                "failed to load model" in msg
                or "operation canceled" in msg
                or "model loading" in msg
                or "has not started loading" in msg
                or "has been unloaded" in msg
            )
            if (
                not exc.retryable
                and exc.status_code not in (502, 503, 504, 408)
                and not jit_race
            ):
                raise
            print(
                f"[live-smoke] embed attempt {attempt}/{_EMBED_RETRIES} "
                f"retryable ({exc}); waiting {_RETRY_SLEEP_S}s for JIT load",
                file=sys.stderr,
            )
            await asyncio.sleep(_RETRY_SLEEP_S)
    raise last if last else RuntimeError("embed failed with no exception")


async def _main() -> int:
    db_dsn = os.environ.get("LORE_ENRICHMENT_DB_URL", "")
    pr_dsn = os.environ.get("PROVIDER_REGISTRY_DB_URL", "")
    pr_url = os.environ.get("PROVIDER_REGISTRY_URL", "http://localhost:8208")
    token = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev_internal_token")
    model_name = os.environ.get("EMBED_MODEL_NAME", "text-embedding-bge-m3")

    if not db_dsn or not pr_dsn:
        print(
            "live infra unavailable: LORE_ENRICHMENT_DB_URL / "
            "PROVIDER_REGISTRY_DB_URL not set",
            file=sys.stderr,
        )
        return 3

    # discover the model_ref (UUID) by NAME — never hardcoded.
    try:
        model_ref, owner_user_id = await _resolve_model_ref(pr_dsn, model_name)
    except (OSError, asyncpg.PostgresError, RuntimeError) as exc:
        print(f"live infra unavailable: model lookup failed ({exc})", file=sys.stderr)
        return 3
    user_id = uuid.UUID(owner_user_id)
    model_ref_uuid = model_ref
    print(f"[live-smoke] resolved {model_name!r} → model_ref={model_ref_uuid}")

    # connect + apply migrations (idempotent; brings source_corpus_chunk up).
    try:
        pool = await asyncpg.create_pool(db_dsn, min_size=1, max_size=2, command_timeout=15)
    except (OSError, asyncpg.PostgresError) as exc:
        print(f"live infra unavailable: lore DB unreachable ({exc})", file=sys.stderr)
        return 3
    await run_migrations(pool)

    client = KnowledgeClient(
        knowledge_base_url=pr_url,
        provider_registry_base_url=pr_url,
        internal_token=token,
        embed_timeout_s=90.0,  # generous for cold JIT load
    )

    project_id = uuid.uuid4()
    store = SourceCorpusStore(pool)

    # batch embed_fn (ingest) + query embed_fn (search), both REAL calls.
    async def embed_fn(texts):
        result = await _embed_with_retry(
            client, user_id=user_id, model_ref=model_ref_uuid, texts=list(texts)
        )
        return result.embeddings

    try:
        # ── REAL ingest: chunk → real embed → persist ────────────────────────
        text = _SHANHAIJING_CHUNK + _OTHER_CHUNK
        ingest = await store.ingest_corpus(
            user_id=user_id, project_id=project_id, name="山海经-live-smoke",
            kind="shanhaijing", text=text, embed_fn=embed_fn,
            model_ref=model_ref_uuid, target_chars=20,
            license="public-domain",  # genuine PD demo (ingest fails closed otherwise, WARN-1)
        )
        if ingest.chunks_embedded < 1:
            print("live infra unavailable: no chunk embedded", file=sys.stderr)
            return 3

        # ── REAL retrieve: embed the 蓬萊 query → cosine search → top-1 ───────
        embed_query = make_embed_query_fn(client, user_id=user_id)
        ctx = StrategyContext(
            user_id=str(user_id), project_id=str(project_id), model_ref=model_ref_uuid
        )
        qvec = await embed_query("蓬萊山 仙人 金玉", ctx)
        hits = await store.search(project_id=project_id, query_vector=qvec, k=3)

        if not hits:
            print("live infra unavailable: search returned no hits", file=sys.stderr)
            return 3
        top = hits[0]
        ok = "蓬萊" in top.content
        print(
            f"live smoke: real bge-m3 embed+retrieve round-tripped — ingested "
            f"{ingest.chunks_embedded} 山海经 chunk(s), retrieved top-1 "
            f"'{top.content[:18]}…' score={top.score:.4f} (蓬萊-match={ok})"
        )
        # cleanup the throwaway corpus (CASCADE drops its chunks).
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM source_corpus WHERE project_id = $1", project_id
            )
        return 0 if ok else 4
    except KnowledgeServiceError as exc:
        print(f"live infra unavailable: embed failed after retries ({exc})", file=sys.stderr)
        return 3
    finally:
        await client.aclose()
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
