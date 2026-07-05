"""Durable notification producer (D-C-PRODUCER-OUTBOX).

Replaces the fire-and-forget `NotificationClient` HTTP POST (lost if notification-
service was down) as the production `Notifier`. Instead of POSTing, it writes the
notification into composition's transactional outbox as an `aggregate_type='notification'`
row; worker-infra's shared relay delivers it to notification-service's
`/internal/notifications` ingest with retry, idempotent via a deterministic `dedup_key`.

This is an OWN-tx durable enqueue (a short tx around the single outbox INSERT), not the
same tx as the FSM `transition()` that flipped the run to terminal. That fully fixes the
dominant loss cause — notification-service being down — which the former POST swallowed;
the residual (a process crash in the sub-ms window between the transition commit and this
enqueue commit) is negligible and strictly better than the prior fire-and-forget. Keeping
it out of the FSM tx avoids threading a conn through the driver's complex transition path.

Satisfies the `Notifier` protocol (authoring_run_service.Notifier) — swapped in as the
lazy default; tests still inject their own recorder, so this never runs under unit tests.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


def _dedup_key(metadata: dict[str, Any] | None) -> str | None:
    """A deterministic idempotency key so the relay's at-least-once delivery can't
    double-post. Terminal authoring notifications carry run_id + status; one
    notification per (run, terminal status)."""
    if not metadata:
        return None
    run_id, status = metadata.get("run_id"), metadata.get("status")
    if run_id and status:
        return f"authoring:{run_id}:{status}"
    return None


class OutboxNotifier:
    """Best-effort by contract (a notify blip never affects a run), but durable:
    the failure surface is now a write to composition's OWN db (far more reliable
    than a cross-service HTTP POST) plus the relay's retrying drain."""

    def __init__(self, pool: Any | None = None) -> None:
        # Optional injected pool for tests; None ⇒ the process pool at call time.
        self._pool = pool

    async def notify(
        self,
        user_id: UUID,
        *,
        title: str,
        metadata: dict[str, Any] | None = None,
        category: str = "system",
    ) -> None:
        body = {
            "user_id": str(user_id),
            "category": category,
            "title": title,
            "metadata": metadata or {},
        }
        dedup = _dedup_key(metadata)
        if dedup:
            body["dedup_key"] = dedup
        try:
            from app.db.repositories import outbox

            pool = self._pool
            if pool is None:
                from app.db.pool import get_pool

                pool = get_pool()
            # aggregate_id is informational (routing is by aggregate_type); anchor it
            # to the run when present so the outbox row is traceable.
            run_id = (metadata or {}).get("run_id")
            agg_id = UUID(str(run_id)) if run_id else uuid4()
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await outbox.emit(
                        conn,
                        aggregate_id=agg_id,
                        event_type="notification.requested",
                        payload=body,
                        aggregate_type="notification",
                    )
        except Exception as exc:  # noqa: BLE001 — best-effort by contract
            logger.warning("notification outbox enqueue failed (ignored): %s", exc)
