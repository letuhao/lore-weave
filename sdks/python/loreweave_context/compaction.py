"""Provider-agnostic conversation compaction (RAID Wave A4).

Keeps a turn under the model's context window WITHOUT a provider-specific feature —
works for local lm_studio / Qwen / Gemma AND Claude (the Anthropic server-side
overlay is A5, layered on top). The measured provider usage stays ground truth;
this acts on the assembled `messages` before the provider call, keyed off the
script-aware estimate (loreweave_context.tokens) so it is right for the VN/CJK POC (edge #1).

Deterministic tiers (no LLM in the base):
  1. **microcompact** — evict the oldest tool-result message CONTENTS (keep the last
     ``keep_tool_results``, never evict an excluded tool e.g. web_search), replacing
     each with a short placeholder. Cheapest; tool results are the biggest/stalest
     bucket (07R §2).
  2. **full-compact (optional)** — an injected ``summarize`` callback (the LLM path).
     Its FAILURE falls through to (3) — never draft on a poisoned summary (edge #2).
  3. **hard-truncate** — if still over, drop the oldest non-pinned conversation turns,
     keeping the system/steering/anchor/pinned messages + the most recent
     ``keep_recent`` turns. Deterministic, no model call.

If even the non-evictable messages exceed the budget (edge #4) the result carries
``overflowed=True`` so the caller can surface it / trip a breaker (autonomous runs).

**What actually fires today (be honest — RAID A4 wiring):**
  * The cross-turn send path loads history as ``{role, content}`` only (tool_calls /
    tool_call_id are NOT rehydrated), so tiers 1 has nothing to evict there and the
    effective behaviour is tier 3 (truncate oldest turns) — safe, no pairs to split.
  * The **resume** path (agent→GUI 2nd pass) feeds the live ``working`` array, which
    DOES contain assistant ``tool_calls`` + ``role:tool`` results. Tier 1 fires there,
    and tier 3 must never split a call/result pair (a provider 400). That is why
    truncation operates on whole *tool-exchange atoms* (``_atoms`` / ``_recent_tail``),
    not raw message slices — dropping/keeping a whole exchange can't orphan.
  * ``stream_service`` wires a real summarizer (``_summarizer`` / ``_loop_summarizer``,
    the ``compact_service`` FACTS/SYNOPSIS extractor) into ``summarize=`` — so on
    overflow we COMPRESS the middle into a synopsis and keep the recent tail verbatim.
    If the summarizer fails OR returns a truncated result (it now RAISES on
    ``finish_reason='length'``), we fall back to deterministic hard-truncation below
    (``report.summarize_failed`` → drop oldest whole atoms) rather than store a
    partial summary.
"""
from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Union

from loreweave_context.tokens import estimate_messages_tokens

# Tool names whose results are NEVER evicted (their output is load-bearing / cited).
#
# These are WIRE names — what the model actually calls — not aspirational ones. Until Track
# D WS-D0 Wave 2 registered the universal `web_search`, the only real wire name was
# `glossary_web_search`, so this set matched NOTHING: every web-search result was silently
# evictable despite the intent stated above. Both names are listed while the glossary alias
# survives (demoted `legacy` + `superseded_by: web_search`, never deleted). A test pins the
# set against the real tool names so this can't silently rot again.
DEFAULT_EXCLUDE_TOOLS = frozenset({"web_search", "glossary_web_search"})
_PLACEHOLDER = "[tool result cleared to save context]"
_DUP_PLACEHOLDER = "[duplicate of a later identical tool result — see the most recent read]"

# Compaction fires when estimated tokens exceed trigger_ratio × effective_limit.
# Named so consumers (token_budget.until_compact_pct — the meter's "until
# auto-compact" distance) reuse THE constant instead of duplicating 0.75.
COMPACT_TRIGGER_RATIO = 0.75


