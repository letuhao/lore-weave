"""CP-1.6 · C-0 identity, and the contract check `admit()` runs.

`ARCHITECTURE.md` §4.1. **C-0 exists because M4 was gated on C-1…C-12 and identity was in none of
them** — so the first admitted declaration would have had no id, no owner and no lifecycle. There is
no CODEOWNERS file and no `owner` key anywhere in this repository; nothing would have noticed.

**CP-1 checks C-0 and the structural clauses only.** C-3…C-17 are per-kind contract clauses whose
subjects (arguments, results, error classes) do not exist until a declaration is written, and CP-4
admits the first one. Claiming to enforce them here would produce seven gates with no subject —
the vacuity failure this run has a standard about. What CP-1 owes is the **frame**: identity,
kind, and references that resolve.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

CONTRACT_VERSION = "1.0.0"

Kind = Literal["tool", "skill", "workflow"]
KINDS: frozenset[str] = frozenset({"tool", "skill", "workflow"})

Lifecycle = Literal["draft", "admitted", "deprecated", "retired"]
LIFECYCLES: frozenset[str] = frozenset({"draft", "admitted", "deprecated", "retired"})

_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class ContractViolation(Exception):
    """A declaration that does not satisfy the contract. Carries the field path, per C-12.

    C-12: *name the field path rejected, the reason, and what would be accepted.* The measured
    defect behind it — a misspelled key dropped by a Go typed struct and reported as *"missing
    required"* — is a message that blames the caller for something the server did. So a violation
    here always says which field, and never says "invalid".
    """

    def __init__(self, declaration_id: str, field_path: str, reason: str, accepted: str) -> None:
        self.declaration_id = declaration_id
        self.field_path = field_path
        self.reason = reason
        self.accepted = accepted
        super().__init__(f"{declaration_id or '<no id>'}.{field_path}: {reason}. Accepted: {accepted}")


@dataclass(frozen=True, slots=True)
class Declaration:
    """An **untrusted** declaration. Being one of these means nothing; `admit()` is the boundary.

    `owning_service` is absent BY DESIGN — C-0 requires it **derived, never authored**. A field a
    declaration can state is a claim about ownership, not a fact about it, and this repository has
    no CODEOWNERS to check such a claim against. It is derived from `source_path` instead.
    """

    id: str
    kind: Kind
    source_path: str
    lifecycle: Lifecycle = "draft"
    # S and W only: the declarations this one references. C-11 / M5 — every member is a foreign key
    # into the manifest. Today 12 rails point at 30 dead tools behind a gate that fails open.
    members: tuple[str, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class Identity:
    """C-0, assembled — never authored as a block."""

    id: str
    owning_service: str
    lifecycle: str
    contract_version: str


def derive_owning_service(source_path: str) -> str:
    """C-0's *derived, never authored*. The owner is **where the code lives**, which cannot be
    misstated by the declaration.

    `services/<name>/…` → `<name>`. A path outside `services/` has no owning service and that is a
    contract violation rather than a default: `unknown` would be a plausible-looking value for a
    question nobody answered, and this run has paid repeatedly for those.
    """
    parts = Path(source_path.replace("\\", "/")).parts
    if "services" in parts:
        i = parts.index("services")
        if i + 1 < len(parts):
            return parts[i + 1]
    return ""


def check_contract(declaration: Declaration) -> str:
    """Run every clause CP-1 owns. Returns the contract version on success; raises on the first
    failing clause with its field path.

    Called ONLY from `admission.admit`. It is not exported for direct use: a caller that can run
    the check separately from construction is a caller that can skip it, which is exactly the
    14-of-58 shape M4 replaces.
    """
    d = declaration

    if not isinstance(d.id, str) or not _ID.match(d.id or ""):
        raise ContractViolation(
            getattr(d, "id", ""), "id",
            "not a stable identifier",
            "lowercase letters, digits and underscores, starting with a letter",
        )
    if d.kind not in KINDS:
        raise ContractViolation(
            d.id, "kind", f"unknown kind {d.kind!r}", f"one of {sorted(KINDS)}",
        )
    if d.lifecycle not in LIFECYCLES:
        raise ContractViolation(
            d.id, "lifecycle", f"unknown lifecycle {d.lifecycle!r}", f"one of {sorted(LIFECYCLES)}",
        )
    owner = derive_owning_service(d.source_path)
    if not owner:
        raise ContractViolation(
            d.id, "source_path",
            f"owning service cannot be derived from {d.source_path!r}",
            "a path under services/<name>/ — C-0 requires the owner derived, never authored",
        )
    if d.kind == "tool" and d.members:
        raise ContractViolation(
            d.id, "members",
            "a tool has no members; only skills and workflows reference other declarations",
            "an empty members tuple",
        )
    if d.kind in ("skill", "workflow") and not d.members:
        raise ContractViolation(
            d.id, "members",
            "a skill or workflow with no members references nothing and can never resolve",
            "at least one declaration id, which M5 resolves against the manifest",
        )
    for i, m in enumerate(d.members):
        if not isinstance(m, str) or not _ID.match(m or ""):
            raise ContractViolation(
                d.id, f"members[{i}]", f"not a declaration id: {m!r}",
                "the id of another declaration, resolved against the manifest at generation",
            )
    return CONTRACT_VERSION


def identity_of(declaration: Declaration) -> Identity:
    """C-0 for an admitted declaration. Derives rather than reads the owner, every time.

    ⚠️ `Identity.contract_version` is **the constant this build carries**, not the version any
    particular declaration was admitted against. It is a property of the *running code*, and the
    manifest deliberately does **not** use it for a row: a row records `admitted_against`, taken
    from the `Admitted` object that captured it at admission time. Binding this constant per-row was
    a live P4 violation — see `manifest._row`.
    """
    return Identity(
        id=declaration.id,
        owning_service=derive_owning_service(declaration.source_path),
        lifecycle=declaration.lifecycle,
        contract_version=CONTRACT_VERSION,
    )
