"""Chapter self-heal orchestrator (Phase 2) — judge → locate → satellite-edit → splice.

Proven end-to-end in the POC (docs/specs/2026-06-30-chapter-synthesis-self-healing.md):

  1. an LLM **JUDGE** reads the WHOLE chapter and returns located findings — each a
     `{type, verbatim span, issue, fix}` (semantic defects rule-code can't find:
     logic holes, emotion-loops, flat cast, motif overuse);
  2. code **fuzzy-locates** each verbatim span back to ORIGINAL offsets (the judge
     abbreviates/re-spaces, so exact match alone is insufficient — 3/7 in the POC);
  3. a **satellite EDIT** (selection-scoped, mechanism-2 isolation via the existing
     `build_selection_messages`) fixes ONLY that span — it stays surgical because it
     never sees the rest of the chapter (POC: ×1.01 length vs the whole-chapter
     stitch's ×1.68);
  4. code **splices** the edited spans back (rightmost-first, non-overlapping);
  5. an optional **re-judge** reports the finding-count drop.

Advisory + degrade-safe throughout: a finding that won't locate, overlaps an applied
edit, or whose edit runs away in length is SKIPPED (the original prose is kept) — the
self-heal only ever *proposes* localized fixes, never rewrites the chapter wholesale.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.engine.cowrite import build_selection_messages
from app.packer.profile import BookProfile

logger = logging.getLogger(__name__)

# Disable hidden thinking on reasoning-model judges/editors (mirrors plan.py/stitch.py).
_NO_THINK = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
}


@dataclass
class Finding:
    """One judge finding + its lifecycle through the pipeline."""
    type: str
    span: str            # the VERBATIM excerpt the judge quoted (may be abbreviated / re-spaced)
    issue: str
    fix: str
    located: tuple[int, int] | None = None  # (start, end) offsets in the ORIGINAL chapter
    edited: bool = False
    skip_reason: str | None = None          # not_located | overlap | edit_failed | edit_expanded


@dataclass
class SelfHealReport:
    findings: list[Finding] = field(default_factory=list)
    located: int = 0
    edits_applied: int = 0
    rejudge_before: int = 0
    rejudge_after: int | None = None        # None when re-judge skipped (no edits / disabled)


# ── JUDGE (detector) ───────────────────────────────────────────────────

def build_judge_messages(chapter: str, source_language: str = "auto") -> tuple[str, str]:
    """(system, user) for the whole-chapter judge. Language-neutral instruction; the
    span MUST be copied verbatim from the chapter (any language) so code can locate it,
    and issue/fix are written in the chapter's own language."""
    system = (
        "You are a demanding fiction editor. Read the CHAPTER and list its most "
        "important CONCRETE defects to fix: repeated imagery/motif, repeated "
        "information already stated, logic / cause-effect holes, emotion loops "
        "(the same feeling restated each scene), one-note characters, and pacing. "
        "For EACH defect return a JSON object with: "
        '"type" (the defect kind), '
        '"span" (a VERBATIM excerpt of 6-15 words COPIED CHARACTER-FOR-CHARACTER from '
        "the chapter — do NOT paraphrase or summarize — so it can be located), "
        '"issue" (what is wrong), and "fix" (a short concrete fix). Write "issue" and '
        '"fix" in the SAME LANGUAGE as the chapter. Choose only the 6-10 clearest '
        'defects. Return ONLY a JSON array: '
        '[{"type":...,"span":...,"issue":...,"fix":...}]. No prose around it.'
    )
    return system, "CHAPTER:\n\n" + chapter


