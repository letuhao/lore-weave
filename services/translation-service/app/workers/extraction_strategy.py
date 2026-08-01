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
#: engine does not wire must not be accepted, or it runs as the default and an A/B reports
#: "no difference" from a control compared against itself. That is not hypothetical: before
#: `edc_cited` was wired it was accepted and fell through to `batched`, and the live smoke
#: caught it because both cost ZERO tokens on the same chapter — same cache key, because
#: same shape.
STRATEGIES: Final[frozenset[str]] = frozenset(
    {BATCHED, SINGLE_CALL, SINGLE_CALL_DELTA, EDC_CITED}
)

#: Declared but not yet implemented. Empty today; kept as the mechanism, because the
#: alternative — quietly accepting a name the engine ignores — is the failure above.
PLANNED: Final[frozenset[str]] = frozenset()

#: Shapes whose ONE response carries every kind. They need a larger output ceiling than the
#: per-batch one, because a single response must hold every kind's entities — which is the
#: very thing `MAX_KINDS_PER_BATCH` was introduced to avoid, so raising the ceiling is part
#: of the shape and not a tuning knob. `edc_cited` qualifies: its second stage is one call
#: over all kinds.
ONE_RESPONSE_SHAPES: Final[frozenset[str]] = frozenset(
    {SINGLE_CALL, SINGLE_CALL_DELTA, EDC_CITED}
)
#: Back-compat alias — the older name described the same set before `edc_cited` joined it.
SINGLE_CALL_SHAPES: Final[frozenset[str]] = ONE_RESPONSE_SHAPES

#: Shapes that run a SWEEP first and then type from its citations rather than from the
#: chapter a second time (BOOK_TO_GAME/15 §6b-6c, A9).
TWO_STAGE_SHAPES: Final[frozenset[str]] = frozenset({EDC_CITED})


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

    if strategy in ONE_RESPONSE_SHAPES:
        return [[k for k in extraction_profile if find_kind(kinds_metadata, k)]]
    return plan_kind_batches(extraction_profile, kinds_metadata)


def output_ceiling(strategy: str, per_batch: int, single_call: int) -> int:
    """The output cap a strategy needs. A single-call shape must hold every kind's
    entities in one response, so the per-batch cap would truncate it — and a truncated
    response is how the original bug lost an entire batch silently."""
    return single_call if strategy in ONE_RESPONSE_SHAPES else per_batch


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


def defs_digest(kinds_metadata: list[dict] | None) -> str:
    """A stable digest of the kind + attribute DESCRIPTIONS a run was prompted with.

    They are rendered straight into the prompt — the kind's own line, and
    `- <code> (<type>): <description>` — so editing one changes what comes back. Keying
    only on the profile meant the cache served the pre-edit parse, which is the same
    collision the strategy had, and it made the edit UNMEASURABLE: you cannot re-run a
    chapter to see whether a better definition helped if the answer comes from before you
    wrote it.

    Separated from `shape_hash` because it is the one component that cannot be RECOVERED
    later. The profile is stored verbatim on the job row and the strategy is a column, but
    the descriptions live in glossary and drift; a replay months later would recompute a
    different digest from today's definitions and wrongly call a faithful cache row stale.
    So it is persisted per raw-output row and fed back in — see `compose_shape_hash`.
    """
    import json

    if not kinds_metadata:
        return ""
    return json.dumps(
        [[k.get("code"), k.get("description") or "",
          [[a.get("code"), a.get("description") or "", a.get("auto_fill_prompt") or ""]
           for a in (k.get("attributes") or [])]]
         for k in kinds_metadata],
        sort_keys=True, ensure_ascii=False)


def compose_shape_hash(extraction_profile: dict, strategy: str, defs: str) -> str:
    """The three components, combined. Public so a CONSUMER (replay) can re-derive the key
    from what it can prove — the live profile map, the job's recorded strategy, the row's
    recorded defs digest — instead of mirroring the formula locally."""
    import hashlib
    import json

    return hashlib.sha256(
        (json.dumps(extraction_profile, sort_keys=True, ensure_ascii=False)
         + "|strategy=" + strategy + "|defs=" + defs).encode("utf-8")
    ).hexdigest()


def shape_hash(extraction_profile: dict, strategy: str,
               kinds_metadata: list[dict] | None = None) -> str:
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
    return compose_shape_hash(extraction_profile, strategy, defs_digest(kinds_metadata))


def sweep_shape_hash(sweep_system_prompt: str) -> str:
    """The key component for a STAGE-1 SWEEP row, which is a different question entirely.

    The sweep asks "what named things are mentioned here, quote them" — it is handed no
    kinds, no attributes, no profile. So keying it on the extraction shape hash would bust
    it on every kind-description edit for an answer that cannot change, and re-spend the
    tokens this cache exists to save.

    Instead it is keyed on the ONE input it actually has: the rendered sweep system prompt.
    That is stricter than the batch key in the direction that matters — reword the template
    and the digest moves, where the batch key would keep serving the old parse (which is
    why `always_refresh` exists as an escape hatch at all).
    """
    import hashlib

    return "sweep:" + hashlib.sha256(sweep_system_prompt.encode("utf-8")).hexdigest()


# ── Cache policy (2026-08-01) ────────────────────────────────────────────────
#
# The raw-output cache can serve an entire job at ZERO tokens, and until now that was both
# INVISIBLE and UNCONDITIONAL. Two dimensions of its key were found missing on a single day
# — the extraction strategy, then the kind/attribute descriptions — and each produced the
# same silent failure: a user edits a kind definition, re-extracts, and is served the parse
# from before the edit, with nothing in the UI to say so.
#
# The lesson is not "remember every dimension". It is that the DEFAULT must be correctness
# and the state must be visible. So the default policy REFRESHES when anything the job can
# see has changed, and the caller may opt back into reuse deliberately.

#: Default. Reuse a cached batch only when every dimension the row records still matches —
#: including the model, which the content-addressed key deliberately excludes. Anything else
#: re-extracts.
CACHE_REFRESH_IF_STALE: Final = "refresh_if_stale"
#: Reuse whatever the key matches, model drift included. The old behaviour, now explicit.
CACHE_PREFER_CACHE: Final = "prefer_cache"
#: Ignore the cache entirely and overwrite it. The escape hatch for a change the key cannot
#: see — a reworded prompt template, a provider-side model update, or simple distrust.
CACHE_ALWAYS_REFRESH: Final = "always_refresh"

CACHE_POLICIES: Final[frozenset[str]] = frozenset(
    {CACHE_REFRESH_IF_STALE, CACHE_PREFER_CACHE, CACHE_ALWAYS_REFRESH}
)


def normalize_cache_policy(value: object) -> str:
    """Closed set, and an unknown value RAISES — same reason as `normalize`. A typo that
    quietly fell back would make a run that the caller believed was fresh serve cache."""
    s = str(value or "").strip().lower() or CACHE_REFRESH_IF_STALE
    if s not in CACHE_POLICIES:
        raise ValueError(
            f"unknown cache_policy {s!r} — expected one of {sorted(CACHE_POLICIES)}")
    return s
