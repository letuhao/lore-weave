import time
import asyncpg
import httpx
from uuid import UUID

from ..auth import mint_user_jwt
from ..config import settings


async def run_translation_job(job_id: UUID, user_id: str, pool: asyncpg.Pool) -> None:
    async with pool.acquire() as db:
        # Mark job running
        await db.execute(
            "UPDATE translation_jobs SET status='running', started_at=now() WHERE job_id=$1",
            job_id,
        )

        job = await db.fetchrow("SELECT * FROM translation_jobs WHERE job_id=$1", job_id)
        if not job:
            return

        # Mint JWT
        token = mint_user_jwt(user_id, settings.jwt_secret, ttl_seconds=300)
        token_exp = time.time() + 300

        async with httpx.AsyncClient(timeout=60) as client:
            for chapter_id in job["chapter_ids"]:
                # Check for cancellation before each chapter
                current_status = await db.fetchval(
                    "SELECT status FROM translation_jobs WHERE job_id=$1", job_id
                )
                if current_status == "cancelled":
                    return

                await db.execute(
                    """UPDATE chapter_translations
                       SET status='running', started_at=now()
                       WHERE job_id=$1 AND chapter_id=$2""",
                    job_id, chapter_id,
                )

                # Fetch chapter from book-service
                try:
                    r = await client.get(
                        f"{settings.book_service_internal_url}/internal/books/{job['book_id']}/chapters/{chapter_id}"
                    )
                except httpx.RequestError as e:
                    await _mark_chapter_failed(db, job_id, chapter_id, "network_error")
                    continue

                if r.status_code == 404:
                    await _mark_chapter_failed(db, job_id, chapter_id, "chapter_not_found")
                    continue
                if not r.is_success:
                    await _mark_chapter_failed(db, job_id, chapter_id, f"book_service_error_{r.status_code}")
                    continue

                chapter = r.json()
                source_language = chapter.get("original_language") or "unknown"
                user_msg = job["user_prompt_tpl"].format_map({
                    "source_language": source_language,
                    "target_language": job["target_language"],
                    "chapter_text": chapter.get("body") or "",
                })

                # Refresh JWT if expiring soon
                if time.time() > token_exp - 30:
                    token = mint_user_jwt(user_id, settings.jwt_secret, ttl_seconds=300)
                    token_exp = time.time() + 300

                # Invoke provider
                try:
                    r = await client.post(
                        f"{settings.provider_registry_service_url}/v1/model-registry/invoke",
                        json={
                            "model_source": job["model_source"],
                            "model_ref": str(job["model_ref"]),
                            "input": {
                                "messages": [
                                    {"role": "system", "content": job["system_prompt"]},
                                    {"role": "user", "content": user_msg},
                                ]
                            },
                        },
                        headers={"Authorization": f"Bearer {token}"},
                    )
                except httpx.TimeoutException:
                    await _mark_chapter_failed(db, job_id, chapter_id, "provider_timeout")
                    continue
                except httpx.RequestError:
                    await _mark_chapter_failed(db, job_id, chapter_id, "network_error")
                    continue

                if r.status_code == 402:
                    await _mark_chapter_failed(db, job_id, chapter_id, "billing_rejected")
                    continue
                if r.status_code >= 500:
                    await _mark_chapter_failed(db, job_id, chapter_id, "provider_error")
                    continue
                if not r.is_success:
                    await _mark_chapter_failed(db, job_id, chapter_id, f"invoke_error_{r.status_code}")
                    continue

                resp = r.json()
                translated_body = resp["output"]["content"]
                usage_log_id = resp.get("usage_log_id")
                usage = resp.get("usage") or {}
                input_tokens = usage.get("input_tokens")
                output_tokens = usage.get("output_tokens")

                await db.execute(
                    """UPDATE chapter_translations SET
                         status='completed',
                         translated_body=$1,
                         source_language=$2,
                         input_tokens=$3,
                         output_tokens=$4,
                         usage_log_id=$5,
                         finished_at=now()
                       WHERE job_id=$6 AND chapter_id=$7""",
                    translated_body,
                    source_language,
                    input_tokens,
                    output_tokens,
                    UUID(usage_log_id) if usage_log_id else None,
                    job_id,
                    chapter_id,
                )
                await db.execute(
                    "UPDATE translation_jobs SET completed_chapters=completed_chapters+1 WHERE job_id=$1",
                    job_id,
                )

        # Determine final status
        final = await db.fetchrow(
            "SELECT status, total_chapters, completed_chapters, failed_chapters FROM translation_jobs WHERE job_id=$1",
            job_id,
        )
        if final["status"] == "cancelled":
            return

        if final["failed_chapters"] == 0:
            final_status = "completed"
        elif final["completed_chapters"] > 0:
            final_status = "partial"
        else:
            final_status = "failed"

        await db.execute(
            "UPDATE translation_jobs SET status=$1, finished_at=now() WHERE job_id=$2",
            final_status, job_id,
        )


async def _mark_chapter_failed(db, job_id: UUID, chapter_id: UUID, reason: str) -> None:
    await db.execute(
        """UPDATE chapter_translations SET
             status='failed', error_message=$1, finished_at=now()
           WHERE job_id=$2 AND chapter_id=$3""",
        reason, job_id, chapter_id,
    )
    await db.execute(
        "UPDATE translation_jobs SET failed_chapters=failed_chapters+1 WHERE job_id=$1",
        job_id,
    )
