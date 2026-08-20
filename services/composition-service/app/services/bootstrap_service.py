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


def compiled_package_across_arcs(
    artifacts: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fold a run's `package` artifacts into ONE (chapters, glossary_seeds) pair.

    🔴 THE DEFECT THIS EXISTS FOR, measured live 2026-08-13 on book 019ff497. `propose` read
    `latest_artifact(..., "package")` — a single artifact — but a run emits ONE PACKAGE PER ARC:
    `_autocompile_rules_run` loops `compile(arc_id=…)` over every parsed arc, and each compile
    saves its own arc-scoped package. That book compiled 3 arcs into 3 package artifacts, so the
    preview offered 2 chapters where the plan holds 6, and the other 4 (arcs 1-2) were silently
    absent from the thing the author approves from. Nothing looked broken: 2 real chapters with
    real titles, `status: pending`, no warning.

    TWO RULES, and the second is the one a plain concat gets wrong:

    * LATEST PER ARC, not every artifact. Re-compiling one arc appends ANOTHER package for that
      arc; concatenating all of them would offer its chapters twice. This is the same "BY TARGET,
      not latest" rule `plan_forge_service` already states for `link_report`.
    * ARC ORDER = COMPILE ORDER. `artifacts` arrives oldest-first, so first appearance of an
      arc_id is its authored position; a later re-compile updates that arc's content WITHOUT
      moving it. `apply` creates chapters in list order, so this ordering IS the book's order.

    An artifact whose package declares no `arc_id` (a pre-per-arc run, or a whole-run compile)
    keys on its own id, so it is neither dropped nor deduped against a real arc.
    """
    by_arc: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for art in artifacts:
        content = getattr(art, "content", None) or {}
        package = content.get("planning_package")
        if not package:
            continue  # a package artifact with no compiled package is not a compile result
        arc_key = str(package.get("arc_id") or f"__artifact:{getattr(art, 'id', len(order))}")
        if arc_key not in by_arc:
            order.append(arc_key)
        by_arc[arc_key] = content  # oldest-first ⇒ the last write per arc is the newest

    chapters: list[dict[str, Any]] = []
    seeds: list[dict[str, Any]] = []
    for arc_key in order:
        content = by_arc[arc_key]
        chapters.extend((content.get("planning_package") or {}).get("chapters", []) or [])
        seeds.extend(content.get("glossary_seeds", []) or [])
    return chapters, seeds


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

        # EVERY package, not the latest — a run emits one per ARC. See
        # `compiled_package_across_arcs` for the measured defect (2 chapters offered on a 6-chapter
        # plan) and for why the fold is latest-per-arc rather than a concat.
        pkg_arts = await self._runs.list_artifacts(book_id, run_id, "package")
        package_chapters, glossary_seeds = compiled_package_across_arcs(pkg_arts)
        if not any(
            (getattr(a, "content", None) or {}).get("planning_package") for a in pkg_arts
        ):
            raise ValueError("run has no compiled package yet — call compile() first")

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

        # RENUMBER, because the compiler's `ordinal` is PER ARC. Folding three arcs together
        # yields 1,2,1,2,1,2 — a preview that reads as three first chapters. `apply` ignores
        # ordinal entirely and creates chapters in list order, so the honest number is this list's
        # own position: what the author sees is then the order they will actually be created in.
        new_chapters = [
            {
                "event_id": ch["event_id"],
                "title": ch["title"],
                "ordinal": i,
                **({"drafting_guide": drafting_guides[ch["event_id"]]}
                   if ch["event_id"] in drafting_guides else {}),
            }
            for i, ch in enumerate(
                [
                    c for c in package_chapters
                    if c.get("title") not in existing_titles
                    and c.get("title") not in claimed_titles
                ],
                start=1,
            )
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
    ) -> PlanBootstrapProposal | None:
        """A glossary-ONLY bootstrap proposal built from a PASS artifact (27 PF-7).

        Returns **None** when every entity is already claimed by an active (or applied) proposal —
        i.e. there is nothing to ask the human about. See the empty-diff branch at the bottom.

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

        if not new_glossary_entities:
            # NOTHING NEW TO OFFER ⇒ NO PROPOSAL. This is the re-run case, and creating a row here
            # was a bug with a long tail.
            #
            # `list_active_for_book` counts APPLIED proposals as claiming their entities, so
            # re-running `cast` after its seed was applied dedups to zero — and an empty proposal
            # would then: (1) overwrite `pass_state.cast.bootstrap_proposal_id`, so (2) accepting
            # cast REFUSES (the new proposal is `pending`) and the author has to approve and apply an
            # EMPTY diff to proceed, after which (3) its `applied_results` is `{}`, the roster join
            # resolves no ids, and every scene silently loses its cast.
            #
            # Returning None leaves the caller's `record_pass(bootstrap_proposal_id=None)` to leave
            # the field UNTOUCHED — so the already-applied proposal stays pointed at, and the
            # re-run is the no-op it should be. Re-running a pass is this compiler's whole selling
            # point; it must not be the thing that breaks it.
            logger.info(
                "propose_seed: book=%s run=%s pass=%s — all %d entit(ies) are already claimed by "
                "an active proposal; no new proposal opened",
                book_id, run_id, pass_id, len(entities),
            )
            return None

        diff = {"new_chapters": [], "new_glossary_entities": new_glossary_entities}
        record = await self._proposals.create(created_by, book_id, run_id, diff=diff)
        logger.info(
            "propose_seed: book=%s run=%s pass=%s proposal=%s entities=%d "
            "(%d offered, %d already claimed by an active proposal)",
            book_id, run_id, pass_id, record.id, len(entities),
            len(new_glossary_entities), len(claimed),
        )
        return record

    async def _stamp_planned_node(
        self, book_id: UUID, event_id: str, chapter_id: Any,
    ) -> None:
        """27 V2-E3 — join the planned node to the chapter that now exists.

        Stamps BOTH the chapter node (matched on `plan_event_id`) AND its scene children (matched on
        `parent_id`). The scene nodes carry a DERIVED `plan_event_id` (`<event>:1`, `<event>:2`, …),
        so an exact `plan_event_id = event` match reaches only the chapter node and leaves every
        scene at `chapter_id = NULL`. That is not cosmetic: `outline.scenes_for_chapter` resolves a
        chapter's scenes by `chapter_id`, so unstamped scenes make a materialised chapter draft with
        NO scene breakdown — the thin/short-chapter bug. Stamping via the scenes' parent chapter node
        is the reliable link (their parent IS the chapter node, whatever their derived event id).

        Idempotent and NON-CLOBBERING: `chapter_id IS NULL` in the WHERE. A node already bound to a
        chapter keeps it — a re-applied proposal (the resume path) must not re-point a node at a
        second, newly-created chapter and orphan the first. The parent subselect does NOT filter on
        the chapter's `chapter_id`, so a re-apply that finds the chapter already stamped still
        repairs any scene left NULL (the exact half-stamped state a pre-fix apply produced).

        ADVISORY. A failure here must not fail the apply: the chapter has ALREADY been created in
        book-service, and raising would roll back nothing (it is a different database) while leaving
        the proposal `failed` and the user staring at a chapter that exists. So it logs loudly and
        the node stays NULL — recoverable, and honestly reported as "planned", which is what the
        Hub will show until someone re-links.
        """
        if not chapter_id:
            return
        try:
            pool = self._runs._pool
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE outline_node
                       SET chapter_id = $1, updated_at = now()
                     WHERE book_id = $2 AND chapter_id IS NULL AND NOT is_archived
                       AND (
                         plan_event_id = $3
                         OR parent_id IN (
                           SELECT id FROM outline_node
                            WHERE book_id = $2 AND plan_event_id = $3
                              AND kind = 'chapter' AND NOT is_archived
                         )
                       )
                    """,
                    UUID(str(chapter_id)), book_id, event_id,
                )
        except Exception:  # noqa: BLE001 — advisory: the chapter is already created
            logger.warning(
                "bootstrap apply: could not stamp outline_node.chapter_id for book=%s event=%s "
                "chapter=%s — the node stays 'planned, not yet written' until it is re-linked",
                book_id, event_id, chapter_id, exc_info=True,
            )

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
        *, may_scaffold: bool = False,
    ) -> PlanBootstrapProposal:
        """Deterministic, zero LLM calls. Claims the record atomically
        (approved|failed → applying); a claim miss means another apply
        already ran or the record isn't in an applicable state — the
        current record is returned as-is (safe no-op / caller inspects
        `status`), never a blind re-run.

        `may_scaffold` — whether the CALLER holds MANAGE on the book, resolved once at the router
        from the same grant lookup that gates the request. It decides whether an unscaffolded book
        may have the kinds this proposal needs seeded on the spot (see the seed step below).
        Scaffolding a book's ontology is a MANAGE-tier act and this route is EDIT-gated, so the
        capability is passed IN rather than assumed here: an EDIT collaborator must not be able to
        reshape a book's ontology as a side effect of applying a cast proposal."""
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
                # 27 V2-E3 — STAMP THE PLANNED NODE.
                #
                # The linker deliberately writes `outline_node.chapter_id = NULL` — "planned, not
                # yet written" — because at compile time the manuscript chapter does not exist. THIS
                # is the moment it starts existing, and it is the only moment at which the plan node
                # and the real chapter can be joined.
                #
                # Without this stamp the two halves never meet: the Plan Hub's two-truths view can
                # never resolve a planned chapter to a written one, so a fully-drafted book would go
                # on reporting every chapter as "planned, not yet written", forever. And nothing
                # would look broken — the nodes are all there, the chapters are all there, and the
                # only thing missing is the pointer between them.
                await self._stamp_planned_node(book_id, event_id, created.get("chapter_id"))
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
                    if exc.code != "GLOSS_BOOK_NOT_SCAFFOLDED":
                        raise
                    # A BRAND-NEW book has no ontology, so its very first cast proposal could not
                    # be applied — and the only signal was this error, pointing the author at a
                    # different screen in a different feature. That is a dead end in the first run
                    # anyone ever does: nothing earlier in the plan flow mentions it, and the
                    # author has already approved a cast by the time they hit it.
                    #
                    # knowledge-service solved the same shape already — adopting a KG graph-schema
                    # used to 422 NEEDS_GLOSSARY, and now it seeds the node-kinds the schema
                    # requires via this exact internal route. A dependent operation that needs a
                    # kind should SEED that kind, not send the author away.
                    #
                    # Only the kinds THESE entities need, never a blanket ontology: seeding what
                    # the proposal actually references is a mechanical prerequisite, whereas
                    # choosing a book's whole ontology is an authoring decision that is not ours.
                    needed = sorted({
                        str(ge.get("kind_code") or "").strip()
                        for ge in pending_glossary if (ge.get("kind_code") or "").strip()
                    })
                    if not (may_scaffold and needed):
                        raise GlossaryClientError(
                            exc.status, exc.code,
                            "This book has no Glossary ontology yet, and setting one up needs "
                            "MANAGE access to the book — ask the book's owner to open it once, "
                            "then retry apply."
                            if needed else
                            "This book has no Glossary ontology yet and this proposal names no "
                            "entity kind to seed one from — adopt an ontology for the book first.",
                        ) from exc
                    logger.info(
                        "bootstrap apply: book=%s is unscaffolded — seeding %s and retrying",
                        book_id, needed,
                    )
                    await self._glossary.adopt_book_kinds(book_id, created_by, needed)
                    # Retried ONCE, and deliberately without inspecting the adopt result: if the
                    # scaffold did not take, the retry raises the real error from the operation the
                    # caller actually asked for, rather than a second-hand one about the repair.
                    created_entities = await self._glossary.seed_entities_or_raise(
                        book_id, source_language=original_language, entities=pending_glossary,
                    )
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