def parse_findings(content: str) -> list[Finding]:
    """Tolerant parse of the judge's JSON array. Drops a finding with no usable span
    (the load-bearing field). Never raises."""
    if not content:
        return []
    m = re.search(r"\[.*\]", content, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    out: list[Finding] = []
    for row in arr if isinstance(arr, list) else []:
        if not isinstance(row, dict):
            continue
        span = row.get("span")
        if not isinstance(span, str) or not span.strip():
            continue  # a finding we can't locate is unusable
        out.append(Finding(
            type=str(row.get("type", "")).strip(),
            span=span.strip(),
            issue=str(row.get("issue", "")).strip(),
            fix=str(row.get("fix", "")).strip(),
        ))
    return out


# ── LOCATE (code — the make-or-break fuzzy match) ──────────────────────

def _ws_regex(chunk: str) -> str:
    """A regex matching `chunk`'s word tokens with flexible whitespace between them."""
    toks = [t for t in chunk.split() if t]
    return r"\s+".join(re.escape(t) for t in toks)


def locate_span(span: str, text: str) -> tuple[int, int] | None:
    """Find the ORIGINAL-text offsets for a (possibly abbreviated / re-spaced) judge
    span. Strategy, cheapest first: exact → whitespace-flexible regex → ellipsis-anchored
    (match the part before the first '…' and after the last) → any 5-word shingle. The
    POC needed this fuzziness: only 3/7 spans matched exactly, 7/7 with fuzzy.
    Returns offsets in `text`, or None when nothing anchors (the finding is skipped)."""
    span = span.strip()
    if not span:
        return None
    if span in text:
        i = text.index(span)
        return (i, i + len(span))
    # split on ellipsis: the judge often elides the middle ("A… B… C")
    parts = [p for p in re.split(r"\s*(?:\.\.\.|…)\s*", span) if p.strip()]
    if not parts:
        return None
    try:
        m1 = re.search(_ws_regex(parts[0]), text)
    except re.error:
        return None
    if m1 is None:
        # last resort: any contiguous 5-word shingle of the span present in the text
        toks = [t for t in span.split() if t]
        for i in range(0, max(0, len(toks) - 4)):
            try:
                m = re.search(_ws_regex(" ".join(toks[i:i + 5])), text)
            except re.error:
                continue
            if m:
                return (m.start(), m.end())
        return None
    if len(parts) == 1:
        return (m1.start(), m1.end())
    # multi-part: extend to the end of the LAST part if it follows the first
    try:
        m2 = re.search(_ws_regex(parts[-1]), text[m1.end():])
    except re.error:
        m2 = None
    if m2 is not None:
        return (m1.start(), m1.end() + m2.end())
    return (m1.start(), m1.end())


# ── orchestration ──────────────────────────────────────────────────────

async def _chat(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    system: str, user: str, max_tokens: int, purpose: str,
    trace_id: str | None, cancel_check: Callable[[], Awaitable[bool]] | None,
) -> str | None:
    """One blocking completion → raw content, or None on error/non-completion/empty."""
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.3,
                "max_tokens": max_tokens, **_NO_THINK,
            },
            job_meta={"usage_purpose": purpose, "extractor": "self_heal"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("self_heal %s LLM error: %s", purpose, exc)
        return None
    if job.status != "completed":
        logger.info("self_heal %s status=%s → degraded", purpose, job.status)
        return None
    content = extract_judge_content(job.result)
    return content if content.strip() else None


async def _judge(
    llm: LLMClient, chapter: str, *, source_language: str, max_tokens: int, **kw,
) -> list[Finding] | None:
    """Findings, or None when the judge call itself DEGRADED (so the caller can tell a
    genuine 'zero defects' apart from a failed/empty re-judge — the latter must NOT read
    as 'all clean')."""
    system, user = build_judge_messages(chapter, source_language)
    content = await _chat(llm, system=system, user=user, max_tokens=max_tokens,
                          purpose="self_heal_judge", **kw)
    if content is None:
        return None
    return parse_findings(content)


async def run_self_heal(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    chapter: str, source_language: str = "auto", profile: BookProfile | None = None,
    max_edit_expansion: float = 1.6, judge_max_tokens: int = 2200,
    edit_max_tokens: int = 1200, rejudge: bool = True,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[str, SelfHealReport]:
    """Judge the chapter, satellite-edit each locatable finding's span, splice, and
    (optionally) re-judge. Returns ``(healed_chapter, report)``. Degrade-safe: a judge
    failure returns the chapter unchanged with an empty report; every per-finding
    failure is skipped (original prose kept)."""
    profile = profile or BookProfile(source_language=source_language)
    kw = dict(user_id=user_id, model_source=model_source, model_ref=model_ref,
              trace_id=trace_id, cancel_check=cancel_check)

    findings = await _judge(llm, chapter, source_language=source_language,
                            max_tokens=judge_max_tokens, **kw) or []
    report = SelfHealReport(findings=findings, rejudge_before=len(findings))
    if not findings:
        return chapter, report

    # locate every finding's span in the original text
    located: list[Finding] = []
    for f in findings:
        loc = locate_span(f.span, chapter)
        if loc is None:
            f.skip_reason = "not_located"
            continue
        f.located = loc
        report.located += 1
        located.append(f)

    # drop overlaps (left-to-right; a later span that overlaps an accepted one is skipped)
    located.sort(key=lambda f: f.located[0])  # type: ignore[index]
    chosen: list[Finding] = []
    last_end = -1
    for f in located:
        s, e = f.located  # type: ignore[misc]
        if s < last_end:
            f.skip_reason = "overlap"
            continue
        chosen.append(f)
        last_end = e

    # satellite-edit each chosen span (mechanism-2 isolation), reject runaway expansion
    edits: list[tuple[int, int, str]] = []
    for f in chosen:
        s, e = f.located  # type: ignore[misc]
        original = chapter[s:e]
        guide = (f"Vấn đề: {f.issue} Cách sửa: {f.fix} "
                 "Chỉ sửa đúng đoạn được chọn; giữ độ dài tương đương; không thêm tình tiết mới."
                 if source_language == "vi" else
                 f"Issue: {f.issue} Fix: {f.fix} "
                 "Edit only the selected passage; keep a similar length; add no new events.")
        messages = build_selection_messages(original, profile, "rewrite", guide=guide, grounding="")
        new = await _chat(llm, system=messages[0]["content"], user=messages[1]["content"],
                          max_tokens=edit_max_tokens, purpose="self_heal_edit", **kw)
        if not new:
            f.skip_reason = "edit_failed"
            continue
        new = new.strip()
        if len(new) > max(40, len(original)) * max_edit_expansion:
            f.skip_reason = "edit_expanded"   # the satellite guard — a span edit must stay local
            continue
        edits.append((s, e, new))
        f.edited = True
        report.edits_applied += 1

    # splice rightmost-first so earlier offsets stay valid
    healed = chapter
    for s, e, new in sorted(edits, key=lambda x: x[0], reverse=True):
        healed = healed[:s] + new + healed[e:]

    if rejudge and report.edits_applied:
        after = await _judge(llm, healed, source_language=source_language,
                             max_tokens=judge_max_tokens, **kw)
        # None ⇒ the re-judge DEGRADED — leave rejudge_after None (don't report a false 0).
        report.rejudge_after = len(after) if after is not None else None

    return healed, report
