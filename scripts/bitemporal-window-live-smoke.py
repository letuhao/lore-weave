#!/usr/bin/env python3
"""bitemporal-window-live-smoke — does a windowed read actually HOLD a reader at a position?

T48s found the answer was no, live, on the default backend: `/kg/neighborhood` accepted
`as_of_chapter`, computed the window, reported `temporal_capability.kg = "ordinal_valid_time"`
— and returned chapter-10 relationships to a caller held at chapter 1. The value was computed
on one line, `None`-checked on the next, and reached nothing.

**It was invisible because nothing asked.** `architecture-live-proof`'s four legs cover the
backend, the store, the KAL surface and the port; none of them the BI-TEMPORAL SPINE, which is
what this architecture exists for. This is that leg.

WHAT IT ASSERTS, AND WHY EACH HALF IS NEEDED
────────────────────────────────────────────
    1 MONOTONIC   a wider window never returns FEWER rows than a narrower one
    2 BOUNDED     every row's `valid_from_ordinal` is <= the requested position on the axis
    3 NON-VACUOUS the narrow window returns FEWER rows than the head

Two of these pass on a broken system by themselves, which is the point of having three:

  · a read that IGNORES the window is perfectly monotonic and perfectly bounded-looking if you
    never check the ordinals — that is exactly the state T48s found.
  · a read that returns NOTHING at every position satisfies monotonicity and boundedness
    trivially. That is the state the first half of T48s's fix produced (the route passed a raw
    chapter number where the axis is `chapter × 1_000_000`), and an empty answer reads as "this
    reader may see nothing yet" rather than "the units are wrong".

So the smoke fails on an empty run and on an unbounded one, and only a read that both moves
with the window AND respects the axis can pass.

Usage
    python scripts/bitemporal-window-live-smoke.py --selftest
    python scripts/bitemporal-window-live-smoke.py --base-url http://localhost:23210 \\
        --book-id <uuid> --user-id <uuid> --internal-token <tok> --entity-id <glossary-id>
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

#: The reading axis. `EVENT_ORDER_CHAPTER_STRIDE` in `app/domain/graph_models.py` — a chapter
#: position N is stored as N × STRIDE, and passing a raw N is the bug the second half of
#: T48s's fix repaired.
STRIDE = 1_000_000

HOLDS, LEAKS, EMPTY, FLAT, ERROR = "HOLDS", "LEAKS", "EMPTY", "FLAT", "ERROR"


def verdict(samples: list[dict], head_rows: int) -> dict:
    """Pure. `samples` are `{as_of, rows, max_ordinal}` in ascending `as_of` order.

    Order matters: EMPTY and LEAKS are checked before monotonicity, because a read that
    returns nothing is monotonic and a read that ignores the window is monotonic too. The
    cheap property must not be allowed to answer for the expensive one.
    """
    if not samples:
        return {"verdict": ERROR, "reason": "no samples"}
    if any(s.get("rows") is None for s in samples):
        return {"verdict": ERROR, "reason": "a probe failed to return a row count"}

    if all(s["rows"] == 0 for s in samples):
        return {"verdict": EMPTY, "reason":
                "every windowed read returned NOTHING. That satisfies monotonic and bounded "
                "trivially and is how a units bug looks: `valid_from_ordinal <= 1` excludes a "
                "corpus stored at 1_000_000. An empty answer is the SAFE direction, which is "
                "why it must fail here"}

    leaked = [s for s in samples
              if s["max_ordinal"] is not None and s["max_ordinal"] > s["as_of"] * STRIDE]
    if leaked:
        return {"verdict": LEAKS, "leaked": leaked, "reason":
                "a row was returned whose story position is AFTER the requested one — the "
                "window is advertised and not applied. This is T48s, exactly"}

    rows = [s["rows"] for s in samples]
    if any(b < a for a, b in zip(rows, rows[1:])):
        return {"verdict": ERROR, "rows": rows, "reason":
                "a WIDER window returned FEWER rows; a cumulative as-of read cannot do that"}

    if max(rows) >= head_rows and min(rows) >= head_rows:
        return {"verdict": FLAT, "rows": rows, "head": head_rows, "reason":
                "every window returned as much as the UNWINDOWED head, so nothing was "
                "actually filtered. A read that ignores `as_of` looks exactly like this"}

    return {"verdict": HOLDS, "rows": rows, "head": head_rows,
            "max_ordinals": [s["max_ordinal"] for s in samples],
            "reason": "the window moves with the position, every row sits at or before it on "
                      "the axis, and the narrow window is strictly smaller than the head"}


def _get(url: str, headers: dict) -> object:
    req = urllib.request.Request(url)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode("utf-8", "replace")[:160]}
    except Exception as e:  # noqa: BLE001 — a smoke reports a transport failure
        return {"_error": 0, "_body": f"{type(e).__name__}: {e}"}


def _sample(payload: object, as_of: int | None) -> dict:
    if not isinstance(payload, dict) or "_error" in payload:
        return {"as_of": as_of, "rows": None, "max_ordinal": None}
    edges = payload.get("edges") or []
    ords = [e.get("valid_from_ordinal") for e in edges
            if isinstance(e, dict) and e.get("valid_from_ordinal") is not None]
    return {"as_of": as_of, "rows": len(edges), "max_ordinal": max(ords) if ords else None}


def _selftest() -> int:
    S = lambda a, r, m: {"as_of": a, "rows": r, "max_ordinal": m}  # noqa: E731
    cases = [
        ("a window that moves and stays on the axis HOLDS",
         verdict([S(1, 25, 1_000_000), S(3, 33, 2_000_000), S(6, 41, 6_000_000)], 50), HOLDS),
        ("THE LEAK: a row positioned after the request is LEAKS, not a pass",
         verdict([S(1, 50, 10_000_000), S(3, 50, 10_000_000)], 50), LEAKS),
        ("THE UNITS BUG: everything empty is EMPTY, never a trivially-monotonic pass",
         verdict([S(1, 0, None), S(3, 0, None), S(6, 0, None)], 50), EMPTY),
        ("...and EMPTY is checked BEFORE monotonicity, or the cheap property answers first",
         verdict([S(1, 0, None), S(3, 0, None)], 50)["verdict"] != HOLDS, True),
        ("a read that IGNORES the window returns the head at every position — FLAT",
         verdict([S(1, 50, None), S(3, 50, None)], 50), FLAT),
        ("a WIDER window returning FEWER rows is an ERROR, not a narrower window",
         verdict([S(1, 40, 1_000_000), S(3, 10, 2_000_000)], 50), ERROR),
        ("the boundary is INCLUSIVE: max_ordinal == as_of x STRIDE is fine",
         verdict([S(1, 25, 1_000_000), S(6, 41, 6_000_000)], 50), HOLDS),
        ("a failed probe is ERROR, never a silent pass",
         verdict([S(1, None, None)], 50), ERROR),
        ("no samples at all is ERROR", verdict([], 50), ERROR),
    ]
    failures = 0
    print("bitemporal-window-live-smoke - selftest (offline)")
    for label, got, want in cases:
        actual = got if isinstance(got, bool) else got["verdict"]
        ok = actual == want
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: expected {want}, got {actual}")
    print("\n  all checks passed" if not failures else f"\n  {failures} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--base-url", default="http://localhost:23210")
    ap.add_argument("--book-id")
    ap.add_argument("--user-id")
    ap.add_argument("--internal-token")
    ap.add_argument("--entity-id")
    ap.add_argument("--positions", default="1,3,6,10")
    ap.add_argument("--cap", type=int, default=50)
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not (args.book_id and args.user_id and args.internal_token and args.entity_id):
        print("[bitemporal] --book-id, --user-id, --internal-token and --entity-id are required")
        return 2

    headers = {"X-Internal-Token": args.internal_token, "X-User-Id": args.user_id}
    base = (f"{args.base_url.rstrip('/')}/v1/kal/books/{args.book_id}"
            f"/entities/{args.entity_id}/neighborhood?hops=1&cap={args.cap}")

    head = _sample(_get(base, headers), None)
    print(f"  head (no window)   {head['rows']} row(s)  max_ordinal={head['max_ordinal']}")
    samples = []
    for pos in [int(p) for p in args.positions.split(",") if p.strip()]:
        s = _sample(_get(f"{base}&as_of={pos}", headers), pos)
        samples.append(s)
        print(f"  as_of={pos:<4}         {s['rows']} row(s)  max_ordinal={s['max_ordinal']}"
              f"   ceiling={pos * STRIDE}")

    v = verdict(samples, head["rows"] if head["rows"] is not None else 0)
    print("\n[bitemporal] " + json.dumps(v, ensure_ascii=False, indent=1))
    return 0 if v["verdict"] == HOLDS else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
