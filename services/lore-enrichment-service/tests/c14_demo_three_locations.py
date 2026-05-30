"""C14 P1 enrichment demo — THREE seeded Fengshen locations, persist-each-before-next.

Reuses the SAME working pipeline + config as the prior 蓬萊 live-smoke
(``live_smoke_c14_job.py``): resolve model refs by NAME at runtime → ingest one
grounding chunk into the demo project's source_corpus → run the REAL P1 JobRunner
(retrieval C10 → real Qwen generation C11 → canon-verify C12 → persist a
QUARANTINED, H0-tagged Chinese proposal). Promotion is OPTIONAL and is NOT done
here (the task says promote is optional; persistence + durability read-back is
the requirement).

Order (each PERSISTED + READ-BACK before the next so partial progress survives a
transient error):  玉虛宮 → 陳塘關 → 碧遊宮/金鰲島

For each location:
  1. ingest its public-domain grounding passage (REAL /internal/embed, JIT retry)
  2. run the real JobRunner for that location's gap (5 Chinese dims via real Qwen)
  3. persist a quarantined proposal (origin='enrichment', conf<1.0, technique=retrieval)
  4. IMMEDIATELY query the persisted row back to confirm durability

Emits a single JSON result block to stdout (between RESULT_BEGIN/RESULT_END
markers) so the caller can parse it. Per-location failure is captured with a
reason; Qwen JIT load failure after retries → that location reports
``live infra unavailable``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

import asyncpg

from app.clients.knowledge import KnowledgeClient, KnowledgeServiceError
from app.clients.port import KnowledgeReadHttp
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
from app.services.review import ProposalsRepo
from app.strategies.base import StrategyContext, Technique
from app.strategies.template import TemplateStrategy
from app.verify.canon_verify import CanonFact, CanonVerifier

_RETRIES = 6
_RETRY_SLEEP_S = 8.0

# ── grounding passages (all PUBLIC DOMAIN) ──────────────────────────────────────
# 玉虛宮 — 闡教 HQ on 昆侖山. Ground with the canonical 山海经 西山经 昆侖之丘 passage
# (rich geography: 帝之下都, 河/赤/洋/黑水出焉; features: 沙棠/薲草/土螻/欽原; inhabitant: 神陸吾).
_GROUND_YUXU = (
    "西南四百里，曰昆侖之丘，是實惟帝之下都，神陸吾司之。其神狀虎身而九尾，"
    "人面而虎爪；是神也，司天之九部及帝之囿時。有獸焉，其狀如羊而四角，名曰土螻，"
    "是食人。有鳥焉，其狀如蠭，大如鴛鴦，名曰欽原，蠚鳥獸則死，蠚木則枯。"
    "有木焉，其狀如棠，黃華赤實，其味如李而無核，名曰沙棠，可以禦水，食之使人不溺。"
    "有草焉，名曰薲草，其狀如葵，其味如蔥，食之已勞。"
    "河水出焉，而南流注于無達。赤水出焉，而東南流注于氾天之水。"
    "洋水出焉，而西南流注于醜塗之水。黑水出焉，而西流于大杅。是多怪鳥獸。"
)

# 陳塘關 — Nezha's frontier pass, 封神演义-specific (NOT in 山海经). Ground with the
# 封神演义 回12 opening that establishes the pass: 李靖 as 總兵 governs it, 殷夫人, three sons.
_GROUND_CHENTANG = (
    "話說陳塘關有一總兵官，姓李，名靖，自幼訪道修真，拜西崑崙度厄真人為師，"
    "學成五行遁術。因仙道難成，故遣下山輔佐紂王，官居總兵，享受人間之富貴。"
    "元配殷氏，生有二子：長曰金吒，次曰木吒。殷夫人後又懷孕在身，已及三年零六個月。"
    "李靖在關上無事，忽聞報天下反了四百諸侯。忙傳令出，把守關隘，操演三軍，"
    "訓練士卒，謹提防野馬嶺要地。哪吒同家將出得關來，約行一里之餘，"
    "猛忽的見那壁廂清波滾滾，綠水滔滔，不知這河是九灣河，是東海口上。"
)

# 碧遊宮/金鰲島 — 截教 HQ, 封神演义-specific. Ground with the 金鰲島 description (回42):
# 東海 island, 青山幽靜, 截教 immortals'洞府. 碧遊宮 (inner palace of 通天教主) is only
# named in passing in canon → expect honest-sparse on the inner-palace dims.
_GROUND_BIYOU = (
    "話說聞太師的墨麒麟週遊天下，霎時可至千里；其日行到東海金鰲島。"
    "太師觀看大海，青山幽靜。真個好海島，有無窮奇景："
    "勢鎮汪洋，威寧搖海。潮湧銀山魚入穴，波翻雪浪蜃離淵。丹岩怪石，峭壁奇峰。"
    "瑤草奇花不謝；青松翠柏長春。仙桃常結果，修竹每留雲。"
    "正是：百川會處擎天柱，萬劫無移大地根。聞太師到了金鰲島，下了墨麒麟，"
    "看了一回，各處洞門緊閉，並無一人。金鰲島眾道友往白鹿島去練陣圖，皆截教門人。"
    "碧遊宮內聖人傳，乃截教通天教主說法之所。"
)

# (name, target_ref, corpus_name, corpus_kind, grounding_text)
_LOCATIONS = [
    ("玉虛宮", "loc:玉虛宮", "山海经-昆侖之丘-c14-demo", "shanhaijing", _GROUND_YUXU),
    ("陳塘關", "loc:陳塘關", "封神演义-陳塘關-c14-demo", "fengshen", _GROUND_CHENTANG),
    ("碧遊宮/金鰲島", "loc:碧遊宮金鰲島", "封神演义-金鰲島-c14-demo", "fengshen", _GROUND_BIYOU),
]


async def _resolve_model_ref(pr_dsn, name, *, owner=None):
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
            print(f"[c14-demo] embed attempt {attempt}/{_RETRIES} retryable ({exc})",
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
                print(f"[c14-demo] gen attempt {attempt}/{_RETRIES} retryable ({exc}) "
                      f"— waiting {_RETRY_SLEEP_S}s for JIT load", file=sys.stderr)
                await asyncio.sleep(_RETRY_SLEEP_S)
        raise last if last else RuntimeError("generation failed")
    return _fn


async def _run_one_location(
    *, loc_name, target_ref, corpus_name, corpus_kind, grounding_text,
    pool, client, store, pr_url, token, redis_url,
    user_id, project_uuid, demo_project, embed_owner_uuid, embed_ref, gen_ref,
):
    """Ingest grounding → run REAL P1 job → persist quarantined proposal →
    read it back. Returns a result dict for the JSON block."""
    result = {"name": loc_name}

    async def embed_fn(texts):
        r = await _embed_with_retry(
            client, user_id=embed_owner_uuid, model_ref=embed_ref, texts=list(texts)
        )
        return r.embeddings

    # 1. ingest grounding chunk (REAL embed)
    ingest = await store.ingest_corpus(
        user_id=user_id, project_id=project_uuid, name=corpus_name,
        kind=corpus_kind, text=grounding_text, embed_fn=embed_fn,
        model_ref=embed_ref, target_chars=160,
    )
    if ingest.chunks_embedded < 1 and ingest.chunks_total < 1:
        result["error"] = "live infra unavailable: no grounding chunk embedded"
        return result
    print(f"[c14-demo] {loc_name}: ingested grounding {ingest.chunks_total} chunk(s), "
          f"{ingest.chunks_embedded} embedded")

    # 2. assemble the REAL runner
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

    async def _canon_lookup(entity, dim):
        return []

    verifier = CanonVerifier(read_port=read_port, canon_lookup=_canon_lookup)
    pipeline = GapPipeline(retrieval=retrieval, generator=generator, verifier=verifier)

    pg_store = PgProposalStore(pool)
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
        entity_kind=EntityKind.LOCATION, canonical_name=loc_name,
        target_ref=target_ref, mention_count=3,
        present_dimensions=(), missing_dimensions=tuple(Dimension),
    )
    ctx = StrategyContext(user_id=str(user_id), project_id=demo_project, model_ref=gen_ref)

    print(f"[c14-demo] {loc_name}: running REAL P1 job {job_id} (real Qwen)...")
    outcome = await runner.run_job(
        job_id=job_id, gaps=[gap], context=ctx, entity_kind="location"
    )

    if outcome.final_state != "completed":
        result["error"] = (f"live infra unavailable: job ended {outcome.final_state} "
                           f"(err={outcome.error}, skipped={outcome.skipped_gaps})")
        return result
    if not outcome.proposals:
        result["error"] = ("live infra unavailable: no proposal produced "
                           "(gap skipped — likely JIT generation failure)")
        return result

    p = outcome.proposals[0]
    # H0 invariants
    assert p.origin == "enrichment", f"H0 LEAK: origin={p.origin}"
    assert 0.0 < p.confidence < 1.0, f"H0 LEAK: confidence={p.confidence}"
    assert p.review_status == "proposed", f"H0: review_status={p.review_status}"
    assert p.pending_validation is True, "H0: not pending_validation"

    # 4. IMMEDIATELY read the persisted row back to confirm durability — fresh repo,
    # fresh fetch (not the in-memory outcome object).
    repo = ProposalsRepo(pool)
    row = await repo.get(user_id=user_id, project_id=project_uuid,
                         proposal_id=uuid.UUID(p.proposal_id))
    assert row is not None, "persisted proposal not found on read-back"
    dims = (row.provenance_json or {}).get("dimensions", {})
    assert dims, "no generated dimensions persisted"
    cosines = []
    for ref in (row.source_refs_json or []):
        if isinstance(ref, dict):
            # RetrievalStrategy stores the cosine under "score" (see C10).
            val = ref.get("score", ref.get("cosine"))
            if val is not None:
                cosines.append(float(val))

    def _trunc(s):
        s = str(s)
        return s[:400]

    result.update({
        "proposal_id": p.proposal_id,
        "confidence": float(row.confidence),
        "review_status": row.review_status,
        "n_grounding_refs": len(row.source_refs_json or []),
        "top_cosine": (round(max(cosines), 4) if cosines else None),
        "generated": {
            "历史": _trunc(dims.get("历史", "")),
            "地理": _trunc(dims.get("地理", "")),
            "文化": _trunc(dims.get("文化", "")),
            "features": _trunc(dims.get("features", "")),
            "inhabitants": _trunc(dims.get("inhabitants", "")),
        },
    })
    print(f"[c14-demo] {loc_name}: PERSISTED + READ-BACK ok — proposal {p.proposal_id} "
          f"(origin={row.origin}, conf={row.confidence}, {len(dims)} dims, "
          f"{len(row.source_refs_json or [])} grounding ref(s))")
    for label, value in dims.items():
        print(f"    【{label}】{value}")
    return result


async def _main():
    db_dsn = os.environ.get("LORE_ENRICHMENT_DB_URL", "")
    pr_dsn = os.environ.get("PROVIDER_REGISTRY_DB_URL", "")
    pr_url = os.environ.get("PROVIDER_REGISTRY_URL", "http://localhost:8208")
    know_url = os.environ.get("KNOWLEDGE_SERVICE_URL_H", "http://localhost:8216")
    redis_url = os.environ.get("REDIS_URL_H", "redis://localhost:6399")
    token = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev_internal_token")
    gen_name = os.environ.get("GEN_MODEL_NAME", "qwen/qwen3.6-35b-a3b")
    embed_name = os.environ.get("EMBED_MODEL_NAME", "text-embedding-bge-m3")

    demo_project = os.environ.get("DEMO_PROJECT", "019e7850-aa1c-7cd3-a25c-c2f9ad84fd39")
    demo_user = os.environ.get("DEMO_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")

    out = {"result": "FAILED", "gen_model": gen_name, "locations": [],
           "diversity_note": "", "notable": ""}

    if not db_dsn or not pr_dsn:
        out["notable"] = ("live infra unavailable: LORE_ENRICHMENT_DB_URL / "
                          "PROVIDER_REGISTRY_DB_URL not set")
        _emit(out)
        return 3

    try:
        embed_ref, embed_owner = await _resolve_model_ref(pr_dsn, embed_name)
        gen_ref, gen_owner = await _resolve_model_ref(pr_dsn, gen_name, owner=demo_user)
    except (OSError, asyncpg.PostgresError, RuntimeError) as exc:
        out["notable"] = f"live infra unavailable: model lookup failed ({exc})"
        _emit(out)
        return 3
    print(f"[c14-demo] resolved gen {gen_name!r}→{gen_ref} (owner {gen_owner}) "
          f"embed {embed_name!r}→{embed_ref} (owner {embed_owner})")

    user_id = uuid.UUID(demo_user)
    embed_owner_uuid = uuid.UUID(embed_owner)
    project_uuid = uuid.UUID(demo_project)

    try:
        pool = await asyncpg.create_pool(db_dsn, min_size=1, max_size=3, command_timeout=30)
    except (OSError, asyncpg.PostgresError) as exc:
        out["notable"] = f"live infra unavailable: lore DB unreachable ({exc})"
        _emit(out)
        return 3
    await run_migrations(pool)

    client = KnowledgeClient(
        knowledge_base_url=know_url, provider_registry_base_url=pr_url,
        internal_token=token, embed_timeout_s=120.0,
    )
    store = SourceCorpusStore(pool)

    # Optional subset filter (comma-separated location names) so a re-run can
    # resume only the locations that did not yet persist — earlier durable
    # progress is left untouched (no duplicate proposal).
    only = os.environ.get("DEMO_ONLY", "").strip()
    only_names = {s.strip() for s in only.split(",") if s.strip()} if only else None
    locations = [loc for loc in _LOCATIONS
                 if only_names is None or loc[0] in only_names]

    n_ok = 0
    try:
        for (loc_name, target_ref, corpus_name, corpus_kind, grounding_text) in locations:
            try:
                res = await _run_one_location(
                    loc_name=loc_name, target_ref=target_ref, corpus_name=corpus_name,
                    corpus_kind=corpus_kind, grounding_text=grounding_text,
                    pool=pool, client=client, store=store, pr_url=pr_url, token=token,
                    redis_url=redis_url, user_id=user_id, project_uuid=project_uuid,
                    demo_project=demo_project, embed_owner_uuid=embed_owner_uuid,
                    embed_ref=embed_ref, gen_ref=gen_ref,
                )
            except AssertionError as exc:
                res = {"name": loc_name, "error": f"H0/durability assertion failed: {exc}"}
            except (KnowledgeServiceError, CompletionSeamError) as exc:
                res = {"name": loc_name,
                       "error": f"live infra unavailable: upstream error after retries ({exc})"}
            except Exception as exc:  # noqa: BLE001 — capture per-location, keep going
                res = {"name": loc_name, "error": f"{type(exc).__name__}: {exc}"}
            out["locations"].append(res)
            if "error" not in res:
                n_ok += 1
            # progress already durable in Postgres before the next location starts.
    finally:
        await client.aclose()
        await pool.close()

    n_total = len(locations)
    if n_ok == n_total:
        out["result"] = "DONE"
    elif n_ok > 0:
        out["result"] = "PARTIAL"
    else:
        out["result"] = "FAILED"
    _emit(out)
    return 0 if n_ok == n_total else (2 if n_ok > 0 else 1)


def _emit(out):
    print("RESULT_BEGIN")
    print(json.dumps(out, ensure_ascii=False))
    print("RESULT_END")


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
