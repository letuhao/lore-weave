"""CP-3 · the plan — **the architecture's central claim**, and the carrier the conversation is not.

`ARCHITECTURE.md` §0.11. **This closes the 61.8%.** The model receives `entity_id:019fafa2-…` at
step 12 and sends `"0"` at step 16 because the only carrier between them is the conversation — and
RT3 measured that carrier: a pin-blind `LIMIT 50` window, tool results evicted beyond the newest 3,
arguments dropped entirely by the transcript renderer. **The conversation is a lossy carrier and the
runtime was relying on it to hold identifiers.**

THE PLAN IS TWO OBJECTS, AND THE SPLIT IS THE WHOLE PERMISSION FIX
------------------------------------------------------------------
* **SPEC** — *what we intend*: immutable, versioned, **hashed**. Steps, bindings, `done_when`.
* **STATE** — *what happened*: mutable, **append-only**. Status, emitted values, effects, outcomes.

The approval binds to the SPEC hash; execution never changes it. A revision writes a **new SPEC
version**, and an approval over changed *gated* steps is invalidated while one over changed *ungated*
steps is not (§0.8). That is §0.8's permission-laundering fix, and it works **only** because the two
are split — which is why `Spec` here is frozen and `State` cannot be constructed with a history.

🔴 **THE SPEC IS SESSION-SCOPED AND NEVER A USER ARTIFACT.** The PO rescoped this on 2026-08-05 and
the distinction is easy to lose: *"outside"* in §0.11 means **outside the CONTEXT WINDOW**, not
outside the product. The plan keeps a representation in src — without one there is nothing to
execute, nothing to project, and nothing for `emits`→`accepts` to bind against — but it gets no place
in the user's document library beside planforge and the writing specs. The **hash is load-bearing and
survives**; the document is not.

WHAT THIS MODULE IS NOT
-----------------------
**The plan informs; it never gates.** The tool surface is unchanged by the plan. That is the Ceiling
Test: a strong model writes its own plan or ignores ours, a weak one receives a template as
scaffolding, and *the action space is identical in every case — only the information space changes.*
A `Spec` that could narrow the surface would be the rail this design deletes, so nothing here
returns a tool list.
"""
from __future__ import annotations

import re as _re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from . import canon

#: A step's lifecycle in STATE. **`blocked` is not here and that is deliberate** — a step nothing can
#: run is a plan-level terminal condition (§3.6), not a step status that lets a plan sit forever.
STEP_STATUSES: frozenset[str] = frozenset({"pending", "running", "done", "failed", "skipped"})

#: §0.5's five recovery scopes. `abandoned_by_user` is the one that cannot be inferred from recorded
#: data — CP-0.4 measured that it is **indistinguishable from a dropped transport** without a client
#: signal, and inventing one server-side is the guess this run keeps catching.
RECOVERY_SCOPES: frozenset[str] = frozenset({
    "retry_step", "replan_from_step", "replan_whole", "abandoned_by_user", "escalate_to_human",
})


class PlanError(ValueError):
    """Base for every refusal in this module. A `ValueError`, like `UntrustedRow`, so no caller's
    `except` has to learn a new hierarchy."""


class BindingError(PlanError):
    """C-12 · an `accepts` binding that names something no earlier step emits.

    Carries the locus — step index, parameter, and what WOULD satisfy it — because *"invalid"* is
    not a rejection a caller can act on, and §6.2 makes generation-time detection the whole point:
    *"step n+1 asking for something no earlier step emits is a generation error, not a runtime one."*
    """

    def __init__(self, step_index: int, param: str, reason: str, accepted: str) -> None:
        self.step_index = step_index
        self.param = param
        self.reason = reason
        self.accepted = accepted
        super().__init__(f"steps[{step_index}].accepts.{param}: {reason}. Accepted: {accepted}")