def summary_message(summary: str) -> dict:
    """THE one summary-message convention (W3): a compacted-away stretch of
    conversation is represented as a pinned system message wrapping the synopsis
    in ``<summary>`` tags. Used by the in-turn summarize tier below, by the
    persisted-compact history splice (stream_service) and by the manual
    /compact route's re-compact fold — one shape everywhere."""
    return {"role": "system", "content": f"<summary>\n{summary.strip()}\n</summary>"}


# T6/D6 — the recovery hint. When compaction has summarized earlier turns THIS turn,
# a lossy summary can drop a specific detail (a number, a spelling) the current turn
# needs — the model then GUESSES or says "I don't have that" instead of using the
# `conversation_search` tool that can pull it back from the raw (still-stored) turns.
# This system hint, injected only on a turn where compaction did work, tells the model
# the raw history is recoverable and to reach for the tool rather than fabricate/omit.
# (Live A/B finding, docs/eval/context-budget/T2-compaction-trigger-2026-07-04.md: the
# net was built but unused — the gap was USAGE, which this closes.)
_RECOVERY_HINT = (
    "Note: to save context, earlier turns in this conversation were compacted into the "
    "<summary> above — some specific details (an exact name, number, or spelling) may not "
    "be in it. If you need such a detail and it is not in the summary or the recent turns, "
    "call the `conversation_search` tool with the exact term to pull it from the full "
    "conversation history. Do NOT guess and do NOT say you lack the information without "
    "searching first."
)


def recovery_hint_message() -> dict:
    """The post-compaction recovery hint (see ``_RECOVERY_HINT``) as a pinned system
    message. Injected by the caller only on a turn where compaction ``did_work``."""
    return {"role": "system", "content": _RECOVERY_HINT}


# T6/D6 breadcrumb — the fix for "a dropped fact leaves no trace, so the model can't even
# know to recover it" (user insight, 2026-07-04). BEFORE the lossy LLM summarizer runs, a
# DETERMINISTIC extractor pulls the highest-value, most-often-dropped facts from the turns
# being compacted away — VERBATIM — so they survive regardless of summarizer variance. The
# model can then answer straight from the breadcrumb (no tool call needed — the weak local
# models don't reliably call one) OR knows the exact term to conversation_search.
# Opening quote must NOT follow a letter (so a possessive apostrophe — protagonist's — is
# not mistaken for an opening quote), and the quoted term starts with a letter.
_QUOTED = re.compile(r"(?<![A-Za-z])['‘“\"]([A-Za-z][^'‘’“”\"\n]{1,38})['’”\"]")
# CJK/fullwidth quote marks (「」『』《》〈〉“”) around a term — the CJK analogue of _QUOTED,
# since CJK proper nouns carry no capitalization signal a quote is often the only marker.
_QUOTED_CJK = re.compile(r"[「『《〈]([^」』》〉\n]{1,20})[」』》〉]")
_PROPER = re.compile(r"\b[A-Z][A-Za-z’'-]+(?:\s+(?:of\s+|the\s+)?[A-Z][A-Za-z’'-]+){1,4}\b")
# Sentence split — ASCII terminators (with trailing space) OR CJK terminators 。！？
# (which are NOT followed by a space), so a Chinese passage segments instead of being one
# over-long blob that trips the length gate.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])")
# a figure = a digit OR a spelled-out number word (counts like "seven" are dropped as
# often as "7"), so both make a sentence "fact-bearing" and worth preserving verbatim.
_NUMWORD = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety|hundred|thousand|million|billion|dozen)\b",
    re.IGNORECASE,
)


# CJK numerals + fullwidth digits — a number-bearing Chinese/Japanese sentence ("三百回合",
# "一万守军", "２０人") is a fact worth preserving verbatim, but none of these are str.isdigit()
# and the English _NUMWORD misses them.
_CJK_NUM = re.compile(r"[0-9０-９一二三四五六七八九十百千万亿萬億兆两兩零]")


