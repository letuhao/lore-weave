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

import asyncio
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


@dataclass
class EditProposal:
    """One PROPOSED span edit — the unit of the human review-gate (M6). `recommended` drives the
    UI pre-check (the human still sees + can toggle ALL of them — the re-ranker RANKS, never
    vetoes): deterministic edits are always recommended; semantic edits are recommended when the
    optional comparative re-ranker approves (`rerank_reason` explains why). Splice via
    `apply_self_heal_edits`."""
    id: str          # stable within a proposal set ("e0","e1",… by ascending offset)
    type: str
    tier: str        # "deterministic" | "semantic"
    start: int
    end: int
    before: str
    after: str
    issue: str = ""
    fix: str = ""
    recommended: bool = False   # pre-checked in the UI (deterministic always; semantic per re-ranker)
    rerank_reason: str = ""     # the re-ranker's one-line rationale (advisory)


# ── JUDGE (detector) ───────────────────────────────────────────────────

# Appended to the judge system prompt when a STORY BIBLE (canon + naming/honorific
# convention) is supplied. Adds two axes the bare judge can't see — convention violations
# and canon contradictions — plus the two false-positive guards the POC proved necessary
# (no out-of-text inference; already-explained ⇒ not a defect). See
# docs/specs/2026-06-30-chapter-synthesis-self-healing.md (cheap-stack POC).
_JUDGE_CANON_ADDENDUM = (
    "\n\nYou are ALSO given a STORY BIBLE — the canon (each character's established "
    "traits/role) and a naming/honorific CONVENTION. In ADDITION to the defects above, "
    "flag: (a) any ADDRESS or HONORIFIC that violates the convention, and (b) any action "
    "or description that CONTRADICTS a character's canon. Two HARD rules to avoid false "
    "positives: (1) do NOT infer events outside the chapter text; (2) if the chapter "
    "ALREADY explains something, it is NOT a defect. Ground every finding in this bible "
    "and copy each span VERBATIM.\n\nSTORY BIBLE:\n"
)


def build_judge_messages(
    chapter: str, source_language: str = "auto", canon: str | None = None,
) -> tuple[str, str]:
    """(system, user) for the whole-chapter judge. Language-neutral instruction; the
    span MUST be copied verbatim from the chapter (any language) so code can locate it,
    and issue/fix are written in the chapter's own language. When `canon` (a story bible)
    is given, the judge is GROUNDED — it gains the convention/canon axes and the
    out-of-text/already-explained guards."""
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
    if canon and canon.strip():
        system = system + _JUDGE_CANON_ADDENDUM + canon.strip()
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
    temperature: float = 0.3,
) -> str | None:
    """One blocking completion → raw content, or None on error/non-completion/empty."""
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": temperature,
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
    llm: LLMClient, chapter: str, *, source_language: str, max_tokens: int,
    canon: str | None = None, temperature: float = 0.3, **kw,
) -> list[Finding] | None:
    """Findings, or None when the judge call itself DEGRADED (so the caller can tell a
    genuine 'zero defects' apart from a failed/empty re-judge — the latter must NOT read
    as 'all clean')."""
    system, user = build_judge_messages(chapter, source_language, canon)
    content = await _chat(llm, system=system, user=user, max_tokens=max_tokens,
                          purpose="self_heal_judge", temperature=temperature, **kw)
    if content is None:
        return None
    return parse_findings(content)


# ── VOTE (L4 — self-consistency) ───────────────────────────────────────

def _vote_bucket(span: str, chapter: str) -> int | None:
    """Coarse span key for cross-run aggregation: the located start offset // 40 (so the
    judge's quote drift across runs still collapses to one bucket). None ⇒ unlocatable,
    which is ALSO the must-quote (L2) drop — an un-anchorable finding never votes."""
    loc = locate_span(span, chapter)
    return None if loc is None else loc[0] // 40


