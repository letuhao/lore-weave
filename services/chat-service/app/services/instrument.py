"""CP-0 · the instrument — the fields that make the runtime claim falsifiable.

Spec: ``docs/specs/2026-08-03-agent-runtime-unification/ARCHITECTURE.md`` §5.

This module owns four recordings and nothing else. It deliberately holds no policy: it does not
decide what to advertise, what to withhold, or when a turn ends. It records what those decisions
were, so that a later question about them has an answer that is not a reconstruction.

**Why it is a module and not four inline dicts.** Each field below exists because a measurement was
attempted against production and found to have no source. Inline dicts drift: the ninth write site
omits a key, and the resulting hole is indistinguishable from a zero. A single constructor per
recording means a missing field is a bug in one place rather than a silent bias in the data.

The design rule this whole file obeys, from §0.3: **a narrowing that does not register is a defect,
not a policy.** Every function here is therefore biased toward recording *too much* — an
`unclassified` row that shows up in a dashboard is a finding; a row that was never written is a
question nobody knows to ask.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Iterable, Literal

logger = logging.getLogger(__name__)

# ── CP-0.3 · where a result came from ──────────────────────────────────────────────────────────
#
# A large share of what the model sees as a tool error is OUR OWN PROSE — a loop breaker, a
# permission refusal, an argument-repair failure — minted by chat-service in the exact
# `{id, tool, ok, result, error}` shape a real tool result uses, with no field marking the
# difference. The model retries what was never retryable and blames the tool.
#
# **The number, stated honestly.** An earlier "65.7%" circulated through this spec with NO
# derivation behind it; the documents that actually measured said 58% / 58.5%. Recomputed against
# `loreweave_chat` by an independent verifier: **57.7% (2,315/4,010)** — and that population is
# itself 57.5% test-harness traffic, so the organic figure is lower again. Any figure quoted here
# must name its query; a number that survives only by being repeated is how the 65.7% got compiled
# into a migration comment in the first place.
#
# ── THE CLASS DEFINITION, AND WHY IT IS `source != 'tool'` ─────────────────────────────────────
#
# Splitting `meta` out of `breaker` is useful for diagnosis and is a TRAP for measurement. The same
# 1,337 `tool_list`/`find_tools` failures that the old runtime counted as tool errors become `meta`
# under this classifier — which moves the class by 33pp on IDENTICAL ROWS. Comparing the new
# runtime's `breaker` rate against the old runtime's blended rate would show a ~41pp improvement
# before a single request is served: not a result, an artefact of redefinition.
#
# So the measured class is **`source != 'tool'`** — everything that was not a real dispatch — and
# `meta` is a REPORTING sub-class within it, never a deduction from it. The baseline must be
# recomputed under this same classifier before any comparison is drawn.
SOURCE_TOOL = "tool"            # a real dispatch ran and this is what it returned
SOURCE_BREAKER = "breaker"      # our code declined, capped, or repaired — no tool ran
SOURCE_META = "meta"            # a runtime primitive answered (discovery, skill load, recall)
SOURCE_UNCLASSIFIED = "unclassified"  # see below — a finding, never a default in disguise

TOOL_CALL_SOURCES = (SOURCE_TOOL, SOURCE_BREAKER, SOURCE_META, SOURCE_UNCLASSIFIED)

# ── CP-0.4 · how a turn ended ──────────────────────────────────────────────────────────────────
#
# Distinct from the provider's `finish_reason`, which answers "why did generation stop" and is
# populated on 9.4% of rows. These answer "what happened to the user's request", and the vocabulary
# is closed so that an unhandled path cannot quietly invent a value.
OUTCOME_COMPLETED = "completed"
OUTCOME_AWAITING_INPUT = "awaiting_input"      # asked the user something — a SUCCESS state (§0.5)
OUTCOME_ABANDONED_BY_USER = "abandoned_by_user"  # cancelled — not a failure, and needs its own state
OUTCOME_FAILED = "failed"
OUTCOME_CRASHED = "crashed"
OUTCOME_INTERRUPTED = "interrupted"            # retained, deprecated — see below

OUTCOMES = (
    OUTCOME_COMPLETED, OUTCOME_AWAITING_INPUT, OUTCOME_ABANDONED_BY_USER,
    OUTCOME_FAILED, OUTCOME_CRASHED, OUTCOME_INTERRUPTED,
)

#: `interrupted` is kept only so the column can represent what the old code wrote. It fuses "the
#: user cancelled" with "we lost the turn", which is why the run's own `interrupted` baseline was
#: uninterpretable: cancellation is not a failure, so a metric containing both cannot move in a
#: meaningful direction. Anything still landing here after CP-0 is a path we failed to classify —
#: a finding about us. **The number to drive to zero.**
OUTCOME_DEPRECATED = frozenset({OUTCOME_INTERRUPTED})

RUNTIME_LEGACY = "legacy"
RUNTIME_AGENTRUNTIME = "agentruntime"


def tool_call_source(chunk: dict) -> str:
    """The source of a recorded call, or ``unclassified`` if nobody said.

    **This is the one place where the fail-safe direction matters most.** Defaulting an unlabelled
    result to ``tool`` would silently re-merge the exact two populations the field exists to
    separate, and it would do so invisibly — the dashboard would show a clean split that is a
    fiction. Defaulting to ``unclassified`` instead makes the gap countable, and a countable gap
    gets closed. An honest ``unknown`` beats a confident wrong answer.
    """
    src = chunk.get("source")
    return src if src in TOOL_CALL_SOURCES else SOURCE_UNCLASSIFIED


def stamp_tool_call(
    chunk: dict,
    *,
    source: str,
    latency_ms: int | None = None,
    declaration: str | None = None,
    runtime_variant: str = RUNTIME_LEGACY,
) -> dict:
    """Attach CP-0.3 and CP-0.7 to one recorded call, in place, and return it.

    ``declaration`` is the identity of the thing that ran — which is **not** always ``chunk["tool"]``
    once consolidation starts, because the point of the migration is that one new declaration
    supersedes several legacy tool names. Recording both is what makes the matched-pair comparison
    possible: the new declaration's calls join against its predecessors' calls in the frozen
    baseline. Without it the run accumulates traffic that cannot answer its own question.
    """
    if source not in TOOL_CALL_SOURCES:
        raise ValueError(f"unknown tool-call source {source!r}; expected one of {TOOL_CALL_SOURCES}")
    chunk["source"] = source
    if latency_ms is not None:
        chunk["latency_ms"] = int(latency_ms)
    chunk["declaration"] = declaration or chunk.get("tool")
    chunk["runtime_variant"] = runtime_variant
    return chunk


#: Runtime primitives — the calls the runtime answers out of its own catalog, with nothing
#: dispatched. This is a CLOSED SET WE OWN, listed by name, not a guess about behaviour: each name
#: is a constant defined in this service. That distinction is what keeps the classifier below from
#: being a heuristic. (Deliberately excludes ``run_subagent``: a subagent dispatches real tools, so
#: it is stamped ``tool`` at its own site.)
RUNTIME_PRIMITIVES = frozenset({
    "find_tools", "tool_list", "tool_load",
    "conversation_search", "chat_search_sessions",
    "load_skill", "workflow_list", "workflow_load",
})


def ensure_tool_call_instrumented(chunk: dict) -> dict:
    """The chokepoint: no recorded call reaches persistence without CP-0.3/0.7 fields.

    Both INSERT paths call this, so adding a mint site cannot quietly produce unlabelled rows.

    **How an unstamped chunk is classified, and why this is not a heuristic.** ``source='tool'`` is
    assigned at exactly one place — the site where a dispatch actually executes — so *having run* is
    a structural fact here, never an inference from the result's shape. Anything arriving unstamped
    therefore did not dispatch, which leaves only two possibilities, and they are separated by a
    closed set of names this service defines. What is explicitly NOT done is matching our breaker
    phrasing against the error text: an earlier measurement had to do that, and it produced a lower
    bound that was then reported as a population count.

    Inferred rows carry ``source_inferred: true`` so an audit can tell a classified row from a
    stamped one — and so that a future real-dispatch site added without a stamp is findable as a
    ``breaker`` row with that flag, rather than silently miscounted forever.
    """
    if chunk.get("source") not in TOOL_CALL_SOURCES:
        name = chunk.get("tool") or ""
        chunk["source"] = SOURCE_META if name in RUNTIME_PRIMITIVES else SOURCE_BREAKER
        chunk["source_inferred"] = True
    # CP-0.3 — `latency_ms` was null on every meta and breaker result, which made the field mean
    # "dispatch latency" rather than "how long this call cost the turn". A `meta` call is not free:
    # `tool_list` and `find_tools` read a 315-tool catalog, and a breaker still costs a model pass
    # to produce and another to react to. Recording 0 for a result our own code minted WITHOUT
    # measuring it would be a fabricated number, so the honest value is an explicit null with a
    # reason — the field then reads as "not measured here", never as "instant".
    if chunk.get("latency_ms") is None:
        chunk["latency_ms"] = None
        chunk.setdefault("latency_unmeasured", chunk["source"])
    chunk.setdefault("declaration", chunk.get("tool"))
    chunk.setdefault("runtime_variant", RUNTIME_LEGACY)
    chunk.setdefault("latency_ms", None)
    return chunk


#: Request-scoped sink for narrowings that happen OUTSIDE the turn function.
#:
#: Threading an explicit ``withheld_sink`` argument failed twice, in the same way both times: the
#: mechanism was built, and the call sites did not pass it. The surface-assembly budget calls live
#: in a *different function* from the recorder — two frames up and before the turn exists — so
#: "just pass the sink" meant editing call sites that a gate reading the wrong file never checked.
#:
#: A ContextVar removes the parameter from the problem. It is inherited by asyncio tasks, so it is
#: naturally per-request, and a NEW narrowing site added anywhere in the call tree registers without
#: anyone remembering to wire it. The failure mode inverts: forgetting now means recording too much,
#: in the wrong turn's bucket, which is loud — rather than recording nothing, which is silent and
#: has now cost three verification rounds.
surface_withheld: ContextVar[list | None] = ContextVar("lw_surface_withheld", default=None)


def record_surface_withheld(tool: str, *, stage: str, reason: str) -> None:
    """Register a narrowing from anywhere in the request, with no plumbing.

    A no-op when nothing has begun a turn (a background job, a test importing the module), which is
    correct: there is no turn for the record to belong to, and inventing one would attribute a
    narrowing to a turn that never saw it.
    """
    sink = surface_withheld.get()
    if sink is None:
        return
    sink.append({"tool": tool, "stage": stage, "reason": reason})


class AdvertisedToolsRecorder:
    """CP-0.1 + CP-0.2 — what the model was offered on each pass, and what was withheld.

    **One entry per model pass, appended, never replaced.** The founding defect of this effort is a
    tool that was offered on pass 1 and silently deleted before pass 2; a recorder that keeps only
    the latest state cannot show it, because the deletion IS the difference between two passes. A
    last-write-wins column would have shown arm E as though the tool had never been offered at all.

    Withholdings accumulate across the turn rather than per pass: the question a withholding answers
    is *"was this reachable at all during this turn, and if not, who decided that"*, and the answer
    must survive a later pass that happens not to consider the tool.
    """

    __slots__ = ("_passes", "_withheld", "_seen")

    def __init__(self) -> None:
        self._passes: list[dict] = []
        self._withheld: list[dict] = []
        self._seen: set[tuple[str, str]] = set()

    def record_pass(
        self,
        names: Iterable[str],
        *,
        tool_choice: str | None = None,
        manifest_revision: str | None = None,
    ) -> None:
        """Record the set actually sent to the model on one pass.

        ``names`` is sorted on the way in. Not cosmetic: the live surface is built from a ``set``
        iterated unsorted, so the wire order changes between restarts — and ``tools`` is the FIRST
        prompt-cache block, so an unstable order invalidates the whole cache downstream of it.
        Sorting here at least makes the *record* comparable between turns; CP-2.3 fixes the surface.
        """
        entry: dict[str, Any] = {
            "pass": len(self._passes) + 1,
            "tool_choice": tool_choice,
            "names": sorted(names),
        }
        entry["count"] = len(entry["names"])
        if manifest_revision is not None:
            entry["manifest_revision"] = manifest_revision
        self._passes.append(entry)

    def record_withheld(self, tool: str, *, stage: str, reason: str) -> None:
        """Register one withholding. ``stage`` is WHO narrowed, ``reason`` is WHY, ``pass`` is WHEN.

        Deduplicated on ``(tool, stage)`` so a tool dropped by the same stage on five passes is one
        withholding rather than five — otherwise the count measures pass depth instead of narrowing.

        **``pass`` is not decoration and its absence was a defect.** A verifier found 19 of 303
        withheld tools *simultaneously advertised on every pass* and had no way to tell whether that
        was a contradiction or a sequence: dropped at activation, then re-added by a later stage, is
        a perfectly coherent history — and indistinguishable from a bug when the record is
        timeless. A narrowing is an EVENT; stamping the pass it happened on is what lets it be
        reconciled against the advertised array instead of merely contradicting it.
        """
        key = (tool, stage)
        if key in self._seen:
            return
        self._seen.add(key)
        self._withheld.append({
            "tool": tool, "stage": stage, "reason": reason,
            # The pass this narrowing APPLIES TO — the one just recorded, not the next one.
            #
            # `len + 1` was off by exactly one, measured live and consistently across five
            # removals: a tool dropped from pass 6 was stamped 7. The drain happens immediately
            # AFTER `record_pass` for the same pass, so by the time this runs the pass it belongs to
            # is already counted. An off-by-one here is not cosmetic — it is what makes a withheld
            # entry look simultaneous with an advertisement it actually preceded, which is precisely
            # the contradiction the field was added to resolve.
            #
            # `max(..., 1)` covers a narrowing decided during surface assembly, before any pass
            # exists: it belongs to the first pass, which is the one it shaped.
            "pass": max(len(self._passes), 1),
        })

    def record_withheld_many(self, tools: Iterable[str], *, stage: str, reason: str) -> None:
        for t in tools:
            self.record_withheld(t, stage=stage, reason=reason)

    @property
    def passes(self) -> list[dict]:
        return self._passes

    @property
    def withheld(self) -> list[dict]:
        return self._withheld

    def advertised_json(self) -> list[dict] | None:
        """The CP-0.1 value, or ``None`` when the model was never given a tool surface at all.

        ``None`` and ``[]`` mean different things and the distinction is load-bearing: ``None`` is a
        turn that never reached the model with tools (a refusal, a crash before the first pass),
        while ``[]`` would claim we offered an empty set — which, per §0.1, is a statement the
        runtime is not allowed to make silently.
        """
        return self._passes or None

    def withheld_json(self) -> list[dict] | None:
        return self._withheld or None


def outcome_for_finish_reason(finish_reason: str | None, *, is_error: bool = False) -> str:
    """Map a legacy ``finish_reason`` onto the CP-0.4 vocabulary.

    A migration shim, not the intended path: the write sites set ``outcome`` directly. This exists
    so that a path nobody updated still lands somewhere honest instead of NULL, and so historical
    rows can be read through one vocabulary.

    Note ``'streaming'`` → ``crashed``. A ``'streaming'`` row is a checkpoint written at a tool
    boundary; if it is still ``'streaming'`` when read, the process died before any terminal handler
    ran. Nothing in this codebase reads those rows back today, which is why process death is one of
    the four ways a turn can end with nobody recording that it did.
    """
    if is_error:
        return OUTCOME_FAILED
    match finish_reason:
        case "stop":
            return OUTCOME_COMPLETED
        case "awaiting_input":
            return OUTCOME_AWAITING_INPUT
        case "error":
            return OUTCOME_FAILED
        case "streaming":
            return OUTCOME_CRASHED
        case "interrupted":
            # Deliberately NOT abandoned_by_user. The old code wrote 'interrupted' for both a user
            # cancel and a lost turn, so the historical value genuinely does not distinguish them.
            # Re-labelling it here would invent a fact about rows that never recorded one.
            return OUTCOME_INTERRUPTED
        case _:
            return OUTCOME_INTERRUPTED


Outcome = Literal[
    "completed", "awaiting_input", "abandoned_by_user", "failed", "crashed", "interrupted",
]
