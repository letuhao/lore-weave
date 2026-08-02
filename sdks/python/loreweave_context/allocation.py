"""S11 — the allocation layer between a window and the budgets carved out of it.

The gap this fills
------------------
Two budget functions already exist and they are **not complementary**, though the spec's v1
asserted they compose. Their denominators differ by ~25x:

  · ``compute_target(window)``  — a soft target for the WHOLE context window (0.10-0.75 of it).
  · ``enforce_budget(segs, n)`` — trims the GROUNDING BLOCK alone to ``n`` tokens.

Nothing sits between them. So composition sizes its grounding block with
``scale_by_window(pack_token_budget=6000, window)``, whose contract is *"Never smaller than
`flat_default` … this only ever grows the budget"* — which is correct for the problem it was
written for (flat constants tuned against a 200K model that never grew) and wrong as an
allocator, because an allocator's whole job is to be able to say **less**.

MEASURED, `scale_by_window(6000, window)` as a share of the window it must fit inside:

    window     grounding      share
      4096          6000     146.5%   ← the block alone exceeds the whole context
      8192          6000      73.2%   ← before the prompt, and before any output
     16384          6000      36.6%
     32768          6000      18.3%
    200000          6000       3.0%

At 4096 the request cannot be built. At 8192 it can, and then the prompt and the output
compete for the remaining quarter — which is exactly the overflow ``resolve_distill_window``
was written to prevent one service over, and the same shape S7-1 fixed for worker-ai's distill
reserve. The output side of that sum got BIGGER in S7-4, so the two halves now have to be
decided together rather than each defending itself.

What this does NOT do
---------------------
It does not change any existing behaviour, and it cannot: it is a new name with no callers.
That is deliberate and it is the sealed rule (RUN-STATE invariant 6, and the spec's own
correction) — **additive-then-switch is impossible through a shared symbol**, because the SDK
is not version-pinned. Every service does ``COPY sdks/python`` + ``pip install /sdk``, so
editing ``compute_target`` or ``scale_by_window`` in place would be adopted by chat,
knowledge and worker-ai on their next unrelated rebuild. So: new name, and each consumer
flips in its own commit, after its own measurement.

The unknown-window case is the load-bearing one
-----------------------------------------------
When the window is unknown this returns the caller's flat defaults **unchanged**, and says so
via ``source``. A caller that adopts this must be able to see that it changed nothing, or the
first adoption is indistinguishable from a silent re-tuning of every book.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ContextAllocation", "allocate_context", "DEFAULT_OVERHEAD_SHARE"]

#: Share of the window reserved for everything that is neither the grounding block nor the
#: output: the system message, the guide, the length directive, recent prose, the canon
#: constraint. REASONED from the packer's segment list, not measured against real prompts —
#: `ContextAllocation.source` and the tests say so rather than letting the number imply
#: authority it has not earned.
DEFAULT_OVERHEAD_SHARE = 0.25

#: Never hand back a grounding budget below this. A window too small to hold a usable block
#: is a configuration problem, and the honest response is a floor plus `clamped=True` — not a
#: budget of 12 tokens that produces an empty pack and reads as "this book has no grounding".
#: Same reasoning as `MIN_WINDOW_TOKENS` in worker-ai's distiller.
_MIN_GROUNDING = 512


@dataclass(frozen=True)
class ContextAllocation:
    """One window, divided. Every field is a number a caller can act on, plus why."""

    #: The window this was computed against; None ⇒ the caller did not know it.
    window: int | None
    #: Tokens the grounding block may use — what `enforce_budget` should be handed.
    grounding: int
    #: Tokens set aside for the model's reply, echoed back so a caller can see the sum it is
    #: part of rather than reconciling two numbers from two places.
    output_reserve: int
    #: Everything that is neither grounding nor output.
    overhead: int
    #: "flat" ⇒ window unknown, the caller's defaults returned untouched.
    #: "window" ⇒ derived from the window.
    source: str
    #: True ⇒ the caller's requested grounding did NOT fit and was reduced. This is the field
    #: that makes adoption safe to review: a consumer can assert it is False across its real
    #: traffic and know the switch changed nothing for anybody.
    clamped: bool

    @property
    def total(self) -> int:
        return self.grounding + self.output_reserve + self.overhead

    @property
    def fits(self) -> bool:
        """False ⇒ even the floor does not fit; the caller is over-committed on this model."""
        return self.window is None or self.total <= self.window


def allocate_context(
    window: int | None,
    *,
    grounding_default: int,
    output_reserve: int,
    overhead_share: float = DEFAULT_OVERHEAD_SHARE,
    min_grounding: int = _MIN_GROUNDING,
) -> ContextAllocation:
    """Divide `window` among grounding, output and overhead.

    `grounding_default` is what the caller would have used anyway — it is a CEILING here, never
    a floor. That inversion is the whole point: `scale_by_window` treats the flat default as a
    minimum and can only grow it, which is why an 8K model is still asked for a 6000-token
    grounding block.

    An unknown window returns the caller's numbers untouched (`source="flat"`), so adopting
    this on a path where the window cannot be resolved is a provable no-op.
    """
    if not window or window <= 0:
        return ContextAllocation(
            window=None, grounding=grounding_default, output_reserve=output_reserve,
            overhead=0, source="flat", clamped=False,
        )

    overhead = int(window * max(0.0, min(1.0, overhead_share)))
    # What is left for grounding once the reply and the rest of the prompt are paid for. The
    # output reserve is subtracted rather than shared because it is the one part that CANNOT
    # be trimmed after the fact: prose is generated into it, and a scene that stops mid
    # sentence is the failure the whole budget seam exists to avoid.
    available = window - output_reserve - overhead
    grounding = min(grounding_default, available)

    clamped = grounding < grounding_default
    if grounding < min_grounding:
        # Below the floor the honest answer is the floor AND the flag — a 12-token grounding
        # block would return an empty pack that reads as "this book has nothing to ground on",
        # which is a lie a caller cannot distinguish from the truth.
        grounding = min_grounding
    return ContextAllocation(
        window=window, grounding=grounding, output_reserve=output_reserve,
        overhead=overhead, source="window", clamped=clamped,
    )
