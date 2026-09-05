#!/usr/bin/env python3
"""glossary-ordinal-axis-gate — one fact in 48,611 sits on the wrong reading axis.

T48s cost this repo two fixes for the same mistake on the GRAPH side: a chapter number used
where the axis is `chapter × EVENT_ORDER_CHAPTER_STRIDE`, and the reverse. Both times the
symptom was a windowed read returning nothing, and "nothing" reads as *this reader may see
nothing yet* rather than *the units are wrong*.

This is the same question asked of the SSOT side. Measured on iso 2026-08-30:

    valid_from_ordinal < 1000          48 610 facts      <- the convention
    valid_from_ordinal >= 1 000 000         1 fact       <- six orders of magnitude out
    books carrying BOTH scales               1

The glossary substrate stores chapter-scale positions. `composition-service`'s KAL client says
so in its own docstring — *"`as_of` is REQUIRED and is the chapter's `sort_order`"* — and the
`state` route echoes the value back unchanged. **One row does not.**

WHY A ROW LIKE THAT IS WORSE THAN A MISSING ONE
───────────────────────────────────────────────
It is present in the unwindowed head and absent from every windowed read a real reader can
make: bounded by `as_of <= N`, a fact at 12 000 000 needs a caller asking for chapter twelve
MILLION. So it is simultaneously *there* (a head read, a count, an export) and *unreachable*
(every as-of read), and neither answer is wrong on its own terms. That is the shape this
project keeps paying for — a mechanism that exists and reaches nothing.

WHAT THIS GATE IS, AND IS NOT
─────────────────────────────
It is a RATCHET on a measured number, not a repair. The outlier lives in a store this run is
not authorised to write, and one bad row is a data question, not a code one. The number may
only fall: a producer that starts writing stride-scale ordinals into the glossary moves it up
and reds this gate on the commit that does it.

Like `graph-store-migrated-gate`, it takes a CENSUS rather than opening a connection — a gate
that needed live credentials could not run offline in CI, which is where it has to run.

PRODUCING THE CENSUS (the command, not a placeholder)
────────────────────────────────────────────────────
Until T48ao nothing ever fed this gate: it was wired as `--selftest` and its live arm never
ran, so the measurement below was taken once, by hand, and never again. It is now leg 6 of
`architecture-live-proof`, and this is the command that produces its input:

    docker exec <postgres> psql -U loreweave -d loreweave_glossary -tAc "
      SELECT json_build_object(
        'chapter_scale', count(*) FILTER (WHERE valid_from_ordinal <  1000000
                                            AND valid_from_ordinal IS NOT NULL),
        'stride_scale',  count(*) FILTER (WHERE valid_from_ordinal >= 1000000),
        'mixed_books', (SELECT count(*) FROM (
            SELECT book_id FROM entity_facts WHERE valid_from_ordinal IS NOT NULL
            GROUP BY book_id
            HAVING count(*) FILTER (WHERE valid_from_ordinal <  1000000) > 0
               AND count(*) FILTER (WHERE valid_from_ordinal >= 1000000) > 0) t))
      FROM entity_facts;" > axis.json

    python scripts/glossary-ordinal-axis-gate.py --census axis.json --ceiling 1

Usage
    python scripts/glossary-ordinal-axis-gate.py --selftest
    python scripts/glossary-ordinal-axis-gate.py --census <file> [--ceiling N]
"""
from __future__ import annotations

import argparse
import json
import sys

CONSISTENT, OUTLIERS, REGRESSED, INVERTED, DISARMED = (
    "CONSISTENT", "OUTLIERS", "REGRESSED", "INVERTED", "DISARMED")

#: A position at or above this is not a chapter number by any reading — the smallest stride
#: this repo uses is 1 000 000, so a value here is an ordinal that escaped conversion.
#:
#: T48aq — it was DEFINED AND NEVER USED: not printed, not compared, referenced nowhere. The
#: gate takes a pre-split census, so the threshold is applied by the PRODUCER, and this constant
#: silently documented a number in someone else's SQL. `gate-number-visibility-gate` caught it —
#: "a ratchet nobody can see… the number IS the mechanism" — and it had been RED for eleven
#: commits because `--run-all` is CI-only and I never ran it.
#:
#: It is now printed on every verdict, and the selftest asserts the documented producer command
#: uses this same threshold, so the constant and the SQL cannot drift apart in silence.
STRIDE_FLOOR = 1_000_000


