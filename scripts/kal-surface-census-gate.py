#!/usr/bin/env python3
"""kal-surface-census-gate — hold the live sweep to a DECLARED scope, whole-KAL derived.

`kal-read-surface-live-smoke` prints `14 route(s) derived from kal-read.controller.ts`. Every
word of that is true, and read quickly it says the KAL's read surface is swept. Derived
2026-08-30:

    controller                      routes  guard                sweep
    kal-read.controller.ts             14    KalAuthGuard         SWEPT
    kal-write.controller.ts            13    InternalTokenGuard   not swept
    kal-project-read.controller.ts      2    KalAuthGuard         SWEPT (T48x)
    -------------------------------------------------------------------
                                       29                        16 swept

**Fifteen of the KAL's twenty-nine routes had no live sweep**, and the sentence that made that
invisible is a true one about a filename.

THE GUARD SORTS THE GAP, AND ONLY ONE HALF OF IT WAS DEFENSIBLE
───────────────────────────────────────────────────────────────
Thirteen of the fifteen are the write controller, and it carries `InternalTokenGuard`: **no user
can reach it at all.** That is a principled boundary for a user-facing read sweep, and it is
DERIVED from the decorator rather than argued. The other two were `kal-project-read`, which
carries `KalAuthGuard` like the swept controller does — user-reachable reads that both reach
knowledge-service, so exactly the routes a graph refactor most wants swept. **T48x closed
them**, and `user_facing_unswept` is now **0**: a CEILING that may only fall.

WHAT THE SWEPT HALF ACTUALLY PROVES ABOUT THE GRAPH
───────────────────────────────────────────────────
Of the 16 swept routes, **10 federate to glossary-service** — the Postgres SSOT projection — and
**6 reach knowledge-service** and therefore the graph store this refactor is about
(`neighborhood`, `retrieve`, `wiki-neighborhood`, `timeline`, `fact-for-check`,
`glossary-semantic`). That split is correct design, not a defect: Postgres is the SSOT and the
graph is for traversal. It does mean a green 16-route sweep is 6/16 evidence about the store
under refactor, and `architecture-live-proof`'s SURFACE leg inherits that ratio. Every KAL WRITE
forwards to glossary-service, which is the same design seen from the other side.

Measured live on iso, the ratio INVERTS: all four routes that carried rows were graph-backed and
every one of the ten glossary routes was empty, because that stack holds KG data and no glossary
projection. Which is why the census and the sweep report separate numbers — neither one alone
says what the surface proves.

So this gate does two things a sweep cannot do for itself:

  1 It derives the WHOLE KAL — every controller, every decorator, one hop through the private
    `forward` helper — and compares it against the scope the sweep DECLARES. A new controller,
    or a new route in an unswept one, reds until someone re-declares. The gap can grow, but
    never silently.
  2 It counts how many swept routes are graph-backed, so "the surface works" can never quietly
    mean "the Postgres projection works".

Usage
    python scripts/kal-surface-census-gate.py --selftest
    python scripts/kal-surface-census-gate.py
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KAL_DIR = os.path.join(ROOT, "services", "knowledge-gateway", "src", "kal")
SMOKE = os.path.join(ROOT, "scripts", "kal-read-surface-live-smoke.py")

DECLARED, DRIFTED, ERROR = "DECLARED", "DRIFTED", "ERROR"

_ROUTE = re.compile(r"@(Get|Post|Put|Patch|Delete)\(\s*['\"]([^'\"]*)['\"]")
_PREFIX = re.compile(r"@Controller\(\s*['\"]([^'\"]*)['\"]")
_DOWNSTREAM = re.compile(r"\b(glossary|knowledge|book|composition|learning|translation)\.\w+\(")
_GUARD = re.compile(r"@UseGuards\(\s*(\w+)")
_HELPER = re.compile(r"this\.(\w+)\(")

#: The guard that puts a controller on the USER path. `InternalTokenGuard` means no user can
#: reach it at all, which is why the 13 write routes sit outside a read sweep by DERIVATION
#: rather than by an excuse.
USER_GUARD = "KalAuthGuard"


def _route_body(span: str) -> str:
    """One route's body, minus the trailing comment block that documents the NEXT route."""
    lines = span.split(chr(10))
    while lines and (not lines[-1].strip()
                     or lines[-1].lstrip().startswith(("//", "/*", "*", "*/"))):
        lines.pop()
    return chr(10).join(lines)


