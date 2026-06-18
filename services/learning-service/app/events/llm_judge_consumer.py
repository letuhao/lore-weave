"""LLM re-arch Phase 3 M1 — llm-job terminal-event consumer for online judges.

Consumes ``loreweave:events:llm_job_terminal`` (the durable terminal-event stream
the provider-registry relay XADDs on every job's terminal transition) under its OWN
group ``learning-judge-resume`` (distinct from translation's ``translation-llm-resume``
— Redis fan-out delivers a copy to each group). For each terminal event it folds the
finished judge batch and dispatches the next / finalizes (see ``decoupled_judge``).

Any terminal event that isn't a running judge (a translation job, an extraction job,
or a judge already finalized/superseded) finds no matching ``llm_judges`` row → acked
+ ignored. Best-effort: never crashes the service; bounded retry then ack.

Unified Job Control Plane P1 — the Redis transport (BUSYGROUP-safe group, startup PEL
drain, ``socket_timeout=None`` blocking loop, redis-py-8 idle ``TimeoutError``, bounded
retry → poison-ack, sweeper scaffold) now lives in the shared
``loreweave_jobs.BaseTerminalConsumer``; this module supplies only the business fold
(``handle`` → ``decoupled_judge``) + the sweeper SQL (``sweep_once``).
"""

from __future__ import annotations

import logging

from loreweave_jobs import BaseTerminalConsumer

from app.judges import decoupled_judge

log = logging.getLogger(__name__)

STREAM = "loreweave:events:llm_job_terminal"
GROUP_NAME = "learning-judge-resume"


class LLMJudgeConsumer(BaseTerminalConsumer):
    """Terminal-event consumer for online judges on the shared transport scaffold.
    ``sdk`` is the long-lived loreweave_llm Client used for get_job (the consumer's own
    auth identity per-call comes from the terminal event's owner_user_id) and the
    next-batch submits inside ``decoupled_judge.resume``."""

    stream = STREAM
    group = GROUP_NAME
    consumer_name_prefix = "learn-judge"
    retry_prefix = "learn:judgeresume:retry"

    def __init__(self, redis_url: str, pool, sdk, *, consumer_name: str | None = None) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool
        self._sdk = sdk

    async def handle(self, fields: dict) -> None:
        job_id = fields.get("job_id")
        if not job_id:
            return  # no job id → ack-ignore (the base acks on a normal return)
        owner_user_id = fields.get("owner_user_id") or None
        loaded = await decoupled_judge.load_for_job(self._pool, job_id)
        if loaded is None:
            return  # not a running judge (translation/extraction job, or finalized) → ack-ignore
        _row_id, billing_user_id = loaded
        job = await self._sdk.get_job(job_id, user_id=owner_user_id or billing_user_id)
        await decoupled_judge.resume(self._pool, self._sdk, job)

    async def sweep_once(self, *, timeout_s: int, batch: int) -> int:
        return await decoupled_judge.sweep_once(
            self._pool, self._sdk, timeout_s=timeout_s, batch=batch,
        )