async def _judge_vote(
    llm: LLMClient, chapter: str, *, source_language: str, max_tokens: int,
    canon: str | None, k: int, min_votes: int, temperature: float, **kw,
) -> list[Finding] | None:
    """Run the (grounded) judge `k` times and keep only findings whose span bucket recurs
    in ≥ `min_votes` runs. The POC lesson: voting cleans RANDOM noise, but only on a
    GROUNDED judge — an ungrounded judge confabulates the SAME wrong thing every run, so
    voting can't save it. Hence vote_k>1 is meant to pair with `canon`. k≤1 ⇒ the plain
    single-shot judge (temperature 0.3) for byte-identical legacy behavior."""
    if k <= 1:
        return await _judge(llm, chapter, source_language=source_language,
                            max_tokens=max_tokens, canon=canon, temperature=0.3, **kw)
    runs = await asyncio.gather(*[
        _judge(llm, chapter, source_language=source_language, max_tokens=max_tokens,
               canon=canon, temperature=temperature, **kw)
        for _ in range(k)
    ])
    if all(r is None for r in runs):
        return None  # every run degraded — surface as degrade, not a false 'clean'
    buckets: dict[int, dict] = {}
    for ri, fl in enumerate(runs):
        if not fl:
            continue
        seen: set[int] = set()
        for f in fl:
            b = _vote_bucket(f.span, chapter)
            if b is None or b in seen:   # unlocatable (L2 drop) or already counted this run
                continue
            seen.add(b)
            slot = buckets.setdefault(b, {"votes": set(), "rep": f})
            slot["votes"].add(ri)
    return [s["rep"] for s in buckets.values() if len(s["votes"]) >= min_votes]


# ── VERIFY (L5 — asymmetric skeptical refute) ──────────────────────────

_VERIFY_SYSTEM = (
    "You are a SKEPTICAL reviewer; default to REFUTED. Given a CHAPTER, a FINDING and its "
    "QUOTE, decide whether the finding is a REAL defect in the chapter, judged against the "
    "STORY BIBLE below when provided. REFUTE if: the quote is not present in the chapter; or "
    "the supposed defect is actually explained elsewhere in the chapter; or the finding "
    "infers events beyond the text. CONFIRM only when you can point to the exact wrong words. "
    'Reply ONLY JSON: {"verdict":"CONFIRMED"|"REFUTED","reason":"..."}.'
)


async def _verify(
    llm: LLMClient, chapter: str, finding: Finding, *, canon: str | None,
    max_tokens: int = 320, **kw,
) -> bool:
    """True ⇒ keep the finding (confirmed or verify degraded), False ⇒ drop (refuted).
    Fail-OPEN: a degraded/unparseable verify keeps the finding — the satellite edit is
    canon-grounded and localized, and a human/stronger-model gate follows; dropping a real
    fix on a transient verify failure is the worse error here."""
    system = _VERIFY_SYSTEM + ("\n\nSTORY BIBLE:\n" + canon.strip() if canon and canon.strip() else "")
    user = f"CHAPTER:\n\n{chapter}\n\nFINDING: {finding.issue}\nQUOTE: \"{finding.span}\""
    content = await _chat(llm, system=system, user=user, max_tokens=max_tokens,
                          purpose="self_heal_verify", temperature=0.2, **kw)
    if content is None:
        return True  # degrade ⇒ fail-open
    m = re.search(r'"verdict"\s*:\s*"?\s*(CONFIRMED|REFUTED)', content, re.IGNORECASE)
    if m:
        return m.group(1).upper() == "CONFIRMED"
    # no JSON verdict — fall back to a keyword read, still fail-open if ambiguous
    up = content.upper()
    return not ("REFUT" in up and "CONFIRM" not in up)


async def _verify_vote(
    llm: LLMClient, chapter: str, finding: Finding, *, canon: str | None, k: int, **kw,
) -> bool:
    """Vote the verify to RAISE recall — single-shot verify is stochastic + fail-toward-refute
    (it dropped the real CH01 'mẫu thân ngươi'). Because each `_verify` already DEFAULTS to
    REFUTED (skeptical, for precision against confabs), a majority vote would only compound the
    refute-lean. So the vote DROPS only on a UNANIMOUS refute — one confirming vote (overcoming
    the skeptical default) is enough to keep a finding; a true confab the model refutes every
    time still gets 0 confirms → dropped. k≤1 ⇒ single-shot."""
    if k <= 1:
        return await _verify(llm, chapter, finding, canon=canon, **kw)
    votes = await asyncio.gather(*[_verify(llm, chapter, finding, canon=canon, **kw) for _ in range(k)])
    return any(votes)   # keep unless EVERY vote refutes (recall-biased; the human gate culls the rest)


