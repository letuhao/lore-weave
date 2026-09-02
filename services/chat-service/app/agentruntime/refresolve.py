"""CP-5.3 · identifier resolution — how a NAME becomes an id, and why it never guesses.

`docs/specs/2026-08-09-v2-tool-contract/CP-5.md` §3a, gated on `5.3-pilot` (§3b), which cleared it.

**The failure.** Measured from `loreweave_chat`: **338 failed calls across 11 sessions sent a human
name into an id field** — `entity_id: "Ember Codex"`, `"Lâm Uyên"`, `"Count Dracula"` — 99.5% of
every UUID-type failure. A semantic type does not fix this. Declaring `entity_id: EntityId` rejects
`"Ember Codex"` one layer EARLIER: the same failure, moved forward, and the model still holds a name
and still cannot proceed.

**What the pilot established, on the population this serves rather than a convenient one.**
`ZERO_EXACT` was **0 in every stratum** — the resolver never came up empty on a name that failed.
The informative rate is the contested stratum (books holding 7–27 entities): **83.3% of pairs,
62.5% of calls, resolve to exactly one exact match.** The aggregate 91.5% is not quoted, because 77%
of measurable calls come from books holding ONE entity, where resolution cannot fail.

🔴 **AND AMBIGUITY IS MEASURED, NOT BOUNDED.** v3 argued from `0/18` that ambiguity was at most
15.4% by the rule of three. The pilot found it: querying `Dracula` in one book returns **four
`tier: exact` matches — three separate live entities of that literal name, plus `Count Dracula`
carrying `Dracula` as an alias — all tied at `rank_score` 0.9**, separable only by `updated_at`.
That is **37.5% of the contested calls**. So the refusal branch is not an edge case to be tidied
away later; it is a first-class branch carrying more than a third of the traffic, and a
`rank_score` tiebreak would have been a guess deciding a correctness question.

**The two branches, and there is deliberately no third:**

| condition | action |
|---|---|
| exactly **one** match at the declared quality | substitute, dispatch, and **record the substitution** |
| zero, or **more than one** | **refuse**, and return the candidates as a structured error |

**Why the refusal is still an improvement.** Today a name yields `entity_id must be a UUID` — loud
but not actionable. Under this contract the same input yields *"'Ember Codex' matched no entity
exactly"* with candidates. Both are loud; only one can be acted on. **The contract may remove a
failure's COST; it may never remove its SIGNAL** (§3) — so a refusal here is recorded as a refusal,
never as a quiet success.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

#: Where the ref/resolver map lives. 🔴 **A REGISTRY ROW, NOT A CHAT-SERVICE CONSTANT** — W1's
#: correction, and the same one §4a took for the contract itself. Written as a constant here it
#: would be the hardcoding the PO rejected; written as a registry row it is the runtime control that
#: was asked for, authored once per ref type and pushed upstream into `_meta` when the owning
#: service catches up.
REF_REGISTRY_FILENAME = "agent-runtime-ref-resolvers.json"

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class RefContractViolation(ValueError):
    """A ref/resolver declaration that may not be registered."""

    def __init__(self, ref_type: str, problem: str, expected: str) -> None:
        self.ref_type = ref_type
        self.problem = problem
        self.expected = expected
        super().__init__(f"ref type {ref_type!r} {problem}; expected {expected}")


@dataclass(frozen=True, slots=True)
class Resolver:
    """How one ref type turns a name into an id.

    A statement about **how two existing tools relate**, which is why it needs no other team to
    start — unlike a schema annotation, which needs the owning service to change first.
    """

    ref_type: str
    #: The tool that answers "what is this name?". MUST be lane=read — see `check_resolver`.
    tool: str
    #: The parameter the name goes into.
    query_param: str
    #: Parameters copied from the ORIGINAL call, so a resolution is scoped exactly as the call is
    #: (an entity name is only unique within its book).
    scope_params: tuple[str, ...]
    #: Where the candidates live in the result, and which field carries the id.
    result_path: str
    id_field: str
    #: The MATCH-QUALITY gate. `glossary_search` returns `tier`, and `tier == "exact"` means the
    #: name or one of the entity's aliases matched exactly — it is not a fuzzy score.
    match_field: str
    match_value: str
    #: Shown to a human when the resolution refuses, so the refusal is actionable.
    name_field: str = ""

    def scoped_args(self, call_args: dict, name: str) -> dict:
        out: dict[str, Any] = {self.query_param: name}
        for p in self.scope_params:
            if p in call_args:
                out[p] = call_args[p]
        return out


@dataclass(frozen=True, slots=True)
class Candidate:
    id: str
    name: str
    quality: str


@dataclass(frozen=True, slots=True)
class Resolution:
    """One parameter's outcome. Returned whole — a boolean would make a refusal unactionable."""

    param: str
    ref_type: str
    sent: str
    #: Set only on the single-match branch.
    resolved: str | None = None
    candidates: tuple[Candidate, ...] = field(default=())
    #: `resolved` | `no_match` | `ambiguous` | `truncated` | `resolver_failed`
    #: `truncated` is kept DISTINCT from `ambiguous`: one says the candidates conflict, the
    #: other says we cannot see all of them. Merging them would hide which defect to fix.
    outcome: str = "no_match"

    @property
    def ok(self) -> bool:
        return self.outcome == "resolved"


