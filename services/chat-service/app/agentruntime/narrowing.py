"""CP-1.7 · P1 — every narrowing registers `{tool, stage, reason, pass}`.

**This is the property that failed eleven straight verification rounds as a retrofit**, and the
reason it failed is worth stating where the replacement lives. On the legacy surface P1 is one
claim about **seven narrowing stages spread over five files, thirty mint sites and six INSERT
paths**. Eight fixes were attempted. Every one was correct at the layer it named and blind to the
next; two were placed where they could not run at all — one 73 lines after the stage it
instrumented, one inside a branch that stage never takes. There was no place to stand from which
the whole surface was visible.

**So P1 is not enforced here. It is made hard to violate, and the residual is named.** A caller
cannot express *"drop these and say nothing"* through `NarrowingRule`, because the stage and the
reason are required arguments and the record is written in the same statement that computes the
removal — and `SurfaceAssembler.assemble` checks `offered + registered == admitted` before it
returns.

**What that check does not cover, because a verifier had to find each of these:** its baseline is
the assembler's own input list, so mutating that before assembly is invisible; it conserves
**cardinality, not identity**, so fabricated records balance a real drop; and it guards `assemble`
only — `discover` carries its own registration for that reason.

🔴 **An earlier version of this paragraph ended *"there is no second path, and `Surface` cannot be
built from a name list"*. Both halves were false.** `discover(kind=…)` is a second removal path (it
registers, but it exists), and `Surface` is an ordinary frozen dataclass that anyone can call. The
sentence 60 lines away in `surface.py` had already been corrected to say so; **this copy was left
standing through four verification rounds**, which is the same erratum-not-applied-everywhere
failure that this run has now made in three separate documents.

**What is true:** every *shipped* removal registers — `_narrow` and `discover` are the only two, and
both write the record in the loop that computes it. 🔴 *And the sentence that replaced the false one
was itself an over-claim of the same shape, caught one round later: it said the gate keeps `Surface`
single-sited "so a second construction reds CI". Executed on four spellings, only a plain in-package
call reds — an attribute call, an alias, and any site outside the package all pass.* The gate raises
the cost of a second construction site; it does not make one impossible.

That is the concrete meaning of §0.1's *"the membrane is construction, not filtering"* for this
property: not a gate over a filter, but the absence of a filter to gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Narrowing:
    """One declaration, absent from one pass, with who decided and why.

    Every field is required. `stage` answers *which mechanism do I go and fix*, and a bare name list
    — *"glossary_search was dropped"* — is not actionable, which is why the legacy column's first
    version was rejected. `pass_number` is not decoration either: without it a verifier found 19 of
    303 withheld declarations **simultaneously advertised on every pass** and could not tell a
    contradiction from a sequence, because *dropped at one stage, restored by a later one* is
    coherent history and indistinguishable from a bug when the record is timeless.
    """

    declaration_id: str
    stage: str
    reason: str
    pass_number: int
    #: §0.14.1a rule 6 — a RANK-DEPENDENT narrowing must say where in the ranking this landed and
    #: what the ranking was. Without them `{stage: token_budget, reason: over budget}` says *that*
    #: it was cut and cannot answer "why this one and not that one" — the only question a person
    #: debugging a missing tool actually has. `None` on stages whose decision is per-row, where the
    #: question does not arise.
    rank: int | None = None
    ordered_by: tuple[tuple[str, str], ...] | None = None

    def as_record(self) -> dict:
        out = {
            "tool": self.declaration_id,
            "stage": self.stage,
            "reason": self.reason,
            "pass": self.pass_number,
        }
        if self.rank is not None:
            out["rank"] = self.rank
            out["ordered_by"] = [list(k) for k in (self.ordered_by or ())]
        return out


@dataclass(frozen=True, slots=True)
class Widening:
    """CP-2.2 · §4.3 — one declaration RESTORED because the current plan step names it.

    > **A plan step's declaration MUST be advertised while that step is current.**

    §0.1 governs only *narrowing*; the measured failure class runs the other way — **a plan names a
    declaration that is not on the wire.** This repository has paid for that omission three times,
    with three heuristics that exist for no other reason: the rail next-step budget exemption, the
    backtick prose scraper, and `load_skill` naming tools that were never advertised. The last one
    is the `co_write` incident: **6,948 characters of plan prose, zero tool calls**, because the two
    plan tools were named only in signature form and the scraper required a closing backtick.

    🔴 **THIS IS ITS OWN EVENT KIND RATHER THAN AN ABSENCE, AND THAT IS THE DESIGN DECISION.** The
    shorter implementation drops the `Narrowing` and lets the conservation law rebalance — and it
    erases the only evidence that **a stage wanted this declaration gone and the plan overruled
    it.** That disagreement *is* the finding. Each of the three heuristics was written blind to the
    other two precisely because nobody could see it.

    `over_stage` / `over_reason` carry what was overruled. Without them the record says a
    declaration was widened and cannot answer *widened past what* — the same argument that put
    `rank` and `ordered_by` on a rank-dependent narrowing.
    """

    declaration_id: str
    reason: str
    pass_number: int
    over_stage: str
    over_reason: str

    def as_record(self) -> dict:
        return {
            "tool": self.declaration_id,
            "stage": "widening",
            "reason": self.reason,
            "pass": self.pass_number,
            "over": {"stage": self.over_stage, "reason": self.over_reason},
        }


@dataclass(slots=True)
class NarrowingLog:
    """Everything withheld during one turn, in the order it was decided.

    Accumulates across passes rather than per pass: the question a withholding answers is *"was
    this reachable at all during this turn, and if not, who decided that"*, and the answer must
    survive a later pass that happens not to consider the declaration.
    """

    entries: list[Narrowing] = field(default_factory=list)
    #: CP-2.2. A SEPARATE list, not a second kind inside `entries`, because every existing reader
    #: of `entries` — the conservation law, `for_pass`, `stages`, `records` — asks *"what did the
    #: model not see"*, and a widening is the opposite answer. Mixing them would silently change
    #: what four call sites mean, which is the shape `withheld` was already corrected for once.
    widenings: list[Widening] = field(default_factory=list)

    def record(
        self, declaration_id: str, *, stage: str, reason: str, pass_number: int,
        rank: int | None = None, ordered_by: tuple[tuple[str, str], ...] | None = None,
    ) -> None:
        self.entries.append(Narrowing(declaration_id, stage, reason, pass_number, rank, ordered_by))

    def widen(
        self, declaration_id: str, *, reason: str, pass_number: int,
        over_stage: str, over_reason: str,
    ) -> None:
        """Register a restoration. **The `Narrowing` it overrules stays in `entries`.**

        Deleting it would be shorter and would balance the conservation law just as well. It would
        also destroy the record of the disagreement, which is the one thing this event is for.
        """
        self.widenings.append(
            Widening(declaration_id, reason, pass_number, over_stage, over_reason))

    def widened_at(self, pass_number: int) -> set[str]:
        return {w.declaration_id for w in self.widenings if w.pass_number == pass_number}

    def records(self) -> list[dict]:
        return [e.as_record() for e in self.entries]

    def widening_records(self) -> list[dict]:
        return [w.as_record() for w in self.widenings]

    def for_pass(self, pass_number: int) -> list[Narrowing]:
        return [e for e in self.entries if e.pass_number == pass_number]

    def stages(self) -> set[str]:
        return {e.stage for e in self.entries}

    def __len__(self) -> int:
        return len(self.entries)
