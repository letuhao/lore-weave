#!/usr/bin/env python3
"""architecture-live-proof — the GOAL's own sentence, as one command.

The plan's goal is *"the architecture is implemented correctly **and a live run proves it**."*
Every leg of that proof exists and each was run in its own cycle — but **there was no single
command that runs them together and returns one verdict**, so "a live run proves it" was a
claim assembled by a reader across a 25 000-line journal. That is the same defect
`plan-final-verification` had (T48k): a sentence wider than its check.

WHAT IT PROVES, AND WHY EACH LEG IS HERE
────────────────────────────────────────
    1 BACKEND     the declared graph engine is `age` for every declared deployment
                  -> port-adoption-gate's `backend declarations` ratchet (§9.2)
    2 STORE       the declared store actually HOLDS the corpus, not just points at one
                  -> graph-store-migrated-gate (T54g: nothing compared the two STORES)
    3 SURFACE     every KAL read route answers, derived from the controller not hand-listed
                  -> kal-read-surface-live-smoke (T54i/T55b)
    4 PORT        class (d) is discharged by one of §10.1's two paths
                  -> port-adoption-gate's `class (d) UNDISCHARGED` ratchet (A33)

⚠️ **A COMPOSER IS THE EASIEST PLACE TO LIE, so it does two things it would be simpler to skip.**

**It reports what it RAN, never "everything".** T48k's whole finding was a verifier claiming
*"every gate is green"* while running 6 of 113. This one names each leg and its exit code, and
its PASS line says how many legs it ran.

**It has a FLOOR (`--min-legs`), because a run where every leg was skipped returns no failures.**
"No leg failed" over zero legs is the vacuous pass this repo keeps paying for — a grant-404 and
an empty-200 both read as success. A leg that could not run is `SKIP`, and SKIP is not PASS.

Usage
    python scripts/architecture-live-proof.py --selftest
    python scripts/architecture-live-proof.py --run --book-id <uuid> --user-id <uuid> \\
        --internal-token <tok> --entity-id <id>
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
PROVEN, NOT_PROVEN, TOO_FEW_LEGS = "PROVEN", "NOT-PROVEN", "TOO-FEW-LEGS"


def verdict(legs: list[dict], min_legs: int) -> dict:
    """Pure. `legs` are `{name, status}`. Order matters — the floor is checked BEFORE the
    failure count, because "0 failures" over 0 legs is the shape that reads as success.
    """
    ran = [l for l in legs if l["status"] in (PASS, FAIL)]
    failed = [l["name"] for l in legs if l["status"] == FAIL]
    skipped = [l["name"] for l in legs if l["status"] == SKIP]
    if len(ran) < min_legs:
        return {"verdict": TOO_FEW_LEGS, "ran": len(ran), "floor": min_legs,
                "skipped": skipped,
                "reason": "a run where the legs could not execute proves the harness works and "
                          "nothing else. 'No leg failed' over too few legs is not a proof."}
    return {"verdict": NOT_PROVEN if failed else PROVEN,
            "ran": len(ran), "failed": failed, "skipped": skipped,
            "reason": (f"{len(failed)} leg(s) failed" if failed else
                       f"every one of the {len(ran)} leg(s) that RAN passed — and this line "
                       f"says how many, because a proof that claims 'everything' while running "
                       f"a subset is the defect it exists to catch")}


def _run(cmd: list[str], timeout: int = 900) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           timeout=timeout, cwd=ROOT)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def _selftest() -> int:
    L = lambda n, s: {"name": n, "status": s}  # noqa: E731
    cases = [
        ("every leg passing is PROVEN",
         verdict([L("a", PASS), L("b", PASS)], 2), lambda v: v["verdict"] == PROVEN),
        ("one failing leg is NOT-PROVEN",
         verdict([L("a", PASS), L("b", FAIL)], 2), lambda v: v["verdict"] == NOT_PROVEN),
        ("THE FLOOR: all legs skipped is TOO-FEW-LEGS, never a pass",
         verdict([L("a", SKIP), L("b", SKIP)], 2), lambda v: v["verdict"] == TOO_FEW_LEGS),
        ("...and the floor is checked BEFORE the failure count, so 0-of-0 cannot read clean",
         verdict([], 1), lambda v: v["verdict"] == TOO_FEW_LEGS and "failed" not in v),
        ("a SKIP is not a PASS even when the rest are green",
         verdict([L("a", PASS), L("b", SKIP)], 2), lambda v: v["verdict"] == TOO_FEW_LEGS),
        ("...but the same run clears a floor it actually meets",
         verdict([L("a", PASS), L("b", SKIP)], 1), lambda v: v["verdict"] == PROVEN),
        ("the PASS line names HOW MANY legs ran, never 'everything' (T48k)",
         verdict([L("a", PASS)], 1), lambda v: "1 leg(s) that RAN" in v["reason"]),
        ("skipped legs are always reported, so a shrinking proof is visible",
         verdict([L("a", PASS), L("b", SKIP)], 1), lambda v: v["skipped"] == ["b"]),
    ]
    failures = 0
    print("architecture-live-proof - selftest (offline)")
    for label, got, pred in cases:
        ok = bool(pred(got))
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              f"{'' if ok else '  -> ' + json.dumps(got, ensure_ascii=False)}")
    print("\n  all checks passed" if not failures else f"\n  {failures} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--base-url", default="http://localhost:23210")
    ap.add_argument("--book-id")
    #: The KG project, which is NOT the book id. Required by the SURFACE leg since T48x put the
    #: `projects/:projectId` controller in the sweep's scope — see the leg's comment.
    ap.add_argument("--project-id", default="")
    #: Downstreams this FIXTURE is known to lack data for. On iso, glossary-service
    #: holds 7380 entities across 512 books and ZERO rows for the acceptance book, so
    #: its 10 KAL routes answer nothing while all 4 graph routes carry data. Declaring
    #: it keeps the leg honest instead of letting a global --min-data floor be
    #: satisfied by one half of the surface. A ratchet: if glossary starts answering,
    #: the sweep reports the stale declaration.
    ap.add_argument("--cold-downstream", default="")
    ap.add_argument("--user-id")
    ap.add_argument("--internal-token")
    # REQUIRED for leg 3: without it the entity-dependent routes cannot carry
    # rows, and the leg passed on 1 route of 14 while claiming the surface answers.
    ap.add_argument("--entity-id", default="")
    ap.add_argument("--declared-census")
    ap.add_argument("--other-census")
    ap.add_argument("--min-legs", type=int, default=3)   # 5 legs exist; the floor
                                                        # is what must RUN
    ap.add_argument("--min-data", type=int, default=1)
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.run:
        ap.print_help()
        return 2

    py = sys.executable
    legs: list[dict] = []

    def leg(name: str, cmd: list[str] | None, needle: str | None = None) -> None:
        if cmd is None:
            legs.append({"name": name, "status": SKIP, "why": "inputs not supplied"})
            print(f"  {SKIP:<5} {name}  (inputs not supplied)")
            return
        rc, out = _run(cmd)
        ok = rc == 0 and (needle is None or needle in out)
        legs.append({"name": name, "status": PASS if ok else FAIL, "rc": rc})
        tail = [l for l in out.strip().split("\n") if l.strip()][-1:] or [""]
        print(f"  {'PASS' if ok else 'FAIL':<5} {name}  rc={rc}  {tail[0][:110]}")

    print("[arch-proof] the GOAL's four legs, run together\n")
    leg("1 BACKEND  every declared deployment is on `age`",
        [py, "scripts/port-adoption-gate.py"], "backend declarations 0/")
    # ⚠️ This leg ran `--selftest` in its first draft — an OFFLINE check under a name that
    # claims the store HOLDS the corpus. That is exactly T48k's defect, in the composer
    # written to avoid it. It now needs two real censuses or it SKIPs; it never passes on
    # a selftest.
    leg("2 STORE    the declared store holds the corpus",
        ([py, "scripts/graph-store-migrated-gate.py", "--declared", "age",
          "--declared-census", args.declared_census, "--other-census", args.other_census,
          # T48ab — this leg's NAME is the claim, so it must demand it. The gate is repo-wide
          # and rightly does not fail on "I could not look": BOTH_EMPTY exits 0. With no needle
          # on this leg, two empty censuses produced `PASS 2 STORE the declared store holds the
          # corpus` and the proof read PROVEN. An empty census is also exactly what a failed
          # producer emits.
          "--require-corpus"]
         if (args.declared_census and args.other_census) else None))
    # T48y — `--project-id` is REQUIRED here, not optional. The sweep covers both user-facing
    # controllers since T48x, and one of them is prefixed `v1/kal/projects/:projectId`. Called
    # without it, the sweep used to address that route with the BOOK id; the downstream answered
    # `project not found`, the sweep read NOT-FOUND, and this leg PASSED. A leg that SKIPS is
    # visible (`--min-legs` counts it); a leg that passes on a route it never addressed is not.
    leg("3 SURFACE  every KAL read route answers",
        ([py, "scripts/kal-read-surface-live-smoke.py", "--base-url", args.base_url,
          "--book-id", args.book_id, "--user-id", args.user_id, "--project-id", args.project_id,
          "--internal-token", args.internal_token, "--entity-id", args.entity_id,
          "--min-data", str(args.min_data), "--cold-downstream", args.cold_downstream]
         if (args.book_id and args.user_id and args.internal_token and args.entity_id
             and args.project_id)
         else None))
    # T48t — the leg whose ABSENCE hid T48s. The four above cover the backend, the store,
    # the surface and the port; none of them the bi-temporal spine, which is what this
    # architecture is for. A spoiler window can be advertised, computed and discarded, and
    # every one of the other legs stays green.
    leg("5 TEMPORAL a windowed read HOLDS its story position",
        ([py, "scripts/bitemporal-window-live-smoke.py", "--base-url", args.base_url,
          "--book-id", args.book_id, "--user-id", args.user_id,
          "--internal-token", args.internal_token, "--entity-id", args.entity_id]
         if (args.book_id and args.user_id and args.internal_token and args.entity_id)
         else None))
    leg("4 PORT     class (d) discharged by one of §10.1's two paths",
        [py, "scripts/port-adoption-gate.py"], "class (d) UNDISCHARGED 0/")

    v = verdict(legs, args.min_legs)
    print("\n[arch-proof] " + json.dumps(v, ensure_ascii=False, indent=1))
    return 0 if v["verdict"] == PROVEN else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