def routes_in(src: str) -> list[dict]:
    """Every decorated route in one controller, with the downstream its body calls.

    A route's body runs to the next decorator, so the downstream attributed to it is the one it
    actually calls rather than the file's most common.
    """
    out: list[dict] = []
    prefix = _PREFIX.search(src)
    guard = _GUARD.search(src)
    hits = list(_ROUTE.finditer(src))
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(src)
        # T48aj — the next route's leading doc comment is NOT this route's body. Slicing
        # decorator-to-decorator gave `cast/by-ids` and `search` a temporal parameter they do
        # not have, because `state`'s doc block sat in their spans. Downstream attribution
        # happened to be unaffected (the same service is named either way), which is exactly
        # why it went unnoticed here and was caught in the sibling derivation.
        body = _route_body(src[m.end(): end])
        downs = set(_DOWNSTREAM.findall(body))
        # ONE hop through a private helper. Every write route forwards via `this.forward(...)`,
        # and reporting those as calling nothing reads as "these routes reach no service".
        for helper in set(_HELPER.findall(body)):
            h = re.search(r"^\s*(?:private |protected )?(?:async )?" + re.escape(helper)
                          + r"\s*\(", src, re.M)
            if h:
                downs |= set(_DOWNSTREAM.findall(src[h.end(): h.end() + 1500]))
        out.append({
            "method": m.group(1).upper(),
            "path": m.group(2),
            "prefix": prefix.group(1) if prefix else "",
            "guard": guard.group(1) if guard else "",
            "downstreams": sorted(downs),
        })
    return out


def census(kal_dir: str) -> dict[str, list[dict]]:
    """Every `*.controller.ts` under the KAL. Derived — a hand list is how the 15 went missing."""
    found = {}
    for path in sorted(glob.glob(os.path.join(kal_dir, "*.controller.ts"))):
        with open(path, encoding="utf-8") as fh:
            found[os.path.basename(path)] = routes_in(fh.read())
    return found