# ── code mechanical edits (L1 — deterministic, no LLM) ─────────────────

_DUP_WORD = re.compile(r"\b([^\W\d_]+)(\s+)\1\b", re.IGNORECASE | re.UNICODE)


# Languages where a doubled word is overwhelmingly a VALID reduplication (từ láy:
# 'chằm chằm', 'rắc rắc', 'xa xa'), NOT a typo — deterministic collapse would corrupt prose.
# In these, dup-word collapsing is OFF; a genuine slip is left to the LLM judge instead.
_REDUP_LANGS = frozenset({"vi", "zh", "ja", "ko", "th", "id", "ms"})


def code_mechanical_edits(chapter: str, source_language: str = "auto") -> list[tuple[int, int, str]]:
    """Deterministic mechanical fixes that need no LLM judgement — the consecutive
    duplicate-word slip ('ran ran' → 'ran'). Returns (start, end, replacement) spans,
    spliced alongside the satellite edits. SKIPPED for reduplication-heavy languages
    (`_REDUP_LANGS`), where a doubled word is almost always intentional."""
    if source_language in _REDUP_LANGS:
        return []
    return [(m.start(), m.end(), m.group(1)) for m in _DUP_WORD.finditer(chapter)]


# A judge span is a fragment quoted mid-clause; editing it in isolation leaves an orphaned
# tail at the splice ('…dốc lòng. che chở' artifact). Snap the span OUT to the enclosing
# sentence so the satellite editor always rewrites a coherent unit.
_SENT_BOUND = frozenset(".!?…\n")


def _snap_to_sentence(text: str, s: int, e: int) -> tuple[int, int]:
    i = s
    while i > 0 and text[i - 1] not in _SENT_BOUND:
        i -= 1
    while i < s and text[i] in " \t\"“”'":     # skip leading whitespace / opening quotes
        i += 1
    j = max(e, s + 1)
    while j < len(text) and text[j - 1] not in _SENT_BOUND:
        j += 1
    return i, j


# Modern third-person pronouns used as the NARRATOR's voice — a closed lexical class that
# is ~always wrong in xianxia. Detected deterministically (full recall the voting judge
# misses); the canon-grounded satellite editor still picks the right replacement in context.
_MODERN_PRONOUN = re.compile(
    r"(?<![^\W\d_])(ông ta|bà ta|cô ấy|anh ấy|ông|bà)(?![^\W\d_])", re.IGNORECASE | re.UNICODE)


def code_pronoun_findings(chapter: str) -> list[Finding]:
    """One pre-located Finding per modern-pronoun-as-narrator slip. Detection is mechanical
    (closed class); the replacement stays contextual — the editor sees the whole (snapped)
    sentence + the canon and chooses hắn/y/lão (male) or nàng/thị (female)."""
    out: list[Finding] = []
    for m in _MODERN_PRONOUN.finditer(chapter):
        w = m.group(0)
        out.append(Finding(
            type="xưng hô (code)", span=w,
            issue=f"Đại từ hiện đại '{w}' dùng làm ngôi kể — trái quy ước tiên hiệp.",
            fix=(f"Thay '{w}' bằng đại từ tiên hiệp phù hợp (nam: hắn/y/lão; nữ: nàng/thị) "
                 "theo canon; giữ nguyên phần còn lại của câu."),
            located=(m.start(), m.end())))
    return out


