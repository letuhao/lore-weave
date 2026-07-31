"""Per-OPERATION criteria — the checks that need no answer key (``BLD-A1``).

The finding this module exists for: you cannot write a semantic check for a
question whose answer you do not know, but you *can* check the **operation's
signature**. P17 returned 11 categories for 11 objects and passed a fidelity gate
at 1.0 — a 1:1 map is by definition not an abstraction, and that is checkable
without knowing which tags are right.

Two disciplines carried in from the measured rounds:

* ``MEM-A7`` — criteria are **HARD** or **SCORED**. A weighted score over a small
  categorical rubric is a rubber stamp: seven criteria, one failure, 6/7 = 0.857,
  which cleared a copied 0.85 threshold. A HARD failure fails outright.
* ``BLD-A4`` — a criterion must rest on something the model does not control.
  Requiring a self-justification field *licensed* arbitrary granularity instead of
  exposing thin categories; ``m < n`` held in every round.

And the scan bug, so it cannot come back: a criterion that looks for a banned word
looks in the **name**, never in the serialised member. Round 8's checker matched
"long" inside an evidence quote and reported a false failure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.pool.registry import Operation, Slot

__all__ = ["Finding", "Verdict", "evaluate"]

#: A code is a contract identifier, so it may not open with a digit or an underscore.
#: `24_pearls` passed the older `[a-z0-9_]+` and then reached the register, where a
#: leading digit is an ASP syntax error. The register no longer depends on this
#: (it quotes model text), and this no longer depends on the register — two layers
#: that hold independently, which is the point of having two.
_CODE = re.compile(r"[a-z][a-z0-9_]*")

#: Words that describe how a thing LOOKS rather than what a rule conditions on.
#: Checked against the member's `code` and display names ONLY — never against its
#: evidence (round 8's false positive).
_SHAPE_WORDS = frozenset({
    "long", "elongated", "short", "large", "small", "round", "circular", "square",
    "shaped", "coloured", "colored", "textile", "object", "thing", "item", "misc",
    "other", "general", "various", "assorted",
})

#: Values that LOOK like an owner and name nothing. `BLD-A3` says a refusal routes
#: work to whoever should own it; a refusal routed to "null" has been dropped, not
#: routed, and it looks routed in every report.
_NO_OWNER = frozenset({"", "null", "none", "nil", "n/a", "na", "unknown", "unclear",
                       "tbd", "-", "?"})

#: Rarity vocabulary from a different tradition (`MEM-A6`).
_GENERIC_TIER = frozenset({
    "common", "uncommon", "rare", "epic", "legendary", "mythic", "mythical",
    "supreme", "ultimate", "exotic",
})


@dataclass(frozen=True)
class Finding:
    criterion: str
    hard: bool
    detail: str


@dataclass
class Verdict:
    findings: list[Finding]
    checked: int

    @property
    def score(self) -> float:
        return round((self.checked - len(self.findings)) / self.checked, 3) if self.checked else 0.0

    @property
    def hard_broken(self) -> bool:
        return any(f.hard for f in self.findings)

    @property
    def passed(self) -> bool:
        return not self.hard_broken and self.score >= 0.85

    def __str__(self) -> str:
        if self.passed:
            return f"PASS (score {self.score}, {self.checked} criteria)"
        why = "hard criterion" if self.hard_broken else "score"
        return f"FAIL ({why}, score {self.score}): " + "; ".join(
            f.criterion for f in self.findings)


def _names(member: dict) -> str:
    """Code + display names only. Deliberately NOT the whole member."""
    return (member.get("code", "") + " " +
            " ".join(str(v) for v in (member.get("name") or {}).values())).lower()


def evaluate(slot: Slot, members: list[dict], refused: list[dict],
             *, evidence_n: int | None = None,
             registry_enums: dict[str, tuple[str, ...]] | None = None,
             pool: dict[str, list[dict]] | None = None) -> Verdict:
    """Run the shared hygiene criteria plus this slot's OPERATION criteria.

    ``pool`` is what has already SETTLED. Passing it turns on the reference check,
    which is the only criterion here that needs to know anything outside this slot.
    It is optional because a unit test of one operation has no pool; the loop always
    passes it, and a test asserts that it does — otherwise the check would be
    default-uncovered and the register would be the only thing catching a broken
    reference, one step too late to heal.
    """
    f: list[Finding] = []
    n_checks = 0

    def check(name: str, ok: bool, hard: bool, detail: str) -> None:
        nonlocal n_checks
        n_checks += 1
        if not ok:
            f.append(Finding(name, hard, detail))

    codes = [m.get("code", "") for m in members]

    # ── shared hygiene ────────────────────────────────────────────────────
    check("codes_ascii", all(_CODE.fullmatch(c or "") for c in codes), True,
          f"a code must be an ascii identifier — lowercase, starting with a letter: "
          f"{[c for c in codes if not _CODE.fullmatch(c or '')]}")
    check("codes_unique", len(set(codes)) == len(codes), True,
          f"duplicate codes: {sorted({c for c in codes if codes.count(c) > 1})}")
    check("arity", slot.arity[0] <= len(members) <= slot.arity[1], True,
          f"{len(members)} members, hard arity is {slot.arity}")
    check("suggest_range", slot.suggest[0] <= len(members) <= slot.suggest[1], False,
          f"{len(members)} members, suggest range is {slot.suggest}")
    check("no_generic_tier",
          not [c for c, m in zip(codes, members)
               if any(w in _names(m).split() for w in _GENERIC_TIER)], True,
          "rarity vocabulary from another tradition (MEM-A6)")
    check("provenance_present",
          all(m.get("provenance") for m in members), True, "every member names a provenance")
    check("evidence_resolves",
          not [m for m in members
               if m.get("provenance") in ("CANON", "CITED", "DERIVED") and not m.get("evidence")],
          True, "a CANON/CITED/DERIVED member with no evidence (MEM-A5)")

    # ── the member SHAPE the slot declares ────────────────────────────────
    # Not operation-specific: these follow from `slot.member`, which every operation
    # may declare. They lived inside the CLASSIFY_LINK branch for one cycle, which
    # meant a PARTITION slot with a required reference field had it checked by
    # nothing — the operation decides the SEMANTIC criteria, not whether a declared
    # field is present.
    enums = registry_enums or {}
    missing, bad_enum, unresolved = [], [], []
    for m in members:
        body = m.get("body") or {}
        for fld in slot.member:
            val = body.get(fld.name)
            if val in (None, [], ""):
                if fld.required:
                    missing.append(f"{m.get('code')}.{fld.name}")
                continue
            if fld.engine_enum and val not in enums.get(fld.engine_enum, ()):
                bad_enum.append(f"{m.get('code')}.{fld.name}={val!r}")
            if fld.target_slot and pool is not None:
                have = {x.get("code") for x in pool.get(fld.target_slot, [])}
                unresolved += [f"{m.get('code')}.{fld.name}→{fld.target_slot}:{v}"
                               for v in (val if isinstance(val, list) else [val])
                               if v not in have]
    declared = {f.name for f in slot.member}
    extra = sorted({k for m in members for k in (m.get("body") or {})} - declared)
    check("required_fields", not missing, True, f"missing required body fields: {missing}")
    # A slot's member shape is the contract. An undeclared field is not harmless
    # decoration: nothing downstream reads it, and it goes into the frozen digest,
    # so two runs that agree on every meaningful value can still disagree on the
    # hash. A live run put `aspect` on a slot whose `member` is empty.
    check("no_undeclared_body_fields", not extra, True,
          f"body fields this slot does not declare: {extra}. Declared: "
          f"{sorted(declared) or 'none — this slot takes no body'}")
    check("engine_enum_legal", not bad_enum, True,
          f"value outside an engine-fixed enum: {bad_enum}")
    if pool is not None:
        check("references_resolve", not unresolved, True,
              f"a reference to a code no settled slot provides: {unresolved}")

    # ── the OPERATION's own criteria (BLD-A1) ─────────────────────────────
    if slot.operation is Operation.ABSTRACT:
        n = evidence_n or 0
        # `covers` belongs to the OPERATION, not to the slot body. This used to
        # accept it in `body` too, because the envelope declared it nowhere and a
        # correct answer should not fail on placement. The envelope now names it
        # (`kinds._COVERS`), so the tolerance is withdrawn — and it had to be:
        # `no_undeclared_body_fields` rejects a `body.covers` that this branch was
        # simultaneously accepting, and two rules disagreeing about one field is
        # how a check gets quietly defeated by an adjacent decision. One place,
        # named in the envelope, enforced once.
        covers = {m.get("code"): (m.get("covers") or []) for m in members}
        multi = [c for c, v in covers.items() if len(v) >= 2]
        check("is_an_abstraction", bool(n) and len(members) < n, True,
              f"{len(members)} categories for {n} objects — a 1:1 map is a renaming, not "
              f"an abstraction")
        check("every_category_covers", all(covers.values()), True,
              f"categories covering nothing: {[c for c, v in covers.items() if not v]}")
        check("some_category_generalises", bool(multi), True,
              "no category covers 2+ objects — a renaming, not an abstraction")
        check("axis_not_appearance",
              not [c for c, m in zip(codes, members)
                   if any(w in _names(m).split("_") or w in _names(m).split()
                          for w in _SHAPE_WORDS)], False,
              "grouped by appearance rather than by what a consumer conditions on (BLD-A2)")

    elif slot.operation is Operation.CLASSIFY_LINK:
        classes = {(m.get("body") or {}).get("class") for m in members}
        check("classes_vary", len(classes) > 1, False,
              f"every member got the same class ({classes}) — a classifier that never "
              f"discriminates is not classifying")

    elif slot.operation is Operation.PARTITION:
        # The v1 criterion here checked that ordinals were contiguous 1..N — and the
        # planner ASSIGNS them 1..N by construction, so it could not fail. It was a
        # claim wearing a check's costume (`NV-1`). What can genuinely fail is the
        # seam: the model emitting a number of its own, which `QTY-A5` forbids and
        # which the probe rounds actually did. So the criterion runs on the RAW model
        # output, before the planner has stamped anything.
        stamped = [m.get("code") for m in members
                   if any(k in m for k in ("ordinal", "rank", "level", "tier", "index"))]
        check("no_model_assigned_ordinal", not stamped, True,
              f"the model numbered its own bands: {stamped}. The ORDER is the answer; "
              f"the planner assigns the number once the set settles (QTY-A5)")

        gfield = next((f.name for f in slot.member if f.target_slot), None)
        groups: dict[str, int] = {}
        for m in members:
            g = str((m.get("body") or {}).get(gfield, "")) if gfield else ""
            groups[g] = groups.get(g, 0) + 1
        thin = [g for g, k in groups.items() if k < 2]
        check("every_group_is_a_partition", not thin, True,
              f"a single band is not a partition of anything: {thin}. An axis this "
              f"reality does not ladder belongs in refused, not in members")

    elif slot.operation is Operation.CONFIRM:
        # NOT `declared` — that name is taken above by the set of declared BODY FIELDS,
        # and these two are unrelated. Shadowing it worked only because the hygiene
        # check had already run.
        declared_default = set(slot.default)
        check("has_members", bool(members), True, "a Profile slot always ships a set")
        added = [c for c in codes if c not in declared_default]
        check("additions_carry_evidence",
              not [c for c, m in zip(codes, members)
                   if c not in declared_default and not m.get("evidence")],
              True,
              f"an addition outside the declared default with no evidence: {added}. The "
              f"declared entries already carry the platform's burden of proof; an "
              f"addition has to carry its own")

    # ── the refusal channel (BLD-A3) ──────────────────────────────────────
    # `r.get("owner")` alone was satisfied by the STRING "null", which a live run
    # duly produced. A truthiness test on model text is not a test that a name was
    # given — the model can always supply a truthy nothing.
    bad_owner = [r.get("what") for r in refused
                 if str(r.get("owner") or "").strip().lower() in _NO_OWNER]
    check("refusals_name_an_owner", not bad_owner, True,
          f"a refusal that names no module which should own it: {bad_owner}")
    check("no_refusal_as_member",
          not [c for c in codes if "refus" in c or "not_a" in c or "non_" in c], True,
          "a refusal disguised as a member — refusal has its own channel (BLD-A3)")

    return Verdict(findings=f, checked=n_checks)
