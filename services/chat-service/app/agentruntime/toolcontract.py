"""CP-5.1 · the TOOL contract — members as versioned data, core vs conditional.

`docs/specs/2026-08-09-v2-tool-contract/CP-5.md`. CP-1 built a contract for a registry **ROW**
(ten fields: id, kind, owning_service, lifecycle, contract_version, admitted_against, members,
lane, tier, cost). **Nothing in it constrains the TOOL.** Measured at the time of writing:
`inputSchema` validated at admission → 0; a declared result shape → 0; C-3…C-17 implemented → no.

**Why the members live HERE and not in a Python base class.** v1's enforcement ladder was
`ABC` + `__init_subclass__` + frozen dataclass + private token — all Python-class mechanisms.
chat-service implements **9** tools in Python; the catalogue is federated from Go and Python
services. A mechanism whose subject is a few percent of the population, specified as *the* pattern,
is the clause-with-no-subject failure that produced CP-5, committed inside the document correcting
it. So the contract is a **language-neutral declaration in the MCP tool's `_meta`** — a mechanism
already proven, since `_meta` carries `tier`, `scope`, `ambient_book` and `superseded_by` today —
and the enforcement is rung 2, `promote()` in `promotion.py`, which needs no other team.

🔴 **CORE vs CONDITIONAL, AND THE CONDITIONALITY IS ITSELF DECLARED.** v1 required all members of
every tool, and two of its members affected **one session in 358**. Requiring everything makes
migration impossible; requiring nothing is what we already have. So each member states the
`trigger` under which it applies, as a predicate over the tool DEFINITION — computable, countable
over the live catalogue, and refutable. A member with `trigger=None` is core: it applies to every
tool, unconditionally.

🔴 **EVERY MEMBER CARRIES ITS SUBJECT AND ITS EVIDENCE, because §7 is the gate this checkpoint owes
itself.** *"The subject does not exist yet"* is exactly how C-3…C-17 became permanent — deferred
for a real reason, then never revisited, and no gate could notice because a gate over a clause with
no subject is the vacuity this board has a standard about. `subject` names what in the definition
the member constrains; `evidence` names the measured failure it answers, in **sessions affected**
out of the audited population, never in call events (ranking by events ranks a handful of
pathological loops — the top 3 sessions alone held 28.3% of all failed calls).
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable

TOOL_CONTRACT_VERSION = "1.0.0"


class ToolContractViolation(ValueError):
    """A tool whose `_meta.contract` does not satisfy the members that apply to it.

    Carries the tool, the member and what would satisfy it — C-12's *the rejection names what WOULD
    be legal*, because a refusal a producer cannot act on just moves the work to whoever reads logs.
    """

    def __init__(self, tool: str, member: str, problem: str, expected: str) -> None:
        self.tool = tool
        self.member = member
        self.problem = problem
        self.expected = expected
        super().__init__(f"{tool}._meta.contract.{member} {problem}; expected {expected}")


# ── the triggers ─────────────────────────────────────────────────────────────
#
# Each is a pure predicate over the tool definition. They are functions rather than a string DSL
# for the reason §3a gives for having no expression syntax in an emit path: a language that can
# compute can read something it was not handed. These only look.


def _fn(tool_def: dict) -> dict:
    fn = tool_def.get("function") if type(tool_def) is dict else None
    return fn if type(fn) is dict else (tool_def if type(tool_def) is dict else {})


def _meta(tool_def: dict) -> dict:
    m = _fn(tool_def).get("_meta")
    return m if type(m) is dict else {}


def _schema(tool_def: dict) -> dict:
    fn = _fn(tool_def)
    s = fn.get("inputSchema")
    if type(s) is not dict:
        s = fn.get("parameters")
    return s if type(s) is dict else {}


def properties_of(tool_def: dict) -> dict:
    p = _schema(tool_def).get("properties")
    return p if type(p) is dict else {}


def _tier(tool_def: dict) -> str:
    t = _meta(tool_def).get("tier")
    return t if type(t) is str else ""


#: A property is REF-SHAPED when its name reads as an identifier. This is the subject of the member
#: that 5.3-pilot measured: 338 calls / 11 sessions sent a human NAME into one of these.
def has_ref_property(tool_def: dict) -> bool:
    return any(_is_ref_name(k) for k in properties_of(tool_def))


def _is_ref_name(name: str) -> bool:
    return type(name) is str and (name.endswith("_id") or name.endswith("_ids"))


def _declared_types(prop: dict) -> tuple[str, ...]:
    """The type names a property declares, whether it declares one or a UNION of several.

    🔴 **`prop.get("type") == "array"` IS THE WRONG TEST, AND IT COST THIS CHECKPOINT TWICE.**
    JSON Schema lets `type` be a LIST, and Pydantic emits exactly that for an optional field:
    `"type": ["null", "array"]`. Measured over the frozen catalogue, **100 of 1,313 properties
    declare a union type** — so any predicate comparing `type` to a bare string is blind to them.

    This is the **third** appearance of the same artifact in one checkpoint, and it has now pointed
    in both directions. It withdrew row 5.3b by making `anyOf: [string, null]` look UNTYPED (the
    *"120 untyped properties"* that did not exist), and it silently shrank `partial_outcome` by
    making a batch tool look scalar — `is_batch` selected **3 tools where 16 qualify**, missing
    **81%** of them, including `glossary_propose_entities`, whose measured failures are the
    member's own subject.

    A withdrawal on a false absence and a member scoped to a fifth of its population are the same
    bug wearing opposite signs, which is why the reader lives here rather than in each predicate.
    """
    t = prop.get("type")
    if type(t) is str:
        return (t,)
    if type(t) is list:
        return tuple(x for x in t if type(x) is str)
    return ()


def _enum_anywhere(prop: dict) -> bool:
    """An enum declared directly, or inside a `anyOf`/`oneOf` branch.

    Optional-with-a-closed-set is written `anyOf: [{enum: [...]}, {type: null}]`, and reading only
    the top level misses it — **10 of 106** tools with a closed vocabulary, measured.
    """
    if type(prop.get("enum")) is list:
        return True
    for key in ("anyOf", "oneOf"):
        for branch in (prop.get(key) or ()):
            if type(branch) is dict and type(branch.get("enum")) is list:
                return True
    return False


def has_enum_property(tool_def: dict) -> bool:
    return any(type(v) is dict and _enum_anywhere(v)
               for v in properties_of(tool_def).values())


#: The keys any one of which declares a property's shape. `enum` and `const` count: a closed set of
#: literals says what the value may be as firmly as a type name does.
_TYPE_KEYS = ("type", "$ref", "anyOf", "oneOf", "allOf", "enum", "const")


def _declares_a_type(prop: dict) -> bool:
    """🔴 **`"type" in prop` IS THE WRONG TEST, AND IT SHIPPED A TRIGGER THAT NEVER FIRED.**

    The first version of this asked whether the key was ABSENT and found **0 untyped properties in
    1,389** — so `untyped_properties` would have entered the member set with a subject that does
    not exist, which is precisely the C-3…C-17 failure §7 gates against, committed inside the
    module built to end it.

    The key is present. Its VALUE is `null`: **129 of the 498 `*_id` properties in the frozen
    catalogue declare `"type": null`**, which every JSON Schema validator treats as no constraint
    and every reader of the source treats as typed. A gate that greps for the key agrees with the
    reader and is wrong about the data.
    """
    for k in _TYPE_KEYS:
        if k in prop and prop[k] is not None and prop[k] != "" and prop[k] != []:
            return True
    return False


def has_untyped_property(tool_def: dict) -> bool:
    """5.3b's residue — a property that constrains its value in no way at all."""
    return any(type(v) is dict and not _declares_a_type(v)
               for v in properties_of(tool_def).values())


