"""V3 quality model — deterministic Issues + report (M1).

Pure data + scoring; no I/O. Persistence lives in the orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Severity → quality-score penalty (a chapter starts at 100).
_SEVERITY_PENALTY = {"high": 10, "med": 3, "low": 1}


@dataclass
class Issue:
    block_index: int
    type: str        # wrong_name | untranslated | number_mismatch | omission | repetition
    severity: str    # high | med | low
    detail: str
    expected: str | None = None
    detected_by: str = "rule"


@dataclass
class IssueReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def high(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "high"]

    def block_indices_with_high(self) -> set[int]:
        """Blocks a deterministic corrector should re-translate (M1b)."""
        return {i.block_index for i in self.high}

    def quality_score(self) -> int:
        penalty = sum(_SEVERITY_PENALTY.get(i.severity, 0) for i in self.issues)
        return max(0, 100 - penalty)
