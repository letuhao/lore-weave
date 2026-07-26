"""HTTP client for glossary-service's /internal/books/{id}/select-for-context.

Graceful degradation is the contract: every failure path (timeout,
5xx, 4xx, connection error, decode error) returns an empty list and
logs a warning. The caller never sees an exception — chat should keep
working with a smaller context when glossary-service is unavailable.

The async client is long-lived and created in the knowledge-service
lifespan so it can pool connections. Tests substitute a fake via
FastAPI dependency_overrides rather than hitting the real URL.
"""

import logging
import time
from typing import Literal
from uuid import UUID

import httpx
from loreweave_internal_client import build_internal_client
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.logging_config import trace_id_var
from app.metrics import circuit_open as circuit_open_gauge

__all__ = [
    "KNOWN_ENTITIES_MAX_PAGE",
    "KNOWN_ENTITIES_MAX_PAGES",
    "GlossaryClient",
    "GlossaryEntityForContext",
]

logger = logging.getLogger(__name__)

# The known-entities handler caps `limit` at 500 (its own default is a silent 50).
KNOWN_ENTITIES_MAX_PAGE = 500
# Runaway guard for the paging walk: 40 × 500 = 20k entities. Hitting it reports
# `truncated=True` rather than silently under-reading (no silent caps).
KNOWN_ENTITIES_MAX_PAGES = 40


class GlossaryEntityForContext(BaseModel):
    """Mirror of glossary-service's selectForContext row (K2b)."""

    model_config = ConfigDict(extra="ignore")

    entity_id: str
    cached_name: str | None = None
    cached_aliases: list[str] = Field(default_factory=list)
    short_description: str | None = None
    kind_code: str
    is_pinned: bool = False
    tier: str = ""
    rank_score: float = 0.0