def is_write(tool_def: dict) -> bool:
    """`A` (auto-commit) and `W` (human-confirmed) both change state; `R` reads and `S` is system."""
    return _tier(tool_def) in ("A", "W")


def is_gated(tool_def: dict) -> bool:
    """`W` is the human-confirmed tier — the one that mints a confirm token rather than writing."""
    return _tier(tool_def) == "W"


def is_scoped(tool_def: dict) -> bool:
    """A tool whose `_meta.scope` names a container it must be given, so it has a precondition
    beyond its arguments."""
    s = _meta(tool_def).get("scope")
    return type(s) is str and s not in ("", "none")


def is_paged(tool_def: dict) -> bool:
    """A tool that can return a TRUNCATED answer. This is the quiet-failure class: `book_list`
    returns `{total, returned, is_complete}` and a model asked for *"the first book"* reads a
    truncated page and is never told. It cannot fail loudly, so it appears in no error bucket —
    a contract that fixes only the loud members converts nothing, it just stops counting."""
    props = properties_of(tool_def)
    return any(k in props for k in ("limit", "offset", "cursor", "page"))


def is_batch(tool_def: dict) -> bool:
    """A tool taking a LIST of work items, so it can half-succeed."""
    for v in properties_of(tool_def).values():
        if type(v) is dict and "array" in _declared_types(v) and type(v.get("items")) is dict:
            if "object" in _declared_types(v["items"]) or "properties" in v["items"]:
                return True
    return False


