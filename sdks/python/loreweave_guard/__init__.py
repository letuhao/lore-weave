"""loreweave_guard — S1: one honest verdict shape for every guard in the platform.

The bug class this exists to kill
---------------------------------
A guard that could not check something reports a value that READS like a pass. Measured on this
repo, 2026-08-01: a 4-scene, 8,116-word chapter was generated with the canon guard returning
``status="skipped_no_cast"``, ``resolved=True``, ``violations=[]`` — honest field by field, and
green to anything that looks at the two fields a caller naturally looks at. An invented
character appeared in three of those scenes. Nothing anywhere said *"no check ran"*.

Two rules follow, and they are the whole package.

**1 · A status is per-CHECK, never per-guard.** Every real guard here is a composite that
degrades unevenly: the canon guard runs a cast-liveness check AND a name-grounding check AND a
cross-scene check; wiki verify runs four; translation runs a deterministic rule tier plus an LLM
tier. A single scalar makes every one of them lie — it either over-reports (one check ran, so
"checked") or under-reports (one check skipped, so the whole guard looks broken). So
:class:`GuardReport` carries ``checks: dict[str, CheckStatus]`` and DERIVES the headline.

**2 · A verdict is only a verdict if something was checked — but the FINDINGS are not.**
``verdict`` returns ``None`` unless the report as a whole is CHECKED. It is a property, not a
convention, because a convention is what the four guards above were already violating.
``findings`` is deliberately untouched by that rule: *"unverified ⇒ discard the evidence"* would
break translation's corrector loop and two publish gates. A guard may legitimately return
``verdict=None`` with a non-empty findings list, and callers MUST act on the findings.

Why ``NO_RULES`` is computed on the INPUT CORPUS
------------------------------------------------
The tempting implementation asks "did anything match?" — and then every book in which nobody has
died renders a permanent amber banner, which trains the author to ignore it. The question is
"was there anything to check AGAINST?". :func:`check_over` exists so the right version is the
short one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = ["CheckStatus", "GuardReport", "check_over", "worst"]


class CheckStatus(StrEnum):
    """What ONE check did. Ordered by the docstrings, not by severity — see :data:`_RANK`."""

    #: Ran against a real, NON-EMPTY input corpus and produced a usable answer.
    CHECKED = "checked"
    #: Gated off, not sampled, or not relevant to this subject. Renders as NOTHING — it is not
    #: a gap in coverage, it is a check that was never part of this run's scope.
    NOT_APPLICABLE = "not_applicable"
    #: The verdict was self-reported by an upstream caller and taken on trust. Distinct from
    #: CHECKED because nothing here verified it.
    TRUSTED_CALLER = "trusted_caller"
    #: Ran, but the INPUT CORPUS was empty — no rules, no canon, no status rows to check
    #: against. Computed on the corpus, NEVER on the matched subset (see the module docstring).
    NO_RULES = "no_rules"
    #: There was nothing to check: no cast, no entity, no target.
    NO_SUBJECT = "no_subject"
    #: The subject exists but its position on the reading axis could not be resolved, so a
    #: position-gated check could not run.
    NO_POSITION = "no_position"
    #: No DISTINCT judge model was available, so the check could not be confirmed by anything
    #: other than the model under test.
    NO_JUDGE = "no_judge"
    #: The check ran, but its INPUTS were degraded — the guard is fine, what it was fed is not.
    UNVERIFIED_INPUT = "unverified_input"
    #: The judge answered and the answer could not be used.
    UNPARSEABLE = "unparseable"
    #: A dependency was unavailable (knowledge outage, LLM down). Could not verify.
    DEGRADED = "degraded"
    #: The check raised. Distinct from DEGRADED: something is broken, not merely absent.
    FAILED = "failed"


#: Precedence for the derived headline, WORST FIRST. `NOT_APPLICABLE` is absent on purpose —
#: it is filtered out before ranking, because "not in scope" must not drag a report amber.
_RANK: tuple[CheckStatus, ...] = (
    CheckStatus.FAILED,
    CheckStatus.DEGRADED,
    CheckStatus.UNPARSEABLE,
    CheckStatus.UNVERIFIED_INPUT,
    CheckStatus.NO_JUDGE,
    CheckStatus.NO_POSITION,
    CheckStatus.NO_SUBJECT,
    CheckStatus.NO_RULES,
    CheckStatus.TRUSTED_CALLER,
    CheckStatus.CHECKED,
)


def worst(statuses: Any) -> CheckStatus:
    """The headline for a set of check statuses.

    `NOT_APPLICABLE` entries are dropped first. If nothing survives, the answer is
    `NOT_APPLICABLE` — a report where every check was out of scope is not "checked", and it is
    not amber either.
    """
    live = [s for s in (CheckStatus(x) for x in statuses) if s is not CheckStatus.NOT_APPLICABLE]
    if not live:
        return CheckStatus.NOT_APPLICABLE
    for rank in _RANK:
        if rank in live:
            return rank
    return CheckStatus.CHECKED  # unreachable while _RANK covers the enum; see the test


def check_over(corpus_size: int, *, degraded: bool = False) -> CheckStatus:
    """The status of a check whose scope is a corpus. Use this instead of writing the branch.

    `degraded` wins: a corpus that could not be READ is not an empty corpus, and reporting
    NO_RULES for an outage is the "nothing found" / "nothing was checked" conflation again.
    """
    if degraded:
        return CheckStatus.DEGRADED
    return CheckStatus.CHECKED if corpus_size > 0 else CheckStatus.NO_RULES


@dataclass
class GuardReport:
    """What a guard actually did, in a shape that cannot round up to a pass.

    ``findings`` is typed `Any` on purpose — this package must not pull in a service's finding
    model, and the nine finding types in this repo do not share a base. What they share is the
    honesty contract, which is what lives here.
    """

    checks: dict[str, CheckStatus] = field(default_factory=dict)
    findings: list[Any] = field(default_factory=list)
    #: What the guard concluded, BEFORE the honesty rule. Read it when you want to know what
    #: the guard thought; read `verdict` when you want to know what it PROVED.
    raw_verdict: bool | None = None

    def __post_init__(self) -> None:
        # Accept plain strings at the boundary (JSON, a DB row) and normalise once, so a
        # consumer never has to wonder whether it is comparing an enum or a string. An unknown
        # value raises here rather than silently ranking as CHECKED further down.
        self.checks = {k: CheckStatus(v) for k, v in (self.checks or {}).items()}

    @property
    def status(self) -> CheckStatus:
        return worst(self.checks.values())

    @property
    def verdict(self) -> bool | None:
        """`raw_verdict` iff the report as a whole is CHECKED, else None.

        A property rather than a rule in a docstring: the canon guard shipped
        ``resolved=True`` alongside ``status="skipped_no_cast"`` for months because the rule was
        a convention and conventions are what a busy caller drops.
        """
        return self.raw_verdict if self.status is CheckStatus.CHECKED else None

    @property
    def covered(self) -> list[str]:
        """The names of the checks that actually ran. Empty = nothing was verified."""
        return sorted(k for k, v in self.checks.items() if v is CheckStatus.CHECKED)

    @property
    def gaps(self) -> dict[str, CheckStatus]:
        """The checks that did NOT run, and why. `NOT_APPLICABLE` is excluded — it is not a gap.

        This is the field a UI banner should render: "nothing found" and "nothing was checked"
        become distinguishable without the reader having to know the enum.
        """
        return {k: v for k, v in self.checks.items()
                if v not in (CheckStatus.CHECKED, CheckStatus.NOT_APPLICABLE)}

    def to_dict(self) -> dict[str, Any]:
        """The wire shape. `status`/`verdict` are DERIVED and included, so a JSON consumer
        (a FE banner, a job envelope) gets the honest values without re-implementing the rules
        in TypeScript."""
        return {
            "status": str(self.status),
            "checks": {k: str(v) for k, v in self.checks.items()},
            "covered": self.covered,
            "gaps": {k: str(v) for k, v in self.gaps.items()},
            "verdict": self.verdict,
            "raw_verdict": self.raw_verdict,
        }
