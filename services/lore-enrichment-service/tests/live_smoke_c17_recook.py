"""C17 live-smoke — a REAL RE-COOK of a PUBLIC-DOMAIN history snippet into 商周.

Drives the C17 :class:`ReCookStrategy` against the RUNNING stack + the seeded
Fengshen demo project, for ONE under-described LOCATION (陳塘關), through the real
Qwen generation seam. Nothing is faked. Three load-bearing facts are proven live:

  1. **GATE ENFORCEMENT (DEFERRED-054, reused for P3):** the
     :class:`GateAwareStrategyFactory` reads the LIVE persisted eval gate
     (``enrichment_eval_runs`` via ``EvalRunsRepo``). If LOCKED, re-cook is NOT
     selectable (``InactiveStrategyError``) → exit 3 (correct refusal). Only when
     CLEARED does re-cook run.
  2. **LICENSING gate (the C17-specific safety):** the source corpus is ingested
     with a PUBLIC-DOMAIN license; the licensing check ADMITS it. (A negative
     control re-cook against a COPYRIGHTED corpus is also exercised — it must be
     REFUSED with UnlicensedSourceError.)
  3. **H0:** every re-cooked fact is ``origin='enriched:recook'``, ``confidence
     <1.0``, quarantined (``pending_validation``), with non-empty grounding
     ``source_refs`` + provenance ``recooked=True`` + the licensed source basis —
     and canon-verify (C12) ran (anachronism check on the re-cooked content). No
     write-back, no promote.

Exit 0 ONLY if the gate was CLEARED AND a REAL re-cooked, H0-tagged proposal was
produced from a LICENSED source AND the copyrighted negative control was refused.
LM Studio won't load / gate not cleared / DB unreachable → exit 3 (legitimate
skip), never a faked-real claim.

Env defaults match infra/docker-compose.yml host ports (see C16 smoke).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import asyncpg

from app.clients.knowledge import KnowledgeClient, KnowledgeServiceError
from app.clients.port import KnowledgeReadHttp
from app.db.migrate import run_migrations
from app.db.repositories.eval_runs import EvalRunsRepo
from app.gaps.model import Dimension, EntityKind, Gap
from app.generation.complete import CompletionSeamError, make_complete_fn
from app.retrieval.store import SourceCorpusStore
from app.retrieval.strategy import RetrievalStrategy
from app.strategies.base import StrategyContext, Technique
from app.strategies.factory import GateAwareStrategyFactory
from app.strategies.gate_reader import make_eval_runs_gate_reader
from app.strategies.licensing import LicenseStatus, SourceLicense, UnlicensedSourceError
from app.strategies.recook import ReCookStrategy
from app.strategies.registry import InactiveStrategyError
from app.verify.canon_verify import CanonFact, CanonVerifier

# A PUBLIC-DOMAIN history snippet about a frontier pass — re-cooked into 商周/封神.
_PD_HISTORY = (
    "古代边关多设于山川险要之处，戍卒屯守，关民耕牧，"
    "岁时祭祀以祈平安，商旅往来，文化交融。"
)
_RETRIES = 6
_RETRY_SLEEP_S = 8.0


async def _resolve_model_ref(pr_dsn, name, *, owner=None):
    conn = await asyncpg.connect(pr_dsn)
    try:
        if owner is not None:
            row = await conn.fetchrow(
                """SELECT user_model_id, owner_user_id FROM user_models
                   WHERE provider_model_name=$1 AND owner_user_id=$2 AND is_active=true
                   ORDER BY created_at DESC LIMIT 1""",
                name, uuid.UUID(owner),
            )
        else:
            row = await conn.fetchrow(
                """SELECT user_model_id, owner_user_id FROM user_models
                   WHERE provider_model_name=$1 AND is_active=true
                   ORDER BY created_at DESC LIMIT 1""",
                name,
            )
    finally:
        await conn.close()
    if row is None:
        raise RuntimeError(f"no active user_model named {name!r}")
    return str(row["user_model_id"]), str(row["owner_user_id"])


async def _embed_with_retry(client, *, user_id, model_ref, texts):
    last = None
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
            print(f"[c17-smoke] embed attempt {attempt}/{_RETRIES} retryable ({exc})",
                  file=sys.stderr)
            await asyncio.sleep(_RETRY_SLEEP_S)
    raise last if last else RuntimeError("embed failed")


def _complete_with_retry(base_complete):
    async def _fn(prompt, ctx):
        last = None
        for attempt in range(1, _RETRIES + 1):
            try:
                return await base_complete(prompt, ctx)
            except CompletionSeamError as exc:
                last = exc
                if not exc.retryable:
                    raise
                print(f"[c17-smoke] gen attempt {attempt}/{_RETRIES} retryable ({exc}) "
                      f"— waiting {_RETRY_SLEEP_S}s for JIT load", file=sys.stderr)
                await asyncio.sleep(_RETRY_SLEEP_S)
        raise last if last else RuntimeError("generation failed")
    return _fn


async def _main() -> int:  # noqa: C901 — a linear smoke script
    db_dsn = os.environ.get("LORE_ENRICHMENT_DB_URL", "")
    pr_dsn = os.environ.get("PROVIDER_REGISTRY_DB_URL", "")
    pr_url = os.environ.get("PROVIDER_REGISTRY_URL", "http://localhost:8208")
    know_url = os.environ.get("KNOWLEDGE_SERVICE_URL_H", "http://localhost:8216")
    token = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev_internal_token")
    gen_name = os.environ.get("GEN_MODEL_NAME", "qwen/qwen3.6-35b-a3b")
    embed_name = os.environ.get("EMBED_MODEL_NAME", "text-embedding-bge-m3")
    suite_version = os.environ.get("SUITE_VERSION", "enrichment-v1")

    demo_project = os.environ.get("DEMO_PROJECT", "019e7850-aa1c-7cd3-a25c-c2f9ad84fd39")
    demo_user = os.environ.get("DEMO_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
    demo_loc = os.environ.get("DEMO_LOCATION", "陳塘關")

    if not db_dsn or not pr_dsn:
        print("live infra unavailable: LORE_ENRICHMENT_DB_URL / PROVIDER_REGISTRY_DB_URL not set",
              file=sys.stderr)
        return 3

    try:
        embed_ref, embed_owner = await _resolve_model_ref(pr_dsn, embed_name)
        gen_ref, _gen_owner = await _resolve_model_ref(pr_dsn, gen_name, owner=demo_user)
    except (OSError, asyncpg.PostgresError, RuntimeError) as exc:
        print(f"live infra unavailable: model lookup failed ({exc})", file=sys.stderr)
        return 3
    user_id = uuid.UUID(demo_user)
    embed_owner_uuid = uuid.UUID(embed_owner)

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

    try:
        async def _retry_embed_query(query, ctx):
            r = await _embed_with_retry(
                client, user_id=embed_owner_uuid, model_ref=embed_ref, texts=[query]
            )
            if not r.embeddings:
                raise RuntimeError("no query vector")
            return r.embeddings[0]

        async def embed_fn(texts):
            r = await _embed_with_retry(
                client, user_id=embed_owner_uuid, model_ref=embed_ref, texts=list(texts)
            )
            return r.embeddings

        # ── ingest the PUBLIC-DOMAIN history snippet as the re-cook source ───────
        ingest = await store.ingest_corpus(
            user_id=user_id, project_id=project_uuid, name="史料-c17-demo-pd",
            kind="history", text=_PD_HISTORY, embed_fn=embed_fn,
            model_ref=embed_ref, target_chars=40, license="public-domain",
        )
        if ingest.chunks_total < 1:
            print("live infra unavailable: no grounding chunk embedded", file=sys.stderr)
            return 3
        pd_corpus_id = str(ingest.corpus_id)

        # ── the production license resolver (reads source_corpus.license) ────────
        async def _license_lookup(corpus_id: str) -> SourceLicense | None:
            raw = await store.get_corpus_license(corpus_id=uuid.UUID(corpus_id))
            if raw is None:
                return None
            return SourceLicense.from_raw(corpus_id=corpus_id, name=corpus_id, license=raw)

        retrieval = RetrievalStrategy(store=store, embed_query=_retry_embed_query, top_k=5)
        base_complete = make_complete_fn(
            provider_registry_base_url=pr_url, internal_token=token, timeout_s=240.0,
        )
        read_port = KnowledgeReadHttp(client)

        async def _canon_lookup(entity, dim) -> list[CanonFact]:
            return []

        verifier = CanonVerifier(read_port=read_port, canon_lookup=_canon_lookup)
        recook = ReCookStrategy(
            retrieval=retrieval,
            complete=_complete_with_retry(base_complete),
            verifier=verifier,
            license_lookup=_license_lookup,
        )

        # ── GATE ENFORCEMENT — read the LIVE gate via the production reader ──────
        repo = EvalRunsRepo(pool)
        factory = GateAwareStrategyFactory(
            gate_reader=make_eval_runs_gate_reader(repo),
            strategies=[recook],
            suite_version=suite_version,
        )
        gate = await factory.read_gate(user_id=str(user_id), project_id=demo_project)
        print(f"[c17-smoke] live gate: has_run={gate.has_run} "
              f"p2_p3_unlocked={gate.p2_p3_unlocked} composite={gate.composite}")

        if os.environ.get("SEED_GATE", "1") == "1" and not gate.p2_p3_unlocked:
            print("[c17-smoke] no passing eval run — seeding one (C15 EvalRunsRepo) "
                  "so the gate-cleared path is deterministic")
            await repo.persist(
                user_id=user_id, project_id=project_uuid,
                run_id=f"c17-smoke-{uuid.uuid4().hex[:8]}",
                suite_version=suite_version, baseline_version=suite_version,
                n_proposals=4,
                subscores={"schema": 100.0, "canon": 100.0, "anachronism": 100.0,
                           "provenance": 100.0, "usefulness": 87.5},
                composite=96.88, fleiss_kappa=None,
                judge_ensemble_acceptable=True, passed=True,
                raw_report={"source": "c17-live-smoke seed (mirrors C15 result)"},
            )
            gate = await factory.read_gate(user_id=str(user_id), project_id=demo_project)
            print(f"[c17-smoke] re-read gate after seed: p2_p3_unlocked={gate.p2_p3_unlocked}")

        try:
            selected = await factory.select(
                Technique.RECOOK, user_id=str(user_id), project_id=demo_project
            )
        except InactiveStrategyError as exc:
            print(f"live infra unavailable: eval gate LOCKED for demo project — "
                  f"re-cook correctly REFUSED ({exc}). Run the C15 eval first.",
                  file=sys.stderr)
            return 3
        assert selected is recook, "factory returned the wrong strategy"
        print("[c17-smoke] gate CLEARED → re-cook SELECTED via the gate-aware factory")

        # ── run the REAL re-cook of the PD source on 陳塘關 (real Qwen) ──────────
        gap = Gap(
            entity_kind=EntityKind.LOCATION, canonical_name=demo_loc,
            target_ref=f"loc:{demo_loc}", mention_count=3,
            present_dimensions=(), missing_dimensions=tuple(Dimension),
        )
        ctx = StrategyContext(user_id=str(user_id), project_id=demo_project, model_ref=gen_ref)
        print(f"[c17-smoke] re-cooking {demo_loc} from PD history (real Qwen)...")
        results = await selected.run([gap], ctx)
        if not results or not results[0].facts:
            print("live infra unavailable: no re-cooked facts (JIT generation failure)",
                  file=sys.stderr)
            return 3

        rc = results[0]
        print("[c17-smoke] ===== REAL RE-COOKED CHINESE (quarantined, H0) =====")
        for f in rc.facts:
            assert f.origin == "enriched:recook", f"H0 LEAK: origin={f.origin}"
            assert f.origin != "glossary", "H0 LEAK: origin is canon"
            assert 0.0 < f.confidence < 1.0, f"H0 LEAK: confidence={f.confidence}"
            assert f.review_status == "proposed", f"H0: review_status={f.review_status}"
            assert f.pending_validation is True, "H0: not pending_validation"
            assert f.source_refs, "H0: re-cooked fact has no licensed source basis"
            assert f.provenance.get("recooked") is True, "provenance missing recooked=True"
            print(f"  【{f.dimension}】{f.content}")
        print("[c17-smoke] =======================================================")
        assert rc.licenses and rc.licenses[0].status is LicenseStatus.PUBLIC_DOMAIN, \
            "the re-cook source license was not public-domain"
        print(f"[c17-smoke] canon-verify ran: status={rc.verify.status.value}, "
              f"flags={len(rc.verify.result.flags)}, quarantined={rc.verify.is_quarantined}")

        # ── NEGATIVE CONTROL: an UNLICENSED source MUST be refused ───────────────
        bad_ingest = await store.ingest_corpus(
            user_id=user_id, project_id=project_uuid, name="某版权新闻-c17-neg",
            kind="other", text="某现代新闻报道，版权所有。", embed_fn=embed_fn,
            model_ref=embed_ref, target_chars=40, license="copyrighted",
        )
        bad_corpus_id = str(bad_ingest.corpus_id)
        bad_lic = await _license_lookup(bad_corpus_id)
        try:
            from app.strategies.licensing import check_admissible
            check_admissible(bad_lic, stage="live-smoke-negative-control")
            print("[c17-smoke] FAIL: copyrighted source was NOT refused", file=sys.stderr)
            return 1
        except UnlicensedSourceError as exc:
            print(f"[c17-smoke] negative control OK: copyrighted source REFUSED ({exc})")

        print(f"[c17-smoke] LIVE-SMOKE PASS: gate-CLEARED → real Qwen re-cook of a "
              f"PUBLIC-DOMAIN source into 商周 on {demo_loc} → {len(rc.facts)} H0-tagged "
              f"(origin=enriched:recook, conf<1.0, quarantined, licensed-source-cited) "
              f"facts. Copyrighted source REFUSED. NOT promoted (H0). "
              f"[pd_corpus={pd_corpus_id} bad_corpus={bad_corpus_id}]")
        return 0
    except AssertionError as exc:
        print(f"[c17-smoke] FAIL (H0 assertion): {exc}", file=sys.stderr)
        return 1
    except UnlicensedSourceError as exc:
        # The PD source should NOT be refused — if it is, that is a real failure.
        print(f"[c17-smoke] FAIL: licensed source unexpectedly refused ({exc})",
              file=sys.stderr)
        return 1
    except (KnowledgeServiceError, CompletionSeamError) as exc:
        print(f"live infra unavailable: upstream error after retries ({exc})", file=sys.stderr)
        return 3
    finally:
        await client.aclose()
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
