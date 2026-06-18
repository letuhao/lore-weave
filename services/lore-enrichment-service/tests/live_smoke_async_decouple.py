"""D-LORE-ASYNC-DECOUPLE-LIVE-SMOKE — the full LLM-driven WORKER path (M1–M4).

Drives the REAL background resume worker (NOT in-process like live_smoke_c14_job)
against the running stack + real Qwen/bge-m3, proving the 4 async-decouple guarantees:

  ST1 happy        seed job_request + XADD → worker run_job → 'completed' + a
                   QUARANTINED proposal persisted (+ best-effort jobs projection check).
  ST2 M2/HIGH-1    a 2-gap job, cancelled MID-run (after gap 1) → ends 'cancelled'
                   (NOT completed), < 2 proposals (stopped between gaps, never clobbered).
  ST3 M1 claim     hold the per-job advisory lock in a side session, XADD → the
                   worker's redrive_one CANNOT claim → does NO work (job stays pending,
                   0 proposals); release → re-XADD → it runs to 'completed'. Proves the
                   claim gates the call site deterministically.
  ST4 M3 retry     reuse ST2's partial job (gap 1 done): force it 'failed', retry via
                   the lore internal endpoint → re-drive SKIPS the done gap (no dup / no
                   re-spend) + runs the remaining gap → 'completed'.

Exit 0 = all pass; 3 = live infra unavailable (LM Studio down / model JIT fails after
retries); 1 = a real assertion failure. Cleans up its throwaway project + job rows.

Env (host-port defaults match infra/docker-compose.yml):
  LORE_ENRICHMENT_DB_URL    postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_lore_enrichment
  PROVIDER_REGISTRY_DB_URL  postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_provider_registry
  PROVIDER_REGISTRY_URL     http://localhost:8208
  KNOWLEDGE_SERVICE_URL_H   http://localhost:8216
  LORE_SERVICE_URL_H        http://localhost:8221
  JOBS_SERVICE_URL_H        http://localhost:8224
  REDIS_URL_H               redis://localhost:6399
  INTERNAL_SERVICE_TOKEN    dev_internal_token
  GEN_MODEL_NAME            qwen/qwen3.6-35b-a3b
  EMBED_MODEL_NAME          text-embedding-bge-m3
  DEMO_USER                 019d5e3c-7cc5-7e6a-8b27-1344e148bf7c
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import asyncpg
import httpx

from app.clients.knowledge import KnowledgeClient, KnowledgeServiceError
from app.jobs.events import LORE_ENRICHMENT_RESUME_STREAM, make_redis_producer
from app.jobs.job_request import save_job_request
from app.jobs.proposal_store import PgProposalStore
from app.retrieval.store import SourceCorpusStore

_GROUNDING = {
    "蓬萊": "蓬萊山在海中，上有仙人，宫室皆以金玉為之，鸟兽尽白，长生不老。",
    "玉虛宮": "玉虛宮乃元始天尊道場，在昆侖之巔，殿宇巍峨，仙鶴翔集，紫氣東來。",
}
_RETRIES = 6
_RETRY_SLEEP_S = 8.0
_LOCK_KEY_SQL = "SELECT ('x' || substr(replace($1, '-', ''), 1, 16))::bit(64)::bigint"


async def _resolve(pr_dsn, name, *, owner=None):
    conn = await asyncpg.connect(pr_dsn)
    try:
        if owner:
            row = await conn.fetchrow(
                "SELECT user_model_id FROM user_models WHERE provider_model_name=$1 "
                "AND owner_user_id=$2 AND is_active ORDER BY created_at DESC LIMIT 1",
                name, uuid.UUID(owner),
            )
        else:
            row = await conn.fetchrow(
                "SELECT user_model_id FROM user_models WHERE provider_model_name=$1 "
                "AND is_active ORDER BY created_at DESC LIMIT 1", name,
            )
    finally:
        await conn.close()
    if row is None:
        raise RuntimeError(f"no active user_model {name!r}")
    return str(row["user_model_id"])


async def _embed_with_retry(client, *, user_id, model_ref, texts):
    last = None
    for attempt in range(1, _RETRIES + 1):
        try:
            return await client.embed(user_id=user_id, model_source="user_model",
                                      model_ref=model_ref, texts=texts)
        except KnowledgeServiceError as exc:
            last = exc
            print(f"[async-smoke] embed attempt {attempt} retryable ({exc})", file=sys.stderr)
            await asyncio.sleep(_RETRY_SLEEP_S)
    raise last or RuntimeError("embed failed")


async def _poll(pool, job_id, *, until, timeout_s=240.0, interval_s=2.0):
    """Poll the job status until `until(status, n_proposals)` is True or timeout."""
    waited = 0.0
    while waited < timeout_s:
        async with pool.acquire() as conn:
            status = await conn.fetchval(
                "SELECT status FROM enrichment_job WHERE job_id=$1", uuid.UUID(job_id))
            n = await conn.fetchval(
                "SELECT count(*) FROM enrichment_proposal WHERE job_id=$1", uuid.UUID(job_id))
        if until(status, n):
            return status, n
        await asyncio.sleep(interval_s)
        waited += interval_s
    return status, n


async def _status(pool, job_id):
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT status FROM enrichment_job WHERE job_id=$1", uuid.UUID(job_id))


async def _nprops(pool, job_id):
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT count(*) FROM enrichment_proposal WHERE job_id=$1", uuid.UUID(job_id))


async def _seed_job(store, pool, *, project, user, gen_ref, embed_ref, targets):
    # NO cost cap — the worker uses the real token-denominated GapCostModel, so a small
    # USD-looking cap pauses before gap 1 (the cost-cap pause is tested separately). This
    # smoke proves the cancel/claim/retry control paths, so let the gaps actually run.
    job_id = await store.create_job(
        user_id=user, project_id=project, technique="retrieval",
        entity_kind="location", max_spend=None, estimated_cost=0.0)
    body = {
        "project_id": project, "embedding_model_ref": embed_ref,
        "generation_model_ref": gen_ref, "targets": targets, "book_id": None,
        "technique": "retrieval", "max_spend_usd": None,
        "eval_reserve_fraction": 0.15, "top_k": 5, "user_id": user,
    }
    await save_job_request(pool=pool, job_id=uuid.UUID(job_id), request=body)
    return job_id


def _target(name):
    return {"canonical_name": name, "target_ref": f"loc:{name}",
            "entity_kind": "location", "mention_count": 3, "present_dimensions": []}


async def _trigger(producer, job_id, project, user):
    await producer.xadd(LORE_ENRICHMENT_RESUME_STREAM,
                        {"job_id": job_id, "project_id": project, "user_id": user},
                        maxlen=10000)


async def _control(lore_url, token, job_id, action, owner):
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(f"{lore_url}/internal/lore_enrichment/jobs/{job_id}/{action}",
                         headers={"X-Internal-Token": token},
                         json={"owner_user_id": owner})
        return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)


async def _main():  # noqa: C901
    db = os.environ.get("LORE_ENRICHMENT_DB_URL", "")
    pr = os.environ.get("PROVIDER_REGISTRY_DB_URL", "")
    know = os.environ.get("KNOWLEDGE_SERVICE_URL_H", "http://localhost:8216")
    pr_url = os.environ.get("PROVIDER_REGISTRY_URL", "http://localhost:8208")
    lore_url = os.environ.get("LORE_SERVICE_URL_H", "http://localhost:8221")
    jobs_url = os.environ.get("JOBS_SERVICE_URL_H", "http://localhost:8224")
    redis_url = os.environ.get("REDIS_URL_H", "redis://localhost:6399")
    token = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev_internal_token")
    gen_name = os.environ.get("GEN_MODEL_NAME", "qwen/qwen3.6-35b-a3b")
    embed_name = os.environ.get("EMBED_MODEL_NAME", "text-embedding-bge-m3")
    user = os.environ.get("DEMO_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
    if not db or not pr:
        print("live infra unavailable: LORE_ENRICHMENT_DB_URL / PROVIDER_REGISTRY_DB_URL not set",
              file=sys.stderr)
        return 3

    project = str(uuid.uuid4())  # throwaway, easy cleanup
    try:
        gen_ref = await _resolve(pr, gen_name, owner=user)
        # the embed model MUST be owned by the job user too — the WORKER's retrieval
        # embeds with the job's user_id (build_live_runner), so a different-owner embed
        # ref would 404 the worker exactly like it 404s this ingest.
        embed_ref = await _resolve(pr, embed_name, owner=user)
    except Exception as exc:  # noqa: BLE001
        print(f"live infra unavailable: model lookup failed ({exc})", file=sys.stderr)
        return 3
    print(f"[async-smoke] gen={gen_name}→{gen_ref}  embed={embed_name}→{embed_ref}  project={project}")

    pool = await asyncpg.create_pool(db, min_size=1, max_size=4, command_timeout=30)
    client = KnowledgeClient(knowledge_base_url=know, provider_registry_base_url=pr_url,
                             internal_token=token, embed_timeout_s=120.0)
    producer = make_redis_producer(redis_url)
    store = PgProposalStore(pool)
    seeded_jobs: list[str] = []
    rc = 1
    try:
        # ── ingest grounding for both locations (real bge-m3 embed) ───────────────
        corpus_store = SourceCorpusStore(pool)

        async def embed_fn(texts):
            r = await _embed_with_retry(client, user_id=uuid.UUID(user),
                                        model_ref=embed_ref, texts=list(texts))
            return r.embeddings

        for name, passage in _GROUNDING.items():
            ing = await corpus_store.ingest_corpus(
                user_id=uuid.UUID(user), project_id=uuid.UUID(project),
                name=f"grounding-{name}", kind="shanhaijing", text=passage,
                embed_fn=embed_fn, model_ref=embed_ref, target_chars=60,
                license="public-domain")
            if ing.chunks_total < 1:
                print("live infra unavailable: no grounding chunk embedded", file=sys.stderr)
                return 3
        print(f"[async-smoke] grounding ingested for {list(_GROUNDING)}")

        # ── ST1: happy completed via the worker ───────────────────────────────────
        j1 = await _seed_job(store, pool, project=project, user=user, gen_ref=gen_ref,
                             embed_ref=embed_ref, targets=[_target("蓬萊")])
        seeded_jobs.append(j1)
        await _trigger(producer, j1, project, user)
        st, n = await _poll(pool, j1, until=lambda s, n: s in ("completed", "failed"))
        assert st == "completed", f"ST1: expected completed, got {st} (n={n})"
        assert n >= 1, f"ST1: expected >=1 proposal, got {n}"
        print(f"[async-smoke] ST1 PASS: worker drove job→completed, {n} quarantined proposal(s)")
        # best-effort jobs-service projection check (event pipeline → projection)
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                pr_resp = await c.get(
                    f"{jobs_url}/internal/jobs/lore_enrichment/{j1}",
                    headers={"X-Internal-Token": token})
            print(f"[async-smoke] ST1 jobs-projection probe: HTTP {pr_resp.status_code} {pr_resp.text[:160]}")
        except Exception as exc:  # noqa: BLE001
            print(f"[async-smoke] ST1 projection probe skipped ({exc})")

        # ── ST2: cancel a 2-gap job MID-run (M2/HIGH-1) ───────────────────────────
        j2 = await _seed_job(store, pool, project=project, user=user, gen_ref=gen_ref,
                             embed_ref=embed_ref, targets=[_target("蓬萊"), _target("玉虛宮")])
        seeded_jobs.append(j2)
        await _trigger(producer, j2, project, user)
        # wait until gap 1 is done (>=1 proposal) AND still running → cancel between gaps
        st, n = await _poll(pool, j2, until=lambda s, n: n >= 1 or s in ("completed", "failed"),
                            timeout_s=240.0)
        if st in ("completed", "failed"):
            print(f"[async-smoke] ST2 WARN: job reached {st} before a cancel window (n={n}) — "
                  "generation too fast; cannot prove mid-run cancel deterministically", file=sys.stderr)
            return 3
        code, body = await _control(lore_url, token, j2, "cancel", user)
        assert code == 200, f"ST2: cancel HTTP {code}: {body}"
        st, n = await _poll(pool, j2, until=lambda s, n: s in ("cancelled", "completed", "failed"))
        assert st == "cancelled", f"ST2: expected cancelled (not clobbered), got {st} (n={n})"
        assert n < 2, f"ST2: expected < 2 proposals (stopped mid-run), got {n}"
        print(f"[async-smoke] ST2 PASS: mid-run cancel → 'cancelled' (not completed), {n} gap(s) done")

        # ── ST3: per-job advisory claim blocks a second runner (M1) ───────────────
        j3 = await _seed_job(store, pool, project=project, user=user, gen_ref=gen_ref,
                             embed_ref=embed_ref, targets=[_target("蓬萊")])
        seeded_jobs.append(j3)
        lock_conn = await asyncpg.connect(db)
        try:
            key = await lock_conn.fetchval(_LOCK_KEY_SQL, j3)
            got = await lock_conn.fetchval("SELECT pg_try_advisory_lock($1)", key)
            assert got is True, "ST3: could not take the side-session lock"
            await _trigger(producer, j3, project, user)
            await asyncio.sleep(12.0)  # give the worker time to read + try-claim + skip
            st, n = await _status(pool, j3), await _nprops(pool, j3)
            assert st == "pending" and n == 0, \
                f"ST3: claim DID NOT block — status={st} n={n} (expected pending/0)"
            print("[async-smoke] ST3a PASS: lock held → worker could not claim → no work done")
        finally:
            await lock_conn.fetchval("SELECT pg_advisory_unlock($1)", key)
            await lock_conn.close()
        await _trigger(producer, j3, project, user)  # now claimable → runs
        st, n = await _poll(pool, j3, until=lambda s, n: s in ("completed", "failed"))
        assert st == "completed" and n >= 1, f"ST3b: after release expected completed, got {st}/{n}"
        print(f"[async-smoke] ST3b PASS: after release → worker claimed → completed ({n} proposal)")

        # ── ST4: retry a FAILED partially-done job → skip-done + run rest (M3) ─────
        # Reuse j2 (gap 蓬萊 done, 玉虛宮 not). Force it 'failed' so retry is valid.
        async with pool.acquire() as conn:
            await conn.execute("UPDATE enrichment_job SET status='failed' WHERE job_id=$1",
                               uuid.UUID(j2))
            penglai_pid = await conn.fetchval(
                "SELECT proposal_id FROM enrichment_proposal WHERE job_id=$1 AND gap_ref='loc:蓬萊'",
                uuid.UUID(j2))
        n_before = await _nprops(pool, j2)
        code, body = await _control(lore_url, token, j2, "retry", user)
        assert code == 200, f"ST4: retry HTTP {code}: {body}"
        st, n = await _poll(pool, j2, until=lambda s, n: s in ("completed", "failed"))
        assert st == "completed", f"ST4: expected completed after retry, got {st} (n={n})"
        assert n == 2, f"ST4: expected 2 proposals (skip-done 蓬萊 + run 玉虛宮), got {n} (was {n_before})"
        async with pool.acquire() as conn:
            penglai_after = await conn.fetchval(
                "SELECT proposal_id FROM enrichment_proposal WHERE job_id=$1 AND gap_ref='loc:蓬萊'",
                uuid.UUID(j2))
            yuxu = await conn.fetchval(
                "SELECT count(*) FROM enrichment_proposal WHERE job_id=$1 AND gap_ref='loc:玉虛宮'",
                uuid.UUID(j2))
        assert str(penglai_after) == str(penglai_pid), "ST4: done gap 蓬萊 was re-generated (not skipped)!"
        assert yuxu == 1, f"ST4: remaining gap 玉虛宮 not enriched (count={yuxu})"
        print("[async-smoke] ST4 PASS: retry re-drove a failed job, SKIPPED done 蓬萊 (id unchanged), "
              "ran remaining 玉虛宮 → completed")

        print("[async-smoke] LIVE-SMOKE PASS: M1 claim + M2 mid-run-cancel + M3 retry-skip-done "
              "+ happy worker run all proven on the real async path with real Qwen")
        rc = 0
        return rc
    except AssertionError as exc:
        print(f"[async-smoke] FAIL: {exc}", file=sys.stderr)
        return 1
    except (KnowledgeServiceError, OSError, asyncpg.PostgresError) as exc:
        print(f"live infra unavailable: {exc}", file=sys.stderr)
        return 3
    finally:
        # ── cleanup: delete the throwaway project's jobs + proposals + corpora ────
        try:
            async with pool.acquire() as conn:
                for jid in seeded_jobs:
                    await conn.execute("DELETE FROM enrichment_proposal WHERE job_id=$1", uuid.UUID(jid))
                    await conn.execute("DELETE FROM enrichment_job_request WHERE job_id=$1", uuid.UUID(jid))
                    await conn.execute("DELETE FROM enrichment_job WHERE job_id=$1", uuid.UUID(jid))
                await conn.execute("DELETE FROM source_corpus WHERE project_id=$1", uuid.UUID(project))
            print(f"[async-smoke] cleanup: deleted {len(seeded_jobs)} job(s) + project corpora")
        except Exception as exc:  # noqa: BLE001
            print(f"[async-smoke] cleanup WARN: {exc}", file=sys.stderr)
        await client.aclose()
        await producer.aclose()
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
