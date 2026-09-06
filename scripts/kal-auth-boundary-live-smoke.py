#!/usr/bin/env python3
"""kal-auth-boundary-live-smoke — does the KAL's guard DISCRIMINATE, or just answer?

Every other live check in this repo reaches the KAL with `X-Internal-Token`, and
`KalAuthGuard`'s first branch is:

    // 1. SERVICE mode — a valid internal token; trust the forwarded X-User-Id.
    if (cfg.internalToken && presented === cfg.internalToken) return true;

**So the grant check is never executed by any of them.** `architecture-live-proof`'s five legs,
`kal-read-surface-live-smoke`'s fourteen routes, `bitemporal-window-live-smoke` — all service
mode, all past the guard before it looks at a book. The USER path, where the KAL is the
security boundary because the BFF does no grant check, has no live proof at all.

WHY THREE ARMS AND NOT ONE
──────────────────────────
A guard that refuses EVERYTHING passes a refusal test, and a guard that allows everything
passes an allow test. Neither says the guard discriminates. So this asserts three OUTCOMES that
must differ:

    SERVICE   a valid internal token           -> 2xx     the guard lets a trusted caller past
    STRANGER  a valid JWT, no grant on the book -> 403     refused on the GRANT
    ANON      no credential at all              -> 401     refused on AUTHENTICATION

401 and 403 being DIFFERENT is the load-bearing part. A guard that answered 403 to both would
look secure and would have stopped checking grants — it would be rejecting on authentication
alone, and the first user with any valid token would walk through the moment the auth check
moved. Conflating them is how a grant check becomes decorative.

⚠️ **A `--book-id` the book-service does not know answers 403 for EVERY user, owner included.**
Measured 2026-08-30: the KAL sweep's book is a KG-only id with no `books` row on iso, so
`hasBookAccess` correctly answers no to everyone. That makes the STRANGER arm pass for the
wrong reason, and it is why the SERVICE arm is required: if the service arm cannot reach the
data either, the run is UNSCORABLE rather than green.

Usage
    python scripts/kal-auth-boundary-live-smoke.py --selftest
    python scripts/kal-auth-boundary-live-smoke.py --base-url http://localhost:23210 \\
        --path /v1/kal/books/<id>/entities/<eid>/neighborhood --internal-token <tok> \\
        --user-id <uuid> --stranger-jwt <jwt>
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DISCRIMINATES, BLANKET, POROUS, UNSCORABLE = (
    "DISCRIMINATES", "BLANKET-REFUSAL", "POROUS", "UNSCORABLE")


def verdict(service: int, stranger: int, anon: int) -> dict:
    """Pure. Three status codes; the verdict is about whether they DIFFER correctly.

    Checked in this order on purpose: an unreachable SERVICE arm makes the other two
    meaningless, and a POROUS guard matters more than a tidy-looking refusal pair.
    """
    if not (200 <= service < 300):
        return {"verdict": UNSCORABLE, "service": service, "reason":
                "the SERVICE arm did not reach the data, so a refusal on the other arms "
                "proves nothing — a book the book-service does not know refuses EVERYONE, "
                "owner included, and that reads as a working guard"}
    if 200 <= stranger < 300:
        return {"verdict": POROUS, "stranger": stranger, "reason":
                "a JWT with NO grant on this book read it. The KAL is the security boundary "
                "on the user path — the BFF does no grant check"}
    if 200 <= anon < 300:
        return {"verdict": POROUS, "anon": anon, "reason":
                "an unauthenticated request read the data"}
    if stranger == anon:
        return {"verdict": BLANKET, "stranger": stranger, "anon": anon, "reason":
                "the guard answers the same code with and without a credential, so nothing "
                "shows the GRANT check ran. A guard rejecting on authentication alone looks "
                "identical to this, until the auth check moves"}
    return {"verdict": DISCRIMINATES, "service": service, "stranger": stranger, "anon": anon,
            "reason": "the trusted caller is let past, an authenticated stranger is refused "
                      "on the grant, and an anonymous one is refused earlier — three "
                      "outcomes, so the grant check demonstrably runs"}


def _status(url: str, headers: dict) -> int:
    req = urllib.request.Request(url)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001 — a transport failure is not a status
        return 0


def _selftest() -> int:
    cases = [
        ("200 / 403 / 401 is the shape a working guard makes",
         verdict(200, 403, 401), DISCRIMINATES),
        ("THE POROUS CASE: a stranger's 200 is the finding, whatever the anon arm says",
         verdict(200, 200, 401), POROUS),
        ("...and an anonymous 200 likewise", verdict(200, 403, 200), POROUS),
        ("BLANKET: the same refusal with and without a credential proves no grant check",
         verdict(200, 403, 403), BLANKET),
        ("...401 to both is equally blanket", verdict(200, 401, 401), BLANKET),
        ("UNSCORABLE: an unreachable SERVICE arm makes refusals meaningless",
         verdict(403, 403, 401), UNSCORABLE),
        ("...checked FIRST, so a 404 book cannot read as a working guard",
         verdict(404, 403, 401), UNSCORABLE),
        ("a transport failure on the service arm is UNSCORABLE, not a pass",
         verdict(0, 403, 401), UNSCORABLE),
        ("POROUS outranks BLANKET — a leak matters more than a tidy refusal pair",
         verdict(200, 200, 200), POROUS),
    ]
    failures = 0
    print("kal-auth-boundary-live-smoke - selftest (offline)")
    for label, got, want in cases:
        ok = got["verdict"] == want
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: expected {want}, got {got['verdict']}")
    print("\n  all checks passed" if not failures else f"\n  {failures} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--base-url", default="http://localhost:23210")
    ap.add_argument("--path", help="a KAL read path, e.g. /v1/kal/books/<id>/roster?limit=5")
    ap.add_argument("--internal-token")
    ap.add_argument("--user-id")
    ap.add_argument("--stranger-jwt")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not (args.path and args.internal_token and args.user_id and args.stranger_jwt):
        print("[kal-auth] --path, --internal-token, --user-id and --stranger-jwt are required")
        return 2

    url = f"{args.base_url.rstrip('/')}{args.path}"
    service = _status(url, {"X-Internal-Token": args.internal_token,
                            "X-User-Id": args.user_id})
    stranger = _status(url, {"Authorization": f"Bearer {args.stranger_jwt}"})
    anon = _status(url, {})
    print(f"  SERVICE  (internal token)      http {service}")
    print(f"  STRANGER (JWT, no grant)       http {stranger}")
    print(f"  ANON     (no credential)       http {anon}")

    v = verdict(service, stranger, anon)
    print("\n[kal-auth] " + json.dumps(v, ensure_ascii=False, indent=1))
    return 0 if v["verdict"] == DISCRIMINATES else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
