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
  2. **full-compact (optional)** — an injected ``summarize`` callback (the LLM path,
     wired by stream_service / A5). Its FAILURE falls through to (3) — never draft on
     a poisoned summary (edge #2).
  3. **hard-truncate** — if still over, drop the oldest non-pinned conversation turns,
     keeping the system/steering/anchor/pinned messages + the last ``keep_recent``
     turns verbatim. Deterministic, no model call.

If even the non-evictable messages exceed the budget (edge #4) the result carries
``overflowed=True`` so the caller can surface it / trip a breaker (autonomous runs).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.services.token_budget import estimate_messages_tokens

# Tool names whose results are NEVER evicted (their output is load-bearing / cited).
DEFAULT_EXCLUDE_TOOLS = frozenset({"web_search"})
_PLACEHOLDER = "[tool result cleared to save context]"


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


def _hard_truncate(messages: list[dict], keep_recent: int) -> tuple[list[dict], int]:
    """Keep every pinned message (in order) + the last `keep_recent` non-pinned
    messages; drop the middle. Returns (messages, dropped_count)."""
    pinned = [m for m in messages if _is_pinned(m)]
    convo = [m for m in messages if not _is_pinned(m)]
    if len(convo) <= keep_recent:
        return messages, 0
    kept_tail = convo[-keep_recent:] if keep_recent > 0 else []
    dropped = len(convo) - len(kept_tail)
    # Preserve original ordering: pinned messages first (they lead the prompt), then
    # the recent tail. Pinned are system/anchor which by construction precede convo.
    return pinned + kept_tail, dropped


def compact_messages(
    messages: list[dict],
    *,
    effective_limit: int | None,
    trigger_ratio: float = 0.75,
    keep_tool_results: int = 3,
    keep_recent: int = 8,
    exclude_tools: frozenset[str] = DEFAULT_EXCLUDE_TOOLS,
    summarize: Callable[[list[dict]], str] | None = None,
) -> tuple[list[dict], CompactionReport]:
    """Compact `messages` to fit under `effective_limit` tokens. Pure + deterministic
    except for the optional `summarize` LLM callback (whose failure is caught and
    downgraded to hard-truncate). Returns (new_messages, report). Never raises for a
    summarize failure — that is reported, not thrown (edge #2)."""
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
    if summarize is not None:
        try:
            summary = summarize(work)
            if summary and summary.strip():
                pinned = [m for m in work if _is_pinned(m)]
                tail = [m for m in work if not _is_pinned(m)][-keep_recent:]
                summary_msg = {"role": "system", "content": f"<summary>\n{summary.strip()}\n</summary>"}
                work = pinned + [summary_msg] + tail
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
