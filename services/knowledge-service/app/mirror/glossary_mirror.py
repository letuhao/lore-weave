"""The glossary→KG mirror DETECTOR — an anti-join, and the number it produces.

D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER, measured 2026-08-12 on the acceptance book:

    truth (entities glossary-service emits for)   46
    of those, mirrorable (has a name yet)         43
    mirrored (present in the KG)                  26
    MISSING                                       17

The first published figure for this was "22 of 48 (46%)" and it was wrong — computed from
`SELECT count(*) FROM glossary_entities`, which counts 2 soft-deleted rows the KG is
correct not to hold and 3 nameless drafts the handler declines by design. Five of the
twenty-two were the detector's own predicate being sloppy. That is the entire reason the
two predicates below are owned where they are.

Nothing in this system had ever computed those four numbers. The projection is
at-least-once delivery through the outbox with no reconciliation: three entities were
created in one batch on 2026-08-03, all three emitted and published, and only one reached
the graph. The handler has since been fixed (`D-T27-LIVE-REPLAY`) and a live replay proves
it correct today — but nothing back-fills what was lost while it was broken, and nothing
reports that anything is missing. Every canon check in this architecture reads the KG, so
a 40% hole there is a canon check reasoning about a cast it cannot fully see.

THIS MODULE ONLY DETECTS. It writes nothing.
---------------------------------------------
The repairer is the next step and it should re-emit through the outbox rather than write
the graph directly: that path is already proven, already idempotent (the MERGE is keyed on
`glossary_entity_id`), and adding a second writer to the mirror would be a new class of
divergence rather than a fix for this one.

THE TWO PREDICATES, AND WHY THEY ARE OWNED SEPARATELY
------------------------------------------------------
* Which entities EXIST — glossary-service's `mirrorTruthPredicate`, served by
  `/internal/books/{id}/mirror-truth-ids`. Only the producer can answer it, and asking a
  narrower proxy (`entity-ids`, which filters the STORY flag `alive`) manufactures orphans.
* Which of those SHOULD be mirrored — `app.mirror.predicate.is_mirrorable`, this service's
  own handler skip. A nameless draft is not lost, it is not yet nameable.

Presence is asked through the `GraphStore` PORT (`neighborhood`), one id at a time, so the
detector works against whichever adapter T43 selects — Neo4j today, AGE under test. That is
N bounded lookups rather than one bulk read: the port has no batched
`known_glossary_entity_ids`, and this is a detector, not a hot path. When the repairer
needs it at scale, THAT is the demand which earns the port method — the port's own
docstring says it grows by demand, not by inventory. `entity_cap` keeps the cost bounded
and reports when it bit rather than truncating silently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from app.mirror.predicate import is_mirrorable

logger = logging.getLogger(__name__)

__all__ = ["MirrorDrift", "detect_mirror_drift"]

# One detection walks this many entities at most. A book with more is reported as
# `truncated`, never silently cut: an under-reported divergence looks exactly like a
# healthy mirror, which is the single failure mode this detector must not have.
DEFAULT_ENTITY_CAP = 2000


@dataclass
class MirrorDrift:
    """The anti-join, both directions, plus what was deliberately not counted."""

    project_id: str
    book_id: str
    # Every row glossary-service says exists (its emit predicate).
    truth_total: int = 0
    # Of those, the ones this service's handler would actually write a node for.
    mirrorable: int = 0
    # Of the mirrorable ones, the ones the graph holds.
    mirrored: int = 0
    # Mirrorable but absent — the divergence. THIS is the metric that must trend to zero.
    missing_ids: list[str] = field(default_factory=list)
    # Truth rows the handler declines by design (no name yet). Counted so the gap between
    # `truth_total` and `mirrored` is fully accounted for and none of it is mysterious.
    not_mirrorable: int = 0
    # The truth enumeration ran out of pages, or the entity cap bit. Either way the numbers
    # below are a LOWER BOUND on the divergence.
    truncated: bool = False

    @property
    def missing(self) -> int:
        return len(self.missing_ids)

    def as_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "book_id": self.book_id,
            "truth_total": self.truth_total,
            "mirrorable": self.mirrorable,
            "mirrored": self.mirrored,
            "missing": self.missing,
            "missing_ids": self.missing_ids,
            "not_mirrorable": self.not_mirrorable,
            "truncated": self.truncated,
            # ⚠️ NOT A MEASUREMENT — stated, not computed. The other direction (a node in
            # the KG whose glossary row is gone, i.e. a delete that failed to cascade)
            # needs an enumeration of the graph's glossary ids, and the port has no bulk
            # read. Reporting `orphans: 0` from a check that never ran would be the
            # accounting artefact this plan exists to prevent, so it is named as absent
            # instead. Hand-measured once on the acceptance book: 0 of 26.
            "orphans": "not measured — see docstring",
        }


async def detect_mirror_drift(
    *,
    session,
    glossary_client,
    project_id: UUID,
    book_id: UUID,
    user_id: UUID,
    entity_cap: int = DEFAULT_ENTITY_CAP,
) -> MirrorDrift | None:
    """Anti-join the glossary truth set against the KG. Read-only.

    Returns None when the truth side is unreachable — NOT an empty drift. An unreachable
    glossary would otherwise render as "every entity is missing", turning an outage into a
    catastrophic-looking divergence report, or (worse, with the anti-join inverted) as a
    clean zero.
    """
    from app.adapters.graph_store_provider import get_graph_store

    truth = await glossary_client.list_mirror_truth_ids(book_id)
    if truth is None:
        logger.warning(
            "mirror drift: glossary truth unreachable for book=%s — reporting nothing "
            "rather than a fabricated divergence", book_id,
        )
        return None
    rows, truncated = truth

    drift = MirrorDrift(
        project_id=str(project_id), book_id=str(book_id), truth_total=len(rows),
        truncated=truncated,
    )

    expected: list[str] = []
    for row in rows:
        entity_id = str(row.get("entity_id") or "").strip()
        if not entity_id:
            continue
        # `has_name` is the truth side's report of the emitted payload's name; the kind
        # comes from the same row. The DECISION is is_mirrorable's, so this detector and
        # the handler cannot disagree about what "should be there" means.
        name_proxy = "x" if row.get("has_name") else ""
        if is_mirrorable(name_proxy, str(row.get("kind_code") or "")):
            expected.append(entity_id)
        else:
            drift.not_mirrorable += 1

    if len(expected) > entity_cap:
        logger.warning(
            "mirror drift: book=%s has %d mirrorable entities, capped at %d — the "
            "divergence below is a LOWER BOUND", book_id, len(expected), entity_cap,
        )
        expected = expected[:entity_cap]
        drift.truncated = True
    drift.mirrorable = len(expected)

    store = get_graph_store(session)
    for entity_id in expected:
        # rel_cap=1: presence is the question, the neighbourhood is not. An uncapped
        # traversal per entity would make a detector expensive enough not to run.
        detail = await store.neighborhood(
            user_id=str(user_id), glossary_entity_id=entity_id,
            project_id=str(project_id), rel_cap=1,
        )
        if detail is None:
            drift.missing_ids.append(entity_id)
        else:
            drift.mirrored += 1

    logger.info(
        "mirror drift: project=%s truth=%d mirrorable=%d mirrored=%d MISSING=%d "
        "not_mirrorable=%d truncated=%s",
        project_id, drift.truth_total, drift.mirrorable, drift.mirrored,
        drift.missing, drift.not_mirrorable, drift.truncated,
    )
    return drift
