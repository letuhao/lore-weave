"""S10 · the live runner — drive the seeded suite against a real stack and record a BASELINE.

Why a recorded baseline is the point of the slice
-------------------------------------------------
The spec asks S10 for *"a scored set with ≥N seeded defects"*, and the reason is in the risk
table: a later slice must be caught if it BREAKS something. A suite you can run tells you the
engine's state today; a suite whose result is **committed** tells you whether tomorrow's change
moved it. Without the recorded artefact this is a diagnostic, not an instrument.

The predecessor this replaces
------------------------------
`scripts/eval/eval_a2_canon.py` gates on `status=="checked" AND iterations>=1` across five
scenarios and prints *"PASS — gone-cast contradiction detected"*. Two things are wrong with it,
and both are why S10 exists: it has **no control**, so a working canon loop and an engine that
revises unconditionally produce the identical green; and it reads `canon` off the POST response,
which on `mode:"auto"` is a **202 with `{job_id, status:"pending"}`** — the result lands on the
job row. So it has been reporting on a field that is None.

Usage (needs a running stack + a BYOK chat model):

    python -m app.eval.run_live --token <bearer> --model-ref <user_model_id>
    python -m app.eval.run_live ... --write app/eval/baseline.json    # record
    python -m app.eval.run_live ... --against app/eval/baseline.json  # compare

Exit 0 = matches the baseline (or wrote one). Exit 1 = a class moved.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from app.eval.defects import DEFECTS, Outcome
from app.eval.driver import LiveDriver
from app.eval.suite import score_suite


def _run(driver: LiveDriver, only: set[str] | None, notes: dict) -> Any:
    runs = []
    for cls in DEFECTS:
        if only and cls.code not in only:
            continue
        if cls.blocked_on:
            # A blind class is EXCLUDED, not run-and-scored. Running it would produce a
            # permanently-quiet detector, and a quiet detector on the seeded variant scores
            # MISSED — a false finding about the engine caused by the instrument.
            continue
        print(f"  {cls.code} · seeded …", flush=True)
        seeded = driver.run(cls, "seeded")
        notes[(cls.code, "seeded")] = seeded
        print(f"  {cls.code} · control …", flush=True)
        control = driver.run(cls, "control")
        notes[(cls.code, "control")] = control
        runs.append((cls, seeded, control))
    return score_suite(runs)


def _as_json(result: Any) -> dict:
    return {
        "classes": {
            c.code: {"seeded": c.seeded.value, "control": c.control.value}
            for c in result.classes
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--model-ref", required=True)
    ap.add_argument("--language", default="vi")
    ap.add_argument("--user-id", default="", help="owner id — the gone-cast seeding calls knowledge persist-pass2, which is project-scoped")
    ap.add_argument("--only", default="", help="comma-separated class codes")
    ap.add_argument("--write", default="")
    ap.add_argument("--against", default="")
    a = ap.parse_args()

    only = {c.strip() for c in a.only.split(",") if c.strip()} or None
    driver = LiveDriver(token=a.token, model_ref=a.model_ref, language=a.language,
                        user_id=a.user_id)
    print("running the seeded suite against the live stack…", flush=True)
    notes: dict = {}
    result = _run(driver, only, notes)
    payload = _as_json(result)

    print("\n== result ==")
    for cls in result.classes:
        mark = "ok " if (cls.seeded is Outcome.FIRED and cls.control is Outcome.QUIET) else "!! "
        print(f"  {mark}{cls.code:32s} seeded={cls.seeded.value:6s} control={cls.control.value}")
        # An ERROR without its reason is a dead end for whoever reads the run. `note` is the
        # only place the driver records WHY a seeding path could not produce an observation.
        for label, obs in (("seeded", notes.get((cls.code, "seeded"))),
                           ("control", notes.get((cls.code, "control")))):
            if obs is not None and obs.failed and obs.note:
                print(f"       {label}: {obs.note[:160]}")
    for cls in DEFECTS:
        if cls.blocked_on:
            print(f"  -- {cls.code:32s} BLIND — {cls.blocked_on[:80]}")

    if a.write:
        p = pathlib.Path(a.write)
        p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nbaseline written: {p}")
        return 0

    if a.against:
        base = json.loads(pathlib.Path(a.against).read_text(encoding="utf-8"))
        moved = []
        for code, now in payload["classes"].items():
            was = base.get("classes", {}).get(code)
            if was is None:
                moved.append(f"{code}: NEW (not in baseline)")
            elif was != now:
                moved.append(f"{code}: {was} → {now}")
        for code in base.get("classes", {}):
            if code not in payload["classes"]:
                moved.append(f"{code}: MISSING from this run")
        if moved:
            print("\nBASELINE MOVED:")
            for m in moved:
                print("  · " + m)
            return 1
        print("\nmatches the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