@dataclass(frozen=True, slots=True)
class Member:
    """One clause of the tool contract.

    `trigger` **None means CORE** — it applies to every tool. Otherwise it is the predicate under
    which the member is required, and a tool the predicate does not select may omit it. That is what
    *"the conditionality is itself declared"* means: the condition is data on the member, not an
    `if` buried in a validator that only its author can enumerate.
    """

    name: str
    #: What in the tool definition this member constrains. §7: a member with no subject is how
    #: C-3…C-17 became permanent.
    subject: str
    #: Sessions affected in the audited failure population, and what the failure looked like.
    evidence: str
    #: None ⇒ core. Otherwise the predicate that makes it required.
    trigger: Callable[[dict], bool] | None = None
    #: A human name for the trigger, so a report can say WHY a member applied.
    trigger_name: str = ""

    @property
    def is_core(self) -> bool:
        return self.trigger is None

    def applies_to(self, tool_def: dict) -> bool:
        return True if self.trigger is None else bool(self.trigger(tool_def))


@dataclass(frozen=True, slots=True)
class ToolContract:
    """A generation of the tool contract. Versioned for the same reason `Contract` is: a tool
    promoted under one generation must stay re-validatable against the generation it passed."""

    version: str
    breaking_from: str | None
    members: tuple[Member, ...]

    def by_name(self) -> dict[str, Member]:
        return {m.name: m for m in self.members}

    def required_for(self, tool_def: dict) -> tuple[Member, ...]:
        return tuple(m for m in self.members if m.applies_to(tool_def))


