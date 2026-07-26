"""Packer orchestrator (§2.5) — gather → spoiler → budget → assemble.

Flow: A1 chokepoint (project_id) → SEC2 chokepoint (owns_book BEFORE any internal
read) → resolve the scene's reading position → parallel `_safe_*` lens gather →
two-axis spoiler filter (L1b in-world, L4 reading-order with conservative-drop +
LOG) → priority-ladder budget trim → assemble structured blocks. Returns a
PackedContext that the grounding endpoint (and M6 engine) consume.

C3a: when no knowledge lens returned data, `grounding_available=False` + a
warning — surface "grounding thin/unavailable", never silently ship thin.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.config import settings

from app.clients.book_client import BookClient
from app.clients.glossary_client import GlossaryClient
from app.clients.knowledge_client import KnowledgeClient
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
# E0-4c — grant-aware book gate. grant_client imports only app.config (no cycle
# into the packer); authorize_book is imported lazily inside pack() (it imports
# OwnershipError from this module → would cycle at top level).
from app.grant_client import GrantClient, GrantLevel
# scene_at_order / EVENT_ORDER_CHAPTER_STRIDE — the reading-axis cutoff contract
# (canon_check is pure, no app imports → no cycle into the packer).
from app.engine.canon_check import scene_at_order
from app.packer import assemble
from app.packer import budget as B
from app.packer import merge as M
from app.packer import profile as profile_mod
from app.packer import spoiler
from app.packer.lenses import (
    LensBundle, gather_arc, gather_canon, gather_lore, gather_motif, gather_open_promises,
    gather_present, gather_recent, gather_references, gather_source_scene,
    gather_structural, gather_timeline,
)
from app.db.repositories.references import reference_embed_model

logger = logging.getLogger(__name__)


class OwnershipError(Exception):
    """Caller does not own the book — raised by the SEC2 chokepoint so the
    router maps it to 404 (don't leak existence)."""


@dataclass
class PackRequest:
    # The ACTING CALLER (25 signature law): the E0 gate's subject (authorize_book)
    # + the cross-service identity (knowledge/glossary/book reads) + the BYOK
    # spend attribution for the reference-embed (OQ-9). NEVER a row filter — the
    # composition repos are project-keyed; access is decided at the gate.
    user_id: UUID
    project_id: UUID
    book_id: UUID
    node: dict[str, Any]   # the outline_node (id, chapter_id, story_order, present_entity_ids, pov_entity_id, beat_role, goal, synopsis, title)
    bearer: str
    guide: str = ""
    settings: dict[str, Any] | None = None  # composition_work.settings → BookProfile
    # Caller-provided chapter sort_order — when the caller already fetched it
    # (B2/B3 chapter+stitch build the synthetic node's story_order from it), pass
    # it here so pack() skips the redundant book.get_chapter_sort_orders call.
    chapter_sort_hint: int | None = None
    # C25 (dị bản M0) — DERIVATIVE two-project merge. When this Work is a
    # derivative, `source_project_id` is the SOURCE Work's knowledge project (the
    # inherited BASE, read ≤ `branch_point`) and `project_id` is the derivative's
    # OWN project (the DELTA, read full). `overrides` is the freshly-read
    # `entity_override[]` applied to the inherited base entities BEFORE the prompt
    # window — re-read + re-applied EVERY pack (self-syncing, NO cache). All None
    # for a non-derivative (greenfield) Work → the normal single-project path.
    source_project_id: UUID | None = None
    branch_point: int | None = None
    overrides: list[Any] | None = None
    # Part A (2026-07-18 spec) — the derivative's POV-shift anchor (divergence_spec.
    # pov_anchor), a GLOSSARY entity id. When set on a derivative Work, pack() default-
    # fills it as the effective scene POV where the scene sets none (PO-1 default-fill,
    # PO-3 apply-when-set — no taxonomy gate). None for a non-derivative / unset spec.
    pov_anchor: UUID | None = None
    # M1 (D-DERIVATIVE-ADAPT-FROM-SOURCE) — the free-form prose operation this pack
    # serves. Op-AWARE only for `adapt_scene`: that op (and ONLY that op, on a
    # derivative) fires the `gather_source_scene` lens to read the inherited source
    # prose into the <source_scene> block. Every other op leaves the pack
    # BYTE-UNCHANGED. Defaults to the generic draft op so existing callers are
    # unaffected.
    operation: str = "draft_scene"


@dataclass
class PackedContext:
    blocks: dict[str, str]
    prompt: str
    profile: profile_mod.BookProfile
    token_count: int
    dropped_count: int
    l4_dropped_no_position: int
    grounding_available: bool
    over_budget: bool
    # A2-S3b — the scene's chapter reading-order (book sort_order), the canon
    # guard's position axis (× stride = the event_order cutoff). None when the
    # node has no resolved chapter → the guard skips (advisory).
    scene_sort_order: int | None = None
    # FD-1 S4b: how many open promises (S3) were re-injected into THIS prompt (the
    # gathered re-injectable set fed to assemble; the `<open_promises>` block is
    # protected so the budget keeps it). 0 when the Work opts out / no repo / none
    # open. A DETERMINISTIC per-generation signal that S3 fired - distinct from
    # S4a's `open_promise_count` (the arc-end unpaid-DEBT total).
    reinjected_promise_count: int = 0
    warnings: list[str] = field(default_factory=list)
    # T3.4 — the addressable grounding items (present/canon/lore) with their
    # per-scene pin/exclude state, for the grounding panel. Built from the
    # spoiler-ELIGIBLE set (so a pin/exclude can only act within eligible items);
    # excluded items are still listed (flagged) so the FE can un-exclude them, but
    # were NOT packed into `blocks`. Empty when no pins repo is wired.
    grounding_items: list[dict[str, Any]] = field(default_factory=list)


def _as_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


@dataclass
class DerivativeContext:
    """C25 — the resolved dị bản inputs for a derivative pack: the inherited BASE
    project (the source Work's project, read ≤ `branch_point`) and the freshly-read
    `entity_override[]`. None / empty for a non-derivative Work."""
    source_project_id: UUID | None = None
    branch_point: int | None = None
    overrides: list[Any] = field(default_factory=list)
    # Part A — the divergence_spec's pov_anchor (a GLOSSARY entity id), read fresh each
    # pack alongside the overrides. None for a non-derivative / spec without a pov_anchor.
    pov_anchor: UUID | None = None


async def build_derivative_context(
    work: Any, *, works_repo: Any, derivatives_repo: Any | None,
) -> DerivativeContext:
    """C25 — resolve the two-project merge inputs for a Work at a pack call site.

    A derivative Work carries `source_work_id` + `branch_point` (C23). The BASE
    knowledge project is the SOURCE Work's `project_id`, resolved by looking the
    source up by its surrogate `id` (`source_work_id`) — the source's `id` is NOT
    necessarily its `project_id` (the two diverge for a Work whose surrogate id was
    minted distinct from its project), so reusing `source_work_id` as a project_id
    directly would point the base read at the WRONG / a non-existent partition
    (silently empty base, or — worse — another project). Look it up.

    The `entity_override[]` is read FRESH here on every pack (self-syncing — no
    cache; an edited override takes effect on the next pack). A non-derivative Work
    (no source) → an empty context (the normal single-project pack path). If the
    source Work can't be resolved (deleted), the base project is None → the
    derivative GUARD will refuse the pack (rather than silently widen)."""
    src = getattr(work, "source_work_id", None)
    if src is None:
        return DerivativeContext()
    base_project_id: UUID | None = None
    try:
        source = await works_repo.get_by_id(src)
        if source is not None:
            base_project_id = source.project_id
    except Exception:  # noqa: BLE001 — source lookup degrades to a refused derivative pack
        logger.warning("build_derivative_context: source work lookup failed", exc_info=True)
    overrides: list[Any] = []
    pov_anchor: UUID | None = None
    if derivatives_repo is not None and getattr(work, "id", None) is not None:
        try:
            overrides = await derivatives_repo.list_overrides_for_work(work.id)
        except Exception:  # noqa: BLE001 — override read degrades (pack never 500s on it)
            logger.warning("build_derivative_context: override read failed", exc_info=True)
            overrides = []
        # Part A — the divergence spec carries the POV-shift anchor. Read fresh (self-
        # syncing); a missing spec / read failure degrades to no anchor (never 500s).
        try:
            spec = await derivatives_repo.get_spec_for_work(work.id)
            pov_anchor = spec.pov_anchor if spec is not None else None
        except Exception:  # noqa: BLE001 — spec read degrades to no POV default
            logger.warning("build_derivative_context: spec read failed", exc_info=True)
            pov_anchor = None
    return DerivativeContext(
        source_project_id=base_project_id, branch_point=getattr(work, "branch_point", None),
        overrides=overrides, pov_anchor=pov_anchor,
    )


async def pack(
    req: PackRequest, *,
    book: BookClient, glossary: GlossaryClient, knowledge: KnowledgeClient,
    canon_repo: CanonRulesRepo, outline_repo: OutlineRepo, scene_links_repo: SceneLinksRepo,
    budget_tokens: int, counter: B.TokenCounter | None = None,
    jobs_repo: GenerationJobsRepo | None = None,
    compress_fn: Callable[[list[str], list[str], str], Awaitable[str]] | None = None,
    narrative_threads_repo=None,  # FD-1 S3 — open-promise re-injection (gated)
    grounding_pins_repo=None,  # T3.4 — per-scene pin/exclude steering (gated)
    style_profile_repo=None,  # T3.5 — per-scope density/pace (gated)
    voice_profile_repo=None,  # T3.5 — per-character voice tags (gated)
    references_repo=None,  # T3.6 — author reference shelf (gated)
    embedding_client=None,  # T3.6 — provider-registry embed for reference retrieval (gated)
    structure_repo=None,  # 23 BA12 — the arc lens (durable spec layer; gated)
    motif_application_repo=None,  # X-7 / BE-M2 — the motif lens (scene beat structure; gated)
    motif_repo=None,  # X-7 / BE-M2 — ditto; BOTH must be wired or the lens stays dormant
    grant: "GrantClient | None" = None,
    need: "GrantLevel | None" = None,
) -> PackedContext:
    # C16 (WG-3): a GREENFIELD Work whose knowledge project couldn't be created
    # (knowledge-service outage at setup) carries a null project_id. The writer must
    # still Generate — so pack tolerates it by degrading grounding to EMPTY: it skips
    # EVERY knowledge lens (present/timeline/lore) entirely and packs only the local
    # composition lenses (canon/structural/recent). This PRESERVES the A1/C23 guard —
    # rather than calling a knowledge lens with project_id=None (which would widen the
    # timeline endpoint to ALL the user's projects = cross-project grounding leak), we
    # never call it at all. assert_project_scoped therefore still guards the NON-null
    # path below (any knowledge read keeps a real scope).
    # C25: a DERIVATIVE pack grounds on TWO partitions. A Work is a derivative when
    # ANY divergence signal is present (source project, branch_point, or overrides)
    # — keying off all three so a malformed/partial derivative (e.g. branch set but
    # source null) still hits the GUARD instead of silently taking a single-project
    # or greenfield path. GUARD: both the delta (project_id) and base
    # (source_project_id) must be non-null before the null short-circuit can mask a
    # null delta as "greenfield" — a null on either widens a knowledge read
    # cross-project (the C23 leak).
    is_derivative = (
        req.source_project_id is not None
        or req.branch_point is not None
        or bool(req.overrides)
    )
    if is_derivative:
        assemble.assert_derivative_scoped(req.project_id, req.source_project_id)
    elif req.project_id is None:
        return await _pack_null_project(req, grant=grant, need=need, budget_tokens=budget_tokens)
    # A1: never pack unscoped (knowledge timeline/entities widen cross-project).
    assemble.assert_project_scoped(req.project_id)
    # SEC2 (E0-4c): grant-aware book chokepoint BEFORE any internal (token-trust)
    # read. Was owns_book (owner-only bool); now resolves the caller's book grant
    # and gates by the operation's tier — read-pack=VIEW (default), prose-gen=EDIT
    # (the engine passes it). none → OwnershipError (404, no oracle); under-tier →
    # InsufficientGrant (403). Lazy import breaks the pack↔grant_deps cycle.
    from app.grant_client import get_grant_client
    from app.grant_deps import authorize_book
    await authorize_book(
        grant or get_grant_client(), req.book_id, req.user_id, need or GrantLevel.VIEW,
    )

    profile = profile_mod.from_settings(req.settings)
    node = req.node
    # Part A (2026-07-18 spec) — POV-shift derivative: DEFAULT-FILL the effective scene
    # POV from the divergence spec's pov_anchor when the scene sets none (PO-1 default-
    # fill: a scene's own pov_entity_id wins; the anchor covers the rest. PO-3 apply-
    # when-set: any derivative with a pov_anchor, no taxonomy gate). pov_anchor is a
    # GLOSSARY anchor in the SAME id-space as pov_entity_id, so the copied node flows
    # through the beat lens + present_ids unchanged — its bio grounds and the assemble
    # beat block renders `pov=<name>`. Copy the node (never mutate the caller's dict).
    if is_derivative and req.pov_anchor is not None and not node.get("pov_entity_id"):
        node = {**node, "pov_entity_id": str(req.pov_anchor)}
    story_order = node.get("story_order")
    chapter_id = _as_uuid(node.get("chapter_id"))
    # 23 BA12 — the arc this scene's chapter is assigned to (structure_node.id). A SCENE
    # never carries structure_node_id itself (the outline_structure_kind CHECK forbids
    # it — only chapters may), so resolve it through the chapter: node → chapter_id →
    # the outline chapter node's structure_node_id. If the node dict already carries one
    # (a chapter-mode pack, or a caller that pre-resolved), that wins. None → the arc
    # lens stays dormant (the gate below). Best-effort: a lookup failure never fails a
    # pack. Requires structure_repo to be wired (the packer's own arc lens gate).
    structure_node_id = _as_uuid(node.get("structure_node_id"))
    if structure_node_id is None and structure_repo is not None and chapter_id is not None \
            and req.project_id is not None:
        try:
            structure_node_id = await outline_repo.chapter_structure_node_id(
                req.project_id, chapter_id)
        except Exception:  # noqa: BLE001 — the arc frame is a soft steer; dormant on failure
            logger.warning("pack: arc resolution failed", exc_info=True)
    query = " ".join(
        str(x) for x in [node.get("goal"), node.get("synopsis"), node.get("beat_role"), node.get("title")] if x
    )
    present_ids = [u for u in (
        [_as_uuid(node.get("pov_entity_id"))] + [_as_uuid(e) for e in (node.get("present_entity_ids") or [])]
    ) if u is not None]

    # T3.5 — resolve the scene's prose style (density/pace, most-specific scope) and
    # the present characters' voice tags, and fold them into the profile so the engine
    # threads them into the draft prompts and the grounding preview surfaces them. Both
    # are GATED on the repo being wired (dormant otherwise) and degrade to neutral on
    # any error — style/voice are a soft steer, never a reason to fail a pack.
    from dataclasses import replace as _replace
    if style_profile_repo is not None:
        try:
            sp = await style_profile_repo.resolve(
                req.project_id, _as_uuid(node.get("id")), chapter_id)
            if sp is not None:
                profile = _replace(profile, density_level=sp.density, pace_level=sp.pace)
        except Exception:  # noqa: BLE001 — style is a soft steer; neutral on failure
            logger.warning("pack: style_profile resolve failed", exc_info=True)
    if voice_profile_repo is not None and present_ids:
        try:
            vps = await voice_profile_repo.list_for_entities(
                req.project_id, present_ids)
            cv = tuple((vp.entity_name, tuple(vp.tags)) for vp in vps if vp.tags)
            if cv:
                profile = _replace(profile, character_voices=cv)
        except Exception:  # noqa: BLE001 — voice is a soft steer; neutral on failure
            logger.warning("pack: voice_profile resolve failed", exc_info=True)

    # KG-ML M7 (C6) — the author's reader-language for this book (M3). Resolved
    # ONCE and threaded into the knowledge/glossary lenses so the pack carries
    # per-language entity aliases + surfaces in-language lore passages first. Best-
    # effort (None on unset/outage → the pack stays source-language, never 500s).
    reader_lang = await book.get_reader_language(req.book_id, req.user_id)

    # Resolve the scene's chapter reading position FIRST — it is the timeline
    # cutoff on the DENSE event_order axis (at_order = sort × stride; CM4) AND the
    # canon-guard / L4 reading position. gather_timeline MUST query
    # before_order=at_order (not the sparse chronological axis), or dateless events
    # — the majority, esp. CJK — never carry across chapters (LOOM-32 Round-2).
    scene_sort_order = None
    if chapter_id is not None:
        scene_sort_order = (
            req.chapter_sort_hint if req.chapter_sort_hint is not None
            else (await book.get_chapter_sort_orders([chapter_id])).get(str(chapter_id))
        )
    at_order = scene_at_order(scene_sort_order)
    # RECENT-WINDOW lower bound (/review-impl MED#1): the timeline endpoint orders
    # event_order ASC + LIMIT, so deep in a long book an unbounded query returns the
    # OLDEST prior events. Bound the lookback to the last N chapters before this one
    # so the carry is RECENT. None when the scene is within the first N chapters
    # (carry all prior) or its chapter is unplaceable.
    timeline_after = None
    _window = settings.pack_timeline_recent_chapters
    if scene_sort_order is not None and _window > 0 and scene_sort_order > _window:
        lo = scene_at_order(scene_sort_order - _window)  # (N - W) × stride
        timeline_after = lo - 1 if lo is not None else None  # strict '>' → include chapter (N-W)

    # FD-1 S3 — re-inject the open-promise ledger only when the Work opts in AND
    # a repo was wired (engine passes it). Otherwise an empty list (no extra read).
    nt_enabled = bool((req.settings or {}).get("narrative_thread_enabled")) and narrative_threads_repo is not None

    # Composition-LOCAL lenses (canon/structural/recent/open_promises) are keyed on
    # the DELTA project_id — they read the DERIVATIVE Work's own outline/canon/drafts
    # (a derivative writes forward from branch_point; its delta is its authoring).
    # The KNOWLEDGE lenses (present/timeline/lore) get the two-project merge below.
    # T3.6 — the reference lens is composition-LOCAL (own DB + provider-registry
    # embed), keyed on the DELTA project (a derivative's references are its OWN
    # authoring, never inherited). The embed model is the Work's configured one;
    # None (unset) → the lens no-ops. Gated on both the repo and client being wired.
    ref_model = reference_embed_model(req.settings)
    # 23 BA12 — the arc lens is GATED (structure_repo wired AND the scene's chapter
    # carries a structure_node_id) and best-effort. When dormant it costs nothing (an
    # empty string), riding the same parallel gather as the other soft lenses.
    arc_gated = (
        gather_arc(structure_repo, structure_node_id, story_order=story_order,
                   narrative_threads_repo=narrative_threads_repo,
                   open_promises_cap=settings.pack_open_promises_cap)
        if (structure_repo is not None and structure_node_id is not None) else _empty_str()
    )
    # X-7 / BE-M2 — the MOTIF lens, gated exactly like the arc lens (both repos wired AND
    # the node carries an id) and best-effort. Dormant ⇒ an empty string ⇒ byte-unchanged.
    motif_node_id = _as_uuid(node.get("id"))
    motif_gated = (
        gather_motif(motif_application_repo, motif_repo, req.project_id, motif_node_id,
                     user_id=req.user_id)
        if (motif_application_repo is not None and motif_repo is not None
            and motif_node_id is not None and req.project_id is not None)
        else _empty_str()
    )
    canon, (present, seen_p), (timeline, seen_t), (beat, threads, planned), recent, (lore, seen_l), open_promises, (references, _seen_r), arc_text, motif_text = (
        await asyncio.gather(
            gather_canon(canon_repo, req.project_id, story_order),
            gather_present(glossary, knowledge, book_id=req.book_id, user_id=req.user_id,
                           project_id=req.project_id, bearer=req.bearer, query=query,
                           present_entity_ids=present_ids, language=reader_lang),
            gather_timeline(knowledge, req.bearer, req.project_id, at_order, after_order=timeline_after),
            gather_structural(outline_repo, scene_links_repo,
                              project_id=req.project_id, node=node),
            gather_recent(book, req.book_id, chapter_id, req.bearer,
                          jobs_repo=jobs_repo, project_id=req.project_id,
                          story_order=story_order) if chapter_id else _empty_list(),
            gather_lore(knowledge, req.bearer, req.project_id, query, language=reader_lang),
            gather_open_promises(narrative_threads_repo, req.project_id,
                                 cap=settings.pack_open_promises_cap) if nt_enabled else _empty_list(),
            gather_references(references_repo, embedding_client, user_id=req.user_id,
                              project_id=req.project_id, query=query, model=ref_model),
            arc_gated,
            motif_gated,
        )
    )

    # C25 — DERIVATIVE two-project base+delta merge (G2). Gather the inherited BASE
    # knowledge grounding from the SOURCE project, branch-FILTERED to ≤ branch_point
    # (so the base never leaks content authored after the divergence), then apply the
    # entity overrides to the inherited base entities, then MERGE with the delta —
    # DELTA WINS on collision. The override set is re-read+re-applied EVERY pack
    # (self-syncing; the caller passes a fresh req.overrides — no cache here).
    extra_canon: list[str] = []
    # M1 (D-DERIVATIVE-ADAPT-FROM-SOURCE) — the inherited SOURCE scene's prose,
    # gathered ONLY for the `adapt_scene` op on a derivative (every other op leaves
    # the pack byte-unchanged). Empty otherwise → no <source_scene> block.
    source_scene: list[str] = []
    if is_derivative:
        # branch cutoff on the dense reading-order axis (chapter sort × stride). The
        # base read is capped at min(scene cutoff, branch cutoff) — never past the
        # branch, and never past the scene's own position either.
        branch_at_order = scene_at_order(req.branch_point)
        base_cut = _min_cutoff(at_order, branch_at_order)
        base_after = _min_cutoff(timeline_after, branch_at_order)
        (base_present, base_seen_p), (base_timeline, base_seen_t), (base_lore, base_seen_l) = (
            await asyncio.gather(
                gather_present(glossary, knowledge, book_id=req.book_id, user_id=req.user_id,
                               project_id=req.source_project_id, bearer=req.bearer, query=query,
                               present_entity_ids=present_ids, language=reader_lang),
                gather_timeline(knowledge, req.bearer, req.source_project_id, base_cut,
                                after_order=base_after),
                gather_lore(knowledge, req.bearer, req.source_project_id, query, language=reader_lang),
            )
        )
        # Merge base + delta with DELTA precedence; base timeline is re-capped at the
        # branch by the per-event filter below (base_cut already bounded the query;
        # the spoiler re-filter stays the defensive belt).
        present = M.merge_present(base_present, present)
        timeline = M.merge_timeline(_cap_events(base_timeline, branch_at_order), timeline)
        lore = M.merge_lore(_cap_lore(base_lore, req.branch_point), lore)
        # Override mutation (DPS2) — applied to the MERGED present (AFTER the base+
        # delta merge), so the derivative's divergence truth wins over BOTH the
        # inherited base AND the delta version of an entity. This matters because the
        # glossary `present` lens is BOOK-scoped (not project-scoped): base and delta
        # surface the SAME glossary bio for an entity, and delta would otherwise
        # shadow the overridden base copy. The overrides are the derivative's own
        # statement about the entity, so they apply last. Added canon-rule scope →
        # extra_canon. CROSS-SPACE reconcile: an override target may be a KNOWLEDGE
        # node id while present items key on the GLOSSARY anchor — resolve each target
        # → its glossary_entity_id so the match lands (the normalization seam);
        # best-effort, a failed resolve falls back to matching the raw target (it may
        # already be a glossary id). Re-read+re-applied EVERY pack (self-syncing).
        target_anchor = await _resolve_override_anchors(knowledge, req.bearer, req.overrides)
        present, extra_canon = M.apply_entity_overrides(
            present, req.overrides, target_anchor=target_anchor)
        seen_p = seen_p or base_seen_p
        seen_t = seen_t or base_seen_t
        seen_l = seen_l or base_seen_l

        # M1 — read the inherited SOURCE scene's prose ONLY for the adapt op. The
        # derivative shares the source book_id + chapter spine (COW), so the source
        # prose lives in the SAME chapter draft (chapter_id) on the shared book_id.
        # Spoiler-bounded ≤ the branch inside the lens (a pre-branch chapter is
        # inherited canon → empty). Gated to adapt_scene so every other derivative
        # op's pack is unchanged; gated on a resolvable chapter_id (a plan-free
        # adapt with no chapter → nothing to read → FE falls back to draft_scene).
        if req.operation == "adapt_scene" and chapter_id is not None:
            source_scene = await gather_source_scene(
                book, req.book_id, chapter_id, req.bearer,
                branch_point=req.branch_point, chapter_sort_order=scene_sort_order,
            )

    # The scene's own chapter sort is resolved above; here resolve ONLY the lore
    # hits whose chapter_index is None (best-effort ingest left it unset).
    sort_map: dict[str, int] = {}
    if chapter_id is not None and scene_sort_order is not None:
        sort_map[str(chapter_id)] = scene_sort_order
    lore_to_resolve: list[UUID] = []
    for h in lore:
        if h.get("chapter_index") is None:
            sid = _as_uuid(h.get("source_id"))
            if sid is not None:
                lore_to_resolve.append(sid)
    if lore_to_resolve:
        sort_map.update(await book.get_chapter_sort_orders(lore_to_resolve))

    # Spoiler — two axes. In-world (L1b) on the dense event_order axis (at_order);
    # reading-order (L4) on the chapter sort axis (scene_sort_order).
    tl_kept, tl_dropped = spoiler.filter_inworld_events(timeline, at_order)

    def position_for(h: dict[str, Any]) -> int | None:
        ci = h.get("chapter_index")
        if isinstance(ci, int):
            return ci
        return sort_map.get(str(h.get("source_id")))

    l4 = spoiler.filter_reading_order(lore, scene_sort_order, position_for)
    if l4.dropped_no_position:
        logger.info(
            "l4_dropped_no_position=%d (project=%s node=%s)",
            l4.dropped_no_position, req.project_id, node.get("id"),
        )

    # T3.4 — per-scene grounding steering. Read the scene's pin/exclude set (best-
    # effort: an unwired repo or a node without an id → no-op) and apply it to the
    # spoiler-ELIGIBLE items only (canon/present/lore AFTER the spoiler filters), so
    # a pin can NEVER resurrect a spoiler-dropped item (preserves the T2.3 cutoff).
    # Excluded items are dropped from the pack; pinned lore sources are force-kept
    # through the budget (protected in build_segments below).
    grounding_items, canon, present, lore_kept, references_kept, pinned_lore_ids, pinned_reference_ids = (
        await _apply_grounding_pins(
            grounding_pins_repo, req.project_id, node.get("id"),
            canon=canon, present=present, lore_hits=l4.kept, references=references,
        )
    )

    bundle = LensBundle(
        canon=canon, present=present, timeline=tl_kept, beat=beat, threads=threads,
        planned=planned, recent=recent, lore=lore_kept,
        knowledge_seen=bool(seen_p or seen_t or seen_l),
        open_promises=open_promises,  # FD-1 S3 — re-injected open-promise ledger
        extra_canon=extra_canon,  # C25 — added canon-rule scope from overrides
        references=references_kept,  # T3.6 — author reference passages (excludes dropped)
        source_scene=source_scene,  # M1 — inherited source prose for the adapt op (empty otherwise)
    )

    # S2 — when the raw "story so far" is large (long chapter), COMPRESS the older
    # portion into a re-injectable state summary instead of letting the budget
    # tail-trim it. Keep the last N immediate paragraphs verbatim. compress_fn is
    # fed only the spoiler-FILTERED timeline (tl_kept) + strictly-prior prose, so
    # it cannot leak future canon (/review-impl H2). Degrade-safe: "" → keep raw.
    keep = max(1, settings.pack_compress_keep_immediate)
    recent_chars = sum(len(p) for p in bundle.recent)
    if (compress_fn is not None and len(bundle.recent) > keep
            and recent_chars > settings.pack_compress_recent_threshold_chars):
        older = bundle.recent[:-keep]
        immediate = bundle.recent[-keep:]
        timeline_texts = [
            t for t in (f'{e.get("title", "")}: {e.get("summary", "")}'.strip(": ").strip()
                        for e in tl_kept) if t
        ]
        plan = (node.get("synopsis") or node.get("goal") or "").strip()
        try:
            summary = await compress_fn(older, timeline_texts, plan)
        except Exception:  # noqa: BLE001 — compress must never fail a pack
            logger.warning("compress_fn raised — keeping raw recent prose", exc_info=True)
            summary = ""
        if summary:
            logger.info(
                "S2 compress engaged: %d older paras (%d chars) → summary %d chars "
                "(project=%s node=%s)",
                len(older), recent_chars, len(summary), req.project_id, node.get("id"),
            )
            bundle.state_summary = summary
            bundle.recent = immediate

    segs = assemble.build_segments(bundle, guide=req.guide, pinned_lore_ids=pinned_lore_ids,
                                   pinned_reference_ids=pinned_reference_ids)
    bres = B.enforce_budget(segs, budget_tokens, counter or B.default_counter())
    blocks = assemble.segments_to_blocks(bres.kept)
    prompt = assemble.render(blocks)

    # 23 BA12 — inject the ARC frame as a protected structural header, FIRST (it
    # frames every other block: "this scene is ~60% through arc 'Betrayal'…"). It
    # rides OUTSIDE the budget like the block delimiters themselves — a compact,
    # high-value steer (chain/tracks/pacing/cast + a capped promise rollup), same
    # protected posture as canon/present/beat. `render()` only knows _BLOCK_ORDER,
    # so the <arc> frame is composed here rather than in assemble.py. Empty (the
    # gate: no structure_repo / no structure_node_id / a deleted arc) → byte-unchanged.
    # X-7 / BE-M2 — the MOTIF frame, injected IMMEDIATELY AFTER <arc> (so the prompt reads
    # <arc> → <motif> → the rest). The arc is the durable CHAPTER-level spec frame; the
    # motif is the SCENE-level beat structure inside it. Like <arc> it is composed here,
    # not via assemble.py's _BLOCK_ORDER ("arc" is deliberately absent from assemble.py:25),
    # and it rides OUTSIDE enforce_budget — which is why gather_motif caps it. Empty (the
    # gate: repos unwired / no binding / an archived motif) → byte-unchanged.
    if motif_text:
        blocks["motif"] = motif_text
        prompt = f"<motif>\n{motif_text}\n</motif>" + (f"\n{prompt}" if prompt else "")
    if arc_text:
        blocks["arc"] = arc_text
        prompt = f"<arc>\n{arc_text}\n</arc>" + (f"\n{prompt}" if prompt else "")

    warnings: list[str] = []
    if not bundle.knowledge_seen:
        warnings.append("grounding_unavailable: no knowledge-graph data for this scene/project (C3a)")
    if l4.dropped_no_position:
        warnings.append(f"l4_dropped_no_position={l4.dropped_no_position}")
    if bres.over_budget:
        warnings.append("over_budget: protected context exceeds the token target")

    return PackedContext(
        blocks=blocks, prompt=prompt, profile=profile,
        token_count=bres.total_tokens, dropped_count=bres.dropped_count,
        l4_dropped_no_position=l4.dropped_no_position,
        grounding_available=bundle.knowledge_seen, over_budget=bres.over_budget,
        scene_sort_order=scene_sort_order,
        reinjected_promise_count=len(open_promises),  # FD-1 S4b — S3 fired-signal
        warnings=warnings,
        grounding_items=grounding_items,  # T3.4 — addressable pin/exclude state
    )


async def _pack_null_project(
    req: PackRequest, *, grant: "GrantClient | None", need: "GrantLevel | None",
    budget_tokens: int | None = None,
) -> PackedContext:
    """C16 (WG-3): build an EMPTY-but-valid pack for a lazy null-project Work.

    No knowledge lens is called (the project has no knowledge graph yet — and a
    null project_id would widen the timeline endpoint cross-project, the C23 leak),
    so grounding is empty and `grounding_available=False`. The book grant is STILL
    enforced (a null project_id doesn't bypass authorization). The author guide is
    sanitised and kept so the writer's instruction still reaches the prompt. Generate
    proceeds → prose returns (the FE already signposts empty grounding, C15)."""
    from app.grant_client import get_grant_client
    from app.grant_deps import authorize_book
    await authorize_book(
        grant or get_grant_client(), req.book_id, req.user_id, need or GrantLevel.VIEW,
    )

    profile = profile_mod.from_settings(req.settings)
    bundle = LensBundle(
        canon=[], present=[], timeline=[], beat=[], threads=[],
        planned=[], recent=[], lore=[], knowledge_seen=False, open_promises=[],
    )
    segs = assemble.build_segments(bundle, guide=req.guide)
    # /review-impl MED: this path used to read the FLAT settings.pack_token_budget
    # directly, silently skipping the caller's already-scale_by_window'd
    # budget_tokens — the one pack() branch that never scaled with context_length.
    bres = B.enforce_budget(
        segs, budget_tokens if budget_tokens is not None else settings.pack_token_budget,
        B.default_counter(),
    )
    blocks = assemble.segments_to_blocks(bres.kept)
    warnings = [
        "grounding_unavailable: this work has no knowledge project yet "
        "(knowledge-service was unavailable at setup) — writing proceeds, grounding "
        "will enrich once the project is created (C16/WG-3)",
    ]
    if bres.over_budget:
        warnings.append("over_budget: protected context exceeds the token target")
    return PackedContext(
        blocks=blocks, prompt=assemble.render(blocks), profile=profile,
        token_count=bres.total_tokens, dropped_count=bres.dropped_count,
        l4_dropped_no_position=0, grounding_available=False,
        over_budget=bres.over_budget, scene_sort_order=None,
        reinjected_promise_count=0, warnings=warnings,
    )


async def _empty_list() -> list[Any]:
    """gather() placeholder for the L3 lens when the scene has no chapter_id."""
    return []


async def _empty_str() -> str:
    """gather() placeholder for the 23 BA12 arc lens when it is dormant (no
    structure_repo wired / the scene's chapter carries no structure_node_id)."""
    return ""


_GROUNDING_LABEL_MAX = 160


def _trim_label(text: str) -> str:
    """A compact single-line display label for a grounding item (the FE renders
    these in the pin/exclude panel; full text still lives in the packed block)."""
    t = " ".join((text or "").split())
    return t if len(t) <= _GROUNDING_LABEL_MAX else t[: _GROUNDING_LABEL_MAX - 1] + "…"


async def _apply_grounding_pins(
    repo, project_id: UUID, node_id: Any, *,
    canon: list[Any], present: list[dict[str, Any]], lore_hits: list[dict[str, Any]],
    references: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], set[str], set[str]]:
    """T3.4/T3.6 — read the scene's pin/exclude set and apply it to the eligible
    items. Returns (grounding_items, kept_canon, kept_present, kept_lore,
    kept_references, pinned_lore_ids, pinned_reference_ids). Best-effort: an unwired
    repo, a node with no id, or a repo failure → no steering (all items kept, empty
    grounding_items)."""
    references = references or []
    node_uuid = _as_uuid(node_id)
    if repo is None or node_uuid is None:
        return [], canon, present, lore_hits, references, set(), set()
    try:
        rows = await repo.list_for_scene(project_id, node_uuid)
    except Exception:  # noqa: BLE001 — steering is advisory; never fail a pack
        logger.warning("grounding pins read failed", exc_info=True)
        return [], canon, present, lore_hits, references, set(), set()

    pins: set[tuple[str, str]] = set()
    excludes: set[tuple[str, str]] = set()
    for r in rows:
        (excludes if r.action == "exclude" else pins).add((r.item_type, str(r.item_id)))

    items: list[dict[str, Any]] = []

    # canon — id = rule uuid (composition-owned, stable)
    kept_canon: list[Any] = []
    for r in canon:
        key = ("canon", str(r.id))
        excluded = key in excludes
        items.append({"type": "canon", "id": str(r.id), "label": _trim_label(r.text),
                      "pinned": key in pins, "excluded": excluded})
        if not excluded:
            kept_canon.append(r)

    # present — id = glossary anchor entity_id (stable, not the localized label)
    kept_present: list[dict[str, Any]] = []
    for p in present:
        eid = p.get("entity_id")
        if eid is None:  # not addressable — keep, never list
            kept_present.append(p)
            continue
        key = ("present", str(eid))
        excluded = key in excludes
        label = f'{p.get("name", "")}: {p.get("summary", "")}'.strip(": ").strip() or str(p.get("name", ""))
        items.append({"type": "present", "id": str(eid), "label": _trim_label(label),
                      "pinned": key in pins, "excluded": excluded})
        if not excluded:
            kept_present.append(p)

    # lore — id = source_id (deduped for the addressable list; exclude/pin act on
    # ALL hits of a source). A hit with no source_id is not addressable (kept, never
    # listed). pinned_lore_ids feeds build_segments' protected flag.
    excluded_srcs = {iid for (t, iid) in excludes if t == "lore"}
    pinned_lore_ids = {iid for (t, iid) in pins if t == "lore"}
    seen_src: set[str] = set()
    kept_lore: list[dict[str, Any]] = []
    for h in lore_hits:
        src = h.get("source_id")
        src_s = str(src) if src is not None else None
        if src_s is None or src_s not in excluded_srcs:
            kept_lore.append(h)
        if src_s is not None and src_s not in seen_src:
            seen_src.add(src_s)
            key = ("lore", src_s)
            items.append({"type": "lore", "id": src_s, "label": _trim_label(h.get("text", "")),
                          "pinned": key in pins, "excluded": key in excludes})

    # references — id = reference_source.id (composition-owned, stable). exclude
    # drops it from the pack; pin force-keeps it through the budget (protected in
    # build_segments). A hit with no id is not addressable (kept, never listed).
    pinned_reference_ids = {iid for (t, iid) in pins if t == "reference"}
    kept_references: list[dict[str, Any]] = []
    for h in references:
        rid = h.get("id")
        rid_s = str(rid) if rid is not None else None
        if rid_s is None:
            kept_references.append(h)
            continue
        key = ("reference", rid_s)
        excluded = key in excludes
        if not excluded:
            kept_references.append(h)
        label = " — ".join(x for x in [str(h.get("title") or "").strip(),
                                       str(h.get("content") or "").strip()] if x)
        items.append({"type": "reference", "id": rid_s, "label": _trim_label(label),
                      "pinned": key in pins, "excluded": excluded})

    return items, kept_canon, kept_present, kept_lore, kept_references, pinned_lore_ids, pinned_reference_ids