@dataclass(frozen=True, slots=True)
class Binding:
    """One `accepts` parameter, sourced either from an earlier step's `emits` or from a literal.

    🔴 **THE TWO ARMS ARE SEPARATE FIELDS RATHER THAN ONE `value` THAT MIGHT BE A REFERENCE**, and
    that is the difference between this and the string-templating every prior attempt reached for.
    A `"{{step2.entity_id}}"` living in a value field is indistinguishable from a user who typed
    that text, so the executor would have to *guess* which it was — and §0.14 has a standing rule
    about a guess that decides a correctness question. Here the shape says which.
    """

    #: The index of the step whose `emits` supplies this, or None for a literal.
    from_step: int | None
    #: The name in that step's declared `emits`. Required when `from_step` is set.
    from_emit: str | None = None
    #: The literal, when `from_step` is None. Never consulted otherwise.
    literal: object = None

    def __post_init__(self) -> None:
        if self.from_step is None:
            if self.from_emit is not None:
                raise PlanError(
                    "a literal binding carries `from_emit`, so it is neither one thing nor the "
                    "other; a binding is a reference or a literal and the shape must say which")
            return
        if type(self.from_step) is not int or self.from_step < 0:
            raise PlanError(f"from_step is {self.from_step!r}; expected a non-negative step index")
        if type(self.from_emit) is not str or not self.from_emit:
            raise PlanError(
                "a reference binding needs the NAME it takes from that step's declared `emits`. "
                "Binding to a step rather than to a value is how a carry-forward silently picks "
                "whichever field happened to be first.")
        if self.literal is not None:
            raise PlanError(
                "a reference binding also carries a literal, so two sources answer one parameter "
                "and the executor would have to choose. Exactly one source.")


#: One path segment: a key, optionally followed by integer indices — `books`, `books[0]`, `a[0][1]`.
_SEG = _re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])*$")
_INDEX = _re.compile(r"\[(\d+)\]")


class EmitPathError(PlanError):
    """C-12 · an emit path that is malformed, or that finds nothing in the result it is applied to.

    🔴 **A PATH THAT MISSES IS A STEP FAILURE, NEVER A `None`.** Binding `None` forward would hand
    the next step a value that looks supplied and is not — which is `"0"` instead of
    `entity_id:019fafa2-…` wearing a different costume, and it is the precise failure the plan
    exists to remove. The locus names the path, the segment that failed, and what was actually there.
    """

    def __init__(self, path: str, segment: str, reason: str) -> None:
        self.path = path
        self.segment = segment
        self.reason = reason
        super().__init__(f"emit path {path!r} failed at {segment!r}: {reason}")


def check_emit_path(declaration: str, name: str, path: str) -> None:
    """Refuse a malformed path at PLAN-BUILD time. **There is no expression syntax, deliberately.**

    Keys and integer indices only — no wildcards, no slices, no predicates, no `*`. A path that can
    *compute* is a path that can read something it was not handed, and the whole point of declaring
    it is that the plan says exactly one location. `books[0].book_id` is a location;
    `books[?title=~x].book_id` is a program.
    """
    if type(path) is not str or not path:
        raise EmitPathError(str(path), "", (
            f"{declaration} emits {name!r} with no path. The path is REQUIRED: a result carrying "
            f"197 candidates cannot say which one the plan meant"))
    for seg in path.split("."):
        if not _SEG.match(seg):
            raise EmitPathError(path, seg, (
                "expected `key`, `key[0]` or `key[0][1]` — keys and integer indices only, and no "
                "wildcard or predicate syntax exists"))


def extract_emit(result, path: str):
    """The value at `path` in a tool result. Raises `EmitPathError` rather than returning None."""
    cur = result
    for seg in path.split("."):
        key = seg.split("[", 1)[0]
        if not isinstance(cur, dict):
            raise EmitPathError(path, seg, f"expected an object to take {key!r} from, got "
                                           f"{type(cur).__name__}")
        if key not in cur:
            raise EmitPathError(path, seg, f"no key {key!r}; available: {sorted(cur)[:12]}")
        cur = cur[key]
        for idx in (int(i) for i in _INDEX.findall(seg)):
            if not isinstance(cur, list):
                raise EmitPathError(path, seg, f"[{idx}] needs a list, got {type(cur).__name__}")
            if idx >= len(cur):
                raise EmitPathError(path, seg, f"[{idx}] out of range; the list holds {len(cur)}")
            cur = cur[idx]
    if cur is None:
        raise EmitPathError(path, path, (
            "resolved to null. Binding null forward would hand the next step a value that looks "
            "supplied and is not"))
    return cur