def _has_figure(s: str) -> bool:
    return (
        any(c.isdigit() for c in s)
        or bool(_NUMWORD.search(s))
        or bool(_CJK_NUM.search(s))
    )


# Single-word coined names (VORTHANE, Kael, Emberfall, Dawnbreaker) are the HIGHEST-value
# facts in fiction — a character, place, artifact, or spell — and the multi-word `_PROPER`
# (needs 2+ capitalized words) + quote-only `_QUOTED` miss every one of them, so a
# compaction silently drops them (measured: 7/9 novel names dropped). This extractor keeps
# them with high precision: ALL-CAPS anywhere, a capital MID-sentence (English only
# capitalizes proper nouns there, bar "I"), and a SENTENCE-INITIAL capital only when it is
# not a common opener (so "The"/"Remember"/"Reply" are filtered but "Kael"/"Sorenth" kept).
# Unicode-aware word: a run of letters (any script — Vietnamese diacritics, CJK, …) with
# internal apostrophes/hyphens ("O'Brien", "Anne-Marie"), no digits/underscore. The old
# ASCII `[A-Za-z]…` shredded Vietnamese names at the first diacritic (Nguyên→"Nguy").
_WORD = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)
# common capitalized openers / function words / breadcrumb-scaffold that are NOT proper
# nouns. Applied at EVERY position AND to ALL-CAPS words (so "KEY"/"DETAILS" from a prior
# breadcrumb don't re-extract — the self-pollution loop).
_COMMON_CAP = frozenset("""
a an the this that these those there here it its i we you he she him her they them his their our my your
and or but so if when while then as at by for from in into of on to with within without about after before
note remember also more most some any all each every none no not now new next first second third last
is are was were be been am do does did has have had will would can could should shall may might must
what who whom whose which why how where whether yes ok okay please thanks let reply say tell list
i'm i've it's we're they're you're don't can't won't
suddenly finally however meanwhile perhaps eventually later soon once well yet still thus hence therefore
moreover furthermore instead otherwise indeed anyway besides nonetheless nevertheless afterward afterwards
again already always never often sometimes usually today tomorrow yesterday maybe truly simply just really
monday tuesday wednesday thursday friday saturday sunday
january february march april may june july august september october november december
mr mrs ms dr sir madam king queen lord lady prince princess chapter part book section
key details facts names terms mentioned figures verbatim context conversation search full
""".split())


def _proper_singletons(text: str, seen: set[str]) -> list[str]:
    """Order-preserved single-word proper nouns / coined names, deduped against `seen`
    (which it mutates). Kept: ALL-CAPS anywhere (VORTHANE), or a capitalized word that is
    not a common word (`_COMMON_CAP`) and not the pronoun "I" — the stoplist applies at
    EVERY position so a capitalized "The"/"OK"/"Reply" (even mid-sentence, e.g. after a
    colon) is filtered while coined names (never in the stoplist) are kept."""
    out: list[str] = []
    for w in _WORD.findall(text):
        if len(w) < 3:
            continue
        # a word is a proper-noun candidate if it's ALL-CAPS or capitalized; either way it
        # must NOT be a common word / breadcrumb-scaffold ("KEY", "The", "Suddenly"). The
        # stoplist applies to ALL-CAPS too (self-pollution fix). CJK/uncased words have
        # isupper()==False and [0].isupper()==False → skipped (no case signal to key on).
        if not (w.isupper() or w[0].isupper()) or w == "I" or w.lower() in _COMMON_CAP:
            keep = False
        else:
            keep = True
        if keep:
            k = w.lower()
            if k not in seen:
                seen.add(k)
                out.append(w)
    return out


