#!/usr/bin/env python3
"""T46 — the two `maintain_chain` implementations, and which one is WEAKER in which respect.

WHY THIS EXISTS
---------------
T46 says *"port the mature bitemporal machinery Go → Python and merge the stores… **Move it
working — do not rewrite from the weaker side.**"* That warning has no teeth while nobody has
written down **which side is weaker**, and measured 2026-08-14 the row's framing is also a
category error: the "Go" implementation is not Go at all.

    Postgres   CREATE OR REPLACE FUNCTION maintain_chain(p_entity, p_attr)   -- a stored proc
               `internal/migrate/fact_close_pin.go` (SQL in a Go migration string)
               called from Go as `SELECT maintain_chain($1, $2)`
    Neo4j      MAINTAIN_FACT_CHAIN_CYPHER / MAINTAIN_RELATION_CHAIN_CYPHER
               `app/db/graph_repos/temporal.py` (Cypher in a Python constant)

There is nothing to "port to Python": both are query-language, and each lives with the store it
maintains. The real task is choosing the merged store's substrate and moving BOTH onto it — at
which point the surviving implementation must be the union of the two, not whichever file was
easier to keep.

THE ASYMMETRY THAT MATTERS, MEASURED
------------------------------------
Both close a half-open story interval at the **strictly-greater** next `valid_from` — the Cypher
even says it *"mirrors the Postgres maintain_chain core"*, and the tie rule (equal ordinals must
not close each other into a zero-width interval) is stated on both sides.

They differ in one respect, and it is the one T46's row names:

    Postgres   AND ef.valid_to_pinned = false   -- never recompute an explicitly-closed fact
    Cypher     (no pin concept exists in the KG at all)

**The KG is the weaker side here.** An author's explicit close survives re-derivation in
glossary and would be overwritten in the graph. It is not a live defect — nothing pins in the
KG, so there is no pin to lose today — but a merge that adopts the Cypher semantics silently
drops a capability the Postgres side has, which is exactly the failure the row warns about and
exactly the kind that is invisible afterwards.

WHAT THIS GATE DOES
-------------------
It is the `_EXPECTED_DIVERGENCES` shape that worked for T35d's Kuzu finding: **record the known
asymmetry, and fail when it changes.** Not to freeze it — to make its disappearance a decision
rather than a diff nobody read.

    python scripts/bitemporal-parity-gate.py
    python scripts/bitemporal-parity-gate.py --selftest
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG_SRC = os.path.join(ROOT, "services", "glossary-service", "internal", "migrate",
                      "fact_close_pin.go")
KG_SRC = os.path.join(ROOT, "services", "knowledge-service", "app", "db", "graph_repos",
                      "temporal.py")

#: Each capability, and where it is expected to be present. `True` = the implementation has it.
#: A row flipping is the event this gate exists to surface — it means the two sides moved
#: toward or away from each other, and T46's merge inherits whatever is true on that day.
#:
#: `probe` is matched against the source of each implementation. Source-level because the two
#: run on different substrates: a behavioural comparison would need both databases live, and a
#: gate that only runs with two servers up is a gate that does not run.
PARITY: list[tuple[str, str, str, bool, bool, str]] = [
    # name, postgres probe, cypher probe, pg_expected, kg_expected, why it matters
    (
        "pin-aware supersession",
        r"valid_to_pinned\s*=\s*false",
        # NOT `valid_to_pinned|\bpinned\b`. That alternation matched any COMMENT saying
        # "pinned", so once `kg_expected` flipped to True the row became a criterion that
        # cannot fail: bite 69 renamed every `valid_to_pinned` in the KG and the gate stayed
        # green off the prose alone. The probe now matches the GUARD the maintainers actually
        # execute, so deleting it reds the gate.
        r"coalesce\(cur\.valid_to_pinned,\s*false\)",
        True, True,
        "an author's EXPLICIT close must survive re-derivation on BOTH sides. Was the plan's "
        "one recorded asymmetry — 'the KG has no pin concept at all' — closed 2026-08-21 "
        "(T46f) by moving the Postgres semantics across rather than rewriting from the weaker "
        "side, as T46's row requires: all FOUR Cypher chain maintainers now skip a pinned "
        "valid_to, mirroring `AND ef.valid_to_pinned = false` clause for clause. Proven live "
        "on a real chain with an unpinned control that MUST move in the same run.",
    ),
    (
        "strictly-greater next bound",
        r"valid_from_ordinal\s*>\s*ef\.valid_from_ordinal",
        # T84 moved the KG probe. The comparison list used to hold NODES —
        # `[x IN chain WHERE x.valid_from_ordinal > cur.valid_from_ordinal | …]` — and AGE
        # cannot read a property off a vertex bound inside a list comprehension
        # (`could not find properties for x`), so the maintainers now collect the ordinals
        # alongside the nodes and compare plain integers. **The capability did not change and
        # neither side lost anything**: the bound is still STRICTLY greater, on both engines.
        # What changed is the text this probe reads, and the gate correctly refused the commit
        # until it was pointed at the new text rather than at a shape nobody executes.
        #
        # Still non-vacuous by construction: `o >= cur.valid_from_ordinal` does not match,
        # because the regex requires `cur.` immediately after the `>`.
        r"\bo\s*>\s*cur\.valid_from_ordinal",
        True, True,
        "equal ordinals must NOT close each other into a zero-width [base, base) interval, "
        "invisible at every as-of read. Both sides state it; if either stops, the merge would "
        "inherit the A2 bug.",
    ),
    (
        "skips invalidated rows",
        r"invalidated_at IS NULL",
        r"valid_until IS NULL",
        True, True,
        "a retracted fact must not participate in the chain, or a survivor's bound is derived "
        "from a row nobody can read.",
    ),
]


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def check(pg_src: str, kg_src: str) -> list[str]:
    """Rows whose measured presence disagrees with the recorded expectation."""
    drift = []
    for name, pg_probe, kg_probe, pg_want, kg_want, _why in PARITY:
        pg_has = re.search(pg_probe, pg_src) is not None
        kg_has = re.search(kg_probe, kg_src) is not None
        if pg_has != pg_want:
            drift.append(f"postgres {name}: recorded {pg_want}, measured {pg_has}")
        if kg_has != kg_want:
            drift.append(f"neo4j    {name}: recorded {kg_want}, measured {kg_has}")
    return drift


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    drift = check(_read(PG_SRC), _read(KG_SRC))
    if drift:
        print("[bitemporal-parity-gate] FAIL — the two `maintain_chain` implementations moved:")
        for d in drift:
            print(f"    {d}")
        print("  This is not a lint. T46 merges these two stores and the surviving")
        print("  implementation must be the UNION of their capabilities, not whichever file")
        print("  was easier to keep. Update PARITY in the same commit, and say in the plan")
        print("  which side gained or lost — a capability that disappears in a merge is")
        print("  invisible afterwards.")
        return 1
    gaps = [(n, w) for n, _, _, p, k, w in PARITY if p != k]
    print(f"[bitemporal-parity-gate] OK — {len(PARITY)} capability rows match the record; "
          f"{len(gaps)} known asymmetry(ies):")
    for name, why in gaps:
        print(f"    ⚠️  {name}: postgres HAS it, neo4j does NOT — {why[:88]}…")
    return 0


def selftest() -> int:
    fails = []

    def c(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    print("bitemporal-parity-gate · selftest")
    pg, kg = _read(PG_SRC), _read(KG_SRC)
    c("the real sources match the record today", check(pg, kg) == [], str(check(pg, kg)))

    # 🔴 The one that makes this non-vacuous: if the KG GAINS pins, the gate must notice.
    # A gate that only fires on a capability being LOST would let the two sides converge
    # silently, and convergence is the event T46 is waiting for.
    c("the KG gaining pins is reported",
      any("neo4j" in d for d in check(pg, kg + "\n valid_to_pinned = false\n")))
    # …and if Postgres LOSES its pin guard, that is the capability regression itself.
    c("postgres losing its pin guard is reported",
      any("postgres" in d for d in check(pg.replace("valid_to_pinned = false", "true"), kg)))
    # A probe that matches nothing anywhere would make a row permanently "absent" and the
    # gate would report a fake asymmetry forever.
    c("every recorded-present probe actually matches its source",
      not [n for n, pp, kp, pw, kw, _ in PARITY
           if (pw and not re.search(pp, pg)) or (kw and not re.search(kp, kg))])

    print("\n  all checks passed" if not fails else f"\n  {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
