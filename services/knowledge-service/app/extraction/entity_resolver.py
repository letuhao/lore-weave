"""K13.0 resolver — anchor-aware entity resolution for extraction writers.

Before minting a new `:Entity` via `merge_entity`, check whether the
candidate name (or any of its aliases) matches a glossary anchor of
the same kind. If so, skip the merge round-trip and return an Entity
pointing at the anchor's canonical_id — the caller still runs
`add_evidence` so the anchor accumulates extraction evidence on the
"no new node" path.

Why this sits outside `entities.py`: the repo primitive deliberately
has no side-channel knowledge of glossary state. Anchor resolution is
an extraction-pipeline concern (which names already exist for THIS
book's run), not a graph-primitive concern. Keeping the resolver in
`app/extraction/` keeps the repo thin and the pipeline composable.

Reference: KSA §3.4.E (two-layer anchoring), §6.0.3 (resolver);
K13.0 plan row in KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import logging
from typing import Iterable, Mapping

from uuid import UUID

from app.adapters.graph_store_provider import get_graph_store
from app.db.neo4j_helpers import CypherSession
from loreweave_extraction.canonical import canonicalize_entity_name
from app.db.graph_repos.entities import Entity, merge_entity, merge_entity_at_id
from app.db.repositories.entity_alias_map import EntityAliasMapRepo
from app.extraction.anchor_loader import Anchor
from app.metrics import (
    anchor_resolver_hits_total,
    anchor_resolver_misses_total,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AnchorIndex",
    "build_anchor_index",
    "normalize_kind_for_anchor_lookup",
    "resolve_or_merge_entity",
]

# Lookup key: (folded-name-or-alias, kind). Kind-qualified so
# legitimately distinct entities ("Phoenix" person vs "PHOENIX" org)
# don't alias over each other.
AnchorIndex = Mapping[tuple[str, str], Anchor]


# Extractor kind → glossary `kind_code`.
#
# The LLM entity extractor (K17.4) emits a narrow vocabulary —
# {"person","place","organization","artifact","concept","other"} —
# while the glossary SSOT uses the domain seed vocabulary (character,
# location, item, event, terminology, trope, …). Without this map,
# every Pass 2 (LLM) candidate would fold to a kind that never
# matches an anchor and the K13.0 pre-loader would land cosmetic
# only for Pass 1.
#
# Applied at lookup time, NOT at index build time — anchors keep
# their native glossary `kind_code` so Pass 1 writers (which already
# emit glossary-aligned kinds like "character") hit them directly.
#
# Unmapped kinds (e.g. "other", or a tenant-custom kind) pass through
# unchanged, producing a miss that falls through to `merge_entity` —
# same behavior as having no anchor.
#: Reserved pseudo-kind for the name-only fallback slot in the anchor index. Not a real
#: kind — no extractor or glossary vocabulary may emit it, so it cannot collide.
_ANY_KIND = "\x00any"

_EXTRACTOR_TO_GLOSSARY_KIND: Mapping[str, str] = {
    "person": "character",
    "place": "location",
    "artifact": "item",
    "concept": "terminology",
    # "organization" and "event" already match glossary kind_code.
}

#: The glossary kinds an extractor can actually EXPRESS — the image of the map above
#: plus the pass-through codes. Load-bearing for the D-KG-KIND-VOCAB-FORK fallback: if
#: an anchor's kind is in here and the extractor chose a DIFFERENT one, that was a real
#: classification decision (a `place` Phoenix is not the `character` Phoenix) and the
#: disagreement is meaningful. If the anchor's kind is NOT in here — `power_system`,
#: say — the extractor had no way to name it, so its choice carries no information and
#: cannot be evidence of a different entity.
#:
#: Approximated statically from the mapping rather than read from the project's KG
#: schema. A project that adopts a wider schema (xianxia-harem adds technique/event/
#: relationship) only makes MORE kinds expressible, which would narrow the fallback
#: further — never widen it — so the static form stays on the safe side.
_EXTRACTOR_EXPRESSIBLE_KINDS: frozenset[str] = frozenset(
    _EXTRACTOR_TO_GLOSSARY_KIND.values()
) | {"organization", "event", "other"}


def normalize_kind_for_anchor_lookup(kind: str) -> str:
    """Translate an extractor kind to the glossary `kind_code` used
    by anchor nodes. Returns the input unchanged if no mapping
    applies (matches the glossary-kind pass-through case for Pass 1
    writers and handles tenant-custom extractor outputs gracefully).
    """
    return _EXTRACTOR_TO_GLOSSARY_KIND.get(kind, kind)


def _fold(name: str) -> str:
    """Folded form used for both indexing and lookup.

    Goes through `canonicalize_entity_name` first so surface-level
    variations (accents, case, whitespace) hash the same way the
    repo's canonical_id does.
    """
    return canonicalize_entity_name(name).strip().casefold()


def build_anchor_index(
    anchors: Iterable[Anchor],
) -> dict[tuple[str, str], Anchor]:
    """Index `anchors` by (folded-name, kind), expanding aliases.

    Each anchor contributes its display name plus every alias as
    separate lookup keys. On a collision within the same kind, the
    first anchor wins and a WARNING is logged — the operator can
    then go clean up the duplicate glossary row.

    D-KG-KIND-VOCAB-FORK: the index ALSO carries a name-only fallback under the
    ``(folded, _ANY_KIND)`` key, populated only when a folded name belongs to exactly
    ONE anchor across every kind. See `resolve_or_merge_entity` for why.
    """
    index: dict[tuple[str, str], Anchor] = {}
    by_name: dict[str, set[str]] = {}
    first_by_name: dict[str, Anchor] = {}
    for a in anchors:
        for n in (a.name, *a.aliases):
            folded = _fold(n)
            if not folded:
                continue
            by_name.setdefault(folded, set()).add(a.canonical_id)
            first_by_name.setdefault(folded, a)
            key = (folded, a.kind)
            existing = index.get(key)
            if existing is not None and existing.canonical_id != a.canonical_id:
                logger.warning(
                    "K13.0 resolver: alias collision fold=%r kind=%s "
                    "kept=%s dropped=%s",
                    folded, a.kind,
                    existing.glossary_entity_id,
                    a.glossary_entity_id,
                )
                continue
            index[key] = a
    # Unambiguous names only: if a fold maps to two different anchors (a person and a
    # place both called "Bloom"), the kind is the ONLY thing that tells them apart, so
    # no fallback is registered and the strict lookup still governs.
    for folded, ids in by_name.items():
        if len(ids) == 1:
            index[(folded, _ANY_KIND)] = first_by_name[folded]
    return index


async def resolve_or_merge_entity(
    session: CypherSession,
    index: AnchorIndex,
    *,
    user_id: str,
    project_id: str | None,
    name: str,
    kind: str,
    source_type: str,
    confidence: float = 0.0,
    alias_map_repo: EntityAliasMapRepo | None = None,
    auto_created: bool = False,
    provenance: str = "human_authored",
    job_id: str | None = None,
) -> Entity:
    """Anchor-aware wrapper around `merge_entity`.

    On anchor hit, returns a synthetic Entity bearing the anchor's
    `canonical_id` — no Neo4j round-trip for the merge, because the
    anchor node was already written by K13.0's Pass 0 loader. Callers
    only use `.id` for the subsequent `add_evidence` edge, so a
    lightweight Entity is sufficient.

    On miss, falls through to `merge_entity` (existing behavior).

    C17 alias-map redirect (D-K19d-γb-03 closer): between glossary
    anchor lookup and the SHA-hash MERGE, consult the post-merge
    alias-map. If a previous user merge registered ``name`` as an
    alias of an existing entity, MERGE on that entity's id instead of
    re-deriving the SHA hash (which would resurrect the merged-away
    source). Gated on ``alias_map_repo is not None`` for back-compat
    with extraction call sites that haven't been wired yet — those
    fall through to the original SHA-hash path.

    Stale-row fall-through: if the alias-map row points at an entity
    that has been deleted from Neo4j, ``merge_entity_at_id`` returns
    None; we log a WARNING and fall through to ``merge_entity``. The
    fall-through resurrects the alias as a fresh node — same as
    pre-C17 behavior, but ops gets a clear log line.
    """
    lookup_kind = normalize_kind_for_anchor_lookup(kind)
    folded = _fold(name)
    anchor = index.get((folded, lookup_kind))
    if anchor is None:
        # D-KG-KIND-VOCAB-FORK — name-only fallback for an UNAMBIGUOUS name.
        #
        # The two sides run different, independently-extensible vocabularies: the
        # extractor emits from the project's KG schema (general@v1 is
        # artifact|concept|organization|other|person|place) while a glossary kind is
        # whatever the author's book ontology defines. `_EXTRACTOR_TO_GLOSSARY_KIND`
        # bridges the obvious pairs, but it cannot bridge what it has never seen —
        # `power_system` has no extractor counterpart at all, so `concept` normalised to
        # `terminology` and missed the anchor.
        #
        # Because entity identity is hash(user, project, name, kind), that miss does not
        # degrade to "no anchor" — it MINTS A SECOND NODE beside the author's. Measured
        # on the live Mị Đế chapter: Chân Linh, Vô Cấu Chân Linh and Thần hồn each forked
        # a duplicate next to their anchored twins.
        #
        # A perfect mapping is unreachable (both vocabularies are user-extensible), so
        # identity tolerates kind drift under TWO conditions, both required:
        #
        #   1. the folded name belongs to exactly ONE anchor across all kinds — a name
        #      shared by anchors of different kinds registers no fallback key at all,
        #      because there the kind is the only thing telling them apart;
        #   2. the anchor's kind is one the extractor CANNOT express. If it could have
        #      said `character` and said `place` instead, that is a real classification
        #      decision and the disagreement means something. If the anchor is a
        #      `power_system`, the extractor had no word for it and its `concept` is not
        #      evidence of anything.
        candidate = index.get((folded, _ANY_KIND))
        if candidate is not None and candidate.kind not in _EXTRACTOR_EXPRESSIBLE_KINDS:
            anchor = candidate
            logger.info(
                "K13.0 resolver: kind-vocabulary fallback matched %r "
                "(extractor kind=%s → %s, anchor kind=%s is not expressible)",
                name, kind, lookup_kind, anchor.kind,
            )
    if anchor is not None:
        anchor_resolver_hits_total.labels(kind=lookup_kind).inc()
        return Entity(
            id=anchor.canonical_id,
            user_id=user_id,
            project_id=project_id,
            name=anchor.name,
            canonical_name=canonicalize_entity_name(anchor.name),
            kind=anchor.kind,
            aliases=list(anchor.aliases),
            glossary_entity_id=anchor.glossary_entity_id,
            anchor_score=1.0,
        )
    # Only record misses when there WAS an index to check against.
    # With an empty index every candidate would record a miss, pegging
    # the metric at 100% and making it useless for dashboards — a
    # Mode-1 chat session has no book, no glossary, and no anchors,
    # but the extraction is still working as intended.
    if index:
        anchor_resolver_misses_total.labels(kind=lookup_kind).inc()

    # C17 alias-map redirect.
    if alias_map_repo is not None:
        canonical_alias = canonicalize_entity_name(name)
        if canonical_alias:
            project_scope = project_id or "global"
            target_id = await alias_map_repo.lookup(
                UUID(user_id), project_scope, kind, canonical_alias,
            )
            if target_id is not None:
                redirected = await merge_entity_at_id(
                    session,
                    user_id=user_id,
                    id=target_id,
                    project_id=project_id,
                    name=name,
                    kind=kind,
                    source_type=source_type,
                    confidence=confidence,
                    provenance=provenance,
                )
                if redirected is not None:
                    return redirected
                # Stale row — target was deleted. Log + fall through
                # to SHA hash. Ops can find these via the WARNING
                # filter on this exact message.
                logger.warning(
                    "C17 alias_map points to missing entity user=%s "
                    "kind=%s alias=%s target=%s — falling through "
                    "to SHA-hash MERGE",
                    user_id, kind, canonical_alias, target_id,
                )

    return await get_graph_store(session).resolve_or_merge_entity(  # T17
                user_id=user_id,
        project_id=project_id,
        name=name,
        kind=kind,
        source_type=source_type,
        confidence=confidence,
        auto_created=auto_created,
        provenance=provenance,
        job_id=job_id,
    )
