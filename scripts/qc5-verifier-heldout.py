#!/usr/bin/env python3
"""QC-5 — the precision verifier, measured on cases it was NOT derived from.

C31 is the PO's precision spend, and its evidence is:

    a narrow passage-aware SECOND pass keeps a planted violation 4/4 while dropping
    2/2 clean and 14/14 historical false positives — on a 26B verifier.

**Those 14 are the false positives that motivated building it.** Rule 3: *a criterion that
cannot fail is not a criterion; validate a detector on a case it was NOT derived from, else it
is green by construction.* This repo has shipped that mistake before and named it —
`detector-fitted-to-its-motivating-examples-is-green-by-construction`.

THE HELD-OUT SET, AND WHY IT NEEDS NO HUMAN ADJUDICATION
────────────────────────────────────────────────────────
The control arm is the flow's **unmodified** draft. R1 says the canon antagonist IS the
betrayer and no one else is; the untouched draft attributes the trap to exactly that character.
So **the control arm is canon-conforming with respect to R1 by construction**, and every
violation attributed under R1 on a control draft is a false positive *by the design of the
experiment* — not by anyone's reading of the prose. That is what makes this measurable without
a second adjudication round, and it is the same property C37 relied on for the matched control.

The verifier's own prompt is written to catch exactly this class:

    Answer false if the passage is consistent with the rule, if the rule does not speak to
    what the passage describes, or if the claim would need a requirement the RULE TEXT does
    not literally state. Restating the rule is not a contradiction.

So a surviving R1 attribution on an untouched draft is a verifier miss, in its own terms.

⚠️ **NON-VACUITY, TWICE.** A run proves nothing if the verifier never ran, and nothing if it
ran as the critic auditing itself — C31 measured a model keeping **0/3** of its own false
positives, so a book whose `critic_verifier` resolves to the critic has no second opinion at
all. Both are distinct verdicts, and neither reports a precision figure.

Usage
    python scripts/qc5-verifier-heldout.py --selftest
    python scripts/qc5-verifier-heldout.py --run --token-file T --drafts 4
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

PROJECT = "019f9f41-78a0-7ac1-a88c-9213748484a1"
CANON_ANTAGONIST = "Lâm Trạch"   # doc-language-gate: ok -- the canon name IS the experiment
ISO_PORT = 25555
DEV_PORTS = {5555, 5556}

HELD_OUT_MISS, HELD_OUT_HOLDS, NO_FINDINGS, VERIFIER_ABSENT, VERIFIER_IS_CRITIC = (
    "HELD-OUT-MISS", "HELD-OUT-HOLDS", "NO-FINDINGS", "VERIFIER-ABSENT", "VERIFIER-IS-CRITIC")


def verdict(rows: list[dict], *, verifier_ref: str | None, critic_ref: str | None) -> dict:
    """Pure. `rows` are `{attributed, unverified, raw}` — one per CONTROL critique.

    Order matters: the two vacuity checks come first, because a precision figure computed
    over a run where the verifier never ran is a number about nothing.
    """
    if verifier_ref is None:
        return {"verdict": VERIFIER_ABSENT,
                "reason": "the book configures no `critic_verifier`; the critic audits itself "
                          "and C31 measured that at 0/3. No precision figure is reported."}
    if critic_ref is not None and verifier_ref == critic_ref:
        return {"verdict": VERIFIER_IS_CRITIC, "verifier_ref": verifier_ref,
                "reason": "the configured verifier IS the critic. Same model, no second "
                          "opinion — a distinct ROLE resolving to the same MODEL is the "
                          "shape that reads as configured and behaves as absent."}
    if not rows:
        return {"verdict": NO_FINDINGS, "reason": "no control runs"}
    attributed = sum(r["attributed"] for r in rows)
    dropped = sum(r["unverified"] for r in rows)
    raw = sum(r["raw"] for r in rows)
    if raw == 0:
        return {"verdict": NO_FINDINGS, "runs": len(rows),
                "reason": "the critic found nothing on any control draft, so the verifier had "
                          "nothing to audit. That is a clean drafter, not a precise verifier."}
    # Every surviving attribution on an UNTOUCHED draft is a false positive by construction.
    surviving = attributed
    return {"verdict": HELD_OUT_MISS if surviving else HELD_OUT_HOLDS,
            "runs": len(rows), "raw": raw,
            "false_positives_dropped_by_verifier": dropped,
            "false_positives_SURVIVING": surviving,
            "c31_claim": "14/14 historical false positives dropped (the set it was built from)",
            "reason": ("the verifier kept false positives on drafts it was not derived from — "
                       "C31's 14/14 is a figure over its own motivating examples"
                       if surviving else
                       "the verifier dropped every false positive on a held-out set, so C31's "
                       "result generalises")}


def _psql(port: int, sql: str) -> str:
    r = subprocess.run(
        ["psql", "-h", "localhost", "-p", str(port), "-U", "loreweave",
         "-d", "loreweave_composition", "-At", "-F", "|", "-c", sql],
        capture_output=True, text=True, encoding="utf-8",
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
        return json.loads(r.stdout).get("critic", {"error": "no critic key"})
    except Exception as exc:  # noqa: BLE001
        return {"error": f"unparsable: {exc}"}


def _selftest() -> int:
    V, C = "verifier-26b", "critic-7b"
    R = lambda a, u, raw=1: {"attributed": a, "unverified": u, "raw": raw}  # noqa: E731
    cases = [
        ("a verifier that drops every held-out false positive HOLDS",
         verdict([R(0, 1), R(0, 1)], verifier_ref=V, critic_ref=C),
         lambda v: v["verdict"] == HELD_OUT_HOLDS),
        ("one surviving false positive on an untouched draft is a MISS",
         verdict([R(1, 0), R(0, 1)], verifier_ref=V, critic_ref=C),
         lambda v: v["verdict"] == HELD_OUT_MISS and v["false_positives_SURVIVING"] == 1),
        ("VACUITY 1: no verifier configured reports no precision figure at all",
         verdict([R(1, 0)], verifier_ref=None, critic_ref=C),
         lambda v: v["verdict"] == VERIFIER_ABSENT and "false_positives_SURVIVING" not in v),
        ("VACUITY 2: a verifier that IS the critic is not a second opinion",
         verdict([R(0, 1)], verifier_ref=C, critic_ref=C),
         lambda v: v["verdict"] == VERIFIER_IS_CRITIC),
        ("...and that beats a PERFECT-looking drop rate, which is the whole guard",
         verdict([R(0, 5), R(0, 5)], verifier_ref=C, critic_ref=C),
         lambda v: v["verdict"] == VERIFIER_IS_CRITIC and "false_positives_dropped_by_verifier"
                   not in v),
        ("a critic that found NOTHING is a clean drafter, not a precise verifier",
         verdict([R(0, 0, 0), R(0, 0, 0)], verifier_ref=V, critic_ref=C),
         lambda v: v["verdict"] == NO_FINDINGS),
        ("no runs is NO-FINDINGS, never a pass",
         verdict([], verifier_ref=V, critic_ref=C), lambda v: v["verdict"] == NO_FINDINGS),
        ("C31's claim rides along so the comparison is not from memory",
         verdict([R(1, 0)], verifier_ref=V, critic_ref=C),
         lambda v: "14/14" in v["c31_claim"]),
    ]
    failures = 0
    print("qc5-verifier-heldout - selftest (offline)")
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
    ap.add_argument("--port", type=int, default=ISO_PORT)
    ap.add_argument("--token-file")
    ap.add_argument("--drafts", type=int, default=4)
    ap.add_argument("--out", default="docs/measurements/2026-08-24-qc5-verifier-heldout.json")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.run or not args.token_file:
        ap.print_help()
        return 2
    if args.port in DEV_PORTS:
        raise SystemExit(f"REFUSED — port {args.port} is dev.")

    token = open(args.token_file, encoding="utf-8").read().strip()
    ver = _psql(args.port, f"SELECT settings->'model_roles'->'critic_verifier'->>'model_ref' "
                           f"FROM composition_work WHERE project_id='{PROJECT}' LIMIT 1;") or None
    crit = _psql(args.port, f"SELECT settings->>'critic_model_ref' FROM composition_work "
                            f"WHERE project_id='{PROJECT}' LIMIT 1;") or None
    print(f"[heldout] critic={crit}  verifier={ver}")

    jobs = [j for j in _psql(
        args.port, f"SELECT id FROM generation_job WHERE project_id='{PROJECT}' "
                   f"AND result->>'text' LIKE '%{CANON_ANTAGONIST}%' ORDER BY created_at DESC "
                   f"LIMIT {args.drafts};").split("\n") if j]
    rows, spans = [], []
    for job in jobs:
        text = _psql(args.port, f"SELECT result->>'text' FROM generation_job WHERE id='{job}';")
        c = _critique(f"http://localhost:28217/v1/composition/jobs/{job}/critique", token, text)
        v = c.get("violations") or []
        row = {"job": job[:8], "attributed": len(v),
               "unverified": c.get("violations_unverified", 0),
               "raw": c.get("violations_raw_count", 0),
               "canon": c.get("canon_consistency")}
        rows.append(row)
        for x in v:
            # STRUCTURE, not corpus text. `docs/measurements/*.json` in this repo carry
            # numbers — the existing 1a measurement has zero non-English bytes — and the one
            # verbatim span that carries the argument lives in the plan's C45 block under a
            # `doc-language-gate` pragma, where its form is what is being argued about.
            # `restates_rule` is the class the verifier's own prompt says it must reject:
            # a `why` that quotes the rule id back instead of naming a contradiction.
            why = x.get("why") or ""
            spans.append({"job": job[:8], "rule_id": x.get("rule_id"),
                          "span_chars": len((x.get("span") or "")),
                          "why_chars": len(why),
                          "restates_rule": "[R" in why or "R1" in why})
        print(f"  control {row['job']}  raw={row['raw']}  attributed={row['attributed']}  "
              f"verifier_dropped={row['unverified']}  canon={row['canon']}", flush=True)

    out = verdict(rows, verifier_ref=ver, critic_ref=crit)
    print("\n[heldout] " + json.dumps(out, ensure_ascii=False, indent=1))
    json.dump({"verdict": out, "rows": rows, "surviving_violations": spans,
               "critic_ref": crit, "verifier_ref": ver},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[heldout] -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