def looks_like_an_id(value: Any) -> bool:
    """A value that is already an opaque id needs no resolution.

    Deliberately strict — a UUID, not "anything that is not obviously a name". The pilot measured
    what the model actually sends into these fields, and the classes are distinct: a NAME (this
    member's subject), a MANGLED uuid (a dropped nibble — a different defect, and resolving it
    would invent a match for a typo), a PLACEHOLDER the model invented, and a quantifier like
    `"all"` which no resolver can serve because the parameter cannot express it (W3).

    🔴 **The canonical form ONLY, by regex — `uuid.UUID()` is not used and cannot be.** The membrane
    gate refuses `import uuid` inside this package as an ambient API, and that turned out to make
    the check stricter rather than merely compliant: `uuid.UUID()` accepts an unhyphenated hex run
    and a `urn:uuid:` prefix, neither of which any tool here emits, so accepting them would have
    meant treating a shape the catalogue never produces as an id that needs no resolution.
    """
    if not isinstance(value, str):
        return False
    if _UUID_RE.match(value):
        return True
    return False


def check_resolver(resolver: Resolver, lane_of: Callable[[str], str | None]) -> None:
    """🔴 **A RESOLVER MUST BE `lane=read`, AND THIS IS A SAFETY PROPERTY, NOT A PREFERENCE.**

    Auto-resolution dispatches a tool **the user never asked for**. `glossary_search` is tier `R`,
    so it is auto-approved and harmless — but nothing structural stopped a `W` tool being declared
    as a resolver, and the runtime would then perform an unrequested **write** on the way to
    answering a read. Refused at registration, where it is a decision, rather than at dispatch,
    where it would already have happened.

    An UNKNOWN lane is refused too: a resolver whose tool is not in the catalogue cannot be shown
    to be a read, and *"cannot be shown to be safe"* fails closed.
    """
    for name, value in (("tool", resolver.tool), ("query_param", resolver.query_param),
                        ("result_path", resolver.result_path), ("id_field", resolver.id_field),
                        ("match_field", resolver.match_field),
                        ("match_value", resolver.match_value)):
        if not value or not isinstance(value, str):
            raise RefContractViolation(resolver.ref_type, f"declares no {name}",
                                       f"a non-empty {name}")
    lane = lane_of(resolver.tool)
    if lane is None:
        raise RefContractViolation(
            resolver.ref_type,
            f"names resolver {resolver.tool!r}, whose lane this runtime cannot determine",
            "a tool in the catalogue with a declared tier — a resolver that cannot be shown to be "
            "a read is refused, because resolution dispatches it without the user asking")
    if lane != "read":
        raise RefContractViolation(
            resolver.ref_type,
            f"names resolver {resolver.tool!r}, which is lane={lane!r}",
            "lane=read — auto-resolution dispatches this tool without the user asking for it, so a "
            "non-read resolver would perform an unrequested action or write (§3a)")