@dataclass(frozen=True, slots=True)
class Step:
    """One SPEC step. Immutable — a revision writes a new `Spec`, never an edit in place."""

    #: The declaration this step calls. **A manifest id**, so a plan cannot name a legacy tool.
    declaration: str
    #: The contract generation the declaration was admitted under when the plan was written.
    #: Recorded per §0.11's table so a plan that outlives an amendment is detectable.
    contract_version: str
    #: `param -> Binding`. Everything this step needs, and where each piece comes from.
    accepts: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    #: `name -> path`. What this step's result hands forward (C-6), and **where in the result each
    #: piece is found**. Declared, not discovered, and the PATH is declared too.
    #:
    #: 🔴 **THE PATH IS MANDATORY EVEN WHEN IT LOOKS OBVIOUS** (PO, 2026-08-09). `book_list` emits
    #: `book_id` and returns **197 books** — "which one" is a question the result cannot answer and
    #: the plan must. The rejected alternative was name-matching with a refusal on ambiguity, which
    #: is strictly weaker: it puts a guess one step away from being reachable, and every mechanism
    #: on this board that could guess eventually did. With the path declared there is no ambiguous
    #: case to resolve at runtime, so there is no rule that could be wrong.
    emits: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    #: Step-level completion, derived from this step's own `emits` — *did this step hand forward
    #: what it said it would?* Distinct from the plan-level `done_when` (§0.11's "two levels").
    done_when: str = ""
    #: §0.8's pre-flight answer: does running this step require the principal's assent?
    gated: bool = False

    def __post_init__(self) -> None:
        if type(self.declaration) is not str or not self.declaration:
            raise PlanError(f"declaration is {self.declaration!r}; expected a manifest id")
        if not isinstance(self.emits, Mapping):
            raise PlanError(
                f"{self.declaration} declares emits as {type(self.emits).__name__}; expected a "
                f"mapping of name -> path. A bare list of names cannot say WHERE each value is "
                f"found, and `book_list` returns 197 candidates for one name")
        for name, path in self.emits.items():
            if type(name) is not str or not name:
                raise PlanError(f"emits contains {name!r}; expected non-empty names")
            # The path is validated HERE, at construction, for the same reason `check_bindings` is:
            # a malformed path discovered when the step runs is a failure the plan could not have
            # been built with. §6.2's inversion, applied to extraction.
            check_emit_path(self.declaration, name, path)


@dataclass(frozen=True, slots=True)
class Spec:
    """**What we intend.** Immutable, versioned, hashed. The thing an approval binds to.

    Validation happens in `__post_init__` rather than in a separate `validate()` because a `Spec`
    that exists but has not been checked is exactly the shape M4 replaces — construction IS
    validation, the same rule `Admitted` enforces one module over.
    """

    goal: str
    steps: tuple[Step, ...]
    #: Plan-level completion — *is the GOAL met?*, which is not the conjunction of the step-level
    #: ones. §0.11 keeps them separate because a plan can complete every step and still not have
    #: done the thing the user asked for, and collapsing them hides exactly that case.
    done_when: str = ""
    #: **Template identity by VALUE, not by reference.** `workflows` lives in
    #: `loreweave_agent_registry` and a plan lives beside `chat_messages` in `loreweave_chat` — two
    #: databases, so there is no foreign key to have. Copying also fixes S7-M4: today a rail
    #: re-resolves its slug live every pass, so **editing a template mutates a run in flight**.
    template_id: str = ""
    template_version: str = ""
    #: §0.5 — bounded, because an unbounded replan loop is a plan that never terminates.
    replan_budget: int = 3
    #: Monotonic within a session. A revision is a new version, never an edit.
    version: int = 1

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version < 1:
            raise PlanError(f"version is {self.version!r}; expected a positive integer")
        if type(self.replan_budget) is not int or self.replan_budget < 0:
            raise PlanError(f"replan_budget is {self.replan_budget!r}; expected a non-negative int")
        check_bindings(self.steps)

    def hashed(self) -> str:
        """The SPEC hash. **Over the whole spec**, which is what a revision invalidates."""
        return canon.digest(_spec_payload(self))

    def gated_hash(self) -> str:
        """🔴 **§0.8's ACTUAL REQUIREMENT: the hash over GATED STEPS, not over the whole plan.**

        An approval binds to this. The distinction is the entire permission-laundering fix and it is
        easy to get subtly wrong in the safe-looking direction: hashing the whole spec would
        invalidate an approval whenever ANY step changed, including a prose edit to an ungated one —
        which sounds conservative and is actually the failure, because it trains a user to re-approve
        reflexively. §0.8 says an approval over changed *gated* steps is invalidated and one over
        changed *ungated* steps is **not**.

        The step INDEX is part of the payload, so re-ordering gated steps — or inserting an ungated
        step before one — changes the hash. Position is meaning here: *"approve step 3"* is about
        which call runs third.
        """
        return canon.digest([
            [i, _step_payload(s)] for i, s in enumerate(self.steps) if s.gated
        ])


