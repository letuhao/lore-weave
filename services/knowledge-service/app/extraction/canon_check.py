"""POC — Narrative Forge NDLC gate-reconciliation for Knowledge extraction.

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
writing. It flags a candidate for review; nothing here mutates Neo4j.

**POC scope note:** this is a deliberate near-duplicate of composition's
`canon_check.py` shape, not yet unified into the shared SDK. `sdks/python/` unification
is a real, tracked follow-up (`D-CANON-CHECK-SDK-UNIFY`) — appropriate ONLY once this
POC validates the mechanism catches real contradictions; premature unification would be
generalizing from a single untested use.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

__all__ = [
    "ExtractionCanonCandidate",
    "gone_entities_asserted_active",
    "judge_extraction_contradiction",
    "check_extraction_canon",
]

_SPAN_PAD = 40  # chars of context either side of a match


class ExtractionCanonCandidate(BaseModel):
    """One candidate contradiction: an entity marked `gone` in the KG (as of an
    earlier reading position) whose name appears in chapter text about to be
    extracted as new canon. Mirrors composition's `CanonViolation` shape."""

    kind: str = "gone_entity_asserted_active_in_extraction"
    source: str = "score_symbolic"   # vs "llm_judge"
    entity_id: str
    name: str | None = None
    status: str = "gone"
    gone_from_order: int | None = None
    span: str = ""                   # excerpt of the chapter text around the match
    matched: str = ""                # the name form that matched
    confirmed: bool | None = None    # set by the judge; None = symbolic-only (advisory)
    why: str = ""


def _find_span(text: str, name: str) -> tuple[str, str] | None:
    """Return (matched_name, span_excerpt) if `name` occurs in `text`. Word
    boundaries for ASCII names (avoid 'Al' matching inside 'Always'); plain
    containment for CJK/non-ASCII names (no \\b word boundary in CJK script).
    Identical logic to composition's `canon_check._find_span` — kept duplicate
    per the POC-scope note above, not yet unified."""
    if not name or not name.strip():
        return None
    name = name.strip()
    idx = -1
    if name.isascii():
        m = re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE)
        if m:
            idx = m.start()
    else:
        idx = text.lower().find(name.lower())
    if idx < 0:
        return None
    start = max(0, idx - _SPAN_PAD)
    end = min(len(text), idx + len(name) + _SPAN_PAD)
    excerpt = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    return name, excerpt


def gone_entities_asserted_active(
    chapter_text: str, snapshot: dict[str, Any] | None,
) -> list[ExtractionCanonCandidate]:
    """Symbolic pre-filter (pure, no LLM/IO): every `gone` entity in the snapshot
    whose name (or canonical_name) appears in `chapter_text`. Deliberately
    over-inclusive — candidates, not confirmed violations; the judge narrows.
    Empty when the snapshot is absent (degrades to advisory — a knowledge-graph
    outage never blocks extraction). De-duped per entity."""
    if not chapter_text or not snapshot:
        return []
    out: list[ExtractionCanonCandidate] = []
    seen: set[str] = set()
    for ent in snapshot.get("entities") or []:
        if not isinstance(ent, dict) or ent.get("status") != "gone":
            continue
        eid = ent.get("entity_id")
        if not eid or eid in seen:
            continue
        for name in (ent.get("name"), ent.get("canonical_name")):
            hit = _find_span(chapter_text, name) if isinstance(name, str) else None
            if hit is None:
                continue
            matched, span = hit
            out.append(ExtractionCanonCandidate(
                entity_id=eid,
                name=ent.get("name"),
                gone_from_order=ent.get("from_order"),
                span=span,
                matched=matched,
            ))
            seen.add(eid)
            break
    return out


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


def _parse_verdicts(content: str) -> dict[str, dict[str, Any]]:
    """{entity_id: {violated, why}} from the judge JSON; tolerant (fence strip +
    first balanced object). Empty on hard failure."""
    if not content:
        return {}
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        return {}
    try:
        obj = json.loads(text[s:e + 1])
    except (ValueError, TypeError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for v in (obj.get("verdicts") or []) if isinstance(obj, dict) else []:
        if isinstance(v, dict) and v.get("entity_id") is not None:
            out[str(v["entity_id"])] = {
                "violated": bool(v.get("violated", False)),
                "why": v.get("why") if isinstance(v.get("why"), str) else "",
            }
    return out


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

    POC live-smoke honesty note: a $0 local judge (Gemma-4 26B, this platform's
    established $0 test model) reliably clears the EASY case (flashback/memory
    → not a contradiction) but is INCONSISTENT on the HARD case (an unexplained
    cross-chapter revival → should be a contradiction) — sometimes right,
    sometimes wrong, varying with `thinking`/token-budget settings. This is an
    expected model-tier limitation (same class as this session's
    `D-AGENT-NEEDLE-CONFAB` finding), not a defect in this mechanism — the
    symbolic pre-filter and the submit/parse/degrade plumbing are proven
    correct; judge ACCURACY on nuanced cross-chapter reasoning needs either a
    stronger model or a real calibration eval before this gate is trustworthy
    in production. Tracked, not solved, by this POC."""
    if not candidates:
        return []
    system, user = _build_judge_messages(chapter_text, candidates, source_language)
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source,
            model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"},
                "temperature": 0.0, "max_tokens": 1024, "reasoning_effort": "none",
                "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
            },
            job_meta={"usage_purpose": "extraction_canon_check", "extractor": "canon_check_poc"},
        )
    except Exception as exc:  # noqa: BLE001 — degrade to symbolic-only on any LLM error
        logger.warning("judge_extraction_contradiction degraded (LLM error): %s — symbolic-only", exc)
        return candidates
    if getattr(job, "status", None) != "completed":
        logger.info("judge_extraction_contradiction status=%s → symbolic-only", getattr(job, "status", None))
        return candidates
    payload = job.result or {}
    messages = payload.get("messages") or []
    content = ""
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        content = messages[0].get("content", "") or ""
    verdicts = _parse_verdicts(content)
    for c in candidates:
        v = verdicts.get(c.entity_id)
        if v is not None:
            c.confirmed = v["violated"]
            c.source = "llm_judge"
            c.why = v["why"]
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
