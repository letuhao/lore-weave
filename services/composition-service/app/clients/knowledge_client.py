"""knowledge-service client (composition-service, M2 — resolve slice only).

M2 pulls this ONE read forward from M3 to do the full §6.2 Work resolution:
list the knowledge projects linked to a book so resolve can tell
no-project / unmarked-single / candidates apart.

AUTH (contract-verified 2026-06-03): `GET /v1/knowledge/projects?book_id=` is
**JWT-only** — there is no internal-token variant. So this client FORWARDS the
caller's user `Authorization: Bearer`, NOT the internal service token. That is
the secure choice for resolve: knowledge derives user_id from the JWT `sub` and
filters every row by it, so a cross-user book_id returns an empty list — the
ownership check is enforced server-side by the forwarding itself. (The §2.5
internal-token ownership chokepoint applies to the M4 packer's /internal reads,
not here.)

Graceful degradation (mirrors knowledge-service's book_client): any transport
error / non-200 returns None so resolve can surface "knowledge unavailable"
rather than 500. The base URL is the in-cluster host (`knowledge_internal_url`);
the route it serves is the public `/v1/knowledge` prefix.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

from app.config import settings
from app.logging_config import trace_id_var

logger = logging.getLogger(__name__)

_client: "KnowledgeClient | None" = None


class KnowledgeContractError(Exception):
    """C16 (WG-3): knowledge-service rejected a request with a 4xx CONTRACT error
    (bad/forbidden payload — our bug, not an outage). The caller MUST surface this
    (e.g. POST /work → 502 PROJECT_CREATE_FAILED) rather than silently degrading —
    only down/timeout/5xx are eligible for graceful (lazy-project) degradation.
    Carries the status so the router can log/branch."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"knowledge contract error: {status_code}")