def extract_breadcrumb(messages: list[dict], *, max_chars: int = 900) -> str:
    """Deterministic verbatim trace of salient facts in `messages` (the turns being
    compacted away): (1) number-bearing sentences (counts, prices, dates — the facts a
    lossy summary drops most and confabulates worst), (2) quoted names, (3) multi-word
    proper-noun phrases. Deduped, order-preserved, capped. Empty string when nothing
    salient — the caller then omits the breadcrumb block entirely."""
    text = "\n".join(
        m["content"] for m in messages
        if isinstance(m.get("content"), str) and m["content"]
    )
    if not text.strip():
        return ""
    seen: set[str] = set()

    facts: list[str] = []
    for s in _SENT_SPLIT.split(text):
        s = s.strip()
        if 6 <= len(s) <= 220 and _has_figure(s):
            k = s.lower()
            if k not in seen:
                seen.add(k)
                facts.append(s)

    names: list[str] = []
    # Quoted terms (ASCII + CJP quote marks) — an explicit author signal. `_PROPER`
    # (multi-word capital runs) is deliberately NOT used: it glued sentence-opener adverbs
    # onto real names ("Suddenly Kael") and is redundant now that _proper_singletons keeps
    # each capitalized name individually (multi-word names survive as their component words).
    for pat in (_QUOTED, _QUOTED_CJK):
        for m in pat.findall(text):
            term = m.strip()
            k = term.lower()
            words = _WORD.findall(term)
            if words and all(w.lower() in _COMMON_CAP for w in words):
                continue  # all-common phrase ("Reply OK") carries no fact
            if len(term) >= 3 and k not in seen:
                seen.add(k)
                names.append(term)
                for w in words:
                    seen.add(w.lower())  # constituents seen → no re-add by singletons
    # single-word coined names (the fiction case the multi-word/quoted patterns miss),
    # now Unicode-aware so Vietnamese/accented names are kept whole (not fragmented).
    names.extend(_proper_singletons(text, seen))

    blocks: list[str] = []
    if facts:
        blocks.append("Facts with figures: " + " | ".join(facts))
    if names:
        blocks.append("Names/terms mentioned: " + "; ".join(names))
    if not blocks:
        return ""
    out = "KEY DETAILS (verbatim from compacted turns; conversation_search for full context):\n" \
        + "\n".join(blocks)
    return out[:max_chars]


def inject_recovery_hint(messages: list[dict]) -> None:
    """Insert the recovery hint (in place) right after the leading pinned/system block —
    which after compaction includes the ``<summary>`` — so it reads as guidance about that
    summary and precedes the conversation tail. Caller gates on ``report.did_work``."""
    at = next(
        (i for i, m in enumerate(messages) if not _is_pinned(m)),
        len(messages),
    )
    messages.insert(at, recovery_hint_message())


def _is_pinned(msg: dict) -> bool:
    """system / steering / anchor / developer messages are never dropped."""
    return msg.get("role") in ("system", "developer")


def _is_tool_result(msg: dict) -> bool:
    return msg.get("role") == "tool" or "tool_call_id" in msg


def _tool_name(msg: dict) -> str | None:
    return msg.get("name") or msg.get("tool")


@dataclass
class CompactionReport:
    triggered: bool = False
    tool_results_cleared: int = 0
    duplicates_collapsed: int = 0
    turns_truncated: int = 0
    summarized: bool = False
    summarize_failed: bool = False
    overflowed: bool = False
    tokens_before: int = 0
    tokens_after: int = 0
    steps: list[str] = field(default_factory=list)

    @property
    def did_work(self) -> bool:
        """True when compaction actually CHANGED the prompt (evicted tool results,
        summarized the middle, or truncated turns) — the W1 `compaction` frame is
        only emitted then; a triggered-but-no-op pass stays silent."""
        return (
            self.tool_results_cleared > 0
            or self.duplicates_collapsed > 0
            or self.summarized
            or self.turns_truncated > 0
        )

    def to_event(self) -> dict:
        return {
            "triggered": self.triggered,
            "tool_results_cleared": self.tool_results_cleared,
            "duplicates_collapsed": self.duplicates_collapsed,
            "turns_truncated": self.turns_truncated,
            "summarized": self.summarized,
            "summarize_failed": self.summarize_failed,
            "overflowed": self.overflowed,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "steps": self.steps,
        }


