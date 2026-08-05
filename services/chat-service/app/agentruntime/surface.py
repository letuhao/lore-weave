"""CP-1.2/1.3/1.7 · the assembler — M1 is its only catalog, and it cannot narrow silently.

`ARCHITECTURE.md` §3. **M2 is the load-bearing property**: M1, M3 and M4 are enforceable by tests,
and M2 is what makes those tests *mean* something, because it removes the possibility of the path
rather than checking that it is unused.

The membrane in one signature: `SurfaceAssembler(manifest_doc)`. There is no second catalog
argument, no default that reaches for one, and no import in this package that could supply one —
`scripts/agentruntime-membrane-gate.py` holds that last part, since a rule enforced only by
intention is the thirteenth version of a defect this repository has produced twelve times.

**Why an empty surface is a statement and not a gap.** With no admitted declarations the assembler
returns a surface of zero names — and says so. §0.1 forbids the runtime to narrow *silently*, and
"we offered nothing" is exactly the kind of thing a system reports as absence when it should report
it as a decision. `Surface.is_empty` exists so a caller cannot mistake *"no declarations are
admitted"* for *"the assembler did not run"*; those produced the same screen in the defect that
started this work.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .narrowing import NarrowingLog

def rows_of(manifest_doc: dict) -> list[dict]:
    """The declarations in a manifest document, or a refusal.

    🔴 ONE PLACE, because two hand-written copies of this drifted inside a single commit. The
    assembler was fixed to reject a missing `declarations` key while `discover` — two functions
    below, same file, same commit — kept `.get("declarations", [])`. So `SurfaceAssembler({})`
    raised and `discover({})` returned `[]`: the identical malformed input, two answers, and the
    silent one sat in the M3 entry point.

    A missing key is a **broken document**, not an empty catalog. Serving it as empty erases the
    difference between *"nothing is admitted"* and *"we could not read the catalog"*, which is the
    one confusion `Surface.is_empty` exists to prevent.
    """
    rows = manifest_doc.get("declarations")
    # `_is_exactly`, not `isinstance` — this was the one type decision in the module the identity
    # sweep did not reach, found by asking which sites still spelled it the old way.
    if not _is_exactly(rows, list):
        raise ValueError(
            "manifest document has no `declarations` list. An empty catalog is `[]`; a missing key "
            "is a malformed document, and serving it as empty would hide the difference."
        )
    # 🔴 **THE BOUNDS STOPPED AT THE PIPELINE AND THE DATA WALKED IN.** Every stage parameter is
    # exact-typed, and then `AllowList.keep` asks `row.get("id") in self.names` — so an `id` whose
    # `__eq__` returns True defeated an allow-list of one name and put an **unlisted declaration on
    # the wire with no record at all**, which is arm E reached through the row instead of the rule.
    # A manifest row is an input exactly as much as a stage is; `load()` validates the file, and
    # this validates whatever reached here by any other door (`SurfaceAssembler` and `discover` are
    # both exported and neither went through `load`).
    for i, r in enumerate(rows):
        if not _is_exactly(r, dict):
            raise ValueError(f"declarations[{i}] is a {type(r).__name__}, not a plain object")
        if not _is_exactly(r.get("id"), str) or not r.get("id"):
            raise ValueError(
                f"declarations[{i}].id is {r.get('id')!r}; a declaration id must be a non-empty "
                f"plain string. An id with a custom __eq__ decides membership in every allow-list "
                f"and deny-list it is compared against (§0.14.1)."
            )
    return list(rows)


# ── CP-1.8a · narrowing stages are DATA, and the ordering is explicit ────────────────────────────
#
# `NarrowingRule.keep` was `Callable[[dict], bool]` — a per-row decision — and the stage that
# motivated this whole design is not one. `budget_names_by_tokens` is a RUNNING ACCUMULATOR OVER A
# SORT ORDER: it walks declarations in a ranking and stops when a budget is spent. No per-row
# predicate produces that, and **6 of the 9 rule fixtures in the test suite were already named
# `token_budget`** — the fixtures encoded a shape the type could not hold.
#
# A closure is also not content-addressable, so a pipeline built from closures has no identity: two
# entirely different narrowings hash the same. Data has an identity; a lambda does not.
#
# Each kind is its OWN dataclass rather than `{kind, params}`. A `params` dict would be the same
# blank that `order_by(key, …)` was before §0.14.1a — a placeholder wearing the shape of a design.


@dataclass(frozen=True, slots=True)
class _Narrowing:
    """Shared by every kind that REMOVES declarations. `stage` says who decided, `reason` says why,
    and they are fields of the stage rather than of the call site — so a narrowing cannot be applied
    without them. This is where "every narrowing registers" stops being a discipline."""

    stage: str
    reason: str

    def __post_init__(self) -> None:
        _plain(self.stage, str, "stage")
        _plain(self.reason, str, "reason")
        if not self.stage or not self.reason:
            raise ValueError(
                "a narrowing stage must name its stage and its reason; an exclusion with no "
                "{tool, stage, reason} is a defect, not a policy (ARCHITECTURE §0.3)"
            )


def _is_exactly(value, want) -> bool:
    """`type(value) is want`, and **only** that.

    🔴 **THE IDENTITY FIX REACHED ONE OF THREE SITES.** `type(s) in _KIND_SET` was rewritten to
    `any(type(s) is k …)` after a verifier forged membership with a metaclass `__eq__` — and
    `type(x) not in self.SCALARS`, twice, was left exactly as it was. The same forgery passes both,
    measured for `op="eq"` and for a forged element inside a real tuple. `in` over a container
    dispatches `__eq__`/`__hash__`; `is` is the only comparison Python does not dispatch.

    One helper now, so there is nowhere for a fourth site to disagree.
    """
    t = type(value)
    return any(t is w for w in (want if isinstance(want, tuple) else (want,)))


def _plain(value, want, field: str):
    """🔴 **ONE OPERAND WAS BOUNDED AND SIX WERE NOT** — the first fix reasoned about `Filter.value`
    because that was where the verifier had pointed, and left every other field `Any` in practice.

    Measured on the next round: `TakeWhileBudget.budget` consults a custom `__lt__` **once per row**,
    `Filter.field` steers `row.get()` through custom `__hash__`/`__eq__`, and `TopK.k` runs through
    `__index__`. Each is arbitrary logic reaching the narrowing decision — the thing the six kinds
    exist to make impossible — through a field nobody thought of as an operand.

    **Exact type, never `isinstance`.** A `str` or `int` subclass passes an isinstance check and then
    behaves like a closure; `bool` is an `int` subclass and is refused for `int` fields for the same
    reason `canon` checks it first.
    """
    if not _is_exactly(value, want):
        raise ValueError(
            f"{field} is a {type(value).__name__}; a stage parameter must be a plain "
            f"{want.__name__}. An object with custom dunders is a closure wearing a value's "
            f"clothes, and it reaches the narrowing decision exactly like one (§0.14.1)."
        )
    return value


@dataclass(frozen=True, slots=True)
class Filter(_Narrowing):
    """Per-row membership — the only shape the old `keep` predicate covered.

    **Three operators, deliberately.** Regex or arbitrary comparison would re-admit the closure
    problem under a new name: an unbounded operator set is a closure with extra steps. A stage that
    needs a fourth is **a finding to bring back to §0.14.1**, not a licence to add one here.
    """

    field: str = ""
    op: str = "eq"
    value: Any = None

    OPS = ("eq", "in", "not_in")
    #: The operand types a filter may hold. **Exact type, never `isinstance`** — see `__post_init__`.
    #: `float` is absent for the same reason `canon` refuses it: two spellings of one value.
    SCALARS = (str, bool, int, type(None))

    def __post_init__(self) -> None:
        # NOT `super().__post_init__()`. `@dataclass(slots=True)` REBUILDS the class, so the
        # zero-arg `super()` closes over the pre-rebuild class and raises `TypeError: obj is not an
        # instance or subtype of type`. Named explicitly, which also survives the next reorder.
        _Narrowing.__post_init__(self)
        # 🔴 `op` IS AN OPERAND TOO, and the sharpest one: it selects `keep()`'s branch **and**
        # selects which validation branch runs six lines below. A `str` subclass with a custom
        # `__eq__` spells `'regex'` and satisfies `in self.OPS`; an object that is not a string at
        # all also constructed. Bounding `value` while leaving `op` free is bounding the argument
        # and not the operator — the mirror of the mistake §0.14.1 made in the other direction.
        _plain(self.op, str, "op")
        if not any(self.op is o or self.op == o for o in self.OPS) or self.op not in self.OPS:
            raise ValueError(f"unknown op {self.op!r}; expected one of {self.OPS}")
        # `field` is an OPERAND too: it is the key handed to `row.get()`, so a custom `__hash__` and
        # `__eq__` decide which value the filter reads. Measured.
        _plain(self.field, str, "field")
        if not self.field:
            raise ValueError("a filter must name the field it reads")
        # 🔴 THE OPERATOR SET WAS CLOSED AND THE PREDICATE SET WAS NOT. `value: Any` re-admitted
        # arbitrary logic through Python's own protocols, and a verifier measured it: a class whose
        # `__contains__` runs a regex gives `op="in"` the behaviour of a regex stage with **zero new
        # operators**, and `__eq__` does the same for `op="eq"`. A bare `lambda` was storable here
        # too. The design reasoned about the operator VOCABULARY and never about the OPERAND, so the
        # whole argument for three operators walked straight past this field.
        #
        # `type(x) in SCALARS`, not `isinstance` — a `str` subclass overriding `__eq__` passes an
        # isinstance check and then behaves like a closure. Exactness is the point of the bound.
        if self.op == "eq":
            if not _is_exactly(self.value, self.SCALARS):
                raise ValueError(
                    f"filter value {self.value!r} is a {type(self.value).__name__}; `eq` compares "
                    f"against a plain scalar. An object with a custom __eq__ is a closure wearing a "
                    f"value's clothes (§0.14.1)."
                )
        elif not _is_exactly(self.value, tuple) or any(
            not _is_exactly(v, self.SCALARS) for v in self.value
        ):
            raise ValueError(
                f"filter value {self.value!r} is not a tuple of scalars; `{self.op}` needs one. A "
                f"container with a custom __contains__ expresses arbitrary logic (§0.14.1)."
            )

    def keep(self, row: dict) -> bool:
        got = row.get(self.field)
        if self.op == "eq":
            return got == self.value
        if self.op == "in":
            return got in self.value
        return got not in self.value


@dataclass(frozen=True, slots=True)
class AllowList(_Narrowing):
    """Explicit set membership — the always-hot core."""

    names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _Narrowing.__post_init__(self)
        _require_names(self, "an allow-list with no names narrows the surface to NOTHING")

    def keep(self, row: dict) -> bool:
        return row.get("id") in self.names


@dataclass(frozen=True, slots=True)
class DenyList(_Narrowing):
    """Explicit set exclusion — the retirement list."""

    names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _Narrowing.__post_init__(self)
        _require_names(self, "a deny-list with no names removes nothing and registers nothing")

    def keep(self, row: dict) -> bool:
        return row.get("id") not in self.names


def _require_names(stage, consequence: str) -> None:
    """Both list kinds default `names=()`, and **the default is the failure mode**, not a neutral
    starting point: the realistic way an empty list arrives is a config read that returned nothing.
    An allow-list then hides the whole catalogue and a deny-list becomes a silent no-op — the two
    failures this package exists to make impossible, reached by a default rather than by a decision.

    "Rejected at construction, not at use" was true of pipeline ORDER and not of stage PARAMETERS; a
    verifier found `AllowList("s","r")` constructing happily and narrowing to zero.
    """
    if type(stage.names) is not tuple:
        raise ValueError(
            f"{type(stage).__name__}.names is a {type(stage.names).__name__}; a container with a "
            f"custom __contains__ or __iter__ decides membership, which is arbitrary logic"
        )
    if not stage.names:
        raise ValueError(f"{type(stage).__name__} must name at least one declaration: {consequence}")
    bad = [n for n in stage.names if type(n) is not str or not n]
    if bad:
        raise ValueError(f"{type(stage).__name__} names must be non-empty strings; got {bad!r}")


@dataclass(frozen=True, slots=True)
class OrderBy:
    """**Not a narrowing** — it establishes the ranking that rank-dependent kinds consume, so it
    carries no `stage`/`reason`.

    §0.14.1a is the design, and it exists because a `key` parameter was a blank standing in for one.
    **Rank is what a budget cuts on**, so whatever fills that blank decides which declarations reach
    the model — arm E was a ranking outcome.

    Three rules, each of which the legacy ranking breaks:

    * **every field must be PRESENT on the row.** A missing field is a REJECTION, not a fallback:
      silently falling back to id-order reorders the whole surface and cuts different declarations.
    * **`id` is appended as the final component, always.** Equal keys are not an edge case — an
      embedding failure yields all-zero relevance on every row, and U-2 shows that failure is
      reachable. Without a total order the budget's victim is whatever the iteration produced.
    * **`cost` may never be the primary component.** Cheapest-first optimises COUNT, not usefulness:
      a cheap useless declaration outranks an expensive essential one, and `book_list` — arm E's
      victim — is exactly what loses to volume.
    """

    keys: tuple[tuple[str, str], ...] = ()

    DIRECTIONS = ("asc", "desc")
    #: The final tie-break, appended implicitly. Never omit it: see the class docstring.
    TIE_BREAK = ("id", "asc")

    def __post_init__(self) -> None:
        if type(self.keys) is not tuple:
            raise ValueError(
                f"order_by keys is a {type(self.keys).__name__}; the ranking is what a budget cuts "
                f"on, so a container that decides its own iteration decides the whole surface"
            )
        if not self.keys:
            raise ValueError("order_by must name at least one field")
        for i, pair in enumerate(self.keys):
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError(f"keys[{i}] is not a (field, direction) pair: {pair!r}")
            field, direction = pair
            # `field` is a `row[...]` key and the sort key; a custom `__hash__`/`__eq__` chooses
            # which column is actually ranked.
            _plain(field, str, f"keys[{i}] field")
            # `field` was bounded and `direction` was not — in the same loop. Measured: a direction
            # spelled `'NONSENSE'` was accepted, the sort inverted, and end-to-end it decided which
            # 2 of 4 declarations reached the model. The resulting `ordered_by` record was neither
            # JSON- nor `canon`-serialisable, so the row explaining the cut could not be written.
            _plain(direction, str, f"keys[{i}] direction")
            if direction not in self.DIRECTIONS:
                raise ValueError(f"keys[{i}]: unknown direction {direction!r}")
            if field == "cost" and i == 0:
                raise ValueError(
                    "`cost` may not be the primary ordering component: cheapest-first optimises "
                    "the NUMBER of declarations offered, not their usefulness (§0.14.1a)"
                )

    def effective_keys(self) -> tuple[tuple[str, str], ...]:
        if any(f == self.TIE_BREAK[0] for f, _ in self.keys):
            return self.keys
        return self.keys + (self.TIE_BREAK,)

    def sort(self, rows: list[dict]) -> list[dict]:
        out = list(rows)
        # Stable sorts applied least-significant-first give the lexicographic order of the key list.
        for field, direction in reversed(self.effective_keys()):
            for r in out:
                if field not in r:
                    raise ValueError(
                        f"order_by names {field!r}, which row {r.get('id')!r} does not carry. A "
                        f"missing field is a rejection, not a fallback — falling back to id-order "
                        f"would reorder the surface and cut different declarations (§0.14.1a)."
                    )
            out.sort(key=lambda r: r[field], reverse=(direction == "desc"))
        return out


@dataclass(frozen=True, slots=True)
class TopK(_Narrowing):
    """Drops beyond rank *k*. Rank-dependent: requires an `OrderBy` before it."""

    k: int = 0

    def __post_init__(self) -> None:
        # NOT `super().__post_init__()`. `@dataclass(slots=True)` REBUILDS the class, so the
        # zero-arg `super()` closes over the pre-rebuild class and raises `TypeError: obj is not an
        # instance or subtype of type`. Named explicitly, which also survives the next reorder.
        _Narrowing.__post_init__(self)
        # `k` reaches a slice, so `__index__` runs arbitrary code. Measured.
        _plain(self.k, int, "k")
        if self.k < 1:
            # 🔴 `k=0` IS THE DEFAULT, AND IT NARROWS THE SURFACE TO ZERO — the exact failure
            # `_require_names` was written for, in the kind sitting next to it, missed because the
            # first fix looked at the two list kinds the verifier had named and not at the set.
            raise ValueError(
                "top_k needs k >= 1: k=0 keeps nothing, and it is the DEFAULT, so the failure "
                "arrives by omission rather than by decision"
            )


@dataclass(frozen=True, slots=True)
class TakeWhileBudget(_Narrowing):
    """The accumulator: walks the ranking and drops the tail once `budget` is spent.

    **`budget` is a value in the pipeline, never an ambient read.** The legacy budget is
    `os.environ` read at import, which makes it a property of the container that no record captures
    — so the same recorded inputs stop producing the same surface. The boundary module reads it and
    passes it in, so it travels with the pipeline that used it.
    """

    budget: int = 0
    cost_field: str = "cost"

    def __post_init__(self) -> None:
        # NOT `super().__post_init__()`. `@dataclass(slots=True)` REBUILDS the class, so the
        # zero-arg `super()` closes over the pre-rebuild class and raises `TypeError: obj is not an
        # instance or subtype of type`. Named explicitly, which also survives the next reorder.
        _Narrowing.__post_init__(self)
        # `budget` is compared against a running total ONCE PER ROW, so a custom `__lt__` decides
        # every cut in the pipeline. `cost_field` is a `row.get()` key, same as `Filter.field`.
        _plain(self.budget, int, "budget")
        _plain(self.cost_field, str, "cost_field")
        if self.budget < 0:
            raise ValueError("take_while_budget needs a non-negative budget")
        if not self.cost_field:
            raise ValueError("take_while_budget must name the field it accumulates")


#: Kinds whose decision depends on POSITION in a ranking rather than on the row alone.
RANK_DEPENDENT = (TopK, TakeWhileBudget)

#: 🔴 **THE CLOSED SET, AND IT HAD TO BE WRITTEN DOWN BEFORE IT WAS CLOSED.** `assemble` dispatched
#: on `stage.keep(row)` by duck typing, and `validate_pipeline` only asked whether a stage was an
#: `OrderBy` or rank-dependent. **Nothing anywhere required a stage to be one of the six.** A
#: verifier defined a four-line class holding a lambda, never imported from this package, and drove
#: it through `assemble`: it narrowed, the conservation law balanced, and `validate_pipeline` said
#: nothing. `NarrowingRule(keep=Callable)` had not been removed — it had been **un-named**.
#:
#: Membership is by EXACT TYPE. A subclass of `Filter` that overrides `keep` is the same closure
#: through inheritance, and `isinstance` would welcome it.
STAGE_KINDS = (OrderBy, Filter, AllowList, DenyList, TopK, TakeWhileBudget)
_KIND_SET = frozenset(STAGE_KINDS)


def validate_pipeline(stages) -> None:
    """Every stage is one of the six kinds, and a rank-dependent kind MUST establish its order first.

    A budget or a top-*k* over an **unordered** collection selects an arbitrary subset — which is
    the legacy defect where `active_tool_names` is a `set` iterated unsorted, and `tools` is the
    first prompt-cache block. Checkable from the pipeline value alone, which is what makes it worth
    stating, and rejected **at construction** rather than at use.
    """
    ordered = False
    for i, s in enumerate(stages):
        # 🔴 `type(s) in _KIND_SET` IS DEFEATED BY A METACLASS: `__eq__`/`__hash__` on the class's
        # own metaclass make a foreign class compare equal to a member, so the set lookup says yes.
        # `is` against each member cannot be overridden by anything — identity is the only comparison
        # Python does not dispatch. Measured by a verifier on the version above.
        if not any(type(s) is k for k in STAGE_KINDS):
            raise ValueError(
                f"pipeline[{i}] is a {type(s).__name__}, which is not one of the six stage kinds "
                f"{tuple(k.__name__ for k in STAGE_KINDS)}. A stage that merely answers `keep()` is "
                f"a closure with a different name, and the whole point of §0.14.1 is that a "
                f"narrowing has an identity a reader can hash and compare."
            )
        if isinstance(s, OrderBy):
            ordered = True
        elif isinstance(s, RANK_DEPENDENT) and not ordered:
            raise ValueError(
                f"{type(s).__name__} depends on rank, and no order_by precedes it. Applied to an "
                f"unordered collection it selects an arbitrary subset (§0.14.1)."
            )


@dataclass(frozen=True, slots=True)
class Surface:
    """What the model is offered on one pass.

    **Built at exactly one site — `SurfaceAssembler.assemble` — and that is enforced by
    `scripts/agentruntime-membrane-gate.py`, not by this sentence.** An earlier draft of this
    docstring said "constructible only by", which was false: this is an ordinary frozen dataclass
    and anyone can call it. The gate counts construction sites instead, so a second one reds CI
    rather than quietly producing a surface whose `withheld` does not account for its `names`.

    `withheld` is **what THIS assembly kept from the model**, not everything logged at this pass.
    The distinction is not bookkeeping:

    🔴 An earlier version made it *everything at that pass*, and a verifier showed what that
    produces — `discover(kind="skill")` filters a **query**, so its rows appear withheld at pass 1
    while the assembler advertises the very same declarations at pass 1. **That is the exact
    contradiction `pass_number` was added to make detectable** (a verifier once found 11 of 178
    withheld tools simultaneously advertised on every pass), and I had recreated it — then written
    a test that asserted the contradictory state as correct.

    A query filter and a surface narrowing are different facts. `withheld` answers *"what could the
    model not see on this pass"*; the shared `NarrowingLog` holds the turn's whole record, stage by
    stage, and is where a caller looks for anything wider. Keeping them separate is what stops the
    column meaning two things at once.
    """

    names: tuple[str, ...]
    pass_number: int
    withheld: tuple[dict, ...]

    @property
    def is_empty(self) -> bool:
        return not self.names

    @property
    def count(self) -> int:
        return len(self.names)


class SurfaceAssembler:
    """Builds a surface from the manifest, and from nothing else.

    `manifest_doc` is the ONLY catalog input. §3 forbids the code path, not merely the wrong result:
    a function that reads the legacy catalog and returns nothing from it still IS the path, so the
    argument is not "preferred" or "checked first" — it is the only one that exists.
    """

    __slots__ = ("_rows", "_log")

    def __init__(self, manifest_doc: dict, *, log: NarrowingLog | None = None) -> None:
        self._rows: list[dict] = rows_of(manifest_doc)
        self._log = log if log is not None else NarrowingLog()

    @property
    def log(self) -> NarrowingLog:
        return self._log

    @property
    def admitted_count(self) -> int:
        return len(self._rows)

    def assemble(self, *, pass_number: int, pipeline: Sequence[object] = ()) -> Surface:
        """Assemble one pass's surface.

        **This is the only place THIS CLASS removes a declaration**, and `_narrow` writes the record
        in the same statement that computes the removal. It is *not* the only removal site in the
        module — `discover(kind=…)` is another, and it registers too. An earlier version of this
        docstring said "the only place a declaration can be removed", which four rounds of
        verification left standing while the function 80 lines below did exactly that. Corrected
        rather than defended: the guarantee is *every* removal registers, not that there is one.
        """
        _plain(pass_number, int, "pass_number")
        if pass_number < 1:
            raise ValueError("pass_number is 1-based; a narrowing stamped at pass 0 belongs to no pass")
        # 🔴 **MATERIALISE FIRST, OR WHAT IS VALIDATED IS NOT WHAT RUNS.** `validate_pipeline`
        # consumed one iteration and the loop below took another, so an object yielding different
        # stages on its second pass was checked as one pipeline and executed as a different one: a
        # verifier's four-line rogue class narrowed the surface, registered three records, and
        # **balanced the conservation law**. The accidental form is worse than the adversarial one —
        # passing a bare **generator** made the entire pipeline a silent no-op, a `Filter` keeping
        # one declaration returning all four.
        #
        # Every bound in this module checks a *value*; a value that changes between the check and
        # the use is not bounded at all, and no amount of type-exactness fixes a TOCTOU.
        pipeline = list(pipeline)
        # Rejected at CONSTRUCTION of the assembly, not at use: a rank-dependent stage over an
        # unordered collection selects an arbitrary subset.
        validate_pipeline(pipeline)

        # 🔴 F3 — count only what THIS assembly recorded, not every entry at this pass.
        #
        # The first version read `self._log.for_pass(pass_number)`, which is the whole log. A log
        # shared within one pass — discover-then-assemble, two assemblers in a turn, a retry — made
        # `registered` too large, so the law reported a NEGATIVE loss and raised on correct code.
        # The module's own docstring blesses sharing a log; the test that covers it survived only
        # because it happened to span two passes. **A conservation law over a shared counter must
        # count its own contribution**, or it fails the honest caller and passes the careless one.
        _log_mark = len(self._log.entries)
        kept = self._rows
        ordered_by: tuple[tuple[str, str], ...] | None = None
        for stage in pipeline:
            if isinstance(stage, OrderBy):
                kept = stage.sort(kept)
                ordered_by = stage.effective_keys()
                continue
            kept = self._narrow(kept, stage, pass_number=pass_number, ordered_by=ordered_by)
        mine = [e for e in self._log.entries[_log_mark:] if e.pass_number == pass_number]
        withheld = tuple(e.as_record() for e in mine)

        # 🔴 THE CONSERVATION LAW, ENFORCED IN PRODUCTION CODE RATHER THAN ONLY IN A TEST.
        #
        #     offered + registered == admitted
        #
        # Three rounds each killed a *test* meant to hold this: one checked the wrong direction, one
        # could not fire at all, and the third was a law sampled at five points against one fixture,
        # defeated by a silent drop on the `rules == ()` branch of this very method. A test
        # enumerates the shapes its author thought of, and the author is the person who just wrote
        # the defect. Evaluated here, it needs no enumeration.
        #
        # **What it does NOT do, stated because a verifier had to tell me twice:**
        #   · its baseline is `self._rows`, so mutating that list before assembly is invisible;
        #   · it conserves CARDINALITY, not identity — fabricated records balance a real drop;
        #   · it protects this method only. A path that never calls `assemble` is not covered by it,
        #     which is why `discover` carries its own registration and why the gate counts `Surface`
        #     construction sites.
        # Those are the residuals, not disclaimers: each is a real way to lose a declaration, and
        # naming them is what stops the next reader trusting this line further than it goes.
        if len(kept) + len(withheld) != len(self._rows):
            raise AssertionError(
                f"narrowing lost {len(self._rows) - len(kept) - len(withheld)} declaration(s) "
                f"with no {{tool, stage, reason, pass}} record: {len(self._rows)} admitted, "
                f"{len(kept)} offered, {len(withheld)} registered at pass {pass_number}. "
                f"An exclusion with no record is a defect, not a policy (ARCHITECTURE §0.3)."
            )
        return Surface(
            names=tuple(sorted(r["id"] for r in kept)),
            pass_number=pass_number,
            withheld=withheld,
        )

    def _narrow(
        self, rows: Iterable[dict], stage, *, pass_number: int,
        ordered_by: tuple[tuple[str, str], ...] | None = None,
    ) -> list[dict]:
        """Compute a removal AND register it. These are one statement on purpose.

        Splitting them is the eight-frame defect in miniature: the drop happens in one file and the
        registration is expected in another, and every later change moves one without the other.

        **A rank-dependent stage records the RANK and the KEY it was ranked by** (§0.14.1a rule 6).
        `{stage: token_budget, reason: over budget}` says *that* a declaration was cut; it cannot
        answer **"why this one and not that one"**, which is the only question a person debugging a
        missing tool actually has. A reason that does not distinguish the dropped from the kept is
        not yet actionable.
        """
        rows = list(rows)
        kept: list[dict] = []

        if isinstance(stage, TopK):
            kept, dropped = rows[: stage.k], rows[stage.k:]
        elif isinstance(stage, TakeWhileBudget):
            used, cut_at = 0, len(rows)
            for i, row in enumerate(rows):
                cost = row.get(stage.cost_field)
                # 🔴 THE ROW SIDE WAS `isinstance` WHILE THE STAGE SIDE WAS EXACT — so the bound
                # stopped at the pipeline and the *data* walked in. Measured: a `SneakyCost(int)`
                # with `__radd__` never spends any budget, so the accumulator never reaches its
                # limit and nothing is ever cut. A manifest row is as much an input as a stage is.
                if not _is_exactly(cost, int):
                    raise ValueError(
                        f"take_while_budget reads {stage.cost_field!r}, which row {row.get('id')!r} "
                        f"does not carry as a plain integer. A missing or exotic cost is a "
                        f"rejection, not a fallback (§0.14.1a)."
                    )
                if used + cost > stage.budget and i > 0:
                    cut_at = i
                    break
                used += cost
            kept, dropped = rows[:cut_at], rows[cut_at:]
        else:
            dropped = []
            for row in rows:
                (kept if stage.keep(row) else dropped).append(row)

        rank_dependent = isinstance(stage, RANK_DEPENDENT)
        for row in dropped:
            self._log.record(
                row["id"], stage=stage.stage, reason=stage.reason, pass_number=pass_number,
                rank=(rows.index(row) if rank_dependent else None),
                ordered_by=(ordered_by if rank_dependent else None),
            )
        return kept


def discover(
    manifest_doc: dict,
    *,
    kind: str | None = None,
    log: NarrowingLog | None = None,
    pass_number: int = 1,
) -> list[dict]:
    """CP-1.3 · M3 — discovery reads the manifest and nothing else.

    Same input, same argument, deliberately: M3 is not a separate mechanism from M2, it is the same
    one seen from the discovery side. A legacy-only declaration of any of the three kinds returns
    zero rows here because there is no code path on which it could return anything else.

    🔴 **`kind=` NOW REQUIRES A LOG, because filtering is narrowing.** This function returned fewer
    rows than the manifest holds and registered nothing — a silent drop point sitting beside an
    assembler built so that silent drops are inexpressible. A verifier's enumeration found it; the
    structural test did not, because that test collected the *callers of* `log.record` rather than
    the *places rows are removed*, so it was green over a second narrowing path. **P1 is a property
    of the module, not of one function in it.**
    """
    rows = rows_of(manifest_doc)
    _plain(pass_number, int, "pass_number")
    if kind is None:
        return rows
    # 🔴 `kind` IS AN OPERAND. It is compared against every row, so a custom `__eq__` makes this a
    # regex stage with zero new operators — the §0.14.1 route, in the one narrowing function that
    # is not a stage kind. And its `__repr__` is interpolated into `reason`, so it writes the
    # caller's own text into a **persisted** record.
    _plain(kind, str, "kind")
    if log is None:
        raise ValueError(
            "discover(kind=…) removes declarations, which is a narrowing: pass `log=` so it "
            "registers {tool, stage, reason, pass}. An exclusion with no record is a defect, not a "
            "policy (ARCHITECTURE §0.3)."
        )
    kept: list[dict] = []
    for row in rows:
        if row.get("kind") == kind:
            kept.append(row)
        else:
            log.record(
                row["id"], stage="discovery_kind_filter",
                reason=f"kind is {row.get('kind')!r}, discovery asked for {kind!r}",
                pass_number=pass_number,
            )
    return kept
