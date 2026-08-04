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
from typing import Callable, Iterable, Sequence

from .narrowing import NarrowingLog

# A rule is a KEEP predicate over a manifest row, carrying the two fields P1 requires. The stage and
# the reason are part of the rule rather than of the call site, so a rule cannot be applied without
# them — this is where "every narrowing registers" stops being a discipline.
@dataclass(frozen=True, slots=True)
class NarrowingRule:
    stage: str
    reason: str
    keep: Callable[[dict], bool]

    def __post_init__(self) -> None:
        if not self.stage or not self.reason:
            raise ValueError(
                "a narrowing rule must name its stage and its reason; an exclusion with no "
                "{tool, stage, reason} is a defect, not a policy (ARCHITECTURE §0.3)"
            )


@dataclass(frozen=True, slots=True)
class Surface:
    """What the model is offered on one pass.

    **Built at exactly one site — `SurfaceAssembler.assemble` — and that is enforced by
    `scripts/agentruntime-membrane-gate.py`, not by this sentence.** An earlier draft of this
    docstring said "constructible only by", which was false: this is an ordinary frozen dataclass
    and anyone can call it. The gate counts construction sites instead, so a second one reds CI
    rather than quietly producing a surface whose `withheld` does not account for its `names`.

    Carries the withheld set **alongside** the offered one, not in a log: a narrowing recorded
    somewhere the caller must go and find is a narrowing that gets dropped at the first persistence
    boundary, which is how the legacy column came to be empty for the one stage it was built for.
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
        # `.get("declarations", [])` was a THIRD silent drop: a malformed or wrong-shaped document
        # became an empty surface with no signal, which is indistinguishable from "nothing is
        # admitted" — the one confusion `Surface.is_empty` exists to prevent. A missing key is a
        # broken document, not an empty catalog.
        rows = manifest_doc.get("declarations")
        if not isinstance(rows, list):
            raise ValueError(
                "manifest document has no `declarations` list. An empty catalog is `[]`; a missing "
                "key is a malformed document, and serving it as empty would hide the difference."
            )
        self._rows: list[dict] = list(rows)
        self._log = log if log is not None else NarrowingLog()

    @property
    def log(self) -> NarrowingLog:
        return self._log

    @property
    def admitted_count(self) -> int:
        return len(self._rows)

    def assemble(self, *, pass_number: int, rules: Sequence[NarrowingRule] = ()) -> Surface:
        """The single assembly point. **The only place a declaration can be removed.**

        Each rule is applied through `_narrow`, which computes the removal and writes its record in
        the same statement. There is no branch that drops without recording, because there is no
        second place that drops at all.
        """
        if pass_number < 1:
            raise ValueError("pass_number is 1-based; a narrowing stamped at pass 0 belongs to no pass")
        kept = self._rows
        for rule in rules:
            kept = self._narrow(kept, rule, pass_number=pass_number)
        return Surface(
            names=tuple(sorted(r["id"] for r in kept)),
            pass_number=pass_number,
            withheld=tuple(e.as_record() for e in self._log.for_pass(pass_number)),
        )

    def _narrow(
        self, rows: Iterable[dict], rule: NarrowingRule, *, pass_number: int,
    ) -> list[dict]:
        """Compute a removal AND register it. These are one statement on purpose.

        Splitting them is the eight-frame defect in miniature: the drop happens in one file and the
        registration is expected in another, and every later change moves one without the other.
        """
        kept: list[dict] = []
        for row in rows:
            if rule.keep(row):
                kept.append(row)
            else:
                self._log.record(
                    row["id"], stage=rule.stage, reason=rule.reason, pass_number=pass_number,
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
    rows = list(manifest_doc.get("declarations", []))
    if kind is None:
        return rows
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
