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
    # ACP-10 — AUTONOMOUS mode only: an exhausted REQUIRED step has no user to re-prompt, so it
    # PARKS (escalate + move on) instead of holding. `park_reason` carries the escalation note.
    parked: bool = False
    park_reason: str | None = None
    #: Why the rail did NOT claim this turn. A declining guard that says nothing is
    #: indistinguishable from a rail with nothing to do — the ambiguity that made this class
    #: of defect a transcript-read instead of a grep.
    declined_reason: str | None = None


@dataclass(frozen=True)
class TurnRequest:
    """What THIS turn was asked for — the input the drive decision could not previously see.

    🔴 THE HOLE THIS CLOSES (2026-08-13). `decide_rail_drive` took the rail state, the book
    probe, the nudge counters and the enforcement strength — and nothing at all about the
    user's request. Not down-weighted: structurally absent. The only route the user's words
    had into the decision was `user_abandoned_rail`, a literal regex of ~8 abandon phrases
    applied as a consumer-side guard.

    So the arbitration model the system actually implemented was: THE RAIL OWNS EVERY TURN ON
    A BOOK WITH AN OUTSTANDING STEP, and the user may revoke that ownership only by uttering
    one of those phrases. Ownership was opt-OUT.

    Measured cost, session 019ff929: the author typed "Load the tool composition_list_outline
    by name, then use it to show me the outline of this book." The turn pinned no rail, so a
    STALE `build-a-book` rail from an earlier journey claimed it and drove `plan_propose_spec`
    four times — every call refused. `tool_load` was advertised in all six passes and was
    never called once. The request was discarded after a single fumble.

    Every field is DETERMINISTIC — a literal match or a set intersection, never an inference.
    A field the consumer cannot compute honestly stays empty, and an empty TurnRequest
    reproduces the previous behaviour exactly (rule 5 below), which is what keeps the rail
    doing the job it was built for: an assent ("ok", "yes", "go on") pins nothing, names
    nothing, and is still driven.
    """

    #: Rails the user's own words describe (intent_pinned_workflows) — NOT the mode binding.
    pinned_rails: frozenset[str] = frozenset()
    #: Catalog tool names appearing literally in the message. The user is steering the action
    #: space themselves, which is the one signal that outranks a journey.
    named_tools: frozenset[str] = frozenset()
    #: The existing GOV-13 literal release. Also enforced by a consumer guard upstream; kept
    #: here so the whole precedence table can be read in one place.
    abandons_rail: bool = False


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
    request: TurnRequest | None = None,
    stuck_tools: frozenset[str] = frozenset(),
    mode: str = "interactive",
) -> DriveVerdict:
    """Decide whether to drive the next rail step this turn, and how hard — one verdict.

    ``mode`` (ACP-10, per-runtime enforcement policy): ``interactive`` (chat) holds an exhausted
    REQUIRED step + re-prompts the user with an honest give-up; ``autonomous`` (a future
    background/game runtime — no user to re-prompt) instead PARKS it (``parked=True`` +
    ``park_reason``) so the runtime escalates and moves on (``blocked ≠ stopped``). The verdict
    machine is shared; only this release policy differs by mode.

    `probe_fn` is INJECTED (RW-11) — the consumer supplies its own book-state probe; the harness
    calls it fresh (the turn-start counts go stale the moment the model writes mid-turn). Never
    raises: any failure degrades to `should_drive=False` (today's end-of-turn). `nudge_counts`
    (a Counter) and `nudged_out` (a set) are the consumer's cross-turn state — the harness reads
    and updates them in place, mirroring the pre-extraction behavior exactly.
    """
    req = request or TurnRequest()
    # ── TURN OWNERSHIP, in precedence order. The rail CLAIMS a turn; it does not own one. ──
    #
    #   1. the user released it            → no drive   (GOV-13, also a consumer guard)
    #   2. the user named a tool           → no drive   (they are steering the action space)
    #   3. the user's words pinned rails   → only those may claim it
    #   4. the pinned rail has nothing left→ no drive   (falls out of 3 + next_actionable_step)
    #   5. otherwise                       → drive exactly as before
    #
    # Rule 5 is load-bearing, not a fallback: the rail exists because a mid-tier model will
    # not self-start (S03 0/3, S04 1/3, S09 improvises), and an assent carries no pin and no
    # tool name. Making ownership opt-IN must not weaken the case that justified the driver,
    # so an empty TurnRequest is byte-identical to the pre-contract behaviour.
    if req.abandons_rail:
        return DriveVerdict(should_drive=False, declined_reason="user released the rail")
    if req.named_tools:
        # A message naming a catalog tool is a DISCOVERY turn. 281 of 315 tools are reachable
        # only by the model choosing tool_list/tool_load, and a rail directive replaces that
        # choice with its own step — the recovery path deleting the discovery path. When the
        # user has named the tool themselves there is nothing left to recover.
        return DriveVerdict(
            should_drive=False,
            declined_reason="the request names " + ", ".join(sorted(req.named_tools)),
        )
    if req.pinned_rails:
        _kept = [(slug, steps) for slug, steps in rail_specs if slug in req.pinned_rails]
        if _kept:
            rail_specs = _kept
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
            return DriveVerdict(
                should_drive=False, declined_reason="no actionable step")

        slug, step = drive
        raw_step = next(
            (s for _sl, _steps in rail_specs if _sl == slug
             for s in _steps if str(s.get("id")) == step.step_id),
            {},
        )
        if step.tool and step.tool in stuck_tools:
            # A step whose tool keeps failing THE SAME WAY is not a model that needs steering;
            # it is a wall. Re-driving it burns the turn and buries whatever the user asked.
            #
            # chat-service already has the right rule — the repeated-failure breaker keys on
            # (tool → error → count) and stops at 2 identical failures. It could not help here
            # because BOTH that map and these nudge counters are rebuilt per turn, so a step
            # failing twice a turn resets forever. Measured: plan_propose_spec, 4 identical
            # "not found or not accessible" across 2 turns, breaker never fired. The consumer
            # now supplies the cross-turn verdict and the rail honours it.
            nudged_out.add(step.step_id)
            return DriveVerdict(
                should_drive=True, slug=slug, step=step,
                directive_text=honest_giveup_directive(step), giving_up=True,
                declined_reason="step tool " + str(step.tool) + " keeps failing identically",
            )
        nudge_counts[step.step_id] += 1
        enforced, cap = enforcement_for(raw_step, enforcement_strength, required_nudge_cap)
        giving_up = nudge_counts[step.step_id] >= cap
        if giving_up:
            nudged_out.add(step.step_id)
        # An ENFORCED, exhausted step gets the honest give-up (GOV-7); else the forceful nudge.
        honest = giving_up and enforced
        # ACP-10 — AUTONOMOUS: no user to re-prompt → PARK the exhausted step + escalate, never hold.
        if honest and mode == "autonomous":
            return DriveVerdict(
                should_drive=False, slug=slug, step=step, giving_up=True, parked=True,
                park_reason=f"step '{step.step_id}' unmet after {cap} attempts — parked for escalation",
            )
        directive = honest_giveup_directive(step) if honest else redrive_directive(step)
        return DriveVerdict(
            should_drive=True, slug=slug, step=step, directive_text=directive, giving_up=honest,
        )
    except Exception:  # noqa: BLE001 — the driver must never break a turn
        logger.warning("rail drive-decision skipped", exc_info=True)
        return DriveVerdict(should_drive=False)
