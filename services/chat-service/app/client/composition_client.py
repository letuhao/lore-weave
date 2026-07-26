"""composition-service client — the Book tier of the Chat & AI settings cascade
(spec docs/specs/2026-07-05-chat-ai-settings.md §3.2, D-CHATAI-M1B).

Reads a book's per-role model settings (the OWNER's, grant-gated cross-tenant for
a collaborator) so the effective-settings resolver can populate the Book tier.
Best-effort by contract: any failure returns `{}` — the resolver marks the book
tier unavailable / falls through, never breaking the turn or the panel.
"""

from __future__ import annotations

import logging

from loreweave_internal_client import build_internal_client

from app.config import settings
from app.middleware.trace_id import trace_id_var

logger = logging.getLogger(__name__)


class CompositionClient:
    def __init__(self) -> None:
        self._base = settings.composition_service_internal_url
        self._token = settings.internal_service_token

    async def get_book_model_roles(self, book_id: str, caller_user_id: str) -> dict:
        """Return `{role: {model_source, model_ref}}` for the book, or `{}` on any
        error / no-grant (404) / no book model set. Never raises into the caller."""
        url = f"{self._base}/internal/composition/books/{book_id}/model-settings"
        try:
            async with build_internal_client(
                self._base, internal_token=self._token,
                timeout_s=2, trace_id_provider=trace_id_var.get,
            ) as client:
                resp = await client.get(url, params={"caller_user_id": caller_user_id})
            if resp.status_code == 200:
                data = resp.json()
                roles = data.get("model_roles") or {}
                return roles if isinstance(roles, dict) else {}
            return {}  # 404 (no grant / no book) or anything else → no book override
        except Exception:  # noqa: BLE001 — degrade to no-book-override, never break the turn
            logger.debug("composition book model-settings unavailable for book=%s", book_id, exc_info=True)
            return {}


_client: CompositionClient | None = None


def get_composition_client() -> CompositionClient:
    global _client
    if _client is None:
        _client = CompositionClient()
    return _client
