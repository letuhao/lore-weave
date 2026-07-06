"""PlanForge auto-bootstrap gate (POC) — propose→record→approve→apply.

See docs/specs/2026-07-06-planforge-auto-bootstrap.md §3.1/§4/§4.1. Kept as
its own module (not folded into the 700+-line `plan_forge_service.py`) since
this is a distinct structural-mutation quarantine subsystem, not a PlanForge
pipeline step.

PROPOSE computes a diff exactly ONCE and persists it; APPLY never re-derives
the diff and never calls an LLM — it only replays the already-approved,
already-persisted plan. This is the whole point of the gate (D-PLANFORGE
auto-bootstrap CLARIFY): a human approves a plan, not a re-negotiated one.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.clients.book_client import BookClient, BookClientError
from app.clients.glossary_client import GlossaryClient, GlossaryClientError
from app.db.models import PlanBootstrapProposal
from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo
from app.db.repositories.plan_runs import PlanRunsRepo

logger = logging.getLogger(__name__)


def _glossary_item_key(kind_code: str | None, name: str | None) -> str:
    return f"glossary:{kind_code or 'character'}:{name}"


class BootstrapService:
    def __init__(
        self,
        proposals: PlanBootstrapProposalsRepo,
        plan_runs: PlanRunsRepo,
        book: BookClient,
        glossary: GlossaryClient,
    ) -> None:
        self._proposals = proposals
        self._runs = plan_runs
        self._book = book
        self._glossary = glossary

    async def propose(
        self, owner_user_id: UUID, book_id: UUID, run_id: UUID, bearer: str,
    ) -> PlanBootstrapProposal:
        """One deterministic diff pass — zero LLM calls for this scope (the
        diff is title-matched against real chapters + every non-rejected
        prior proposal for this book; see §4.1.3 for why title, not a
        stable id, is the accepted POC-scope key, and §6 M1 for why
        dedup covers PENDING/APPROVED proposals too, not just APPLIED
        ones — a still-open proposal already claims its event_ids; without
        this, calling propose() twice before applying the first would
        silently double-offer (and, if both got applied, double-create)
        the same chapters)."""
        run = await self._runs.get_for_owner(owner_user_id, book_id, run_id)
        if run is None:
            raise LookupError("run not found")

        pkg_art = await self._runs.latest_artifact(owner_user_id, run_id, "package")
        package = pkg_art.content.get("planning_package") if pkg_art else None
        if not package:
            raise ValueError("run has no compiled package yet — call compile() first")

        package_chapters: list[dict[str, Any]] = package.get("chapters", [])
        glossary_seeds: list[dict[str, Any]] = pkg_art.content.get("glossary_seeds", [])

        existing = await self._book.list_chapters(book_id, bearer)
        existing_titles = {c["title"] for c in existing if c.get("title")}

        active_records = await self._proposals.list_active_for_book(book_id)
        claimed_titles: set[str] = set()
        claimed_glossary_keys: set[str] = set()
        for rec in active_records:
            for ch in rec.diff.get("new_chapters", []):
                title = ch.get("title") if isinstance(ch, dict) else None
                if title:
                    claimed_titles.add(title)
            for ge in rec.diff.get("new_glossary_entities", []):
                if isinstance(ge, dict) and ge.get("name"):
                    claimed_glossary_keys.add(_glossary_item_key(ge.get("kind_code"), ge["name"]))

        new_chapters = [
            {
                "event_id": ch["event_id"],
                "title": ch["title"],
                "ordinal": ch.get("ordinal"),
            }
            for ch in package_chapters
            if ch.get("title") not in existing_titles and ch.get("title") not in claimed_titles
        ]

        # M2 (§6): the real, already-correct glossary_seeds compile() computes
        # (characters + mechanics/concepts) — previously dead code, never
        # POSTed anywhere. Dedup here is ONLY against other active proposals'
        # own diffs, NOT against glossary-service's live entity state: the
        # direct entity-list read was intentionally removed from this client
        # (INV-KAL — composition reads cast through the knowledge-gateway
        # roster, never glossary directly). `seed_entities`'s own
        # create/upsert-by-name semantics at the glossary-service layer is
        # the backstop against a true duplicate slipping through — same
        # "accepted approximation, documented not hidden" posture as the
        # chapter title-dedup in §4.1.3.
        new_glossary_entities = [
            {"name": ge["name"], "kind_code": ge.get("kind_code") or "character",
             "attributes": ge.get("attributes") or {}}
            for ge in glossary_seeds
            if ge.get("name")
            and _glossary_item_key(ge.get("kind_code"), ge["name"]) not in claimed_glossary_keys
        ]

        diff = {"new_chapters": new_chapters, "new_glossary_entities": new_glossary_entities}
        record = await self._proposals.create(owner_user_id, book_id, run_id, diff=diff)
        logger.info(
            "bootstrap propose: book=%s run=%s proposal=%s new_chapters=%d "
            "new_glossary_entities=%d (skipped %d already-existing chapters, "
            "%d chapters + %d glossary entities already claimed by another proposal)",
            book_id, run_id, record.id, len(new_chapters), len(new_glossary_entities),
            len(existing_titles), len(claimed_titles), len(claimed_glossary_keys),
        )
        return record

    async def get(
        self, owner_user_id: UUID, book_id: UUID, proposal_id: UUID,
    ) -> PlanBootstrapProposal | None:
        return await self._proposals.get_for_owner(owner_user_id, book_id, proposal_id)

    async def approve(
        self, owner_user_id: UUID, book_id: UUID, proposal_id: UUID,
    ) -> PlanBootstrapProposal:
        result = await self._proposals.mark_approved(owner_user_id, book_id, proposal_id)
        if result is not None:
            logger.info("bootstrap approve: book=%s proposal=%s", book_id, proposal_id)
            return result
        existing = await self._proposals.get_for_owner(owner_user_id, book_id, proposal_id)
        if existing is None:
            raise LookupError("proposal not found")
        raise ValueError(f"cannot approve a proposal in status '{existing.status}'")

    async def reject(
        self, owner_user_id: UUID, book_id: UUID, proposal_id: UUID,
    ) -> PlanBootstrapProposal:
        result = await self._proposals.mark_rejected(owner_user_id, book_id, proposal_id)
        if result is not None:
            logger.info("bootstrap reject: book=%s proposal=%s", book_id, proposal_id)
            return result
        existing = await self._proposals.get_for_owner(owner_user_id, book_id, proposal_id)
        if existing is None:
            raise LookupError("proposal not found")
        raise ValueError(f"cannot reject a proposal in status '{existing.status}'")

    async def apply(
        self, owner_user_id: UUID, book_id: UUID, proposal_id: UUID, bearer: str,
    ) -> PlanBootstrapProposal:
        """Deterministic, zero LLM calls. Claims the record atomically
        (approved|failed → applying); a claim miss means another apply
        already ran or the record isn't in an applicable state — the
        current record is returned as-is (safe no-op / caller inspects
        `status`), never a blind re-run."""
        claimed = await self._proposals.claim_for_apply(owner_user_id, book_id, proposal_id)
        if claimed is None:
            existing = await self._proposals.get_for_owner(owner_user_id, book_id, proposal_id)
            if existing is None:
                raise LookupError("proposal not found")
            logger.info(
                "bootstrap apply: book=%s proposal=%s claim missed, current status=%s "
                "(safe no-op — another apply already ran or record isn't applicable)",
                book_id, proposal_id, existing.status,
            )
            return existing

        book = await self._book.get_book(book_id, bearer)
        original_language = (book or {}).get("original_language") or "en"
        new_chapters: list[dict[str, Any]] = claimed.diff.get("new_chapters", [])
        new_glossary_entities: list[dict[str, Any]] = claimed.diff.get("new_glossary_entities", [])
        logger.info(
            "bootstrap apply: book=%s proposal=%s claimed, %d chapter(s) + %d glossary "
            "entity/entities to apply (%d item(s) already applied in a prior attempt)",
            book_id, proposal_id, len(new_chapters), len(new_glossary_entities),
            len(claimed.applied_results),
        )

        try:
            for ch in new_chapters:
                event_id = ch["event_id"]
                if event_id in claimed.applied_results:
                    continue  # resumed retry — already applied in a prior attempt
                created = await self._book.create_chapter(
                    book_id, bearer,
                    title=ch["title"], original_language=original_language,
                )
                await self._proposals.mark_item_applied(
                    owner_user_id, book_id, proposal_id,
                    item_key=event_id,
                    result={"chapter_id": created.get("chapter_id"), "title": ch["title"]},
                )

            pending_glossary = [
                ge for ge in new_glossary_entities
                if _glossary_item_key(ge.get("kind_code"), ge.get("name")) not in claimed.applied_results
            ]
            if pending_glossary:
                try:
                    created_entities = await self._glossary.seed_entities_or_raise(
                        book_id, source_language=original_language, entities=pending_glossary,
                    )
                except GlossaryClientError as exc:
                    if exc.code == "GLOSS_BOOK_NOT_SCAFFOLDED":
                        raise GlossaryClientError(
                            exc.status, exc.code,
                            "This book has no Glossary ontology yet — adopt one in the "
                            "Graph Schema tab, then retry apply.",
                        ) from exc
                    raise
                for item in created_entities:
                    await self._proposals.mark_item_applied(
                        owner_user_id, book_id, proposal_id,
                        item_key=_glossary_item_key(item.get("kind_code"), item.get("name")),
                        result={
                            "entity_id": item.get("entity_id"),
                            "kind_code": item.get("kind_code"),
                            "name": item.get("name"),
                            "status": item.get("status"),
                        },
                    )
                if len(created_entities) < len(pending_glossary):
                    # glossary-service's own contract returns one entityResult per
                    # requested item (created/updated/skipped — never a silent drop);
                    # fewer back than requested is a real discrepancy, not success.
                    raise GlossaryClientError(
                        502, "GLOSS_PARTIAL_RESULT",
                        f"requested {len(pending_glossary)} glossary entities, "
                        f"glossary-service returned {len(created_entities)} — apply incomplete",
                    )
        except (BookClientError, GlossaryClientError) as exc:
            error_detail = getattr(exc, "detail", None) or str(exc)
            logger.warning(
                "bootstrap apply FAILED partway: book=%s proposal=%s error=%s",
                book_id, proposal_id, error_detail,
            )
            await self._proposals.mark_failed(
                owner_user_id, book_id, proposal_id, error_detail=error_detail,
            )
            raise

        applied = await self._proposals.mark_applied(owner_user_id, book_id, proposal_id)
        logger.info("bootstrap apply: book=%s proposal=%s all items applied", book_id, proposal_id)
        return applied if applied is not None else claimed
