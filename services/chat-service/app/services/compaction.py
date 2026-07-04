"""Provider-agnostic conversation compaction (RAID Wave A4).

Keeps a turn under the model's context window WITHOUT a provider-specific feature —
works for local lm_studio / Qwen / Gemma AND Claude (the Anthropic server-side
overlay is A5, layered on top). The measured provider usage stays ground truth;
this acts on the assembled `messages` before the provider call, keyed off the
script-aware estimate (token_budget.py) so it is right for the VN/CJK POC (edge #1).

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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Union

from app.services.token_budget import estimate_messages_tokens

# Tool names whose results are NEVER evicted (their output is load-bearing / cited).
DEFAULT_EXCLUDE_TOOLS = frozenset({"web_search"})
_PLACEHOLDER = "[tool result cleared to save context]"

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
            or self.summarized
            or self.turns_truncated > 0
        )

    def to_event(self) -> dict:
        return {
            "triggered": self.triggered,
            "tool_results_cleared": self.tool_results_cleared,
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
    tools. Returns how many were cleared. Mutates copies in-place (caller passes a copy)."""
    idxs = [
        i for i, m in enumerate(messages)
        if _is_tool_result(m) and (_tool_name(m) not in exclude)
    ]
    if len(idxs) <= keep:
        return 0
    to_clear = idxs[: len(idxs) - keep]  # oldest first
    for i in to_clear:
        m = messages[i]
        if m.get("content") != _PLACEHOLDER:
            m["content"] = _PLACEHOLDER
    return len(to_clear)


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
    keep_tool_results: int = 3,
    keep_recent: int = 8,
    exclude_tools: frozenset[str] = DEFAULT_EXCLUDE_TOOLS,
    summarize: Summarizer | None = None,
) -> tuple[list[dict], CompactionReport]:
    """Compact `messages` to fit under `effective_limit` tokens. Deterministic except
    for the optional `summarize` callback (sync OR async — an LLM call), whose failure
    is caught and downgraded to hard-truncate. Returns (new_messages, report). Never
    raises for a summarize failure — that is reported, not thrown (edge #2).

    Async because the summarizer is an LLM call; with `summarize=None` it does no I/O
    and is effectively the pure deterministic path."""
    report = CompactionReport()
    report.tokens_before = estimate_messages_tokens(messages)
    if not effective_limit or effective_limit <= 0:
        report.tokens_after = report.tokens_before
        return messages, report

    trigger = int(effective_limit * trigger_ratio)
    if report.tokens_before <= trigger:
        report.tokens_after = report.tokens_before
        return messages, report

    report.triggered = True
    work = [dict(m) for m in messages]  # copy so we never mutate the caller's list

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
            try:
                summary = summarize(middle)
                if inspect.isawaitable(summary):
                    summary = await summary
                if summary and summary.strip():
                    work = pinned + [summary_message(summary)] + tail
                    report.summarized = True
                    report.steps.append("summarize")
                else:
                    report.summarize_failed = True
            except Exception:
                report.summarize_failed = True
                report.steps.append("summarize_failed")
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
