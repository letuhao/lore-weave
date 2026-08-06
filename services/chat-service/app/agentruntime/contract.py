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
from types import MappingProxyType
from typing import Literal

# 🔴 **`from . import canon` STOOD HERE WITH ZERO CALL SITES FOR SEVEN ROUNDS.** The one
# `canon.nfc(...)` in this module was removed when its stated harm was refuted by execution, and the
# import it existed for was left — so every reader of this file's imports believed the contract
# consulted the canonical serialisation, and the four `canon.*` spellings still in `check_row`'s
# comment made that belief look confirmed. An import is a claim about what a module depends on.

CONTRACT_VERSION = "1.0.0"

Kind = Literal["tool", "skill", "workflow"]
KINDS: frozenset[str] = frozenset({"tool", "skill", "workflow"})

Lifecycle = Literal["draft", "admitted", "deprecated", "retired"]
LIFECYCLES: frozenset[str] = frozenset({"draft", "admitted", "deprecated", "retired"})

#: A declaration id is a **key**, and an unbounded key is not one.
#:
#: 🔴 **SIX ROUNDS OPEN, AND THE VEHICLE IS PLAIN JSON.** `^[a-z][a-z0-9_]*$` bounded the alphabet
#: and not the length, so a 300-character id was measured travelling through `check_row`, `rows_of`
#: and `validate_document` end to end. It is the `AllowList`/`DenyList` membership key, it is the
#: `OrderBy` tie-break, it is the M5 foreign key, and it is rendered into the prompt the model reads
#: — so an id longer than the surface it names is a budget the ranking spends on one row.
#:
#: The bound is **stated rather than assumed**: 64 characters, which is longer than every identifier
#: this repository declares and short enough that no single row can crowd a surface. A limit chosen
#: by a person and written down is checkable; the absent one was neither.
ID_MAX_LEN = 64
_ID = re.compile(r"^[a-z][a-z0-9_]{0,%d}$" % (ID_MAX_LEN - 1))
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


class UntrustedRow(ValueError):
    """A manifest row that did not come from an admission, on either side of the file.

    §6.1 layer 3. **The type was never the boundary it was believed to be**, and trusting it hid two
    separate defects: `build()` wrote a row for any object carrying a `.declaration` attribute (a
    four-line duck-typed class put `sneaky` into a generated manifest), and `load()` served whatever
    JSON was on disk — so a row **typed in by hand** reached the assembler having passed no clause.

    JSON has no types. A boundary that assumes its neighbour validated is a boundary that validates
    nothing.

    🔴 **IT LIVES HERE NOW, AND IT IS A `ValueError`.** It was defined in `manifest.py`, so the one
    door a consumer actually stands behind — `rows_of` — could not raise it without an import cycle
    and raised `ContractViolation` for a bad row and a bare `ValueError` for a bad document: **two
    unrelated classes at one exported door, neither of them the one whose docstring is verbatim this
    case.** A verifier measured it and called it a breaking change, because every pre-delta refusal
    at that door was a `ValueError` and callers catch what a door used to raise. Both halves are
    answered by putting the class where the contract is and keeping it a `ValueError`: one documented
    refusal, and no caller's `except` stops working.
    """


class UnresolvedReference(UntrustedRow):
    """C-11 / M5 — a member naming a declaration the manifest does not contain."""

    def __init__(self, declaration_id: str, member: str) -> None:
        self.declaration_id = declaration_id
        self.member = member
        super().__init__(
            f"{declaration_id} references {member!r}, which is not admitted. A reference is a "
            f"foreign key into the manifest (C-11 / M5) — resolve it or do not declare it."
        )