def load_registry(doc: dict, lane_of: Callable[[str], str | None]) -> tuple[
        dict[str, Resolver], dict[tuple[str, str], str]]:
    """`(resolvers by ref type, (tool, param) -> ref type)`. Every resolver is checked here.

    Raises rather than skipping a bad row: a registry that silently dropped an unsafe resolver
    would report a clean load while the binding it names still exists.
    """
    resolvers: dict[str, Resolver] = {}
    for ref_type, row in (doc.get("ref_types") or {}).items():
        if not isinstance(row, dict):
            raise RefContractViolation(str(ref_type), "is not an object", "a resolver declaration")
        r = Resolver(
            ref_type=str(ref_type),
            tool=str(row.get("resolver_tool") or ""),
            query_param=str(row.get("query_param") or ""),
            scope_params=tuple(row.get("scope_params") or ()),
            result_path=str(row.get("result_path") or ""),
            id_field=str(row.get("id_field") or ""),
            match_field=str(row.get("match_field") or ""),
            match_value=str(row.get("match_value") or ""),
            name_field=str(row.get("name_field") or ""),
        )
        check_resolver(r, lane_of)
        resolvers[r.ref_type] = r

    bindings: dict[tuple[str, str], str] = {}
    for tool, params in (doc.get("bindings") or {}).items():
        if not isinstance(params, dict):
            raise RefContractViolation(str(tool), "binding is not an object",
                                       "{param: ref_type}")
        for param, ref_type in params.items():
            if ref_type not in resolvers:
                raise RefContractViolation(
                    str(ref_type),
                    f"is bound to {tool}.{param} but no resolver declares it",
                    f"one of {sorted(resolvers)} — a binding naming an undeclared ref type would "
                    f"silently never resolve")
            bindings[(str(tool), str(param))] = str(ref_type)
    return resolvers, bindings


#: The bound `resolve_call` asks for. A result holding exactly this many rows may have had more.
#: Mirrors `glossary_search`'s own default (`searchToolDefaultLimit`), which is what the resolver
#: sends; a tool that DECLARES its completeness (`page.is_complete`) is read from the declaration
#: instead, which is the whole point of the member.
RESOLVER_PAGE_LIMIT = 20


def _page_cap(result: Any) -> int:
    """How many rows would mean *"possibly truncated"*.

    Prefers the tool's OWN completeness declaration when it makes one — `is_complete: true` means
    the list is whole no matter how long it is, so the cap is unreachable. Falls back to the
    requested bound for the tools measured to declare nothing.
    """
    if isinstance(result, dict):
        page = result.get("page")
        block = page if isinstance(page, dict) else result
        complete = block.get("is_complete") if isinstance(block, dict) else None
        if complete is True:
            return 1 << 30
        if isinstance(block, dict) and block.get("has_more") is False:
            return 1 << 30
    return RESOLVER_PAGE_LIMIT


def _dig(result: Any, path: str) -> list:
    """Follow a dotted path to the candidate list. No expression syntax, for §3a's reason: a
    language that can compute can read something it was not handed."""
    node = result
    for part in path.split("."):
        if not part:
            continue
        if not isinstance(node, dict):
            return []
        node = node.get(part)
    return node if isinstance(node, list) else []


@dataclass(frozen=True, slots=True)
class Pending:
    """One parameter that needs resolving, and the call that would answer it.

    🔴 **DECIDING WHAT TO RESOLVE IS SEPARATED FROM FETCHING IT, and that is not tidiness.** The one
    place this must run — the dispatch chokepoint in `stream_service` — is `async`, while the tests
    and the measurement replay are sync. A second async copy of the decision logic would be two
    implementations of *"exactly one match or refuse"*, and the one under test would not be the one
    that runs. So the decision is pure (`decide`), and each caller does its own fetching.
    """

    param: str
    resolver: Resolver
    name: str
    args: dict


