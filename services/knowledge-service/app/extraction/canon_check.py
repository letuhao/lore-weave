"""D-KG-EXTRACTION-CANON-GATE — Narrative Forge NDLC gate for Knowledge extraction.

`docs/specs/2026-07-05-narrative-forge/00_METHODOLOGY.md` Finding A named Knowledge
extraction the `none`-strictness worst offender (writes straight to Neo4j, zero review).
Two data-driven candidate signals were checked against the REAL KG first and rejected:
`confidence` clusters at 0.9-1.0 with only 7 distinct values platform-wide (no variance
to gate on); `evidence_count` flags 94.5% of Events / 100% of Facts as "low" (single
mention is normal for a novel — a load-bearing plot fact is often stated exactly once,
so mention-count is not a truth proxy the way multi-source corroboration would be for
real-world fact-checking).

This module borrows the ONE gate mechanism the platform audit found is proven and
UNIVERSALLY hard-blocking: composition-service's `app/engine/canon_check.py` symbolic
pre-filter → LLM-judge confirmation. Composition checks a NEW DRAFT against the KG's
EXISTING gone-entities; this checks the CHAPTER TEXT BEING EXTRACTED (about to become
new KG content) against the KG's OWN gone-status as of an EARLIER position — catching a
bad extraction that resurrects a dead/departed character with no revival signal.

Advisory-only by design (CC4 lesson: a critic must never block on its own failure or
turn a fast-path feature into a slow/broken one) — this NEVER blocks extraction from
writing. It flags a candidate for review (via `job_logs`, see
`app/extraction/pass2_orchestrator.py::_maybe_run_canon_check_gate`); nothing here
mutates Neo4j.

2026-07-06 update: a 16-fixture scored eval (`docs/eval/canon-check-judge-2026-07-06.md`)
found Gemma-4 26B QAT reaches 93.75% accuracy / 100% recall — good enough to wire as a
quarantine (log-and-flag) gate, not a hard block. The mechanical pieces (span-matching,
verdict parsing/application, judge request shape) are now shared with composition's
mirror via `loreweave_canon_check` (D-CANON-CHECK-SDK-UNIFY) — this also fixes a real
gap the unification diff found: the previous bare-`except Exception` + manual
`job.result["messages"][0]["content"]` indexing is replaced with the shared, more
precise `LLMError` + `extract_judge_text` handling composition's version already had.
"""

from __future__ import annotations

import logging
from typing import Any

from loreweave_canon_check import (
    CanonCandidateBase,
    apply_verdicts,
    build_judge_request,
    extract_judge_text,
    gone_entities_referenced,
    parse_judge_verdicts,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ExtractionCanonCandidate",
    "gone_entities_asserted_active",
    "judge_extraction_contradiction",
    "check_extraction_canon",
]


class ExtractionCanonCandidate(CanonCandidateBase):
    """One candidate contradiction: an entity marked `gone` in the KG (as of an
    earlier reading position) whose name appears in chapter text about to be
    extracted as new canon. Mirrors composition's `CanonViolation` shape."""

    kind: str = "gone_entity_asserted_active_in_extraction"
    gone_from_order: int | None = None


def gone_entities_asserted_active(
    chapter_text: str, snapshot: dict[str, Any] | None,
) -> list[ExtractionCanonCandidate]:
    """Symbolic pre-filter (pure, no LLM/IO): every `gone` entity in the snapshot
    whose name (or canonical_name) appears in `chapter_text`. Deliberately
    over-inclusive — candidates, not confirmed violations; the judge narrows.
    Empty when the snapshot is absent (degrades to advisory — a knowledge-graph
    outage never blocks extraction). De-duped per entity."""
    rows = gone_entities_referenced(chapter_text, snapshot, extra_field="from_order")
    return [
        ExtractionCanonCandidate(
            entity_id=r["entity_id"], name=r["name"],
            gone_from_order=r.get("from_order"), span=r["span"], matched=r["matched"],
        )
        for r in rows
    ]


# ── LLM-judge: confirm contradiction vs legitimate (flashback/revival/memory) ──