async def _resolve_override_anchors(
    knowledge: KnowledgeClient, bearer: str, overrides: list[Any] | None,
) -> dict[str, str]:
    """C25 — resolve each override's `target_entity_id` (a KNOWLEDGE canonical_id,
    as recorded by the C24 wizard) to its GLOSSARY anchor (`glossary_entity_id`), so
    the override-apply can match a present item (which keys on the glossary anchor).
    Returns {raw_target: glossary_anchor}; a target that doesn't resolve (or has no
    anchor) is simply omitted (apply_entity_overrides then falls back to matching
    the raw target — it may already be a glossary id). Best-effort: a knowledge
    outage yields an empty map (the override degrades, never 500s the pack)."""
    if not overrides:
        return {}
    # NOTE (adversary review): get_entity is user-scoped but NOT project-scoped — the
    # override DECLARES its own target id, so we resolve it project-agnostically. This
    # can't leak grounding content: the resolved anchor only re-keys the override for
    # matching against present items that are ALREADY base/delta-scoped; a target that
    # names another project's node simply won't match any present item (the override
    # silently no-ops) rather than widening any read.
    tids = [str(getattr(ov, "target_entity_id", "")) for ov in overrides
            if getattr(ov, "target_entity_id", None) is not None]
    if not tids:
        return {}
    # Resolve all targets concurrently (one pack can carry many overrides — avoid N
    # serial round-trips). dedup tids so a repeated target is fetched once.
    uniq = list(dict.fromkeys(tids))
    details = await asyncio.gather(*(knowledge.get_entity(bearer, t) for t in uniq))
    out: dict[str, str] = {}
    for tid, detail in zip(uniq, details):
        anchor = ((detail or {}).get("entity") or {}).get("glossary_entity_id")
        if anchor:
            out[tid] = str(anchor)
    return out


