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
    """C-0, assembled — never authored as a block.

    🔴 **`contract_version` was removed from here, not relocated.** It held the running build's
    constant, the manifest stopped using it once the row learned to record `admitted_against`, and
    its only remaining reader was a test asserting it was truthy. Round 2 named it a dead field;
    the first fix moved the deadness one type over instead of ending it. **A field kept because
    removing it feels lossy is a field the next reader will trust.** The build's version is
    `CONTRACT_VERSION`, available directly and belonging to the module rather than to an identity.
    """

    id: str
    owning_service: str
    lifecycle: str


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


#: The fields a manifest row may carry — **exactly these, no more**.
#:
#: 🔴 **THE CLASS OF DEFECT THIS CLOSES, AND WHY BOUNDING TYPES DID NOT.** Two rounds were spent
#: bounding row VALUES, and both times the vehicle was a plain scalar that walked through: a
#: hand-typed `"cost": 1000000000` steered `TakeWhileBudget`, `"relevance"` steered `OrderBy`. No
#: type bound can help, because those values are *well-typed* — the defect is that the row carries a
#: field **the contract never defined**, and every stage kind will happily rank on whatever it is
#: handed.
#:
#: So the rule stops being about the value and becomes about the SCHEMA: a row carrying an unknown
#: key **passed no clause**, which is the same sentence `UntrustedRow` already exists for. `lane`,
#: `tier`, `cost` and `relevance` are therefore refused today **on purpose** — §0.14.1c records them
#: as UNBUILT with CP-2/CP-4 owning their producers, and a door that accepted them would be letting
#: an unbuilt capability in through the back.
ROW_FIELDS: dict[str, tuple] = {
    "id": (str,),
    "kind": (str,),
    "owning_service": (str,),
    "lifecycle": (str,),
    "contract_version": (str,),
    "admitted_against": (str,),
    "members": (list, tuple),
    # 🔴 **THE RANKING FIELDS, AND THE HONEST LINE ABOUT THEM.** A verifier showed a hand-typed
    # `"cost": 1000000000` steering `TakeWhileBudget` and asked for it to be closed. It **cannot be
    # closed by a value bound**: `1000000000` is a well-typed integer, and no rule distinguishes a
    # forged cost from a real one. That is the **hand-edited-manifest** threat, and this design
    # already records its only answer — a document digest, §6.4.2, **not taken** because it trades
    # re-validation for tamper-evidence.
    #
    # What IS closable, and what the finding actually contained, is an **undefined** field: a row
    # carrying a key the contract never named passed no clause for it, and every stage will rank on
    # whatever it is handed. So these are named and bounded; anything else is refused.
    #
    # §0.14.1c records their producers as CP-2 (`relevance`) and CP-4 (`lane`, `tier`, `cost`), so a
    # row carrying one today came from somewhere those checkpoints have not built yet — which is
    # worth knowing and is not, by itself, a forgery.
    "lane": (str,),
    "tier": (str,),
    "cost": (int,),
    "relevance": (int,),
}
#: Fields a row must carry. `members` is required rather than defaulted: `r.get("members", ()) or ()`
#: served **absent, `null`, `0` and `false`** as "no members", so the M5 reference check silently had
#: nothing to check.
ROW_REQUIRED = frozenset({"id", "kind", "owning_service", "lifecycle", "members"})


def check_row_shape(row, where: str) -> None:
    """One definition of a valid manifest row, for **every** door.

    🔴 There were two: `rows_of` bounded fields and `validate_document` bounded none, so `load()`
    accepted a row the assembler then refused — **with a different exception type**. Two definitions
    of the same thing in one package is the failure `UntrustedRow`'s own docstring is about, and it
    arrived because a fix was applied at the door a verifier had named.

    Raises `ContractViolation`, which per C-12 names the field path, the reason, and what would be
    accepted — never "invalid".
    """
    rid = row.get("id") if type(row) is dict else None
    if type(row) is not dict:
        raise ContractViolation("", where, f"is a {type(row).__name__}", "a plain JSON object")
    for key in row:
        if type(key) is not str:
            raise ContractViolation(rid or "", where, f"has a non-string key {key!r}",
                                    "string keys only")
        if key not in ROW_FIELDS:
            raise ContractViolation(
                rid or "", f"{where}.{key}",
                "is a field the contract does not define, so the row passed no clause for it and "
                "every ranking stage will happily order on whatever it is handed",
                f"one of {sorted(ROW_FIELDS)}")
    for key in sorted(ROW_REQUIRED):
        if key not in row:
            raise ContractViolation(rid or "", f"{where}.{key}", "is missing",
                                    f"every row carries {sorted(ROW_REQUIRED)}")
    for key, val in row.items():
        want = ROW_FIELDS[key]
        if not any(type(val) is w for w in want):
            raise ContractViolation(
                rid or "", f"{where}.{key}", f"is a {type(val).__name__}",
                f"exactly {' or '.join(w.__name__ for w in want)}")
    for m in row["members"]:
        if type(m) is not str or not m:
            raise ContractViolation(
                rid or "", f"{where}.members", f"contains {m!r}",
                "non-empty declaration ids; each member is a foreign key (C-11 / M5)")


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
    """C-0 for an admitted declaration. Derives rather than reads the owner, every time."""
    return Identity(
        id=declaration.id,
        owning_service=derive_owning_service(declaration.source_path),
        lifecycle=declaration.lifecycle,
    )