def pending_for(tool: str, call_args: dict, bindings: dict[tuple[str, str], str],
                resolvers: dict[str, Resolver]) -> list[Pending]:
    """Every ref-shaped parameter of one call that carries a NAME rather than an id. Pure."""
    out: list[Pending] = []
    for param, value in sorted(call_args.items()):
        ref_type = bindings.get((tool, param))
        if ref_type is None or looks_like_an_id(value):
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        r = resolvers[ref_type]
        out.append(Pending(param=param, resolver=r, name=value.strip(),
                           args=r.scoped_args(call_args, value.strip())))
    return out


def decide(resolver: Resolver, param: str, name: str, result: Any) -> Resolution:
    """The two branches, from an already-fetched result. **The single implementation.**"""
    rows = _dig(result, resolver.result_path)
    matched = [r for r in rows if isinstance(r, dict)
               and r.get(resolver.match_field) == resolver.match_value]
    candidates = tuple(
        Candidate(id=str(r.get(resolver.id_field) or ""),
                  name=str(r.get(resolver.name_field) or "") if resolver.name_field else "",
                  quality=str(r.get(resolver.match_field) or ""))
        for r in rows if isinstance(r, dict)
    )
    # 🔴 **CP-5.6 — "EXACTLY ONE" IS ONLY TRUE IF THE LIST WAS NOT TRUNCATED, AND THIS RESOLVER'S
    # OWN SOURCE NEVER SAYS.** Measured 2026-08-10: of the 36 tools that declare paging, **five
    # never report completeness at all** — `kg_project_list`, `memory_search`, `jobs_list`,
    # `book_get_chapter`, and **`glossary_search`, which is this resolver's tool**. It returns at
    # most `limit` rows and no `is_complete`, so a full page is indistinguishable from a page that
    # had more behind it.
    #
    # The exact tier is filled FIRST, so one exact among a truncated page is still the only exact
    # — unless the exacts themselves fill the page, and then a second one may be sitting just past
    # the cap. Substituting there would be a silent wrong answer, which is worse than every
    # failure this member exists to fix. Refused instead, and named as its own outcome so it never
    # merges with a genuine ambiguity.
    if matched and len(matched) >= len(rows) and len(rows) >= _page_cap(result):
        return Resolution(param=param, ref_type=resolver.ref_type, sent=name,
                          candidates=candidates, outcome="truncated")
    if len(matched) == 1:
        return Resolution(param=param, ref_type=resolver.ref_type, sent=name,
                          resolved=str(matched[0].get(resolver.id_field) or ""),
                          candidates=candidates, outcome="resolved")
    # 🔴 NO "PICK THE BEST" ARM. With four candidates tied at 0.9 the runtime would be choosing by
    # `updated_at`, which is a guess deciding a correctness question (§0.14).
    return Resolution(param=param, ref_type=resolver.ref_type, sent=name, candidates=candidates,
                      outcome="ambiguous" if len(matched) > 1 else "no_match")


def resolve_call(tool: str, call_args: dict, bindings: dict[tuple[str, str], str],
                 resolvers: dict[str, Resolver],
                 dispatch: Callable[[str, dict], Any]) -> list[Resolution]:
    """The SYNC composition of `pending_for` + fetch + `decide`, for tests and the measurement
    replay. The async caller at the dispatch chokepoint composes the same two pure halves itself.

    **This function does not mutate `call_args`.** The caller substitutes, so the record of what the
    model sent is captured before anything overwrites it — the separation `plan_supplied.overrode`
    had to make, for the same reason.
    """
    out: list[Resolution] = []
    for p in pending_for(tool, call_args, bindings, resolvers):
        try:
            result = dispatch(p.resolver.tool, p.args)
        except Exception:
            # A resolver that fails is not a licence to guess, and not a silent pass either: the
            # outcome is recorded as `resolver_failed` and the argument is left as the model sent it.
            out.append(Resolution(param=p.param, ref_type=p.resolver.ref_type, sent=p.name,
                                  outcome="resolver_failed"))
            continue
        out.append(decide(p.resolver, p.param, p.name, result))
    return out


