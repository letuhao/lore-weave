#!/usr/bin/env python3
"""QC-5 1a with ONLY R1 active — the seventh candidate the six-cause search never tested.

§12 declared 1a unsatisfiable after eliminating six candidates, every one of them about the
JUDGE: model tier, prompt wording, bi-temporal anchor, bible contents, rule windows, narrative
framing. **None asked whether the RULES are violable propositions.** Read from the acceptance
book's own `canon_rule` rows:

    R1  the antagonist is the cousin AND the betrayer, and NO ONE ELSE is  <- an EXCLUSION
    R2  X is a member of family A                                          a positive fact
    R3  Y is a member of family B; the families are betrothed              a positive fact
    R4  Z is X's adversary                                                 a positive fact
    R5  X controls the L-Field                                             a capability
    R6  spirit energy is this world's power system                         a DEFINITION

(Glossed; the originals are quoted under a pragma in the plan's C44 block and spec §12,
where their grammatical FORM is the evidence being argued about.)

**Only R1 states what is not allowed.** Nothing a work of fiction can say contradicts "spirit
energy is this world's power system", and the judge is asked "is this violated?" about it
anyway. C30 adjudicated four attributed verdicts as false and **two of them invent a clause and
hang it on a real rule id** — the fabricated *"and no one can drain his spirit energy"* was
attached to R5, the five-word capability. A model asked an unanswerable question manufactures
the premise that would make it answerable.

The plant targets R1 and R1 alone. If five unfalsifiable rules are generating the false-positive
floor the plant has to rise above, restricting to R1 separates the arms. If it does not, §12
stands as written and the critic genuinely cannot discriminate.

⚠️ **THE NON-VACUITY CHECK IS THE POINT.** The restriction is applied by deactivating rows, and
a run where it silently failed to apply would produce numbers that look like an answer. Every
critique response carries `active_rule_count`; if it is not 1, the verdict is `UNAPPLIED` and no
rate is reported. This repo has already paid for the general form — *"a test injecting a fake at
the chokepoint cannot prove the chokepoint is wired"*.

WRITES: iso only, and guarded. The rule rows are mutated on `lw-iso` (port 25555) and restored
in a `finally`. Port 5555 is dev and is refused by name.

Usage
    python scripts/qc5-arm1a-rule-isolation.py --selftest
    python scripts/qc5-arm1a-rule-isolation.py --run --token-file T --keep <rule-uuid>
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

PROJECT = "019f9f41-78a0-7ac1-a88c-9213748484a1"
CANON_ANTAGONIST = "Lâm Trạch"   # doc-language-gate: ok -- the swapped NAME is the measurement
INVENTED = "Lục Vô Tội"       # doc-language-gate: ok -- a name with 0 canon entities, by design

#: The isolated stack. Dev's composition Postgres is 5555 and is refused by number, not by
#: hostname — a hostname is a string someone can get right and still be pointing at dev.
ISO_PORT = 25555
DEV_PORTS = {5555, 5556}

SEPARATED, NOT_SEPARATED, UNAPPLIED, UNSCORABLE = (
    "SEPARATED", "NOT-SEPARATED", "UNAPPLIED", "UNSCORABLE")


def guard_iso(port: int) -> None:
    """Refuse to mutate anything but the isolated stack."""
    if port in DEV_PORTS:
        raise SystemExit(f"REFUSED — port {port} is dev. This script DEACTIVATES canon rules; "
                         f"rule 6 makes dev read-only and no GRANT covers this.")
    if port != ISO_PORT:
        raise SystemExit(f"REFUSED — port {port} is not the isolated stack ({ISO_PORT}).")


def verdict(rows: list[dict], expected_rules: int = 1) -> dict:
    """Pure. `rows` are `{arm, flagged, rules}` — one per critique call.

    A run is FLAGGED when the critic attributed at least one violation. `rules` is the
    response's own `active_rule_count`, and it is checked BEFORE any rate is computed: a
    restriction that did not apply produces arms that look measured and mean nothing.
    """
    if not rows:
        return {"verdict": UNSCORABLE, "reason": "no runs"}
    wrong = [r for r in rows if r.get("rules") != expected_rules]
    if wrong:
        return {"verdict": UNAPPLIED, "runs": len(rows),
                "saw_rule_counts": sorted({r.get("rules") for r in rows}),
                "reason": f"{len(wrong)} response(s) did not report active_rule_count="
                          f"{expected_rules}; the restriction did not reach the critic, so "
                          f"no rate from this run means anything"}
    planted = [r for r in rows if r["arm"] == "planted"]
    control = [r for r in rows if r["arm"] == "control"]
    if not planted or not control:
        return {"verdict": UNSCORABLE, "reason": "1a needs BOTH arms; a planted arm with no "
                                                 "matched control is what C37 called unscorable"}
    pf = sum(1 for r in planted if r["flagged"])
    cf = sum(1 for r in control if r["flagged"])
    majority = len(planted) // 2 + 1
    sep = pf >= majority and cf == 0
    return {"verdict": SEPARATED if sep else NOT_SEPARATED,
            "planted_flagged": f"{pf}/{len(planted)}", "control_flagged": f"{cf}/{len(control)}",
            "baseline_6_rules": "planted 8/8 · control 7/8 (C37, pre-verification)",
            "reason": ("the plant rises above the floor once the unfalsifiable rules are gone"
                       if sep else
                       "restricting to the one exclusive rule did NOT separate the arms — §12 "
                       "stands, and the rule corpus is not the cause")}


def _psql(port: int, sql: str) -> str:
    r = subprocess.run(
        ["psql", "-h", "localhost", "-p", str(port), "-U", "loreweave",
         "-d", "loreweave_composition", "-At", "-F", "|", "-c", sql],
        capture_output=True, text=True, encoding="utf-8",
        # COPY the environment, never replace it: a bare {PGPASSWORD, PATH} dict drops
        # SystemRoot on Windows and psql fails with "could not translate host name
        # localhost" — a DNS error that reads like an infrastructure problem and is not one.
        env={**os.environ, "PGPASSWORD": "loreweave_dev"})
    if r.returncode != 0:
        raise SystemExit(f"psql failed: {r.stderr[:200]}")
    return r.stdout.strip()


def _critique(url: str, token: str, passage: str) -> dict:
    r = subprocess.run(
        ["curl", "-s", "-m", "300", "-X", "POST", url,
         "-H", f"Authorization: Bearer {token}", "-H", "Content-Type: application/json",
         "-d", json.dumps({"passage": passage}, ensure_ascii=False)],
        capture_output=True, text=True, encoding="utf-8")
    try:
        body = json.loads(r.stdout)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"unparsable: {exc}", "_raw": r.stdout[:160]}
    if "critic" not in body:
        return {"error": f"no critic in response: {str(body)[:120]}"}
    return body["critic"]


def _selftest() -> int:
    R = lambda arm, f, rules=1: {"arm": arm, "flagged": f, "rules": rules}  # noqa: E731
    cases = [
        ("a clean separation is SEPARATED",
         verdict([R("planted", True), R("planted", True), R("planted", True),
                  R("control", False), R("control", False), R("control", False)]),
         lambda v: v["verdict"] == SEPARATED),
        ("THE CONTROL: arms that flag alike are NOT-SEPARATED, which is a real answer",
         verdict([R("planted", True), R("planted", True),
                  R("control", True), R("control", True)]),
         lambda v: v["verdict"] == NOT_SEPARATED),
        ("one control flag is enough to refuse separation — the floor is what 1a fails on",
         verdict([R("planted", True), R("planted", True), R("planted", True),
                  R("control", True), R("control", False), R("control", False)]),
         lambda v: v["verdict"] == NOT_SEPARATED),
        ("THE NON-VACUITY CHECK: a response reporting 6 rules is UNAPPLIED, not a result",
         verdict([R("planted", True, 6), R("planted", True, 6),
                  R("control", False, 6), R("control", False, 6)]),
         lambda v: v["verdict"] == UNAPPLIED),
        ("...and UNAPPLIED beats a separation that LOOKS perfect — that is the whole guard",
         verdict([R("planted", True, 6), R("control", False, 6)]),
         lambda v: v["verdict"] == UNAPPLIED and "planted_flagged" not in v),
        ("a planted arm with NO matched control is UNSCORABLE (C37's lesson)",
         verdict([R("planted", True), R("planted", True)]),
         lambda v: v["verdict"] == UNSCORABLE),
        ("no runs at all is UNSCORABLE, never a pass", verdict([]),
         lambda v: v["verdict"] == UNSCORABLE),
        ("the 6-rule baseline rides along so the comparison is not from memory",
         verdict([R("planted", True), R("control", False)]),
         lambda v: "C37" in v["baseline_6_rules"]),
    ]
    failures = 0
    print("qc5-arm1a-rule-isolation - selftest (offline)")
    for label, got, pred in cases:
        ok = bool(pred(got))
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              f"{'' if ok else '  -> ' + json.dumps(got, ensure_ascii=False)}")
    for label, port, want_raise in (("dev's composition port is REFUSED by number", 5555, True),
                                    ("dev's knowledge-pg too", 5556, True),
                                    ("the iso port is accepted", ISO_PORT, False)):
        try:
            guard_iso(port)
            raised = False
        except SystemExit:
            raised = True
        ok = raised == want_raise
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print("\n  all checks passed" if not failures else f"\n  {failures} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--port", type=int, default=ISO_PORT)
    ap.add_argument("--token-file")
    ap.add_argument("--keep", help="the canon_rule id to leave ACTIVE")
    ap.add_argument("--drafts", type=int, default=4)
    ap.add_argument("--out", default="docs/measurements/2026-08-24-qc5-1a-only-r1.json")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.run:
        ap.print_help()
        return 2
    guard_iso(args.port)
    if not (args.token_file and args.keep):
        print("--token-file and --keep are required")
        return 2

    token = open(args.token_file, encoding="utf-8").read().strip()
    before = _psql(args.port, f"SELECT id FROM canon_rule WHERE project_id='{PROJECT}' "
                              f"AND active AND NOT is_archived ORDER BY created_at;").split("\n")
    before = [b for b in before if b]
    print(f"[1a-only-r1] active before: {len(before)} rule(s); keeping {args.keep}")
    if args.keep not in before:
        print("[1a-only-r1] REFUSED — the rule to keep is not active")
        return 2

    jobs = [j for j in _psql(
        args.port,
        f"SELECT id FROM generation_job WHERE project_id='{PROJECT}' "
        f"AND result->>'text' LIKE '%{CANON_ANTAGONIST}%' ORDER BY created_at DESC "
        f"LIMIT {args.drafts};").split("\n") if j]
    print(f"[1a-only-r1] {len(jobs)} draft(s) naming the antagonist")

    rows: list[dict] = []
    try:
        others = [b for b in before if b != args.keep]
        _psql(args.port, "UPDATE canon_rule SET active=false WHERE id IN ("
                         + ",".join(f"'{o}'" for o in others) + ");")
        now = _psql(args.port, f"SELECT count(*) FROM canon_rule WHERE project_id='{PROJECT}' "
                               f"AND active AND NOT is_archived;")
        print(f"[1a-only-r1] active now: {now}")
        for job in jobs:
            text = _psql(args.port, f"SELECT result->>'text' FROM generation_job "
                                    f"WHERE id='{job}';")
            if CANON_ANTAGONIST not in text:
                continue
            planted = text.replace(CANON_ANTAGONIST, INVENTED)
            url = f"http://localhost:28217/v1/composition/jobs/{job}/critique"
            for arm, passage in (("planted", planted), ("control", text)):
                c = _critique(url, token, passage)
                row = {"arm": arm, "job": job[:8],
                       "flagged": len(c.get("violations") or []) >= 1,
                       "canon": c.get("canon_consistency"),
                       "rules": c.get("active_rule_count"), "error": c.get("error")}
                rows.append(row)
                print(f"  {arm:8s} {row['job']}  flagged={row['flagged']}  "
                      f"canon={row['canon']}  rules={row['rules']}  {row['error'] or ''}",
                      flush=True)
    finally:
        _psql(args.port, "UPDATE canon_rule SET active=true WHERE id IN ("
                         + ",".join(f"'{b}'" for b in before) + ");")
        after = _psql(args.port, f"SELECT count(*) FROM canon_rule WHERE project_id='{PROJECT}' "
                                 f"AND active AND NOT is_archived;")
        print(f"[1a-only-r1] RESTORED — active after: {after} (was {len(before)})")

    v = verdict(rows)
    print("\n[1a-only-r1] " + json.dumps(v, ensure_ascii=False, indent=1))
    json.dump({"verdict": v, "rows": rows},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[1a-only-r1] -> {args.out}")
    return 0 if v["verdict"] in (SEPARATED, NOT_SEPARATED) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