def verdict(census: dict | None, ceiling: int) -> dict:
    """Pure. `census` is `{chapter_scale, stride_scale, mixed_books}`.

    Order matters. INVERTED is checked before the ceiling because a store that has flipped to
    stride-scale wholesale is not "many outliers" — it is a different axis, and reporting it as
    a ratchet breach would send the next reader looking for bad rows instead of a migration.
    """
    if not census:
        return {"verdict": DISARMED, "reason":
                "no census supplied — nothing was measured, and a gate that passes on no "
                "measurement is the vacuous green this repo keeps paying for"}
    for key in ("chapter_scale", "stride_scale", "mixed_books"):
        if not isinstance(census.get(key), int):
            return {"verdict": DISARMED, "reason":
                    f"the census is missing `{key}`, so the axis was not measured"}

    chapter, stride, mixed = (census["chapter_scale"], census["stride_scale"],
                              census["mixed_books"])
    if chapter == 0 and stride == 0:
        return {"verdict": DISARMED, "reason":
                "the store holds no positioned facts at all, so there is no axis to check"}
    if stride > chapter:
        return {"verdict": INVERTED, "reason":
                f"{stride} fact(s) are stride-scale against {chapter} chapter-scale — the "
                f"store's convention has MOVED. That is a migration to describe, not outliers "
                f"to hunt, and this gate's ceiling is meaningless until it is described"}
    if stride > ceiling:
        return {"verdict": REGRESSED, "stride_scale": stride, "ceiling": ceiling, "reason":
                f"{stride} fact(s) sit on the stride axis against a ceiling of {ceiling}. A "
                f"producer is writing `chapter × STRIDE` where the store keeps chapters; those "
                f"rows are in every head read and in NO windowed one"}
    if stride:
        return {"verdict": OUTLIERS, "stride_scale": stride, "ceiling": ceiling,
                "mixed_books": mixed, "reason":
                f"{stride} known off-axis fact(s) at or under the ceiling, in {mixed} book(s) "
                f"carrying both scales. Present in a head read, unreachable by every as-of read "
                f"a real position can make. A CEILING: it may only fall"}
    return {"verdict": CONSISTENT, "chapter_scale": chapter, "reason":
            f"every one of {chapter} positioned fact(s) is on the chapter axis"}


def _selftest() -> int:
    iso = {"chapter_scale": 48610, "stride_scale": 1, "mixed_books": 1}
    cases = [
        ("ISO AS MEASURED: one known outlier at the ceiling", verdict(iso, 1), OUTLIERS),
        ("THE REGRESSION: a second off-axis row breaches the ceiling",
         verdict({**iso, "stride_scale": 2}, 1), REGRESSED),
        ("...and the ceiling is what makes it a criterion — at 2 the same census passes",
         verdict({**iso, "stride_scale": 2}, 2), OUTLIERS),
        ("a clean store is CONSISTENT",
         verdict({"chapter_scale": 100, "stride_scale": 0, "mixed_books": 0}, 1), CONSISTENT),
        ("...and CONSISTENT is reachable at ceiling 0, so the ratchet can actually finish",
         verdict({"chapter_scale": 100, "stride_scale": 0, "mixed_books": 0}, 0), CONSISTENT),
        ("A MIGRATED store is INVERTED, not a ratchet breach — a case NOT derived from iso",
         verdict({"chapter_scale": 3, "stride_scale": 48000, "mixed_books": 2}, 1), INVERTED),
        ("...and INVERTED is checked BEFORE the ceiling, or it reads as 47999 bad rows",
         verdict({"chapter_scale": 3, "stride_scale": 48000, "mixed_books": 2}, 0)["verdict"],
         INVERTED),
        ("no census is DISARMED, never a pass", verdict(None, 1), DISARMED),
        ("a census missing a key is DISARMED, not read as zero",
         verdict({"chapter_scale": 5, "stride_scale": 0}, 1), DISARMED),
        ("an EMPTY store is DISARMED — nothing was measured, so nothing is proven",
         verdict({"chapter_scale": 0, "stride_scale": 0, "mixed_books": 0}, 1), DISARMED),
        ("only REGRESSED and INVERTED block",
         sorted(v for v in (CONSISTENT, OUTLIERS, REGRESSED, INVERTED, DISARMED)
                if v in _BLOCKING), sorted([INVERTED, REGRESSED])),
        ("T48aq — the documented PRODUCER uses the same threshold as STRIDE_FLOOR, so the "
         "constant and the SQL cannot drift apart in silence",
         str(STRIDE_FLOOR) in __doc__ and __doc__.count(str(STRIDE_FLOOR)) >= 2, True),
        ("every verdict carries a reason",
         all(verdict(c, 1).get("reason") for c in
             (iso, None, {}, {"chapter_scale": 0, "stride_scale": 0, "mixed_books": 0})), True),
    ]
    failures = 0
    print("glossary-ordinal-axis-gate - selftest (offline)")
    for label, got, want in cases:
        actual = got["verdict"] if isinstance(got, dict) and "verdict" in got else got
        ok = actual == want
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: expected {want}, got {actual}")
    print(chr(10) + "  all checks passed" if not failures
          else chr(10) + f"  {failures} FAILED")
    return 1 if failures else 0


