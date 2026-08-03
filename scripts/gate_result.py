#!/usr/bin/env python3
"""Emit a LoreWeave gate result in the shared `aif-gate-result` shape.

WHY THIS IS THEIR SCHEMA AND NOT OURS
-------------------------------------
This repo has 48 gate scripts. Each prints prose, in its own format, and the workflow
gate records free-text evidence strings. That is readable by a human reading one gate
and by nothing else — an orchestrator (a CI leg, a Codex run, a Claude session chaining
phases) cannot tell "blocked" from "warned" without a per-gate parser.

AI Factory already solved this, better than we had: a human-readable report first, then
ONE final fenced `aif-gate-result` JSON block carrying `status` / `blocking` / stable
finding ids / `affected_files` / `suggested_next`. The contract lives at
`.codex/skills/aif-verify/references/GATE-RESULT-CONTRACT.md`.

Rather than invent a parallel LoreWeave schema, we adopt theirs, so a gate written here
is consumable by whichever agent a contributor runs. Our contribution flows the other
way: the CONTENT of the checks — the invariants those 48 gates encode.

Usage from a gate script:

    from gate_result import GateResult

    result = GateResult(gate="review", suggested_command="/aif-fix")
    result.blocker(id="tenancy-1", summary="books table has no owner scope",
                   file="services/book-service/migrations/003.sql")
    print(result.render())        # human summary + the fenced JSON block
    sys.exit(result.exit_code())

Only the four gate names the contract defines are valid (`verify`, `review`, `security`,
`rules`); a LoreWeave-specific gate maps onto the closest one rather than inventing a
fifth, because an orchestrator switching on an unknown value is exactly the silent
no-op this repo keeps paying for.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

# The contract's closed sets. Enumerated here so a typo fails loudly at emit time
# instead of producing JSON an orchestrator silently ignores.
GATES = ("verify", "review", "security", "rules")
SEVERITIES = ("error", "warning")
STATUSES = ("pass", "warn", "fail")
SUGGESTED_COMMANDS = (
    "/aif-fix", "/aif-rules", "/aif-architecture", "/aif-roadmap", "/aif-commit", None,
)
SCHEMA_VERSION = 1


@dataclass
class Finding:
    id: str
    summary: str
    severity: str = "error"
    file: str | None = None

    def as_dict(self) -> dict:
        d: dict = {"id": self.id, "severity": self.severity, "summary": self.summary}
        if self.file:
            d["file"] = self.file
        return d


@dataclass
class GateResult:
    gate: str
    suggested_command: str | None = None
    suggested_reason: str | None = None
    findings: list[Finding] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.gate not in GATES:
            raise ValueError(f"gate must be one of {GATES}, got {self.gate!r}")
        if self.suggested_command not in SUGGESTED_COMMANDS:
            raise ValueError(
                f"suggested_command must be one of {SUGGESTED_COMMANDS}, "
                f"got {self.suggested_command!r}"
            )

    def blocker(self, *, id: str, summary: str, file: str | None = None,
                severity: str = "error") -> None:
        if severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}, got {severity!r}")
        self.findings.append(Finding(id=id, summary=summary, severity=severity, file=file))
        if file and file not in self.affected_files:
            self.affected_files.append(file)

    def note(self, message: str) -> None:
        """An INFORMATIONAL line for the human summary. Never enters `blockers`, and
        deliberately does not move `status` — a gate that passed cleanly must report
        `pass`, not `warn`, or an orchestrator learns to ignore `warn` entirely."""
        self.notes.append(message)

    def warn(self, message: str) -> None:
        """A non-blocking WARNING: worth a human's attention, not worth blocking."""
        self.notes.append(message)
        self._warned = True

    @property
    def status(self) -> str:
        if self.findings:
            return "fail"
        return "warn" if getattr(self, "_warned", False) else "pass"

    def exit_code(self) -> int:
        return 1 if self.findings else 0

    def render(self) -> str:
        lines: list[str] = []
        if self.findings:
            lines.append(f"{self.gate}-gate: FAIL — {len(self.findings)} blocking finding(s).\n")
            for f in self.findings:
                where = f" [{f.file}]" if f.file else ""
                lines.append(f"  ({f.severity}) {f.id}{where}: {f.summary}")
        else:
            lines.append(f"{self.gate}-gate: OK — no blocking findings.")
        for n in self.notes:
            lines.append(f"  note: {n}")

        payload = {
            "schema_version": SCHEMA_VERSION,
            "gate": self.gate,
            "status": self.status,
            "blocking": bool(self.findings),
            "blockers": [f.as_dict() for f in self.findings],
            "affected_files": self.affected_files,
            "suggested_next": {
                "command": self.suggested_command,
                "reason": self.suggested_reason,
            },
        }
        lines.append("")
        lines.append("```aif-gate-result")
        lines.append(json.dumps(payload, indent=2, ensure_ascii=False))
        lines.append("```")
        return "\n".join(lines)
