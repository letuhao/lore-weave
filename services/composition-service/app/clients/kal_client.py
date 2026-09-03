"""KAL (knowledge-gateway) client — the single versioned knowledge READ boundary.

INV-KAL (spec §12.5.5): composition-service does NOT read the glossary EAV or the
KG directly, and does NOT call the owning services' ``/internal/*`` knowledge
routes for data the KAL exposes. Those reads (roster, facts, canonical, search,
timeline, neighborhood) go through this client → the knowledge-gateway typed
contract (``contracts/api/knowledge-gateway/kal.v1.yaml``).

Auth (mirrors the gateway's ``InternalTokenGuard`` + ``downstream.ts``): every call
presents ``X-Internal-Token`` (service-to-service) and forwards the caller's
``X-User-Id`` for tenancy. Composition must still verify book ownership upstream
(SEC2 chokepoint) before reaching these book-scoped reads — the internal token
trusts the caller, not the user.

v1 semantics == today's current projection (latest-valid facts), so this migration
is BEHAVIOR-PRESERVING: ``roster`` wraps the exact glossary
``/internal/books/{id}/entities`` list the old ``GlossaryClient.list_entities``
hit, projected to ``{entity_id, name}``. The one real fix here (D4 / §12.5.2):
``roster`` is *bounded-per-page, complete-in-aggregate* — we DRAIN ``next_cursor``
to completion so the cast list is no longer silently truncated at one page.

Graceful degradation (the planner ``_cast_roster`` contract): any transport error /
non-200 yields the partial-so-far (or empty) result and never raises — a KAL
outage thins the roster, it does not 500 a /decompose.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from loreweave_internal_client import build_internal_client

from app.config import settings
from app.logging_config import trace_id_var

logger = logging.getLogger(__name__)

# Safety cap on the keyset drain (§12.5.2: the roster is a snapshot as-of drain-start
# with a monotonic-id cursor). A bounded cap prevents an infinite loop on a
# pathological/never-null cursor; 200 pages × the 200/page server default (max 500)
# covers tens of thousands of entities — far past any real book's cast.
_ROSTER_MAX_PAGES = 200
_ROSTER_PAGE_LIMIT = 200

_client: "KalClient | None" = None


class RosterIncomplete(Exception):
    """Raised by ``roster(strict=True)`` when the keyset drain could NOT complete (a mid-drain
    transport/HTTP failure, a stuck cursor, or the page cap). A COMPLETE drain — even an empty
    cast — never raises. Callers that validate against the cast as authoritative (the commit
    path) use strict mode so a TRUNCATED cast can't false-reject a valid entity in a dropped
    page; degrade-tolerant callers (the packer's thin-roster hints) use the default non-strict
    mode and accept the partial-so-far list."""


class KalClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        # W3: shared factory bakes X-Internal-Token + JSON + per-request X-Trace-Id
        # (trace_id_var). The per-request X-User-Id tenancy header stays in _headers.
        self._http = build_internal_client(
            base_url, internal_token=internal_token,
            timeout_s=timeout_s, trace_id_provider=trace_id_var.get,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self, user_id: UUID | str | None) -> dict[str, str]:
        # X-Internal-Token + X-Trace-Id are baked into the client; only the
        # per-request X-User-Id tenancy header is added here (merged by httpx).
        if user_id is not None:
            return {"X-User-Id": str(user_id)}
        return {}

    async def roster(
        self, book_id: UUID, *, user_id: UUID | str | None = None, strict: bool = False,
    ) -> list[dict[str, Any]]:
        """The book's full cast — ``[{entity_id, name}, ...]`` — drained across the
        keyset cursor to completion (D4 fix: the old ``list_entities`` path read only
        the first page and ignored ``next_cursor``, truncating the cast).

        Bounded-but-complete (§12.5.2): each page is bounded; we follow ``next_cursor``
        until it is null (or the safety cap). In the default (``strict=False``) mode a
        mid-drain failure degrades to the partial-so-far list — never raises (the packer
        tolerates a thin roster). In ``strict=True`` mode an INCOMPLETE drain raises
        ``RosterIncomplete`` so a caller that treats the cast as authoritative (commit-time
        entity validation) skips rather than validating against a TRUNCATED set (which would
        false-reject a valid entity in a dropped page). A complete-but-empty cast never raises.
        """
        url = f"{self._base_url}/v1/kal/books/{book_id}/roster"
        out: list[dict[str, Any]] = []
        cursor: str | None = None

        def _partial(reason: str) -> list[dict[str, Any]]:
            if strict:
                raise RosterIncomplete(reason)
            return out

        for _ in range(_ROSTER_MAX_PAGES):
            params: dict[str, Any] = {"limit": _ROSTER_PAGE_LIMIT}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = await self._http.get(url, params=params, headers=self._headers(user_id))
            except httpx.HTTPError as exc:
                logger.warning("kal roster unavailable (partial drain): %s", exc)
                return _partial(f"transport: {exc}")
            if resp.status_code != 200:
                logger.warning("kal roster → %d (partial drain)", resp.status_code)
                return _partial(f"status {resp.status_code}")
            try:
                data = resp.json()
            except (ValueError, AttributeError) as exc:
                logger.warning("kal roster bad JSON: %s", exc)
                return _partial("bad json")
            items = data.get("items", []) if isinstance(data, dict) else []
            for e in items:
                eid, name = e.get("entity_id"), e.get("name")
                if eid and name:
                    # A3 — carry the entity KIND through when the gateway provides it (optional;
                    # None on an older gateway → degrade-safe, callers treat kind as a hint).
                    out.append({"entity_id": str(eid), "name": name, "kind": e.get("kind")})
            nxt = data.get("next_cursor") if isinstance(data, dict) else None
            if not nxt:
                return out  # COMPLETE drain (even if out is empty)
            if nxt == cursor:
                # Server echoed the same cursor — a stuck/buggy cursor. Stop rather than
                # re-fetch the same page forever; an incomplete drain in strict mode.
                logger.warning("kal roster stuck cursor for book %s — stopping", book_id)
                return _partial("stuck cursor")
            cursor = nxt
        logger.warning(
            "kal roster drain hit the %d-page safety cap for book %s (cast may be incomplete)",
            _ROSTER_MAX_PAGES, book_id,
        )
        return _partial("page cap")
    async def cast(
        self, book_id: UUID, *, user_id: UUID | str | None = None, strict: bool = False,
    ) -> list[dict[str, Any]]:
        """The book's cast WITH SURFACE FORMS — ``[{entity_id, name, aliases, kind}, ...]``,
        drained across the keyset cursor to completion exactly like ``roster``.

        ``roster`` cannot serve this. It is **deliberately** projection-restricted to
        id+name+kind — the gateway says widening it "would put aliases and descriptions on the
        enumeration path every indexing pass walks" — and an alias-free name set is worse than
        no name set for `audit_names`: every alias an author legitimately uses comes back as an
        invented name. `name_grounding`'s own note says which error direction matters ("a name
        missing from `known` becomes a false accusation an author reads"), so the completeness
        check needs the richer projection, which is what ``cast`` is for.

        ``strict=True`` raises ``RosterIncomplete`` on a partial drain, and callers that treat
        the cast as AUTHORITATIVE must use it: a truncated set does not merely miss names, it
        actively accuses the ones it dropped.
        """
        url = f"{self._base_url}/v1/kal/books/{book_id}/cast"
        out: list[dict[str, Any]] = []
        cursor: str | None = None

        def _partial(reason: str) -> list[dict[str, Any]]:
            if strict:
                raise RosterIncomplete(reason)
            return out

        for _ in range(_ROSTER_MAX_PAGES):
            params: dict[str, Any] = {"limit": _ROSTER_PAGE_LIMIT}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = await self._http.get(url, params=params, headers=self._headers(user_id))
            except httpx.HTTPError as exc:
                logger.warning("kal cast unavailable (partial drain): %s", exc)
                return _partial(f"transport: {exc}")
            if resp.status_code != 200:
                logger.warning("kal cast → %d (partial drain)", resp.status_code)
                return _partial(f"status {resp.status_code}")
            try:
                data = resp.json()
            except (ValueError, AttributeError) as exc:
                logger.warning("kal cast bad JSON: %s", exc)
                return _partial("bad json")
            items = data.get("items", []) if isinstance(data, dict) else []
            for e in items:
                eid = e.get("entity_id")
                name = e.get("name") or e.get("cached_name")
                if not (eid and name):
                    continue
                # Both alias keys are accepted for the same reason the gateway accepts both:
                # the LIST endpoint returns `aliases` while by-ids/select-for-context return
                # `cached_aliases`, and reading only one of them is how "36 entities, 0 with a
                # surface form" shipped once already.
                raw = e.get("aliases")
                if not isinstance(raw, list):
                    raw = e.get("cached_aliases")
                out.append({
                    "entity_id": str(eid),
                    "name": name,
                    "aliases": [a for a in (raw or []) if isinstance(a, str) and a.strip()],
                    "kind": e.get("kind"),
                })
            nxt = data.get("next_cursor") if isinstance(data, dict) else None
            if not nxt:
                return out  # COMPLETE drain (even if out is empty)
            if nxt == cursor:
                logger.warning("kal cast stuck cursor for book %s — stopping", book_id)
                return _partial("stuck cursor")
            cursor = nxt
        logger.warning(
            "kal cast drain hit the %d-page safety cap for book %s (cast may be incomplete)",
            _ROSTER_MAX_PAGES, book_id,
        )
        return _partial("page cap")



    async def cast_by_ids(
        self, book_id: UUID, entity_ids: list[str], *,
        user_id: UUID | str | None = None,
    ) -> list[dict[str, Any]]:
        """The identity of specific entities IN THIS BOOK — ``[{entity_id, name, aliases, kind}]``.

        Added 2026-09-04 by the merge with `feat/frontend-tools-mcp-migration`, which brought a
        `composition_entity_override_add` target check that read glossary-service's
        `/internal/books/{book}/entities/by-ids` DIRECTLY. `authored-catalog-reader-gate` caught
        it, and correctly: that file's roster read had already been migrated onto the KAL, so the
        new read was a regression against the direction of travel rather than a fresh debt to
        baseline. This is the missing rung it needed.

        ⚠️ **IT RAISES, AND THAT IS THE WHOLE POINT.** Its caller is about to WRITE on the
        strength of the answer, so "I could not ask" must never arrive looking like "it is not
        there" — the same contract the direct client spelled as `_or_raise`. `cast` degrades to
        a partial list because its callers want names; this one has no partial worth having.

        BOOK-SCOPED, and that is load-bearing rather than incidental: an entity that does not
        exist and one belonging to ANOTHER book are both simply absent from this book's items and
        earn the same refusal, which is what H13 wants — telling them apart would be an existence
        oracle for a book the caller may not own.
        """
        if not entity_ids:
            return []
        url = f"{self._base_url}/v1/kal/books/{book_id}/cast/by-ids"
        try:
            resp = await self._http.post(
                url, json={"entity_ids": [str(e) for e in entity_ids]},
                headers=self._headers(user_id))
        except httpx.HTTPError as exc:
            raise RosterIncomplete(f"transport: {exc}") from exc
        if resp.status_code != 200:
            raise RosterIncomplete(f"status {resp.status_code}")
        try:
            data = resp.json()
        except (ValueError, AttributeError) as exc:
            raise RosterIncomplete("bad json") from exc
        items = data.get("items", []) if isinstance(data, dict) else []
        out: list[dict[str, Any]] = []
        for e in items:
            eid = e.get("entity_id")
            if not eid:
                continue
            # Both alias keys, for the reason `cast` states one method up: the LIST endpoint
            # returns `aliases` while by-ids returns `cached_aliases`.
            raw = e.get("aliases")
            if not isinstance(raw, list):
                raw = e.get("cached_aliases")
            out.append({
                "entity_id": str(eid),
                "name": e.get("name") or e.get("cached_name"),
                "aliases": [a for a in (raw or []) if isinstance(a, str)],
                "kind": e.get("kind"),
            })
        return out

    async def state(
        self, book_id: UUID, *, as_of: int, user_id: UUID | str | None = None,
    ) -> list[dict[str, Any]]:
        """The whole cast AS OF story position ``as_of`` — ``[{entity_id, facts: [...]}, ...]``,
        one value per (entity, attribute).

        This is the read ``roster`` cannot be. ``roster`` enumerates every entity that ever
        existed in the book, with no position, so a drafting run at chapter 12 grounds on the
        END of the book: characters who die in chapter 40 are alive, ranks are the final ones,
        and a betrayal three chapters ahead is already canon. ``state`` answers what was true
        AT the position being written.

        ``as_of`` is REQUIRED and is the chapter's ``sort_order`` — the book position, the same
        axis ``valid_from_ordinal`` is written on (extraction sources it from book-service's
        ``sort_order``, deliberately, after a job-relative index was found colliding). Passing a
        job-relative or list index here would silently answer about a different chapter.

        Degradation matches ``roster`` non-strict: any transport error / non-200 / bad JSON
        yields ``[]`` and logs, never raises — a KAL outage leaves a drafting run ungrounded
        (legacy behaviour) rather than 500-ing it. A 400 from the service means the position was
        rejected, which is a CALLER bug and is logged as such.
        """
        url = f"{self._base_url}/v1/kal/books/{book_id}/state"
        try:
            resp = await self._http.get(
                url, params={"as_of": int(as_of)}, headers=self._headers(user_id))
        except httpx.HTTPError as exc:
            logger.warning("kal state@%s unavailable for book %s: %s", as_of, book_id, exc)
            return []
        if resp.status_code == 400:
            # The service owns the required-position rule; a 400 here is composition asking
            # wrongly, not the service failing. Distinguished from a generic non-200 so it
            # cannot hide in the outage bucket.
            logger.warning(
                "kal state → 400 for book %s at as_of=%r — the story position was REFUSED "
                "(missing/negative); the run will be ungrounded", book_id, as_of)
            return []
        if resp.status_code != 200:
            logger.warning("kal state@%s → %d for book %s", as_of, resp.status_code, book_id)
            return []
        try:
            data = resp.json()
        except (ValueError, AttributeError) as exc:
            logger.warning("kal state@%s bad JSON for book %s: %s", as_of, book_id, exc)
            return []
        entities = data.get("entities", []) if isinstance(data, dict) else []
        if not isinstance(entities, list):
            # Same strictness the gateway applies downstream: an object keyed by id is not the
            # bounded list the contract promises, and iterating it yields keys, not entities.
            logger.warning("kal state@%s returned a non-list `entities` for book %s", as_of, book_id)
            return []
        logger.info(
            "kal state resolved: book=%s as_of=%s entities=%d", book_id, as_of, len(entities))
        return [e for e in entities if isinstance(e, dict) and e.get("entity_id")]
    async def append_role_fact(
        self,
        book_id: UUID,
        *,
        subject_entity_id: UUID | str,
        predicate: str,
        object_value: str,
        valid_from_ordinal: int,
        source_episode_id: UUID | str | None = None,
        user_id: UUID | str | None = None,
        writeback_key: str | None = None,
        origin: str = "author",
    ) -> dict[str, Any]:
        """T37 — composition's FIRST write to the KAL. Appends one role as a
        `fact_kind='relation'` fact carrying a story interval.

        **This is the write T36 defined and nothing performed.** `entity_facts_kind_chk` has
        always admitted `'relation'` and `appendFact` has always written any kind; measured
        2026-08-11 the graph held `attribute 41435 · name 5189 · alias 1868 · **relation 0**`.
        A schema that permits a row and a writer that never emits one look identical from the
        database, which is why the count was the measurement that scoped this task.

        Roles are **plan-authored, not extracted** (Q2), so composition — which is where a
        plan decides who betrays whom and when — is the producer. `valid_from_ordinal` is
        REQUIRED here rather than optional, unlike the KG's `recreate_relation`: T36 Half 3
        found that the authoring path had no story axis at all, and that author-declared
        roles were therefore exactly the ones the canon check could never see (an as-of read
        excludes positionless edges by design). Making it required means this producer cannot
        reintroduce that class of invisible role.

        Idempotency is the KAL's, not ours: the append is `ON CONFLICT DO NOTHING` on
        `UNIQUE(entity_id, fact_kind, attr_or_predicate, value_hash, valid_from_ordinal,
        source_episode_id)`, so re-authoring the same role at the same position is a no-op
        and returns the existing fact. `writeback_key` is the Path-A gate when a caller needs
        a second idempotency scope.

        Raises `httpx.HTTPStatusError` on a 4xx/5xx. Deliberately NOT degrade-tolerant, the
        opposite of `roster`: a dropped role is a canon fact that silently never existed, and
        the guard would then pass a scene it should have questioned. A read may degrade; a
        write may not.
        """
        url = f"{self._base_url}/v1/kal/books/{book_id}/facts"
        body: dict[str, Any] = {
            "entity_id": str(subject_entity_id),
            "fact_kind": "relation",
            "attr_or_predicate": predicate,
            "value": object_value,
            "valid_from_ordinal": valid_from_ordinal,
            # T37c — WHICH producer wrote this, so one can retract its own claims without
            # touching another's. Defaults to `author` because that is the conservative one:
            # an author-marked fact is never closed by a plan revision, so a caller that
            # forgets to say gets its role KEPT rather than silently retracted later. The
            # dangerous default would be `plan`.
            "origin": origin,
        }
        # ⚠️ OMITTED when absent, never sent as null or as a fresh UUID. `entity_facts
        # .source_episode_id` carries a FOREIGN KEY to `episodes`, so an invented id is a
        # 500 — which is exactly how the T37 live smoke failed: the producer minted one
        # because the contract declares the field `required`, and nothing below HTTP could
        # tell an author-declared role from an extracted one.
        #
        # A plan-authored role HAS no episode (Q2: "plan-authored, not extracted"). NULL is
        # the shape the core already expects — its ON CONFLICT reads
        # `coalesce(source_episode_id, '000…')`, which only makes sense if NULL is normal.
        if source_episode_id is not None:
            body["source_episode_id"] = str(source_episode_id)
        if writeback_key is not None:
            body["writeback_key"] = writeback_key
        resp = await self._http.post(url, json=body, headers=self._headers(user_id))
        resp.raise_for_status()
        return resp.json()



    async def open_facts_for(
        self, book_id: UUID, entity_id: UUID | str, *,
        user_id: UUID | str | None = None,
    ) -> list[dict[str, Any]]:
        """The entity's currently-OPEN facts (`valid_to_ordinal IS NULL`), each carrying its
        `origin` (T37d).

        `origin` is what makes a retraction path possible at all: the close must find the
        facts ITS producer wrote and leave every other producer's alone. Before chain step
        0066 the read did not expose it, so "close what this plan no longer implies" was
        undecidable at the only layer that can decide it.

        Degrade-tolerant, like `roster` and unlike the writes: a close that cannot see the
        current state must do NOTHING rather than guess. Returning `[]` on failure means the
        caller retracts nothing, which is the safe direction — the alternative is closing
        roles because a read timed out.
        """
        url = f"{self._base_url}/v1/kal/books/{book_id}/entities/{entity_id}/facts"
        try:
            resp = await self._http.get(url, headers=self._headers(user_id))
            resp.raise_for_status()
            return list(resp.json().get("items") or [])
        except Exception:  # noqa: BLE001 — see the docstring: blind means do nothing
            logger.warning("kal: open_facts_for failed entity=%s", entity_id, exc_info=True)
            return []

    async def close_fact(
        self, book_id: UUID, *, fact_id: str, valid_to_ordinal: int,
        user_id: UUID | str | None = None,
    ) -> dict[str, Any]:
        """Valid-time close (supersede) at a story position — `POST facts/close` (§12.3.2).

        NOT an invalidation: the fact stays true for the interval it covered, and an as-of
        read before `valid_to_ordinal` still returns it. That distinction is the whole reason
        a plan revision closes rather than deletes — the chapters written under the old plan
        did happen, and their canon checks must still see the role that was in force then.

        Raises on a non-2xx. The caller decides whether to tolerate it; `close_stale_planned_roles`
        does, for the same reason the rest of the pipeline degrades.
        """
        url = f"{self._base_url}/v1/kal/books/{book_id}/facts/close"
        resp = await self._http.post(
            url, json={"fact_id": str(fact_id), "valid_to_ordinal": valid_to_ordinal},
            headers=self._headers(user_id),
        )
        resp.raise_for_status()
        return resp.json()


def init_kal_client() -> KalClient:
    global _client
    if _client is None:
        _client = KalClient(settings.knowledge_gateway_url, settings.internal_service_token)
    return _client


def get_kal_client() -> KalClient:
    return _client or init_kal_client()


async def close_kal_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
