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


@dataclass(frozen=True, slots=True)
class Contract:
    """CP-4 · **the contract as versioned DATA, which is what §6.4 has been blocked on.**

    §6.4.1 states the problem exactly: for `admitted_against` to differ from the document's version
    the manifest must hold a row **this build did not admit** — a grandfathered one — and *"a
    grandfathered row is by definition one the CURRENT contract may reject, so `load()` cannot
    re-check it against the current contract; it would have to be checked against the contract it
    was admitted under. This code has only the current contract, as code."*

    That last sentence is the whole blocker, and it is a sentence about a *representation*. A
    function cannot be indexed by version; a record can. So the clause PARAMETERS move out of the
    function body and into one of these, `check_contract_against(d, version)` becomes expressible,
    and a grandfathered row is **genuinely re-validated** rather than exempted — which is the hole
    §6.4.1 says exempting would open (*"a hand-typed row and a grandfathered row are
    indistinguishable from the file alone"*).

    🔴 **WHAT THIS DOES AND DOES NOT CLOSE.** A grandfathered row is now checked against a real,
    named contract instead of being skipped — so *"skips the current check"* no longer implies
    *"unchecked"*. It does **not** make a hand-typed row detectable: one that claims an older
    version and satisfies that version's clauses is a validly-shaped declaration, and telling it
    from a genuine one needs the document digest §6.4.2 records as **deliberately not taken**.
    Option A was rejected there for trading re-validation for tamper-evidence; this adds the
    re-validation and leaves the tamper question exactly where the PO left it.

    `breaking_from` is what makes an amendment's KIND data rather than a judgement: a
    backward-compatible amendment leaves prior admissions standing, a breaking one puts them in the
    re-admission queue. Recording it on the contract means nobody has to remember which kind they
    just shipped.
    """

    version: str
    #: The predecessor this version BREAKS compatibility with, or None for a compatible amendment
    #: (and for the first contract, which breaks nothing).
    breaking_from: str | None
    kinds: frozenset[str]
    lifecycles: frozenset[str]
    id_max_len: int
    id_pattern: str

    def id_re(self) -> re.Pattern:
        return re.compile(self.id_pattern)

Kind = Literal["tool", "skill", "workflow"]
KINDS: frozenset[str] = frozenset({"tool", "skill", "workflow"})

Lifecycle = Literal["draft", "admitted", "deprecated", "retired"]
LIFECYCLES: frozenset[str] = frozenset({"draft", "admitted", "deprecated", "retired"})

#: 🔴 **WHICH LIFECYCLES REACH A MODEL — AND UNTIL 2026-08-09 THE ANSWER WAS "ALL OF THEM".**
#:
#: `lifecycle` was a validated enum that **nothing consulted**. Measured directly: a row flipped to
#: `retired` and a row flipped to `draft` were both advertised, unchanged. So *"register a tool but
#: do not release it until it passes QC"* was **not an expressible state** — there was no unreleased
#: state, only an unread field.
#:
#: `draft` is registered-and-not-released; `retired` is gone. `deprecated` still SERVES, because
#: deprecation is *"prefer the successor"*, not *"this no longer works"* — a caller mid-migration
#: whose tool vanished on a deprecation would be the sunset window slamming rather than closing.
SERVED_LIFECYCLES: frozenset[str] = frozenset({"admitted", "deprecated"})

#: The registration STATE MACHINE — legal moves only, and deliberately not a full mesh.
#:
#: **Resurrection is absent on purpose.** `retired -> admitted` and `deprecated -> admitted` are not
#: here: a declaration that comes back is a NEW admission against the CURRENT contract, and letting
#: it return by a status edit would carry a row admitted under an older contract straight back onto
#: the wire — §6.4's re-admission queue with the queue skipped. Widen this table deliberately if the
#: product ever wants un-deprecation; do not widen it by accident.
LIFECYCLE_MOVES: dict[str, frozenset[str]] = {
    "draft": frozenset({"admitted", "retired"}),      # QC passes, or the candidate is abandoned
    "admitted": frozenset({"deprecated", "retired"}),
    "deprecated": frozenset({"retired"}),
    "retired": frozenset(),                            # terminal
}


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