def _microcompact(messages: list[dict], keep: int, exclude: frozenset[str]) -> int:
    """Clear the oldest tool-result CONTENTS beyond the last `keep`, skipping excluded
    tools. Returns how many were ACTUALLY cleared (content changed). Mutates copies
    in-place (caller passes a copy).

    A message already at EITHER placeholder — `_PLACEHOLDER` (a prior microcompact) or
    `_DUP_PLACEHOLDER` (a D13a dup-read collapse) — is left untouched and NOT counted:
    it is already minimal, re-clearing it would overwrite the more-specific dup reference,
    and counting it would double-count against `duplicates_collapsed` (and falsely report
    `did_work`). So the return is the real change count, not `len(to_clear)`."""
    idxs = [
        i for i, m in enumerate(messages)
        if _is_tool_result(m) and (_tool_name(m) not in exclude)
    ]
    if len(idxs) <= keep:
        return 0
    to_clear = idxs[: len(idxs) - keep]  # oldest first
    cleared = 0
    for i in to_clear:
        m = messages[i]
        if m.get("content") not in (_PLACEHOLDER, _DUP_PLACEHOLDER):
            m["content"] = _PLACEHOLDER
            cleared += 1
    return cleared


def _collapse_duplicate_reads(messages: list[dict], exclude: frozenset[str]) -> int:
    """D13a — reversible dup-read collapse. When the SAME tool result content appears
    more than once (the model re-read an unchanged resource — Cline's dup-read case),
    replace every occurrence EXCEPT the most recent with a short reference placeholder,
    keeping the latest full copy. Returns how many were collapsed. Mutates copies
    in-place (caller passes a copy).

    Reversible: the raw turns stay in Postgres; this only shrinks the send-time view.
    Orphan-safe by construction: it only rewrites the CONTENT of a `role:tool` message,
    never removes the message, so every `tool_call_id ↔ role:tool` pairing survives (D13a).
    Excluded tools (e.g. web_search — cited/load-bearing) are never collapsed, and an
    already-cleared microcompact placeholder is skipped (no double-processing)."""
    # Index tool-result messages by their exact content; a group with >1 member is a
    # duplicate-read set. Keep the LAST (most recent) full; collapse the earlier ones.
    groups: dict[str, list[int]] = {}
    for i, m in enumerate(messages):
        if not _is_tool_result(m) or _tool_name(m) in exclude:
            continue
        content = m.get("content")
        if not isinstance(content, str) or content in (_PLACEHOLDER, _DUP_PLACEHOLDER):
            continue
        groups.setdefault(content, []).append(i)
    collapsed = 0
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        for i in idxs[:-1]:  # every occurrence except the most recent
            messages[i]["content"] = _DUP_PLACEHOLDER
            collapsed += 1
    return collapsed


def _atoms(convo: list[dict]) -> list[list[dict]]:
    """Group a non-pinned conversation into indivisible *atoms*: a tool-result
    message binds to the atom it answers (the nearest preceding message), so an
    assistant `tool_calls` turn and its `role:tool` results are never split. Any
    structural truncation keeps/drops whole atoms — that is what keeps the array
    provider-valid (an orphan tool result / tool call is a 400)."""
    atoms: list[list[dict]] = []
    for m in convo:
        if (m.get("role") == "tool" or "tool_call_id" in m) and atoms:
            atoms[-1].append(m)  # attach the result to the exchange that made the call
        else:
            atoms.append([m])
    return atoms


