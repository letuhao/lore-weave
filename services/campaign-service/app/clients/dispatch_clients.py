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


class EmbeddingConflict(Exception):
    """S5b: the campaign's embedding override differs from the project's current
    model AND the project already has a graph, but confirm_embedding_change was not
    set. Changing it would destroy the existing vectors — the caller must surface a
    409 so the user explicitly confirms the destructive change."""


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
        campaign_id: str | None = None,
        verifier_model_source: str | None = None,
        verifier_model_ref: str | None = None,
        eval_judge_model_source: str | None = None,
        eval_judge_model_ref: str | None = None,
    ) -> str:
        """POST /internal/translation/dispatch-job → returns the new job_id.

        S4a: campaign_id is threaded so every provider job the translation job
        spawns is attributable to this campaign's cumulative spend (decision C).
        S5b: verifier_model_* lets the campaign pick the V3 verifier model (null →
        translation falls back to the translator model)."""
        url = f"{self._base_url}/internal/translation/dispatch-job"
        body = {
            "user_id": user_id,
            "book_id": book_id,
            "chapter_ids": chapter_ids,
            "target_language": target_language,
            "model_source": model_source,
            "model_ref": model_ref,
            "campaign_id": campaign_id,
            "verifier_model_source": verifier_model_source,
            "verifier_model_ref": verifier_model_ref,
            "eval_judge_model_source": eval_judge_model_source,
            "eval_judge_model_ref": eval_judge_model_ref,
        }
        try:
            resp = await self._http.post(url, json=body)
        except httpx.RequestError as exc:
            raise DispatchError(f"translation dispatch: {exc}") from exc
        if not resp.is_success:
            raise DispatchError(f"translation dispatch {resp.status_code}: {resp.text[:300]}")
        return str(resp.json().get("job_id", ""))

    async def job_status(self, *, user_id: str, job_id: str) -> str:
        """D-CAMPAIGN-BESTEFFORT-EMIT-REDIS: job-level aliveness for the stuck
        reconcile — checked ONCE per job so a slow-but-alive batch isn't probed
        per-chapter every tick. Returns "active" | "terminal"; a 404 → "gone"
        (safe to re-dispatch). Raises DispatchError on transport/other errors so
        the caller LEAVES the rows untouched."""
        url = f"{self._base_url}/internal/translation/jobs/{job_id}/status"
        try:
            resp = await self._http.get(url, params={"user_id": user_id})
        except httpx.RequestError as exc:
            raise DispatchError(f"translation job_status: {exc}") from exc
        if resp.status_code == 404:
            return "gone"
        if not resp.is_success:
            raise DispatchError(
                f"translation job_status {resp.status_code}: {resp.text[:300]}"
            )
        return str(resp.json().get("status", ""))

    async def chapter_status(self, *, user_id: str, job_id: str, chapter_id: str) -> str:
        """D-CAMPAIGN-BESTEFFORT-EMIT-REDIS: ground-truth for the stuck reconcile.
        Returns the normalized vocab "done" | "failed" | "running" | "gone" for a
        chapter's translation. A 404 (job not found/owned) → "gone" (safe to
        re-dispatch). Raises DispatchError on transport/other errors so the caller
        LEAVES the row untouched (never reset on uncertainty → no re-dispatch loop)."""
        url = f"{self._base_url}/internal/translation/jobs/{job_id}/chapters/{chapter_id}/status"
        try:
            resp = await self._http.get(url, params={"user_id": user_id})
        except httpx.RequestError as exc:
            raise DispatchError(f"translation chapter_status: {exc}") from exc
        if resp.status_code == 404:
            return "gone"
        if not resp.is_success:
            raise DispatchError(
                f"translation chapter_status {resp.status_code}: {resp.text[:300]}"
            )
        return str(resp.json().get("status", ""))

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
        campaign_id: str | None = None,
        billing_user_id: str | None = None,
        billing_embedding_model: str | None = None,
    ) -> str:
        """POST /internal/knowledge/projects/{project_id}/dispatch-extraction →
        returns the new extraction job_id.

        `chapter_from/to` are forwarded for when the knowledge runner honours the
        range (S2, D-K16.2-02b); in S1 the endpoint passes them through but the
        runner still processes the whole project and the projection tracks
        per-chapter completion via events. The endpoint owns the knowledge-side
        `scope_range` shape — this client stays agnostic of it.

        E0-4b dual identity: `user_id` is the GRAPH partition (the book owner who
        owns the project). When a manage-collaborator runs the campaign,
        `billing_user_id` (the caller) + `billing_embedding_model` (the caller's own
        ref for the SAME embedding model) make the knowledge stage bill the CALLER
        on their key while writing into the owner's graph — the endpoint's 2b
        dual-identity branch (dimension-guarded). Owner-self → both None (legacy
        owner-paid)."""
        url = f"{self._base_url}/internal/knowledge/projects/{project_id}/dispatch-extraction"
        body: dict = {
            "user_id": user_id,
            "scope": scope,
            "chapter_from": chapter_from,
            "chapter_to": chapter_to,
            "model_source": model_source,
            "model_ref": model_ref,
            "campaign_id": campaign_id,
            "billing_user_id": billing_user_id,
            "billing_embedding_model": billing_embedding_model,
        }
        try:
            resp = await self._http.post(url, json=body)
        except httpx.RequestError as exc:
            raise DispatchError(f"knowledge dispatch: {exc}") from exc
        if not resp.is_success:
            raise DispatchError(f"knowledge dispatch {resp.status_code}: {resp.text[:300]}")
        return str(resp.json().get("job_id", ""))

    async def set_campaign_models(
        self,
        *,
        project_id: str,
        user_id: str,
        embedding_model_source: str | None = None,
        embedding_model_ref: str | None = None,
        rerank_model_source: str | None = None,
        rerank_model_ref: str | None = None,
        confirm_embedding_change: bool = False,
    ) -> dict:
        """S5b: apply the campaign's embedding/reranker picks to its knowledge
        project (the project is SSOT). Raises EmbeddingConflict on a 409 (graph
        exists + embedding differs + not confirmed) so create can surface it;
        DispatchError on other failures."""
        url = f"{self._base_url}/internal/knowledge/projects/{project_id}/set-campaign-models"
        body = {
            "user_id": user_id,
            "embedding_model_source": embedding_model_source,
            "embedding_model_ref": embedding_model_ref,
            "rerank_model_source": rerank_model_source,
            "rerank_model_ref": rerank_model_ref,
            "confirm_embedding_change": confirm_embedding_change,
        }
        try:
            resp = await self._http.post(url, json=body)
        except httpx.RequestError as exc:
            raise DispatchError(f"knowledge set-campaign-models: {exc}") from exc
        if resp.status_code == 409:
            raise EmbeddingConflict(resp.text[:300])
        if not resp.is_success:
            raise DispatchError(
                f"knowledge set-campaign-models {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    async def verify_project_owner(self, *, user_id: str, project_id: str) -> bool:
        """D-CAMPAIGN-KPROJECT-OWNERSHIP: cheap early ownership probe for campaign
        create. Reuses the owner-scoped extraction-status endpoint (404 iff the
        project doesn't exist / isn't owned by user_id). Returns False on 404 (caller
        → 400); True on 2xx. Raises DispatchError on transport/other errors so create
        does NOT falsely reject on a transient knowledge-service blip."""
        url = f"{self._base_url}/internal/knowledge/projects/{project_id}/extraction-status"
        try:
            resp = await self._http.get(url, params={"user_id": user_id})
        except httpx.RequestError as exc:
            raise DispatchError(f"knowledge verify_project_owner: {exc}") from exc
        if resp.status_code == 404:
            return False
        if not resp.is_success:
            raise DispatchError(
                f"knowledge verify_project_owner {resp.status_code}: {resp.text[:300]}"
            )
        return True

    async def extraction_status(self, *, user_id: str, project_id: str) -> dict:
        """D-CAMPAIGN-BESTEFFORT-EMIT-REDIS: ground-truth for the stuck reconcile.
        Returns `{active: bool, last_outcome: str|None}`. Knowledge runs one job
        per project over a scope (no per-chapter job), so the truth is project-
        scoped: `active` → a chapter is legitimately in-flight (leave it); not
        active + last_outcome=='complete' → the scope finished, so a stuck chapter
        was extracted but its event was lost (reconcile to done). Raises
        DispatchError on transport/other errors → caller LEAVES the row untouched."""
        url = f"{self._base_url}/internal/knowledge/projects/{project_id}/extraction-status"
        try:
            resp = await self._http.get(url, params={"user_id": user_id})
        except httpx.RequestError as exc:
            raise DispatchError(f"knowledge extraction_status: {exc}") from exc
        if not resp.is_success:
            raise DispatchError(
                f"knowledge extraction_status {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

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