class RequirementNotAdmitted(UntrustedRow):
    """CP-2.2 · §4.3 — the current plan step names a declaration the manifest does not admit.

    🔴 **NOT `UnresolvedReference`, and the difference is the whole of §4.3's second half.** That
    one is C-11/M5: a *member* of an admitted declaration naming another declaration, resolved at
    generation, so a manifest that fails it is never written. This is a **plan step** naming
    something at assembly time, from outside the manifest entirely — a different actor, a different
    moment, and a different fix. Reusing the class would have made two facts share one message and
    one `except`, which is how `ok=true` came to mean seven things.

    It is a refusal rather than a widening because §4.3 widens the ADVERTISED set within the
    ADMITTED set. A step that names something un-admitted is asking the assembler to invent, and
    *"never invent"* is the clause §0.1 has that §4.3 must not spend.

    A subclass of `UntrustedRow` for the reason recorded above: one documented refusal type, and no
    caller's `except` stops working.
    """

    def __init__(self, names: list[str]) -> None:
        self.names = list(names)
        super().__init__(
            f"the current step requires {sorted(self.names)}, which the manifest does not admit. "
            f"§4.3 widens the ADVERTISED set within the ADMITTED set; it is an obligation on "
            f"assembly, not a licence to invent (C-11 / M5)."
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


def check_transition(declaration_id: str, before: str, after: str) -> None:
    """Refuse an illegal registration move. **C-12: the rejection names what WOULD be legal.**

    Defined here rather than at the writer because the writer is not the only mover: a row edited in
    the store, a migration, and an admission script are three hands on the same field, and a rule
    enforced at one of them is a rule the other two do not have.
    """
    if before not in LIFECYCLES:
        raise UntrustedRow(declaration_id, "lifecycle", f"unknown current lifecycle {before!r}",
                           f"one of {sorted(LIFECYCLES)}")
    if after not in LIFECYCLES:
        raise UntrustedRow(declaration_id, "lifecycle", f"unknown target lifecycle {after!r}",
                           f"one of {sorted(LIFECYCLES)}")
    if before == after:
        return
    legal = LIFECYCLE_MOVES[before]
    if after not in legal:
        raise UntrustedRow(
            declaration_id, "lifecycle", f"{before} -> {after} is not a legal registration move",
            (f"one of {sorted(legal)}" if legal else
             f"nothing — {before!r} is terminal. A declaration that comes back is a NEW admission "
             f"against the CURRENT contract, not a status edit"),
        )

#: A declaration id is a **key**, and an unbounded key is not one.
#:
#: 🔴 **SIX ROUNDS OPEN, AND THE VEHICLE IS PLAIN JSON.** `^[a-z][a-z0-9_]*$` bounded the alphabet
#: and not the length, so a 300-character id was measured travelling through `check_row`, `rows_of`
#: and `validate_document` end to end. It is the `AllowList`/`DenyList` membership key, it is the
#: `OrderBy` tie-break, it is the M5 foreign key, and it is rendered into the prompt the model reads
#: — so an id longer than the surface it names is a budget the ranking spends on one row.
#:
#: The bound is **stated rather than assumed**: 64 characters. 🔴 **AND IT IS NOW MEASURED RATHER
#: THAN ASSERTED** — a verifier read the three registries this checkpoint's declarations will come
#: from (`tools-list.snapshot.json`, `LOADABLE_SKILL_CODES`, `intent_workflows._COMPILED`, **334
#: ids**) and found max length **38**, p99 37, and **0 over 64**. The docstring used to claim
#: *"longer than every identifier this repository declares"* with nobody having run it.
ID_MAX_LEN = 64

#: 🔴 **AND THE ALPHABET REFUSED 9 OF 9 REAL WORKFLOW IDS, WHICH SIX ROUNDS ABOUT THE *LENGTH* NEVER
#: ASKED.** `^[a-z][a-z0-9_]*$` was a builder choice; `ARCHITECTURE.md` C-0 says *"id"* and specifies
#: no alphabet. Every workflow this repository actually declares is hyphenated — `entity-triage`,
#: `canon-check`, `kg-build`, `build-a-book`, `translation-pass`, `autonomous-drafting`,
#: `chapter-compose`, `draw-a-map`, `lore-so-far` — so at CP-4 `check_contract` would have refused
#: **100% of one declaration kind**, and the message it printed would have led with the length.
#:
#: One command over the same corpus that justified `ID_MAX_LEN` would have found it, and the
#: measurement made was *"is the length bounded"* rather than *"what does this regex do to the real
#: data"*. `-` is admitted, because these ids are **persisted** and renaming nine of them is a
#: migration this checkpoint has no mechanism for (§6.4's re-admission queue is not built). A hyphen
#: is safe in every place an id is used here: a dict key, an allow-list member, a sort key, and
#: prompt text — none of them require a Python identifier.
#:
#: `test_THE_ALPHABET_ADMITS_EVERY_ID_THIS_REPOSITORY_ALREADY_DECLARES` runs the regex over all three
#: live registries, so the next kind that arrives with a new spelling is refused at **CP-1**, where
#: the answer is a decision, rather than at CP-4, inside the admission of the first declaration.
_ID = re.compile(r"^[a-z][a-z0-9_-]{0,%d}$" % (ID_MAX_LEN - 1))
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


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
#: 🔴 **CP-4.c ADDS THE THREE RANKING FACETS, AND THE COMMENT ABOVE IS THE REASON THEY ARE SAFE NOW
#: AND WERE NOT BEFORE.** The argument for removing them was never *"these fields are wrong"* — it
#: was *"nothing writes them, so nothing legitimate is refused, and a row carrying one came from a
#: hand edit."* §0.14.1c said the field arrives **with its producer, in the same change**. That
#: producer now exists (`derive.py`, measured 315/315), so the condition is met and this is the
#: change it was waiting for.
#:
#: What keeps a forged `cost: 1000000000` out is **not** a value bound — `1000000000` is a well-typed
#: integer and no predicate tells it from a real one. It is that the writer will not accept one: the
#: facets reach `_row` only inside a `Facets`, whose constructor is token-locked to `derive.derive_one`
#: exactly as `Admitted`'s is to `admit()`. There is no parameter for a caller to fill.
#:
#: `relevance` is still ABSENT and still deliberate — §0.14.1b puts its producer (a scoring stage
#: that calls a model) at CP-2, and CP-2 closed without one. A row cannot carry it, so a pipeline
#: ordering by it is still rejected, which is the correct fail-closed direction.
ROW_FIELDS = MappingProxyType({
    "id": (str,),
    "kind": (str,),
    "owning_service": (str,),
    "lifecycle": (str,),
    "contract_version": (str,),
    "admitted_against": (str,),
    "members": (list, tuple),
    # CP-4.c — optional, so every row already on disk still loads. `ROW_REQUIRED` is unchanged, and
    # that separation is exactly what CP-1 built it for.
    "lane": (str,),
    "tier": (str,),
    "cost": (int,),
})

#: The lanes a row may declare — C-1's *"data at registration"*, mirrored from the tier enum the
#: providers actually publish. `derive.LANE_BY_TIER` maps one to the other and
#: `test_THE_TWO_LANE_MAPS_AGREE` keeps the three spellings in step.
LANES: frozenset[str] = frozenset({"read", "action", "write", "system"})
TIERS: frozenset[str] = frozenset({"R", "A", "W", "S"})

#: 🔴 **ALL THREE OR NONE.** A row carrying `cost` but not `lane` is a row the ranking can order by
#: one key and not the other — and §0.14.1a rule 2 says a missing field is a REJECTION rather than a
#: fallback, precisely so a half-ranked surface cannot arise by default. Enforcing the set here
#: means the partial state is unrepresentable rather than caught later by whichever stage looked
#: first.
FACET_FIELDS: frozenset[str] = frozenset({"lane", "tier", "cost"})
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
    # ── CP-4.c · the ranking facets ────────────────────────────────────────────────────────────
    present = FACET_FIELDS & row.keys()
    if present and present != FACET_FIELDS:
        raise ContractViolation(
            rid or "", f"{where}.{sorted(FACET_FIELDS - present)[0]}",
            f"is missing while {sorted(present)} are present",
            f"all of {sorted(FACET_FIELDS)} or none of them — a row the ranking can order by one "
            f"key and not another is the half-ranked surface §0.14.1a rule 2 exists to refuse")
    if present:
        if row["lane"] not in LANES:
            raise ContractViolation(
                rid or "", f"{where}.lane", f"unknown lane {row['lane']!r}",
                f"one of {sorted(LANES)} (C-1: declared at registration, never inferred)")
        if row["tier"] not in TIERS:
            raise ContractViolation(
                rid or "", f"{where}.tier", f"unknown tier {row['tier']!r}", f"one of {sorted(TIERS)}")
        # `type(...) is int` already ran above, and it excluded `bool` there for the reason `bool`
        # is excluded everywhere in this file: it is an `int` subclass, so `True` would be a cost
        # of 1 — the cheapest declaration on the surface.
        if row["cost"] < 0:
            raise ContractViolation(
                rid or "", f"{where}.cost", f"is {row['cost']}",
                "a non-negative token count. 🔴 This bound is NOT what keeps a forged cost out — "
                "1000000000 is a well-typed non-negative integer and was measured steering "
                "TakeWhileBudget. What keeps it out is that `_row` accepts facets only inside a "
                "token-locked `Facets`, so there is no field to fill; this clause only catches a "
                "value that is not a count at all")


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
        # 🔴 **CP-4 — A ROW'S CLAUSES COME FROM THE ROW'S OWN GENERATION, NOT FROM THE
        # RUNNING ONE.** This called `check_contract`, which is the CURRENT contract, and
        # that made §6.4's grandfathering unreachable one layer below where the blocker was
        # diagnosed: `build(previous=)` re-validates the prior document, so a row admitted
        # under 1.0.0 was refused here by 2.0.0's clauses **before** the grandfathering code
        # could carry it. §6.4.1 says a grandfathered row *"would have to be checked against
        # the contract it was admitted under"* — this is that sentence, at the row door.
        check_contract_against(Declaration(
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
        ), row["admitted_against"])
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


#: The manifest format this reader supports. It lives here, beside `check_document`, because the
#: document check is what reads it and `manifest.py` re-exports it for every existing caller.
MANIFEST_VERSION = 1


def check_document(doc, source: str) -> str:
    """**One definition of a valid manifest DOCUMENT, for every door** — schema and both stamps.

    🔴 **THIS IS THE NINE-CLASSES FINDING ONE LEVEL UP, AND I MOVED IT TO CP-2 ON A CRITERION THE
    BOARD DID NOT STATE.** The ROW definition was consolidated across every door; the DOCUMENT
    definition was left in `validate_document` alone. A verifier measured the result at **24 of 24
    cells SERVED**: `rows_of`, `declarations`, `discover` and `SurfaceAssembler` all hand rows to a
    consumer from a document carrying `manifest_version: 999`, `contract_version: "banana"`, either
    stamp missing, or an undefined top-level key — while `load()` refuses every one of them.

    `contract_version` is the comparand §6.4's re-admission queue is derived from. Four exported
    doors never read it.

    The transfer said *"production-reachable at CP-2, not today"*. The criterion this board declared
    is *"no SUBJECT until a later checkpoint's code exists"* — and the subject is this function and
    the four doors, all of which are in the tree now and all of which a verifier drove in one
    command. **Those are different predicates, and the nine items I kept were judged on the first.**
    So it comes back, and it is fixed here rather than re-worded where it sat.

    Returns the validated `contract_version`, so a caller cannot re-read it off the object it just
    handed in — the `{**doc}` half of this same defect, one level down, took four rounds.
    """
    if type(doc) is not dict:
        raise UntrustedRow(
            f"{source}: manifest is a {type(doc).__name__}, not a plain JSON object. A container "
            f"that decides its own answers can answer the validator and the consumer differently."
        )
    extra = sorted(set(doc) - {"manifest_version", "contract_version", "declarations"})
    if extra:
        raise UntrustedRow(
            f"{source}: manifest carries {extra}, which the format does not define. One format is "
            f"supported; an unknown key is not a newer file, it is one this reader cannot make "
            f"claims about."
        )
    if doc.get("manifest_version") != MANIFEST_VERSION:
        raise UntrustedRow(
            f"{source}: manifest_version is {doc.get('manifest_version')!r}, expected "
            f"{MANIFEST_VERSION}. One format is supported and an unknown one is not a newer file, "
            f"it is a file this reader cannot make claims about."
        )
    doc_version = doc.get("contract_version")
    if type(doc_version) is not str or not _VERSION.match(doc_version):
        raise UntrustedRow(
            f"{source}: contract_version is {doc_version!r}; §6.4's re-admission queue is derived "
            f"by comparing every row against it, so an unreadable value empties the queue in silence"
        )
    return doc_version


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


#: Every contract generation this runtime can validate against, newest last.
#:
#: 🔴 **A VERSION IS NEVER REMOVED FROM HERE.** The manifest may hold a row admitted under any of
#: them, and dropping a generation would make that row unvalidatable — which is the state §6.4.1
#: describes as the blocker, reintroduced by tidying.
CONTRACTS: MappingProxyType = MappingProxyType({
    "1.0.0": Contract(
        version="1.0.0",
        breaking_from=None,
        kinds=KINDS,
        lifecycles=LIFECYCLES,
        id_max_len=ID_MAX_LEN,
        id_pattern=_ID.pattern,
    ),
})


def contract_for(version: str) -> Contract:
    """The named generation, or a `ContractViolation` naming what is available.

    An unknown version is a **rejection**, never a fallback to the current contract: falling back
    would validate a grandfathered row against clauses it was never checked against and then report
    success, which is precisely the silent-pass §6.4 exists to prevent.
    """
    got = CONTRACTS.get(version)
    if got is None:
        raise ContractViolation(
            "", "admitted_against", f"names contract {version!r}, which this runtime does not have",
            f"one of {sorted(CONTRACTS)} — a row admitted under a generation this code cannot load "
            f"is a row nothing can re-validate, so it is refused rather than waved through")
    return got


def check_contract_against(declaration: Declaration, version: str) -> str:
    """Run one generation's clauses. **The single implementation**; `check_contract` is this at the
    current version, so a grandfathered row and a fresh admission cannot diverge in their checking.
    """
    d = declaration
    contract = contract_for(version)
    _ID_RE = contract.id_re()
    KINDS_ = contract.kinds
    LIFECYCLES_ = contract.lifecycles
    ID_MAX_LEN_ = contract.id_max_len
    return _run_clauses(d, _ID_RE, KINDS_, LIFECYCLES_, ID_MAX_LEN_, contract.version)


def check_contract(declaration: Declaration) -> str:
    """Run every clause CP-1 owns, at the CURRENT generation. Returns the contract version on
    success; raises on the first failing clause with its field path.

    Called ONLY from `admission.admit`. It is not exported for direct use: a caller that can run
    the check separately from construction is a caller that can skip it, which is exactly the
    14-of-58 shape M4 replaces.
    """
    return check_contract_against(declaration, CONTRACT_VERSION)


def _run_clauses(d: Declaration, _ID_RE, KINDS_, LIFECYCLES_, ID_MAX_LEN_, version: str) -> str:

    # 🔴 `type(...) is str`, not `isinstance`. **THE TWIN OF `check_row_shape`'s TWO PINS, LEFT
    # UNFIXED WHILE THEY WERE CLOSED.** A verifier executed it: `admit(Declaration(id=SubStr(...)))`
    # **succeeded**, and the same held for a `str`-subclass member — so the one door whose whole job
    # is to be the boundary accepted the exact forgery the row-shape check had just been guarded
    # against, two functions away. `in`, `[]` and `==` all dispatch to user code; `type(x) is str` is
    # the only comparison Python does not dispatch, and it belongs at every pin of one claim.
    if type(d.id) is not str or not _ID_RE.match(d.id or ""):
        raise ContractViolation(
            getattr(d, "id", ""), "id",
            "not a stable identifier",
            f"lowercase letters, digits, underscores and hyphens, starting with a letter, at most "
            f"{ID_MAX_LEN_} characters, and a plain `str` — an id is the membership key of every "
            f"allow-list and the ranking's final tie-break, so an unbounded or self-answering one "
            f"is an unbounded or self-answering key",
        )
    if d.kind not in KINDS_:
        raise ContractViolation(
            d.id, "kind", f"unknown kind {d.kind!r}", f"one of {sorted(KINDS_)}",
        )
    if d.lifecycle not in LIFECYCLES_:
        raise ContractViolation(
            d.id, "lifecycle", f"unknown lifecycle {d.lifecycle!r}", f"one of {sorted(LIFECYCLES_)}",
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
        # `type(...) is str` here for the same reason as the id above — the second half of the same
        # unfixed twin, and a member is M5's foreign key.
        if type(m) is not str or not _ID_RE.match(m or ""):
            raise ContractViolation(
                d.id, f"members[{i}]", f"not a declaration id: {m!r}",
                f"the id of another declaration (a plain `str`, at most {ID_MAX_LEN_} characters), "
                f"resolved against the manifest at generation",
            )
    return version


def identity_of(declaration: Declaration) -> Identity:
    """C-0 for an admitted declaration. Derives rather than reads the owner, every time."""
    return Identity(
        id=declaration.id,
        owning_service=derive_owning_service(declaration.source_path),
        lifecycle=declaration.lifecycle,
    )
