"""notification-service HTTP-ingest client (RAID Wave D4 — completion notify).

Mirrors the translation-service producer exactly
(`services/translation-service/app/workers/chapter_worker.py`
`_send_translation_notification`): POST
`{notification_service_internal_url}/internal/notifications` with the
`X-Internal-Token` header (shared `internal_service_token`), body
`{user_id, category, title, metadata}`. notification-service allows only the
categories {translation, social, wiki, system} — authoring runs use `system`;
the machine-readable discriminator rides `metadata.operation =
"autonomous_authoring"` (+ run payload) so the FE can filter/deep-link.

Best-effort BY CONSTRUCTION (project memory: notify via HTTP ingest, not AMQP):
every failure is swallowed and logged — a notification blip must never affect
an authoring run's outcome.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from loreweave_internal_client import build_internal_client

from app.config import settings
from app.logging_config import trace_id_var

logger = logging.getLogger(__name__)


class NotificationClient:
    """Fire-and-forget internal notification producer."""

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self._base_url = (base_url or settings.notification_service_internal_url).rstrip("/")
        self._token = token if token is not None else settings.internal_service_token

    async def notify(
        self,
        user_id: UUID,
        *,
        title: str,
        metadata: dict[str, Any] | None = None,
        category: str = "system",
    ) -> None:
        """Best-effort: swallows every exception (logged at warning)."""
        try:
            # W5 (ephemeral wave): shared factory bakes X-Internal-Token + JSON + trace.
            async with build_internal_client(
                self._base_url, internal_token=self._token,
                timeout_s=5.0, trace_id_provider=trace_id_var.get,
            ) as client:
                await client.post(
                    f"{self._base_url}/internal/notifications",
                    json={
                        "user_id": str(user_id),
                        "category": category,
                        "title": title,
                        "metadata": metadata or {},
                    },
                )
        except Exception as exc:  # noqa: BLE001 — best-effort by contract
            logger.warning("notification ingest failed (ignored): %s", exc)
