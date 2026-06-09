"""Internal clients that DRIVE the existing per-service job APIs (decision A).

Both pass the campaign owner's VERIFIED `user_id` in the request body over an
internal-token call — never a minted user-JWT. Ownership was verified once at
campaign-create; these are trusted S2S "assert-verified-user_id" calls into the
new `/internal/.../dispatch-*` endpoints added in S1.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


class DispatchError(Exception):
    """A downstream dispatch call failed (network or non-2xx)."""


class TranslationDispatchClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def dispatch_job(
        self,
        *,
        user_id: str,
        book_id: str,
        chapter_ids: list[str],
        target_language: str | None,
        model_source: str | None,
        model_ref: str | None,
    ) -> str:
        """POST /internal/translation/dispatch-job → returns the new job_id."""
        url = f"{self._base_url}/internal/translation/dispatch-job"
        body = {
            "user_id": user_id,
            "book_id": book_id,
            "chapter_ids": chapter_ids,
            "target_language": target_language,
            "model_source": model_source,
            "model_ref": model_ref,
        }
        try:
            resp = await self._http.post(url, json=body)
        except httpx.RequestError as exc:
            raise DispatchError(f"translation dispatch: {exc}") from exc
        if not resp.is_success:
            raise DispatchError(f"translation dispatch {resp.status_code}: {resp.text[:300]}")
        return str(resp.json().get("job_id", ""))

    async def cancel_job(self, *, user_id: str, job_id: str) -> None:
        """S3c-2: cancel an in-flight translation job (campaign cancel). Idempotent
        on the translation side; a 404/409 (already terminal) is treated as success."""
        url = f"{self._base_url}/internal/translation/jobs/{job_id}/cancel"
        try:
            resp = await self._http.post(url, json={"user_id": user_id})
        except httpx.RequestError as exc:
            raise DispatchError(f"translation cancel: {exc}") from exc
        if resp.status_code in (404, 409):
            return  # already terminal / gone — nothing to cancel
        if not resp.is_success:
            raise DispatchError(f"translation cancel {resp.status_code}: {resp.text[:300]}")


class KnowledgeDispatchClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def dispatch_extraction(
        self,
        *,
        project_id: str,
        user_id: str,
        scope: str,
        chapter_from: int | None,
        chapter_to: int | None,
        model_source: str | None,
        model_ref: str | None,
    ) -> str:
        """POST /internal/knowledge/projects/{project_id}/dispatch-extraction →
        returns the new extraction job_id.

        `chapter_from/to` are forwarded for when the knowledge runner honours the
        range (S2, D-K16.2-02b); in S1 the endpoint passes them through but the
        runner still processes the whole project and the projection tracks
        per-chapter completion via events. The endpoint owns the knowledge-side
        `scope_range` shape — this client stays agnostic of it."""
        url = f"{self._base_url}/internal/knowledge/projects/{project_id}/dispatch-extraction"
        body: dict = {
            "user_id": user_id,
            "scope": scope,
            "chapter_from": chapter_from,
            "chapter_to": chapter_to,
            "model_source": model_source,
            "model_ref": model_ref,
        }
        try:
            resp = await self._http.post(url, json=body)
        except httpx.RequestError as exc:
            raise DispatchError(f"knowledge dispatch: {exc}") from exc
        if not resp.is_success:
            raise DispatchError(f"knowledge dispatch {resp.status_code}: {resp.text[:300]}")
        return str(resp.json().get("job_id", ""))

    async def cancel_extraction(self, *, user_id: str, project_id: str) -> None:
        """S3c-2: cancel the project's active extraction job (campaign cancel).
        Knowledge cancel is project-scoped. 404/409 (no active job / already
        terminal) is treated as success."""
        url = f"{self._base_url}/internal/knowledge/projects/{project_id}/extraction/cancel"
        try:
            resp = await self._http.post(url, json={"user_id": user_id})
        except httpx.RequestError as exc:
            raise DispatchError(f"knowledge cancel: {exc}") from exc
        if resp.status_code in (404, 409):
            return
        if not resp.is_success:
            raise DispatchError(f"knowledge cancel {resp.status_code}: {resp.text[:300]}")