def _recent_tail(convo: list[dict], keep_recent: int) -> list[dict]:
    """The most-recent messages, but never breaking a tool exchange: accumulate
    whole atoms from the end until at least `keep_recent` messages are kept. This
    preserves recency (incl. the just-answered pair on the resume path) AND keeps
    tool-call/result pairs intact."""
    if keep_recent <= 0:
        return []
    tail: list[dict] = []
    count = 0
    for atom in reversed(_atoms(convo)):
        tail = atom + tail
        count += len(atom)
        if count >= keep_recent:
            break
    return tail


def _hard_truncate(messages: list[dict], keep_recent: int) -> tuple[list[dict], int]:
    """Keep every pinned message (in order) + the most-recent non-pinned messages
    (whole tool exchanges only); drop the middle. Returns (messages, dropped_count)."""
    pinned = [m for m in messages if _is_pinned(m)]
    convo = [m for m in messages if not _is_pinned(m)]
    if len(convo) <= keep_recent:
        return messages, 0
    kept_tail = _recent_tail(convo, keep_recent)
    dropped = len(convo) - len(kept_tail)
    # Preserve original ordering: pinned messages first (they lead the prompt), then
    # the recent tail. Pinned are system/anchor which by construction precede convo.
    return pinned + kept_tail, dropped


Summarizer = Callable[[list[dict]], Union[str, Awaitable[str]]]


