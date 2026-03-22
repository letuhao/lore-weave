import logging
from uuid import UUID

log = logging.getLogger(__name__)


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
        await db.execute(
            "UPDATE translation_jobs SET status='running', started_at=now() WHERE job_id=$1",
            job_id,
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