def apply_resolutions(call_args: dict, resolutions: list[Resolution]) -> dict:
    """Substitute the resolved ids and return the RECORD of what happened.

    The record is the point, not a by-product: without it a resolved argument and a model-typed one
    are the same row, and no measurement can tell whether the mechanism did anything (the round-2
    V-METRIC table was half theatre for exactly this reason).
    """
    resolved = [r for r in resolutions if r.ok]
    for r in resolved:
        call_args[r.param] = r.resolved
    return {
        "params": sorted(r.param for r in resolved),
        "model_sent": {r.param: r.sent for r in resolved},
        "resolved": {r.param: r.resolved for r in resolved},
        "refused": sorted(r.param for r in resolutions if not r.ok),
        "outcomes": {r.param: r.outcome for r in resolutions},
    }


def refusal_message(resolutions: list[Resolution]) -> str:
    """The actionable half. Today the model gets `entity_id must be a UUID`; this names what it
    sent, what happened, and what it could have meant."""
    parts = []
    for r in resolutions:
        if r.ok:
            continue
        shown = [c for c in r.candidates if c.name][:5]
        if r.outcome == "ambiguous":
            names = ", ".join(f"{c.name!r} ({c.id})" for c in shown) or "several entries"
            parts.append(
                f"{r.param}: {r.sent!r} matched MORE THAN ONE entry exactly — {names}. "
                f"Pick one and pass its id; this cannot be guessed for you.")
        elif r.outcome == "truncated":
            parts.append(
                f"{r.param}: {r.sent!r} matched the maximum number of entries the search can "
                f"return, so there may be more it could not show. Narrow the name or pass the id "
                f"directly; picking one from a partial list could be wrong.")
        elif r.outcome == "no_match":
            names = ", ".join(repr(c.name) for c in shown)
            parts.append(
                f"{r.param}: {r.sent!r} matched no entry exactly."
                + (f" Did you mean {names}?" if names else " Search first, then pass the id."))
        else:
            parts.append(f"{r.param}: could not be resolved ({r.outcome}); pass the id directly.")
    return " ".join(parts)


# ── The ABSENT-argument branch (DQ-T76) ──────────────────────────────────────
#
# 🔴 EVERYTHING ABOVE RESOLVES A NAME SITTING IN AN ID FIELD. Measured on the corpus AFTER
# that shipped, that is the SMALLER failure by an order of magnitude:
#
#     the id argument is ABSENT entirely   685 failures / 55 tools   (89%)
#     a NAME was passed into an id field    86 failures / 20 tools   (11%)
#
# 🔴 AND THE OBVIOUS REMEDY IS ALREADY BUILT AND ALREADY MEASURED FAILING. `argument_emitters`
# declares WHICH TOOL SUPPLIES each required id — 88 pairs, and **632 of the 723 failures
# (87%) are on pairs it ALREADY covers**. The refusal names that supplier to the model. Of
# 605 (session, tool) pairs that failed this way, only **51 (8%) ever succeeded with that
# tool again in the same session** — and that count is generous, since it credits successes
# that happened BEFORE the failure. Telling the model where the id comes from is a mechanism
# that FIRES and does not MATTER.
#
# So this branch does what the name branch does — it FETCHES — rather than advising. The
# two-branch contract is unchanged and is the whole safety story: exactly one candidate
# substitutes, anything else REFUSES. Ambiguity here is not hypothetical; the 5.3 pilot
# measured it at 37.5% of contested calls, which is why there is no "pick the best" arm.
#
# What a refusal returns is still strictly better than today: the model currently gets the
# NAME OF A TOOL TO GO CALL, and gets back the actual rows to choose between.

#: Prefixes that name the id's ROLE in a call, not the KIND of record it identifies.
#: `composition_motif_link_edit` requires from_motif_id/to_motif_id while its supplier
#: `composition_motif_link_list` returns `motif_id` — 168 failures that a literal-name match
#: scores as unsupplied.
_ROLE_PREFIX = re.compile(r"^(from|to|source|target|parent|child|left|right)_")

