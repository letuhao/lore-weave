"""CP-1.7 · P1 — every narrowing registers `{tool, stage, reason, pass}`.

**This is the property that failed eleven straight verification rounds as a retrofit**, and the
reason it failed is worth stating where the replacement lives. On the legacy surface P1 is one
claim about **seven narrowing stages spread over five files, thirty mint sites and six INSERT
paths**. Eight fixes were attempted. Every one was correct at the layer it named and blind to the
next; two were placed where they could not run at all — one 73 lines after the stage it
instrumented, one inside a branch that stage never takes. There was no place to stand from which
the whole surface was visible.

**So P1 is not enforced here. It is made unavailable to violate.** A caller of this module cannot
express "drop these and say nothing", because the only operation that removes a declaration takes
the stage and the reason as required arguments and writes the record in the same statement that
computes the removal. There is no second path, and `Surface` cannot be built from a name list.

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

    def as_record(self) -> dict:
        return {
            "tool": self.declaration_id,
            "stage": self.stage,
            "reason": self.reason,
            "pass": self.pass_number,
        }


@dataclass(slots=True)
class NarrowingLog:
    """Everything withheld during one turn, in the order it was decided.

    Accumulates across passes rather than per pass: the question a withholding answers is *"was
    this reachable at all during this turn, and if not, who decided that"*, and the answer must
    survive a later pass that happens not to consider the declaration.
    """

    entries: list[Narrowing] = field(default_factory=list)

    def record(self, declaration_id: str, *, stage: str, reason: str, pass_number: int) -> None:
        self.entries.append(Narrowing(declaration_id, stage, reason, pass_number))

    def records(self) -> list[dict]:
        return [e.as_record() for e in self.entries]

    def for_pass(self, pass_number: int) -> list[Narrowing]:
        return [e for e in self.entries if e.pass_number == pass_number]

    def stages(self) -> set[str]:
        return {e.stage for e in self.entries}

    def __len__(self) -> int:
        return len(self.entries)