def _min_cutoff(a: int | None, b: int | None) -> int | None:
    """C25 — the tighter of two reading-order cutoffs (None = unbounded). Used to
    cap the BASE read at min(scene cutoff, branch cutoff): the base must never carry
    content past the branch_point NOR past the scene's own position."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _cap_events(events: list[dict[str, Any]], branch_at_order: int | None) -> list[dict[str, Any]]:
    """C25 belt-and-suspenders — drop BASE events at/after the branch cutoff on the
    dense event_order axis (the query already bounded ≤ branch, this re-asserts it
    so a stub/misorder can't leak post-branch base canon into the derivative). A
    None branch cutoff (unplaceable) keeps all (the downstream spoiler filter still
    applies the scene cutoff)."""
    if branch_at_order is None:
        return events
    return [
        e for e in events
        if not (isinstance(e.get("event_order"), int) and e["event_order"] >= branch_at_order)
    ]


def _cap_lore(hits: list[dict[str, Any]], branch_point: int | None) -> list[dict[str, Any]]:
    """C25 — drop BASE lore hits whose chapter reading position is at/after the
    branch_point (keep only ≤ branch). A hit with no resolvable chapter_index is
    KEPT here (the downstream L4 reading-order spoiler filter conservative-drops it
    against the scene position) — capping it here would double-drop without the
    l4_dropped_no_position accounting."""
    if branch_point is None:
        return hits
    out: list[dict[str, Any]] = []
    for h in hits:
        ci = h.get("chapter_index")
        if isinstance(ci, int) and ci >= branch_point:
            continue
        out.append(h)
    return out
