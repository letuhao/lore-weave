"""The extraction prompt SHAPE, as a per-job closed set.

`BOOK_TO_GAME/15` measured four shapes over a frozen 10-chapter slice and found the cost
differences (60%+) far outside the noise floor while most quality differences sat inside
it. Ten chapters of one book is not enough to choose, so the shapes ship as a per-job
parameter and the choice is made from an A/B run at real scale.

**Why per-job and not a deploy flag.** A global `EXTRACTION_STRATEGY` env var cannot A/B:
it has to be flipped between runs, so the two arms differ in *when* they ran as well as in
*how* — and `BTG-A41` is the measured case of exactly that confound (the known-entity
context makes extraction path-dependent, so a later run inherits an earlier one's
discoveries). Two jobs on one book with different strategies is the comparison that works.
It also keeps this off the global-flag path CLAUDE.md's settings boundary forbids for
user-facing behavior: two users genuinely would want different values.

Measured per chapter over chapters 21-30 of 封神演義 (Gemma-4 26B-A4B QAT, concurrency 1):

    strategy            in      out   calls   grounded   new/ch   note
    batched         22,614    6,189     3.0      80.1%      9.7   the shipped shape
    single_call      8,603    3,282     1.0      80.1%      8.1   -62% in, -47% out
    single_call_delta 8,688   3,301     1.0      81.8%      9.5   best kind mix of the cheap arms
    edc_cited        9,663    5,266     2.0      92.7%     12.5   best quality; DROPS `event`

`edc_cited` carries a known coverage hole and is not a default candidate: its sweep asks
for a name quoted verbatim, and an event has no name in the text to quote — it has to be
composed (`BTG-A55`). It extracted zero events where the baseline found 34, and an
explicit, emphatic prompt fix moved that to two. Use it only for the nameable kinds, or
accept the hole knowingly.
"""
from __future__ import annotations

from typing import Final

#: The shipped 3-batch shape. The default, so an unspecified job behaves exactly as before.
BATCHED: Final = "batched"
#: Every kind in one call. -62% input, -47% output, 2x faster; needs the raised output
#: ceiling and the parse retry, because one call makes a bad parse cost the whole chapter.
SINGLE_CALL: Final = "single_call"
#: SINGLE_CALL plus "report only what is NEW". Same cost, best kind mix of the cheap arms,
#: and its apparent recall loss is suppressed repeats rather than missed discoveries.
SINGLE_CALL_DELTA: Final = "single_call_delta"
#: Two stages: sweep for named mentions with a quote, then type from the CITATIONS rather
#: than from the chapter again. Best grounding and discovery measured; see the `event` hole.
EDC_CITED: Final = "edc_cited"

#: What the WORKER actually implements. The API advertises only this — a strategy the
#: engine does not wire must not be accepted, or it runs as the default and the A/B reports
#: "no difference" from a control compared against itself. Caught in the live smoke exactly
#: that way: `edc_cited` and `batched` both cost ZERO tokens on the same chapter, because
#: they produced the same cache key, because they were the same shape.
STRATEGIES: Final[frozenset[str]] = frozenset({BATCHED, SINGLE_CALL, SINGLE_CALL_DELTA})

#: Declared, measured in the POC, NOT yet wired in the worker (it needs a two-stage call
#: flow, not just a different batching). Named here so the name is stable and the intent is
#: recorded — and refused at the boundary until the engine catches up.
PLANNED: Final[frozenset[str]] = frozenset({EDC_CITED})

#: Shapes that issue ONE call carrying every kind. They need a larger output ceiling than
#: the per-batch one, because a single response must hold every kind's entities — which is
#: the very thing `MAX_KINDS_PER_BATCH` was introduced to avoid, so raising the ceiling is
#: part of the shape and not a tuning knob.
SINGLE_CALL_SHAPES: Final[frozenset[str]] = frozenset({SINGLE_CALL, SINGLE_CALL_DELTA})


def plan_batches(strategy: str, extraction_profile: dict, kinds_metadata: list[dict]) -> list[list[str]]:
    """The kind-batching a strategy implies.

    Lives here rather than inline in the worker so it can be tested directly — the worker's
    chapter processor is a 400-line async function against a live pool, and a branch buried
    in it is a branch nothing can red.

    `batched` defers to `plan_kind_batches` (schema-token budget + MAX_KINDS_PER_BATCH).
    The single-call shapes return ONE batch carrying every kind the metadata knows, which
    is precisely what that cap forbids — see the ceiling and retry that make it safe.
    """
    from .extraction_prompt import find_kind, plan_kind_batches

    if strategy in SINGLE_CALL_SHAPES:
        return [[k for k in extraction_profile if find_kind(kinds_metadata, k)]]
    return plan_kind_batches(extraction_profile, kinds_metadata)


def output_ceiling(strategy: str, per_batch: int, single_call: int) -> int:
    """The output cap a strategy needs. A single-call shape must hold every kind's
    entities in one response, so the per-batch cap would truncate it — and a truncated
    response is how the original bug lost an entire batch silently."""
    return single_call if strategy in SINGLE_CALL_SHAPES else per_batch


def normalize(value: object) -> str:
    """Coerce a caller-supplied strategy to the closed set, or raise.

    Unknown values RAISE rather than silently falling back to the default: a typo that
    quietly ran the baseline would make an A/B comparison report "no difference" for a
    reason that has nothing to do with the shapes. That is the silent-no-op failure the
    Frontend-Tool-Contract rules exist to prevent, one layer down.
    """
    s = str(value or "").strip().lower() or BATCHED
    if s in PLANNED:
        raise ValueError(
            f"extraction_strategy {s!r} is measured but NOT YET WIRED in the worker — it "
            f"would silently run as {BATCHED!r}. Available now: {sorted(STRATEGIES)}"
        )
    if s not in STRATEGIES:
        raise ValueError(
            f"unknown extraction_strategy {s!r} — expected one of {sorted(STRATEGIES)}"
        )
    return s


def shape_hash(extraction_profile: dict, strategy: str) -> str:
    """The cache/writeback key component that identifies WHAT a `batch_idx` names.

    Lives here, and is called by the worker, so a test can bind to the real computation.
    A local mirror in the test file would keep passing after the worker stopped folding
    the strategy in — which is exactly what a bite-test of the first version showed.

    The strategy belongs in this hash for the same reason the profile does: it re-maps
    `batch_idx` to a different set of kinds. `batched` batch 0 is three kinds;
    `single_call` batch 0 is all eight. Without it those two collide in the raw-output
    cache, so running one shape over a chapter the other already did returns a HIT and
    serves the three-kind parse as the eight-kind one — five kinds silently gone, zero
    tokens reported. It also makes an A/B between two shapes on one chapter impossible,
    which is the entire purpose of the parameter.
    """
    import hashlib
    import json

    return hashlib.sha256(
        (json.dumps(extraction_profile, sort_keys=True, ensure_ascii=False)
         + "|strategy=" + strategy).encode("utf-8")
    ).hexdigest()
