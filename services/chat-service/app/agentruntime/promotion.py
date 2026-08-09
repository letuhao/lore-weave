"""CP-5.2 · rung 2 — **admission refuses to promote an incomplete contract.**

`CP-5.md` §4. chat-service cannot rewrite the Go services that serve most of the catalogue. It can
refuse to *promote* a declaration whose contract is incomplete — so an unmigrated tool registers
`draft`, never serves, and the pattern becomes mandatory **by consequence** rather than by memo.
That is why rung 2 is the whole enforcement and rungs 3–4 are a reference implementation.

🔴 **THIS MODULE BUILDS THE PROMOTER, NOT JUST THE GUARD, AND THAT IS THE FINDING THAT PRODUCED
IT.** `check_transition` documented `draft -> admitted` and had **zero production callers** —
`derive.py`'s own comment says *"reaching `admitted` is a deliberate move through
`check_transition`"*, and no such move existed anywhere. Measured 2026-08-09 by execution: the two
rows serving on the new arm were stamped `admitted` before derivation stopped self-releasing, and
re-running `scripts/agentruntime-admit.py` over them **rewrote both to `draft`** — so the only way
to admit a third declaration was a command that silently took the other two off the wire.

Adding a refusal to a promotion path nobody walks would have been the fourth instance in two days
of the shape this board keeps finding (`sweep_expired_runs` with no caller, `agentruntime_arm` with
no compose entry, `resolve_arguments` with no production caller). **A record and the place that
consumes it are ONE change**, so the move and the check that governs it land together.

**What promotion is NOT.** There is no `force=`, no `skip_contract=`, no `allow_incomplete=`.
`admission.admit` deliberately has none either, for the reason §6.4 gives: *a declaration that fails
admission is not patched into compliance and re-run — the failure is data about the contract.*
"""
from __future__ import annotations

from dataclasses import dataclass

from .contract import Declaration, check_transition
from .toolcontract import (
    Member, ToolContract, ToolContractViolation, resolve_contract, tool_contract_for,
)


@dataclass(frozen=True, slots=True)
class Completeness:
    """What a tool's declared contract covers, and what it does not.

    Returned WHOLE rather than as a boolean, for the reason `derive_all` returns its unresolved
    list: a producer that answered only *"is it complete?"* would report a refusal nobody can act
    on. `missing` names the members and `applicable` names the denominator, so a coverage figure
    computed from this can never be self-derived.
    """

    tool: str
    version: str
    applicable: tuple[str, ...]
    declared: tuple[str, ...]
    missing: tuple[str, ...]
    #: Members the tool declares that this generation does not define. An unknown member is a
    #: REFUSAL, not a shrug: it is either a typo that silently satisfies nothing, or a member from a
    #: generation this runtime cannot validate.
    unknown: tuple[str, ...]
    #: Why each applicable conditional member applied, for a report that has to explain itself.
    because: tuple[tuple[str, str], ...]
    #: `_meta` | `registry` | `none` — WHICH source supplied the contract. Recorded rather than
    #: merged, so a contract the owning service published and one we authored in the interim never
    #: become the same indistinguishable row.
    source: str = "none"

    @property
    def is_complete(self) -> bool:
        return not self.missing and not self.unknown


def _member_satisfied(tool: str, member: Member, payload: object) -> str | None:
    """A member is satisfied when it is declared with SOMETHING TO SAY. Returns a problem or None.

    🔴 **AN EMPTY DECLARATION IS NOT A DECLARATION.** `"repeat_semantics": {}` and
    `"repeat_semantics": null` would both pass a mere key-presence check while telling every reader
    nothing, and a contract satisfiable by typing the key is the *"documented in a docstring"*
    failure this checkpoint exists to end. The shape a member's payload takes is the member's own
    business (5.3…5.10 each define theirs); what is refused here, uniformly, is emptiness.
    """
    if payload is None:
        return "is declared as null"
    if isinstance(payload, (dict, list, tuple, str)) and len(payload) == 0:
        return "is declared empty, which states nothing"
    if payload is False:
        return "is declared `false`; a member is a statement, not a flag to switch off"
    return None


