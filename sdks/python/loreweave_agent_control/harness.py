"""Agent Control Plane SDK — the drive HARNESS (ACP A2, RW-3 / RV-H3).

The verdict-only drive decision, extracted from chat-service's stream loop. It UNIFIES the two
pieces that used to be split there: the *drive decision* (`_maybe_redrive_rail` — re-probe the
book fresh, compute progress, pick the next actionable step) AND the *enforcement decision* (the
inline block at stream_service:1806-1853 — the per-step nudge cap, the deploy strength, the
honest give-up vs the forceful nudge).

RW-3 (the boundary that makes it reusable): this returns a **verdict**; the CONSUMER owns the loop
mechanics — appending the directive as a `role=user` message, bumping its redrive counter, dropping
the stateful chain head, and `continue`-ing the loop. The harness owns NO streaming/generator state.

RV-H3 (the real signature, not "hold|release"): the verdict carries the probe (INJECTED — RW-11, so
any runtime supplies its own effect-probe), the cross-turn nudge counters, the enforcement strength,
and the escape-hatch outcome — the things the drive genuinely depends on.

RV-H2: a consumer may run this as ONE of a SET of active control programs (executive tick + rail
drive), sequenced — the harness governs the RAIL program only; it never assumes it is the sole one.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from .rail import (
    DRIVE,
    StepProgress,
    compute_rail_progress,
    enforcement_for,
    honest_giveup_directive,
    next_actionable_step,
    redrive_directive,
)

logger = logging.getLogger(__name__)


class _BookStateLike(Protocol):
    """Duck-typed book-state — whatever the injected probe returns; `compute_rail_progress`
    reads it via `.get(key)`. Kept a Protocol so the harness imports no chat internals."""

    def get(self, key: str) -> int | None: ...


# The injected effect-probe (RW-11): async (book_id, user_id) -> a BookState-like object.
ProbeFn = Callable[[str, str], Awaitable[_BookStateLike]]


@dataclass
class DriveVerdict:
    """What the harness decided — a pure value; the consumer executes it in ITS loop.

    - `should_drive=False` ⇒ end the turn (nothing drivable / degraded probe / all guards say stop).
    - `should_drive=True`  ⇒ inject `directive_text` as a `role=user` message and loop once more.
      `giving_up` marks the honest give-up (GOV-7): the directive tells the user it did not land,
      and the consumer should stop re-driving THIS step after this pass.
    """

    should_drive: bool
    slug: str | None = None
    step: StepProgress | None = None
    directive_text: str | None = None
    giving_up: bool = False


async def decide_rail_drive(
    *,
    probe_fn: ProbeFn,
    rail_specs: list[tuple[str, list[dict]]],
    book_id: str,
    user_id: str,
    turn_start_counts: dict | None,
    turn_succeeded,
    async_tools: frozenset[str],
    nudged_out: set[str],
    nudge_counts: Counter,
    enforcement_strength: str,
    required_nudge_cap: int,
) -> DriveVerdict:
    """Decide whether to drive the next rail step this turn, and how hard — one verdict.

    `probe_fn` is INJECTED (RW-11) — the consumer supplies its own book-state probe; the harness
    calls it fresh (the turn-start counts go stale the moment the model writes mid-turn). Never
    raises: any failure degrades to `should_drive=False` (today's end-of-turn). `nudge_counts`
    (a Counter) and `nudged_out` (a set) are the consumer's cross-turn state — the harness reads
    and updates them in place, mirroring the pre-extraction behavior exactly.
    """
    try:
        fresh = await probe_fn(str(book_id), str(user_id))
        merged = Counter(turn_start_counts or {}) + turn_succeeded
        started = set(merged)
        drive: tuple[str, StepProgress] | None = None
        for slug, steps in rail_specs:
            if not isinstance(steps, list) or not steps:
                continue
            prog = compute_rail_progress(slug, steps, fresh, merged)
            action, step = next_actionable_step(prog, steps, started, async_tools)
            if action == DRIVE and step is not None and step.step_id not in nudged_out:
                drive = (slug, step)
                break
        if drive is None:
            return DriveVerdict(should_drive=False)

        slug, step = drive
        raw_step = next(
            (s for _sl, _steps in rail_specs if _sl == slug
             for s in _steps if str(s.get("id")) == step.step_id),
            {},
        )
        nudge_counts[step.step_id] += 1
        enforced, cap = enforcement_for(raw_step, enforcement_strength, required_nudge_cap)
        giving_up = nudge_counts[step.step_id] >= cap
        if giving_up:
            nudged_out.add(step.step_id)
        # An ENFORCED, exhausted step gets the honest give-up (GOV-7); else the forceful nudge.
        honest = giving_up and enforced
        directive = honest_giveup_directive(step) if honest else redrive_directive(step)
        return DriveVerdict(
            should_drive=True, slug=slug, step=step, directive_text=directive, giving_up=honest,
        )
    except Exception:  # noqa: BLE001 — the driver must never break a turn
        logger.warning("rail drive-decision skipped", exc_info=True)
        return DriveVerdict(should_drive=False)
