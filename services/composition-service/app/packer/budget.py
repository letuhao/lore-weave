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


# ── S11 · the allocation layer: how much grounding actually FITS ──────────────────────────

#: Tokens set aside for the scene reply when sizing the grounding block.
#:
#: REASONED, and the reasoning is the point: a default-target Vietnamese scene is
#: `DEFAULT_SCENE_TARGET_WORDS` (1000) x 2.6 tokens/word x the PROSE headroom (2.0) — call it
#: ~4700. NOT `SCENE_OUTPUT_CEILING` (32768): that is a runaway guard, and reserving it would
#: clamp the grounding block to its floor on every model up to ~128K, which is a re-tuning of
#: every book disguised as a safety fix.
#:
#: It is an ESTIMATE used only to decide how much room grounding may take, and it is needed
#: BEFORE the real output budget can be computed — `scene_output_budget` wants the profile's
#: language, and the profile comes out of the pack this budget is sizing. Reserving a typical
#: reply rather than the true one is the honest way out of that ordering, and it errs toward
#: reserving too much (smaller grounding) rather than too little (a truncated scene).
PACK_OUTPUT_RESERVE_TOKENS = 4700


def pack_budget_for(context_length: int | None, flat_default: int, *,
                    output_reserve: int = PACK_OUTPUT_RESERVE_TOKENS):
    """How many grounding tokens this model can actually afford.

    Composes the two budget functions that were never composed. `scale_by_window` answers
    *how much would we LIKE* — it grows a flat default for a genuinely bigger model and, by
    its own contract, "only ever grows". `allocate_context` answers *how much FITS* once the
    reply and the rest of the prompt are paid for. Neither alone is correct:

      · `scale_by_window` alone leaves an 8K model asking for a 6000-token grounding block —
        73% of its entire window before the prompt or the output. At 4096 it asks for 146%.
      · `allocate_context` alone would CAP at the flat default and lose the growth a 1M-window
        model should get.

    MEASURED across real windows, with the two composed (reserve = 4700):
        window   want    gets    effect
          None   6000    6000    unchanged (window unknown ⇒ caller's number, untouched)
          4096   6000     512    REDUCED — today's value is 146% of the window
          8192   6000    1444    REDUCED — today's value is 73% of the window
         16384   6000    6000    unchanged
        200000   6000    6000    unchanged
       1000000  30000   30000    unchanged (the growth survives)

    So adopting this is a no-op on every window at or above 16K and on every unresolved one,
    and only bites where the current number cannot work. That measurement is what RUN-STATE
    invariant 6 requires before a consumer may switch.

    Returns the full `ContextAllocation` rather than an int so the caller can report
    `clamped`/`fits` instead of silently shrinking a book's grounding — the S8 rule that a
    number the pack computed must be able to reach the job.
    """
    from loreweave_context import allocate_context, scale_by_window

    alloc = allocate_context(
        context_length,
        grounding_default=scale_by_window(flat_default, context_length),
        output_reserve=output_reserve,
    )
    if alloc.clamped:
        # A book whose grounding was silently reduced looks, from the prose, exactly like a
        # book that had little grounding to begin with — the same indistinguishability that
        # let `propose_world` return zero entities for weeks. Say it happened.
        logger.warning(
            "pack budget CLAMPED to the model's window: grounding %d (wanted %d) · "
            "window=%s · output_reserve=%d · fits=%s",
            alloc.grounding, scale_by_window(flat_default, context_length),
            alloc.window, alloc.output_reserve, alloc.fits,
        )
    return alloc