#: 🔴 **THE MEMBER SET, AND EVERY ROW HERE HAS A SUBJECT THAT EXISTS TODAY.**
#:
#: Ordered by sessions affected out of the audited population — the honest denominator. `identifier
#: resolution` leads because 5.3-pilot measured it end to end (§3b): `ZERO_EXACT` 0 in every
#: stratum, 83.3% of contested pairs resolving to exactly one, and ambiguity real rather than
#: bounded.
_MEMBERS_1_0_0: tuple[Member, ...] = (
    Member(
        name="identifier_resolution",
        subject="every ref-shaped input (`*_id`, `*_ids`): how does a NAME become an id?",
        evidence="11 sessions / 338 calls sent a human name into an id field; 99.5% of every "
                 "UUID-type failure. 5.3-pilot §3b measured the resolver on that exact population",
        trigger=has_ref_property,
        trigger_name="the tool takes a ref-shaped input",
    ),
    Member(
        name="argument_supplier",
        subject="every input: is it supplied by the model, by context, or by the plan?",
        evidence="85 sessions (23.7%) — a required argument absent. CP-3.10's executor already "
                 "supplies plan-bound arguments; this makes the fact DECLARABLE rather than "
                 "plan-only",
    ),
    Member(
        name="repeat_semantics",
        subject="a re-call with identical arguments: free, cached, or an error?",
        evidence="46 sessions (12.8%). 🔴 The contract may remove a repeat's COST and NEVER its "
                 "SIGNAL — declaring `tool_list` idempotent and serving the cache would turn a "
                 "393-call loop into 393 SILENT successes, which is converting loud failures into "
                 "quiet ones",
    ),
    Member(
        name="error_contract",
        subject="every failure: a C-7 class AND a message",
        evidence="29 sessions (8.1%) — these failures carried NO MESSAGE AT ALL, so nothing "
                 "downstream could decide whether to retry, re-route or stop",
    ),
    Member(
        name="output_contract",
        subject="the declared shape of the result",
        evidence="6 sessions (1.7%) by its own error class, but LOAD-BEARING FOR CP-3: an `emits` "
                 "path is a literal string and `check_emit_path` can only prove it is syntactically "
                 "a path, because no tool declares a result shape. So `EmitPathError` fires at "
                 "EXECUTION, inverting §6.2's *a generation error, not a runtime one*",
    ),
    Member(
        name="result_completeness",
        subject="a truncated result: the fields that say so (`total` / `returned` / `is_complete`)",
        evidence="0% by construction — invisible in every bucket. A model asked for the first book "
                 "reads a truncated page and is never told. This is the quiet-failure class "
                 "V-METRIC exists to detect, sitting inside a tool result",
        trigger=is_paged,
        trigger_name="the tool can return a truncated page",
    ),
    Member(
        name="preconditions",
        subject="the scope, capability or prerequisite state the tool requires before dispatch",
        evidence="67 sessions (18.7%). Also gates ADVERTISEMENT (§4.3): a tool whose precondition "
                 "is unmet should not be offered, and the withholding is recorded",
        trigger=is_scoped,
        trigger_name="the tool declares a scope it must be given",
    ),
    Member(
        name="partial_outcome",
        subject="which items of a batch succeeded, and which did not",
        evidence="37 sessions (10.3%) — a batch tool that half-succeeds and reports one status",
        trigger=is_batch,
        trigger_name="the tool takes a list of work items",
    ),
    Member(
        name="consent",
        subject="what the human is confirming, before a gated write happens",
        evidence="20 sessions (5.6%)",
        trigger=is_gated,
        trigger_name="the tool is human-confirmed (tier W)",
    ),
    Member(
        name="effect_and_undo",
        subject="what the write changes, and whether it is reversible",
        evidence="`undo_hint` exists in `_meta` on a handful of tools today but is not "
                 "contractual, so a write's reversibility is a convention rather than a fact",
        trigger=is_write,
        trigger_name="the tool changes state",
    ),
    Member(
        name="closed_vocabulary",
        subject="each enum parameter's accepted values, as data",
        evidence="10 sessions (2.8%)",
        trigger=has_enum_property,
        trigger_name="the tool has an enum parameter",
    ),
    # 🔴 **`untyped_properties` (spec row 5.3b) IS DELIBERATELY ABSENT — ITS SUBJECT DOES NOT
    # EXIST, MEASURED.** The spec demotes `typed inputs` to a conditional member covering *"the
    # residue — the 120 properties with no `type` at all"*. Over the frozen catalogue there are
    # **1,389 properties and ZERO of them are untyped**, at any depth.
    #
    # The 120 are a measurement artifact, and it is one I reproduced before catching it: reading
    # `prop.get("type")` returns `None` for a property typed as `anyOf: [{"type": "string"},
    # {"type": "null"}]` — Pydantic's `Optional[str]`, which **129 of the 498 `*_id` properties
    # use**. `.get()` cannot tell *absent* from *a union that includes null*, so a real and
    # correctly-typed union counts as untyped.
    #
    # Shipping the member anyway would be the exact failure §7 gates: a clause whose subject does
    # not exist, which is how C-3…C-17 became permanent. `has_untyped_property` stays, unused by
    # any member, as the predicate `test_THE_CATALOGUE_HAS_NO_UNTYPED_PROPERTY` asserts stays empty
    # — so if a provider ever ships one, the member's subject appears and a test says so, rather
    # than a clause sitting here waiting for a subject nobody re-checks.
)

#: Every generation this runtime can validate against, newest last. **A version is never removed** —
#: a tool promoted under an older generation would become unvalidatable, which is the state §6.4.1
#: names as the blocker, reintroduced by tidying.
TOOL_CONTRACTS: MappingProxyType = MappingProxyType({
    "1.0.0": ToolContract(version="1.0.0", breaking_from=None, members=_MEMBERS_1_0_0),
})


def tool_contract_for(version: str) -> ToolContract:
    """The named generation, or a violation naming what exists. An unknown version is a REJECTION,
    never a fallback to the current one — falling back would validate a tool against clauses it was
    never checked against and then report success."""
    got = TOOL_CONTRACTS.get(version)
    if got is None:
        raise ToolContractViolation(
            "", "version", f"names tool contract {version!r}, which this runtime does not have",
            f"one of {sorted(TOOL_CONTRACTS)}")
    return got


