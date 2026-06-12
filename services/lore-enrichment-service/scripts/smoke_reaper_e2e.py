"""Live E2E for the worker reaper (D-COMPOSE-S3-UPLOAD-REAPER + CONTEXT-CORPUS-SCOPE).

Runs INSIDE the lore-enrichment-worker (or -service) container — it uses the
container's settings/env (DB + MinIO). Seeds the three reaper scenarios against the
REAL Postgres + MinIO, runs each sweep, asserts, and cleans up:

  1. an upload stuck in 'processing' past the stale window → flipped to 'failed';
  2. a compose-ephemeral corpus past the TTL → reaped (chunks cascade);
  3. a row-less MinIO object → deleted (grace_s=0 so the fresh test object is eligible).

Usage (host):
  docker cp services/lore-enrichment-service/scripts/smoke_reaper_e2e.py \
      infra-lore-enrichment-worker-1:/app/smoke_reaper_e2e.py
  docker exec infra-lore-enrichment-worker-1 python /app/smoke_reaper_e2e.py
"""

from __future__ import annotations

import asyncio
import io
import uuid

from app.config import settings
from app.db.pool import close_pool, create_pool
from app.storage import minio_client
from app.worker import reaper


async def main() -> int:
    pool = await create_pool(settings.database_url)
    uid, bid, pid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    up_id, cid = uuid.uuid4(), uuid.uuid4()
    okey = f"{uid}/{bid}/{uuid.uuid4()}.txt"
    ok = False
    try:
        async with pool.acquire() as c:
            # 1. stale 'processing' upload (created 3h ago > the 2h default window)
            await c.execute(
                """INSERT INTO enrichment_upload
                   (upload_id,user_id,book_id,project_id,filename,mime,status,created_at,updated_at)
                   VALUES ($1,$2,$3,$4,'reaper-smoke.pdf','application/pdf','processing',
                           now()-interval '3 hours', now()-interval '3 hours')""",
                up_id, uid, bid, pid,
            )
            # 2. compose-ephemeral corpus past the TTL (40 days old)
            await c.execute(
                """INSERT INTO source_corpus
                   (corpus_id,project_id,user_id,name,kind,license,provenance_json,created_at,updated_at)
                   VALUES ($1,$2,$3,'reaper-smoke-eph','other','public_domain',
                           '{"compose_ephemeral": true, "source": "compose"}'::jsonb,
                           now()-interval '40 days', now())""",
                cid, pid, uid,
            )
        # 3. a row-less orphan object
        await minio_client.ensure_bucket()
        await minio_client.upload_file(okey, io.BytesIO(b"orphan bytes"), "text/plain")

        n_stale = await reaper.sweep_stale_uploads(pool, max_age_s=settings.upload_stale_processing_s)
        n_eph = await reaper.sweep_ephemeral_corpora(pool, ttl_s=settings.context_corpus_ttl_s)
        n_orph = await reaper.sweep_orphan_objects(pool, grace_s=0.0)  # grace 0 → fresh test orphan eligible

        async with pool.acquire() as c:
            up_status = await c.fetchval("SELECT status FROM enrichment_upload WHERE upload_id=$1", up_id)
            eph_left = await c.fetchval("SELECT count(*) FROM source_corpus WHERE corpus_id=$1", cid)
        orphan_left = any(o.key == okey for o in await minio_client.list_objects())

        print(f"1. stale_uploads: failed={n_stale}, this row status={up_status!r}")
        print(f"2. ephemeral_corpora: reaped={n_eph}, this corpus rows_left={eph_left}")
        print(f"3. orphan_objects: deleted>={n_orph}, this object_left={orphan_left}")
        ok = up_status == "failed" and eph_left == 0 and not orphan_left
    finally:
        # cleanup (the corpus + orphan are gone if the sweeps worked; drop the upload row)
        async with pool.acquire() as c:
            await c.execute("DELETE FROM enrichment_upload WHERE upload_id=$1", up_id)
            await c.execute("DELETE FROM source_corpus WHERE corpus_id=$1", cid)
        try:
            await minio_client.delete_object(okey)
        except Exception:  # noqa: BLE001 — already deleted by the sweep (expected)
            pass
        await close_pool()

    print("SMOKE OK — all three reaper sweeps fired against real PG + MinIO." if ok
          else "SMOKE FAIL — see the per-sweep lines above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