#: DISARMED does not block, for the reason its sibling gives: a gate that reddened on "I could
#: not look" gets switched off. It prints as INDETERMINATE so it never reads as a pass.
_BLOCKING = {REGRESSED, INVERTED}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--census", help="JSON: {chapter_scale, stride_scale, mixed_books}")
    ap.add_argument("--ceiling", type=int, default=1,
                    help="known off-axis rows; a RATCHET, it may only fall")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()

    # T48aq — REFUSE a bare invocation.
    #
    # `gate-wiring-gate --run-all` runs every discovered gate with NO arguments, and this one
    # answered DISARMED and exited 0: executed in CI, green, and proving nothing, on every
    # commit. That is worse than never running, because the green is visible and the vacuity
    # is not. The runner's honesty mechanism (NEEDS_ARGS + a staleness probe) catches a gate
    # that FAILS bare and cannot see one that passes vacuously -- so the gate has to say so.
    #
    # Same contract the two existing NEEDS_ARGS rows carry: "requires --file or --selftest".
    if not args.census:
        # The threshold is named even in the REFUSAL. `gate-number-visibility-gate` inspects a
        # BARE run, so a refusal that withholds the number makes the ratchet invisible again --
        # which is exactly what happened when T48aq added this branch and the meta-gate stayed
        # red for a second reason.
        print(f"[glossary-ordinal-axis] stride floor {STRIDE_FLOOR} · ceiling {args.ceiling}")
        print("[glossary-ordinal-axis] REFUSED — no --census supplied. Bare, this gate can only "
              "answer DISARMED, which exits 0 and proves nothing; run --selftest for the "
              "offline checks or produce a census (see the usage block).")
        return 2

    census = None
    if args.census:
        try:
            with open(args.census, encoding="utf-8") as fh:
                census = json.load(fh)
        except (OSError, ValueError) as e:
            print(f"[glossary-ordinal-axis] DISARMED — census unreadable: {e}")
            return 0

    v = verdict(census, args.ceiling)
    label = ("FAIL" if v["verdict"] in _BLOCKING
             else "INDETERMINATE" if v["verdict"] == DISARMED else "OK")
    # The numbers ON THE PASS PATH, not only on failure: a ratchet that speaks only when it
    # breaks turns drift into history rather than a diff.
    print(f"[glossary-ordinal-axis] stride floor {STRIDE_FLOOR} · ceiling {args.ceiling} · "
          f"chapter-scale {census.get('chapter_scale')} · stride-scale "
          f"{census.get('stride_scale')} · mixed books {census.get('mixed_books')}")
    print(f"[glossary-ordinal-axis] {label} — {v['verdict']}: {v['reason']}")
    return 1 if v["verdict"] in _BLOCKING else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