def _binding_payload(b: Binding) -> dict:
    return {"from_step": b.from_step, "from_emit": b.from_emit,
            "literal": b.literal if b.from_step is None else None}


def _step_payload(s: Step) -> dict:
    return {
        "declaration": s.declaration,
        "contract_version": s.contract_version,
        "accepts": {k: _binding_payload(v) for k, v in sorted(s.accepts.items())},
        # 🔴 The PATH is inside the hash, not only the name. Changing where a value is taken from
        # changes what the step does, so an approval must not survive it (§0.8).
        "emits": {k: v for k, v in sorted(s.emits.items())},
        "done_when": s.done_when,
        "gated": s.gated,
    }


def _spec_payload(spec: Spec) -> dict:
    return {
        "goal": spec.goal,
        "steps": [_step_payload(s) for s in spec.steps],
        "done_when": spec.done_when,
        "template_id": spec.template_id,
        "template_version": spec.template_version,
        "replan_budget": spec.replan_budget,
        "version": spec.version,
    }


def check_bindings(steps: tuple[Step, ...]) -> None:
    """C-6 / §6.2 — **every `accepts` binding must be satisfiable from an EARLIER step's `emits`.**

    *"Step n+1 asking for something no earlier step emits is a generation error, not a runtime
    one."* Checking it here means the plan cannot be built, so the failure is impossible to reach
    at execution — the same inversion M5 makes for manifest members, and for the same reason: a
    reference checked when it is used has a failure mode of *allow*.
    """
    for i, step in enumerate(steps):
        for param, b in sorted(step.accepts.items()):
            if type(b) is not Binding:
                raise BindingError(i, param, f"is a {type(b).__name__}",
                                   "a Binding — a plain value would be a literal nobody declared")
            if b.from_step is None:
                continue
            if b.from_step >= i:
                raise BindingError(
                    i, param,
                    f"reads step {b.from_step}, which does not run before this one",
                    f"a step index below {i}; a plan is ordered, and a binding to a later step is "
                    f"a cycle the executor would resolve to nothing")
            emits = steps[b.from_step].emits
            if b.from_emit not in emits:
                raise BindingError(
                    i, param,
                    f"reads {b.from_emit!r} from step {b.from_step} "
                    f"({steps[b.from_step].declaration}), which does not declare it",
                    f"one of {list(emits)}" if emits else
                    f"nothing — step {b.from_step} declares no `emits` at all, so no later step "
                    f"can carry anything forward from it")


#: The event kinds STATE is built from. **Append-only**: replay reconstructs, nothing is mutated.
#:
#: §0.11's second adjustment, corroborated by the external survey: *"STATE is event-sourced, not
#: snapshotted. §0.5's replan input is what has already COMMITTED, and an event history answers that
#: natively while a snapshot does not."* Temporal's model — replay to reconstruct, resume at the
#: failed step without re-running completed work.
#:
#: 🔴 **AND THE WRITE HALF ALREADY EXISTS IN THIS REPOSITORY.** Turns checkpoint per tool call at
#: `finish_reason='streaming'` and **nothing ever reads a `'streaming'` row back** (S3-M6). The
#: events are produced and discarded; only recovery is missing. That is why this is a small
#: mechanism rather than a new subsystem.
EVENT_KINDS: frozenset[str] = frozenset({
    "step_started", "step_emitted", "step_failed", "step_skipped", "effect_committed", "replanned",
})


