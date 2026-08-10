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

import json
import logging
import re
from contextvars import ContextVar
from typing import Any, Iterable, Literal
from uuid import uuid4

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
#: Cancelled — not a failure, and it needed its own state because `interrupted` fused "the user
#: changed their mind" with "we lost the turn".
#:
#: 🔴 **MEASURED DEFECT, 2026-08-04: this value reproduces that fusion one layer down.** A verifier
#: opened a second browser tab, the connection dropped, and the turn was recorded
#: `abandoned_by_user` with no user cancel. A deliberate stop and a dead transport both arrive as
#: `CancelledError` and nothing here distinguishes them — so this value currently means "the stream
#: ended from the client side", which is NOT what its name claims.
#:
#: Distinguishing them needs a signal only the client has (an explicit stop, versus a socket that
#: went away). Until that exists, **do not report this as a user-intent metric**; it is a
#: client-side-termination metric wearing a more confident name, and that is exactly the error this
#: whole column was introduced to correct.
OUTCOME_ABANDONED_BY_USER = "abandoned_by_user"
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


def current_runtime_variant() -> str:
    """CP-2.8 — **which arm is serving this process, derived where the arm is DECIDED.**

    🔴 **`legacy` AS A DEFAULT IS FAIL-SAFE IN ONLY ONE DIRECTION, AND THE OTHER ONE IS THE
    MEASUREMENT.** A missing label protects the new arm from **false credit** — an unlabelled row
    never counts as a success for the new runtime. It does **not** protect the new arm's own
    **failure rate**: an unlabelled new-runtime row loses its *numerator* too, and **label-omission
    correlates with crash and cancel**, which are exactly the terminal paths a hand-passed label is
    most likely to miss. The arm would then measure as safer than it is, by construction.

    So the label is not a parameter anyone can pass, forget, or pass wrongly. `stamp_tool_call`
    calls this, and this reads the same setting the route reads. **Five production call sites stamp
    tool calls and not one of them passes a variant** — under a keyword default every one of them
    wrote `legacy` regardless of which arm ran; under this, every one of them is correct with no
    call-site edit at all. That is the difference between *a structural chokepoint covering every
    terminal path* and *the happy path*.

    🔴 **AND IT DOES NOT PERTURB THE CONTROL ARM.** With `agentruntime_arm` off this returns
    `legacy` — the same value the constant wrote — so every existing row is byte-identical. That
    matters because the legacy arm is CP-2's control group (§7), and CP-1.9 established that a
    control moved by a change nobody decided invalidates the comparison before it starts. 2.2 and
    2.3 both declined to touch the control; this one does not have to.
    """
    from app.config import settings

    return RUNTIME_AGENTRUNTIME if settings.agentruntime_arm else RUNTIME_LEGACY


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


#: CP-5.5 — the typed CALL outcome, imported rather than re-declared.
#:
#: 🔴 **NAMED `call_outcome` ON THE CHUNK, NOT `outcome`, ON PURPOSE.** `chat_messages.outcome` is
#: the TURN vocabulary (`completed` · `awaiting_input` · `abandoned_by_user` · `failed` · `crashed`)
#: and this is the CALL vocabulary (`done` · `deferred` · `failed` · …). They overlap only at
#: `failed`, and a query that joined them by name would be comparing two different questions. The
#: distinct key makes that mistake unwritable.
from app.agentruntime.observation import (  # noqa: E402
    ERROR_CLASSES as CALL_ERROR_CLASSES,
    FAILED as CALL_FAILED,
    OUTCOMES as CALL_OUTCOMES,
    UNCLASSIFIABLE as CALL_UNCLASSIFIABLE,
)

CALL_DONE = "done"
#: A call that stopped to ask a HUMAN. Measured 2026-08-10: **every one of the 41 "failures with no
#: message" §1 files under the error contract is one of these** — not one is a tier-R read. They are
#: consumer-local confirm/propose tools, tier `A` writes raising a mutation card, and tier `W`
#: human-confirmed tools, and **38 of the 41 sit in turns the human never came back to**
#: (`abandoned_by_user`). A deferred call is not a failure and must never be counted as one.
CALL_DEFERRED = "deferred"


def stamp_deferred(chunk: dict) -> dict:
    """Mark a call that SUSPENDED awaiting a human. Called at the suspend sites, where the fact is
    structural — never inferred later from the absence of an error, which is what made a suspension
    and a broken tool the same row."""
    chunk["call_outcome"] = CALL_DEFERRED
    return chunk


