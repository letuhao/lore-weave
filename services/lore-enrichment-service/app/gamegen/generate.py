"""S5 — admission. The last stage of POC-1, and the one v1 had no human in.

Doc 39 §7. This module turns ``(creative_structure, numeric_policy)`` into the
authored ruleset TOML the **engine's own binary** then validates
(`progression-validate`, `PGN-A7`). Three things make it more than a serializer:

**The structure supplies SHAPE; the policy supplies every NUMBER.** That split is
`PGN-A5` at the point where it finally bites. S3 refuses a magnitude reaching the
structure; here is where the magnitude has to come from *somewhere*, and the only
somewhere is a band a human authored or narrowed. If this module could invent one,
every guard upstream would have been theatre.

**`PGN-A9`'s second direction.** S3 proved every approved answer reached a
position. S5 proves every position was READ: :func:`generate` records a
``read_set`` of the JSON-Pointers it consumed, and a leaf in ``body_json`` outside
that set is a **refusal** naming the pointer. v1 had this as a count identity,
which cannot see its own worked example — rows in equals rows out while a leaf
vanishes.

**Defaults are NAMED, not silent.** Every field the engine will fill because
nobody asked is recorded in ``default_provenance`` with the reason from the
schema contract. §7.2's whole argument is that *"you are approving 24 tiers of
which 132 fields will be engine-defaulted"* is the number that turns an invisible
hole into something a human can veto. A count nobody can see is not that.

## What refuses, and why each is a refusal rather than a repair

* a ``not_stated`` cell on a **required** position — `PGN-A4` makes it a complete
  answer; complete is not the same as resolvable, and the honest response is to
  name the field rather than let the engine default fill a human's silence;
* a ``refused`` cell (`PGN-A20`) — the requirement is real and out of scope, so
  the refusal carries the owning module forward instead of quietly generating
  something place-less;
* a magnitude with no band — S4's coverage check should have caught it, and this
  is the second, independent place it cannot slip through;
* a ``Remove`` / ``Weaken`` / ``Substitute`` repair op (`PGN-A17`, below).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.gamegen.brief import load_contract
from app.gamegen.policy import Policy

__all__ = [
    "AdmissionRefusal",
    "GeneratedArtifact",
    "REPAIR_OPS",
    "STRUCTURE_BEARING",
    "assert_repairs_are_admissible",
    "generate",
]


class AdmissionRefusal(Exception):
    """S5 cannot generate an honest artifact. Every message names what and where."""


#: `PGN-A17`. ``Adjust`` moves a magnitude **within its policy band** and is
#: admissible. The other three are refusals, and the attack needs no adversary:
#: the validator refuses a tier whose requirement resolves to nothing, repair
#: round 2 sets it to ``None``, verdict **admitted**, ``repair_round: 2`` honestly
#: recorded, every trust property green — and the human-approved *"advancement
#: requires a sealed place"* is gone. Repair runs entirely below the signature.
REPAIR_OPS = {
    "adjust": True,
    "remove": False,
    "weaken": False,
    "substitute": False,
}

#: The cell states that carry a human's statement. A repair may not touch a
#: position holding one — that is what "structure-bearing" means.
STRUCTURE_BEARING = frozenset({"value", "refused"})


@dataclass
class GeneratedArtifact:
    toml: str
    #: JSON-Pointers into ``body_json`` this stage actually consumed.
    read_set: list[str] = field(default_factory=list)
    #: ``schema path -> reason``, for every field the engine will fill.
    default_provenance: dict[str, str] = field(default_factory=dict)
    #: ``policy path -> value`` — every number, and where it came from.
    magnitudes: dict[str, int] = field(default_factory=dict)


def assert_repairs_are_admissible(repair_ops: list[Mapping[str, Any]]) -> None:
    """`PGN-A17` — repair may **Adjust**; it may never **Remove, Weaken or
    Substitute**.

    v1 said only that repair increments ``repair_round``, constraining *how many*
    repairs and never *what a repair may change*. Doc 38 and `PGN-Q6` both
    constrain the failure path; nobody constrained the **success** path.
    """
    for i, op in enumerate(repair_ops):
        kind = str(op.get("op", "")).lower()
        if kind not in REPAIR_OPS:
            raise AdmissionRefusal(
                f"repair op {i} is {kind!r}, which is not one of {sorted(REPAIR_OPS)}. "
                f"An untyped repair is a repair nobody constrained - `repair_ops_json` is "
                f"typed precisely so the SUCCESS path has a rule."
            )
        if not REPAIR_OPS[kind]:
            raise AdmissionRefusal(
                f"repair op {i} is a {kind.upper()} of {op.get('path', '(unnamed)')!r}. "
                f"`PGN-A17`: repair may ADJUST a magnitude within its policy band and "
                f"nothing else. This returns to the S3 gate. The attack needs no "
                f"adversary - the validator refuses a tier whose requirement resolves to "
                f"nothing, repair sets it to None, verdict `admitted`, repair_round "
                f"honestly recorded, every trust property green, and the human-approved "
                f"statement is gone."
            )


def _cell(node: Mapping[str, Any], pointer: str, read_set: list[str]) -> Any:
    """Read one cell, recording the pointer, and refuse the two non-values."""
    read_set.append(pointer)
    state = node.get("state")
    if state == "value":
        return node["value"]
    if state == "not_stated":
        raise AdmissionRefusal(
            f"{pointer} is `not_stated` ({node.get('reason')}) and the engine requires it. "
            f"`PGN-A4` makes 'the book does not say' a COMPLETE answer - approvable in one "
            f"click - and this is where complete stops being resolvable. Named rather than "
            f"defaulted: an engine default filling a human's silence is the silent-drop "
            f"class with a signature on it."
        )
    if state == "refused":
        raise AdmissionRefusal(
            f"{pointer} was REFUSED at the fold: {node.get('requirement')!r}. "
            f"Owner: {node.get('owner')}. `PGN-A20` - an out-of-scope element is a refusal "
            f"that names its owner, never a narrowed schema. Generating around it would "
            f"delete the requirement, which is the QTY-Q5 class shipping in the POC that "
            f"exists to prove it cannot."
        )
    raise AdmissionRefusal(f"{pointer} has unknown cell state {state!r}")


def _tier_max(policy: Policy, index: int, total: int) -> int:
    """The per-tier ceiling, derived from the band as a RISING sequence.

    **Found by running the chain end to end, not by reading.** Every unit test
    passed and the engine refused:

    ``progression.schema.tiers_not_monotonic: kind at ordinal 0, tier 1 does not
    raise tier_max above the tier before it. A ladder whose rungs do not rise is a
    ladder an actor can never climb``

    The first version handed every tier the band's scalar ``default``, which is
    correct for a per-kind magnitude and wrong for a per-tier one: ``tier[].
    tier_max`` is *n* numbers, and a policy that supplies one cannot express a
    ladder. The band is the SPAN — *"this ladder runs from min to max"* — and the
    rungs are interpolated across it. That is `PGN-A11`'s shape one tier down: the
    human approves the span, the code expands it, and monotonicity holds **by
    construction** rather than by a check that would have to refuse a policy a
    human legitimately authored.

    Integer arithmetic throughout (`PGN-A16`) — the rounding is truncating and
    deterministic, so the same band and tier count give the same ladder on every
    platform. The ``+ index`` keeps the sequence strictly rising even when the
    span is narrower than the tier count, which is the degenerate case a human can
    reach by narrowing hard.
    """
    band = policy.bands.get("kind.tier[].tier_max")
    if band is None:
        raise AdmissionRefusal(
            "no policy band for magnitude 'kind.tier[].tier_max'. S4's coverage check "
            "should have caught this; refused again here because a magnitude with no "
            "band is a number this stage would otherwise have to invent - and an "
            "invented number is indistinguishable afterwards from one a human chose."
        )
    span = band.max - band.min
    return band.min + (span * (index + 1)) // total + index


def _band(policy: Policy, path: str) -> int:
    band = policy.bands.get(path)
    if band is None:
        raise AdmissionRefusal(
            f"no policy band for magnitude {path!r}. S4's coverage check should have "
            f"caught this; refused again here because a magnitude with no band is a "
            f"number this stage would otherwise have to invent - and an invented number "
            f"is indistinguishable afterwards from one a human chose."
        )
    return band.default


def _toml_str(s: str) -> str:
    # `ensure_ascii`-equivalent: CJK stays CJK. A basic TOML string escapes only
    # backslash and quote for our inputs; names come from an approved answer and
    # cannot carry a control character (the DB CHECK on says[] and the value
    # column both refuse one).
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def generate(
    *,
    body: Mapping[str, Any],
    policy: Policy,
    repair_ops: list[Mapping[str, Any]] | None = None,
) -> GeneratedArtifact:
    """Structure + policy → the authored TOML the engine's binary validates.

    :raises AdmissionRefusal: on an unresolvable cell, an unbanded magnitude, an
        inadmissible repair, or a leaf in ``body`` this stage never read.
    """
    assert_repairs_are_admissible(list(repair_ops or []))

    contract = load_contract()
    why = {p["path"]: p.get("why", "") for p in contract["paths"]}
    read_set: list[str] = []
    defaults: dict[str, str] = {}
    magnitudes: dict[str, int] = {}

    kinds = body.get("kinds") or []
    if not kinds:
        raise AdmissionRefusal("the structure declares no kinds")

    quantities = [k["id"] for k in kinds]
    lines = ["quantities = [" + ", ".join(_toml_str(q) for q in quantities) + "]", ""]

    for i, k in enumerate(kinds):
        base = f"/kinds/{i}"
        read_set.append(base + "/id")
        name = _cell(k["name"], base + "/name", read_set)
        ptype = _cell(k["progression_type"], base + "/progression_type", read_set)
        curve = _cell(k["curve"], base + "/curve", read_set)
        cap = _cell(k["cap_rule"], base + "/cap_rule", read_set)
        initial_tier = _cell(k["initial_tier"], base + "/initial_tier", read_set)
        tier_count = _cell(k["tier_count"], base + "/tier_count", read_set)

        lines += [
            "[[progression_kinds]]",
            f"name = {_toml_str(str(name))}",
            f"quantity = {_toml_str(k['id'])}",
            f"type = {_toml_str(str(ptype))}",
            f"curve = {_toml_str(str(curve))}",
            f"cap = {_toml_str(str(cap))}",
            f"initial_tier = {int(initial_tier)}",
        ]

        # `body_or_soul` is Defaultable and the brief does not ask it — so the
        # engine will fill it, and §7.2 says that fact must be COUNTABLE.
        defaults[f"{k['id']}.body_or_soul"] = why.get("kind.body_or_soul", "")

        if str(cap) in ("soft_cap", "hard_cap"):
            v = _band(policy, "kind.cap_rule.cap")
            magnitudes[f"{k['id']}.cap_value"] = v
            lines.append(f"cap_value = {v}")
        if str(curve) == "linear":
            v = _band(policy, "kind.curve.rate_milli")
            magnitudes[f"{k['id']}.rate_milli"] = v
            lines.append(f"rate = {v / 1000:.3f}")

        tiers = k.get("tiers") or []
        if len(tiers) != int(tier_count):
            raise AdmissionRefusal(
                f"{base}: the structure declares tier_count {tier_count} and carries "
                f"{len(tiers)} tier objects. S3 is supposed to make these equal by "
                f"construction; refused rather than trusting either."
            )
        for t_i, t in enumerate(tiers):
            tb = f"{base}/tiers/{t_i}"
            t_name = _cell(t["name"], tb + "/name", read_set)
            _cell(t["tier_index"], tb + "/tier_index", read_set)
            _cell(t["within_tier_curve"], tb + "/within_tier_curve", read_set)
            bt = _cell(t["breakthrough"], tb + "/breakthrough", read_set)
            v = _tier_max(policy, t_i, len(tiers))
            magnitudes[f"{k['id']}.tier[{t_i}].tier_max"] = v
            lines += [
                "[[progression_kinds.tiers]]",
                f"name = {_toml_str(str(t_name))}",
                f"tier_max = {v}",
            ]
            if str(bt) != "at_max":
                lines.append(f"breakthrough = {_toml_str(str(bt))}")
            defaults[f"{k['id']}.tier[{t_i}].initial_value_on_advance"] = why.get(
                "kind.tier[].initial_value_on_advance", ""
            )
        lines.append("")

    _assert_every_leaf_was_read(body, read_set)

    return GeneratedArtifact(
        toml="\n".join(lines),
        read_set=sorted(read_set),
        default_provenance=defaults,
        magnitudes=magnitudes,
    )


def _assert_every_leaf_was_read(body: Mapping[str, Any], read_set: list[str]) -> None:
    """`PGN-A9`, S3→S5. A leaf in ``body_json`` outside the read set is a refusal
    **with its pointer**.

    v1 offered T6's count identity as the mechanism for this, which cannot see
    `PGN-A9`'s own worked example: rows-in equals rows-out while a leaf vanishes.
    So the check is positional, not numeric.
    """
    seen = set(read_set)
    missed: list[str] = []

    def walk(node: Any, pointer: str) -> None:
        if isinstance(node, dict):
            # A CELL is the unit S5 reads; its internals are not separate leaves.
            if "state" in node and "answer_id" in node:
                if pointer not in seen:
                    missed.append(pointer)
                return
            for key, v in node.items():
                walk(v, f"{pointer}/{key}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{pointer}/{i}")
        elif pointer not in seen and pointer != "/element_kind":
            missed.append(pointer)

    walk(dict(body), "")
    if missed:
        raise AdmissionRefusal(
            f"the structure carries {len(missed)} position(s) this stage never read: "
            f"{sorted(missed)[:8]}. `PGN-A9` runs both directions - S3 proved every "
            f"approved answer reached a position, and this proves every position was "
            f"consumed. A leaf nobody read is a human decision that shaped nothing, and "
            f"a count identity cannot see it."
        )
