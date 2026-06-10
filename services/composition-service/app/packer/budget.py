"""Budget trim — priority ladder, drop lowest-first (§2.3).

The pack is a list of `Segment`s, each tagged with a drop `priority` (higher =
keep longer) and a `protected` flag for the never-drop tiers (L0 canon, L1a core
state, L1b in-window events, L2 beat/goal, L3 immediate prose). When the pack
exceeds the token budget we drop the lowest-priority UNPROTECTED segments first;
protected segments are always kept (if they alone exceed budget we keep them and
flag `over_budget` — better to over-spend than drop a canon constraint).

Token counting is injectable so tests stay deterministic; the default counter
uses tiktoken (cl100k_base) — a reasonable multilingual proxy incl. CJK.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# Drop-priority tiers (higher = kept longer). Mirrors the §2.3 ladder.
PRIO_CANON = 100        # protected
PRIO_PRESENT_CORE = 95  # protected — L1a current state
PRIO_TIMELINE_WINDOW = 90  # protected — L1b in-window events
PRIO_BEAT = 85          # protected — L2 beat/goal/POV/synopsis
PRIO_PROMISES = 84      # protected — L2.5 open-promise re-injection (FD-1 S3, F2)
PRIO_RECENT_IMMEDIATE = 80  # protected — L3 immediately-preceding prose
PRIO_TIMELINE_OLDER = 40    # droppable
PRIO_RELATIONS_2HOP = 35
PRIO_THREADS_STALE = 30
PRIO_RECENT_OLDER = 25
PRIO_LORE = 20          # L4 refs — dropped first


@dataclass
class Segment:
    block: str       # the <block> it belongs to: canon/present/threads/beat/recent/lore/…
    text: str
    priority: int
    protected: bool = False


TokenCounter = Callable[[str], int]

_encoder = None


def _tiktoken_counter(text: str) -> int:
    global _encoder
    if _encoder is None:
        import tiktoken
        _encoder = tiktoken.get_encoding("cl100k_base")
    return len(_encoder.encode(text))


def default_counter() -> TokenCounter:
    return _tiktoken_counter


@dataclass
class BudgetResult:
    kept: list[Segment]
    dropped_count: int
    total_tokens: int
    over_budget: bool   # True if protected segments alone exceed the budget


def enforce_budget(
    segments: list[Segment], budget: int, counter: TokenCounter,
) -> BudgetResult:
    """Drop lowest-priority unprotected segments until under `budget`. Protected
    segments are never dropped. Returns the kept segments (original order)."""
    sized = [(seg, counter(seg.text)) for seg in segments]
    total = sum(n for _, n in sized)
    if total <= budget:
        return BudgetResult([s for s, _ in sized], 0, total, over_budget=False)

    # Candidates to drop = unprotected, lowest priority first; tie-break on size
    # (drop the larger one first to free budget faster).
    droppable = sorted(
        (i for i, (s, _) in enumerate(sized) if not s.protected),
        key=lambda i: (sized[i][0].priority, -sized[i][1]),
    )
    dropped: set[int] = set()
    for i in droppable:
        if total <= budget:
            break
        dropped.add(i)
        total -= sized[i][1]

    kept = [s for idx, (s, _) in enumerate(sized) if idx not in dropped]
    protected_total = sum(n for s, n in sized if s.protected)
    return BudgetResult(
        kept=kept, dropped_count=len(dropped), total_tokens=total,
        over_budget=protected_total > budget,
    )