def declared_contract(tool_def: dict) -> dict:
    """The `_meta.contract` block a tool declares, or `{}` when it declares none.

    Absent is not an error here — it is an error at PROMOTION (`promotion.check_tool_contract`).
    Registration and release are different decisions: a tool with no contract registers `draft`
    like everything else and simply never reaches the wire.
    """
    c = _meta(tool_def).get("contract")
    return c if type(c) is dict else {}


#: 🔴 **WHERE THE CONTRACT LIVES ON DAY ONE — A REGISTRY ROW, NOT THE WIRE (PO, 2026-08-09).**
#:
#: §4 says the contract is a declaration in the tool's `_meta`, and that is the right END state:
#: `_meta` is produced by the owning service, so a contract there is the owner's own statement.
#: It cannot be the START, for two reasons the first migration made concrete.
#:
#: **It needs another team.** `_meta` for 306 of the 315 tools is emitted by Go and Python services
#: chat-service does not own — the same objection W2/§3a already resolved for the ref/resolver map:
#: *"a registry row, authored once and later pushed upstream into `_meta` when the owning service
#: catches up."* §4's placement gets the correction §3a already took; the destination is unchanged.
#:
#: **And it perturbed the control group.** A minimal contract block took `book_list` from cost 1284
#: to 1998 (+56%), rank 191 → 262 of 315, because `token_cost` serialised `_meta`. That is now
#: corrected — cost measures the wire form — so the eventual push upstream is free. The registry is
#: what makes the contract authorable *today*, without waiting for either.
#:
#: **`_meta` WINS where a service supplies it.** The registry is interim authoring; the owner's own
#: declaration is the truth, and the moment one arrives it takes precedence and the registry row
#: becomes removable. `contract_source()` records which one answered, because a contract we wrote
#: and a contract the owner published must never merge into one indistinguishable row — the same
#: separation `plan_supplied.overrode` had to make.
CONTRACT_REGISTRY_FILENAME = "agent-runtime-tool-contracts.json"

#: CP-5.4 — the suppliers an input may declare. `model` is the ONLY one the model can act on; the
#: other two name a value the RUNTIME owes it, which is the distinction the generic
#: *"missing required argument"* message cannot make.
SUPPLIERS = ("model", "context", "plan")


def declared_supplier(contract: dict, param: str) -> str | None:
    """Which side owes `param`, per the tool's `argument_supplier` member, or None.

    🔴 **THE MEASUREMENT THAT MAKES THIS WORTH BUILDING.** Of 266 missing-argument failures across
    87 sessions, the single largest is **`book_read` missing `book_id` — 78 calls over 46
    sessions** — and `book_id` is a **context** value: the runtime fills it from the ambient book
    and simply has none outside a book studio. The model is told *"missing required argument
    book_id"*, which reads as *"you forgot something"* when the truth is *"I owe you this and do
    not have it"*. The remaining classes (`body`, `items`, `base_version`) are genuinely
    `model`-supplied content, where that same message IS right.

    One generic sentence for two opposite situations is the same defect as `ok:false` covering both
    a failure and a suspension (5.5), one layer up.
    """
    block = contract.get("argument_supplier")
    if type(block) is not dict:
        return None
    raw = block.get(param)
    if type(raw) is not str:
        return None
    # A declaration reads like `"context | plan — the ambient book …"`. The SUPPLIERS it names are
    # what matters; the prose after them is for a human. `model` last: a value the runtime can
    # supply is the runtime's to supply, and only if nothing can is it the model's job.
    named = [s for s in ("context", "plan", "model") if s in raw.split("—")[0]]
    return named[0] if named else None


def resolve_contract(tool_def: dict, registry: dict | None) -> tuple[dict, str]:
    """The contract that governs this tool, and WHICH source supplied it.

    Returns `({}, "none")` when neither has one — which is a refusal at promotion, not here.
    """
    from_meta = declared_contract(tool_def)
    if from_meta:
        return from_meta, "_meta"
    fn = tool_def.get("function") if type(tool_def) is dict else None
    name = (fn if type(fn) is dict else tool_def if type(tool_def) is dict else {}).get("name")
    rows = (registry or {}).get("contracts")
    row = rows.get(name) if type(rows) is dict and type(name) is str else None
    if type(row) is dict and row:
        return row, "registry"
    return {}, "none"