async def _compute_edits(
    llm: LLMClient, chapter: str, *, source_language: str, profile: BookProfile,
    max_edit_expansion: float, judge_max_tokens: int, edit_max_tokens: int,
    canon: str | None, vote_k: int, min_votes: int, verify: bool, verify_k: int,
    prefilter: bool, vote_temperature: float, **kw,
) -> tuple[list[EditProposal], SelfHealReport]:
    """The shared cheap-stack pipeline up to (but NOT including) the splice: judge-vote →
    verify-vote → locate+snap → overlap-dedup → satellite-edit → merge mechanical edits.
    Returns the computed `EditProposal`s (offset-ascending, stable ids) + the report.
    `run_self_heal` splices all of them; `propose_self_heal` hands them to the review-gate."""
    findings = await _judge_vote(
        llm, chapter, source_language=source_language, max_tokens=judge_max_tokens,
        canon=canon, k=vote_k, min_votes=min_votes, temperature=vote_temperature, **kw) or []
    report = SelfHealReport(findings=findings, rejudge_before=len(findings))

    # L5 — skeptical verify drops refuted findings (kept in report w/ skip_reason). When
    # verify_k>1 the verify is itself VOTED (majority-refute) to stop a stochastic single
    # refute from dropping a real finding (the CH01 'mẫu thân ngươi' false-refute).
    if verify and findings:
        survivors: list[Finding] = []
        for f in findings:
            if await _verify_vote(llm, chapter, f, canon=canon, k=verify_k, **kw):
                survivors.append(f)
            else:
                f.skip_reason = "refuted"
        findings = survivors

    # L1 — deterministic edits (no LLM): dup-word splice + full-recall pronoun findings.
    mech = code_mechanical_edits(chapter, source_language) if prefilter else []
    if prefilter and source_language == "vi":
        pron = code_pronoun_findings(chapter)
        findings = findings + pron
        report.findings.extend(pron)

    if not findings and not mech:
        return [], report

    # locate every finding's span (code findings arrive pre-located), then SNAP each to its
    # enclosing sentence so the satellite editor rewrites a coherent unit (no orphaned tail).
    located: list[Finding] = []
    for f in findings:
        loc = f.located or locate_span(f.span, chapter)
        if loc is None:
            f.skip_reason = "not_located"
            continue
        f.located = _snap_to_sentence(chapter, loc[0], loc[1])
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
    proposals: list[EditProposal] = []
    occupied: list[tuple[int, int]] = []
    for f in chosen:
        s, e = f.located  # type: ignore[misc]
        original = chapter[s:e]
        guide = (f"Vấn đề: {f.issue} Cách sửa: {f.fix} "
                 "Chỉ sửa đúng đoạn được chọn; giữ độ dài tương đương; không thêm tình tiết mới."
                 if source_language == "vi" else
                 f"Issue: {f.issue} Fix: {f.fix} "
                 "Edit only the selected passage; keep a similar length; add no new events.")
        messages = build_selection_messages(original, profile, "rewrite", guide=guide,
                                            grounding=canon or "")
        new = await _chat(llm, system=messages[0]["content"], user=messages[1]["content"],
                          max_tokens=edit_max_tokens, purpose="self_heal_edit", **kw)
        if not new:
            f.skip_reason = "edit_failed"
            continue
        new = new.strip()
        if len(new) > max(40, len(original)) * max_edit_expansion:
            f.skip_reason = "edit_expanded"   # the satellite guard — a span edit must stay local
            continue
        f.edited = True
        report.edits_applied += 1
        occupied.append((s, e))
        tier = "deterministic" if "(code)" in f.type else "semantic"
        proposals.append(EditProposal(id="", type=f.type, tier=tier, start=s, end=e,
                                      before=original, after=new, issue=f.issue, fix=f.fix))

    # merge the deterministic mechanical edits — satellite edits keep priority (a semantic
    # rewrite of a clause already subsumes any dup-word inside it), so a mechanical edit is
    # applied only where it does NOT overlap a satellite edit.
    for s, e, new in mech:
        if any(s < oe and os < e for os, oe in occupied):
            continue
        occupied.append((s, e))
        report.edits_applied += 1
        proposals.append(EditProposal(id="", type="dup-word", tier="deterministic", start=s,
                                      end=e, before=chapter[s:e], after=new,
                                      issue="Từ bị lặp liên tiếp.", fix="Xóa từ bị lặp."))

    proposals.sort(key=lambda p: p.start)
    for i, p in enumerate(proposals):
        p.id = f"e{i}"
    return proposals, report