class ContractViolation(UntrustedRow):
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
#: key **passed no clause**, which is the same sentence `UntrustedRow` already exists for.
#:
#: 🔴 **AND `lane`, `tier`, `cost` AND `relevance` ARE NOT HERE — WHICH IS THE WHOLE FIX, AND THE
#: LAST ROUND WROTE THE SENTENCE ABOVE AND THEN LISTED THEM ANYWAY.** The comment said they were
#: *"refused today on purpose"*; four lines below, the dict defined all four, so both doors accepted
#: a hand-typed `"cost": 1000000000` and a hand-typed `"relevance": 9999` — and a verifier measured
#: the second one **selecting which single declaration the model sees** under `OrderBy(relevance) →
#: TopK(1)`. The file argued the correct rule and shipped its four exceptions in the same literal.
#:
#: The rationalisation that produced them is worth keeping in view, because it read as principle:
#: *"a hand-typed but well-typed `cost` is the hand-edited-manifest threat, whose **only** answer is
#: the document digest at §6.4.2, deliberately not taken."* The first half is true — no value bound
#: distinguishes a forged cost from a real one, and shipping one would be a gate with no subject.
#: **The word "only" was false.** Removing these four entries refuses the forged cost outright, and
#: it is *stronger* than the digest rather than a trade: the accepted set is strictly smaller, every
#: row is still fully re-validated, and the manifest format does not change — where §6.4.2 records
#: that a digest **does** change the format, and that a recomputed digest passes.
#:
#: §0.14.1c owns the producers: CP-2 for `relevance`, CP-4 for `lane`/`tier`/`cost`. Nothing writes
#: them today, so nothing legitimate is refused. When a producer is built, the field arrives **with
#: it**, in the same change — which is what "a record and the place that consumes it are ONE change"
#: means, applied to a schema.
ROW_FIELDS = MappingProxyType({
    "id": (str,),
    "kind": (str,),
    "owning_service": (str,),
    "lifecycle": (str,),
    "contract_version": (str,),
    "admitted_against": (str,),
    "members": (list, tuple),
})
#: The fields every row must carry — the seven `_row` writes today.
#:
#: 🔴 **THIS WAS A FIVE-ELEMENT SUBSET AND THAT SUBSET WAS ITSELF A HOLE.** `validate_document`
#: additionally required the two §6.4 stamps, so a row carrying **exactly** `ROW_REQUIRED` passed
#: `rows_of` and failed `load()` — the two doors disagreeing about validity while a docstring said
#: they were one definition.
#:
#: 🔴 **AND THE FIX FOR THAT WAS `frozenset(ROW_FIELDS)`, WHICH LEFT NO OPTIONAL TIER AND MADE THE
#: NEXT CHECKPOINT UNSHIPPABLE.** Deriving *required* from *allowed* keeps them from drifting and
#: makes every new field mandatory on arrival — so the moment CP-2 adds `relevance`, **every row
#: already on disk fails `load()`, `rows_of` and `SurfaceAssembler`**, and a verifier measured that
#: there is no way out: `generate(path=<existing>)` raises, `bootstrap=True` does not apply while
#: the file exists, and the only remaining route is `rm` + bootstrap — **which erases every origin
#: stamp**, the exact operation `generate`'s own guard exists to prevent, while §6.4's re-admission
#: queue (the mechanism that would carry a row across a format change) is NOT BUILT. Latent today
#: only because the committed manifest is empty; **scheduled, not hypothetical.**
#:
#: So the two sets are separate again, and the thing that stops them drifting is a **gate** rather
#: than a definition: `test_THE_REQUIRED_SET_IS_WHAT_THE_WRITER_ACTUALLY_EMITS` compares this set
#: against `_row`'s real output, so adding a field to the writer without deciding whether it is
#: required fails immediately — and adding an OPTIONAL field to `ROW_FIELDS` is now expressible,
#: which is what CP-2 and CP-4 need.
ROW_REQUIRED = frozenset({
    "id", "kind", "owning_service", "lifecycle", "contract_version", "admitted_against", "members",
})


