#!/usr/bin/env python3
"""kal-read-surface-live-smoke.py — drive EVERY KAL read route and say which ones ANSWER.

`knowledge-graph-backend-live-smoke` proves ONE engine end to end on data it writes itself.
This asks the other question: of the routes the KAL actually exposes, how many return rows —
and it asks it of **all** of them, derived from the controller rather than a hand list.

WHY DERIVED
───────────
`knowledge-http-surface-gate` already derives the federated read set from
`kal-read.controller.ts` "not hand-listed", and for the reason this file inherits: a hand list
drifts, and then the sweep reports coverage of a surface that has moved. A route added tomorrow
is swept tomorrow.

THE FOUR VERDICTS, AND WHY AN EMPTY 200 IS NOT A PASS
────────────────────────────────────────────────────
    DATA        2xx and the body carries rows
    EMPTY       2xx and the body carries none          <- NOT a pass
    NOT-FOUND   404 — the book or entity does not exist
    NO-ROUTE    501 — the KAL federates to a downstream path NOBODY BUILT (T55b)
    ERROR       5xx other than 501, or a transport failure

The distinction is the whole point and this repo has paid for it twice: `live-http sweep:
grant-404 and empty-200 read as success`, and T89's `neighborhood` shipping a 500 on AGE
because no rule ever called it. A sweep that counts 2xx counts nothing.

⚠️ **THE ROW COUNTER IS PART OF THE INSTRUMENT AND IT LIED ONCE.** Its envelope list omitted
`relations`, so `wiki-neighborhood` was reported EMPTY while the endpoint was returning a full
neighbourhood. An instrument that does not know an envelope reports the SYSTEM as empty — the
safe-looking direction, which is the dangerous one. Found by probing the endpoint directly when
its verdict disagreed with the store.

Run:
    python scripts/kal-read-surface-live-smoke.py \
        --base-url http://localhost:23210 --book-id <uuid> --user-id <uuid> \
        --internal-token <tok> --entity-id <glossary-entity-id> --min-data 3
    python scripts/kal-read-surface-live-smoke.py --selftest

`--min-data` is the CONTROL ARM: a run where nothing anywhere carried rows proves only that the
gateway is up. Without a floor, a totally cold stack reports fourteen tidy verdicts and passes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

#: Where the routes come from. Repo-relative so the sweep and the gate read the same file.
CONTROLLER = os.path.join(
    "services", "knowledge-gateway", "src", "kal", "kal-read.controller.ts")
#: BOTH user-facing read controllers. `kal-project-read` carries `KalAuthGuard` exactly as this
#: one does, and both its routes reach knowledge-service — it went unswept only because the URL
#: prefix was hardcoded to `books/:bookId`. `kal-write` stays out by its guard, not by omission:
#: `InternalTokenGuard` means no user can reach it (see SCOPE below).
PROJECT_CONTROLLER = os.path.join(
    "services", "knowledge-gateway", "src", "kal", "kal-project-read.controller.ts")
CONTROLLERS = [CONTROLLER, PROJECT_CONTROLLER]

#: WHAT THIS SWEEP COVERS, as numbers rather than a filename.
#:
#: T48w found this sweep reporting `14 route(s) derived from kal-read.controller.ts` — true, and
#: it reads as the KAL's read surface. The KAL has **29 routes across three controllers**, and
#: the 2 in `kal-project-read` were user-facing reads that both reach knowledge-service. They
#: went unswept for a mechanical reason: the URL prefix was hardcoded to `books/:bookId` and
#: theirs is `projects/:projectId`. Both are swept now, and the prefix is DERIVED per controller.
#:
#:   user_facing_unswept  **0.** The 13 write routes carry `InternalTokenGuard`, so no user
#:                        reaches them and a user-facing read sweep excludes them BY DERIVATION
#:                        from the decorator, not by an argument. A CEILING: it may only fall.
#:   graph_backed_swept   6 of the 16 swept routes reach knowledge-service and therefore the
#:                        graph (`neighborhood`, `retrieve`, `wiki-neighborhood`, `timeline`,
#:                        `fact-for-check`, `glossary-semantic`). The other 10 federate to
#:                        glossary-service, the Postgres SSOT projection. Correct design — and
#:                        it keeps "the surface works" from quietly meaning "the projection
#:                        works". Measured on iso, the live ratio inverts: every route that
#:                        carried rows was graph-backed and all 10 glossary routes were empty.
#:
#: `scripts/kal-surface-census-gate.py` holds every one of these true against the source.
SCOPE = {"controllers_swept": ["kal-read.controller.ts", "kal-project-read.controller.ts"], "kal_controllers_total": 3, "routes_swept": 16, "kal_routes_total": 29, "graph_backed_swept": 6, "user_facing_unswept": 0}

#: Envelopes a KAL body may carry its rows in. `relations` is here because leaving it out made
#: the instrument under-report — see the module docstring.
ROW_KEYS = ("items", "entities", "edges", "nodes", "results", "facts", "events", "passages",
            "cast", "roster", "hits", "timeline", "neighbors", "relations")

DATA, EMPTY, NOT_FOUND, ERROR = "DATA", "EMPTY", "NOT-FOUND", "ERROR"
#: 501 is a CORRECT answer, not a failure: the KAL now refuses by name when its
#: downstream has no such route (T55b). Counting it as ERROR would make the sweep red
#: for the gateway telling the truth — and the previous behaviour, forwarding the
#: framework's 404, was the thing that scored GREEN.
NO_ROUTE = "NO-ROUTE"


def derive_routes(controller_path: str) -> list[tuple[str, str, str]]:
    """Every `@Get('…')` / `@Post('…')` on a KAL read controller, in declaration order.

    Returns the controller's `@Controller('…')` PREFIX alongside each route. The two read
    controllers sit on different prefixes — `v1/kal/books/:bookId` and
    `v1/kal/projects/:projectId` — and hardcoding the first is what kept the second unswept.
    """
    src = open(controller_path, encoding="utf-8").read()
    prefix = re.search(r"@Controller\('([^']*)'\)", src)
    return [(m.group(1).upper(), m.group(2), prefix.group(1) if prefix else "")
            for m in re.finditer(r"@(Get|Post)\('([^']*)'\)", src)]


def route_url(base_url: str, prefix: str, tmpl: str, *, entity: str, book_id: str,
              project_id: str, query: str = "") -> str:
    """Build one route's URL from ITS controller's prefix. Pure, so the selftest can drive it.

    Extracted because BITE T48x-1 showed the failure mode of getting this wrong is INVISIBLE:
    address a `projects/:projectId` route under `books/:bookId` and it answers 404, which the
    sweep reads as NOT-FOUND — "the book or entity does not exist" — and still reports PASS.
    A sweep can then claim 16 routes while two of them were never reached. So the mapping from
    prefix to URL is asserted offline rather than trusted.
    """
    base = prefix.replace(":bookId", book_id).replace(":projectId", project_id)
    return f"{base_url.rstrip('/')}/{base}/{tmpl.replace(':entityId', entity)}{query}"


def unfillable(routes: list[tuple[str, str, str]], book_id: str, project_id: str) -> list[str]:
    """Which `:placeholder` a run has no value for. Pure, so the selftest can drive it.

    T48y: `route_url` used to fall back to the BOOK id for `:projectId`, and
    `architecture-live-proof` calls this sweep with no `--project-id` at all. The downstream
    answered `project not found`, the sweep read that as NOT-FOUND — a legitimate verdict for a
    cold stack — and PASSED at exit 0. A wrong-typed id produces a PLAUSIBLE refusal, which is
    the dangerous kind. So a run that cannot address a route refuses to pretend it swept it.
    """
    have = {":bookId": book_id, ":projectId": project_id}
    return sorted({ph for _v, _t, prefix in routes for ph, val in have.items()
                   if ph in prefix and not val})


def rows_in(payload: object) -> int:
    """How many result rows a body carries, whatever the envelope calls them."""
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0
    for key in ROW_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            return len(value["items"])
    return 1 if any(k in payload for k in ("entity_id", "id", "canonical")) else 0


def verdict_for(status: int, rows: int) -> str:
    """Status + row count -> one of the four readings. Pure, so the selftest can drive it."""
    if status == 501:
        return NO_ROUTE
    if status == 0 or status >= 500:
        return ERROR
    if status == 404:
        return NOT_FOUND
    if 200 <= status < 300:
        return DATA if rows else EMPTY
    return f"HTTP-{status}"


def _call(url: str, verb: str, body: dict | None, headers: dict) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=verb)
    for k, v in headers.items():
        req.add_header(k, v)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, raw[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]
    except Exception as e:  # noqa: BLE001 — a smoke must report a transport failure, not raise
        return 0, f"{type(e).__name__}: {e}"


def _selftest() -> int:
    """The readings and the row counter, on cases a live stack cannot produce on demand."""
    cases = [
        ("a 200 carrying rows is DATA", verdict_for(200, 3), DATA),
        ("a 200 carrying NONE is EMPTY, not a pass", verdict_for(200, 0), EMPTY),
        ("a 404 is NOT-FOUND, never EMPTY", verdict_for(404, 0), NOT_FOUND),
        ("a 500 is ERROR", verdict_for(500, 0), ERROR),
        ("a 501 is NO-ROUTE — the KAL refusing by name, not a failure",
         verdict_for(501, 0), NO_ROUTE),
        ("...and NO-ROUTE is NOT ERROR, so a truthful refusal does not redden the sweep",
         verdict_for(501, 0) != ERROR, True),
        ("a transport failure is ERROR", verdict_for(0, 0), ERROR),
        ("a 400 keeps its own status rather than becoming EMPTY",
         verdict_for(400, 0), "HTTP-400"),
    ]
    counts = [
        ("a bare list counts its length", rows_in([1, 2, 3]), 3),
        ("`items` is counted", rows_in({"items": [1, 2]}), 2),
        ("`edges` is counted", rows_in({"edges": [1]}), 1),
        ("`relations` is counted — the envelope that was MISSING",
         rows_in({"found": True, "relations": [1, 2, 3, 4]}), 4),
        ("a nested `items` is counted", rows_in({"results": {"items": [1, 2, 3]}}), 3),
        ("an empty envelope is ZERO, not one", rows_in({"items": []}), 0),
        ("a bare object with an identity is one row", rows_in({"entity_id": "e"}), 1),
        ("an object with no identity and no envelope is zero", rows_in({"ok": True}), 0),
    ]
    failures = 0
    print("kal-read-surface-live-smoke - selftest (offline)")
    for label, got, want in cases + counts:
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: expected {want}, got {got}")

    routes = [r for c in CONTROLLERS if os.path.exists(c) for r in derive_routes(c)]
    ok = len(routes) >= 16
    failures += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  BOTH user-facing controllers still parse "
          f"({len(routes)} route(s) derived)")
    # The prefix must come from the controller, or the project routes are addressed
    # under `books/:bookId` and 404 as though they had been swept.
    prefixes = sorted({r[2] for r in routes})
    ok = prefixes == ["v1/kal/books/:bookId", "v1/kal/projects/:projectId"]
    failures += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  each route carries its OWN prefix: {prefixes}")
    # ...and that the prefix is actually USED. BITE T48x-1: addressed under the wrong prefix
    # both project routes 404, which reads as NOT-FOUND and still PASSES.
    for label, routes_, bid, pid, want in [
        ("a run with both ids can address everything",
         [("GET", "roster", "v1/kal/books/:bookId")], "B", "P", []),
        ("THE REFUSAL: a project route with no --project-id is unfillable, never book-id'd",
         [("POST", "fact-for-check", "v1/kal/projects/:projectId")], "B", "", [":projectId"]),
        ("...and a book route is unaffected by a missing project id",
         [("GET", "roster", "v1/kal/books/:bookId")], "B", "", []),
        ("both missing are both named",
         [("GET", "a", "v1/kal/books/:bookId"), ("POST", "b", "v1/kal/projects/:projectId")],
         "", "", [":bookId", ":projectId"]),
    ]:
        got = unfillable(routes_, bid, pid)
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: expected {want}, got {got}")
    for label, prefix, tmpl, want in [
        ("a books route addresses /books/", "v1/kal/books/:bookId", "roster", "/v1/kal/books/B/"),
        ("THE BITE, caught offline: a projects route addresses /projects/, never /books/",
         "v1/kal/projects/:projectId", "fact-for-check", "/v1/kal/projects/P/"),
        (":entityId is substituted, not left literal", "v1/kal/books/:bookId",
         "entities/:entityId/facts", "/entities/E/facts"),
    ]:
        got = route_url("http://h", prefix, tmpl, entity="E", book_id="B", project_id="P")
        ok = want in got
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got}")
    # A floor that cannot fail is not a floor.
    ok = _passes_floor({DATA: 0}, 1) is False and _passes_floor({DATA: 3}, 3) is True
    failures += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  --min-data actually gates a cold run")

    print(chr(10) + "  all checks passed" if not failures else chr(10) + f"  {failures} FAILED")
    return 1 if failures else 0


def _passes_floor(tally: dict, floor: int) -> bool:
    return tally.get(DATA, 0) >= floor


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--base-url", default="http://localhost:23210")
    ap.add_argument("--book-id")
    ap.add_argument("--user-id")
    ap.add_argument("--internal-token")
    ap.add_argument("--entity-id", default="", help="a GLOSSARY entity id with neighbours")
    ap.add_argument("--controller", default=",".join(CONTROLLERS),
                    help="comma-separated; both user-facing read controllers")
    ap.add_argument("--project-id", default="",
                    help="for the `projects/:projectId` controller; the KG project, "
                         "which is NOT the book id")
    ap.add_argument("--min-data", type=int, default=1,
                    help="routes that must carry rows; the control arm")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    for required in ("book_id", "user_id", "internal_token"):
        if not getattr(args, required):
            print(f"[kal-smoke] --{required.replace('_', '-')} is required")
            return 2

    headers = {"X-Internal-Token": args.internal_token, "X-User-Id": args.user_id}
    entity = args.entity_id or "unknown"
    bodies = {
        "cast/by-ids": {"entity_ids": [entity]},
        "retrieve": {"query": "a", "limit": 5},
        "wiki-neighborhood": {"user_id": args.user_id, "glossary_entity_id": entity,
                              "rel_cap": 10},
        "timeline": {"chapter_order": 10, "limit": 5},
        # kal-project-read. Both reach knowledge-service; `at_order` is on the reading axis
        # (chapter x 1_000_000), not a raw chapter number -- the units bug T48s paid for.
        "fact-for-check": {"glossary_entity_ids": [entity], "at_order": 10_000_000,
                           "relation_limit": 5, "event_limit": 5},
        "glossary-semantic": {"query": "a", "max_entities": 5},
    }
    query = {"roster": "?limit=5", "cast": "?limit=5", "search": "?q=a&limit=5",
             "state": "?as_of=10", "entities/:entityId/neighborhood": "?hops=1&cap=10",
             "entities/:entityId/facts": "?limit=5",
             "entities/:entityId/attr-values": "?attr=title&limit=5"}

    paths = [p for p in args.controller.split(",") if p.strip()]
    routes = [r for p in paths for r in derive_routes(p)]
    missing = unfillable(routes, args.book_id, args.project_id)
    if missing:
        print(f"[kal-smoke] REFUSED — {len(routes)} route(s) are in scope but this run has no "
              f"value for {', '.join(missing)}. Substituting another id makes the route answer "
              f"a plausible 404 that reads as NOT-FOUND and PASSES; a sweep that cannot address "
              f"a route must not report it as swept.")
        return 2
    print(f"[kal-smoke] {len(routes)} route(s) derived from "
          f"{', '.join(os.path.basename(p) for p in paths)}")
    tally: dict[str, int] = {}
    for verb, tmpl, prefix in routes:
        url = route_url(args.base_url, prefix, tmpl, entity=entity, book_id=args.book_id,
                        project_id=args.project_id, query=query.get(tmpl, ""))
        status, payload = _call(url, verb, bodies.get(tmpl) if verb == "POST" else None, headers)
        rows = rows_in(payload) if 200 <= status < 300 else 0
        got = verdict_for(status, rows)
        tally[got] = tally.get(got, 0) + 1
        note = f"{rows} row(s)" if got == DATA else (
            str(payload)[:70] if got in (ERROR, NOT_FOUND) or got.startswith("HTTP") else "")
        print(f"  {got:<9} {status:>3}  {verb:<4} {tmpl:<42} {note}")

    print("\n[kal-smoke] " + "  ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    if tally.get(ERROR):
        print(f"[kal-smoke] FAIL — {tally[ERROR]} route(s) ERRORED")
        return 1
    if not _passes_floor(tally, args.min_data):
        print(f"[kal-smoke] FAIL — only {tally.get(DATA, 0)} route(s) carried rows, floor is "
              f"{args.min_data}. A sweep where nothing answers proves the gateway is up and "
              f"nothing else.")
        return 1
    print(f"[kal-smoke] PASS — {tally.get(DATA, 0)} route(s) carried rows, no route errored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