def apply_self_heal_edits(
    chapter: str, proposals: list[EditProposal], accepted_ids: list[str] | None = None,
) -> str:
    """Splice the accepted proposals into the chapter (default: ALL), rightmost-first so
    earlier offsets stay valid. The review-gate's apply step — no LLM, no re-judge."""
    keep = proposals if accepted_ids is None else [p for p in proposals if p.id in set(accepted_ids)]
    healed = chapter
    for p in sorted(keep, key=lambda p: p.start, reverse=True):
        healed = healed[:p.start] + p.after + healed[p.end:]
    return healed


# ── DIRECT high-recall propose (the human-gated path) ──────────────────
#
# Diagnosis (PO, 2026-07-01): the conservative judge→vote→verify→satellite chain OVER-FILTERED
# — `verify` defaults to REFUTED and dropped real edits (e.g. 'mẫu thân ngươi' refuted 3/3),
# so v2≈v3 barely changed. A bare prompt on the SAME model finds 7 splice-ready edits where the
# pipeline kept ~4. For a HUMAN-gated flow the filter is the human, not verify — so propose uses
# a single high-recall judge that emits the replacement directly, no vote/verify pre-filter.
_DIRECT_JUDGE_SYSTEM = (
    "You are a demanding fiction editor. Find EVERY concrete anomaly in the CHAPTER: logic / "
    "cause-effect holes, abrupt scene cuts, awkward or unclear phrasing, repeated information, "
    "ADDRESS/HONORIFIC errors (modern pronouns, third-person self-reference, wrong name/role), "
    "character contradictions vs the story bible, and typos. For EACH anomaly return a JSON object: "
    '{"type": the defect kind, '
    '"original": a SHORT 4-20 word excerpt COPIED CHARACTER-FOR-CHARACTER from the chapter so it can '
    'be found and replaced, '
    '"replacement": the corrected span at a SIMILAR length — do NOT rewrite the whole passage, and it '
    "MUST DIFFER from the original (NEVER echo the original text back as the replacement; if a span needs "
    'no change, do not report it), '
    '"explanation": a short reason}. '
    "List ALL anomalies you find — do NOT pre-filter or self-censor; a human reviews each before it "
    'applies. Write "replacement" and "explanation" in the chapter\'s language. Return ONLY a JSON '
    "array: [{\"type\":...,\"original\":...,\"replacement\":...,\"explanation\":...}]. No prose around it."
)


def build_direct_judge_messages(
    chapter: str, source_language: str = "auto", canon: str | None = None,
) -> tuple[str, str]:
    """(system, user) for the one-pass DIRECT judge — it proposes the replacement inline. The
    `canon` is CONTEXT (flag anything inconsistent with it), NOT a suppression filter — the old
    'do not infer / already-explained' guardrails were what muted recall."""
    system = _DIRECT_JUDGE_SYSTEM
    if canon and canon.strip():
        system = system + "\n\nSTORY BIBLE (context — flag anything inconsistent with it):\n" + canon.strip()
    return system, "CHAPTER:\n\n" + chapter


def parse_direct_findings(content: str) -> list[dict[str, str]]:
    """Tolerant parse of the direct judge's array → [{type, original, replacement, explanation}].
    Drops a row with no usable `original`/`replacement`. Salvages a truncated array. Never raises."""
    if not content:
        return []
    arr: list = []
    m = re.search(r"\[.*\]", content, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, list):
                arr = parsed
        except (json.JSONDecodeError, ValueError):
            arr = []
    if not arr:  # salvage a token-capped array — parse each complete {...}
        for obj in re.findall(r"\{[^{}]*\}", content, re.DOTALL):
            try:
                row = json.loads(obj)
                if isinstance(row, dict):
                    arr.append(row)
            except (json.JSONDecodeError, ValueError):
                continue
    out: list[dict[str, str]] = []
    for row in arr:
        if not isinstance(row, dict):
            continue
        orig, repl = row.get("original"), row.get("replacement")
        if not isinstance(orig, str) or not orig.strip() or not isinstance(repl, str):
            continue
        out.append({"type": str(row.get("type", "")).strip(), "original": orig.strip(),
                    "replacement": repl.strip(), "explanation": str(row.get("explanation", "")).strip()})
    return out