def _build_judge_messages(
    chapter_text: str, candidates: list[ExtractionCanonCandidate], source_language: str,
) -> tuple[str, str]:
    lang = "" if source_language in ("", "auto") else (
        f" Write each `why` in the language with code '{source_language}'."
    )
    system = (
        "You verify story continuity during knowledge extraction. Each listed "
        "character was already established GONE (dead, destroyed, departed, or "
        "lost) in an EARLIER chapter than this one. For each, decide whether THIS "
        "chapter's passage portrays them as an ACTIVE PRESENCE — acting, speaking, "
        "perceiving, or bodily present — with no revival/resurrection signal in "
        "this SAME passage. A memory, flashback, a corpse, others speaking ABOUT "
        "them, or an explicit revival/return is NOT a contradiction. Return ONLY a "
        'JSON object {"verdicts":[{"entity_id":str,"violated":bool,"why":str}]}.'
        + lang
    )
    listed = "\n".join(
        f'- entity_id={c.entity_id} name="{c.name}" (near: {c.span})'
        for c in candidates
    )
    user = f"ALREADY-GONE CHARACTERS REFERENCED:\n{listed}\n\nNEW CHAPTER PASSAGE:\n{chapter_text}"
    return system, user


async def judge_extraction_contradiction(
    llm, *, user_id: str, model_source: str, model_ref: str,
    chapter_text: str, candidates: list[ExtractionCanonCandidate],
    source_language: str = "auto",
) -> list[ExtractionCanonCandidate]:
    """Confirm the symbolic candidates with the LLM-judge — only the FEW
    candidates the cheap pre-filter flagged, never the whole chapter. Sets
    `confirmed`/`why` per candidate.

    Degrade-safe (mirrors composition's CC4 lesson): any LLM/parse failure
    leaves `confirmed=None` (symbolic-only → advisory, never auto-blocks) — the
    judge must never turn extraction into a broken/blocked pipeline on its own
    failure. A candidate the judge omits is also left `confirmed=None`. Verified
    live under a REAL infra fault (a Redis event-wait timeout mid-live-smoke) —
    degraded to symbolic-only exactly as designed, did not crash or hang.

    Judge accuracy (2026-07-06 eval, Gemma-4 26B QAT): 93.75% accuracy, 100%
    recall (never misses a real contradiction), 1 false-positive in 16 scored
    fixtures — good enough for a quarantine/review gate, not a hard block. See
    docs/eval/canon-check-judge-2026-07-06.md for the full scored breakdown."""
    if not candidates:
        return []
    from loreweave_llm.errors import LLMError

    system, user = _build_judge_messages(chapter_text, candidates, source_language)
    req = build_judge_request(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        usage_purpose="extraction_canon_check", extractor="canon_check_poc",
    )
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source,
            model_ref=model_ref, **req,
        )
    except LLMError as exc:
        logger.warning("judge_extraction_contradiction degraded (LLM error): %s — symbolic-only", exc)
        return candidates
    if getattr(job, "status", None) != "completed":
        logger.info("judge_extraction_contradiction status=%s → symbolic-only", getattr(job, "status", None))
        return candidates
    verdicts = parse_judge_verdicts(extract_judge_text(job.result))
    apply_verdicts(candidates, verdicts)
    return candidates


async def check_extraction_canon(
    chapter_text: str, snapshot: dict[str, Any] | None, *,
    llm=None, user_id: str = "", model_source: str = "", model_ref: str = "",
    source_language: str = "auto",
) -> list[ExtractionCanonCandidate]:
    """Full check: SCORE-style symbolic pre-filter → (if any candidates AND an
    LLM client is configured) judge confirmation. Returns ALL candidates with
    `confirmed` set (True/False by the judge, or None when no judge ran or it
    degraded). The caller treats `confirmed is True` as the reviewable signal —
    this function NEVER blocks extraction; it only annotates."""
    candidates = gone_entities_asserted_active(chapter_text, snapshot)
    if not candidates or llm is None or not model_ref:
        return candidates
    return await judge_extraction_contradiction(
        llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
        chapter_text=chapter_text, candidates=candidates, source_language=source_language,
    )
