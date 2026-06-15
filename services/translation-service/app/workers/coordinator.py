import logging
from uuid import UUID

from loreweave_jobs import emit_job_event

log = logging.getLogger(__name__)

#: Unified Job Control Plane P1 — stamped on every emitted JobEvent.
_JOB_SERVICE = "translation"
_JOB_KIND = "translation"


async def handle_job_message(msg: dict, pool, publish, publish_event) -> None:
    """
    Fast fan-out worker: receives one job message, marks job running,
    publishes one chapter message per chapter, emits job.status_changed(running).
    Expected duration: < 1 second.
    """
    job_id  = UUID(msg["job_id"])
    user_id = msg["user_id"]
    n       = len(msg["chapter_ids"])
    log.info("coordinator: job %s — marking running, fanning out %d chapter(s)", job_id, n)

    async with pool.acquire() as db:
        async with db.transaction():
            # P1 — running transition. UPDATE + emit in one tx (H1). RETURNING the
            # owner so the event carries it (msg.user_id is the same value, but the
            # row is authoritative). Guarded: only emit when a row actually changed.
            row = await db.fetchrow(
                "UPDATE translation_jobs SET status='running', started_at=now() "
                "WHERE job_id=$1 RETURNING owner_user_id",
                job_id,
            )
            if row is not None:
                await emit_job_event(
                    db, service=_JOB_SERVICE, job_id=str(job_id),
                    owner_user_id=str(row["owner_user_id"]), kind=_JOB_KIND,
                    status="running",
                )

    # Routing key "translation.chapter" must match the binding in broker.connect_broker()
    for index, chapter_id in enumerate(msg["chapter_ids"]):
        log.debug("coordinator: publishing chapter %s (%d/%d)", chapter_id, index + 1, n)
        await publish("translation.chapter", {
            "job_id":               msg["job_id"],
            "chapter_id":           chapter_id,
            "chapter_index":        index,
            "total_chapters":       len(msg["chapter_ids"]),
            "book_id":              msg["book_id"],
            "user_id":              user_id,
            "model_source":         msg["model_source"],
            "model_ref":            msg["model_ref"],
            "system_prompt":        msg["system_prompt"],
            "user_prompt_tpl":      msg["user_prompt_tpl"],
            "target_language":      msg["target_language"],
            "compact_model_source": msg.get("compact_model_source"),
            "compact_model_ref":    msg.get("compact_model_ref"),
            "chunk_size_tokens":    msg.get("chunk_size_tokens", 2000),
            "invoke_timeout_secs":  msg.get("invoke_timeout_secs", 300),
            "pipeline_version":     msg.get("pipeline_version", "v2"),
            "qa_depth":             msg.get("qa_depth", "standard"),
            "max_qa_rounds":        msg.get("max_qa_rounds", 2),
            "verifier_model_source": msg.get("verifier_model_source"),
            "verifier_model_ref":   msg.get("verifier_model_ref"),
            # S5b-eval: ride the campaign's eval-judge model to the per-chapter
            # worker → onto the translation.quality event for learning's judge.
            "eval_judge_model_source": msg.get("eval_judge_model_source"),
            "eval_judge_model_ref": msg.get("eval_judge_model_ref"),
            "cold_start_mode":      msg.get("cold_start_mode", "single_pass"),
            # S4a: propagate the owning campaign to the per-chapter worker, which
            # sets it as a contextvar so every provider job_meta carries it.
            "campaign_id":          msg.get("campaign_id"),
            # T2-M2: dirty-only re-translate scope (None for whole-chapter jobs).
            "block_index_filter":   msg.get("block_index_filter"),
            "seed_version_id":      msg.get("seed_version_id"),
        })

    log.info("coordinator: job %s — all %d chapter messages published", job_id, n)
    await publish_event(user_id, {
        "event":    "job.status_changed",
        "job_id":   msg["job_id"],
        "job_type": "translation",
        "payload":  {
            "status":             "running",
            "completed_chapters": 0,
            "failed_chapters":    0,
        },
    })
