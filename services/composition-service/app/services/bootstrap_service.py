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
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo
from app.db.repositories.plan_runs import PlanRunsRepo

logger = logging.getLogger(__name__)


def _glossary_item_key(kind_code: str | None, name: str | None) -> str:
    return f"glossary:{kind_code or 'character'}:{name}"


def _drafting_guides_by_event_id(pipeline_result: dict[str, Any]) -> dict[str, str]:
    """§6 M3: `plan_pipeline` job result (`dataclasses.asdict(PipelineResult)`)
    → {event_id: guide text}, joining each chapter's scene synopses into one
    plain-text guide. `ChapterScenes.chapter.chapter_id` IS the event_id —
    the `plan_forge_service.compile()` fix stamps it that way precisely so
    this correlation works (see that fix's comment for why `chapter_id` was
    previously incompatible garbage that crashed before reaching here)."""
    guides: dict[str, str] = {}
    for cs in pipeline_result.get("decompose", {}).get("chapters", []):
        chapter = cs.get("chapter") or {}
        event_id = chapter.get("chapter_id")
        scenes = cs.get("scenes") or []
        if not event_id or not scenes:
            continue
        lines = [f"- {s.get('title', '(untitled scene)')}: {s.get('synopsis', '')}" for s in scenes]
        guides[event_id] = "\n".join(lines)
    return guides


