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

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

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
PRIO_REFERENCES = 18    # T3.6 author reference passages — softest steer; trimmed before lore (a PINNED reference is protected)


@dataclass
class Segment:
    block: str       # the <block> it belongs to: canon/present/threads/beat/recent/lore/…
    text: str
    priority: int
    protected: bool = False


TokenCounter = Callable[[str], int]

_encoder = None
_encoder_name = ""


def _load_encoder() -> tuple[object | None, str]:
    """D-PACK-CL100K-STARVES-NONLATIN (2026-07-31).

    This counted with **cl100k_base**, which knowledge-service retired on 2026-07-07 after
    a live gateway measurement (`docs/eval/context-budget/M3-tokenlever-tuning-2026-07-07.md`):
    cl100k tokenizes CJK/Vietnamese at ~1.5-2.5 tokens/char, **far above what the platform
    actually serves** — GPT-4o (o200k) and the local gemma/qwen models at ~1 tok/CJK-char.
    Its docstring names the consequence exactly: *"CJK books were trimmed to a smaller REAL
    budget than Latin ones"*.

    composition-service never got that fix, so `pack_token_budget` meant two different
    things depending on the book's language. Measured on real Vietnamese prose from the
    dogfood book, characters of grounding surviving a 6000-token budget:

        English                29,756   (cl100k and o200k agree on Latin)
        Vietnamese · cl100k    11,777   ← 40% of the English budget
        Vietnamese · o200k     17,636   ← 59%

    Vietnamese genuinely tokenizes denser than English — that part is real and stays. The
    defect was the ADDITIONAL 1.50x over-count, which silently starved every non-Latin
    book's grounding. `pack_token_budget` is deliberately UNCHANGED: 6000 was always meant
    to buy ~6000 real tokens, and it now does so in every language rather than only in
    Latin ones.

    The fallback chain is lifted verbatim in spirit from knowledge-service's counter, which
    composition lacked entirely: a bare `import tiktoken` + `get_encoding` inside the pack
    meant an air-gapped or cold container raised **inside `enforce_budget`** — tiktoken
    fetches its BPE file over HTTPS on first use. Degrading loudly to a rough estimate is
    strictly better than failing a draft.
    """
    try:
        import tiktoken
    except Exception:  # noqa: BLE001 — missing wheel, network-less install, cold container
        logger.warning(
            "tiktoken unavailable — packing with a rough char heuristic. Budgets will be "
            "approximate; install tiktoken for accurate trimming."
        )
        return None, "heuristic"
    try:
        return tiktoken.get_encoding("o200k_base"), "o200k_base"
    except Exception:  # noqa: BLE001 — tiktoken too old to carry the GPT-4o encoding
        logger.warning(
            "tiktoken o200k_base unavailable — falling back to cl100k_base, which "
            "over-counts CJK/Vietnamese ~1.5x and will under-fill non-Latin packs. "
            "Upgrade tiktoken."
        )
        return tiktoken.get_encoding("cl100k_base"), "cl100k_base"


def _tiktoken_counter(text: str) -> int:
    global _encoder, _encoder_name
    if _encoder_name == "":
        _encoder, _encoder_name = _load_encoder()
    if _encoder is None:
        # Last-resort heuristic. Deliberately NOT len/4: that under-counts CJK 4-8x and
        # would overflow the prompt rather than merely trimming it short.
        return max(1, len(text) // 3)
    return len(_encoder.encode(text))


def encoder_name() -> str:
    """Which encoding the pack is actually budgeting with — surfaced so a degraded
    fallback is visible rather than silently changing every book's budget."""
    global _encoder, _encoder_name
    if _encoder_name == "":
        _encoder, _encoder_name = _load_encoder()
    return _encoder_name


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
