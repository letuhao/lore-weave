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

_CODE = re.compile(r"[a-z0-9_]+")

#: Words that describe how a thing LOOKS rather than what a rule conditions on.
#: Checked against the member's `code` and display names ONLY — never against its
#: evidence (round 8's false positive).
_SHAPE_WORDS = frozenset({
    "long", "elongated", "short", "large", "small", "round", "circular", "square",
    "shaped", "coloured", "colored", "textile", "object", "thing", "item", "misc",
    "other", "general", "various", "assorted",
})

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
             registry_enums: dict[str, tuple[str, ...]] | None = None) -> Verdict:
    """Run the shared hygiene criteria plus this slot's OPERATION criteria."""
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
          f"codes must be ascii snake_case: {[c for c in codes if not _CODE.fullmatch(c or '')]}")
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

    # ── the OPERATION's own criteria (BLD-A1) ─────────────────────────────
    if slot.operation is Operation.ABSTRACT:
        n = evidence_n or 0
        # `covers` belongs to the OPERATION, not to the slot body — a slot whose
        # `member: {}` is empty leaves the model nowhere legal to put it, and the
        # first run of the cycle put it in `body`. Accept either position rather
        # than fail a correct answer on placement.
        covers = {m.get("code"): (m.get("covers") or (m.get("body") or {}).get("covers") or [])
                  for m in members}
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
        enums = registry_enums or {}
        bad_class, bad_ref = [], []
        for m in members:
            body = m.get("body") or {}
            for fld in slot.member:
                val = body.get(fld.name)
                if fld.required and val in (None, [], ""):
                    bad_ref.append(f"{m.get('code')}.{fld.name} missing")
                if fld.engine_enum and val is not None:
                    if val not in enums.get(fld.engine_enum, ()):
                        bad_class.append(f"{m.get('code')}.{fld.name}={val!r}")
        check("engine_enum_legal", not bad_class, True,
              f"value outside an engine-fixed enum: {bad_class}")
        check("required_fields", not bad_ref, True, f"missing required body fields: {bad_ref}")
        classes = {(m.get("body") or {}).get("class") for m in members}
        check("classes_vary", len(classes) > 1, False,
              f"every member got the same class ({classes}) — a classifier that never "
              f"discriminates is not classifying")

    elif slot.operation is Operation.PARTITION:
        ords = [m.get("ordinal") for m in members]
        check("ordinals_contiguous",
              sorted(o for o in ords if isinstance(o, int)) == list(range(1, len(members) + 1)),
              True, f"ordinals must be 1..N assigned by the planner, got {ords}")

    elif slot.operation is Operation.CONFIRM:
        check("has_members", bool(members), True, "a Profile slot always ships a set")

    # ── the refusal channel (BLD-A3) ──────────────────────────────────────
    check("refusals_name_an_owner",
          all(r.get("owner") for r in refused), True,
          "a refusal that does not name the module which should own it")
    check("no_refusal_as_member",
          not [c for c in codes if "refus" in c or "not_a" in c or "non_" in c], True,
          "a refusal disguised as a member — refusal has its own channel (BLD-A3)")

    return Verdict(findings=f, checked=n_checks)