def declared_scope(smoke_src: str) -> dict | None:
    """The sweep's own declaration of what it covers, as a JSON literal it must keep true."""
    m = re.search(r"^SCOPE\s*=\s*(\{.*?\})\s*$", smoke_src, re.M | re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def verdict(found: dict[str, list[dict]], scope: dict | None) -> dict:
    """Pure. The derived KAL against what the sweep says it covers."""
    if not found:
        return {"verdict": ERROR, "reason":
                "no KAL controller was found — an empty derivation is never read as full "
                "coverage, which is the whole failure this gate exists for"}
    if scope is None:
        return {"verdict": ERROR, "reason":
                "the sweep declares no SCOPE, so there is nothing to hold it to"}

    swept = list(scope.get("controllers_swept") or [])
    unknown = [c for c in swept if c not in found]
    if unknown:
        return {"verdict": DRIFTED, "reason":
                f"the sweep claims controller(s) that do not exist: {unknown}"}

    total_routes = sum(len(v) for v in found.values())
    swept_routes = sum(len(found[c]) for c in swept)
    graph_backed = sum(1 for c in swept for r in found[c] if "knowledge" in r["downstreams"])
    # THE NUMBER THAT MATTERS. A route a user can reach, that reads, and that no live sweep
    # touches. The write controller falls out by its guard, not by an argument.
    user_unswept = sum(1 for c, rs in found.items() if c not in swept
                       for r in rs if r.get("guard") == USER_GUARD)
    actual = {
        "controllers_swept": sorted(swept),
        "kal_controllers_total": len(found),
        "routes_swept": swept_routes,
        "kal_routes_total": total_routes,
        "graph_backed_swept": graph_backed,
        "user_facing_unswept": user_unswept,
    }
    want = {k: (sorted(v) if isinstance(v, list) else v)
            for k, v in scope.items() if k in actual}
    drift = {k: {"declared": want.get(k), "derived": actual[k]}
             for k in actual if want.get(k) != actual[k]}
    if drift:
        return {"verdict": DRIFTED, "drift": drift, "reason":
                "the KAL's surface no longer matches what the sweep declares it covers. Update "
                "the declaration deliberately — an unswept route that appears while the number "
                "stays put is exactly how 15 of 29 went unnoticed"}
    return {"verdict": DECLARED, **actual, "unswept": total_routes - swept_routes, "reason":
            f"the sweep covers {swept_routes} of {total_routes} KAL routes and says so. "
            f"{graph_backed} swept routes reach the graph; the rest read the Postgres "
            f"projection through glossary-service. {user_unswept} route(s) a USER can reach "
            f"are still unswept — a CEILING that may only fall"}


def _ctrl(guard: str, downstream: str) -> str:
    """One synthetic controller, differing ONLY in its guard — so the selftest's guard case
    cannot pass for some other reason."""
    return chr(10).join([
        f"@UseGuards({guard})",
        "@Controller('v1/kal/x/:id')",
        "class Synthetic {",
        "  @Post('probe')",
        f"  async q() {{ return {downstream}.post('/p'); }}",
        "}",
    ])


def _selftest() -> int:
    real = census(KAL_DIR)
    with open(SMOKE, encoding="utf-8") as fh:
        real_scope = declared_scope(fh.read())

    ctrl = ("@Controller('v1/kal/books/:bookId')\nclass C {\n"
            "  @Get('roster')\n  async a() { return glossary.get('/x'); }\n"
            "  @Get('entities/:id/neighborhood')\n  async b() { return knowledge.get('/y'); }\n"
            "}\n")
    one = {"a.controller.ts": routes_in(ctrl)}
    two = dict(one, **{"b.controller.ts": routes_in(
        "@Controller('v1/kal/books/:bookId')\nclass D {\n  @Post('purge')\n  async z() {}\n}\n")})
    ok = {"controllers_swept": ["a.controller.ts"], "kal_controllers_total": 1,
          "routes_swept": 2, "kal_routes_total": 2, "graph_backed_swept": 1,
          "user_facing_unswept": 0}

    cases = [
        ("a sweep that covers the whole KAL and says so", verdict(one, ok), DECLARED),
        ("THE GAP: a second controller appears and the declaration still says 1",
         verdict(two, ok), DRIFTED),
        ("...and declaring the gap HONESTLY passes — the gap is allowed, hiding it is not",
         verdict(two, dict(ok, kal_controllers_total=2, kal_routes_total=3)), DECLARED),
        ("THE GUARD SORTS THE GAP: an unswept controller a USER can reach is counted",
         verdict(dict(one, **{"c.controller.ts": routes_in(_ctrl("KalAuthGuard", "knowledge"))}),
                 dict(ok, kal_controllers_total=2, kal_routes_total=3)), DRIFTED),
        ("...and the SAME shape behind InternalTokenGuard is NOT counted — no user reaches it",
         verdict(dict(one, **{"c.controller.ts": routes_in(
             _ctrl("InternalTokenGuard", "glossary"))}),
                 dict(ok, kal_controllers_total=2, kal_routes_total=3)), DECLARED),
        ("a route added to a SWEPT controller drifts too",
         verdict({"a.controller.ts": routes_in(ctrl.replace(
             "}\n", "  @Get('cast')\n  async c() { return glossary.get('/z'); }\n}\n"))}, ok),
         DRIFTED),
        ("THE GRAPH COUNT is asserted, so 'the surface works' cannot mean the projection does",
         verdict(one, dict(ok, graph_backed_swept=2)), DRIFTED),
        ("a claimed controller that does not exist is DRIFTED, not ignored",
         verdict(one, dict(ok, controllers_swept=["ghost.controller.ts"])), DRIFTED),
        ("NO controllers found is ERROR — an empty derivation is never full coverage",
         verdict({}, ok), ERROR),
        ("no declaration at all is ERROR, never a pass", verdict(one, None), ERROR),
        ("THE BODY PARSER attributes a downstream per ROUTE, not per file",
         [r["downstreams"] for r in one["a.controller.ts"]], [["glossary"], ["knowledge"]]),
        ("...and reads the method and path", [(r["method"], r["path"])
                                              for r in one["a.controller.ts"]],
         [("GET", "roster"), ("GET", "entities/:id/neighborhood")]),
        ("the REAL KAL parses into three controllers", sorted(real), sorted([
            "kal-project-read.controller.ts", "kal-read.controller.ts",
            "kal-write.controller.ts"])),
        ("...29 routes in total", sum(len(v) for v in real.values()), 29),
        ("...the write controller is behind InternalTokenGuard, which is why it is excluded",
         real["kal-write.controller.ts"][0]["guard"], "InternalTokenGuard"),
        ("...and the unswept project-read controller is NOT — it is user-reachable",
         real["kal-project-read.controller.ts"][0]["guard"], "KalAuthGuard"),
        ("THE HELPER HOP: a write route forwarding via `this.forward` resolves its downstream",
         real["kal-write.controller.ts"][0]["downstreams"], ["glossary"]),
        ("...and the sweep's own SCOPE parses", real_scope is not None, True),
    ]
    failures = 0
    print("kal-surface-census-gate - selftest (offline)")
    for label, got, want in cases:
        actual = got["verdict"] if isinstance(got, dict) and "verdict" in got else got
        ok_ = actual == want
        failures += 0 if ok_ else 1
        print(f"  {'PASS' if ok_ else 'FAIL'}  {label}: expected {want}, got {actual}")
    print(chr(10) + "  all checks passed" if not failures
          else chr(10) + f"  {failures} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()

    found = census(KAL_DIR)
    try:
        with open(SMOKE, encoding="utf-8") as fh:
            scope = declared_scope(fh.read())
    except OSError:
        scope = None

    swept = set((scope or {}).get("controllers_swept") or [])
    width = max((len(c) for c in found), default=10)
    for name, rs in sorted(found.items()):
        downs = sorted({d for r in rs for d in r["downstreams"]})
        mark = "SWEPT" if name in swept else "not swept"
        print(f"  {name:<{width}}  {len(rs):>2} route(s)  {mark:<9}  "
              f"-> {', '.join(downs) or '(none)'}")

    v = verdict(found, scope)
    print(f"[kal-surface-census] {v['verdict']} — {v['reason']}")
    if v["verdict"] == DRIFTED and "drift" in v:
        for k, d in v["drift"].items():
            print(f"    {k}: declared {d['declared']!r} · derived {d['derived']!r}")
    return 0 if v["verdict"] == DECLARED else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
