"""CP-2.5 · P5 — the four fields, and no path that omits them.

Spec: ``ARCHITECTURE.md`` §5 (four fields, not five), §0.5 (what a guardrail is for), §0.14.3
(the `scope` of a withholding record). Checkpoint: RUNSTATE → L2 · CP-2.5.

**P5 failed as a retrofit for eleven consecutive rounds and it is not being retried here.** On the
legacy runtime *"every terminal path records"* is a claim about six INSERT sites, thirty mint sites
and five producers; eight fixes were attempted, each correct at the layer it named and blind to the
next. `finish_reason` covers **9.4%** of turns today.

So the property is not enforced, it is made **inexpressible**: an `Observation` has four required
fields and no defaults, so a path that omits one does not produce a partial record — it does not
produce an `Observation` at all, and it cannot end a turn. The same construction argument as M2 and
`Admitted[D]`.

WHAT IS DELIBERATELY NOT HERE
------------------------------
* **The wrong-object counter is not a P5 field** (§5, §0.6): *a counter without a detector ships
  reading zero.* Only substitution-shaped cases are detectable at the call, and the 61.8%
  carry-forward class is detectable only from plan-binding state — so its detector belongs with the
  plan (§0.11) and P5 merely carries the output when there is one.
* **`manifest_revision` is not here either** (CP-1.8): hashing an empty manifest is a
  constant-valued column at every write, which is the exact P4 violation CP-1 repaired.

WHAT CP-2.6's ENUM DOES **NOT** SETTLE
--------------------------------------
V-METRIC's overturn condition for class 3 is *"a structured `tool_calls[].error_class` written by
**all five producers** against one enum"*. This module gives one enum and one arm. **Four of the
five producers are in the legacy arm**, and §7 forbids editing it mid-run — it is not tolerated
legacy, it is the **control group**, and the sentence CP-2 exists to test is *"the new runtime
performs better than the old"*. Retrofitting the old arm's instrument would remove the thing the
new one is compared against.

So the honest statement of what shipped: class 3 is **scoreable in the NEW ARM ONLY**. A cross-arm
delta remains uninterpretable for class 2's reason exactly — a baseline derived from error prose
and a new arm classified at the raise site are **two different instruments**, and a difference
between them measures the instruments. The ruling stands; what changes is that the new arm is no
longer the half that cannot be measured.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .canon import digest

#: §5 field 3 — `source` on every result. **58–66% of what the model sees as an error is our own
#: prose**, and until this exists that fraction of the signal is uninterpretable.
SOURCES = ("tool", "breaker", "meta")

#: C-14's typed outcome, which replaces `ok: bool`. **`ok=true` is untyped and means seven
#: different things**: 358 refusals rode the success channel, 400 empty results had four
#: indistinguishable causes, 430 results were silently truncated.
OUTCOMES = (
    "done", "partial", "empty", "ambiguous", "refused",
    "degraded", "deferred", "failed", "unknown_effect",
)

#: The outcome C-7 refines. Named once so the invariant below and its guards read the same symbol
#: rather than two copies of a string that can drift apart.
FAILED = "failed"

#: C-7's error contract (ARCHITECTURE.md §4.2, C-7 row) — **four classes set WHERE THE FAILURE IS
#: RAISED**, plus one this run's V-METRIC ruling demands by name.
#:
#: 🔴 **THIS IS THE ENUM THAT OVERTURNS A RULING, AND ONLY BECAUSE IT IS AN ENUM.** V-METRIC spent
#: four rounds on class 3 and ended by proving *its own* predicate insufficient: `R7-8` reached
#: perfect precision and recall on 834 rows and still could not leave the corpus, three ways — 158
#: rows rested on fitted product sentences, a mid-corpus rename moved the metric by 33 rows
#: invisibly, and 239 rows sit behind a deliberate anti-oracle. Its words: *"Not by a better regex —
#: I have now demonstrated that the best possible regex is insufficient."* So this is not a
#: classifier. Nothing here reads an error message.
#:
#: `unresolved_or_forbidden` is **not** a fifth class someone thought would be handy: it is the
#: exact remedy the ruling names — `jobs_skill.py` and `mcp_server.go` merge *"doesn't exist"* with
#: *"not yours"* **on purpose**, and a taxonomy without this member forces that blend into one of
#: the other four, which is the hiding the ruling refuses. It admits the merge instead.
ERROR_CLASSES = (
    "retryable_transient",
    "retryable_modified",
    "terminal_permanent",
    "terminal_budget",
    "unresolved_or_forbidden",
)

#: C-7: *"a wrapper that cannot classify returns `terminal_permanent`"* — the **fail-closed**
#: direction. An unclassifiable failure must not read as retryable, because the measured behaviour
#: this whole run exists to change is **74% byte-identical repeat calls**.
UNCLASSIFIABLE = "terminal_permanent"


def prompt_hash(prompt: str) -> str:
    """CP-2.9 — the digest of what was actually sent. **Chat-service-local, and that is the item.**

    It closes a **currently undetectable** failure: a prompt can change today and nothing notices.
    No column answers *"was this turn assembled from the same instructions as that one"*, so a
    regression caused by an edited system prompt is indistinguishable from a model getting worse.

    **Normalised to NFC**, for the reason §0.14.2 gives: two byte-sequences that render identically
    must not produce two digests. The repository has a measured 1.44× NFD/NFC token swing, so a
    prompt that round-trips through a normalising editor would otherwise read as *changed* on every
    turn and the column would be noise from the day it shipped.

    🔴 **AND THE NORMALISATION IS `canon._norm`'s, NOT THIS FUNCTION'S.** The first version wrote
    `digest(nfc(prompt))` and the docstring called that call load-bearing. **It was not**: `digest`
    already normalises every string it walks, so the falsifier that removed the `nfc(...)` left the
    guard GREEN — *"the guard requires nothing"* — and the runner said so. The redundant call is
    gone and the claim is corrected to name the place the property actually lives, which is also
    where its falsifier now points.

    🔴 **THREE THINGS ARE NOT HERE, EACH FOR A MEASURED REASON** (RUNSTATE 2.9), because the first
    draft of this row bundled four and red team killed three:

    * **`code_revision`** — `GIT_SHA` became an **OCI image label**; no Dockerfile consumes it, so
      `os.environ.get("GIT_SHA")` is `None` in **every** scenario. A column that is null everywhere
      is P4's constant with extra steps.
    * **`seed`** — it is **already forwarded** (`adapters.go:678`); the three typed hops above it
      drop it; production runs `temperature=0.0`, so a greedy decode consumes no randomness; and
      Anthropic has no seed parameter at all.
    * **`block_hashes`** — **cannot be computed correctly here.** The cache breakpoint is owned by
      provider-registry *after* a schema translation, so a chat-service hash can be green while the
      cached bytes changed. A hash that can be right for the wrong reason is worse than none.
    """
    return digest(prompt)


class NotObservable(ValueError):
    """A turn that cannot be recorded honestly. Raised rather than defaulted.

    Every field this refuses has a plausible default — `source="tool"`, `outcome="done"`,
    `advertised=()` — and every one of those defaults is a **constant written at a write
    boundary**, which is P4's violation exactly. A record that guesses is worse than a missing one:
    it is a missing one that counts.
    """


@dataclass(frozen=True, slots=True)
class Guardrail:
    """§0.5's guardrail, in its **v1 shadow arm**: evaluate, record, **do not act**.

    🔴 **PROPERTY 3 IS UNOBSERVABLE IF THE GUARDRAIL BLOCKS**, which is why the shadow arm is v1
    and not v2. The property is *"a strong model reaches the transition before the guardrail
    fires"*, and it is measurable only as **fire-rate falling toward zero as model strength
    rises**. A guardrail that acts destroys its own denominator: the turns where the model would
    have recovered on its own never happen, so the rate it produces is about the guardrail rather
    than about the model. *If it does not fall, we built a ceiling and mislabelled it* — and that
    sentence cannot be tested at all once the ceiling is in place.

    `acted` exists as a field rather than as a comment because **an invariant that is only
    documented is one this run has watched fail eleven times.** It is refused at construction, so
    "do not act" is not a rule someone must remember at the moment they are most sure the guardrail
    is right.

    `evidence` is required and must be **deterministic** (§0.5 property 1: an identical call
    repeated, a budget spent) — never a judgement about whether the model *seems* confused. A
    guardrail that fires on a judgement is the sixth breaker with a new name.
    """

    fired: bool
    evidence: str
    #: What it WOULD have proposed. §0.5: *a guardrail's output must be a PLAN STATE TRANSITION,
    #: not a stop.* Recorded even in the shadow arm, because the thing being measured is whether a
    #: strong model reached this transition first — and that comparison needs the transition.
    transition: str
    acted: bool = False

    def __post_init__(self) -> None:
        if self.acted:
            raise NotObservable(
                "the guardrail acted. v1 is a SHADOW ARM (§0.5): it evaluates, it records, and it "
                "does not act — because property 3 (`fire-rate falls toward zero as model strength "
                "rises`) is unobservable once the guardrail removes the turns it would be measured "
                "against. This is un-retrofittable: the data for a v2 decision only exists if v1 "
                "does not act."
            )
        if self.fired and not self.evidence.strip():
            raise NotObservable(
                "a guardrail fired with no evidence. §0.5 property 1: it fires on DETERMINISTIC "
                "evidence — an identical call repeated, a budget spent — never on a judgement "
                "about whether the model seems confused."
            )
        if self.fired and not self.transition.strip():
            raise NotObservable(
                "a guardrail fired with no transition. §0.5: its output must be a PLAN STATE "
                "TRANSITION, not a stop; a fire with nothing to move to IS the stop."
            )


@dataclass(frozen=True, slots=True)
class Observation:
    """One turn's P5 record. **Four fields, all required, no defaults.**

    A path that cannot answer one of these cannot build this object, so it cannot end a turn with a
    partial record. That is the whole mechanism — there is no validator to run and forget to run.
    """

    #: §5 field 1 — **an array PER PASS**, each `{pass, tool_choice, names}`. 🔴 A scalar `text[]`
    #: would record only the LAST pass and lose the mid-turn deletion this field exists to catch:
    #: arm E's silent deletion is invisible in production today precisely because no column answers
    #: *"what did this turn advertise, and when"*.
    advertised: tuple[dict, ...]
    #: §5 field 2 / §0.14.3 — `[{scope, …}]`. The shape is deliberately not `{tool, stage, reason}`:
    #: that admits NEITHER row the code writes, because it omits `pass` and requires `tool`, which
    #: the catalogue and pass scopes do not carry.
    withheld: tuple[dict, ...]
    #: §5 field 3. 🔴 **NOT A PARAMETER ANYONE CHOOSES.** There is no public constructor that takes
    #: it: `observe_dispatch` / `observe_breaker` / `observe_meta` each write one literal, so the
    #: value is a fact about *which line ran*. CP-0.3's residual was the opposite — a `meta`/`breaker`
    #: split by looking a name up in a set, self-flagged `source_inferred` so the gap stayed
    #: countable. That flag has no counterpart here because there is no inference to count.
    source: str
    outcome: str
    guardrail: Guardrail = field(default_factory=lambda: Guardrail(False, "", ""))
    #: C-7, and §4.2's shape: **a REFINEMENT of one outcome value, never a peer taxonomy.** Only
    #: `failed` carries a retryability class; *"is `partial` retryable"* is a category error, and a
    #: field that answers it anyway is a second vocabulary that will drift from the first.
    error_class: str | None = None

    def __post_init__(self) -> None:
        if type(self.source) is not str or self.source not in SOURCES:
            raise NotObservable(
                f"source is {self.source!r}; it must be one of {SOURCES} (§5 field 3). A result "
                f"whose origin is unknown makes the error signal uninterpretable — 58-66% of what "
                f"the model sees as an error is our own prose."
            )
        if type(self.outcome) is not str or self.outcome not in OUTCOMES:
            raise NotObservable(
                f"outcome is {self.outcome!r}; C-14 replaced `ok: bool` with exactly {OUTCOMES}. "
                f"`ok=true` meant seven different things: 358 refusals rode the success channel."
            )
        # C-7 · §4.2 — the refinement relation, enforced in BOTH directions. Totality: a `failed`
        # with no class is the prose-derived row all over again, and V-METRIC's ruling turns on
        # every producer writing one. Disjointness: a class on any other outcome answers a question
        # that has no answer, and a column that is sometimes a category error cannot be aggregated.
        if self.outcome == FAILED:
            if type(self.error_class) is not str or self.error_class not in ERROR_CLASSES:
                raise NotObservable(
                    f"outcome is {FAILED!r} and error_class is {self.error_class!r}; it must be one "
                    f"of {ERROR_CLASSES} (C-7). A failure with no class is a row that can only be "
                    f"classified later by reading its prose — the measurement V-METRIC ruled "
                    f"unscoreable after proving the best possible regex insufficient. If the raising "
                    f"site genuinely cannot tell, C-7's answer is {UNCLASSIFIABLE!r}, which is the "
                    f"fail-closed direction: an unclassifiable failure must never read as retryable."
                )
        elif self.error_class is not None:
            raise NotObservable(
                f"outcome is {self.outcome!r} and error_class is {self.error_class!r}. §4.2: the "
                f"error class is a SUB-FIELD of {FAILED!r}, not a peer taxonomy — asking whether "
                f"{self.outcome!r} is retryable is a category error, and a field that answers it "
                f"anyway becomes a second vocabulary drifting from the first."
            )
        seen: set[int] = set()
        for i, entry in enumerate(self.advertised):
            if type(entry) is not dict or set(entry) != {"pass", "tool_choice", "names"}:
                raise NotObservable(
                    f"advertised[{i}] is {entry!r}; each entry is exactly "
                    f"{{pass, tool_choice, names}} (§5 field 1)."
                )
            p = entry["pass"]
            if type(p) is not int or p < 1:
                raise NotObservable(f"advertised[{i}].pass is {p!r}; passes are 1-based ints")
            # 🔴 **TWO ENTRIES FOR ONE PASS IS THE SCALAR DEFECT WEARING THE ARRAY'S CLOTHES.** The
            # field is per-pass so a mid-turn deletion is visible; two rows for the same pass make
            # "what was advertised at pass 2" ambiguous, and every consumer that reads the first
            # one silently disagrees with every consumer that reads the last.
            if p in seen:
                raise NotObservable(
                    f"advertised has two entries for pass {p}. The array is per PASS — a duplicate "
                    f"makes the field answer two things at once, which is the scalar `text[]` "
                    f"defect this shape exists to avoid."
                )
            seen.add(p)
            if type(entry["names"]) is not tuple:
                raise NotObservable(
                    f"advertised[{i}].names is a {type(entry['names']).__name__}; a mutable or "
                    f"lazily-computed container is a record that can change after it is written"
                )


def _observe(
    surfaces: Sequence,
    *,
    source: str,
    outcome: str,
    error_class: str | None,
    tool_choice: str,
    guardrail: Guardrail | None,
) -> Observation:
    """Build the record **from the surfaces that were actually assembled**.

    🔴 **PRIVATE, AND THAT UNDERSCORE IS THE WHOLE OF CP-2.6's FIRST HALF.** This is the only
    function that accepts `source` as an argument, and nothing outside this module may reach it: the
    three callers below are the only ones, each writing one literal. See `observe_dispatch` for what
    that buys and what it deliberately does not.

    🔴 **DERIVED, NEVER HAND-TYPED.** The one thing this run has proved five times over is that a
    denominator a person maintains is a lower bound. `advertised` is exactly what each pass offered
    and `withheld` is exactly what each pass registered, both read off the `Surface` objects the
    assembler returned — so a pass that happened and was not recorded is not possible to express,
    rather than possible and discouraged.
    """
    return Observation(
        advertised=tuple(
            {"pass": s.pass_number, "tool_choice": tool_choice, "names": tuple(s.names)}
            for s in surfaces
        ),
        withheld=tuple(record for s in surfaces for record in s.withheld),
        source=source,
        outcome=outcome,
        guardrail=guardrail if guardrail is not None else Guardrail(False, "", ""),
        error_class=error_class,
    )


def observe_dispatch(
    surfaces: Sequence,
    *,
    outcome: str,
    error_class: str | None = None,
    tool_choice: str = "auto",
    guardrail: Guardrail | None = None,
) -> Observation:
    """A declaration actually ran. **`source='tool'` because this line is the dispatch site.**

    🔴 **CP-2.6 · P2 — `source` IS ASSIGNED STRUCTURALLY, AND THE MECHANISM IS THE ABSENCE OF A
    PARAMETER.** The legacy classifier is three lines and looks like this:

        _source = SOURCE_META if name in RUNTIME_PRIMITIVES else SOURCE_BREAKER
        chunk["source_inferred"] = True

    Every objection to that code is an objection to `name in RUNTIME_PRIMITIVES` — the origin of a
    result is being recovered from a *string*, after the fact, by a set this service happens to
    maintain. It is right until someone adds a dispatch site without a stamp, at which point it is
    confidently wrong and the flag is the only reason anyone could ever find out.

    Here there is nothing to recover. `source` is not a value a caller supplies, so it cannot be
    supplied wrongly; there are three functions, each pinned to one literal, and choosing this one
    *is* the statement that a dispatch happened. **A verifier's question changes shape**: not *"is
    the classifier right"*, which needs a corpus, but *"is this the dispatch site"*, which needs one
    look at the enclosing function.

    🔴 **WHAT THIS DOES NOT BUY, said plainly because the tempting claim is one step too far.** It
    does not stop a caller writing `(observe_dispatch if x else observe_breaker)(...)` and putting
    the lookup back one frame up. Nothing in the type system forbids that, so it is forbidden
    *statically* instead — the CP-2.6 guards reject any use of these three names other than as the
    direct callee of a call, which is the same shape of check the membrane gate already applies to
    the P4 ceiling methods. The claim is therefore: **no inference inside the package, and a gate
    that goes red the moment one is introduced** — not a proof about all possible callers anywhere.
    """
    return _observe(
        surfaces, source="tool", outcome=outcome, error_class=error_class,
        tool_choice=tool_choice, guardrail=guardrail,
    )


def observe_breaker(
    surfaces: Sequence,
    *,
    outcome: str,
    error_class: str | None = None,
    tool_choice: str = "auto",
    guardrail: Guardrail | None = None,
) -> Observation:
    """**Our own prose, minted by us.** `source='breaker'` because this line is inside a breaker.

    This is the source that motivated §5 field 3 at all: **58–66% of what the model sees as an error
    is something we wrote**, and while that fraction is unlabelled every error-rate comparison in
    this run is measuring the two runtimes' breakers as if they were the world's failures.
    """
    return _observe(
        surfaces, source="breaker", outcome=outcome, error_class=error_class,
        tool_choice=tool_choice, guardrail=guardrail,
    )


def observe_meta(
    surfaces: Sequence,
    *,
    outcome: str,
    error_class: str | None = None,
    tool_choice: str = "auto",
    guardrail: Guardrail | None = None,
) -> Observation:
    """A runtime primitive answered — `tool_list`, `tool_load`. `source='meta'`, structurally.

    In the legacy path this and `breaker` are the pair the name lookup separates, and it is the only
    place `source_inferred` is ever set. Here they are two different functions in two different
    places, so the split that needed a closed set of names needs nothing at all.
    """
    return _observe(
        surfaces, source="meta", outcome=outcome, error_class=error_class,
        tool_choice=tool_choice, guardrail=guardrail,
    )


__all__ = ["ERROR_CLASSES", "FAILED", "Guardrail", "NotObservable", "OUTCOMES", "Observation",
           "SOURCES", "UNCLASSIFIABLE", "observe_breaker", "observe_dispatch", "observe_meta",
           "prompt_hash"]