def check_tool_contract(tool_def: dict, *, version: str | None = None,
                        registry: dict | None = None) -> Completeness:
    """Which members apply to this tool, and which of them it actually declares.

    Pure. Raises only when the tool names a contract GENERATION this runtime does not hold, because
    that is a question about this code rather than about the tool.
    """
    from .toolcontract import TOOL_CONTRACT_VERSION

    contract: ToolContract = tool_contract_for(version or TOOL_CONTRACT_VERSION)
    fn = tool_def.get("function") if type(tool_def) is dict else None
    name = (fn if type(fn) is dict else tool_def if type(tool_def) is dict else {}).get("name")
    tool = name if type(name) is str else str(name)

    block, source = resolve_contract(tool_def, registry)
    applicable = contract.required_for(tool_def)
    known = contract.by_name()

    declared = tuple(k for k in block if k in known)
    unknown = tuple(sorted(k for k in block if k not in known))
    missing: list[str] = []
    for m in applicable:
        if m.name not in block:
            missing.append(m.name)
            continue
        problem = _member_satisfied(tool, m, block[m.name])
        if problem is not None:
            missing.append(m.name)

    return Completeness(
        tool=tool,
        version=contract.version,
        applicable=tuple(m.name for m in applicable),
        declared=declared,
        missing=tuple(missing),
        unknown=unknown,
        because=tuple((m.name, m.trigger_name or "core — applies to every tool")
                      for m in applicable),
        source=source,
    )


def promote(declaration: Declaration, tool_def: dict, *,
            version: str | None = None, registry: dict | None = None) -> Declaration:
    """`draft -> admitted`, and **the only way a declaration reaches a served lifecycle.**

    Two gates, in this order:

    1. `check_transition` — the move itself must be legal. Kept in `contract.py` because the writer
       is not the only mover, and enforcing it at one hand is a rule the other hands do not have.
    2. **rung 2** — the tool's `_meta.contract` must cover every member that applies to it.

    Raises `ToolContractViolation` naming every missing member at once. Reporting one at a time
    would make a migration a guessing loop, and C-12 requires the rejection to name what would be
    legal.
    """
    check_transition(declaration.id, declaration.lifecycle, "admitted")
    report = check_tool_contract(tool_def, version=version, registry=registry)
    if not report.is_complete:
        detail = []
        if report.missing:
            detail.append(f"missing {list(report.missing)}")
        if report.unknown:
            detail.append(f"declares unknown member(s) {list(report.unknown)}")
        raise ToolContractViolation(
            report.tool, "|".join(report.missing) or "|".join(report.unknown),
            " and ".join(detail),
            f"every applicable member of tool contract {report.version}: "
            f"{list(report.applicable)} — a tool that does not implement the pattern is registered "
            f"`draft` and never reaches the wire (CP-5 §4 rung 2)")
    return Declaration(
        id=declaration.id,
        kind=declaration.kind,
        source_path=declaration.source_path,
        lifecycle="admitted",
        members=declaration.members,
    )


def coverage(catalogue: list[dict], *, version: str | None = None,
             registry: dict | None = None) -> dict:
    """How much of the LIVE catalogue could be promoted today, denominator from the input.

    Reported as data so a gate can assert on it, and so the figure is never typed. `by_member`
    names which member defeats how many tools, because *"3% promotable"* is not actionable and
    *"every tool omits `error_contract`"* is.
    """
    total = len(catalogue)
    complete = 0
    by_member: dict[str, int] = {}
    triggered: dict[str, int] = {}
    for td in catalogue:
        report = check_tool_contract(td, version=version, registry=registry)
        for m in report.applicable:
            triggered[m] = triggered.get(m, 0) + 1
        if report.is_complete:
            complete += 1
        for m in report.missing:
            by_member[m] = by_member.get(m, 0) + 1
        for m in report.unknown:
            by_member[f"unknown:{m}"] = by_member.get(f"unknown:{m}", 0) + 1
    return {
        "total": total,
        "promotable": complete,
        "blocked": total - complete,
        "blocked_by_member": dict(sorted(by_member.items(), key=lambda kv: -kv[1])),
        "member_applies_to": dict(sorted(triggered.items(), key=lambda kv: -kv[1])),
    }