@dataclass(frozen=True, slots=True)
class Event:
    """One append-only fact about what happened. Immutable by construction."""

    kind: str
    step_index: int
    #: For `step_emitted`: the ACTUAL values, keyed by the step's declared `emits` names. These are
    #: the identifiers §0.11 forbids compressing — they are the whole reason STATE exists.
    values: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    #: For `step_failed`: C-7's error class, the enum CP-2.6 built.
    error_class: str | None = None
    #: For `effect_committed`: how to undo it, and whether it actually landed.
    undo_hint: str = ""
    committed: bool = False

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise PlanError(f"unknown event kind {self.kind!r}; one of {sorted(EVENT_KINDS)}")
        if type(self.step_index) is not int or self.step_index < 0:
            raise PlanError(f"step_index is {self.step_index!r}; expected a non-negative index")
        if self.kind == "step_failed" and not self.error_class:
            raise PlanError(
                "a step_failed event carries no error_class. C-7 classifies at the point of "
                "failure, and unclassifiable is `terminal_permanent` rather than absent — a "
                "failure nobody classified is one recovery cannot act on (§0.5).")
        if self.kind == "step_emitted" and not self.values:
            raise PlanError(
                "a step_emitted event carries no values. The event exists to record what was handed "
                "forward; an empty one says a step completed while destroying the only thing a "
                "later step can bind to.")


class State:
    """**What happened.** Append-only, and the executor is its only writer.

    🔴 **THE HISTORY CANNOT BE SUPPLIED AT CONSTRUCTION**, which is what keeps *"one writer during
    execution"* true. A `State(events=[...])` would let a caller manufacture a past — including an
    `effect_committed` for something that never ran, which is precisely the input §0.5 feeds to a
    replan. Events arrive one at a time through `append`, or by `replay` of a recorded history, and
    `replay` is a classmethod so the two paths are visibly different at every call site.
    """

    __slots__ = ("_events", "_spec_hash")

    def __init__(self, spec_hash: str) -> None:
        if type(spec_hash) is not str or not spec_hash:
            raise PlanError("State is bound to a SPEC hash; without one it describes no plan")
        self._spec_hash = spec_hash
        self._events: list[Event] = []

    @classmethod
    def replay(cls, spec_hash: str, events) -> "State":
        """Reconstruct from a recorded history — the recovery path, and the only bulk entry."""
        st = cls(spec_hash)
        for e in events:
            st.append(e)
        return st

    @property
    def spec_hash(self) -> str:
        return self._spec_hash

    @property
    def events(self) -> tuple:
        """A tuple, so a caller cannot append behind the guard in `append`."""
        return tuple(self._events)

    def append(self, event: Event) -> None:
        if type(event) is not Event:
            raise PlanError(
                f"{type(event).__name__} is not an Event. STATE is the record recovery replays; a "
                f"duck type here is a fact nobody validated.")
        self._events.append(event)

    def emitted(self) -> dict:
        """`step_index -> {name: value}` — every value handed forward so far.

        Later events win for the same (step, name): a retried step's second emission is the current
        truth, and §0.5's `retry_step` scope depends on that rather than on the first write sticking.
        """
        out: dict = {}
        for e in self._events:
            if e.kind == "step_emitted":
                out.setdefault(e.step_index, {}).update(dict(e.values))
        return out

    def status_of(self, step_index: int) -> str:
        """The current status of one step, DERIVED from the history rather than stored.

        Stored status and an event log are two records of one fact, and this run has a standard
        about what happens when they disagree.
        """
        status = "pending"
        for e in self._events:
            if e.step_index != step_index:
                continue
            if e.kind == "step_started":
                status = "running"
            elif e.kind == "step_emitted":
                status = "done"
            elif e.kind == "step_failed":
                status = "failed"
            elif e.kind == "step_skipped":
                status = "skipped"
        return status

    def committed_effects(self) -> tuple:
        """§0.5's replan input: *what has already committed.* An event history answers this
        natively; a snapshot cannot, which is why STATE is event-sourced."""
        return tuple(e for e in self._events
                     if e.kind == "effect_committed" and e.committed)


