"""CP-6.1 · closed-vocabulary resolution — the same shape as CP-5.3, for a value set instead of an id.

🔴 **MEASURED, ORGANIC CORPUS: `glossary_propose_entities` fails in 51 sessions, and 88 of its 109
failures (81%) are `unknown kind` — the model proposing an entity of a kind that does not exist in
that book's ontology.** It is the largest single defect left in the co-writer journey by the honest
denominator, and CP-5 admitted the tool against exactly this.

🔴 **AND THE REMEDY IT ALREADY HAS IS PROSE, WHICH MEASURABLY DID NOT WORK.** The current failure
message is complete and correct — it explains what an unknown kind means and names BOTH repair tools
(`glossary_adopt_standards` for the system kinds, `glossary_propose_kinds` for custom ones). It has
been saying so for the whole recorded period and the corpus is still 88 calls over 37 sessions.
**Third time on this board that a better sentence was the fix that did not fix it** (the placeholder
`entity_id`, the *"these carry the actual CONTENT"* missing-argument line, and now this).

⭐ **WHAT THE MEASUREMENT CHANGED ABOUT THE DESIGN.** Splitting the 154 recorded mentions against
`system_kinds`:

* **83 (54%) name a kind that IS a system standard the book never adopted** — `character` ×32,
  `item` ×14, `terminology` ×13, `location` ×11, `power_system` ×7, `organization` ×4, `event` ×2.
* 71 (46%) are not system kinds: genuinely custom world concepts (`cultivation_system`, `era`,
  `sect`, `soul_path`), near-misses (`place`, `power_systems`), and several that are not kinds at
  all but attributes or events (`betrayal` ×8, `cost` ×5, `toll` ×3).

So the model is not mostly inventing exotic categories; **more than half the time it asks for an
ordinary standard kind and the book simply has not adopted it.** The existing message names the
adoption TOOL and never the VALUE, so the model is told the mechanism and never the answer. A
refusal that carries the book's actual kinds *and* the exact adoptable standard is not better
prose — it is a closed set computed per book, which is a different kind of thing to hand a model.

**THE TWO BRANCHES, AND THERE IS NO THIRD (PO, 2026-08-10).** Every sent value is in the book's
vocabulary, or the call is refused with that vocabulary named. **There is no fuzzy arm**: `place` is
not silently rewritten to `location`, because a wrong kind is a SILENT bad write into canon, which
is worse than the loud failure it would replace. 5.3-pilot measured four entities tied at 0.9 for
one name and drew the same line there.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


VOCABULARY_REGISTRY_FILENAME = "agent-runtime-vocabularies.json"


class VocabularyContractViolation(ValueError):
    """A vocabulary row that cannot be trusted to run. Carries what would be legal (C-12)."""

    def __init__(self, vocabulary: str, problem: str, expected: str) -> None:
        self.vocabulary = vocabulary
        self.problem = problem
        self.expected = expected
        super().__init__(f"vocabulary {vocabulary!r} {problem}; expected {expected}")


@dataclass(frozen=True, slots=True)
class Vocabulary:
    """One closed value set, and the READ that enumerates it.

    `source_tool` answers *what may this field contain, in THIS book* — it is per-book data, which
    is why the set cannot live in the tool's JSON Schema as an enum. That is the whole reason this
    member needs a runtime resolver rather than a declaration: a static schema cannot express a
    vocabulary that differs per book.
    """

    name: str
    source_tool: str
    source_path: str
    value_field: str
    scope_params: tuple[str, ...]
    #: The wider set a value MAY be adopted from — the 54% case. Optional: a vocabulary with no
    #: standards source simply reports nothing adoptable, rather than pretending there is nothing.
    standards_tool: str = ""
    standards_path: str = ""
    standards_field: str = ""
    adopt_tool: str = ""
    create_tool: str = ""

    def scoped_args(self, call_args: dict) -> dict:
        return {p: call_args[p] for p in self.scope_params if p in call_args}


@dataclass(frozen=True, slots=True)
class VocabularyDecision:
    """The outcome for one parameter of one call. `ok` means every sent value is in the set."""

    tool: str
    param: str
    vocabulary: str
    sent: tuple[str, ...]
    allowed: tuple[str, ...]
    unknown: tuple[str, ...]
    #: Unknown values that ARE in the wider standard set — repairable by ONE adoption call.
    adoptable: tuple[str, ...] = ()
    #: Unknown values that are in neither — they need creating, or they are not kinds at all.
    custom: tuple[str, ...] = ()
    #: Exact-after-normalisation near misses, as a SUGGESTION only. Never substituted.
    did_you_mean: tuple[tuple[str, str], ...] = ()
    #: Carried on the decision rather than looked up by the message builder, so the refusal can name
    #: the repair CALL and not only the repair idea — the whole point of this member.
    adopt_tool: str = ""
    create_tool: str = ""
    outcome: str = "ok"

    @property
    def is_ok(self) -> bool:
        return self.outcome == "ok"


def check_vocabulary(vocab: Vocabulary, lane_of: Callable[[str], str | None]) -> None:
    """🔴 **THE SOURCE MUST BE `lane=read`, AND IT IS THE SAME SAFETY PROPERTY CP-5.3 STATED.**

    Enumerating a vocabulary dispatches a tool **the user never asked for**. `glossary_book_ontology_read`
    is tier `R` and harmless, but nothing structural stops a `W` tool being declared as a source, and
    the runtime would then perform an unrequested write on the way to validating an argument.
    Refused at registration, where it is a decision, rather than at dispatch, where it has happened.

    An UNKNOWN lane is refused for the same reason: *cannot be shown to be safe* fails closed.
    """
    for field, value in (("source_tool", vocab.source_tool),
                         ("source_path", vocab.source_path),
                         ("value_field", vocab.value_field)):
        if not value or not isinstance(value, str):
            raise VocabularyContractViolation(vocab.name, f"declares no {field}",
                                              f"a non-empty {field}")
    for tool_field, tool in (("source_tool", vocab.source_tool),
                             ("standards_tool", vocab.standards_tool)):
        if not tool:
            continue
        lane = lane_of(tool)
        if lane is None:
            raise VocabularyContractViolation(
                vocab.name,
                f"names {tool_field} {tool!r}, whose lane this runtime cannot determine",
                "a tool in the catalogue with a declared tier — a source that cannot be shown to "
                "be a read is refused, because enumeration dispatches it without the user asking")
        if lane != "read":
            raise VocabularyContractViolation(
                vocab.name,
                f"names {tool_field} {tool!r}, which is lane={lane!r}",
                "lane=read — enumeration dispatches this tool without the user asking for it")


def load_registry(doc: dict, lane_of: Callable[[str], str | None]) -> tuple[
        dict[str, Vocabulary], dict[tuple[str, str], str]]:
    """`(vocabularies by name, (tool, param path) -> vocabulary name)`. Every row is checked here.

    Raises rather than skipping a bad row: a registry that silently dropped an unsafe source would
    report a clean load while the binding naming it still exists — F-50's shape.
    """
    vocabs: dict[str, Vocabulary] = {}
    for name, row in (doc.get("vocabularies") or {}).items():
        if not isinstance(row, dict):
            raise VocabularyContractViolation(str(name), "is not an object", "a declaration object")
        v = Vocabulary(
            name=str(name),
            source_tool=str(row.get("source_tool") or ""),
            source_path=str(row.get("source_path") or ""),
            value_field=str(row.get("value_field") or ""),
            scope_params=tuple(str(p) for p in (row.get("scope_params") or ())),
            standards_tool=str(row.get("standards_tool") or ""),
            standards_path=str(row.get("standards_path") or ""),
            standards_field=str(row.get("standards_field") or ""),
            adopt_tool=str(row.get("adopt_tool") or ""),
            create_tool=str(row.get("create_tool") or ""),
        )
        check_vocabulary(v, lane_of)
        vocabs[v.name] = v

    bindings: dict[tuple[str, str], str] = {}
    for tool, block in (doc.get("bindings") or {}).items():
        if not isinstance(block, dict):
            raise VocabularyContractViolation(str(tool), "binding block is not an object",
                                              "a map of parameter path -> vocabulary name")
        for path, vocab_name in block.items():
            if vocab_name not in vocabs:
                raise VocabularyContractViolation(
                    str(vocab_name), f"is bound to {tool}.{path} but is not declared",
                    f"one of {sorted(vocabs)}")
            bindings[(str(tool), str(path))] = str(vocab_name)
    return vocabs, bindings


def values_at(call_args: Any, path: str) -> list[str]:
    """Every string an argument path selects. Supports ONE list hop, written `items[].kind`.

    No expression syntax and no wildcards beyond that hop, for §3a's reason: a language that can
    compute can read something it was not handed. `items[].kind` is the shape the measured defect
    lives in (a batch of entities each carrying a kind) and it is the only shape supported.
    """
    node: Any = call_args
    parts = path.split(".")
    for i, part in enumerate(parts):
        if part.endswith("[]"):
            key = part[:-2]
            if not isinstance(node, dict):
                return []
            seq = node.get(key)
            if not isinstance(seq, list):
                return []
            rest = ".".join(parts[i + 1:])
            out: list[str] = []
            for item in seq:
                out.extend(values_at(item, rest) if rest else
                           ([item] if isinstance(item, str) else []))
            return out
        if not isinstance(node, dict):
            return []
        node = node.get(part)
    return [node] if isinstance(node, str) else []


def dig(result: Any, path: str) -> list:
    """Follow a dotted path to a list. Shared shape with `refresolve._dig`, deliberately."""
    node = result
    for part in path.split("."):
        if not part:
            continue
        if not isinstance(node, dict):
            return []
        node = node.get(part)
    return node if isinstance(node, list) else []


def codes_from(result: Any, path: str, field: str) -> tuple[str, ...]:
    """The declared value set, read out of an already-fetched result."""
    out = []
    for row in dig(result, path):
        if isinstance(row, dict):
            code = row.get(field)
            if isinstance(code, str) and code:
                out.append(code)
        elif isinstance(row, str) and row:
            out.append(row)
    return tuple(dict.fromkeys(out))


def _normalise(value: str) -> str:
    """Lowercase, trim, and drop ONE trailing plural `s`.

    Used **only to suggest**, never to substitute. `power_systems` for `power_system` is a typo the
    model can act on once it is pointed out; rewriting it silently would be the guess arm this
    member does not have.
    """
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    return v[:-1] if len(v) > 3 and v.endswith("s") else v


@dataclass(frozen=True, slots=True)
class Pending:
    """One bound parameter of one call, and the reads that would answer it.

    Decision and fetch are separated for CP-5.3's reason, restated because it is load-bearing: the
    only place this runs is an `async` chokepoint while the tests and the replay are sync, and a
    second async copy of *"in the set or refused"* would mean the implementation under test is not
    the one that runs.
    """

    tool: str
    param: str
    vocabulary: Vocabulary
    sent: tuple[str, ...]
    source_args: dict


def pending_for(tool: str, call_args: dict, bindings: dict[tuple[str, str], str],
                vocabs: dict[str, Vocabulary]) -> list[Pending]:
    """Every bound parameter of one call that carries at least one value. Pure."""
    out: list[Pending] = []
    for (bound_tool, path), vocab_name in sorted(bindings.items()):
        if bound_tool != tool:
            continue
        sent = [v.strip() for v in values_at(call_args, path) if isinstance(v, str) and v.strip()]
        if not sent:
            continue
        v = vocabs[vocab_name]
        out.append(Pending(tool=tool, param=path, vocabulary=v,
                           sent=tuple(dict.fromkeys(sent)),
                           source_args=v.scoped_args(call_args)))
    return out


def decide(pending: Pending, source_result: Any,
           standards_result: Any = None) -> VocabularyDecision:
    """The two branches, from already-fetched results. **The single implementation.**"""
    v = pending.vocabulary
    allowed = codes_from(source_result, v.source_path, v.value_field)
    standards = (codes_from(standards_result, v.standards_path, v.standards_field)
                 if standards_result is not None and v.standards_path else ())

    allowed_set = set(allowed)
    unknown = tuple(s for s in pending.sent if s not in allowed_set)
    if not unknown:
        return VocabularyDecision(
            tool=pending.tool, param=pending.param, vocabulary=v.name,
            sent=pending.sent, allowed=allowed, unknown=(), outcome="ok")

    standards_set = set(standards)
    adoptable = tuple(u for u in unknown if u in standards_set)
    custom = tuple(u for u in unknown if u not in standards_set)

    # Suggestions, from BOTH sets, and only on an exact normalised match.
    by_norm = {_normalise(a): a for a in list(allowed) + list(standards)}
    suggestions = tuple(
        (u, by_norm[_normalise(u)]) for u in custom
        if _normalise(u) in by_norm and by_norm[_normalise(u)] != u
    )
    return VocabularyDecision(
        tool=pending.tool, param=pending.param, vocabulary=v.name,
        sent=pending.sent, allowed=allowed, unknown=unknown,
        adoptable=adoptable, custom=custom, did_you_mean=suggestions,
        adopt_tool=v.adopt_tool, create_tool=v.create_tool,
        outcome="unknown_value")


def refusal_message(decisions: list[VocabularyDecision]) -> str:
    """The refusal, carrying the VALUES rather than only the mechanism.

    🔴 **THIS IS THE ONE THING THE EXISTING FAILURE MESSAGE DOES NOT DO.** Today the model is told
    *"that category does not exist in this book yet — create the categories first"* and is named the
    two repair TOOLS. It is never told which values the book actually has, nor that more than half
    the time the kind it wants is a standard one call away. Naming the set is the difference between
    a description of the mechanism and an answer.
    """
    parts: list[str] = []
    for d in decisions:
        if d.is_ok:
            continue
        v_desc = ", ".join(f"'{a}'" for a in d.allowed) if d.allowed else "(none yet)"
        head = (f"{d.tool} was not called: {', '.join(repr(u) for u in d.unknown)} "
                f"{'is' if len(d.unknown) == 1 else 'are'} not in this book's vocabulary.")
        parts.append(head)
        parts.append(f"This book has: {v_desc}.")
        if d.adoptable:
            adopt = ", ".join(f"'{a}'" for a in d.adoptable)
            call = (f" — adopt in ONE call: {d.adopt_tool}(kinds=[{', '.join(repr(a) for a in d.adoptable)}])"
                    if d.adopt_tool else "")
            parts.append(
                f"{adopt} {'is a STANDARD kind' if len(d.adoptable) == 1 else 'are STANDARD kinds'} "
                f"this book has not adopted yet{call}.")
            # T13-D1 — THE ADOPT TOOL IS INTENT-GATED, so on a turn that is not world-setup this
            # message named the one remedy the SAME RUNTIME had just withheld.
            #
            # MEASURED LIVE 2026-08-13 (session 019ffa85), in a single turn: the refusal said
            # "adopt in ONE call: glossary_adopt_standards(kinds=['character'])", and that turn's
            # withheld_tools recorded glossary_adopt_standards, glossary_propose_kinds AND
            # glossary_propose_batch all withheld at stage=intent_gate ("world-setup tool withheld
            # unless the turn has world-setup intent"). The model read the ontology, listed the
            # system standards, could not adopt them, and retried the identical failing call.
            #
            # This is the exact shape filter_intent_gated_setup_tools' own docstring describes and
            # exempts RAILS for — "guidance and capability move as ONE signal" — except a refusal
            # emitted at runtime is guidance too, and nothing exempted it.
            #
            # `create_tool` (glossary_ontology_upsert) is NOT intent-gated and creates a kind
            # directly, so naming it alongside gives the model a remedy it can always reach. The
            # adopt tool stays FIRST because it is the better answer when available: it brings the
            # standard's attribute definitions with it, where a bare create does not. Whether the
            # gate should instead unlock a tool its own refusal names is DQ-T3, not decided here.
            if d.create_tool:
                parts.append(
                    f"If {d.adopt_tool or 'that tool'} is not among your available tools this turn, "
                    f"create {'it' if len(d.adoptable) == 1 else 'them'} directly with "
                    f"{d.create_tool} instead — same result, one call.")
        if d.custom:
            create = f" with {d.create_tool}" if d.create_tool else ""
            parts.append(
                f"{', '.join(repr(c) for c in d.custom)} "
                f"{'is' if len(d.custom) == 1 else 'are'} not a standard kind; create "
                f"{'it' if len(d.custom) == 1 else 'them'}{create} first if the story really "
                f"needs a new category.")
        for sent, near in d.did_you_mean:
            parts.append(f"Did you mean '{near}' rather than '{sent}'?")
    return " ".join(parts)