class KnowledgeClient:
    def __init__(
        self, base_url: str, internal_token: str = "", timeout_s: float = 5.0,
        extract_timeout_s: float = 180.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_token = internal_token
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s))
        # C27 — extract-item runs an LLM Pass-2 extraction (slow); its per-request
        # timeout is far longer than the read-lens default. Configurable for tests.
        self._extract_timeout_s = extract_timeout_s

    async def aclose(self) -> None:
        await self._http.aclose()

    def _bearer_headers(self, bearer: str) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {bearer}"}
        tid = trace_id_var.get()
        if tid:
            headers["X-Trace-Id"] = tid
        return headers

    def _internal_headers(self) -> dict[str, str]:
        headers = {"X-Internal-Token": self._internal_token}
        tid = trace_id_var.get()
        if tid:
            headers["X-Trace-Id"] = tid
        return headers

    async def list_projects_for_book(
        self, book_id: UUID, bearer: str
    ) -> list[dict[str, Any]] | None:
        """Projects linked to `book_id` for the JWT's user. Returns the items
        list, or None on any transport/HTTP failure (caller treats None as
        'knowledge unavailable'). `bearer` is the raw JWT (no 'Bearer ' prefix);
        we add the scheme. Empty header → return None (can't authenticate)."""
        if not bearer:
            logger.warning("knowledge resolve called without a bearer token")
            return None
        url = f"{self._base_url}/v1/knowledge/projects"
        try:
            resp = await self._http.get(
                url, params={"book_id": str(book_id), "limit": "100"},
                headers=self._bearer_headers(bearer),
            )
        except httpx.HTTPError as exc:
            logger.warning("knowledge unreachable: %s", exc)
            return None
        if resp.status_code != 200:
            logger.warning("knowledge %s → %d", url, resp.status_code)
            return None
        try:
            return resp.json().get("items", [])
        except (ValueError, AttributeError) as exc:
            logger.warning("knowledge bad JSON: %s", exc)
            return None

    async def create_project(
        self, book_id: UUID, name: str, bearer: str, *, force_new: bool = False,
    ) -> dict[str, Any] | None:
        """Create a BOOK-typed knowledge project for this book (M8 POST /work).
        JWT-forward → knowledge scopes it to the user. Returns the created project
        dict (carries `project_id`).

        `force_new` (C23-fix, dị bản G2): when True (the derive path) knowledge
        ALWAYS mints a FRESH distinct project (skips its per-(user,book)
        get-or-create dedup) and flags it is_derivative — so a derivative gets
        its OWN partition instead of inheriting the source book's project_id
        (which violated composition's uq_composition_work_project). Default
        False keeps the greenfield POST /work path idempotent (unchanged).

        C16 (WG-3) error discrimination — the caller degrades vs surfaces by class:
          • 5xx / timeout / transport error → return None (knowledge OUTAGE → the
            POST /work caller may create a lazy null-project Work and keep writing).
          • 4xx → raise KnowledgeContractError (a CONTRACT bug — bad/forbidden
            payload — that must NOT be swallowed as an outage; the caller surfaces
            it as a 502 PROJECT_CREATE_FAILED). A 401/403 (auth) is also 4xx →
            surfaced, never silently degraded into a grounding-blind Work.
          • empty bearer → None (can't authenticate; treat as unavailable)."""
        if not bearer:
            return None
        url = f"{self._base_url}/v1/knowledge/projects"
        payload: dict[str, Any] = {
            "name": name, "project_type": "book", "book_id": str(book_id),
        }
        if force_new:
            payload["force_new"] = True
        try:
            resp = await self._http.post(url, json=payload, headers=self._bearer_headers(bearer))
        except httpx.HTTPError as exc:
            # transport / timeout / connect refused → outage → degrade.
            logger.warning("knowledge create_project unavailable: %s", exc)
            return None
        if resp.status_code in (200, 201):
            try:
                return resp.json()
            except (ValueError, AttributeError) as exc:
                logger.warning("knowledge create_project bad JSON: %s", exc)
                return None
        if 400 <= resp.status_code < 500:
            logger.warning("knowledge create_project CONTRACT %d (surfacing)", resp.status_code)
            raise KnowledgeContractError(resp.status_code)
        # 5xx (or any other non-2xx) → outage → degrade.
        logger.warning("knowledge create_project → %d (degrading)", resp.status_code)
        return None

    # ── C27 (dị bản M4) delta flywheel ──────────────────────────────────

    async def extract_item(
        self, *, user_id: UUID, project_id: UUID, source_id: str,
        chapter_text: str, model_source: str, model_ref: str,
        job_id: UUID, known_entities: list[str] | None = None,
        source_type: str = "chapter",
    ) -> dict[str, Any] | None:
        """C27 delta flywheel — dispatch the EXISTING knowledge extraction trigger
        (`POST /internal/extraction/extract-item`, X-Internal-Token) for ONE
        approved derivative chapter, scoped to the derivative's OWN `project_id`
        (its delta partition, G2). This REUSES the existing extraction engine — it
        only points it at the delta project; no new extraction code.

        `project_id` MUST be the derivative's delta project (the caller asserts the
        project-scope GUARD first — never null, never the source). The internal
        endpoint runs Pass-2 extraction + writes into that project's Neo4j
        partition, so the next pack (C25) merges the new delta facts.

        AI-FREE: composition supplies a caller-resolved (provider-registry) model
        ref; the LLM call happens inside knowledge-service. No provider SDK here.

        Returns the extraction result dict (entities/relations/events/facts merged)
        or None on any transport/HTTP failure — the approval must not 500 on a
        knowledge outage (the flywheel re-arms on the next approval; grounding just
        stays thinner until then).

        TIMEOUT: extract-item runs a FULL Pass-2 LLM extraction inside
        knowledge-service (many seconds — far longer than the 5s read-lens default).
        We pass an explicit long per-request timeout so the dispatch isn't a
        false-`knowledge_unavailable` on a slow-but-healthy extraction (a live-smoke
        catch: the read-lens 5s timeout silently aborted the LLM call)."""
        url = f"{self._base_url}/internal/extraction/extract-item"
        payload: dict[str, Any] = {
            "user_id": str(user_id),
            "project_id": str(project_id),
            "item_type": "chapter",
            "source_type": source_type,
            "source_id": source_id,
            "job_id": str(job_id),
            "model_source": model_source,
            "model_ref": model_ref,
            "chapter_text": chapter_text,
            "known_entities": list(known_entities or []),
        }
        try:
            resp = await self._http.post(
                url, json=payload, headers=self._internal_headers(),
                # LLM extraction is slow — override the short read-lens default.
                timeout=httpx.Timeout(self._extract_timeout_s),
            )
            if resp.status_code != 200:
                logger.warning("knowledge extract-item → %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("knowledge extract-item unavailable: %r", exc)
            return None

    # ── W8 motif mining: the motif_beat sequence source (cross-service) ──────────
    async def get_motif_beat_sequences(
        self, user_id: UUID, *, book_id: UUID | None = None, corpus: bool = False,
        language: str | None = None,
    ) -> list[list[dict[str, Any]]]:
        """W8 — the `motif_beat` extraction source for the composition-side miner.

        Returns ORDERED beat sequences: one list per coherent narrative unit
        (book/arc/chapter), each a list of `{beat, thread, tension, role_mentions}`
        ordered by the knowledge timeline's `event_order` (the SPADE/PrefixSpan
        input). Scope is `book_id` (one book) or `corpus=True` (all the user's
        books); `language` narrows the axis. The user scope is carried on the call
        (tenancy — the server filters by user_id; a cross-user book returns []).

        DEFERRED — D-W8-MOTIF-BEAT-EXTRACTOR: the knowledge-service SERVER route
        (`POST /internal/extraction/motif-beats`) — a 5th map-extractor in
        loreweave_extraction (§12.4) emitting `{beat, thread, tension, role_mentions}`
        per scene/chapter, keyed by `motif_mine_extractor_version` — does NOT exist
        yet (it needs the running service + a corpus + an LLM). Until it lands this
        thin client returns [] on a 404/501/transport-error so the miner DEGRADES
        cleanly (`mined: 0, reason: 'beat_extractor_unavailable'`) instead of
        crashing — the whole mining path is wired + unit-testable now, and flips
        live the moment the extractor ships (no composition-side change).
        """
        url = f"{self._base_url}/internal/extraction/motif-beats"
        payload: dict[str, Any] = {"user_id": str(user_id)}
        if corpus:
            payload["corpus"] = True
        elif book_id is not None:
            payload["book_id"] = str(book_id)
        if language:
            payload["language"] = language
        payload["extractor_version"] = settings.motif_mine_extractor_version
        try:
            resp = await self._http.post(url, json=payload, headers=self._internal_headers())
        except httpx.HTTPError as exc:
            logger.warning("knowledge motif-beats unavailable (extractor deferred): %s", exc)
            return []
        # 404 (route not deployed yet) / 501 (not implemented) → the deferred
        # extractor — degrade to [] (NOT a crash). Any other non-200 also degrades.
        if resp.status_code != 200:
            logger.warning("knowledge motif-beats → %d (extractor deferred?)", resp.status_code)
            return []
        try:
            data = resp.json()
        except (ValueError, AttributeError) as exc:
            logger.warning("knowledge motif-beats bad JSON: %s", exc)
            return []
        seqs = data.get("sequences") if isinstance(data, dict) else None
        if not isinstance(seqs, list):
            return []
        # Normalize: keep only well-formed list-of-dict sequences.
        return [s for s in seqs if isinstance(s, list)]

    async def tag_threads(
        self, user_id: UUID, *, book_id: UUID, threads: list[dict[str, Any]],
        model_source: str, model_ref: str,
    ) -> dict[str, Any]:
        """D-W10-ARC-CONFORMANCE-THREAD-TAG — classify the book's :Event timeline into the
        given narrative-thread vocabulary (the arc's threads) and persist the labels, so a
        subsequent motif-beats read carries real ``narrative_thread`` per step. ADVISORY:
        returns ``{tagged, events_seen, threads_assigned}`` on success, or a degrade
        ``{tagged:0, …, status:'unavailable'}`` on any outage/non-200 (the deep conformance
        caller then just sees no tags — pacing still works)."""
        url = f"{self._base_url}/internal/extraction/tag-threads"
        payload = {"user_id": str(user_id), "book_id": str(book_id), "threads": threads,
                   "model_source": model_source, "model_ref": model_ref}
        try:
            resp = await self._http.post(url, json=payload, headers=self._internal_headers())
        except httpx.HTTPError as exc:
            logger.warning("knowledge tag-threads unavailable: %s", exc)
            return {"tagged": 0, "events_seen": 0, "threads_assigned": {}, "status": "unavailable"}
        if resp.status_code != 200:
            logger.warning("knowledge tag-threads → %d", resp.status_code)
            return {"tagged": 0, "events_seen": 0, "threads_assigned": {}, "status": "unavailable"}
        try:
            return resp.json()
        except (ValueError, AttributeError):
            return {"tagged": 0, "events_seen": 0, "threads_assigned": {}, "status": "unavailable"}

    async def tag_motifs(
        self, user_id: UUID, *, book_id: UUID, motifs: list[dict[str, Any]],
        model_source: str, model_ref: str,
    ) -> dict[str, Any]:
        """D-W10-ARC-CONFORMANCE-SUCCESSION — classify the book's :Event timeline into which
        arc-placement motif (by code) each event realizes, and persist it, so a subsequent
        motif-beats read carries ``realized_motif_code`` per step (the realized order for the
        succession diff). ADVISORY: returns ``{tagged, events_seen, motifs_assigned}`` or a
        degrade ``{tagged:0, …, status:'unavailable'}`` on any outage/non-200."""
        url = f"{self._base_url}/internal/extraction/tag-motifs"
        payload = {"user_id": str(user_id), "book_id": str(book_id), "motifs": motifs,
                   "model_source": model_source, "model_ref": model_ref}
        try:
            resp = await self._http.post(url, json=payload, headers=self._internal_headers())
        except httpx.HTTPError as exc:
            logger.warning("knowledge tag-motifs unavailable: %s", exc)
            return {"tagged": 0, "events_seen": 0, "motifs_assigned": {}, "status": "unavailable"}
        if resp.status_code != 200:
            logger.warning("knowledge tag-motifs → %d", resp.status_code)
            return {"tagged": 0, "events_seen": 0, "motifs_assigned": {}, "status": "unavailable"}
        try:
            return resp.json()
        except (ValueError, AttributeError):
            return {"tagged": 0, "events_seen": 0, "motifs_assigned": {}, "status": "unavailable"}

    async def infer_causal_edges(
        self, user_id: UUID, *, book_id: UUID, model_source: str, model_ref: str,
    ) -> dict[str, Any]:
        """D-W10-ARC-CONFORMANCE-SUCCESSION F2 — infer + persist `(:Event)-[:CAUSES]` edges
        over the book's motif-tagged events. ADVISORY: returns the counts or a degrade dict."""
        url = f"{self._base_url}/internal/extraction/causal-edges"
        payload = {"user_id": str(user_id), "book_id": str(book_id),
                   "model_source": model_source, "model_ref": model_ref}
        try:
            resp = await self._http.post(url, json=payload, headers=self._internal_headers())
        except httpx.HTTPError as exc:
            logger.warning("knowledge causal-edges unavailable: %s", exc)
            return {"edges_written": 0, "events_considered": 0, "status": "unavailable"}
        if resp.status_code != 200:
            return {"edges_written": 0, "events_considered": 0, "status": "unavailable"}
        try:
            return resp.json()
        except (ValueError, AttributeError):
            return {"edges_written": 0, "events_considered": 0, "status": "unavailable"}

    async def causal_motif_pairs(self, user_id: UUID, *, book_id: UUID) -> list[tuple[str, str]]:
        """The realized CAUSES edges in motif-code space — ``[(cause_code, effect_code)]`` —
        for deep succession causal-verify. ADVISORY: returns ``[]`` on any outage/non-200."""
        url = f"{self._base_url}/internal/extraction/causal-motif-pairs"
        payload = {"user_id": str(user_id), "book_id": str(book_id)}
        try:
            resp = await self._http.post(url, json=payload, headers=self._internal_headers())
        except httpx.HTTPError as exc:
            logger.warning("knowledge causal-motif-pairs unavailable: %s", exc)
            return []
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except (ValueError, AttributeError):
            return []
        pairs = data.get("pairs") if isinstance(data, dict) else None
        if not isinstance(pairs, list):
            return []
        return [(p[0], p[1]) for p in pairs
                if isinstance(p, list) and len(p) == 2 and all(isinstance(x, str) for x in p)]

    # ── M4 packer lenses ────────────────────────────────────────────────
    # All return None/[] on any failure (the packer `_safe_*` degrade, F1) so a
    # knowledge outage thins the pack rather than 500-ing a generate.

    async def build_context(
        self, user_id: UUID, *, project_id: UUID | None, message: str = "",
        session_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        """POST /internal/context/build (X-Internal-Token). The caller MUST have
        verified book/project ownership first (SEC2) — the internal endpoint
        trusts the token, not the user. Returns the context envelope
        (`context`/`stable_context`/`volatile_context`/`token_count`) or None."""
        url = f"{self._base_url}/internal/context/build"
        payload: dict[str, Any] = {"user_id": str(user_id), "message": message}
        if project_id is not None:
            payload["project_id"] = str(project_id)
        if session_id is not None:
            payload["session_id"] = str(session_id)
        try:
            resp = await self._http.post(url, json=payload, headers=self._internal_headers())
            if resp.status_code != 200:
                logger.warning("knowledge context/build → %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("knowledge context/build unavailable: %s", exc)
            return None

    async def glossary_semantic(
        self, user_id: UUID, *, project_id: UUID, query: str,
        max_entities: int = 20, max_tokens: int = 1000,
    ) -> list[dict[str, Any]]:
        """L1a (mui #4) — semantically-ranked glossary entities (X-Internal-Token).
        POST /internal/context/glossary-semantic: knowledge embeds the query,
        vector-ranks its `:Entity` nodes, and enriches the glossary-anchored hits
        with canon detail. Same item shape as glossary select-for-context
        (entity_id/cached_name/short_description/kind_code). Returns [] on any
        failure or a no-embedding project — the caller falls back to glossary
        FTS. Caller MUST have verified ownership first (SEC2; internal endpoint
        trusts the token)."""
        url = f"{self._base_url}/internal/context/glossary-semantic"
        payload = {
            "user_id": str(user_id), "project_id": str(project_id),
            "query": query, "max_entities": max_entities, "max_tokens": max_tokens,
        }
        try:
            resp = await self._http.post(url, json=payload, headers=self._internal_headers())
            if resp.status_code != 200:
                logger.warning("knowledge glossary-semantic → %d", resp.status_code)
                return []
            data = resp.json()
            return data.get("items", []) if isinstance(data, dict) else []
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("knowledge glossary-semantic unavailable: %s", exc)
            return []

    async def timeline(
        self, bearer: str, *, project_id: UUID, before_chronological: int | None = None,
        before_order: int | None = None, after_order: int | None = None,
        entity_id: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """L1b — in-world events for a project (JWT-forward). `project_id` is
        ALWAYS sent (A1/§12: omitting it widens to ALL the user's projects).
        `before_order` is the dense reading-order spoiler cutoff (event_order);
        `after_order` is the RECENT-WINDOW lower bound (the endpoint orders
        event_order ASC + LIMIT, so without it a deep-book query returns the
        OLDEST prior events — LOOM-32 MED#1). Returns the events list (each carries
        `chronological_order`/`event_order`/`title`/`summary`/`participants`) or
        [] on failure."""
        params: dict[str, Any] = {"project_id": str(project_id), "limit": limit}
        if before_chronological is not None:
            params["before_chronological"] = before_chronological
        if before_order is not None:
            params["before_order"] = before_order
        if after_order is not None:
            params["after_order"] = after_order
        if entity_id is not None:
            params["entity_id"] = entity_id
        return await self._jwt_get_list(
            "/v1/knowledge/timeline", params, bearer, key="events", label="timeline",
        )

    async def get_entity(self, bearer: str, entity_id: str) -> dict[str, Any] | None:
        """L1a — a single entity's current state + currently-valid relations
        (the detail endpoint filters `valid_until IS NULL` server-side).
        JWT-forward. Returns `{entity, relations, ...}` or None."""
        url = f"{self._base_url}/v1/knowledge/entities/{entity_id}"
        try:
            resp = await self._http.get(url, headers=self._bearer_headers(bearer))
            if resp.status_code != 200:
                logger.warning("knowledge entity %s → %d", entity_id, resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("knowledge entity unavailable: %s", exc)
            return None

    async def search_drawers(
        self, bearer: str, *, project_id: UUID, query: str, limit: int = 40,
        source_type: str | None = None, language: str | None = None,
    ) -> list[dict[str, Any]]:
        """L4 — semantic search (JWT-forward). `project_id` is REQUIRED by the
        endpoint (cross-project unsupported). Each hit carries `source_id` +
        `chapter_index` (int|None — the packer's reading-order spoiler axis) +
        `raw_score` (NOT `score`) + `source_lang`. Returns hits or [] on failure.

        KG-ML M7 (C6): `language` (the author's reader-language) soft-orders
        in-language passages first (matched-first partition, not a filter) so a vi
        author's lore lens surfaces vi passages — the headline scenario. Omitted →
        relevance order only (back-compat)."""
        params: dict[str, Any] = {
            "project_id": str(project_id), "query": query, "limit": limit,
        }
        if source_type is not None:
            params["source_type"] = source_type
        if language:
            params["language"] = language
        return await self._jwt_get_list(
            "/v1/knowledge/drawers/search", params, bearer, key="hits", label="drawers",
        )

    async def fact_for_check(
        self, *, project_id: UUID, at_order: int,
        glossary_entity_ids: list[str] | None = None,
        entity_ids: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """A2-S2/S3 — the canon snapshot (status@P + entities + relations +
        events≤P) for the SCORE symbolic guard. POST /internal/projects/{id}/
        fact-for-check (X-Internal-Token). The cast is composition's glossary
        entity ids (resolved server-side via the glossary_entity_id FK).
        Returns the snapshot dict or None on any failure (the guard degrades to
        advisory — a knowledge outage must never block a generate, F1)."""
        if not glossary_entity_ids and not entity_ids:
            return None
        url = f"{self._base_url}/internal/projects/{project_id}/fact-for-check"
        payload: dict[str, Any] = {"at_order": at_order}
        if glossary_entity_ids:
            payload["glossary_entity_ids"] = list(glossary_entity_ids)
        if entity_ids:
            payload["entity_ids"] = list(entity_ids)
        try:
            resp = await self._http.post(url, json=payload, headers=self._internal_headers())
            if resp.status_code != 200:
                logger.warning("knowledge fact-for-check → %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("knowledge fact-for-check unavailable: %s", exc)
            return None

    async def _jwt_get_list(
        self, path: str, params: dict[str, Any], bearer: str, *, key: str, label: str,
    ) -> list[dict[str, Any]]:
        url = f"{self._base_url}{path}"
        try:
            resp = await self._http.get(url, params=params, headers=self._bearer_headers(bearer))
            if resp.status_code != 200:
                logger.warning("knowledge %s → %d", label, resp.status_code)
                return []
            return resp.json().get(key, [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("knowledge %s unavailable: %s", label, exc)
            return []


def init_knowledge_client() -> KnowledgeClient:
    global _client
    if _client is None:
        _client = KnowledgeClient(
            settings.knowledge_internal_url, settings.internal_service_token,
        )
    return _client


def get_knowledge_client() -> KnowledgeClient:
    return _client or init_knowledge_client()


async def close_knowledge_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
