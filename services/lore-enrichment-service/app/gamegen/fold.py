"""S3 — the fold. Deterministic, dense, and accountable in both directions.

Doc 39 §5. Three properties, each of which v1 asserted and none of which it had:

**Deterministic** (`PGN-A10`). No model runs here. Every value in the output came
from an approved answer's ``value``; this module chooses *placement*, never
content. That is why `S2` resolves the value under the human signature — a fold
that had to read ``proposed_text`` and decide *"I'd call it a staged ladder"*
means `ProgressionType::Stage` would be a model at consolidation, which is exactly
the stage `PGN-A10` removes.

**Dense** (§5). ``body_json`` carries *N* tier objects, not two and a count. v1's
sparse ``{tier_count: 24}`` required S5 to synthesise **132 required values** from
one integer, of which exactly one had a policy path — so 131 fields would have
been engine-defaulted with nothing recording that they were. Every leaf here is a
:class:`Cell` carrying its ``answer_id``, so "where did this come from" always has
an answer.

**Accountable** (`PGN-A9`). The ledger runs **both ways**:

* every approved answer maps to **≥1 JSON-Pointer**, or the fold REFUSES naming
  the answer. v1 offered a count identity as the mechanism, which cannot see
  `PGN-A9`'s own worked example: rows-in equals rows-out while a leaf vanishes.
* every leaf in ``body_json`` carries the ``answer_id`` that produced it, so S5's
  ``read_set`` can be checked against it from the other side.

## The three things a cell can be

A leaf is never a bare value, because *"the book does not say"* and *"this needs a
module that does not exist"* are **answers**, and flattening either to a default
is the silent-drop class this pipeline exists to prove it cannot ship.

``value``    — a settled value, with the answer that settled it.
``not_stated`` — `PGN-A4`. Complete, approvable in one click, and accountable: the
             reason is a closed set and S5 refuses it on a required field.
``refused``  — `PGN-A20`. An out-of-scope requirement, **named, with its owning
             module**. Recorded rather than dropped, which is the whole point:
             寒潭 (a *place*) as a training condition is a real requirement the
             book states, and the honest artifact says *"refused — requires the
             place module"*, not silence.

## Pattern expansion (`PGN-A11`)

*"sub-levels are named 一層…九層"* is **one** approved answer that the fold expands
to nine dense rows. The human approves the pattern; the code does the expansion.
Every expanded cell carries the same ``answer_id``, so nine leaves and one decision
are consistent — and the ledger sees one answer with nine pointers, which is what
`PGN-A9` asks for.

## What the fold refuses to emit

`PGN-A5` / T2: a **magnitude** must never reach ``body_json``. How many tiers and
which is fourth are facts a span supports; how much grinding a tier costs is a
balance decision that belongs to S4's policy. :func:`assert_no_magnitude_leaked`
walks the finished structure and refuses any number outside the
``{ordinal, count, index}`` class **by pointer**, so planting ``tier_max: 500``
in a fixture is a refusal rather than a plausible-looking artifact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "Cell",
    "CreativeStructure",
    "FoldRefusal",
    "OUT_OF_SCOPE_OWNERS",
    "ORDINAL_LEAVES",
    "fold",
    "content_hash",
    "NUMERALS",
    "assert_no_magnitude_leaked",
]

_DOMAIN = b"lw.gamegen.structure.v1"

#: The only leaf names allowed to hold a number. Everything else numeric is a
#: MAGNITUDE and belongs to S4's policy (`PGN-A5`). Names, not paths, because the
#: same leaf means the same thing wherever the schema puts it — and a path list
#: would be default-uncovered the moment a nesting level is added.
ORDINAL_LEAVES = frozenset({"tier_index", "tier_count", "initial_tier", "kind_count"})

#: `PGN-A20` — an element the progression module cannot resolve, and **who owns
#: it**. A refusal that does not name an owner is a refusal nobody can act on, and
#: it decays into "the pipeline does not support that" within one session.
OUT_OF_SCOPE_OWNERS: Mapping[str, str] = {
    "place": "CPL-A3 place element module (TrainingCondition::LocationMatch needs a PlaceTypeRef)",
    "item": "CPL-A3 item element module (TrainingCondition::InstrumentMatch needs an ItemRef)",
    "actor": "CPL-A3 actor element module (TargetMatch needs both a place and an item)",
}


class FoldRefusal(Exception):
    """The fold cannot produce an honest structure, and says exactly why.

    Never a warning and never a partial result. A fold that emitted a structure
    plus a list of complaints would ship the structure, because the next stage
    reads the structure.
    """


@dataclass(frozen=True)
class Cell:
    """One leaf. Exactly one of value / not_stated / refused, always with an answer."""

    answer_id: str
    value: Any = None
    not_stated: bool = False
    not_stated_reason: str | None = None
    refused_owner: str | None = None
    refused_requirement: str | None = None

    @property
    def state(self) -> str:
        if self.refused_owner is not None:
            return "refused"
        return "not_stated" if self.not_stated else "value"

    def as_json(self) -> dict[str, Any]:
        base: dict[str, Any] = {"state": self.state, "answer_id": self.answer_id}
        if self.state == "value":
            base["value"] = self.value
        elif self.state == "not_stated":
            base["reason"] = self.not_stated_reason
        else:
            base["owner"] = self.refused_owner
            base["requirement"] = self.refused_requirement
        return base


@dataclass(frozen=True)
class CreativeStructure:
    element_kind: str
    body: dict[str, Any]
    #: ``answer_id -> [JSON-Pointer, …]``. The forward half of `PGN-A9`.
    consumption: dict[str, list[str]]
    #: ``[(answer_id, answer_hash), …]``. **Hash-linked, not id-linked** — v1
    #: referenced answers by bare id, so an UPDATE after pinning could retroactively
    #: convert an invented tier into an extracted one with every hop still green.
    answer_refs: list[tuple[str, str]]
    content_hash: str


# ── the answers, as the fold needs them ─────────────────────────────────────


@dataclass(frozen=True)
class ApprovedAnswer:
    """One approved answer, flattened out of the S2 rows the fold reads.

    ``question_path`` comes from the brief, not from the answer: the answer knows
    its ``question_id`` and the brief maps that to a schema position. Carrying the
    path on the answer would let two answers to the same question claim different
    positions.
    """

    answer_id: str
    answer_hash: str
    question_id: str
    question_path: str
    target_ref: str
    value: Any
    not_stated: bool
    not_stated_reason: str | None


def _pointer(*parts: object) -> str:
    """RFC-6901. ``~`` and ``/`` are escaped because a kind id is author-supplied
    and a slash in one would silently split a pointer into two segments."""
    out = ""
    for p in parts:
        s = str(p).replace("~", "~0").replace("/", "~1")
        out += "/" + s
    return out


def _cell_from(a: ApprovedAnswer) -> Cell:
    """The three states, decided from the answer alone.

    ``refused`` is recognised by the value's shape rather than a separate column:
    an S2 reviewer marks an out-of-scope requirement by answering
    ``{"out_of_scope": "place", "requirement": "…"}``. Recognised here rather than
    in the schema because the OWNER map is a property of the progression module,
    and a new element module changes it without a migration.
    """
    if a.not_stated:
        return Cell(answer_id=a.answer_id, not_stated=True, not_stated_reason=a.not_stated_reason)

    if isinstance(a.value, dict) and "out_of_scope" in a.value:
        kind = a.value["out_of_scope"]
        owner = OUT_OF_SCOPE_OWNERS.get(kind)
        if owner is None:
            raise FoldRefusal(
                f"answer {a.answer_id} marks {a.question_path!r} out of scope as {kind!r}, "
                f"which names no owning module. Known: {sorted(OUT_OF_SCOPE_OWNERS)}. "
                f"A refusal that does not name an owner is one nobody can act on, and it "
                f"decays into 'the pipeline does not support that' within a session."
            )
        return Cell(
            answer_id=a.answer_id,
            refused_owner=owner,
            refused_requirement=a.value.get("requirement", "(unstated)"),
        )

    return Cell(answer_id=a.answer_id, value=a.value)


# ── the fold ────────────────────────────────────────────────────────────────

_KIND_LEAF_PATHS = {
    "kind.name": "name",
    "kind.progression_type": "progression_type",
    "kind.curve": "curve",
    "kind.cap_rule": "cap_rule",
    "kind.initial_tier": "initial_tier",
    "kind.tier_count": "tier_count",
}
_TIER_LEAF_PATHS = {
    "kind.tier[].tier_index": "tier_index",
    "kind.tier[].name": "name",
    "kind.tier[].within_tier_curve": "within_tier_curve",
    "kind.tier[].breakthrough": "breakthrough",
}
_CARDINALITY_PATH = "kind.quantity"


def fold(
    *,
    element_kind: str,
    schema_fingerprint: str,
    answers: Sequence[ApprovedAnswer],
    max_batch_size: int | None = None,
    batch_sizes: Iterable[int] = (),
) -> CreativeStructure:
    """Fold approved answers into a dense creative structure.

    :param max_batch_size: T3's ceiling — S3 refuses a run containing a bulk
        approval larger than the deployment allows. ``None`` means no ceiling,
        which is the honest default: a ceiling nobody chose is a number that looks
        like a policy.
    :raises FoldRefusal: on a missing cardinality answer, an unconsumed approved
        answer, a magnitude in the body, an unowned out-of-scope marker, or a
        batch above the ceiling.
    """
    if max_batch_size is not None:
        for size in batch_sizes:
            if size > max_batch_size:
                raise FoldRefusal(
                    f"a batch of {size} decisions was approved in one action and this "
                    f"deployment's ceiling is {max_batch_size}. T3 is 'nothing reaches "
                    f"players unreviewed'; a batch big enough that nobody read it is the "
                    f"way that fails while every signature is present."
                )

    consumption: dict[str, list[str]] = {}
    refs: dict[str, str] = {}

    def record(a: ApprovedAnswer, pointer: str) -> None:
        consumption.setdefault(a.answer_id, []).append(pointer)
        refs[a.answer_id] = a.answer_hash

    by_target: dict[str, dict[str, ApprovedAnswer]] = {}
    cardinality: ApprovedAnswer | None = None
    for a in answers:
        if a.question_path == _CARDINALITY_PATH:
            if cardinality is not None:
                raise FoldRefusal(
                    f"two approved answers claim the cardinality of {element_kind!r} "
                    f"({cardinality.answer_id}, {a.answer_id}). Nothing downstream can "
                    f"say which list of kinds the structure is."
                )
            cardinality = a
            continue
        slot = by_target.setdefault(a.target_ref, {})
        if a.question_path in slot:
            raise FoldRefusal(
                f"two approved answers for {a.question_path!r} on {a.target_ref!r} "
                f"({slot[a.question_path].answer_id}, {a.answer_id}). The live-answer "
                f"index should have made this impossible; the fold refuses rather than "
                f"picking one."
            )
        slot[a.question_path] = a

    if cardinality is None:
        raise FoldRefusal(
            f"no approved answer for {_CARDINALITY_PATH!r}. Without it the fold does not "
            f"know which kinds exist, and inventing an empty list would produce a "
            f"structurally valid element containing nothing."
        )
    if cardinality.not_stated:
        raise FoldRefusal(
            "the cardinality answer is `not_stated`. `PGN-A4` makes that a COMPLETE "
            "answer and this is the field where complete is still not resolvable - a "
            "progression system whose corpus never says which ladders exist has nothing "
            "to generate, and defaulting to one would author the book's premise."
        )

    kind_ids = list(cardinality.value or [])
    if not kind_ids:
        raise FoldRefusal("the cardinality answer names no kinds")
    if len(set(kind_ids)) != len(kind_ids):
        raise FoldRefusal(f"the cardinality answer repeats a kind: {kind_ids}")

    body: dict[str, Any] = {"element_kind": element_kind, "kinds": []}
    record(cardinality, _pointer("kinds"))

    for k_i, kind_id in enumerate(kind_ids):
        target = f"kind:{kind_id}"
        slot = by_target.get(target, {})
        kind_obj: dict[str, Any] = {"id": kind_id}
        base = _pointer("kinds", k_i)

        for path, leaf in _KIND_LEAF_PATHS.items():
            a = slot.get(path)
            if a is None:
                raise FoldRefusal(
                    f"{target}: no approved answer for {path!r}. The brief asserts every "
                    f"REQUIRED position has a question (`PGN-A2`), so a missing answer here "
                    f"means the question was asked and never decided - and folding around "
                    f"it would fill the field with a default nobody chose."
                )
            kind_obj[leaf] = _cell_from(a).as_json()
            record(a, base + _pointer(leaf))

        n = _tier_count(kind_obj, target)
        kind_obj["tiers"] = []
        for t_i in range(n):
            tier: dict[str, Any] = {}
            for path, leaf in _TIER_LEAF_PATHS.items():
                a = slot.get(path)
                if a is None:
                    raise FoldRefusal(
                        f"{target}: no approved answer for {path!r}, and the ladder has "
                        f"{n} tiers to fill. A sparse tier is what forced v1's S5 to "
                        f"synthesise values nothing recorded."
                    )
                cell = _cell_from(a)
                # PGN-A11: one approved answer, expanded. `tier_index` is the
                # ordinal itself and is the one leaf the fold computes rather than
                # copies - the human approved the ORDER, and position i in that
                # order is arithmetic, not a second judgement.
                if leaf == "tier_index":
                    cell = Cell(answer_id=a.answer_id, value=t_i)
                elif leaf == "name" and cell.state == "value":
                    cell = Cell(answer_id=a.answer_id, value=_expand(cell.value, t_i, n, target))
                tier[leaf] = cell.as_json()
                record(a, base + _pointer("tiers", t_i, leaf))
            kind_obj["tiers"].append(tier)

        body["kinds"].append(kind_obj)

    unconsumed = [a for a in answers if a.answer_id not in consumption]
    if unconsumed:
        raise FoldRefusal(
            f"{len(unconsumed)} approved answer(s) reached no position in the structure: "
            f"{[(a.answer_id, a.question_path, a.target_ref) for a in unconsumed]}. "
            f"`PGN-A9` both directions - an approved assertion that the fold silently "
            f"ignores is a human decision thrown away with a signature on it. A count "
            f"identity cannot see this: rows-in equals rows-out while a leaf vanishes."
        )

    assert_no_magnitude_leaked(body)

    return CreativeStructure(
        element_kind=element_kind,
        body=body,
        consumption={k: sorted(v) for k, v in consumption.items()},
        answer_refs=sorted(refs.items()),
        content_hash=content_hash(element_kind, schema_fingerprint, body),
    )


def _tier_count(kind_obj: dict[str, Any], target: str) -> int:
    cell = kind_obj["tier_count"]
    if cell["state"] != "value":
        raise FoldRefusal(
            f"{target}: tier_count is {cell['state']!r}. A ladder whose height is unknown "
            f"cannot be made dense, and emitting zero tiers would look like a deliberate "
            f"flat progression."
        )
    n = cell["value"]
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise FoldRefusal(f"{target}: tier_count {n!r} is not a positive integer")
    if n > 64:
        raise FoldRefusal(
            f"{target}: tier_count {n} exceeds MAX_TIERS_PER_KIND (64). Refused here "
            f"rather than at S5 so the number is rejected next to the answer that "
            f"produced it."
        )
    return n


_CN_DIGITS = "〇一二三四五六七八九"


def _cn_numeral(n: int) -> str:
    """1–99 in Chinese numerals: 一, 十, 十一, 二十, 二十一, 六十四.

    Bounded by ``MAX_TIERS_PER_KIND`` (64), so no 百/千 arm is needed and adding
    one speculatively would be untested code on a path nothing reaches.
    """
    if not 1 <= n <= 99:
        raise FoldRefusal(f"{n} is outside the 1–99 range Chinese tier numerals cover")
    if n < 10:
        return _CN_DIGITS[n]
    tens, ones = divmod(n, 10)
    head = "十" if tens == 1 else _CN_DIGITS[tens] + "十"
    return head + (_CN_DIGITS[ones] if ones else "")


#: Numeral systems a tier-name pattern may request. **This exists because the
#: first version could not express the fixture's own convention.**
#:
#: Doc 39 §1 states the sub-levels are named *一層…九層 by convention* — one
#: pattern, one decision (`PGN-A11`). The first implementation expanded ``{n}``
#: with ``str(index + 1)``, which produces ``1層, 2層, 3層``: ASCII digits for a
#: Chinese corpus. An author wanting the real names would have had to fall back to
#: an explicit 9-item list, which is nine decisions and defeats `PGN-A11` exactly
#: where the fixture needs it. That is ML-4 — English/ASCII-first rule logic on a
#: path every language traverses — in the one module whose corpus is Chinese.
NUMERALS = {
    "arabic": lambda n: str(n),
    "cn": _cn_numeral,
}


def _expand(pattern: Any, index: int, total: int, target: str) -> Any:
    """Expand one approved naming answer into the name for tier ``index``.

    Two shapes, and no third: an explicit list of exactly ``total`` names, or a
    pattern containing ``{n}`` (Arabic) or ``{n:<system>}`` from :data:`NUMERALS`.
    A pattern with no placeholder would name every tier the same, which reads as a
    ladder and is not one.
    """
    if isinstance(pattern, list):
        if len(pattern) != total:
            raise FoldRefusal(
                f"{target}: {len(pattern)} tier names for {total} tiers. The count came "
                f"from a different answer than the names; refused rather than truncated "
                f"or padded, because both hide which of the two the human got wrong."
            )
        return pattern[index]
    if isinstance(pattern, str):
        for system, render in NUMERALS.items():
            token = "{n}" if system == "arabic" else "{n:" + system + "}"
            if token in pattern:
                return pattern.replace(token, render(index + 1))
        # An unrecognised `{n:...}` is refused BY NAME rather than passed through
        # as a literal — a tier called `九{n:jp}` shipping to a player is the
        # silent-degradation ML-4 forbids.
        if "{n:" in pattern:
            raise FoldRefusal(
                f"{target}: tier-name pattern {pattern!r} asks for a numeral system this "
                f"module does not have. Known: {sorted(NUMERALS)}. Refused rather than "
                f"left as a literal, which would ship the placeholder to a player."
            )
        raise FoldRefusal(
            f"{target}: tier-name pattern {pattern!r} has no {{n}} placeholder, so "
            f"every tier would get the same name. `PGN-A11` approves a PATTERN; a "
            f"constant is not one."
        )
    raise FoldRefusal(
        f"{target}: tier-name answer {pattern!r} is neither a list of names nor a pattern"
    )


# ── T2: no magnitude reaches the structure ──────────────────────────────────


def assert_no_magnitude_leaked(body: Mapping[str, Any]) -> None:
    """Refuse any number outside the ordinal class, **naming its pointer**.

    T2 is *"I can tell where a number came from"*, and its mechanism is that
    ``body_json`` contains no magnitude at all: every number the engine consumes
    is derived at S5 from ``(structure_hash, policy_hash)``. A ``tier_max: 500``
    that reached here would be a balance decision authored by whoever wrote the
    answer, reviewed as prose, and indistinguishable afterwards from one the
    policy produced.
    """
    bad: list[str] = []

    def walk(node: Any, pointer: str, leaf: str | None, direct: bool) -> None:
        """``direct`` is True only for a number sitting AT a cell's own ``value``
        slot. Everything deeper is inside an author-supplied structure.

        This distinction closes a bypass an adversarial probe found: the first
        version carried ``leaf`` down through nested values, so a cap-rule
        answered as ``{"soft_cap": null, "tier_count": 500}`` re-bound ``leaf`` to
        ``"tier_count"`` and **500 sailed through** — a magnitude smuggled in by
        naming its key after an ordinal. An allow-list keyed on a name the input
        controls is not an allow-list.
        """
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "value":
                    walk(v, pointer + _pointer(k), leaf, True)
                else:
                    walk(v, pointer + _pointer(k), k, False)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, pointer + _pointer(i), leaf, False)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            if not (direct and leaf in ORDINAL_LEAVES):
                bad.append(f"{pointer} = {node!r}")

    walk(dict(body), "", None, False)
    if bad:
        raise FoldRefusal(
            f"MAGNITUDE in the creative structure at {bad}. `PGN-A5`: a model may emit "
            f"cardinality, order and names the book contains - never magnitude. A number "
            f"here is a balance decision reviewed as prose, and after S5 it is "
            f"indistinguishable from one the policy produced. Ordinal leaves are "
            f"{sorted(ORDINAL_LEAVES)}; anything else numeric belongs to S4."
        )


def content_hash(element_kind: str, schema_fingerprint: str, body: Mapping[str, Any]) -> str:
    """Content address for the structure. Canonical JSON, same discipline as
    ``answer_hash``: sorted keys, no whitespace, real UTF-8 for CJK.

    **``schema_fingerprint`` is part of the address, and that is a fix, not a
    decoration.** A structure is only meaningful relative to the schema it was
    folded against. With the fingerprint outside the hash, re-folding the same
    answers after the schema MOVED produced the same ``content_hash``, the
    ``ON CONFLICT (job_id, element_kind, content_hash)`` returned the OLD row, and
    the new fingerprint was **silently discarded** — the stored row then claimed a
    schema the caller never asserted, which is exactly the drift the column exists
    to make loud. Found by probe, not by reading.
    """
    h = hashlib.blake2b(digest_size=32)
    h.update(_DOMAIN)
    h.update(element_kind.encode("utf-8"))
    h.update(b"\x00")
    h.update(schema_fingerprint.encode("utf-8"))
    h.update(b"\x00")
    h.update(
        json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    return h.hexdigest()