#: Where a human label lives, in preference order. A candidate without one is still returned
#: — an id with no label is worse to choose between, but hiding it would be worse still.
_LABEL_FIELDS = ("cached_name", "name", "title", "display_name", "label", "alias")


def bare_id_field(param: str) -> str:
    """`from_motif_id` → `motif_id`. The role is about this call; the field is about the record."""
    return _ROLE_PREFIX.sub("", param)


def harvest(result: Any, id_field: str, _depth: int = 0) -> tuple[Candidate, ...]:
    """Every record in a supplier's result that carries `id_field` as a canonical UUID.

    🔴 **THE VALUE MUST BE A UUID, NOT MERELY THE KEY.** Keyed on the field NAME alone, the
    sizing pass credited `tool_load` as a supplier of world_id/map_id/job_id — it returns tool
    SCHEMAS, where every id parameter appears as a property KEY. A schema describes an
    argument; it is not a value anything can pass. Requiring the value to parse as a UUID
    removes that entire class, and it reuses `looks_like_an_id` so this agrees with the name
    branch about what an id IS rather than keeping a second opinion.

    Walks nested structures because suppliers wrap their rows differently (`entities[]`,
    `models[]`, `page.items[]`); depth is bounded so a cyclic or pathological payload cannot
    spin. Order is preserved and duplicates by id are collapsed — the same record appearing
    twice is one choice, not an ambiguity.
    """
    if _depth > 8:
        return ()
    out: list[Candidate] = []
    if isinstance(result, dict):
        value = result.get(id_field)
        if looks_like_an_id(value):
            label = ""
            for f in _LABEL_FIELDS:
                if isinstance(result.get(f), str) and result[f].strip():
                    label = result[f].strip()
                    break
            out.append(Candidate(id=str(value), name=label, quality="listed"))
        for v in result.values():
            out.extend(harvest(v, id_field, _depth + 1))
    elif isinstance(result, list):
        for v in result:
            out.extend(harvest(v, id_field, _depth + 1))
    seen: set[str] = set()
    unique: list[Candidate] = []
    for c in out:
        if c.id not in seen:
            seen.add(c.id)
            unique.append(c)
    return tuple(unique)


def decide_absent(param: str, supplier_tool: str, result: Any) -> Resolution:
    """The two branches for a MISSING id, from an already-fetched supplier result.

    Mirrors `decide` deliberately, including its vocabulary, so a reader comparing the two
    branches sees one contract rather than two dialects. `sent` is empty because nothing was
    sent — that is the difference between this branch and the name branch, and it is worth
    being able to see in a recorded resolution.
    """
    candidates = harvest(result, bare_id_field(param))
    if len(candidates) == 1:
        return Resolution(param=param, ref_type=supplier_tool, sent="",
                          resolved=candidates[0].id, candidates=candidates,
                          outcome="resolved")
    if not candidates:
        return Resolution(param=param, ref_type=supplier_tool, sent="",
                          candidates=(), outcome="no_match")
    return Resolution(param=param, ref_type=supplier_tool, sent="",
                      candidates=candidates, outcome="ambiguous")


def accept_pick(param: str, pick: Any, candidates: Any) -> str | None:
    """The id to substitute for a disambiguation resume, or None to refuse.

    🔴 **THE PICK MUST BE ONE WE OFFERED.** The resume payload arrives from the client, so an
    id that was never on the card is not a choice — it is an unvalidated identifier reaching a
    tool the author approved for a DIFFERENT row. Membership in the offered set is the whole
    check; shape alone would accept any well-formed UUID.

    Refuses rather than guesses on every other input — a cancelled card, a stale payload, a
    name instead of an id. Choosing on the author's behalf is the exact move this card exists
    to avoid, and it would be worst here, where a pick can drive a destructive call.
    """
    if not param or not isinstance(pick, str) or not looks_like_an_id(pick):
        return None
    offered = {
        str(c.get("id")) for c in (candidates or [])
        if isinstance(c, dict) and c.get("id")
    }
    return pick if pick in offered else None
