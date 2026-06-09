"""A2-S3 — SCORE-style symbolic canon guard (deterministic fast-path).

The cheap, near-free PRIMARY canon gate (spec §5.1 / §9 D2): over the
knowledge `fact-for-check` snapshot (status@P + entities), flag any cast member
that is `gone` at the scene's reading position but **present in the draft text**.

This is a *candidate* contradiction — a gone character named in the prose. The
A2-S3b LLM-judge confirms whether it is an actual contradiction (the entity is
ACTING/present) vs legitimate (flashback, memory, corpse, mourning). Keeping the
symbolic guard over-inclusive is intentional: it is the fast pre-filter, the
judge is the precise (and costly) confirmer.

Pure functions — no LLM, no I/O. The caller (A2-S3b engine wiring) fetches the
snapshot via `knowledge_client.fact_for_check` and feeds it here.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

__all__ = [
    "EVENT_ORDER_CHAPTER_STRIDE",
    "scene_at_order",
    "CanonViolation",
    "gone_cast_in_draft",
    "judge_canon",
    "check_canon",
    "ReflectResult",
    "reflect_revise",
]

# Reading-axis stride — the cross-service contract with knowledge-service's
# event_order (= chapter sort_order × stride; CM4). Composition owns this as a
# CONTRACT constant (not an import of a knowledge internal), per the §CM4 note
# "stride = composition cutoff contract".
EVENT_ORDER_CHAPTER_STRIDE = 1_000_000

_SPAN_PAD = 40  # chars of context either side of a match


def scene_at_order(scene_sort_order: int | None) -> int | None:
    """The reading-axis position to check a scene against: the start of its
    chapter on the event_order scale. A death in a STRICTLY-earlier chapter
    (`from_order < sort_order × stride`) makes the entity `gone` for this scene;
    a death within this chapter does not (the character is alive until it
    happens). `None` when the scene's chapter has no resolved sort_order — the
    caller then skips the symbolic guard (advisory only)."""
    if scene_sort_order is None:
        return None
    return scene_sort_order * EVENT_ORDER_CHAPTER_STRIDE


class CanonViolation(BaseModel):
    kind: str = "gone_entity_present"
    source: str = "score_symbolic"   # vs "llm_judge" (A2-S3b)
    entity_id: str
    glossary_entity_id: str | None = None
    name: str | None = None
    status: str = "gone"
    span: str = ""                   # excerpt of the draft around the match
    matched: str = ""                # the name form that matched
    confirmed: bool | None = None    # set by the A2-S3b judge; None = symbolic-only
    why: str = ""                    # the judge's reasoning (when confirmed)


def _find_span(draft: str, name: str) -> tuple[str, str] | None:
    """Return (matched_name, span_excerpt) if `name` occurs in `draft`. Uses
    word boundaries for ASCII names (avoid 'Al' in 'Always'); plain containment
    for CJK/non-ASCII names (no \\b word boundary in CJK script)."""
    if not name or not name.strip():
        return None
    name = name.strip()
    idx = -1
    if name.isascii():
        m = re.search(r"\b" + re.escape(name) + r"\b", draft, re.IGNORECASE)
        if m:
            idx = m.start()
    else:
        low = draft.lower()
        idx = low.find(name.lower())
    if idx < 0:
        return None
    start = max(0, idx - _SPAN_PAD)
    end = min(len(draft), idx + len(name) + _SPAN_PAD)
    excerpt = ("…" if start > 0 else "") + draft[start:end] + ("…" if end < len(draft) else "")
    return name, excerpt


def gone_cast_in_draft(
    draft: str, snapshot: dict[str, Any] | None,
) -> list[CanonViolation]:
    """Symbolic candidates: every `gone` entity in the snapshot whose name (or
    canonical_name) appears in `draft`. Empty when the snapshot is absent (the
    guard degrades to advisory — a knowledge outage never blocks). De-duped per
    entity (the first matching name form wins)."""
    if not draft or not snapshot:
        return []
    out: list[CanonViolation] = []
    seen: set[str] = set()
    for ent in snapshot.get("entities") or []:
        if not isinstance(ent, dict) or ent.get("status") != "gone":
            continue
        eid = ent.get("entity_id")
        if not eid or eid in seen:
            continue
        for name in (ent.get("name"), ent.get("canonical_name")):
            hit = _find_span(draft, name) if isinstance(name, str) else None
            if hit is None:
                continue
            matched, span = hit
            out.append(CanonViolation(
                entity_id=eid,
                glossary_entity_id=ent.get("glossary_entity_id"),
                name=ent.get("name"),
                status="gone",
                span=span,
                matched=matched,
            ))
            seen.add(eid)
            break
    return out


# ── LLM-judge: confirm acting-vs-mentioned (A2-S3b, spec §9 D2) ─────────

def _build_judge_messages(
    draft: str, candidates: list[CanonViolation], source_language: str,
) -> tuple[str, str]:
    """(system, user) for the canon judge. Abstract + multilingual-safe (no
    English-only illustrative phrases — they bias a CJK/VN judge; the lesson)."""
    lang = "" if source_language in ("", "auto") else (
        f" Write each `why` in the language with code '{source_language}'."
    )
    system = (
        "You verify story continuity. Each listed character is GONE (dead, "
        "destroyed, departed, or lost) before this passage. For each, decide "
        "whether the passage portrays them as an ACTIVE PRESENCE now — acting, "
        "speaking, perceiving, or bodily present — which is a continuity "
        "violation. A reference that is a memory, flashback, mention of their "
        "absence/death, a corpse, or others speaking ABOUT them is NOT a "
        "violation. Return ONLY a JSON object "
        '{"verdicts":[{"entity_id":str,"violated":bool,"why":str}]}.' + lang
    )
    listed = "\n".join(
        f'- entity_id={c.entity_id} name="{c.name}" (near: {c.span})'
        for c in candidates
    )
    user = f"GONE CHARACTERS REFERENCED:\n{listed}\n\nPASSAGE:\n{draft}"
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


async def judge_canon(
    judge, *, user_id: str, model_source: str, model_ref: str,
    draft: str, candidates: list[CanonViolation], source_language: str = "auto",
    max_tokens: int = 1024, trace_id: str | None = None,
) -> list[CanonViolation]:
    """Confirm the symbolic candidates with the LLM-judge (D2 — only the cheap
    SCORE pre-filter runs on everything; the judge confirms the few candidates).
    Sets `confirmed`/`why` per candidate.

    CC4 (critic-degrade lesson): any LLM/parse failure leaves `confirmed=None`
    (symbolic-only → ADVISORY, never auto-revised/hard-gated) — the judge must
    never block on its own failure. A candidate the judge omits is also left
    `confirmed=None`."""
    if not candidates:
        return []
    from loreweave_llm.errors import LLMError
    from app.clients.eval_client import extract_judge_content

    system, user = _build_judge_messages(draft, candidates, source_language)
    try:
        job = await judge.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source,
            model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.0,
                "max_tokens": max_tokens, "reasoning_effort": "none",
                "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
            },
            job_meta={"extractor": "judge_canon"}, trace_id=trace_id,
        )
    except LLMError as exc:
        logger.warning("judge_canon degraded (LLM error): %s — symbolic-only", exc)
        return candidates
    if getattr(job, "status", None) != "completed":
        logger.info("judge_canon status=%s → symbolic-only", getattr(job, "status", None))
        return candidates
    verdicts = _parse_verdicts(extract_judge_content(job.result))
    for c in candidates:
        v = verdicts.get(c.entity_id)
        if v is not None:
            c.confirmed = v["violated"]
            c.source = "llm_judge"
            c.why = v["why"]   # /review-impl #3 — surface the judge's reasoning
    return candidates


async def check_canon(
    draft: str, snapshot: dict[str, Any] | None, *,
    judge=None, user_id: str = "", model_source: str = "", model_ref: str = "",
    source_language: str = "auto", trace_id: str | None = None,
) -> list[CanonViolation]:
    """Full canon check on a draft: SCORE symbolic pre-filter → (if any
    candidates AND a distinct judge is configured) LLM-judge confirmation.
    Returns ALL candidates with `confirmed` set (True/False by the judge, or
    None when no judge ran). The caller treats `confirmed is True` as HARD."""
    candidates = gone_cast_in_draft(draft, snapshot)
    if not candidates or judge is None or not model_ref:
        return candidates
    return await judge_canon(
        judge, user_id=user_id, model_source=model_source, model_ref=model_ref,
        draft=draft, candidates=candidates, source_language=source_language,
        trace_id=trace_id,
    )


# ── reflect: check → revise ≤ N (spec §6/§8.3) ─────────────────────────

class ReflectResult(BaseModel):
    # Whether the canon guard actually ran, so a SKIP isn't a silent false-green:
    #   checked            — the guard ran over a real position + cast.
    #   skipped_no_cast    — the scene has no cast entities (nothing to check).
    #   skipped_no_position— the scene has a cast but no resolved reading position
    #                        (dirty/dangling chapter ref) → could NOT verify.
    #   degraded           — knowledge unavailable → could NOT verify.
    # `resolved=True` only means "no confirmed contradiction"; on a non-`checked`
    # status it means "nothing was verified", which the FE + publish-gate surface
    # so dirty data doesn't silently strip canon protection.
    status: str = "checked"
    text: str                                    # final draft (possibly revised)
    # Remaining violations the author should see: confirmed-HARD (confirmed=True)
    # AND ADVISORY (confirmed=None — symbolic-only, the judge was down/not-distinct
    # /silent). Judge-CLEARED candidates (confirmed=False) are excluded. The gate
    # blocks on the hard subset; advisory is flag-and-override (D4). /review-impl #1.
    violations: list[CanonViolation] = Field(default_factory=list)
    iterations: int = 0                          # revise passes actually run
    resolved: bool = True                        # no confirmed-HARD violations remain
    # D-COMP-TRUNCATION-SURFACING: the stop reason of the revise pass that produced
    # the final `text` ("length" ⇒ that repair itself hit the cap, so `text` may be
    # truncated even when the original winner draft was not). None when no revise
    # pass produced text (no repair, or the reviser gave up). The engine ORs this
    # into the job's `truncated` flag so a truncating repair isn't a silent green.
    revise_finish_reason: str | None = None


async def reflect_revise(
    *,
    draft: str,
    check_fn: Callable[[str], Awaitable[list[CanonViolation]]],
    revise_fn: Callable[[str, list[CanonViolation]], Awaitable[str | None]],
    max_iters: int = 1,
) -> ReflectResult:
    """The §8.3 `reflect(N): loop[check → revise]`. `check_fn(draft)` returns the
    violations (already judge-confirmed); a violation is HARD when
    `confirmed is True`. While there are hard violations and budget remains,
    `revise_fn(draft, hard)` produces a repaired draft; re-check. Stops when no
    hard violations remain, the reviser returns None (give up → keep last), or
    `max_iters` is exhausted (→ escalate: caller hard-gates the remainder)."""
    current = draft
    last_checked = await check_fn(current)
    iterations = 0
    while iterations < max_iters:
        hard = [v for v in last_checked if v.confirmed is True]
        if not hard:
            break
        revised = await revise_fn(current, hard)
        iterations += 1
        if not revised or revised == current:
            break  # reviser gave up or no-op → stop, keep current + its violations
        current = revised
        last_checked = await check_fn(current)
    # Surface hard + advisory (drop only judge-CLEARED); the gate's `resolved`
    # depends on the HARD subset only (/review-impl #1).
    surfaced = [v for v in last_checked if v.confirmed is not False]
    has_hard = any(v.confirmed is True for v in last_checked)
    return ReflectResult(
        text=current, violations=surfaced, iterations=iterations,
        resolved=not has_hard,
    )