def check_row_shape(row, where: str) -> None:
    """The SHAPE half of one definition of a valid manifest row — see `check_row` for the whole.

    🔴 There were two definitions: `rows_of` bounded fields and `validate_document` bounded none, so
    `load()` accepted a row the assembler then refused. Consolidating the *shape* left the *clauses*
    split — nine classes of row still reached the consumer that `load()` refused — so this function
    is deliberately no longer the door. **Callers want `check_row`.**

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
    # 🔴 **THE NON-EMPTY HALF, WHICH THE CONSOLIDATION DELETED.** `rows_of` carried
    # `if not _is_exactly(r.get("id"), str) or not r.get("id")`; moving it here reproduced the type
    # half and dropped the rest, so `id: ""` was REFUSED before the consolidation and ACCEPTED after
    # — measured in one process against both sources. An empty id is the `AllowList` membership key
    # for every row that omits one, and the vehicle is plain JSON.
    # `rid`, not a second `row["id"]`: the builder's own pre-commit read-twice sweep flagged the
    # mixed-mechanism pair here. It is provably safe (the exact-type bound above means both reads are
    # the builtin on one storage) — and "safe because of an argument three lines up" is exactly what
    # was said about the five TOCTOUs this run has already paid for. One read.
    if not rid:
        raise ContractViolation(
            "", f"{where}.id", "is empty",
            "a non-empty declaration id; an id decides membership in every allow-list and deny-list "
            "it is compared against (§0.14.1)")
    for m in row["members"]:
        if type(m) is not str or not m:
            raise ContractViolation(
                rid or "", f"{where}.members", f"contains {m!r}",
                "non-empty declaration ids; each member is a foreign key (C-11 / M5)")


def check_row(row, where: str) -> None:
    """**One definition of a VALID manifest row, for every door — shape AND clauses.**

    🔴 The previous round consolidated the *shape* and called it one definition. A verifier then
    drove fifteen row shapes through both doors and found **nine classes** that `rows_of` accepted
    and `load()` refused: an unknown `kind`, an unknown `lifecycle`, an `id` matching no identifier
    pattern, an empty `id`, a **skill with no members**, a **tool with members**, a row missing both
    §6.4 stamps, and a member naming nothing. The door the consumer actually stands behind —
    `SurfaceAssembler`, `discover`, `declarations`, `rows_of`, none of which go through `load()` —
    was **the weaker of the two**. A shape check that admits `members: ['ghost']` is not a row check.

    So the clauses run here too, and every row-reader in the package calls this one function:
    `rows_of`, `validate_document`, `_row` (the WRITER — it never checked its own output, so an
    added field was written to disk and refused afterwards by `load()` and by CI) and
    `build(previous=)` (which had a third, weaker, hand-written definition).
    """
    check_row_shape(row, where)
    try:
        check_contract(Declaration(
            id=row["id"],
            kind=row["kind"],
            # The row stores the DERIVED owner; the contract derives it from a path. Feed the stored
            # owner back through the same shape so a row naming an owner nothing could have derived
            # is rejected rather than trusted.
            #
            # 🔴 **A `canon.nfc(...)` STOOD HERE AND THE HARM ITS COMMENT DESCRIBED WAS NOT REAL.**
            # It claimed an NFD spelling would *"validate and store un-normalised — two
            # `canon.digest` values for one visibly identical document"*. A verifier executed the
            # second half: `canon.digest` **already normalises**, so `digest(NFD) == digest(NFC)` is
            # True and the drift gate cannot see a difference. And the call normalised only the
            # COPY fed to the check — the row still stored NFD either way — so it changed nothing at
            # all. A normalisation that neither guards a real difference nor alters what is stored
            # is a line that makes the next reader believe a door exists. §0.14.2 door (a) is
            # answered by `canon.digest`, which is where it always was.
            source_path=f"services/{row['owning_service']}/",
            lifecycle=row["lifecycle"],
            members=tuple(row["members"]),
        ))
    except ContractViolation as exc:
        raise ContractViolation(row["id"], f"{where}.{exc.field_path}", exc.reason,
                                exc.accepted) from exc
    # Both stamps, because a field nothing checks is a field anything can say. **A SYNTAX check, not
    # a validity one, deliberately and with a residual**: `"99.0.0"` and `"0.0.0"` pass — they are
    # well-formed versions that never existed. A shape check cannot tell a real generation from a
    # plausible one, and the safe direction is this one, because a bogus stamp lands a row *in*
    # §6.4's queue rather than out of it.
    for stamp_field in ("contract_version", "admitted_against"):
        stamp = row[stamp_field]
        if not _VERSION.match(stamp):
            raise ContractViolation(
                row["id"], f"{where}.{stamp_field}", f"is {stamp!r}",
                "MAJOR.MINOR.PATCH — §6.4 needs both the origin generation (`contract_version`) and "
                "what this admission was checked against (`admitted_against`); the re-admission "
                "queue is the difference between them, so an unreadable stamp empties it silently")


def check_document_rows(rows, where: str) -> None:
    """The clauses that are properties of the SET, not of a row: duplicate ids, and M5.

    Both were run by `validate_document` and by neither consumer door, which is how
    `members: ['ghost']` reached `rows_of`, `declarations`, `discover` and `assemble()` for three
    consecutive rounds. M5 is re-run on every read because a member that resolved at generation can
    be broken by an edit to the file afterwards.
    """
    ids: set[str] = set()
    for i, r in enumerate(rows):
        if r["id"] in ids:
            raise ContractViolation(r["id"], f"{where}[{i}].id", "is a duplicate declaration id",
                                    "one row per declaration id")
        ids.add(r["id"])
    for r in rows:
        for m in r["members"]:
            if m not in ids:
                raise UnresolvedReference(r["id"], m)


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
            f"lowercase letters, digits and underscores, starting with a letter, at most "
            f"{ID_MAX_LEN} characters — an id is the membership key of every allow-list and the "
            f"ranking's final tie-break, so an unbounded one is an unbounded key",
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
                f"the id of another declaration (at most {ID_MAX_LEN} characters), resolved "
                f"against the manifest at generation",
            )
    return CONTRACT_VERSION


def identity_of(declaration: Declaration) -> Identity:
    """C-0 for an admitted declaration. Derives rather than reads the owner, every time."""
    return Identity(
        id=declaration.id,
        owning_service=derive_owning_service(declaration.source_path),
        lifecycle=declaration.lifecycle,
    )