class GlossaryClient:
    """Thin async wrapper around httpx.AsyncClient.

    One instance per knowledge-service process, shared across requests.
    Close via `await client.aclose()` on shutdown.
    """

    # K6.4 — hand-rolled circuit breaker. Matches the tone of the K5
    # retry loop: ~40 lines of state machine rather than pulling in
    # `purgatory`. Three states, all encoded in two fields:
    #
    #   _cb_opened_at is None        → closed (normal operation)
    #   _cb_opened_at is set, cooldown elapsing → open (fast-fail)
    #   _cb_opened_at is set, cooldown elapsed  → half-open (probe)
    #
    # Thread-safety: asyncio is single-threaded within a worker, so
    # no lock is needed. Multi-worker deployments each own their own
    # breaker state (K4-I1 / K5-I9 pattern).
    _CB_THRESHOLD = 3
    _CB_COOLDOWN_S = 60.0

    def __init__(self, base_url: str, internal_token: str, timeout_s: float, retries: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._retries = max(0, retries)
        # K4-I5: token is baked into the client headers — no need for a separate
        # field. W3/W4: the shared factory also bakes JSON + injects X-Trace-Id per
        # request (trace_id_var), replacing the hand-rolled per-method trace threading.
        # The circuit-breaker state below is unchanged (transport-only swap).
        self._http = build_internal_client(
            base_url, internal_token=internal_token,
            timeout_s=timeout_s, trace_id_provider=trace_id_var.get,
        )
        self._cb_fail_count = 0
        self._cb_opened_at: float | None = None
        # D-T2-05 — when the cooldown has elapsed, the breaker is
        # half-open and at most ONE caller gets to probe the
        # upstream. Without this flag, every concurrent caller that
        # arrived during the cooldown would all fire simultaneous
        # probes the instant it ended and the breaker would see N
        # failures at once. With the flag, the first arrival claims
        # the probe, the rest short-circuit, and we preserve the
        # "one probe per half-open window" invariant. Atomic in
        # single-threaded asyncio (the claim happens without any
        # intervening `await`).
        self._cb_probe_in_flight = False

    async def aclose(self) -> None:
        await self._http.aclose()

    def _cb_enter(self) -> Literal["closed", "probe", "open"]:
        """Atomic breaker-state check + probe claim (no `await`).

        Returns:
          "closed" — breaker healthy, caller proceeds normally.
          "probe"  — cooldown elapsed AND no probe in flight; THIS
                     caller is the single probe. Caller MUST release
                     via `_cb_exit_probe()` in a `finally` block.
          "open"   — short-circuit: either still inside cooldown OR
                     another caller is already probing.

        Concurrent callers hitting the half-open window are serialized
        by the event loop scheduler — only one returns "probe", the
        rest see the flag already set and return "open". D-T2-05.
        """
        if self._cb_opened_at is None:
            return "closed"
        if time.monotonic() - self._cb_opened_at < self._CB_COOLDOWN_S:
            return "open"
        # Cooldown elapsed — try to claim the half-open probe slot.
        if self._cb_probe_in_flight:
            return "open"
        self._cb_probe_in_flight = True
        logger.debug(
            "glossary circuit breaker half-open: probe claimed"
        )
        return "probe"

    def _cb_exit_probe(self) -> None:
        """Release the half-open probe slot regardless of outcome.

        Must be called in a `finally` block by whichever caller got
        "probe" from `_cb_enter()`. Release is idempotent — calling
        twice is a no-op."""
        self._cb_probe_in_flight = False

    def _cb_record_success(self) -> None:
        if self._cb_opened_at is not None:
            logger.info("glossary circuit breaker closed (probe succeeded)")
        self._cb_fail_count = 0
        self._cb_opened_at = None
        # Defense-in-depth: the `finally` block in the caller already
        # releases this, but resetting here too means a future
        # refactor that detaches success-recording from the probe
        # release path can't leave a stale flag.
        self._cb_probe_in_flight = False
        circuit_open_gauge.labels(service="glossary").set(0)

    def _cb_record_failure(self) -> None:
        self._cb_fail_count += 1
        if self._cb_fail_count >= self._CB_THRESHOLD:
            if self._cb_opened_at is None:
                logger.warning(
                    "glossary circuit breaker opened after %d consecutive failures",
                    self._cb_fail_count,
                )
            # Reset the clock on every failure so a half-open probe
            # that fails extends the cooldown by another full window.
            self._cb_opened_at = time.monotonic()
            circuit_open_gauge.labels(service="glossary").set(1)

    async def select_for_context(
        self,
        *,
        user_id: UUID,
        book_id: UUID,
        query: str,
        max_entities: int = 20,
        max_tokens: int = 800,
        exclude_ids: list[str] | None = None,
        language: str | None = None,
    ) -> list[GlossaryEntityForContext]:
        """POST /internal/books/{book_id}/select-for-context.

        Returns an empty list on any failure — never raises. The caller
        treats missing glossary as "degrade silently".

        `language` (S6, optional): when set, entity aliases are augmented with the
        per-language alias set for that language (source ∪ target). Omitted →
        source-language aliases only.
        """
        url = f"{self._base_url}/internal/books/{book_id}/select-for-context"
        body = {
            "user_id": str(user_id),
            "query": query or "",
            "max_entities": int(max_entities),
            "max_tokens": int(max_tokens),
            "exclude_ids": exclude_ids or [],
        }
        if language:
            body["language"] = language

        # K6.4 — circuit breaker gate. `_cb_enter` returns one of three
        # states: "closed" (breaker healthy, proceed), "probe" (this
        # caller is the single half-open probe and must release the
        # claim in finally), or "open" (fast-fail, return []). D-T2-05
        # adds the single-probe guarantee: concurrent callers during
        # the half-open window are serialized so only one hits the
        # upstream; others short-circuit instead of dog-piling.
        cb_state = self._cb_enter()
        if cb_state == "open":
            return []
        probe_claimed = cb_state == "probe"

        # K7e: the inbound trace id is forwarded to glossary-service (so it can
        # stitch its logs to the originating chat turn) by the client's baked
        # X-Trace-Id request hook — no per-call header assembly needed.
        try:
            # K4-I4: log AT MOST one warning per call. Per-attempt
            # logging used to spam logs during outages (N candidates ×
            # M retries × every chat turn). Now: silent on individual
            # retries, one consolidated warning at the end if we
            # couldn't get a result.
            attempts = self._retries + 1
            last_err_summary: str | None = None
            for _ in range(attempts):
                try:
                    resp = await self._http.post(url, json=body)
                except httpx.TimeoutException:
                    last_err_summary = "timeout"
                    continue
                except httpx.HTTPError as exc:
                    last_err_summary = f"transport: {type(exc).__name__}"
                    continue

                if resp.status_code >= 500:
                    last_err_summary = f"{resp.status_code}"
                    continue

                if resp.status_code >= 400:
                    # 4xx is not retried — stable request problem.
                    # Breaker state unchanged: upstream IS responsive,
                    # just rejecting this specific call. The probe
                    # slot is released in the finally block, so a
                    # subsequent caller during the same half-open
                    # window can immediately claim a fresh probe
                    # (correct: the service is up, we have no reason
                    # to keep the breaker holding closed callers off).
                    logger.warning(
                        "glossary client %d (no retry) body=%s",
                        resp.status_code, resp.text[:200],
                    )
                    return []

                try:
                    data = resp.json()
                except Exception as exc:
                    logger.warning("glossary client decode failure: %s", exc)
                    return []

                entities_raw = data.get("entities") if isinstance(data, dict) else None
                if not isinstance(entities_raw, list):
                    logger.warning("glossary client unexpected payload shape")
                    return []

                parsed: list[GlossaryEntityForContext] = []
                for row in entities_raw:
                    try:
                        parsed.append(GlossaryEntityForContext.model_validate(row))
                    except Exception as exc:
                        logger.warning("glossary client row validate skip: %s", exc)
                # Success path — this is the only place the breaker closes.
                # 4xx / decode / shape failures return [] above but do NOT
                # record success, because the upstream service IS
                # responsive — they just indicate a bad request, which
                # shouldn't hold the breaker open either way.
                self._cb_record_success()
                return parsed

            # All attempts exhausted — single warning summarising the failure.
            # This IS a breaker-worthy failure (service is unreachable or
            # consistently 5xx).
            self._cb_record_failure()
            logger.warning(
                "glossary client unavailable after %d attempts: %s",
                attempts, last_err_summary or "unknown",
            )
            return []
        finally:
            # Always release the probe slot — success, failure,
            # cancellation, or any unexpected exception. Lets the next
            # half-open caller probe in the next cooldown window.
            if probe_claimed:
                self._cb_exit_probe()

    async def count_entities(self, book_id: UUID) -> int | None:
        """GET /internal/books/{book_id}/entity-count.

        K16.2 cost estimation helper. Returns entity count or None on
        failure. Does NOT use the circuit breaker — cost estimation is
        user-initiated and not on the chat hot path.
        """
        url = f"{self._base_url}/internal/books/{book_id}/entity-count"
        try:
            resp = await self._http.get(
                url,
            )
            if resp.status_code != 200:
                logger.warning("glossary entity-count %d", resp.status_code)
                return None
            return int(resp.json().get("count", 0))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("glossary entity-count failed: %s", exc)
            return None

    async def get_entity_stats(self, book_id: UUID) -> dict | None:
        """GET /internal/books/{book_id}/entities/stats (C13).

        Per-entity mention-span + coverage aggregate over chapter_entity_links,
        for the build-wizard auto-pin suggestion banner. Returns the raw
        ``{"items": [...], "chapter_count": int}`` payload, or None on failure
        (the FE degrades to manual pinning — never blocks the wizard).
        """
        url = f"{self._base_url}/internal/books/{book_id}/entities/stats"
        try:
            resp = await self._http.get(
                url,
            )
            if resp.status_code != 200:
                logger.warning("glossary entities/stats %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("glossary entities/stats failed: %s", exc)
            return None

    # ── K11.10 — HTTP methods for extraction pipeline ────────────────

    async def list_entities(
        self,
        book_id: UUID,
        *,
        status_filter: str | None = None,
        min_frequency: int = 2,
        limit: int | None = None,
        offset: int = 0,
        include_dead: bool = False,
    ) -> list[dict] | None:
        """GET /internal/books/{book_id}/known-entities. One PAGE of entities.

        Returns None on failure. Prefer :meth:`list_all_entities` when "every
        entity" is meant — this method returns at most one server page.

        ``min_frequency`` gates on chapter-appearance count (the Go handler's
        ``HAVING COUNT(cl.link_id) >= min_frequency``, default 2 — the
        extraction-anchor semantics). Callers that want EVERY entity regardless of
        chapter spread (e.g. wiki generation on a low-chapter book, or the WS-4B
        prose-less graph projection) must pass **0**: the chapter join is a LEFT
        JOIN, so an entity with no chapter links has COUNT=0 and even `1` excludes it.

        ``limit`` maps to the handler's ``limit`` — whose default is **50** (capped
        at 500). ``offset`` pages beyond it (the handler's ORDER BY carries a
        deterministic ``e.entity_id`` tiebreak, so paging is stable).

        ``include_dead``: the handler defaults to ``alive=true``, which filters out
        narratively-DEAD entities (`alive` is a story flag, NOT a review status).
        Pass True to include them — a dead character is still a graph node.

        ``status_filter``: one of ``active|inactive|draft|rejected``; **None (the
        default) applies no status filter** — which is what every caller has always
        effectively gotten, because the handler historically ignored this parameter
        (D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM, now fixed server-side).
        """
        url = f"{self._base_url}/internal/books/{book_id}/known-entities"
        params: dict[str, str] = {"min_frequency": str(min_frequency)}
        if status_filter:
            params["status"] = status_filter
        if limit is not None:
            params["limit"] = str(limit)
        if offset:
            params["offset"] = str(offset)
        if include_dead:
            params["alive"] = "false"  # handler: alive != "false" ⇒ require alive
        try:
            resp = await self._http.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("glossary list-entities %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("glossary list-entities failed: %s", exc)
            return None

    async def list_all_entities(
        self,
        book_id: UUID,
        *,
        status_filter: str | None = None,
        min_frequency: int = 2,
        include_dead: bool = False,
        page_size: int = KNOWN_ENTITIES_MAX_PAGE,
        max_pages: int = KNOWN_ENTITIES_MAX_PAGES,
    ) -> tuple[list[dict], bool] | None:
        """Walk EVERY page of `known-entities` (D-ANCHOR-PRELOAD-50-CAP).

        The handler's `limit` defaults to 50 and is capped at 500, so any caller
        that meant "all entities" and passed no limit was silently truncated at 50
        — extraction's anchor pre-load included, which let the extractor mint
        duplicate nodes for every entity past the 50th. This pages via `offset`
        until a short page arrives.

        Returns ``(rows, truncated)`` — `truncated` True only if `max_pages` was
        exhausted with a full page still coming (a runaway guard; never a silent
        cap). Returns None if the FIRST page fails; a later page failing stops the
        walk and returns what was gathered with ``truncated=True`` (honest partial).
        """
        rows: list[dict] = []
        for page in range(max_pages):
            batch = await self.list_entities(
                book_id,
                status_filter=status_filter,
                min_frequency=min_frequency,
                include_dead=include_dead,
                limit=page_size,
                offset=page * page_size,
            )
            if batch is None:
                if page == 0:
                    return None
                logger.warning(
                    "glossary list_all_entities: page %d failed for book=%s — "
                    "returning %d partial rows", page, book_id, len(rows),
                )
                return rows, True
            rows.extend(batch)
            if len(batch) < page_size:
                return rows, False
        logger.warning(
            "glossary list_all_entities: hit max_pages=%d for book=%s (%d rows) — "
            "more entities remain", max_pages, book_id, len(rows),
        )
        return rows, True

    async def list_known_entities_for_chapter(
        self,
        book_id: UUID,
        *,
        before_chapter_index: int,
        recency_window: int = 100,
        min_frequency: int = 2,
        limit: int = 50,
    ) -> list[dict]:
        """P2 — fetch the glossary anchor for ONE chapter position.

        Spec D4. Uses the existing /internal/books/{id}/known-entities
        endpoint with full filtering: alive=true, min_frequency,
        before_chapter_index, recency_window, limit.

        Hard-fail contract (PO choice 4):
          - HTTP 200 -> return list (possibly empty)
          - HTTP 4xx -> raise GlossaryAnchorMalformed (no retry)
          - HTTP 5xx / timeout / network error -> raise GlossaryAnchorUnavailable
            (retry budget applies upstream)
        """
        url = f"{self._base_url}/internal/books/{book_id}/known-entities"
        params = {
            "alive": "true",
            "min_frequency": str(min_frequency),
            "before_chapter_index": str(before_chapter_index),
            "recency_window": str(recency_window),
            "limit": str(limit),
        }
        try:
            resp = await self._http.get(
                url,
                params=params,
            )
        except httpx.HTTPError as exc:
            raise GlossaryAnchorUnavailable(
                f"glossary known-entities transport error: {exc}"
            ) from exc
        if 400 <= resp.status_code < 500:
            raise GlossaryAnchorMalformed(
                f"glossary known-entities {resp.status_code}: {resp.text[:200]}"
            )
        if resp.status_code >= 500:
            raise GlossaryAnchorUnavailable(
                f"glossary known-entities {resp.status_code}: {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise GlossaryAnchorMalformed(
                f"glossary known-entities returned non-JSON: {exc}"
            ) from exc
        # Endpoint returns {"entities": [...], "count": N} OR a plain list
        # (handler variance). Normalize both.
        if isinstance(data, dict):
            return list(data.get("entities") or [])
        if isinstance(data, list):
            return data
        raise GlossaryAnchorMalformed(
            f"glossary known-entities returned unexpected shape: {type(data).__name__}"
        )

    async def _ping_glossary_health(self) -> bool:
        """P2 — explicit health probe at extraction-job start to fail-fast
        if glossary is down BEFORE wasting LLM cycles.

        Returns True if glossary /health returns 200, False otherwise.
        Never raises.
        """
        try:
            resp = await self._http.get(
                f"{self._base_url}/health",
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False


    async def fetch_entities_by_ids(
        self,
        *,
        book_id: UUID,
        entity_ids: list[str],
        language: str | None = None,
    ) -> list[GlossaryEntityForContext]:
        """POST /internal/books/{book_id}/entities/by-ids (mui #4).

        Batch-fetch glossary entities by id so the semantic selector can
        enrich vector hits with canon detail. Best-effort: returns [] on any
        failure — the caller degrades to FTS.

        `language` (S6, optional): augment aliases with the per-language set.
        """
        if not entity_ids:
            return []
        url = f"{self._base_url}/internal/books/{book_id}/entities/by-ids"
        body: dict = {"entity_ids": entity_ids}
        if language:
            body["language"] = language
        try:
            resp = await self._http.post(
                url, json=body,
            )
            if resp.status_code != 200:
                logger.warning("glossary entities/by-ids %d", resp.status_code)
                return []
            data = resp.json()
            return [
                GlossaryEntityForContext.model_validate(it)
                for it in data.get("items", [])
            ]
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("glossary entities/by-ids failed: %s", exc)
            return []

    async def fetch_entity_display_names(
        self,
        *,
        book_id: UUID,
        entity_ids: list[str],
        language: str,
    ) -> dict[str, str]:
        """POST /internal/books/{book_id}/entity-display-names (KG-ML M5 C9).

        Resolve a set of glossary entity ids to their display name in
        ``language``. Returns ``{entity_id: translated_name}`` for ONLY the
        entities that actually had a translation in that language — an entity
        whose name has no translation is omitted (the KG node then keeps its
        canonical name, an honest source-fallback per AC1). Best-effort:
        returns ``{}`` on any failure or an empty input, so the KG graph-view
        degrades to canonical names rather than failing the read.
        """
        if not entity_ids or not language:
            return {}
        url = f"{self._base_url}/internal/books/{book_id}/entity-display-names"
        try:
            resp = await self._http.post(
                url,
                json={"language": language, "entity_ids": entity_ids},
            )
            if resp.status_code != 200:
                logger.warning("glossary entity-display-names %d", resp.status_code)
                return {}
            data = resp.json()
            out: dict[str, str] = {}
            for it in data.get("items", []):
                eid = it.get("entity_id")
                name = it.get("display_name")
                # Only genuinely-translated names override the canonical; an
                # untranslated entity is omitted so name_label stays None.
                if eid and name and it.get("translated"):
                    out[str(eid)] = str(name)
            return out
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("glossary entity-display-names failed: %s", exc)
            return {}

    async def propose_entities(
        self,
        book_id: UUID,
        *,
        entities: list[dict],
        source_language: str = "en",
        attribute_actions: dict | None = None,
        default_tags: list[str] | None = None,
        park_unknown_kinds: bool | None = None,
    ) -> dict | None:
        """POST /internal/books/{book_id}/extract-entities.

        Bulk propose extraction candidates to glossary-service.
        Returns the response or None on failure. Non-blocking — caller
        should queue in extraction_pending on prolonged outage.

        ``default_tags`` (e.g. ``["ai-suggested"]``) marks the created
        entities so the FE can surface them as a reviewable AI-suggestions
        inbox; it also arms glossary's tombstone gate (an ``ai-rejected``
        name is skipped). ``park_unknown_kinds=False`` opts out of the
        glossary 'unknown' review bucket so experimental KG kinds don't
        flood triage (mui #1).
        """
        url = f"{self._base_url}/internal/books/{book_id}/extract-entities"
        body: dict = {
            "source_language": source_language,
            "attribute_actions": attribute_actions or {},
            "entities": entities,
        }
        if default_tags is not None:
            body["default_tags"] = default_tags
        if park_unknown_kinds is not None:
            body["park_unknown_kinds"] = park_unknown_kinds
        try:
            resp = await self._http.post(
                url, json=body,
            )
            if resp.status_code not in (200, 201):
                logger.warning("glossary propose-entities %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("glossary propose-entities failed: %s", exc)
            return None

    async def propose_merge_candidates(
        self,
        book_id: UUID,
        *,
        candidates: list[dict],
    ) -> dict | None:
        """POST /internal/books/{book_id}/merge-candidates (mui #1c G-cand).

        Propose coreference merge clusters discovered by the coref detector
        (K-detect) to glossary, where the human reviews + confirms. Each
        candidate dict: ``{"member_entity_ids": [...],
        "suggested_winner_entity_id"?, "score"?, "evidence"?, "rationale"?}``
        where member ids are glossary entity ids (the KG nodes' anchors).

        Best-effort: returns the response dict, or None on any failure — a
        detection pass must never crash because glossary is briefly down.
        """
        if not candidates:
            return None
        url = f"{self._base_url}/internal/books/{book_id}/merge-candidates"
        try:
            resp = await self._http.post(
                url, json={"candidates": candidates},
            )
            if resp.status_code not in (200, 201):
                logger.warning("glossary propose-merge-candidates %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("glossary propose-merge-candidates failed: %s", exc)
            return None

    async def write_wiki_article(
        self,
        book_id: UUID,
        *,
        body: dict,
    ) -> dict | None:
        """wiki-llm M5 — POST /internal/books/{book_id}/wiki/articles.

        Write an AI-generated article through glossary's clobber-guarded
        writeback. Returns the response dict ({action, article_id,
        generation_status}) or None on any failure (the caller logs + the
        orchestrator decides retry/skip — a writeback miss must not crash a
        batch). `action` distinguishes a direct write from a filed suggestion
        (the human-edited-article guard)."""
        url = f"{self._base_url}/internal/books/{book_id}/wiki/articles"
        try:
            resp = await self._http.post(
                url, json=body,
            )
            if resp.status_code != 200:
                logger.warning("glossary wiki-writeback %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("glossary wiki-writeback failed: %s", exc)
            return None

    async def fetch_wiki_gold_pairs(
        self,
        book_id: UUID,
        *,
        limit: int,
    ) -> list[dict]:
        """D-WIKI-M8-FEWSHOT — GET /internal/books/{book_id}/wiki/gold-pairs.

        Returns up to `limit` recent gold AI→human revision pairs (plaintext, truncated
        server-side) as `[{article_id, entity_id, ai_text, human_text}]`. Best-effort:
        returns [] on ANY failure — missing exemplars must never break generation."""
        url = f"{self._base_url}/internal/books/{book_id}/wiki/gold-pairs"
        try:
            resp = await self._http.get(
                url, params={"limit": limit},
            )
            if resp.status_code != 200:
                logger.warning("glossary wiki-gold-pairs %d", resp.status_code)
                return []
            return resp.json().get("pairs", [])
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("glossary wiki-gold-pairs failed: %s", exc)
            return []

    async def generate_wiki_stubs(
        self,
        book_id: UUID,
        *,
        entity_ids: list[str],
    ) -> dict | None:
        """POST /v1/glossary/books/{book_id}/wiki/generate.

        Propose wiki stubs for extracted entities. Returns None on failure.
        NOTE: this calls a public endpoint (/v1/glossary/...) which
        requires JWT auth. The GlossaryClient sends X-Internal-Token
        instead. Glossary-service must accept internal-token auth on
        this route, or a dedicated /internal/ route is needed.
        """
        url = f"{self._base_url}/v1/glossary/books/{book_id}/wiki/generate"
        try:
            resp = await self._http.post(
                url,
                json={"entity_ids": entity_ids},
            )
            if resp.status_code not in (200, 201):
                logger.warning("glossary wiki-generate %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("glossary wiki-generate failed: %s", exc)
            return None


# ── module-level singleton managed by lifespan ─────────────────────────────

_client: GlossaryClient | None = None


def init_glossary_client() -> GlossaryClient:
    """Instantiate the shared client from settings. Called from lifespan.

    Idempotent: a second call without a prior close_glossary_client()
    returns the existing instance instead of leaking the previous
    httpx.AsyncClient's connection pool (K4-I1).
    """
    global _client
    if _client is not None:
        return _client
    _client = GlossaryClient(
        base_url=settings.glossary_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.glossary_client_timeout_s,
        retries=settings.glossary_client_retries,
    )
    return _client


async def close_glossary_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_glossary_client() -> GlossaryClient:
    if _client is None:
        raise RuntimeError("glossary client not initialised")
    return _client


# ── P2 exception types (placed at module scope after the class) ────────────


class GlossaryAnchorUnavailable(Exception):
    """P2 — glossary anchor fetch failed due to transport / 5xx.

    Caller (leaf_processor) marks the leaf failed + retry budget applies.
    """


class GlossaryAnchorMalformed(Exception):
    """P2 — glossary returned 4xx or malformed JSON.

    Caller surfaces as job error (no retry — not transient).
    """