def stamp_tool_call(
    chunk: dict,
    *,
    source: str,
    latency_ms: int | None = None,
    declaration: str | None = None,
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
    # CP-2.8 — DERIVED, never passed. See `current_runtime_variant`: a label a caller can
    # omit is one that goes missing on exactly the terminal paths that matter.
    chunk["runtime_variant"] = current_runtime_variant()
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


def dedupe_recorded_calls(calls: list[dict]) -> list[dict]:
    """🔴 **NOT WIRED, AND DELIBERATELY SO. It fixes a bug that never existed.**

    I added this after a verifier reported *"18 entries for 17 distinct iterations"* as a
    double-count. Re-measured against the right signature — entries versus distinct CALL IDS — the
    excess is **zero across all 37 rows**, including the flagged one: 18 entries, **18 distinct
    ids**, 17 iterations, because one iteration legitimately carried two calls. The verifier
    retracted it as its own misread.

    So the over-count was never real, and the "fix" could only ever destroy data: my first key
    omitted `args`, collapsing `book_read(chapter=1)` and `book_read(chapter=2)` into one. I
    corrected the key rather than asking whether the function should exist — which is the more
    useful mistake to notice. **A fix for a phantom defect has only downside**: it cannot improve a
    correct record, and every bug in it silently deletes a real one.

    Kept, unwired, with its test, because the *shape* is right if a genuine duplicate is ever
    measured — and because deleting it would erase the record of why it must not be re-wired without
    that measurement first.
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for c in calls:
        # ARGS ARE PART OF THE KEY, and leaving them out was a data-loss bug I shipped while fixing
        # an over-count. Without them `book_read(chapter=1)` and `book_read(chapter=2)` — two real,
        # different calls in one iteration — collapse to one, and the resulting under-count is
        # invisible and moves a failure RATE in the flattering direction, exactly like the
        # over-count it replaced.
        #
        # This repository already contains the correct key 25 lines from where the bug was:
        # `_collapse_identical_tool_calls` keys on (name, canonical args) and explicitly preserves
        # batches of DIFFERENT requests. Same rule here, plus the fields that distinguish a
        # duplicated RECORD from a repeated CALL.
        try:
            _args = json.dumps(c.get("args") or {}, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            _args = repr(c.get("args"))
        key = (
            c.get("iteration"), c.get("tool"), _args,
            c.get("ok"), c.get("source"), str(c.get("error")),
        )
        if key in seen:
            logger.info(
                "CP-0.3: dropping a duplicate recorded call (tool=%s iteration=%s) — same tool, "
                "same outcome, same iteration, different id",
                c.get("tool"), c.get("iteration"),
            )
            continue
        seen.add(key)
        out.append(c)
    return out


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
    # 🔴 One read of `source`, not a `.get` to classify and a `[...]` to stamp. Found by the
    # builder's own pre-commit read-twice sweep rather than by a verifier after the fact: a `chunk`
    # is an ordinary argument here, nothing bounds its type, and a container answering the two reads
    # differently would classify one way and stamp another. This function is instrumentation, so a
    # wrong stamp is not visible anywhere until someone audits the column.
    #
    # 🔴 **AND `tool` WAS READ TWICE IN THIS SAME FUNCTION AND I FIXED ONLY `source`** — the fix
    # went to the read a sweep had named rather than to the pair, which is the flaw six rounds have
    # recorded, committed inside the commit that closed the other half. Driven by a verifier: the
    # row classified `breaker` from `read_file` and stamped `declaration: delete_everything`. One
    # read of each fact, bound to a local, used everywhere below.
    _source = chunk.get("source")
    _tool = chunk.get("tool")
    if _source not in TOOL_CALL_SOURCES:
        name = _tool or ""
        _source = SOURCE_META if name in RUNTIME_PRIMITIVES else SOURCE_BREAKER
        chunk["source"] = _source
        chunk["source_inferred"] = True
    # CP-0.3 — `latency_ms` was null on every meta and breaker result, which made the field mean
    # "dispatch latency" rather than "how long this call cost the turn". A `meta` call is not free:
    # `tool_list` and `find_tools` read a 315-tool catalog, and a breaker still costs a model pass
    # to produce and another to react to. Recording 0 for a result our own code minted WITHOUT
    # measuring it would be a fabricated number, so the honest value is an explicit null with a
    # reason — the field then reads as "not measured here", never as "instant".
    if chunk.get("latency_ms") is None:
        chunk["latency_ms"] = None
        chunk.setdefault("latency_unmeasured", _source)
    chunk.setdefault("declaration", _tool)
    chunk.setdefault("runtime_variant", current_runtime_variant())
    chunk.setdefault("latency_ms", None)

    # ── CP-5.5 · the typed CALL outcome ──────────────────────────────────────────────────────
    # 🔴 **THE ENUM EXISTED AND HAD NEVER BEEN WRITTEN ONCE.** `observation.py` defines this
    # vocabulary and says in its own comment that it *"replaces `ok: bool`"*, because *"ok=true is
    # untyped and means seven different things"*. Measured across 7,990 recorded calls before this
    # landed: `outcome` 0, `error_class` 0. A clause with a subject and no producer — the
    # C-3…C-17 shape, inside the observation module CP-5 exists because of.
    #
    # EXPLICIT AT THE SITE, FAIL-CLOSED HERE. `deferred` is stamped where a call actually suspends
    # (`stamp_deferred`), because *"it stopped to ask a human"* is a structural fact there and an
    # inference here — inferring it from *"failed with no message"* is precisely the conflation
    # this row exists to end, restated as a heuristic.
    _outcome = chunk.get("call_outcome")
    if _outcome not in CALL_OUTCOMES:
        _outcome = CALL_DONE if chunk.get("ok") is True else CALL_FAILED
        chunk["call_outcome"] = _outcome
        chunk["call_outcome_inferred"] = True
    if _outcome == CALL_FAILED:
        # C-7: a failure carries a CLASS. The classes are set where the failure is RAISED, and
        # nothing here reads the error text — V-METRIC proved the best possible regex insufficient
        # over 834 rows. So an unclassified failure gets C-7's own answer for a site that cannot
        # tell: `terminal_permanent`, the FAIL-CLOSED direction, because an unclassifiable failure
        # reading as retryable is what feeds the 74% byte-identical repeat calls.
        if chunk.get("error_class") not in CALL_ERROR_CLASSES:
            chunk["error_class"] = CALL_UNCLASSIFIABLE
            chunk["error_class_inferred"] = True
        # C-7's other half: a failure carries a MESSAGE. This cannot raise — a turn must not die
        # because a raising site was terse — so the residual is made COUNTABLE instead of invisible,
        # which is the only honest option when the fix belongs at a site this code does not own.
        # §1 filed 41 calls as "failures carrying no message at all"; every one turned out to be a
        # suspension, so this field starts life measuring an EMPTY set and the number to watch is
        # whether it stays empty.
        if not str(chunk.get("error") or "").strip():
            chunk["error_message_missing"] = True
    elif chunk.get("error_class") is not None:
        # §4.2 — the error class is a SUB-FIELD of `failed`, not a peer taxonomy. Asking whether a
        # `deferred` call is retryable is a category error, and a field that answers it invites one.
        chunk.pop("error_class", None)
        chunk.pop("error_class_inferred", None)
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
# U-2 · the SCOPE of a narrowing record. P1's shape `{tool, stage, reason, pass}` is
# per-declaration, and a whole-catalogue outage has no single tool — so the record says which
# question it is answering rather than forcing an absent name into a field that must hold one.
SCOPE_DECLARATION = "declaration"
SCOPE_CATALOGUE = "catalogue"
#: A statement about ONE PASS rather than about a declaration — "this pass offered no tools at all".
#: It existed already, spelled `tool: "*"`, which §0.14.3 rejects **by name** because a sentinel makes
#: every consumer that counts tools return a wrong answer while still looking correct. The document
#: forbade the sentinel and the code minted one two thousand lines away.
SCOPE_PASS = "pass"

def _as_text(value) -> str:
    """Whatever it was, as a plain `str` — or `""`.

    Every crash in this recorder's history has been a consumer trusting the shape a producer put in
    the sink: `row["tool"]` when the row had none, an unhashable value reaching a `set`, a
    non-serialisable one reaching `json.dumps` **after** the turn had already succeeded. The sink is
    a plain list any code in the request can append to, so its contents are input, and input is
    coerced at the boundary rather than trusted past it.
    """
    # 🔴 `isinstance` HERE MEANT THE TWO CRASHES THIS FUNCTION'S OWN COMMENT CLAIMED TO CLOSE WERE
    # STILL LIVE: a `str` subclass passes it untouched, and a subclass whose `__hash__` raises then
    # blows the dedupe `set` exactly as before. The whole point of coercing at the boundary is that
    # what comes out is a *plain* `str`, so the check has to be exact — the same identity-vs-equality
    # lesson the membrane learned three rounds ago, in a module that had not been told.
    if type(value) is str:
        return value
    if value is None:
        return ""
    try:
        # `str(value)` returns whatever `__str__` returns, **including a `str` SUBCLASS** — so the
        # unhashable-key crash this function exists to prevent came straight back through its own
        # return. `str.__str__` on the result forces a plain one.
        out = str(value)
        return out if type(out) is str else str.__str__(out)
    except Exception:                                    # noqa: BLE001 — a __str__ that raises
        return f"<unrepresentable {type(value).__name__}>"


surface_withheld: ContextVar[list | None] = ContextVar("lw_surface_withheld", default=None)
#: Whether a CATALOGUE-scope narrowing happened this turn — a fact about the turn, deliberately
#: independent of whether the sink holding its row has since been drained by a persister.
#:
#: 🔴 **I CLAIMED NO ARRANGEMENT OF THIS FACT COULD BE CORRECT WITHOUT A TURN IDENTITY, AND
#: THE COUNTER-EXAMPLE WAS ONE STATEMENT I HAD DELETED MYSELF.**
#:
#: The history, because every step of it looked reasonable from inside:
#:
#:   1. The fact was a flag written HERE by `record_catalogue_unavailable` and DERIVED by
#:      `arm_turn_surface`. Three rounds measured the writer **inert** (every production read
#:      precedes every drain) and one measured it **redundant** (deleting it alone left the flag's
#:      guard test green). Both measurements were correct. **Both were about the state of the tree
#:      at that moment, and I read them as facts about the design.**
#:   2. So the writer was deleted — and deleting it is what made the remaining hole real: with no
#:      writer, a read AFTER a drain has nothing to consult, because the arm derives from a sink the
#:      drain has emptied.
#:   3. Then the fact was moved onto the recorder, which a verifier measured **worse on two
#:      orderings and better on none**.
#:   4. Then I reverted that — to step 2, not to step 1 — and wrote that no arrangement inside this
#:      module could satisfy every ordering. A verifier measured the revert: **worse than the
#:      recorder version on three orderings, worse than the original on four, better than neither on
#:      any.** I called it a revert; it was the worst of the three.
#:
#: **The argument I rested the impossibility claim on was vacuous, and it was my own sentence.** It
#: said *"making the derivation monotone reds two tests, and leaving it lowering keeps the erasure,
#: so no value the arm writes is right in both orders."* That was true in step 1. After step 2 it
#: was not: with the writer gone, **monotone and lowering are the same program**, and a verifier
#: measured the monotone variant reddening **0 of 2255** tests. I carried a justification across a
#: change that had emptied it, and then built a negative existence claim on top.
#:
#: **The arrangement that works is the one that was here before I started:** the write below, plus
#: the derivation at the arm. The write makes the fact survive a drain; the derivation makes it not
#: survive a turn. It needs no turn identity, and it satisfies every ordering measured except one —
#: a turn that records and never calls `arm_turn_surface()` leaks into the next turn in the same
#: context. That one rides the **sink**, not the flag, so no arrangement of this variable addresses
#: it, and the arm-order gate statically forbids the shape that produces it.
#:
#: The transferable part is not about outages. **A measurement is about the tree at the moment it
#: ran.** "Inert" and "redundant" were true of a tree that still had the writer; they stopped being
#: true the instant the writer left, and nothing re-ran them. A claim that something is impossible
#: deserves the same treatment as a claim that something is broken: an execution, not an argument.
catalogue_outage: ContextVar[bool] = ContextVar("lw_catalogue_outage", default=False)


def _sink_for_record() -> list:
    """The turn's sink, **opening one if nobody armed**.

    This is the line that stops ordering from being load-bearing. Eight measured routes walked past
    the ordering gate over three rounds; every one of them ended with a narrowing happening before
    an arming, and every one of them is now harmless, because the narrowing brings its own sink.

    Deliberately NOT `arm_turn_surface`: that name means *"a turn is starting, take a fresh list"*,
    and this means *"a record needs somewhere to go"*. Calling the first from here would let a
    mid-turn narrowing silently replace a sink that already held rows — the discard this whole area
    has been fighting since the sixth recurrence.
    """
    sink = surface_withheld.get()
    if sink is None:
        sink = []
        surface_withheld.set(sink)
    return sink


def arm_turn_surface() -> list[dict]:
    """Open the turn's narrowing sink. **Call this first in a turn entry point, before anything
    that can narrow** — and nothing may arm a second one afterwards.

    🔴 **SEVENTH RECURRENCE OF ARM-AFTER-USE, AND THE FIRST ONE THE RULE ITSELF DID NOT STOP.** The
    sixth was fixed by moving a bare `surface_withheld.set([])` above the stage being repaired, and
    the comment left beside it stated the rule in the imperative: *the sink is armed at the top of
    the turn, not before the stage someone happens to be fixing*. Then U-2 added a narrowing
    **earlier** than that arming — the catalogue fetch — and a verifier measured the result on a real
    turn: `catalog: [] | _catalogue_outage: False`. The arm sat **382 lines below** the fetch that had
    to register into it, in the same function, under the sentence forbidding exactly that.

    **Why a named function and not a better comment.** The arm and the first use were two free-floating
    statements in a 1,600-line generator, so their distance was unbounded and nothing could see it
    grow. A named entry point gives the ordering an anchor a parse tree can find: the gate now
    compares this call's line number against every narrowing call in the same function body, which is
    a fact about the code rather than a substring in a window. What no gate can supply is the reason —
    **a turn's sink must exist before the turn's first decision, because a narrowing that predates its
    sink is not late, it is lost.**

    🔴 **AND THE PREVIOUS FIX CLOSED THE CASE THAT NEVER HAPPENS.** Making a narrowing open its own
    sink was supposed to make ordering irrelevant — but **all eight measured routes are narrowings
    ABOVE an arm**, and this function still *replaced*. So the auto-armed sink was created, filled,
    and then thrown away by the very arming it was meant to survive. Measured: narrow-then-arm gave
    `outage=False, rows=None`; only "an entry point that arms nowhere" — a shape nobody had ever
    reported — was actually fixed.

    Worse, it created a state the old code could not reach: a recorder constructed **before** the arm
    holds the auto-armed list while `catalogue_outage_registered()` reads the replaced one, so the
    persisted row and the model's notice **contradict each other**.

    So arming **ADOPTS**. A sink already present at the top of a turn is that turn's own early
    narrowing — each request runs in its own task and therefore its own context copy, so it cannot be
    a previous turn's. `_emit_chat_turn` has adopted for exactly this reason since CP-0.2; the entry
    points were the ones still replacing.
    """
    sink = surface_withheld.get()
    if sink is None:
        sink = []
        surface_withheld.set(sink)
    # 🔴 **THE FLAG IS DERIVED FROM THE ROWS, NEVER CARRIED.** My first version left it alone when
    # adopting, reasoning that the rows and the flag are the same fact — and they are, which is
    # exactly why the flag must be *computed* from them rather than trusted. Left alone, it outlived
    # its turn: a context that had already served a turn kept `True`, so a later turn inserted the
    # "TOOL CATALOGUE UNAVAILABLE" block with no outage. Two prompt-caching tests caught it by
    # counting system segments — they passed alone and failed in the full run, which is the
    # signature of state leaking between turns rather than of a broken assertion.
    #
    # Production gives each request its own context copy, so this could not have been seen there
    # until it was seen by a user. Deriving costs one pass over a list that is almost always empty.
    # 🔴 THIS READ `isinstance(e, dict) and e.get(...)` — in the commit whose headline was
    # *"`isinstance` was the bug"*. A rogue row then made **`arm_turn_surface` itself raise**, and
    # that is the first statement of every turn entry point: the crash-inside-its-own-fix pattern,
    # fifth occurrence, now at the one place where a failure takes the whole turn with it.
    # 🔴 **THE ASSIGNMENT BELOW IS KNOWN TO BE WRONG IN ONE ORDERING, AND IT IS THE LEAST WRONG OF
    # THE FOUR ARRANGEMENTS MEASURED.** It derives rather than carries, so a re-used context cannot
    # keep a previous turn's answer; it therefore also LOWERS a true flag when an arm follows a
    # drain within one turn. A verifier proved the two properties incompatible on a `ContextVar`
    # (monotone reds two tests, lowering keeps the erasure), and a later one proved that moving the
    # fact onto the recorder is strictly worse. See `catalogue_outage_registered` for the whole
    # measurement and for who owns the real fix.
    catalogue_outage.set(any(_is_catalogue_row(e) for e in list(sink)))
    return sink


def _is_catalogue_row(row) -> bool:
    """Exact type, and no user code on the path — **on the row AND on the value**.

    `dict.get` on a subclass is user code; `type(row) is dict` means the `.get` below is the
    builtin. 🔴 But bounding the row did not bound what the row CONTAINS: a plain dict whose `scope`
    value carries a hostile `__eq__` still ran user code at the `==`, and a verifier made
    `arm_turn_surface` — **the first statement of every turn entry point** — raise on it. Bounding
    the container and not the value is this run's most-repeated shape; `type(v) is str` first means
    the comparison below is `str.__eq__` and cannot dispatch anywhere.
    """
    if type(row) is not dict:
        return False
    v = row.get("scope")
    return type(v) is str and v == SCOPE_CATALOGUE


def record_surface_withheld(tool: str, *, stage: str, reason: str) -> None:
    """Register a narrowing from anywhere in the request, with no plumbing.

    🔴 **THIS USED TO NO-OP WHEN NOTHING HAD ARMED, AND THAT MADE ORDERING LOAD-BEARING.** Three
    rounds of verifiers walked past the ordering gate — a helper one module over, two levels of
    helper, a `_`-prefixed entry point, a class method, `getattr`, `functools.partial`, a
    module-level alias, a name collision — and each time the fix was a better *syntactic* check for
    a *semantic* property. A parse tree cannot decide what a program does, and after the eighth
    route it is the approach that is wrong, not the pattern list.

    So the record no longer depends on somebody having armed first: **if there is no sink, one is
    opened here.** A narrowing cannot be lost to ordering, because the narrowing itself is what
    creates the place to put it. The recorder adopts whatever the ContextVar holds at construction,
    so an auto-armed sink reaches the column exactly as a turn-armed one does.

    In a genuine non-turn (a background job, a test importing the module) this allocates one list
    that nothing drains and the context discards — a cost of nothing against a class of defect that
    has now cost four rounds. The ordering gate stays as a second line, no longer as the only one.
    """
    sink = _sink_for_record()
    sink.append({"scope": SCOPE_DECLARATION, "tool": tool, "stage": stage, "reason": reason})


def record_catalogue_unavailable(*, stage: str, reason: str, count: int | None = None) -> None:
    """U-2 · register the narrowing that has **no tool name** — the source itself was unavailable.

    🔴 **THIS EXISTS BECAUSE P1 WAS FALSIFIABLE AT n=1 AND THIS WAS THE n.** `get_tool_definitions`
    returned `[]` on any exception with only a `logger.warning`, so a gateway hiccup withheld **the
    entire catalogue** and registered nothing — the largest narrowing this system can perform,
    recorded as a log line and treated as a feature.

    **Why not one entry per absent declaration.** That is the literal reading of *"every narrowing
    registers"* and the wrong one twice over: it turns one outage into hundreds of rows saying the
    same thing, **and the names are not knowable** — when the fetch fails there is no list to
    enumerate, so producing one would invent the very thing the outage destroyed.

    **Why not `tool: "*"`.** A sentinel makes every consumer that counts tools return a wrong answer
    while still looking correct, which is worse than an absent record.

    So the record carries a **`scope`**, and this one omits `tool` entirely.

    **`count` is optional, and absent is not zero.** A count exists only when a previous fetch left
    something to compare against; on a cold failure nothing is known, not even the size. `count: 0`
    would claim *we know nothing was there* — a fabrication reached by a default.
    """
    sink = _sink_for_record()
    entry: dict = {"scope": SCOPE_CATALOGUE, "stage": stage, "reason": reason}
    # `type(...) is int` at every door the value can enter by, not only the one a verifier named:
    # `True` is an `int`, so `count=False` persisted as a boolean and `count=True` as a size of 1.
    if type(count) is not int:
        count = None
    if count is not None:
        entry["count"] = count
    sink.append(entry)
    # 🔴 **DELETED FOR THREE ROUNDS ON A MEASUREMENT THAT WAS TRUE AND A CONCLUSION THAT WAS
    # NOT.** The writer was measured *inert* (no production read follows a drain) and *redundant*
    # (the arm recomputes the same fact), and both were correct **of the tree that still had it**.
    # Deleting it is what turned a latent hole into a live one: with no write here, a read after a
    # drain has nothing to consult, because the arm derives from a sink the drain has emptied.
    #
    # It is back, and the ordering it buys is asserted rather than argued — see
    # `catalogue_outage_registered` and `test_THE_OUTAGE_FACT_SURVIVES_A_DRAIN`. "Did a catalogue
    # outage happen this turn" is a fact about the TURN; it must not depend on whether somebody has
    # since moved the rows somewhere else.
    catalogue_outage.set(True)


def catalogue_outage_registered(recorder=None) -> bool:
    """Did a catalogue-scope narrowing get registered this turn?

    🔴 **THE CALLER MUST NOT INFER THIS FROM AN EMPTY CATALOGUE**, and the first version of U-2's fix
    did exactly that (`outage = not catalog`). An empty catalogue and an unavailable one are
    different facts — a user with no permissions legitimately has zero tools — and conflating them
    is the very confusion U-2 exists to end. Three tests caught it by receiving an outage notice on
    a turn that simply had no tools.

    So the outage is read from **the record written by the party that knows it failed**, which is
    also the only source that cannot drift from what the row says.
    """
    # Ask the turn's RECORDER first, not the sink's current contents: the sink is drained by whoever
    # persists it, and a drained sink answers "no outage" for a turn that had one. The recorder is
    # where the drained rows went, so it is the one place the fact cannot be read *before* it exists
    # and cannot survive *after* the turn.
    # 🔴 **THIS FACT HAS BEEN ARRANGED FOUR WAYS AND THE FIRST ONE WAS RIGHT.** The full
    # history is on `catalogue_outage` above; the short version is that a writer measured *inert*
    # was deleted, the fact was then rehoused onto the recorder (measured worse), then "reverted" to
    # the state without the writer (measured worse still — worse than both predecessors on every
    # ordering that discriminates). Restored, and the ordering it exists for is now a test rather
    # than a sentence.
    #
    # Read from the FLAG first, not from the sink's current contents: the sink is drained by whoever
    # persists it, and a drained sink answers "no outage" for a turn that had one — the persisted
    # row saying outage while the model was told nothing, which is worse than either alone.
    # 🔴 **"UNADDRESSABLE BY THIS VARIABLE" WAS REFUTED BY A SIX-LINE PATCH — THE THIRD NEGATIVE
    # CLAIM OF MINE TO FALL, AND THE FIRST WHOSE REFUTATION RUNS.**
    #
    # I argued that `O_K` (arm → record → drain → **arm again** → read) and the two-turn case are
    # *"byte-identically the same execution, so no assignment of the flag can split them."* **The
    # premise is true and the conclusion does not follow.** They are byte-identical *in the
    # ContextVars*. They differ in the object the READER holds: in `O_K` the drained row went into a
    # recorder that is still live; in the two-turn case turn B builds its own. I reasoned about the
    # state I had chosen to look at and concluded about every state.
    #
    # A verifier measured it: flag-only answers **3 of 9** orderings wrong (including an eighth I had
    # not found); consulting the recorder's retained rows answers **8 of 9**, at baseline, with the
    # turn-B row still green. The only survivor is `O_J` — a turn that records and never arms — and
    # that one **is** genuinely sink-borne, which is what this comment said before `O_K` was
    # discovered. **I answered the discovery by widening the excuse instead of narrowing it.**
    #
    # The recorder is passed rather than held in a ContextVar: its lifetime problem was the whole
    # defect of the two earlier attempts, and a caller that has one already knows which turn it is
    # for. `voice_stream_response` constructs it at `:242` and reads here at `:422`, same function.
    # 🔴 **AND THE PARAMETER CREATED A FALSE POSITIVE NOBODY ASSERTED.** It fixes a false NEGATIVE
    # (a drain erasing the turn's outage) and opens a false POSITIVE the flag never had: a recorder
    # that outlived its turn reports THAT turn's outage for THIS one — 228 sequences, measured
    # exhaustively, and the failure is **U-2's founding defect verbatim**: telling a healthy turn its
    # tools are unreachable. My test asserted the *fresh*-recorder case; the **carried** case, which
    # this parameter makes possible for the first time, was the one it never drove. *A fixture chosen
    # for convenience answers a different question* — the third party in this package to earn that
    # sentence, after a verifier and myself.
    #
    # So the door is bounded and the contract is stated instead of assumed: **the recorder must be
    # this turn's**, and the one wired caller (`voice_stream_response`) constructs it and reads it in
    # the same function. `type(...) is` on the argument because five argument types crashed this
    # door from inside prompt assembly — the sixth occurrence of a bound on a container without a
    # bound on what it holds.
    if recorder is not None:
        if type(recorder) is not AdvertisedToolsRecorder:
            raise TypeError(
                f"catalogue_outage_registered(recorder=) got a {type(recorder).__name__}. It reads "
                f"THIS TURN's recorder; anything else is either a crash inside prompt assembly or a "
                f"previous turn's answer reported as this one's."
            )
        if recorder.catalogue_outage():
            return True
    if catalogue_outage.get():
        return True
    sink = surface_withheld.get()
    if not sink:
        return False
    # 🔴 `_is_exactly` HERE TOO — the helper was written three lines above for exactly this and this
    # line was left as a bare `e.get(...)`. A row of `42`, `None` or `"x"` made **the reader raise
    # `AttributeError`**, and the reader is consulted while assembling the system prompt: a
    # malformed row in the sink took the turn down from inside the function that exists to report
    # that something went wrong. The fix went to the site a verifier named and not to the pair.
    return any(_is_catalogue_row(e) for e in list(sink))


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

    __slots__ = ("_passes", "_withheld", "_seen", "_segment", "_sink")

    def __init__(self) -> None:
        self._passes: list[dict] = []
        self._withheld: list[dict] = []
        self._seen: set[tuple[str, str]] = set()
        #: 🔴 **ADOPTED AT CONSTRUCTION, not by a call somebody has to remember.** It was
        #: `bind_sink`, and a gate immediately showed why that is not enough: the arming happens in
        #: `stream_response` and the binding happened in `_emit_chat_turn` — **two functions**, so
        #: the pair could drift exactly as the arm and the drain already had. Deleting either
        #: `bind_sink` call was measured **green**.
        #:
        #: A recorder built inside a turn is a recorder for that turn, and that is knowable here.
        #: `bind_sink` remains for the caller that legitimately owns a different sink (voice builds
        #: its own; tests supply one), but the DEFAULT is no longer a step that can be skipped.
        self._sink: list | None = surface_withheld.get()
        # 🔴 A `_turn_recorder.set(self)` stood here for one round. It was reverted — see
        # `catalogue_outage_registered`. A recorder is a *constructed-object*-lifetime thing and a
        # turn can construct zero, one or two of them, so it was never the turn-lifetime home the
        # docstring claimed.
        # F-48 — the SEGMENT this recorder owns, and it exists because one SQL expression had to
        # satisfy two requirements that pull in opposite directions:
        #
        #   * a RESUME builds a FRESH recorder for the same `message_id`, and must not erase what
        #     the previous one wrote — the founding-defect artefact. That argues for concatenation.
        #   * a MID-TURN CHECKPOINT writes with the SAME recorder that will write again at the
        #     terminal path, and must not duplicate. That argues against concatenation.
        #
        # Unconditional concatenation satisfied the first and broke the second: a 3-pass turn with
        # 2 checkpoints stored 7 entries numbered [1,2,1,2,1,2,3], and `pass 1` then denoted two
        # different sets in one array. The delta-encoding the column exists for — "which tool
        # disappeared between pass N and N+1" — has no answer once the array is non-monotone.
        #
        # Stamping the writer resolves both: a write REPLACES its own segment and touches no other.
        # Re-writing is idempotent; a resume's segment differs, so its entries are appended beside
        # the earlier ones rather than merged into them, and `(segment, pass)` is unique by
        # construction. A random id is deliberate — a counter would need coordination across
        # requests that do not share memory, and guessing a predecessor's count is exactly the kind
        # of assumption this checkpoint has been punished for.
        self._segment: str = uuid4().hex[:12]

    @property
    def segment(self) -> str:
        return self._segment

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
            # F-48 — `pass` is unique only WITHIN a segment. Across a resume the same number is
            # re-issued by a fresh recorder, so any consumer reconstructing the sequence must group
            # by `segment` first. Both are written on every entry so that grouping is possible from
            # the stored value alone, without knowing how the row was assembled.
            "segment": self._segment,
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
        # Deduped per (tool, stage, PASS), not per (tool, stage).
        #
        # First-wins across the whole turn combined with the advertised-set reconciliation below to
        # DELETE A TRUE WITHHOLDING: a tool dropped by a stage on pass 1 but restored (so kept, per
        # the reconciliation) and then genuinely gone on pass 2 recorded nothing at all, because the
        # pass-2 entry was suppressed as a duplicate of the pass-1 one that had already been
        # reconciled away. Two mechanisms each defensible alone, silently destructive together.
        #
        # 🔴 AND IT CHANGES THE SEMANTICS, which an earlier comment here denied. That comment said
        # including the pass "keeps the original intent — a stage dropping a tool on five passes is
        # not five findings". Measured: 1 pass -> 1 entry, 6 -> 6, 10 -> 10. `withheld_tools` now
        # FANS OUT by pass count for every persistent narrowing. That is the correct trade — a
        # per-pass claim must be independently true or false, and turn-level dedupe is what let two
        # mechanisms delete a real withholding between them — but it is a change, not a preservation,
        # and any consumer counting rows is counting pass-instances rather than narrowings.
        key = (tool, stage, len(self._passes))
        if key in self._seen:
            return
        self._seen.add(key)
        self._withheld.append({
            # F-48 — same segment stamp as the advertised entries, for the same reason: the merge
            # replaces a segment's contribution rather than appending it, and without this marker a
            # mid-turn checkpoint multiplied every withholding it had recorded so far (measured at
            # ~215 `domain_not_selected` entries per extra copy).
            "segment": self._segment,
            # 🔴 `scope` was on the SINK's rows and not on the COLUMN's. §0.14.3 specifies a
            # `declaration` row and the column never carried one, so a reader could not tell a
            # per-declaration narrowing from a scope-less legacy row — the distinction the field was
            # added to make. Half a record shape is the same defect as half a consumer.
            "scope": SCOPE_DECLARATION,
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
            # `None` when NO pass has been recorded yet — not `1`.
            #
            # 🔴 ATTRIBUTION CORRECTED. An earlier version of this comment blamed `max(len, 1)`
            # for 145 records "stamped at a pass that does not exist", claiming they were pass 1 on
            # turns that never advertised. **That is false on all three observable properties**: the
            # cited measurement says the 145 are *pass 3 on 2-pass turns*, at stage `token_budget`,
            # i.e. the earlier `len + 1` off-by-one — which was already fixed. I re-attached a true
            # count to the wrong cause and wrote it into the guard, which is the same defect class
            # as the voice literal: an assertion about something I had not checked.
            #
            # What is true, and all that is claimed: `None` is the correct representation when no
            # pass exists, strictly better than fabricating `1`. It is also UNREACHABLE in
            # production today — both call sites run immediately after `record_pass`, so
            # `len(_passes) >= 1` always. It changes no live behaviour and is kept as a correctness
            # floor, not as a fix for an observed defect.
            "pass": len(self._passes) or None,
        })

    def record_catalogue_withheld(self, *, stage: str, reason: str, count: int | None = None) -> None:
        """🔴 **U-2's RECORD HAD NO CONSUMER, AND THE MISSING CONSUMER WAS A CRASH.**

        `record_catalogue_unavailable` deliberately omits `tool` — a catalogue outage has no single
        declaration, and a `"*"` sentinel makes every consumer that counts tools return a wrong
        answer while looking correct. That was the right call and it was made in isolation: the
        drain in `stream_service` reads `_sw["tool"]` unconditionally, so the row this recorder
        was built to carry **raised `KeyError: 'tool'` the moment it arrived.**

        It never arrived, because the sink was armed 382 lines after the fetch. So the fix for
        arm-after-use is what **armed the landmine**: with the sink live, a real editor-surface turn
        and a real resume both ended in `RUN_ERROR "'tool'"` **with the model never called** — a
        degraded catalogue turned from a silent narrowing into a dead turn. A verifier measured
        both, and measured the same turn healthy with the old ordering restored.

        The transferable part: **a record shape and its consumer are one change.** Extending the
        first without the second is not a partial fix, it is a new failure whose severity is decided
        by whichever branch happens to reach it.
        """
        self._record_scoped(SCOPE_CATALOGUE, stage=stage, reason=reason, count=count)

    def record_pass_withheld(self, *, stage: str, reason: str) -> None:
        """A pass that offered NO tools at all — a statement about the pass, not about a declaration.

        🔴 **This shipped as `tool: "*"`, the sentinel §0.14.3 rejects by name**, minted two thousand
        lines from the document that forbids it. The reasoning there is exact and applies here
        unchanged: a sentinel makes every consumer that counts tools return a wrong answer **while
        still looking correct**. So the row says which question it answers and omits `tool`, the same
        way the catalogue row does.
        """
        self._record_scoped(SCOPE_PASS, stage=stage, reason=reason)

    def _record_scoped(self, scope: str, *, stage: str, reason: str, count: int | None = None) -> None:
        # 🔴 TWO KEY NAMESPACES IN ONE `_seen` SET. The per-declaration key is `(tool, stage, pass)`
        # and this one was `(scope, stage, pass)` — and `catalogue` and `pass` are **legal
        # declaration ids**, so a real declaration by either name and a scoped row collide, and
        # whichever arrives first silently suppresses the other. Latent today; a `#` prefix cannot
        # appear in an id, so the two namespaces can no longer meet.
        key = (f"#{scope}", stage, len(self._passes))
        if key in self._seen:
            return
        self._seen.add(key)
        entry: dict = {
            "segment": self._segment,
            "scope": scope, "stage": stage, "reason": reason,
            "pass": len(self._passes) or None,
        }
        # 🔴 `count is not None`, never `count or 0`. Absent and zero are different facts: on a cold
        # failure nothing is known, not even the size, and `0` claims *we know nothing was there*.
        # The guard existed at the recorder's other entry point and not at this one, so an injection
        # writing `count or 0` here was measured **green**.
        # And `type(...) is int` for the third door: `True` is an `int`.
        if type(count) is not int:
            count = None
        if count is not None:
            entry["count"] = count
        self._withheld.append(entry)

    def catalogue_outage(self) -> bool:
        """Did a catalogue-scope narrowing reach THIS recorder? **Retained rows, not the sink.**

        This method existed for one round as the *home* of the turn's outage fact, was measured
        worse than the flag in that role, and was deleted. It is back in a different role: not the
        home, a **second witness**. The flag answers "did this turn record an outage"; this answers
        "did the rows I drained include one", and the two together split the orderings neither can
        split alone — because a drain moves the row from the sink into a specific recorder, and
        *which* recorder the reader holds is the fact both earlier designs threw away.

        `type(...) is str` on the value, one read of it, for the reason `_is_catalogue_row` gives.
        """
        for w in self._withheld:
            v = w.get("scope")
            if type(v) is str and v == SCOPE_CATALOGUE:
                return True
        return False


    def absorb(self, sink: list | None) -> None:
        """Move everything the request-scoped sink holds into this recorder, **by scope**.

        🔴 **THE DISPATCH LIVED AT A CALL SITE, AND THAT CALL SITE WAS UNREACHABLE ON THE TURNS THAT
        MATTERED.** It sat inside `if _adv_ev is not None` — a chunk only `_stream_with_tools` emits
        — so a **tool-free** turn never drained. And a catalogue outage is *precisely what makes a
        turn tool-free*: **the record path was disabled by the event it exists to record.** Measured
        across the four live turn shapes: one wrote the row, three persisted `NULL`.

        So the loop moves here, where the recorder can run it from every path that reads the column,
        rather than staying somewhere a caller has to remember. A record shape and its consumer are
        one change — and *which branch decides whether the consumer runs at all* is part of the
        consumer.
        """
        if not sink:
            return
        # 🔴 `sink = list(sink)` DRAINED THE COPY AND LEFT THE ORIGINAL FULL — so a `list`-subclass
        # sink was never emptied, and a mid-turn checkpoint plus the terminal write absorbed the same
        # rows twice (measured: 1 row became 2). The copy was added to stop a subclass lying about
        # `pop`; it stopped the drain instead. Read defensively, then clear the real container.
        # 🔴 **AND THEN THE READ AND THE CLEAR SHARED ONE `try`, SO A CONTAINER THAT RESISTS `del`
        # DISCARDED ROWS THE READ HAD ALREADY PRODUCED.** The comment said *"read defensively, then
        # clear the real container"*; the code threw the read away when the clear failed. Measured:
        # a tuple, a generator and a `list` subclass forbidding `__delitem__` each gave
        # `withheld_json() = None` against a matched plain-list control that recorded — **a strict
        # behavioural regression against the artifact this replaced**, on inputs that one handled.
        #
        # Two statements, two obligations. A hostile container now degrades to the previous defect
        # (rows recorded twice) rather than to silence, which is the correct direction: a duplicate
        # row is visible and a lost one is not.
        try:
            rows_in = list(sink)
        except Exception:                                    # noqa: BLE001 — a container that resists
            rows_in = []
        try:
            del sink[:]
        except Exception:                                    # noqa: BLE001 — clearing may fail
            pass
        while rows_in:
            row = rows_in.pop(0)
            if type(row) is not dict:
                # `isinstance` again: a `dict` subclass whose `.get` raises took the turn down from
                # inside a recorder. Coerced to a plain dict by reading it defensively — and the
                # SECOND branch that used to stand here was dead code, so a row of `42` recorded
                # `stage: "unknown"` instead of naming what it actually was. One branch now, and it
                # keeps the type in the reason.
                what = type(row).__name__
                try:
                    row = {k: row[k] for k in list(row)} if hasattr(row, "keys") else {}
                except Exception:                            # noqa: BLE001
                    row = {}
                if not row:
                    row = {"stage": "malformed", "reason": f"sink row was {what}"}
            # 🔴 EVERY value is coerced to a plain string before it is used as a key or written.
            # A verifier fed 19 row shapes and **7 still crashed**: an unhashable `stage` blew up
            # the dedupe `set`, an unhashable `tool` blew up the other one, and four more died at
            # `json.dumps` on the write path — i.e. AFTER the turn had already succeeded. A record
            # that can kill the write it belongs to is not instrumentation.
            scope = _as_text(row.get("scope"))
            stage = _as_text(row.get("stage")) or "unknown"
            reason = _as_text(row.get("reason")) or "unrecorded"
            tool = _as_text(row.get("tool"))
            # 🔴 `type(...) is int`, not `isinstance` — **five rounds**. `True` IS an `int` in
            # Python, so `count: false` persisted into the jsonb as a boolean where every reader
            # expects a number, and `count: true` would persist as `1` — a fabricated size for an
            # outage whose whole point is that the size is unknown.
            #
            # This bound is **redundant with `record_catalogue_withheld`'s**, which is the door this
            # line feeds, and it is kept as a defence rather than as a guarantee. Recorded plainly
            # because a red-ability sweep showed weakening it alone leaves the suite green: it is
            # not independently guarded and claiming otherwise would be the vacuity failure this
            # file has a standard about.
            _count_raw = row.get("count")
            count = _count_raw if type(_count_raw) is int else None
            # Scope FIRST, always: `elif row.get("tool")` sat before the fallback, so a new scope
            # that happened to carry a tool was filed as `declaration` and **its scope discarded** —
            # the same one-behind enumeration, in the branch order rather than in the list.
            if scope == SCOPE_CATALOGUE:
                self.record_catalogue_withheld(stage=stage, reason=reason, count=count)
            elif scope == SCOPE_PASS:
                self.record_pass_withheld(stage=stage, reason=reason)
            elif not scope and tool:
                self.record_withheld(tool, stage=stage, reason=reason)
            elif scope == SCOPE_DECLARATION and tool:
                self.record_withheld(tool, stage=stage, reason=reason)
            else:
                # 🔴 **THE `else` READ `row["tool"]` UNCONDITIONALLY — the P0 crash re-created inside
                # the function written to fix it**, and this time on EVERY terminal path, because
                # `withheld_json()` now drains unconditionally. A verifier found it by feeding an
                # unknown scope, which is exactly what the NEXT scope will be before its consumer
                # is written. That is the third time this shape has landed here, so the branch stops
                # trusting the shape: an unrecognised row is recorded as an unrecognised row.
                #
                # Losing it would be worse than a crash was: a crash is loud, and this column exists
                # because silence is the failure being measured.
                self._record_scoped(
                    scope or "unknown",
                    stage=stage,
                    reason=f"{reason} (unrecognised scope {scope!r}; recorded rather than dropped)",
                )



    def bind_sink(self, sink: list | None) -> None:
        """Adopt the turn's sink so `withheld_json()` can drain it **however the turn ends**."""
        self._sink = sink

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
        """The CP-0.2 value, **reconciled against what was actually advertised**.

        A withholding claims *"the model could not see this tool on that pass"*. Three rounds of
        live verification found the same eleven tools recorded as withheld **while advertised on
        every pass** (6.3% → 6.2% → 6.2%, unchanged, the same names each time). No timestamp fixes
        that, because it is not a sequencing error: an intermediate stage genuinely decided to drop
        the tool, and a *later* stage genuinely put it back — the always-hot write allowlist and the
        core set both do this by design. The stage's decision was real; the CLAIM built from it was
        false, because the model could see the tool.

        So the final advertised set wins. A stage's intent is not evidence about what the model
        held; only the wire is. Entries are dropped rather than annotated because a consumer asking
        *"what was hidden from the model?"* must be able to trust the answer without re-deriving it
        — which is the entire reason this column exists rather than a log line.

        **Correction: an earlier version of this docstring claimed the dropped decisions "remain
        visible in the per-stage counters a caller can compute from `passes`". That was false** —
        `passes` entries carry `{pass, tool_choice, names, count}` and no stage or reason, and the
        unreconciled list reaches no INSERT. The decisions are genuinely discarded. Saying otherwise
        was a mitigation I asserted without checking, which is the same error as the number that
        circulated with no derivation behind it.

        What this therefore is: a **narrower, honest** claim. The column answers *"was this tool
        absent from the model's surface on that pass"* — nothing about which stage wanted it gone.
        A future need for per-stage narrowing rates requires a second field, not a reinterpretation
        of this one.
        """
        # Drain FIRST, unconditionally. A turn that never advertised still narrowed — that is what a
        # catalogue outage IS — and reading the column without draining is how three of the four
        # live turn shapes came to persist `NULL` while the sink held the row.
        self.absorb(self._sink)
        if not self._withheld:
            return None
        if not self._passes:
            return self._withheld
        by_pass = {p["pass"]: set(p["names"]) for p in self._passes}
        out = [
            w for w in self._withheld
            # Keep it only if the tool was genuinely absent from the pass it was stamped against.
            # An unknown pass (stamped before any pass was recorded) keeps the entry: absence of
            # evidence is not evidence the tool was visible.
            #
            # 🔴 A CATALOGUE-SCOPE ROW HAS NO `tool` AND THIS EXPRESSION ASSUMED ONE — the second
            # copy of the crash described on `record_catalogue_withheld`. It is also not
            # reconcilable even in principle: reconciliation asks *"was this declaration advertised
            # after all?"*, and an outage is a statement about the whole catalogue, so there is no
            # name to look up. It is always kept.
            # 🔴 **FOURTH RECURRENCE, AND THE LAST TIME IT IS WRITTEN AS A SCOPE LIST.** Every
            # previous fix enumerated the scopes that have no `tool` — and each time a new scope
            # arrived, the enumeration was one behind and the reader crashed. `absorb` now RECORDS
            # an unrecognised scope rather than dropping it, which made this line fail on the very
            # row the fix produces, on every terminal write.
            #
            # The class of defect is "a consumer assumes a key that the producer says is optional".
            # So the consumer stops asking which scope it is and asks **whether the row has a name
            # to reconcile** — which is the actual precondition of reconciliation, and is true of
            # every scope that will ever be added.
            # One read, bound once. The rows here are the recorder's own, so a container that
            # answers twice differently is not constructible — and that is precisely the argument
            # that was made about the sites which later became TOCTOUs. The walrus costs nothing.
            if not (_t := w.get("tool"))
            or _t not in by_pass.get(w.get("pass"), set())
        ]
        return out or None


#: The only non-default `incoming` a caller may pass: a bound placeholder. An SQL fragment
#: from a caller would be an injection point in a helper whose whole job is interpolation.
_INCOMING_PLACEHOLDER = re.compile(r"^\$\d+::jsonb$")


def segment_merge_sql(column: str, *, incoming: str | None = None) -> str:
    """F-48 · the `ON CONFLICT DO UPDATE` expression for a segment-stamped jsonb array.

    **A write replaces its own segment and never touches another's.** Both prior behaviours were
    wrong in opposite directions, and each was introduced as the fix for the other:

    ===============================  ==========================  ==========================
    behaviour                        resume (fresh recorder)     checkpoint (same recorder)
    ===============================  ==========================  ==========================
    ``COALESCE`` / last-write-wins   🔴 ERASES the earlier pass  ✅ correct
    ``||`` unconditional concat      ✅ correct                  🔴 DUPLICATES every pass
    segment-scoped replace (this)    ✅ correct                  ✅ correct
    ===============================  ==========================  ==========================

    The middle row is the one that shipped. It was a real fix for a real erasure — a declined
    confirm card took a row from 2 passes to 1 and destroyed the founding-defect artefact — and it
    broke the other case silently, because a duplicated array still parses, still renders, and still
    looks like a longer version of the truth.

    Three properties this expression holds, each of which the concatenation did not:

    * **idempotent** — writing the same recorder's state N times leaves the array identical to
      writing it once, so the number of checkpoints a turn happens to write cannot change the record;
    * **monotone within a segment** — ``pass`` is strictly increasing per segment, so
      *"what disappeared between pass N and N+1"* has an answer again;
    * **non-destructive across segments** — a resume's entries land beside the earlier ones,
      distinguishable by ``segment`` rather than colliding on a re-issued ``pass`` number.

    Rows written before the segment stamp existed carry no ``segment`` key. ``IS DISTINCT FROM``
    keeps them: a historical entry is never attributed to a segment it predates, so the fix cannot
    retroactively delete data it does not understand. The explicit ``EXCLUDED -> 0 ->> 'segment' IS
    NULL`` branch preserves the old concatenating behaviour for any writer that has not been
    migrated — **fail toward keeping the record**, not toward pruning it.
    """
    if not column.isidentifier():  # defensive: this string is interpolated into SQL
        raise ValueError(f"not a column identifier: {column!r}")
    # 🔴 **F-50, SECOND LAYER — `EXCLUDED` EXISTS ONLY IN AN UPSERT.** This expression was reused
    # verbatim inside a **plain UPDATE** (the CP-0.4 orphan-stamp), where there is no `EXCLUDED`
    # relation at all, so Postgres answered `UndefinedTableError: missing FROM-clause entry for
    # table "excluded"` on **every** execution. It was invisible for the same two reasons the first
    # layer was: the statement is inside a best-effort `except`, and the suite's fake connection
    # accepts any string as SQL.
    #
    # The incoming value is now a **parameter of the expression** rather than an assumption about
    # the statement it lands in. The merge SEMANTICS are untouched — F-48's three properties
    # (idempotent, segment-scoped, order-preserving) are the reason this helper exists, and a second
    # hand-written copy for the UPDATE would be the pair-fixed-at-one-end failure again.
    if incoming is None:
        incoming = f"EXCLUDED.{column}"
    elif not _INCOMING_PLACEHOLDER.match(incoming):
        # Fail closed. This string is interpolated into SQL, so the only alternative to the default
        # is a bound placeholder — never a caller-supplied expression.
        raise ValueError(
            f"incoming must be a bound jsonb placeholder like '$3::jsonb', not {incoming!r}"
        )
    return f"""
                      {column} = CASE
                        WHEN {incoming} IS NULL THEN chat_messages.{column}
                        WHEN chat_messages.{column} IS NULL THEN {incoming}
                        -- An unstamped writer keeps the previous append-only behaviour.
                        WHEN {incoming} -> 0 ->> 'segment' IS NULL
                          THEN chat_messages.{column} || {incoming}
                        ELSE COALESCE((
                               SELECT jsonb_agg(e ORDER BY ord)
                               FROM jsonb_array_elements(chat_messages.{column})
                                    WITH ORDINALITY AS _seg(e, ord)
                               WHERE e ->> 'segment'
                                     IS DISTINCT FROM {incoming} -> 0 ->> 'segment'
                             ), '[]'::jsonb) || {incoming}
                      END"""


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
        # 🔴 F-19. These three are NORMAL terminations that the `case _` fail-safe was sending to
        # `interrupted` — the value this module calls "the number to drive to zero". Anthropic
        # always receives max_tokens, so `length` is a routine truncation, not a lost turn; a
        # turn that stops to call tools has not failed either. Mapping them to the deprecated
        # bucket did not just mislabel: it INFLATED the one metric CP-0 exists to drive down,
        # and it shipped inside my own fix for a different constant.
        #
        # `content_filter` is a real refusal — the request was not carried out — so it is `failed`,
        # not `completed`. Three provider words, three different meanings; the fail-safe collapsed
        # all of them into a fourth.
        case "length" | "tool_calls" | "max_tokens":
            return OUTCOME_COMPLETED
        case "content_filter":
            return OUTCOME_FAILED
        case "interrupted":
            # Deliberately NOT abandoned_by_user. The old code wrote 'interrupted' for both a user
            # cancel and a lost turn, so the historical value genuinely does not distinguish them.
            # Re-labelling it here would invent a fact about rows that never recorded one.
            return OUTCOME_INTERRUPTED
        # 🔴 F-45, and the mechanism is worth more than the line. `resolve_expired_suspends` began
        # writing this value in the SAME COMMIT that taught the class-4 metric about
        # `awaiting_input` — two halves of one fix, each correct alone, cancelling each other:
        # the sweep eliminated the exact state the metric had just learned to read, so every swept
        # row fell through to `unrecorded`, the number CP-0 exists to drive to zero.
        #
        # This shim was the THIRD reader and gave a third answer (`interrupted`, via `case _`), so
        # one row had three verdicts depending on who asked. A value written by one site and known
        # to none of its readers is not a vocabulary extension, it is a fork.
        case "abandoned_expired":
            return OUTCOME_ABANDONED_BY_USER
        case _:
            return OUTCOME_INTERRUPTED


Outcome = Literal[
    "completed", "awaiting_input", "abandoned_by_user", "failed", "crashed", "interrupted",
]

# ── F-45 · the declared `finish_reason` vocabulary ──────────────────────────────────────────────
#
# **F-45 was not a missing branch. It was a missing VOCABULARY.** `resolve_expired_suspends` began
# writing `finish_reason = 'abandoned_expired'` in the same commit that taught the class-4 baseline
# metric to read `finish_reason = 'awaiting_input'`. Each change was correct in isolation and they
# cancelled: the sweep eliminated the only state the metric had just learned to recognise, so every
# swept row fell through to `unrecorded` — the number CP-0 exists to drive to zero. A third reader,
# `outcome_for_finish_reason`, gave a third answer via its `case _` fallback. **One row, three
# readers, three verdicts**, and nothing anywhere said the word was new.
#
# The set below is what makes that recurrence checkable rather than lucky. Split by who produces it,
# because the two halves have different failure modes:
#
#   * PROVIDER values arrive from outside and may grow without warning — the fallback exists for
#     them, and a new one is a mislabelled row, recoverable later from `outcome`.
#   * OURS are written by this codebase. A new one that no reader knows is F-45 again, and a gate
#     asserts that every `finish_reason` literal written under `app/` appears here.
#
# Adding a value to `_OURS` is therefore a deliberate act that fails the build until the readers
# agree — which is the entire difference between extending a vocabulary and forking one.
FINISH_REASONS_PROVIDER = frozenset({
    "stop", "length", "tool_calls", "max_tokens", "content_filter", "error",
})
FINISH_REASONS_OURS = frozenset({
    "streaming",          # a mid-turn checkpoint; terminal handler has not run
    "awaiting_input",     # suspended on a confirm card
    "abandoned_expired",  # the suspend's window closed — written by resolve_expired_suspends
    "interrupted",        # historical: fuses user-cancel with lost-turn, kept for the FE badge
})
KNOWN_FINISH_REASONS = FINISH_REASONS_PROVIDER | FINISH_REASONS_OURS


async def reconcile_crashed_turns(pool, *, older_than_minutes: int = 5) -> dict[str, int]:
    """P3 · the kill path — the one terminal shape a turn cannot record for itself.

    Every other fix in this checkpoint runs INSIDE the turn. A `docker kill` leaves no turn to run
    one: the row stays non-terminal through restart, reload and every later turn, which a verifier
    confirmed over 22 polls. The process that died cannot write its own outcome — but the process
    that STARTS can, and that asymmetry is the whole mechanism.

    Two shapes, both bounded by age so a turn in flight is never touched:

    * an assistant row still at ``finish_reason='streaming'`` — a mid-turn checkpoint whose terminal
      handler never ran. Nothing in this codebase has ever read those rows back, which is why they
      accumulated silently;
    * a user row with **no assistant reply at all** and no outcome — the empty-turn shape, where the
      kill landed before any content existed to checkpoint.

    ``older_than_minutes`` is the safety margin, not a tuning knob: below it a row may belong to a
    live turn, and stamping one would manufacture a crash that did not happen. Erring toward
    stamping late leaves a row briefly unrecorded; erring early **invents a fact**, which is the
    failure mode this checkpoint has committed most often.

    Returns the counts so the caller can log them. **Not silent**: a reconciler that runs and says
    nothing is indistinguishable from one with no callers — which is precisely the state
    ``sweep_expired_runs`` is in, with a docstring claiming it runs periodically and zero callers.
    """
    stamped_assistant = 0
    stamped_user = 0
    try:
        async with pool.acquire() as conn:
            stamped_assistant = await conn.fetchval(
                "WITH t AS (UPDATE chat_messages SET outcome = $1, outcome_source = 'reconciler' "
                "  WHERE role = 'assistant' AND outcome IS NULL "
                "    AND finish_reason = 'streaming' "
                f"    AND created_at < now() - interval '{int(older_than_minutes)} minutes' "
                "  RETURNING 1) SELECT count(*) FROM t",
                OUTCOME_CRASHED,
            ) or 0
            # 🔴 THE USER-ROW BRANCH IS REMOVED, not narrowed. It fired on the largest
            # population and had NO EVIDENCE behind it: `crashed` was a literal over at least five
            # conditions, and the decisive one needs no race at all — `DELETE /v1/chat/{s}/messages
            # /{m}` lets a user delete an assistant reply, after which the preceding user row is
            # stamped `crashed` at the next boot, irreversibly, because nothing re-derives a user
            # row's outcome. A person tidying their history would have been recorded as a crash.
            #
            # It also ignored `branch_id` while the table's key is
            # (session_id, sequence_num, branch_id), so every edit-and-regenerate orphan was masked.
            #
            # I could have added a third guard. But a branch that cannot tell a crash from a
            # deletion is not a narrow branch, it is a guess — and this checkpoint's most expensive
            # defects were all confident values for things never observed. The remaining branch has
            # evidence (`finish_reason='streaming'` is written by exactly one site) and is currently
            # VACUOUS, which is the honest state: it drains the pre-CP-0 backlog once, then stamps
            # nothing, because the dying process now records its own outcome.

    except Exception:  # noqa: BLE001 — startup must never be blocked by reconciliation
        logger.warning("CP-0.4 crash reconciler failed", exc_info=True)
        return {"assistant": 0, "user": 0}
    if stamped_assistant or stamped_user:
        logger.info(
            "CP-0.4 crash reconciler: stamped %d assistant + %d user rows left non-terminal by a "
            "process that died before it could record its own outcome",
            stamped_assistant, stamped_user,
        )
    return {"assistant": stamped_assistant, "user": stamped_user}


async def resolve_expired_suspends(pool) -> int:
    """CP-0.4 · the `awaiting_input` turns that can never receive input.

    Measured: 5 of 8 such rows are unreachable. `load_suspended_run` filters on
    ``expires_at > now()``, so once a run expires the card can never be resumed — while the message
    still advertises ``awaiting_input``, which this module classifies as a SUCCESS state. A turn
    permanently waiting for input that cannot arrive, labelled as one that correctly stopped to ask.

    The evidence is in the data rather than in a guess, which is what separates this from the
    reconciler branch removed for guessing: ``expires_at <= now()`` is a fact the row carries about
    itself. So the outcome moves to ``abandoned_by_user`` — the user was asked and the window closed
    — and ``outcome_source`` marks it as swept, never as the terminal path having recorded it.

    Deliberately does NOT delete the runs. `sweep_expired_runs` in ``db/suspended_runs.py`` does
    that and has **zero callers** despite a docstring claiming it is *"called periodically from the
    lifespan"* — the exact state this checkpoint has now found three times. Deleting the evidence
    before anything reads it is how those rows became unexplainable in the first place.
    """
    try:
        async with pool.acquire() as conn:
            resolved = await conn.fetchval(
                "WITH t AS (UPDATE chat_messages m "
                # F-38 — `finish_reason` MOVES WITH `outcome`. Leaving it at 'awaiting_input'
                # while the outcome says abandoned is the self-contradicting row the lockstep gate
                # exists to reject — and that gate reads only stream_service.py, so it could not
                # see this. A row whose two columns disagree is worse than either being wrong: a
                # reader cannot tell which half to believe, and the published class-4 figure read
                # the WRONG half for 84.6% of that bucket.
                "  SET outcome = $1, outcome_source = 'reconciler', "
                "      finish_reason = 'abandoned_expired' "
                "  WHERE m.finish_reason = 'awaiting_input' "
                "    AND m.outcome IS DISTINCT FROM $1 "
                "    AND EXISTS (SELECT 1 FROM chat_suspended_runs r "
                "                WHERE r.message_id = m.message_id AND r.expires_at <= now()) "
                "  RETURNING 1) SELECT count(*) FROM t",
                OUTCOME_ABANDONED_BY_USER,
            ) or 0
    except Exception:  # noqa: BLE001 — startup must never be blocked
        logger.warning("CP-0.4 expired-suspend resolver failed", exc_info=True)
        return 0
    if resolved:
        logger.info(
            "CP-0.4 expired-suspend resolver: %d turn(s) were advertising 'awaiting_input' with an "
            "expired run — input could never arrive, so they are recorded abandoned_by_user",
            resolved,
        )
    return resolved