async def compact_messages(
    messages: list[dict],
    *,
    effective_limit: int | None,
    trigger_ratio: float = COMPACT_TRIGGER_RATIO,
    target: int | None = None,
    keep_tool_results: int = 3,
    keep_recent: int = 8,
    exclude_tools: frozenset[str] = DEFAULT_EXCLUDE_TOOLS,
    summarize: Summarizer | None = None,
    add_breadcrumb: bool = False,
    collapse_duplicates: bool = False,
) -> tuple[list[dict], CompactionReport]:
    """Compact `messages` to fit under the trigger. Deterministic except for the
    optional `summarize` callback (sync OR async — an LLM call), whose failure is
    caught and downgraded to hard-truncate. Returns (new_messages, report). Never
    raises for a summarize failure — that is reported, not thrown (edge #2).

    The trigger is `int(effective_limit × trigger_ratio)` by default (fire near the
    window). T2/D3: pass `target` (the task-elastic soft budget from
    `token_budget.compute_target`) to fire at that SMALLER value instead — clamped to
    `effective_limit` so it can never exceed the hard ceiling. `effective_limit` stays
    required (it bounds `target` and is the fallback when `target` is None).

    Async because the summarizer is an LLM call; with `summarize=None` it does no I/O
    and is effectively the pure deterministic path."""
    report = CompactionReport()
    report.tokens_before = estimate_messages_tokens(messages)
    if not effective_limit or effective_limit <= 0:
        report.tokens_after = report.tokens_before
        return messages, report

    if target is not None and target > 0:
        # Soft task-elastic trigger, never above the hard ceiling.
        trigger = min(int(target), effective_limit)
    else:
        trigger = int(effective_limit * trigger_ratio)
    if report.tokens_before <= trigger:
        report.tokens_after = report.tokens_before
        return messages, report

    report.triggered = True
    work = [dict(m) for m in messages]  # copy so we never mutate the caller's list

    # 0. D13a reversible dup-read collapse (opt-in). Before evicting the OLDEST results,
    # collapse EXACT-duplicate reads (same content read twice) to a reference, keeping the
    # latest full — pure-waste reduction that never loses information (the identical content
    # is still present) and can't orphan (only rewrites content). Runs first so microcompact's
    # keep-last-N budget isn't spent on redundant copies.
    if collapse_duplicates:
        collapsed = _collapse_duplicate_reads(work, exclude_tools)
        if collapsed:
            report.duplicates_collapsed = collapsed
            report.steps.append("collapse_duplicates")
        # A collapsed `_DUP_PLACEHOLDER` is left alone by a subsequent microcompact pass
        # (it is skipped + not re-counted — see `_microcompact`), so `duplicates_collapsed`
        # and `tool_results_cleared` never double-count the same message.
        if estimate_messages_tokens(work) <= trigger:
            report.tokens_after = estimate_messages_tokens(work)
            return work, report

    # 1. microcompact tool results
    cleared = _microcompact(work, keep_tool_results, exclude_tools)
    if cleared:
        report.tool_results_cleared = cleared
        report.steps.append("microcompact")
    if estimate_messages_tokens(work) <= trigger:
        report.tokens_after = estimate_messages_tokens(work)
        return work, report

    # 2. full-compact via the injected summarizer (LLM path). Failure → fall through.
    # We compress the *droppable middle* (everything non-pinned except the recent tail),
    # so the recent turns stay verbatim and aren't double-represented in the summary.
    if summarize is not None:
        pinned = [m for m in work if _is_pinned(m)]
        non_pinned = [m for m in work if not _is_pinned(m)]
        tail = _recent_tail(non_pinned, keep_recent)
        middle = non_pinned[: len(non_pinned) - len(tail)]
        if middle:
            # T6/D6 breadcrumb — deterministic verbatim fact trace of the middle, computed
            # BEFORE the lossy LLM summary so it survives summarizer variance/failure (the
            # 1/9–9/9 recall swing the A/B found). Empty string when off / nothing salient.
            breadcrumb = extract_breadcrumb(middle) if add_breadcrumb else ""
            try:
                summary = summarize(middle)
                if inspect.isawaitable(summary):
                    summary = await summary
                summary = summary.strip() if summary else ""
            except Exception:
                summary = ""
                report.steps.append("summarize_failed")
            # Combine: the deterministic breadcrumb leads (system of record), the LLM
            # synopsis follows (convenience). Either alone is enough to keep the middle.
            body = "\n\n".join(p for p in (breadcrumb, summary) if p)
            if body:
                work = pinned + [summary_message(body)] + tail
                report.summarized = True
                report.steps.append("summarize" if summary else "breadcrumb")
            else:
                report.summarize_failed = True
    if estimate_messages_tokens(work) <= trigger:
        report.tokens_after = estimate_messages_tokens(work)
        return work, report

    # 3. hard-truncate (deterministic backstop)
    work, dropped = _hard_truncate(work, keep_recent)
    if dropped:
        report.turns_truncated = dropped
        report.steps.append("hard_truncate")

    report.tokens_after = estimate_messages_tokens(work)
    # edge #4: non-evictable messages alone still exceed the budget.
    if report.tokens_after > effective_limit:
        report.overflowed = True
        report.steps.append("overflow")
    return work, report


class CompactionStrategy:
    """The tiered clear→summarize→truncate compaction (Context Budget Law §12) as a
    swappable object. A thin, stateless wrapper over `compact_messages` — subclass and
    override `compact` to A/B a strategy (tier order, breadcrumb on/off, keep-recent) the
    same way `Planner` is the swappable POLICY seam. Construct once, reuse."""

    async def compact(
        self,
        messages: list[dict],
        *,
        effective_limit: int | None,
        target: int | None = None,
        trigger_ratio: float = COMPACT_TRIGGER_RATIO,
        keep_tool_results: int = 3,
        keep_recent: int = 8,
        exclude_tools: frozenset[str] = DEFAULT_EXCLUDE_TOOLS,
        summarize: Summarizer | None = None,
        add_breadcrumb: bool = False,
        collapse_duplicates: bool = False,
    ) -> tuple[list[dict], CompactionReport]:
        return await compact_messages(
            messages,
            effective_limit=effective_limit,
            target=target,
            trigger_ratio=trigger_ratio,
            keep_tool_results=keep_tool_results,
            keep_recent=keep_recent,
            exclude_tools=exclude_tools,
            summarize=summarize,
            add_breadcrumb=add_breadcrumb,
            collapse_duplicates=collapse_duplicates,
        )
