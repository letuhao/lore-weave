"""CP-4 · declarations are DERIVED from the live catalogue, never hand-authored.

**The arithmetic that decides this design.** CP-4's board entry reads *"declarations, one at a
time, starting with `book_list`"*, and there are **315 federated tools**. At the withdrawn
`≈13 admissions/week` that is six months; at any rate a person can sustain by hand it is a project,
not a checkpoint. So what this checkpoint owes is not 315 authored rows — it is a **producer**, plus
an honest measurement of how much of the catalogue it actually reaches.

WHAT IS DERIVABLE, MEASURED BEFORE IT WAS BUILT
-----------------------------------------------
Every field below comes from something the provider already declares or from a deterministic
function of the declaration document. Nothing is invented here, and a field that cannot be derived
is **reported** rather than defaulted — `unresolved` is a return value, not a log line.

| row field | source | measured |
|---|---|---|
| `id` | the tool name on the wire | 315/315 |
| `kind` | `"tool"` — this producer's whole input is the tool catalogue | 315/315 |
| `lifecycle` | **always `draft`** — derivation REGISTERS, release is a separate decision | 315/315 |
| `owning_service` | C-0, derived from `source_path` below | see `PROVIDERS` |
| `lane` / `tier` | `_meta.tier`, set by the provider at registration (C-1) | 315/315 |
| `cost` | `token_cost()` — a pure function of the definition | 315/315 |

🔴 **`source_path` IS THE ONLY HARD ONE, AND THE OBVIOUS ROUTE IS THE DEFECT C-1 FORBIDS.** C-0
requires the owner **derived, never authored**, from a path under `services/<name>/`. A federated
tool arrives over the wire with no path at all, so the temptation is to read the service out of the
tool's name prefix — which is *precisely* the name heuristic CP-4.d has just finished deleting, and
it would be wrong: `settings_*` is served by **provider-registry-service**, not by a
`settings-service`, and there is no such directory in this repository.

The honest source is the gateway's own registration: `AI_GATEWAY_PROVIDERS` binds a provider name to
an upstream URL, and `DEFAULT_PREFIX_MAP` / `EXTRA_PREFIX_MAP` bind it to the namespaces it may
serve. The gateway **enforces** those namespaces — `computeCatalog` drops and warns a tool that
escapes its provider's prefixes — so a prefix here is not an inference about a name, it is a claim
the federation already refuses to violate.

🔴 **AND THE GATEWAY IS DELIBERATELY NOT ASKED TO STAMP IT ON THE WIRE.** Adding `_meta.served_by` to
each tool was the first design, and it is wrong for a measured reason: `_tool_tokens` serialises the
**whole** definition including `_meta`, so one extra key changes every tool's cost, which changes the
rank, which changes what the budget cuts — and the legacy arm is **CP-2's control group** (§7).
Perturbing it to make this checkpoint tidier would invalidate the comparison the whole run exists to
make. The registration data is recorded here as data instead, and `test_PROVIDERS_MATCHES_THE_LIVE_GATEWAY`
reds when it drifts.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType

from .contract import Declaration

#: The federation registry, transcribed from the gateway's own registration config
#: (`AI_GATEWAY_PROVIDERS` for the service, `DEFAULT_PREFIX_MAP` + `EXTRA_PREFIX_MAP` for the
#: namespaces). **This is a claim about another service's configuration**, so it is gated rather
#: than trusted: the drift test dials the live gateway and compares.
#:
#: `service` is the repository directory, which is what C-0's `derive_owning_service` reads — taken
#: from the upstream URL's host (`http://provider-registry-service:8085/mcp` → the row below), never
#: from the provider's logical name. Those two differ for `settings`, and that difference is the
#: whole reason this table exists.
PROVIDERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # (provider name, repository service directory, namespaces it may serve)
    ("knowledge", "knowledge-service", ("memory_", "kg_", "story_", "lore_")),
    ("glossary", "glossary-service", ("glossary_",)),
    ("book", "book-service", ("book_", "world_")),
    ("composition", "composition-service", ("composition_", "plan_")),
    ("translation", "translation-service", ("translation_",)),
    ("settings", "provider-registry-service", ("settings_", "web_")),
    ("jobs", "jobs-service", ("jobs_",)),
    ("catalog", "catalog-service", ("catalog_",)),
    ("registry", "agent-registry-service", ("registry_",)),
    # The gateway's OWN tools. `tool_list`/`tool_load` are the deterministic discovery pair and
    # `propose_edit` is the UI edit proposal — none of them is federated from an upstream, so the
    # service that serves them is the gateway itself.
    ("_gateway", "ai-gateway", ("tool_", "propose_")),
)

#: `_meta.tier` → lane. One map, shared with the consumer side (`tool_discovery.declared_lane`);
#: duplicated as a literal rather than imported because `app.services` importing `app.agentruntime`
#: or the reverse would couple the membrane to the legacy surface, and `test_THE_TWO_LANE_MAPS_AGREE`
#: is what stops them drifting.
LANE_BY_TIER = MappingProxyType({"R": "read", "A": "action", "W": "write", "S": "system"})


class Underivable(Exception):
    """A field no source can supply for a given tool. Carries the tool and the field, per C-12."""

    def __init__(self, tool: str, field_name: str, reason: str) -> None:
        self.tool = tool
        self.field_name = field_name
        self.reason = reason
        super().__init__(f"{tool}.{field_name}: {reason}")


def facets_for(tool_def: dict) -> dict:
    """The three ranking keys `_row` merges — **recomputed from the definition, at the writer**.

    🔴 **THIS REPLACED A TOKEN-LOCKED `Facets` TYPE, AND THE GATE THAT KILLED IT WAS RIGHT.**

    The first design mirrored `Admitted`: a frozen class whose constructor demanded a private token,
    so only `derive_one` could state a rank. `agentruntime-membrane-gate` failed it on six lines —
    the private-token *name* and `object.__setattr__`, both of which it confines to `admission.py`,
    because *"a deliberate bypass must be visible in the diff that introduces it"*. Adding an
    exemption for my own new class would have been narrowing a gate to admit the code it was
    pointed at.

    Removing the type turned out to be **stronger than exempting it**. There is now no facets value
    anywhere for a caller to hand in — `_row` takes the tool DEFINITION and computes the rank
    itself. Two rounds of bounding row *values* failed because the vehicle was always a plain
    well-typed scalar (a hand-typed `"cost": 1000000000` was measured steering `TakeWhileBudget`);
    a token made the value hard to forge, and this makes it impossible to *supply*. The forgery is
    not refused, it is unsayable — and the whole apparatus is one function.

    Raises `Underivable` exactly as `derive_one` does, so a definition that cannot be ranked cannot
    quietly produce a row that is ranked wrongly.
    """
    d = derive_one(tool_def)
    return {"lane": d.lane, "tier": d.tier, "cost": d.cost}


@dataclass(frozen=True, slots=True)
class Derived:
    """One catalogue entry turned into an admissible declaration plus its ranking facets.

    The facets are kept BESIDE the declaration rather than on it: `Declaration` is the untrusted
    input to `admit()`, and a declaration that could carry its own `cost` would be a declaration
    that could state its own rank. They are re-derived at the write boundary, so a value that
    disagrees with the definition cannot reach a row.
    """

    declaration: Declaration
    lane: str
    tier: str
    cost: int


def _fn(tool_def: dict) -> dict:
    fn = tool_def.get("function") if type(tool_def) is dict else None
    return fn if type(fn) is dict else (tool_def if type(tool_def) is dict else {})


def _meta(tool_def: dict) -> dict:
    m = _fn(tool_def).get("_meta")
    return m if type(m) is dict else {}


def wire_form(tool_def: dict) -> dict:
    """The definition as the PROVIDER receives it — `_meta` removed.

    🔴 **This mirrors `app.services.tool_discovery.strip_tool_meta` rather than importing it**, for
    the same reason `LANE_BY_TIER` is duplicated: this package importing `app.services` would couple
    the membrane to the legacy surface, and the import gate refuses it. The copy is what
    `test_THE_TWO_STRIPS_AGREE` exists to keep honest — a drift here would make `cost` measure a
    form nothing sends.
    """
    fn = tool_def.get("function") if type(tool_def) is dict else None
    if type(fn) is dict:
        if "_meta" not in fn:
            return tool_def
        out = dict(tool_def)
        out["function"] = {k: v for k, v in fn.items() if k != "_meta"}
        return out
    if type(tool_def) is dict and "_meta" in tool_def:
        return {k: v for k, v in tool_def.items() if k != "_meta"}
    return tool_def


def token_cost(tool_def: dict) -> int:
    """`cost` as a pure function of the definition — never a value the definition may state.

    🔴 **THE ROW SCHEMA REFUSES A HAND-TYPED `cost` AND THIS IS WHY THAT STAYS TRUE.** A verifier
    measured `{"cost": 1000000000}` steering `TakeWhileBudget`, and no value bound distinguishes a
    forged cost from a real one — `1000000000` is a well-typed integer. Making cost *derived* rather
    than *declared* removes the question instead of answering it: there is no field for a forger to
    fill, because the number is recomputed from the bytes at every admission.

    🔴 **THIS IS A COUNT, NOT A CANONICAL FORM, AND THE DIFFERENCE COST TWO WRONG ATTEMPTS.**

    The first version passed `json.dumps` a key-sorting flag, and CP-1's membrane guard caught it:
    that flag outside `canon.py` is a marker of a **second thing deciding what bytes get hashed**,
    which is the defect that guard exists for. (Spelling the flag out here would trip it again —
    the guard greps this package's source, and prose is source.)

    The second version therefore called `canon.canonical_bytes` — and that was wrong in a more
    interesting way. `canon` **refuses floats by design** (*"platform and version disagree on repr,
    and the disagreement is invisible in the digest it changes"*), which is correct for OUR manifest
    rows, whose schema is closed and float-free. A federated tool definition is **third-party JSON
    Schema**: it may carry a `default: 0.5` or a `multipleOf`, and 315 of them did not derive at all.
    Canon is for documents this package owns; a foreign schema is not one.

    So the honest answer is neither: a size measurement does not need a canonical form. Key order
    cannot change a character count, so sorting them buys nothing here — its only effect would have
    been to make this look like a canonicaliser. NFC stays, and it is load-bearing rather than
    tidy: the counter weights per codepoint, so the same text costs ~1.44x decomposed, and this
    number is a sort key against a budget that ends in a hard `break` (U-1).

    🔴 **AND IT COUNTED BYTES THE MODEL NEVER RECEIVES — CORRECTED 2026-08-09 (PO decision).**
    `_meta` is consumer-side only: `tool_discovery.strip_tool_meta` removes it **before the wire
    request**, so every character in it costs the model exactly nothing. This function serialised
    it anyway. Measured over the frozen catalogue: **9.6% of the entire ranking key was bytes that
    are never sent, all 315 tools were inflated** (median 132 characters, max 366), and correcting
    it moves a tool's cost rank by a median of 6 places and up to 38 (`book_update_details`). A
    sort key against a budget ending in a hard `break` was cutting declarations on the size of
    metadata the model cannot read.

    It surfaced from the opposite direction. This module's own header refused to add `_meta.
    served_by` because *"one extra key changes every tool's cost, which changes the rank, which
    changes what the budget cuts"* — true, and the reason CP-5 §4's placement of the tool contract
    in `_meta` collided with it. Both problems are the same defect: **the cost of a definition is
    the cost of what is SENT.** Measuring that removes the perturbation instead of budgeting for it.

    ✖ **The legacy `tool_surface._tool_tokens` is deliberately NOT changed.** That arm is CP-2's
    control group (§7); correcting the control to match the treatment is how a comparison stops
    measuring anything. It carries the same inflation, and that is now a recorded row rather than
    an unknown.
    """
    return len(unicodedata.normalize("NFC", json.dumps(wire_form(tool_def), ensure_ascii=False)))


#: Every repository service directory a declaration may name as its owner. `PROVIDERS` cannot be
#: the source here: it lists the services the GATEWAY federates from, and a consumer-local tool is
#: served by a consumer that federates nothing. Kept as the union so a typo'd `served_by` is
#: refused rather than written into a manifest as an owner nobody can find.
_OWNING_SERVICES: frozenset[str] = frozenset(
    [service for _p, service, _n in PROVIDERS] + ["chat-service"]
)


def declared_service(tool_def: dict) -> str | None:
    """`_meta.served_by` — the owner as DECLARED BY THE DEFINITION, or None.

    🔴 **THIS EXISTS BECAUSE A TOOL'S NAME CAN LIE ABOUT ITS OWNER, AND ONE DOES.**
    `glossary_propose_entity_edit` is named into glossary-service's namespace and is served by
    **chat-service** — it is a frontend tool, executed in the browser after a human Apply, and
    glossary-service has never heard of it. `resolve_service` is a PREFIX table, so it answers
    `glossary-service` with total confidence, and a manifest built on that answer would attribute
    the tool to a team that does not serve it. C-0 reads the owner out of `source_path`; a wrong
    owner there is not a cosmetic error.

    So the declaration wins over the prefix, for the reason the prefix table itself gives: it is
    *"a claim about another service's configuration"* — specifically the gateway's ROUTING — and a
    consumer-local tool is not routed at all. Where routing has nothing to say, the definition
    does.

    **The forgery question is answered by a gate, not by this function**, exactly as the prefix
    table's own accuracy is: `test_NO_FEDERATED_TOOL_DECLARES_ITS_OWN_OWNER` asserts the frozen
    catalogue carries **zero** `served_by` keys, so today the override is reachable only by tools
    this repository serves itself. The day a provider ships one, that guard reds and a human looks
    at it — which is the visible-drift treatment, not a silent resolution in favour of either side.
    """
    served_by = _meta(tool_def).get("served_by")
    return served_by if type(served_by) is str and served_by else None


def resolve_service(name: str) -> str | None:
    """The repository service directory that serves `name`, or None when no provider claims it.

    Longest prefix wins, so a provider owning `book_` and one owning `book_admin_` cannot both
    claim a tool — today no such pair exists, and making the rule total now costs nothing and stops
    the ambiguity being discovered by whichever entry happened to be listed first.
    """
    best: tuple[int, str] | None = None
    for _provider, service, prefixes in PROVIDERS:
        for p in prefixes:
            if name.startswith(p) and (best is None or len(p) > best[0]):
                best = (len(p), service)
    return best[1] if best else None


def derive_one(tool_def: dict) -> Derived:
    """One tool definition → an admissible `Declaration` + its facets. Raises `Underivable`."""
    name = _fn(tool_def).get("name")
    if type(name) is not str or not name:
        raise Underivable(str(name), "id", "the catalogue entry carries no tool name")

    # The DECLARED owner wins over the name prefix — see `declared_service`. A declared value that
    # names no service in this repository is REFUSED rather than falling back to the prefix: the
    # fallback would turn a typo into a plausible wrong owner, which is the failure mode the whole
    # declaration exists to remove.
    service = declared_service(tool_def)
    if service is not None and service not in _OWNING_SERVICES:
        raise Underivable(
            name, "owning_service",
            f"_meta.served_by is {service!r}, which is not a service directory in this repository. "
            f"A declared owner that names nothing is worse than none: it would be written into the "
            f"manifest and read back as fact")
    if service is None:
        service = resolve_service(name)
    if service is None:
        raise Underivable(
            name, "owning_service",
            "no registered provider declares a namespace this name falls under, and the definition "
            "does not declare `_meta.served_by`. C-0 requires the owner DERIVED; guessing a service "
            "from the name is the heuristic C-1 forbids, so this is reported rather than defaulted")

    meta = _meta(tool_def)
    tier = meta.get("tier")
    lane = LANE_BY_TIER.get(tier)
    if lane is None:
        raise Underivable(
            name, "lane",
            f"_meta.tier is {tier!r}; the lane is declared at registration (C-1) and cannot be "
            f"recovered from anything else on the wire")

    return Derived(
        declaration=Declaration(
            id=name,
            kind="tool",
            # C-0 reads the OWNER out of this path. A trailing marker keeps it a path rather than a
            # bare directory name, matching every other `source_path` the contract sees.
            source_path=f"services/{service}/",
            # 🔴 **ALWAYS `draft`. DERIVATION REGISTERS; IT DOES NOT RELEASE.**
            #
            # This read `deprecated if visibility == "legacy" else "admitted"` — so a tool went from
            # *present in the catalogue* to *served to a model* in one mechanical step, with no gate
            # anywhere between them. Once `lifecycle` began gating the surface that became the whole
            # ballgame: derivation would have been self-releasing, and *"only release a tool that
            # passed QC"* would be unenforceable by construction rather than merely unenforced.
            #
            # The two facts were conflated. **What the catalogue knows** is mechanical and derivable
            # (owner, lane, cost, and that a tool is legacy). **Whether we serve it** is a decision
            # with evidence behind it, and no property of the source can supply that. So every
            # derived row lands `draft` — registered, contract-checked, not on the wire — and
            # reaching `admitted` is a deliberate move through `check_transition`.
            #
            # `visibility: legacy` is not lost, it is just not a release: a legacy tool derives to
            # `draft` like everything else and is simply never promoted. That also closes the door
            # it used to open — `deprecated` IS served, so the old mapping put legacy tools on the
            # wire without anyone deciding to.
            lifecycle="draft",
            members=(),
        ),
        lane=lane,
        tier=tier,
        cost=token_cost(tool_def),
    )


def derive_all(catalogue: list[dict]) -> tuple[list[Derived], list[Underivable]]:
    """The whole catalogue. Returns `(derived, unresolved)` — **both**, always.

    🔴 **THE SECOND ELEMENT IS THE POINT.** A producer that silently skipped what it could not
    handle would report 100% coverage of the rows it chose to attempt, which is the self-derived
    denominator this run has been burned by more than once. Every input appears in exactly one of
    the two lists, and `coverage()` asserts that.
    """
    derived: list[Derived] = []
    unresolved: list[Underivable] = []
    for td in catalogue:
        try:
            derived.append(derive_one(td))
        except Underivable as exc:
            unresolved.append(exc)
    return derived, unresolved


def coverage(catalogue: list[dict]) -> dict:
    """The coverage fraction, with the **denominator taken from the input**, never from the output.

    Reported as a dict rather than printed so a gate can assert on it. `by_field` names which field
    defeated each unresolved tool, because "97% covered" is not actionable and "3 tools carry no
    declared tier" is.
    """
    derived, unresolved = derive_all(catalogue)
    total = len(catalogue)
    if len(derived) + len(unresolved) != total:
        raise AssertionError(
            f"{len(derived)} + {len(unresolved)} != {total}: an input reached neither list, so the "
            f"coverage fraction is measuring a set the caller did not hand in")
    by_field: dict[str, list[str]] = {}
    for exc in unresolved:
        by_field.setdefault(exc.field_name, []).append(exc.tool)
    return {
        "total": total,
        "derived": len(derived),
        "unresolved": len(unresolved),
        "by_field": {k: sorted(v) for k, v in sorted(by_field.items())},
    }