# The TYPE-ROUTED RE-RANKER (optional precision layer) — it RANKS, it does NOT veto. The POC
# (poc/typerouted_compare.py) showed a general "is it better?" judge is a rubber stamp on fiction
# (94% APPLY — it would auto-DELETE passages), because prose quality isn't one "correctness" axis.
# So this classifies each edit: RULE (an objective convention/canon/typo fix — safe to auto-tick) vs
# CRAFT (a subjective prose choice — the AUTHOR decides) vs BAD. Only RULE pre-checks; CRAFT/BAD are
# still SHOWN (recall preserved) but left for the human. Aligns the machine's confidence with what a
# cheap model can actually judge in fiction.
_RERANK_SYSTEM = (
    "You decide whether a proposed fiction edit is safe to AUTO-APPLY or must be left for the human "
    "author, using the STORY BIBLE (convention + canon) as ground truth. Classify into EXACTLY one: "
    "RULE — the ORIGINAL clearly breaks a SPECIFIC OBJECTIVE rule (a modern pronoun; a third-person "
    "self-reference; a fact contradicting the bible; a wrong name/role; a typo or duplicated word; a "
    "grammar error) AND the replacement fixes it → safe to auto-apply. "
    "CRAFT — a SUBJECTIVE prose choice (rephrasing, trimming, DELETING a passage, pacing, tone, word "
    "choice) with NO objective rule broken → the AUTHOR must decide; do NOT auto-apply. "
    "BAD — the replacement is wrong, worse, or a no-op. "
    'Reply ONLY JSON {"reasoning":"<=20 words","verdict":"RULE"|"CRAFT"|"BAD"}.'
)


async def _rerank_edit(
    llm: LLMClient, proposal: EditProposal, *, canon: str | None, **kw,
) -> tuple[bool, str]:
    """(recommended, reason) for ONE proposal — type-routed. `recommended` = the edit is a RULE fix
    (objectively safe to auto-tick); CRAFT/BAD ⇒ not pre-checked (still shown; the author decides).
    Fail-toward-NOT-recommended on degrade/ambiguous — this only affects the pre-check, never hides a
    proposal, so uncertainty should default to 'let the human tick it', not auto-tick."""
    system = _RERANK_SYSTEM + (("\n\nSTORY BIBLE:\n" + canon.strip()) if canon and canon.strip() else "")
    user = f"ORIGINAL: «{proposal.before}»\nPROPOSED: «{proposal.after}»\nISSUE: {proposal.issue}"
    content = await _chat(llm, system=system, user=user, max_tokens=400,
                          purpose="self_heal_rerank", temperature=0.3, **kw)
    if content is None:
        return False, ""   # degrade → not pre-checked (human decides; nothing hidden)
    reason = ""
    rm = re.search(r'"reasoning"\s*:\s*"([^"]{0,200})', content)
    if rm:
        reason = rm.group(1)
    m = re.search(r'"verdict"\s*:\s*"?\s*(RULE|CRAFT|BAD)', content, re.IGNORECASE)
    if m:
        return m.group(1).upper() == "RULE", reason
    up = content.upper()   # no JSON verdict → only pre-check on an unambiguous RULE
    return "RULE" in up and "CRAFT" not in up and "BAD" not in up, reason


# The objective CONVENTION classes the auditor labels in an edit's `type` — xưng-hô/address
# (a modern pronoun, wrong honorific, third-person self-reference) + typos. These are closed,
# objective RULE fixes, so we pre-check them DETERMINISTICALLY + FREE (D-QUALITY-HONORIFIC-PRECHECK):
# the eval showed the LLM re-ranker only classifies ~half the honorific fixes as RULE (8/15) at the
# cost of an extra call each, whereas the auditor's own type label catches all 15 reliably. Matches
# the category label (language-agnostic — the auditor categorizes the edit), NOT prose content.
_CONVENTION_FIX_MARKERS = ("address", "honorif", "xưng", "pronoun", "ngôi kể", "typo")


