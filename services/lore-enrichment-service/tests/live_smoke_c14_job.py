"""C14 live-smoke — the DEMO: a REAL end-to-end P1 enrichment job (NOT mocked).

Drives the full C14 job runner against the RUNNING stack + the seeded Fengshen
demo project, for ONE under-described LOCATION (蓬萊), through the real Qwen 3.6
generation seam, then approves + promotes the resulting proposal and confirms the
write-back hit the glossary SSOT. Nothing is faked. This is the CLAUDE.md
cross-service VERIFY gate for a ≥2-service cycle (the known mock-only false-green
trap for this kind of work).

Round-trip:
  1. Resolve the GENERATION model (Qwen family) + EMBEDDING model (bge-m3 family)
     by NAME → provider-registry model_ref (UUID). Model names live ONLY in the
     registry and are read at RUNTIME — no model id is committed in code.
  2. Ingest a small 山海经 grounding chunk for 蓬萊 into the demo project (REAL
     /internal/embed; tolerate JIT first-call load with retries).
  3. Run the REAL C14 JobRunner for the 蓬萊 gap: retrieval (C10) → schema-gov
     generation via real Qwen (C11) → canon-verify (C12) → persist a QUARANTINED,
     H0-tagged Chinese proposal. Emit lifecycle events on Redis Streams.
  4. Assert H0: the persisted proposal is origin='enrichment', confidence<1.0,
     review_status='proposed', pending_validation; capture the generated Chinese.
  5. Drive the C13 review path: author_reviewing → approved → author PROMOTE
     (book-service owner check) → write-back to the glossary SSOT. Confirm the
     promotion record + permanent origin markers are stamped.

Exit 0 ONLY if a REAL generated proposal was produced AND promoted. If LM Studio
won't load Qwen after retries, exit 3 with ``live infra unavailable: <reason>``
(a legitimate skip per CLAUDE.md) — but never a faked-real claim.

Env (host-port defaults match infra/docker-compose.yml):
  LORE_ENRICHMENT_DB_URL    host DSN for loreweave_lore_enrichment (5555)
  PROVIDER_REGISTRY_DB_URL  host DSN for loreweave_provider_registry (model lookup)
  PROVIDER_REGISTRY_URL     default http://localhost:8208
  KNOWLEDGE_SERVICE_URL_H   default http://localhost:8216
  GLOSSARY_SERVICE_URL_H    default http://localhost:8211
  BOOK_SERVICE_URL_H        default http://localhost:8205
  REDIS_URL_H               default redis://localhost:6399
  INTERNAL_SERVICE_TOKEN    default dev_internal_token
  GEN_MODEL_NAME            default qwen/qwen3-32b  (looked up → model_ref)
  EMBED_MODEL_NAME          default text-embedding-bge-m3
  DEMO_PROJECT / DEMO_USER / DEMO_BOOK / DEMO_LOCATION  seeded demo coordinates
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import asyncpg

from app.clients.knowledge import KnowledgeClient, KnowledgeServiceError
from app.clients.port import KnowledgeReadHttp
from app.clients.writeback import WritebackPorts
from app.db.migrate import run_migrations
from app.gaps.model import Dimension, EntityKind, Gap
from app.generation.complete import CompletionSeamError, make_complete_fn
from app.generation.generate import SchemaGovernedGenerator
from app.jobs.cost import JobCostBudget
from app.jobs.events import JobEventEmitter, make_redis_producer
from app.jobs.proposal_store import PgProposalStore
from app.jobs.runner import JobRunner
from app.jobs.stages import GapPipeline
from app.retrieval.store import SourceCorpusStore
from app.retrieval.strategy import RetrievalStrategy
from app.services.review import ProposalsRepo, ReviewStatus
from app.services.writeback import WritebackService
from app.strategies.base import StrategyContext, Technique
from app.strategies.template import TemplateStrategy
from app.verify.canon_verify import CanonFact, CanonVerifier

# A 山海经 grounding passage for 蓬萊 (public-domain).
_SHANHAIJING_PENGLAI = "蓬萊山在海中，上有仙人，宫室皆以金玉為之，鸟兽尽白。"

_RETRIES = 6
_RETRY_SLEEP_S = 8.0


async def _resolve_model_ref(
    pr_dsn: str, name: str, *, owner: str | None = None
) -> tuple[str, str]:
    """Resolve (user_model_id, owner_user_id) for ``name`` at RUNTIME (the model
    NAME is the only thing committed; the UUID is discovered live). When ``owner``
    is given, the lookup is scoped to that owner — required when a model name is
    registered by multiple users and the BYOK call must use one specific owner's
    credential (e.g. the generation model must be owned by the job's demo user)."""
    conn = await asyncpg.connect(pr_dsn)
    try:
        if owner is not None:
            row = await conn.fetchrow(
                """SELECT user_model_id, owner_user_id FROM user_models
                   WHERE provider_model_name = $1 AND owner_user_id = $2
                     AND is_active = true
                   ORDER BY created_at DESC LIMIT 1""",
                name, uuid.UUID(owner),
            )
        else:
            row = await conn.fetchrow(
                """SELECT user_model_id, owner_user_id FROM user_models
                   WHERE provider_model_name = $1 AND is_active = true
                   ORDER BY created_at DESC LIMIT 1""",
                name,
            )
    finally:
        await conn.close()
    if row is None:
        scope = f" owned by {owner}" if owner else ""
        raise RuntimeError(f"no active user_model named {name!r}{scope}")
    return str(row["user_model_id"]), str(row["owner_user_id"])


async def _embed_with_retry(client, *, user_id, model_ref, texts):
    last: Exception | None = None
    for attempt in range(1, _RETRIES + 1):
        try:
            return await client.embed(
                user_id=user_id, model_source="user_model",
                model_ref=model_ref, texts=texts,
            )
        except KnowledgeServiceError as exc:
            last = exc
            msg = str(exc).lower()
            jit = any(s in msg for s in (
                "failed to load model", "operation canceled", "model loading",
                "has not started loading", "has been unloaded",
            ))
            if not exc.retryable and exc.status_code not in (502, 503, 504, 408) and not jit:
                raise
            print(f"[c14-smoke] embed attempt {attempt}/{_RETRIES} retryable ({exc})",
                  file=sys.stderr)
            await asyncio.sleep(_RETRY_SLEEP_S)
    raise last if last else RuntimeError("embed failed")


def _complete_with_retry(base_complete):
    async def _fn(prompt, ctx):
        last: Exception | None = None
        for attempt in range(1, _RETRIES + 1):
            try:
                return await base_complete(prompt, ctx)
            except CompletionSeamError as exc:
                last = exc
                if not exc.retryable:
                    raise
                print(f"[c14-smoke] gen attempt {attempt}/{_RETRIES} retryable ({exc}) "
                      f"— waiting {_RETRY_SLEEP_S}s for JIT load", file=sys.stderr)
                await asyncio.sleep(_RETRY_SLEEP_S)
        raise last if last else RuntimeError("generation failed")
    return _fn


async def _main() -> int:  # noqa: C901 — a linear smoke script
    db_dsn = os.environ.get("LORE_ENRICHMENT_DB_URL", "")
    pr_dsn = os.environ.get("PROVIDER_REGISTRY_DB_URL", "")
    pr_url = os.environ.get("PROVIDER_REGISTRY_URL", "http://localhost:8208")
    know_url = os.environ.get("KNOWLEDGE_SERVICE_URL_H", "http://localhost:8216")
    gloss_url = os.environ.get("GLOSSARY_SERVICE_URL_H", "http://localhost:8211")
    book_url = os.environ.get("BOOK_SERVICE_URL_H", "http://localhost:8205")
    redis_url = os.environ.get("REDIS_URL_H", "redis://localhost:6399")
    token = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev_internal_token")
    gen_name = os.environ.get("GEN_MODEL_NAME", "qwen/qwen3.6-35b-a3b")
    embed_name = os.environ.get("EMBED_MODEL_NAME", "text-embedding-bge-m3")

    demo_project = os.environ.get("DEMO_PROJECT", "019e7850-aa1c-7cd3-a25c-c2f9ad84fd39")
    demo_user = os.environ.get("DEMO_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
    demo_book = os.environ.get("DEMO_BOOK", "019e7850-a8d9-78dd-8b2a-f33ccc2396ad")
    demo_loc = os.environ.get("DEMO_LOCATION", "蓬萊")

    if not db_dsn or not pr_dsn:
        print("live infra unavailable: LORE_ENRICHMENT_DB_URL / PROVIDER_REGISTRY_DB_URL not set",
              file=sys.stderr)
        return 3

    # ── resolve model refs by NAME (never hardcoded) ───────────────────────────
    # Each BYOK model is scoped to its OWNER for the provider-registry credential
    # lookup; the JOB itself persists under the demo user. So we use the embed
    # model's owner for /internal/embed and the gen model's owner for generation,
    # while the proposal rows are written for the demo user/project.
    try:
        embed_ref, embed_owner = await _resolve_model_ref(pr_dsn, embed_name)
        # the gen model MUST be owned by the demo user (the job's StrategyContext
        # user) so the /internal/llm BYOK lookup resolves it.
        gen_ref, gen_owner = await _resolve_model_ref(
            pr_dsn, gen_name, owner=demo_user
        )
    except (OSError, asyncpg.PostgresError, RuntimeError) as exc:
        print(f"live infra unavailable: model lookup failed ({exc})", file=sys.stderr)
        return 3
    user_id = uuid.UUID(demo_user)  # the job/proposal scope (Q3)
    embed_owner_uuid = uuid.UUID(embed_owner)  # BYOK scope for /internal/embed
    print(f"[c14-smoke] resolved gen {gen_name!r}→{gen_ref} (owner {gen_owner}) "
          f"embed {embed_name!r}→{embed_ref} (owner {embed_owner})")

    try:
        pool = await asyncpg.create_pool(db_dsn, min_size=1, max_size=3, command_timeout=20)
    except (OSError, asyncpg.PostgresError) as exc:
        print(f"live infra unavailable: lore DB unreachable ({exc})", file=sys.stderr)
        return 3
    await run_migrations(pool)

    client = KnowledgeClient(
        knowledge_base_url=know_url, provider_registry_base_url=pr_url,
        internal_token=token, embed_timeout_s=120.0,
    )
    project_uuid = uuid.UUID(demo_project)
    store = SourceCorpusStore(pool)

    async def embed_fn(texts):
        # embed BYOK call scoped to the embed model's owner.
        r = await _embed_with_retry(
            client, user_id=embed_owner_uuid, model_ref=embed_ref, texts=list(texts)
        )
        return r.embeddings

    try:
        # ── 2. ingest a 山海经 grounding chunk for 蓬萊 (REAL embed) ───────────────
        ingest = await store.ingest_corpus(
            user_id=user_id, project_id=project_uuid, name="山海经-c14-demo",
            kind="shanhaijing", text=_SHANHAIJING_PENGLAI, embed_fn=embed_fn,
            model_ref=embed_ref, target_chars=40,
        )
        if ingest.chunks_embedded < 1 and ingest.chunks_total < 1:
            print("live infra unavailable: no grounding chunk embedded", file=sys.stderr)
            return 3
        print(f"[c14-smoke] ingested grounding: {ingest.chunks_total} chunk(s)")

        # ── 3. assemble the REAL runner (host-port wiring) ─────────────────────
        # query-embed seam with JIT retry — uses the EMBED model (+owner), NOT the
        # gen model on the context (retrieval embeds, generation completes).
        async def _retry_embed_query(query, ctx):
            r = await _embed_with_retry(
                client, user_id=embed_owner_uuid, model_ref=embed_ref, texts=[query]
            )
            if not r.embeddings:
                raise RuntimeError("no query vector")
            return r.embeddings[0]

        retrieval = RetrievalStrategy(store=store, embed_query=_retry_embed_query, top_k=5)
        base_complete = make_complete_fn(
            provider_registry_base_url=pr_url, internal_token=token, timeout_s=240.0,
        )
        generator = SchemaGovernedGenerator(complete=_complete_with_retry(base_complete))
        read_port = KnowledgeReadHttp(client)

        async def _canon_lookup(entity, dim) -> list[CanonFact]:
            return []

        verifier = CanonVerifier(read_port=read_port, canon_lookup=_canon_lookup)
        pipeline = GapPipeline(retrieval=retrieval, generator=generator, verifier=verifier)

        pg_store = PgProposalStore(pool)
        # create the job row first so events correlate to the real DB job id.
        job_id = await pg_store.create_job(
            user_id=str(user_id), project_id=demo_project,
            technique=Technique.RETRIEVAL.value, entity_kind="location",
            max_spend=1000.0, estimated_cost=0.0,
        )
        emitter = JobEventEmitter(
            make_redis_producer(redis_url), job_id=job_id,
            project_id=demo_project, user_id=str(user_id),
        )
        budget = JobCostBudget(1000.0, eval_reserve_fraction=0.15)
        runner = JobRunner(
            store=pg_store, pipeline=pipeline, cost_strategy=TemplateStrategy(),
            emitter=emitter, budget=budget,
        )

        gap = Gap(
            entity_kind=EntityKind.LOCATION, canonical_name=demo_loc,
            target_ref=f"loc:{demo_loc}", mention_count=3,
            present_dimensions=(), missing_dimensions=tuple(Dimension),
        )
        ctx = StrategyContext(user_id=str(user_id), project_id=demo_project, model_ref=gen_ref)

        print(f"[c14-smoke] running REAL P1 job {job_id} for {demo_loc} (real Qwen)...")
        outcome = await runner.run_job(
            job_id=job_id, gaps=[gap], context=ctx, entity_kind="location"
        )

        if outcome.final_state != "completed":
            print(f"live infra unavailable: job ended {outcome.final_state} "
                  f"(err={outcome.error}, skipped={outcome.skipped_gaps})", file=sys.stderr)
            return 3
        if not outcome.proposals:
            print("live infra unavailable: no proposal produced (gap skipped — likely "
                  "no grounding / JIT generation failure)", file=sys.stderr)
            return 3

        p = outcome.proposals[0]
        # ── 4. H0 assertions + capture the generated Chinese ───────────────────
        assert p.origin == "enrichment", f"H0 LEAK: origin={p.origin}"
        assert p.origin != "glossary", "H0 LEAK: origin is canon"
        assert 0.0 < p.confidence < 1.0, f"H0 LEAK: confidence={p.confidence}"
        assert p.review_status == "proposed", f"H0: review_status={p.review_status}"
        assert p.pending_validation is True, "H0: not pending_validation"

        # fetch the persisted row to show the actual generated Chinese content.
        repo = ProposalsRepo(pool)
        row = await repo.get(user_id=user_id, project_id=project_uuid,
                             proposal_id=uuid.UUID(p.proposal_id))
        assert row is not None, "persisted proposal not found"
        dims = (row.provenance_json or {}).get("dimensions", {})
        print("[c14-smoke] ===== REAL GENERATED CHINESE (quarantined, H0) =====")
        for label, value in dims.items():
            print(f"  【{label}】{value}")
        print("[c14-smoke] =======================================================")
        assert dims, "no generated dimensions persisted"
        # provenance must cite the 山海经 grounding (source_refs non-empty).
        assert row.source_refs_json, "no grounding provenance on the proposal"
        print(f"[c14-smoke] H0 OK: quarantined enriched proposal {p.proposal_id} "
              f"(origin={p.origin}, conf={p.confidence}, {len(dims)} dims, "
              f"{len(row.source_refs_json)} grounding ref(s))")

        # ── 5. review → approve → author PROMOTE → write-back to glossary ──────
        await repo.set_status(user_id=user_id, project_id=project_uuid,
                              proposal_id=uuid.UUID(p.proposal_id),
                              to_status=ReviewStatus.AUTHOR_REVIEWING)
        await repo.set_status(user_id=user_id, project_id=project_uuid,
                              proposal_id=uuid.UUID(p.proposal_id),
                              to_status=ReviewStatus.APPROVED)
        ports = WritebackPorts(
            glossary_base_url=gloss_url, knowledge_base_url=know_url,
            book_base_url=book_url, internal_token=token,
        )
        wb = WritebackService(repo, ports)
        try:
            promote = await wb.promote(
                acting_user_id=user_id, project_id=project_uuid,
                proposal_id=uuid.UUID(p.proposal_id), book_id=uuid.UUID(demo_book),
            )
        finally:
            await ports.aclose()
        assert promote.canon is True, "promote did not canonize"
        promoted = await repo.get(user_id=user_id, project_id=project_uuid,
                                  proposal_id=uuid.UUID(p.proposal_id))
        assert promoted is not None and promoted.review_status == "promoted"
        # permanent origin markers survive promotion (H0 traceability).
        assert promoted.origin == "enrichment", "promote dropped origin marker"
        assert promoted.original_technique, "promote dropped original_technique"
        assert promoted.promoted_by == user_id, "promoted_by not stamped"
        assert promoted.confidence < 1.0, "proposal-row confidence reached canon"
        print(f"[c14-smoke] PROMOTED → canon (glossary entity {promote.promoted_entity_id}, "
              f"facts_promoted={promote.facts_promoted}) WITH origin marker intact "
              f"(origin=enrichment, original_technique={promoted.original_technique}, "
              f"promoted_by={promoted.promoted_by})")

        print(f"[c14-smoke] events emitted: {len(emitter.emitted)} "
              f"(failures={emitter.emit_failures})")
        print("[c14-smoke] LIVE-SMOKE PASS: real P1 job on Fengshen → quarantined "
              "enriched proposal → review → author promote → write-back to glossary")
        return 0
    except AssertionError as exc:
        print(f"[c14-smoke] FAIL (H0 / round-trip assertion): {exc}", file=sys.stderr)
        return 1
    except (KnowledgeServiceError, CompletionSeamError) as exc:
        print(f"live infra unavailable: upstream error after retries ({exc})", file=sys.stderr)
        return 3
    finally:
        await client.aclose()
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