class BootstrapService:
    def __init__(
        self,
        proposals: PlanBootstrapProposalsRepo,
        plan_runs: PlanRunsRepo,
        book: BookClient,
        glossary: GlossaryClient,
        jobs: GenerationJobsRepo,
    ) -> None:
        self._proposals = proposals
        self._runs = plan_runs
        self._book = book
        self._glossary = glossary
        self._jobs = jobs

    async def propose(
        self, created_by: UUID, book_id: UUID, run_id: UUID, bearer: str,
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
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            raise LookupError("run not found")

        pkg_art = await self._runs.latest_artifact(book_id, run_id, "package")
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

        # §6 M3: if compile()'s OPTIONAL run_pipeline=true already computed a
        # per-chapter scene/beat breakdown for this run (a separate,
        # explicit, user-initiated action — this gate never triggers that
        # expensive multi-LLM-call pipeline itself), attach it as a plain-
        # text drafting guide per event_id. Reading an ALREADY-COMPUTED job
        # result costs zero additional LLM calls — propose() stays cheap
        # regardless of whether a pipeline run happened.
        # /review-impl LOW: this whole block is an OPTIONAL enhancement — a
        # malformed/unreachable pipeline_job_id must never break the REQUIRED
        # propose() behavior (the new_chapters/new_glossary_entities diff),
        # so failures here degrade to "no drafting guide" rather than raising.
        drafting_guides: dict[str, str] = {}
        pipeline_job_id = run.checkpoint_state.get("pipeline_job_id")
        if pipeline_job_id:
            try:
                job = await self._jobs.get(UUID(pipeline_job_id))
                if job is not None and job.status == "completed" and job.result:
                    drafting_guides = _drafting_guides_by_event_id(job.result)
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "bootstrap propose: run=%s has an unusable pipeline_job_id %r (%s) "
                    "— continuing without a drafting guide",
                    run_id, pipeline_job_id, exc,
                )

        new_chapters = [
            {
                "event_id": ch["event_id"],
                "title": ch["title"],
                "ordinal": ch.get("ordinal"),
                **({"drafting_guide": drafting_guides[ch["event_id"]]}
                   if ch["event_id"] in drafting_guides else {}),
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
        record = await self._proposals.create(created_by, book_id, run_id, diff=diff)
        logger.info(
            "bootstrap propose: book=%s run=%s proposal=%s new_chapters=%d "
            "(%d with a drafting guide from job %s) new_glossary_entities=%d "
            "(skipped %d already-existing chapters, %d chapters + %d glossary "
            "entities already claimed by another proposal)",
            book_id, run_id, record.id, len(new_chapters),
            sum(1 for c in new_chapters if "drafting_guide" in c), pipeline_job_id,
            len(new_glossary_entities), len(existing_titles),
            len(claimed_titles), len(claimed_glossary_keys),
        )
        return record

    # ── 27 PF-7 — the GLOSSARY-ONLY seed proposal (passes 2 and 3) ───────────────────────────
    #: Which glossary kind each pass's entities are seeded as. `cast` is all characters; `world`
    #: carries its own kind per entity, clamped to the three the world pass can emit.
    SEED_KINDS: dict[str, tuple[str, ...]] = {
        "cast": ("character",),
        "world": ("location", "faction", "concept"),
    }

    async def propose_seed(
        self,
        created_by: UUID,
        book_id: UUID,
        run_id: UUID,
        pass_id: str,
        entities: list[dict[str, Any]],
    ) -> PlanBootstrapProposal:
        """A glossary-ONLY bootstrap proposal built from a PASS artifact (27 PF-7).

        Why this exists rather than the pass seeding the glossary directly: **one approval
        mechanism, not two.** The glossary is the author's canon. A compiler pass that wrote into it
        on its own would be a second, invisible path into the exact surface the bootstrap quarantine
        was built to guard — and the author would discover the LLM's inventions already in their
        canon, with no diff and nothing to reject.

        So a pass PROPOSES; the human applies. And because pass 2 is a blocking checkpoint whose
        acceptance requires this proposal to be `applied` (see `plan_forge_service.review_checkpoint`),
        the blocking gate and the mutation gate are the SAME gate — they cannot disagree.

        Deduped against every still-active proposal's claims by the same `_glossary_item_key`
        mechanism `propose()` uses: a second `propose_seed` before the first is applied must not
        double-offer (and, if both were applied, double-create) the same entity.

        Emits `new_chapters: []` — the shape stays the one `apply()` already knows how to read. A
        seed proposal never touches the manuscript; the skeleton link is the compiler's job, and it
        already happened at `compile()`.
        """
        if pass_id not in self.SEED_KINDS:
            raise ValueError(
                f"pass '{pass_id}' does not seed the glossary "
                f"(only {sorted(self.SEED_KINDS)} do)",
            )
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            raise LookupError("run not found")

        allowed = self.SEED_KINDS[pass_id]
        default_kind = allowed[0]

        claimed: set[str] = set()
        for rec in await self._proposals.list_active_for_book(book_id):
            for ge in rec.diff.get("new_glossary_entities", []):
                if isinstance(ge, dict) and ge.get("name"):
                    claimed.add(_glossary_item_key(ge.get("kind_code"), ge["name"]))

        seen: set[str] = set()
        new_glossary_entities: list[dict[str, Any]] = []
        for e in entities:
            name = (e.get("name") or "").strip() if isinstance(e, dict) else ""
            if not name:
                continue
            kind = e.get("kind") or e.get("kind_code") or default_kind
            if kind not in allowed:
                # An unknown kind is clamped, never dropped and never passed through: passing it
                # through would push an unvalidated kind_code at glossary-service, and dropping it
                # would silently lose an entity the LLM did propose.
                logger.info(
                    "propose_seed: pass=%s entity=%r has kind %r outside %s — clamping to %r",
                    pass_id, name, kind, allowed, default_kind,
                )
                kind = default_kind
            key = _glossary_item_key(kind, name)
            if key in claimed or key in seen:
                continue
            seen.add(key)
            new_glossary_entities.append({
                "name": name, "kind_code": kind,
                "attributes": e.get("attributes") or {},
            })

        diff = {"new_chapters": [], "new_glossary_entities": new_glossary_entities}
        record = await self._proposals.create(created_by, book_id, run_id, diff=diff)
        logger.info(
            "propose_seed: book=%s run=%s pass=%s proposal=%s entities=%d "
            "(%d offered, %d already claimed by an active proposal)",
            book_id, run_id, pass_id, record.id, len(entities),
            len(new_glossary_entities), len(claimed),
        )
        return record

    async def get(
        self, book_id: UUID, proposal_id: UUID,
    ) -> PlanBootstrapProposal | None:
        # Book-scoped read (OQ-3): the router's E0 book VIEW gate is the access
        # decision, made BEFORE this call; the repo never filters on the actor,
        # so a read carries no created_by.
        return await self._proposals.get_for_book(book_id, proposal_id)

    async def approve(
        self, book_id: UUID, proposal_id: UUID,
    ) -> PlanBootstrapProposal:
        # Book-scoped status transition (OQ-3): the router's E0 book EDIT gate is
        # the access decision; the actor isn't stamped on the state change (the
        # repo's mark_approved stores nothing about the caller), so no created_by.
        result = await self._proposals.mark_approved(book_id, proposal_id)
        if result is not None:
            logger.info("bootstrap approve: book=%s proposal=%s", book_id, proposal_id)
            return result
        existing = await self._proposals.get_for_book(book_id, proposal_id)
        if existing is None:
            raise LookupError("proposal not found")
        raise ValueError(f"cannot approve a proposal in status '{existing.status}'")

    async def reject(
        self, book_id: UUID, proposal_id: UUID,
    ) -> PlanBootstrapProposal:
        # Book-scoped status transition (OQ-3): the router's E0 book EDIT gate is
        # the access decision; the actor isn't stamped on the state change (the
        # repo's mark_rejected stores nothing about the caller), so no created_by.
        result = await self._proposals.mark_rejected(book_id, proposal_id)
        if result is not None:
            logger.info("bootstrap reject: book=%s proposal=%s", book_id, proposal_id)
            return result
        existing = await self._proposals.get_for_book(book_id, proposal_id)
        if existing is None:
            raise LookupError("proposal not found")
        raise ValueError(f"cannot reject a proposal in status '{existing.status}'")

    async def apply(
        self, created_by: UUID, book_id: UUID, proposal_id: UUID, bearer: str,
    ) -> PlanBootstrapProposal:
        """Deterministic, zero LLM calls. Claims the record atomically
        (approved|failed → applying); a claim miss means another apply
        already ran or the record isn't in an applicable state — the
        current record is returned as-is (safe no-op / caller inspects
        `status`), never a blind re-run."""
        del created_by  # actor arity kept; apply replays the approved diff, book-scoped
        claimed = await self._proposals.claim_for_apply(book_id, proposal_id)
        if claimed is None:
            existing = await self._proposals.get_for_book(book_id, proposal_id)
            if existing is None:
                raise LookupError("proposal not found")
            logger.info(
                "bootstrap apply: book=%s proposal=%s claim missed, current status=%s "
                "(safe no-op — another apply already ran or record isn't applicable)",
                book_id, proposal_id, existing.status,
            )
            return existing

        try:
            # /review-impl HIGH: get_book() used to sit OUTSIDE this try block —
            # any transient book-service failure here (or any other unexpected
            # exception anywhere below, not just BookClientError/GlossaryClientError)
            # propagated unhandled, leaving the record stuck at status='applying'
            # forever (claim_for_apply only re-claims from 'approved'/'failed', so
            # a retry silently no-ops on the stuck row instead of retrying). The
            # whole post-claim body is now inside this try so ANY failure marks
            # the record 'failed' (resumable) before propagating.
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

            for ch in new_chapters:
                event_id = ch["event_id"]
                if event_id in claimed.applied_results:
                    continue  # resumed retry — already applied in a prior attempt
                created = await self._book.create_chapter(
                    book_id, bearer,
                    title=ch["title"], original_language=original_language,
                )
                result: dict[str, Any] = {"chapter_id": created.get("chapter_id"), "title": ch["title"]}
                if ch.get("drafting_guide"):
                    # §6 M3 [C]/[D]: carried through verbatim from PROPOSE (computed
                    # once, from an already-completed pipeline job — never
                    # regenerated here) so a reviewer/GUI can surface "here's the
                    # suggested scene/beat guide" for the chapter it just created.
                    result["drafting_guide"] = ch["drafting_guide"]
                await self._proposals.mark_item_applied(
                    book_id, proposal_id,
                    item_key=event_id, result=result,
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
                        book_id, proposal_id,
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
        except Exception as exc:
            # Deliberately broad (not just BookClientError/GlossaryClientError):
            # ANY failure here must mark the record 'failed' (resumable via
            # claim_for_apply) rather than leave it stuck at 'applying' forever.
            # Doesn't swallow cancellation — asyncio.CancelledError is a
            # BaseException, not an Exception, in Python 3.8+.
            error_detail = getattr(exc, "detail", None) or str(exc)
            logger.warning(
                "bootstrap apply FAILED partway: book=%s proposal=%s error=%s (%s)",
                book_id, proposal_id, error_detail, type(exc).__name__,
            )
            await self._proposals.mark_failed(
                book_id, proposal_id, error_detail=error_detail,
            )
            raise

        applied = await self._proposals.mark_applied(book_id, proposal_id)
        logger.info("bootstrap apply: book=%s proposal=%s all items applied", book_id, proposal_id)
        return applied if applied is not None else claimed