def _is_convention_fix(edit_type: str) -> bool:
    """True for an objective xưng-hô/address/typo fix — pre-checked for free, no re-ranker."""
    t = (edit_type or "").lower()
    return any(m in t for m in _CONVENTION_FIX_MARKERS)


async def propose_edits_direct(
    llm: LLMClient, chapter: str, *, user_id: str, model_source: str, model_ref: str,
    canon: str | None = None, source_language: str = "auto", prefilter: bool = True,
    rerank: bool = False, max_tokens: int = 3000, temperature: float = 0.4,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[list[EditProposal], SelfHealReport]:
    """One-pass HIGH-RECALL propose: the direct judge finds anomalies + proposes each replacement;
    code locates each `original` (must-quote, fuzzy) and merges the deterministic dup-word fix.
    No vote/verify (the human gate filters). When `rerank`, a comparative re-ranker sets each
    semantic edit's `recommended` (pre-check) — it never drops. Returns offset-ascending
    `EditProposal`s + a report."""
    kw = dict(user_id=user_id, model_source=model_source, model_ref=model_ref,
              trace_id=trace_id, cancel_check=cancel_check)
    system, user = build_direct_judge_messages(chapter, source_language, canon)
    content = await _chat(llm, system=system, user=user, max_tokens=max_tokens,
                          purpose="self_heal_direct", temperature=temperature, **kw)
    raw = parse_direct_findings(content or "")
    report = SelfHealReport(rejudge_before=len(raw))

    cands: list[tuple[int, int, str, str, str, str]] = []  # start, end, after, type, issue, tier
    for r in raw:
        f = Finding(type=r["type"], span=r["original"], issue=r["explanation"], fix=r["replacement"])
        report.findings.append(f)
        loc = locate_span(r["original"], chapter)
        if loc is None:
            f.skip_reason = "not_located"   # must-quote: can't splice an unanchorable edit
            continue
        if r["replacement"].strip() == chapter[loc[0]:loc[1]].strip():
            f.skip_reason = "noop"   # the "fix" equals the text — the auditor emits ~25% of these;
            continue                 # drop them in CODE (free) so the human/re-ranker never sees a no-op
        f.located = loc
        report.located += 1
        cands.append((loc[0], loc[1], r["replacement"], r["type"] or "edit", r["explanation"], "semantic"))
    if prefilter:   # dup-word is deterministic + carries its own replacement; pronouns the judge already proposes
        for s, e, new in code_mechanical_edits(chapter, source_language):
            cands.append((s, e, new, "dup-word", "Từ bị lặp liên tiếp.", "deterministic"))

    # overlap-dedup (left-to-right; a later span overlapping an accepted one is skipped)
    cands.sort(key=lambda c: c[0])
    proposals: list[EditProposal] = []
    last_end = -1
    for s, e, after, typ, issue, tier in cands:
        if s < last_end:
            continue
        proposals.append(EditProposal(id="", type=typ, tier=tier, start=s, end=e,
                                      before=chapter[s:e], after=after, issue=issue, fix=after))
        last_end = e
    report.edits_applied = len(proposals)
    for i, p in enumerate(proposals):
        p.id = f"e{i}"

    # pre-check defaults: deterministic always recommended; semantic recommended only if the
    # comparative re-ranker approves (when enabled). The re-ranker RANKS — every proposal is
    # still returned + shown; `recommended` only drives the UI's initial checkbox.
    kw = dict(user_id=user_id, model_source=model_source, model_ref=model_ref,
              trace_id=trace_id, cancel_check=cancel_check)
    for p in proposals:
        if p.tier == "deterministic":
            p.recommended = True
        elif _is_convention_fix(p.type):
            # objective xưng-hô/address/typo fix (a closed convention class) — pre-check it
            # deterministically + FREE, instead of paying an LLM re-ranker call that catches only
            # ~half the honorific class (eval: 8/15). D-QUALITY-HONORIFIC-PRECHECK.
            p.recommended = True
            p.rerank_reason = "objective xưng-hô/address/typo convention fix (code-detected)"
        elif rerank:
            p.recommended, p.rerank_reason = await _rerank_edit(llm, p, canon=canon, **kw)
        else:
            p.recommended = False
    return proposals, report


async def propose_self_heal(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    chapter: str, source_language: str = "auto", canon: str | None = None,
    prefilter: bool = True, rerank: bool = False, max_tokens: int = 3000,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
    **_legacy: object,   # absorbs the old vote_k/verify/verify_k/etc. knobs (no longer used here)
) -> tuple[list[EditProposal], SelfHealReport]:
    """The M6 review-gate path — return per-edit PROPOSALS WITHOUT splicing for the human to
    accept/reject. Uses the HIGH-RECALL direct judge (find + propose in one pass); the human is
    the filter, so there is NO verify/vote pre-filter that would mute real edits (the diagnosis
    that v2≈v3). When `rerank`, a comparative re-ranker sets each semantic edit's `recommended`
    pre-check (it never drops). `apply_self_heal_edits` splices the accepted subset."""
    return await propose_edits_direct(
        llm, chapter, user_id=user_id, model_source=model_source, model_ref=model_ref,
        canon=canon, source_language=source_language, prefilter=prefilter, rerank=rerank,
        max_tokens=max_tokens, trace_id=trace_id, cancel_check=cancel_check)


async def run_self_heal(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    chapter: str, source_language: str = "auto", profile: BookProfile | None = None,
    max_edit_expansion: float = 1.6, judge_max_tokens: int = 2200,
    edit_max_tokens: int = 1200, rejudge: bool = True,
    canon: str | None = None, vote_k: int = 1, min_votes: int = 2,
    verify: bool = False, verify_k: int = 1, prefilter: bool = False, vote_temperature: float = 0.7,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[str, SelfHealReport]:
    """Judge the chapter, satellite-edit each locatable finding's span, splice ALL edits,
    and (optionally) re-judge. Returns ``(healed_chapter, report)`` — the autonomous path
    (applies every proposal). For a human review-gate, use `propose_self_heal` +
    `apply_self_heal_edits` instead. Degrade-safe: a judge failure returns the chapter
    unchanged with an empty report; every per-finding failure is skipped.

    The cheap-quality stack (all default-OFF ⇒ legacy single-shot behavior) layers, in
    the order proven by the POC (docs/specs/2026-06-30-chapter-synthesis-self-healing.md):
      • `canon`       — ground the judge AND the satellite editor in a story bible so it
                        catches convention/canon errors and stops confabulating;
      • `vote_k`/`min_votes` — run the grounded judge K× and keep only findings recurring
                        in ≥min_votes runs (cleans random noise; pair with `canon`);
      • `verify`/`verify_k` — a skeptical refute-or-confirm pass drops survivors that are
                        explained-in-text or out-of-text inference (fail-open on degrade);
                        verify_k>1 VOTES the verify (majority-refute) so a stochastic single
                        refute can't drop a real finding;
      • `prefilter`   — deterministic mechanical edits (dup-word) with no LLM.
    Recall/precision measured on CH1: 5/5 real defects caught, 0 confabulations, on a $0
    local model that previously returned 0 findings ungrounded."""
    profile = profile or BookProfile(source_language=source_language)
    kw = dict(user_id=user_id, model_source=model_source, model_ref=model_ref,
              trace_id=trace_id, cancel_check=cancel_check)

    proposals, report = await _compute_edits(
        llm, chapter, source_language=source_language, profile=profile,
        max_edit_expansion=max_edit_expansion, judge_max_tokens=judge_max_tokens,
        edit_max_tokens=edit_max_tokens, canon=canon, vote_k=vote_k, min_votes=min_votes,
        verify=verify, verify_k=verify_k, prefilter=prefilter, vote_temperature=vote_temperature, **kw)
    if not proposals:
        return chapter, report

    healed = apply_self_heal_edits(chapter, proposals)   # autonomous: apply every proposal

    if rejudge and report.edits_applied:
        after = await _judge(llm, healed, source_language=source_language,
                             max_tokens=judge_max_tokens, canon=canon, **kw)
        # None ⇒ the re-judge DEGRADED — leave rejudge_after None (don't report a false 0).
        report.rejudge_after = len(after) if after is not None else None

    return healed, report