def resolve_arguments(spec: Spec, state: State, step_index: int) -> dict:
    """**3.4 — bind `emits` → `accepts` DIRECTLY, instead of asking the model to retype a UUID.**

    This is the one part of the design with no prior art in Dify, in the 584-tool routing paper, or
    in any surveyed system, and it is where the 61.8% is closed. The model received
    `entity_id:019fafa2-…` at step 12 and sent `"0"` at step 16 because the only carrier between
    them was the conversation — a pin-blind `LIMIT 50` window that evicts tool results beyond the
    newest 3 and drops arguments entirely in the transcript renderer.

    The plan is a *good* carrier: small, structured, cheap to re-present. So the executor does not
    ask. It looks the value up and passes it.

    🔴 **A MISSING VALUE IS A REFUSAL, NOT A FALLBACK TO ASKING THE MODEL.** Degrading to *"let the
    model supply it"* would reintroduce the exact failure — silently, and only under the conditions
    where the carrier had already failed, which is the worst possible moment to change behaviour.
    `check_bindings` has already proved the binding *satisfiable*; if the value is absent at
    execution then the producing step has not run or has not emitted, and that is a recovery
    decision (§0.5), not an argument to guess.
    """
    step = spec.steps[step_index]
    emitted = state.emitted()
    args: dict = {}
    for param, b in sorted(step.accepts.items()):
        if b.from_step is None:
            args[param] = b.literal
            continue
        produced = emitted.get(b.from_step, {})
        if b.from_emit not in produced:
            raise BindingError(
                step_index, param,
                f"step {b.from_step} ({spec.steps[b.from_step].declaration}) has not emitted "
                f"{b.from_emit!r} — its status is {state.status_of(b.from_step)!r}",
                f"a completed step {b.from_step}. The value is NOT requested from the model as a "
                f"fallback: that is the carry-forward failure this mechanism exists to close, and "
                f"asking would reintroduce it exactly when the carrier has already failed")
        args[param] = produced[b.from_emit]
    return args


# ── 3.7 · the permission pre-flight ──────────────────────────────────────────────────────────────

def preflight_gates(spec: Spec) -> tuple[int, ...]:
    """**Every gated step, decided at PLAN time — because every input is static then.**

    §0.8. The pre-flight is possible at all only because `check_bindings` has already proved each
    binding satisfiable: a gated step's arguments are either literals in the SPEC or values an
    earlier step is *declared* to emit, so *"what will this step do"* is answerable before anything
    runs. That is what lets a human approve once, up front, instead of being interrupted mid-plan
    with a question they cannot evaluate because they cannot see what follows.

    🔴 **A GATED STEP WHOSE ARGUMENTS ARE NOT DETERMINABLE CANNOT BE PRE-FLIGHTED, AND THAT IS A
    REFUSAL.** The tempting alternative — approve it now and resolve the arguments later — is
    precisely §0.8's permission laundering: assent given against one description, spent on another.
    """
    # 🔴 **THIS FUNCTION USED TO RE-CHECK `b.from_step >= i` AND RAISE, AND THAT BRANCH WAS DEAD.**
    # `Spec.__post_init__` runs `check_bindings`, which refuses a forward reference before a `Spec`
    # can exist — so the raise could not fire for any argument this function can be given. The
    # census found it as an unguarded refusal, which is exactly the right signal: this repository
    # has already deleted two `except` clauses for the same reason (*"an except that cannot fire is
    # not a refusal, so they were deleted from the source rather than carried as debt"*), and
    # carrying a dead raise makes the next reader believe a door exists here.
    #
    # What remains true is stated rather than re-checked: the pre-flight is answerable at plan time
    # BECAUSE construction already proved every binding resolvable, by induction over an ordered
    # plan. The concrete failure — a producing step that is skipped at runtime — is not this
    # function's to catch; `resolve_arguments` refuses it there, where it can actually happen.
    return tuple(i for i, s in enumerate(spec.steps) if s.gated)


# ── 3.5 · recovery, and 3.6 · the four silent exits as ONE mechanism ─────────────────────────────

@dataclass(frozen=True, slots=True)
class Termination:
    """**A plan that ends anywhere but `done_when` names what is live and hands it to a human.**

    §3's four silent exits are one rule, not four:

    | # | silent exit | what made it silent |
    |---|---|---|
    | 1 | effects committed, then a failure with no ledger | `undo_hint` read only by the FE |
    | 2 | `needs-human` never answered | **`sweep_expired_runs` has ZERO callers**, and its docstring claims it runs periodically |
    | 3 | process death mid-plan | turns checkpoint at `finish_reason='streaming'` and **nothing ever reads a `'streaming'` row back** |
    | 4 | user cancels | no scope at all; badged `interrupted`, which §0.5 calls a defect |

    Every one of them is *the plan ended somewhere other than `done_when` and nobody was told*. So
    the mechanism is a single required record rather than four detectors — a detector per exit is
    four things to forget, and #2 and #3 are already proof that a mechanism nobody calls is
    indistinguishable from one that does not exist.

    🔴 **`live_effects` IS REQUIRED AND MAY BE EMPTY, WHICH ARE DIFFERENT CLAIMS.** An empty tuple
    says *nothing is outstanding*; an absent field says *nobody looked*. Exit #1 is exactly the
    second being mistaken for the first, so there is no default here — a caller must state it.
    """

    #: Which of §0.5's scopes this end falls under, or `done_when` for a plan that finished.
    scope: str
    #: The step the plan stopped at.
    step_index: int
    #: What is COMMITTED and still standing. `()` means nothing outstanding; there is no "unknown".
    live_effects: tuple
    #: What a person is being asked to do. Not a status string — exits #2 and #4 became silent
    #: precisely because a status was recorded and no action was named.
    hand_to_human: str
    #: C-7's class when the end was a failure. `None` for `done_when` and `abandoned_by_user`.
    error_class: str | None = None

    def __post_init__(self) -> None:
        if self.scope != "done_when" and self.scope not in RECOVERY_SCOPES:
            raise PlanError(
                f"unknown termination scope {self.scope!r}; one of "
                f"{sorted(RECOVERY_SCOPES | {'done_when'})}")
        if type(self.live_effects) is not tuple:
            raise PlanError(
                f"live_effects is a {type(self.live_effects).__name__}; it must be a tuple, and an "
                f"EMPTY one is a real answer. 'Nothing is outstanding' and 'nobody looked' are the "
                f"difference between silent exit #1 and a closed plan.")
        if self.scope != "done_when" and not self.hand_to_human:
            raise PlanError(
                f"a plan ending in {self.scope!r} names nobody to hand it to. §3: a plan that ends "
                f"anywhere but done_when must name what is live AND hand it to a human — a "
                f"recorded status with no action is how exits #2 and #4 stayed silent.")


def terminate(state: State, scope: str, step_index: int, *,
              hand_to_human: str = "", error_class: str | None = None) -> Termination:
    """Close a plan, **reading the live effects out of STATE rather than taking them on trust.**

    This is why STATE is event-sourced. §0.5's replan input is *"what has already committed"*, and
    an event history answers it natively — a snapshot would have to be kept correct by whoever
    wrote it, which is silent exit #1 with an extra step.
    """
    return Termination(
        scope=scope,
        step_index=step_index,
        live_effects=state.committed_effects(),
        hand_to_human=hand_to_human,
        error_class=error_class,
    )


def re_runnable(spec: Spec, state: State, step_index: int) -> bool:
    """**C-13 — asked BEFORE any automatic re-run, never after.**

    A step that committed an effect is not re-runnable by the runtime on its own initiative: the
    second run would duplicate whatever the first one did, and the ledger is the only record that it
    happened at all. `retry_step` is available to a HUMAN who has seen the ledger; it is not
    available to a loop.

    Returns a bool rather than raising because the caller's next move differs by scope — retry,
    replan, or hand it over — and collapsing three outcomes into one exception would make the
    difference invisible at the call site.
    """
    if step_index < 0 or step_index >= len(spec.steps):
        raise PlanError(f"step {step_index} is not in a plan of {len(spec.steps)} steps")
    return not any(e.step_index == step_index for e in state.committed_effects())
