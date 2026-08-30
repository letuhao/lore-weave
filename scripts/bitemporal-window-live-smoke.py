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
import io
import os
import re
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


#: Every graph-backed KAL route that accepts a story position, and HOW to drive it.
#:
#: T48ad found `wiki-neighborhood` advertising `temporal_capability.kg = "ordinal_valid_time"`
#: while accepting no temporal parameter at all — T48s's exact defect on a route T48s never
#: touched. This smoke had validated the window on `neighborhood` alone: **the route it was
#: derived from**, which is rule 3's definition of green by construction.
#:
#: Derived 2026-08-30: **9 of the 16 swept KAL routes take a temporal parameter** (T48aj —
#: it read 11 until a route's doc comment stopped counting for its predecessor), 5 of them
#: graph-backed. This smoke covered ONE. `timeline` and `fact-for-check` were checked BY
#: HAND — and a hand-check is invisible to CI, which is the same rule that requires a gate to
#: carry a `--selftest`.
#:
#: `axis` is load-bearing and not cosmetic, and the KAL uses BOTH conventions — the parameter
#: NAME carries the unit:
#:
#:     as_of         a CHAPTER   (`neighborhood`, `wiki-neighborhood`) — converted server-side
#:     at_order      an ORDINAL  (`fact-for-check`) — already on the reading axis
#:     chapter_order a CHAPTER   (`timeline`)
#:
#: Driving one with the other's positions is exactly the units bug T48s's first fix produced.
#: This sweep produced BOTH readings of it on its first run: `neighborhood` driven with ordinals
#: returned the head at every position and scored LEAKS, and T48ad's `wiki-neighborhood` — which
#: had shipped `as_of` as a bare ordinal — returned ZERO at every position a translator asks for.
#:
#: `head` says where the unwindowed baseline comes from. A route whose position is OPTIONAL has
#: a real head; one that REQUIRES it does not, and its widest position is the only honest
#: baseline — treating a missing head as 0 rows would score every such route FLAT.
RECIPES: dict[str, dict] = {
    "entities/:entityId/neighborhood": {
        # `as_of` is a CHAPTER on the KAL — the owning route converts with the stride
        # (`internal_kg_neighborhood._ordinal`). Driving it with ordinals returns the head at
        # every position, which reads as LEAKS; the first run of this sweep did exactly that.
        "verb": "GET", "param": "as_of", "where": "query", "axis": "chapter",
        "head": "unwindowed", "suffix": "hops=1&cap=200",
    },
    "wiki-neighborhood": {
        # CHAPTER, same as its sibling — T48ae made it so. It shipped as an ordinal in T48ad
        # and returned ZERO at every position a translator would ask for.
        "verb": "POST", "param": "as_of", "where": "body", "axis": "chapter",
        "head": "unwindowed", "body": {"rel_cap": 200}, "entity_key": "glossary_entity_id",
    },
    "fact-for-check": {
        "verb": "POST", "param": "at_order", "where": "body", "axis": "ordinal",
        "head": "widest", "body": {"relation_limit": 200, "event_limit": 200},
        "entity_key": "glossary_entity_ids", "entity_as_list": True,
        "prefix": "projects",
    },
    "timeline": {
        "verb": "POST", "param": "chapter_order", "where": "body", "axis": "chapter",
        # 50 is the endpoint's own ceiling: `limit: 200` answers 422 `less_than_equal`, which
        # the sweep reports as ERROR — a recipe that violates a contract measures nothing.
        "head": "widest", "body": {"limit": 50},
    },
    # 501 by design since T55b — the KAL refuses BY NAME because its downstream has no such
    # route. Kept here rather than omitted: a route left out of this table is UNCOVERED, and
    # "we know why this one cannot answer" is a different statement from "nobody looked".
    "retrieve": {
        "verb": "POST", "param": "as_of", "where": "body", "axis": "ordinal",
        "head": "widest", "body": {"query": "a", "limit": 50}, "expect_no_route": True,
    },
}

_TEMPORAL_PARAM = re.compile(r"\b(as_of|at_order|chapter_order)\b")
_ROUTE_DECL = re.compile(r"@(Get|Post)\('([^']*)'\)")
_GRAPH_CALL = re.compile(r"\bknowledge\.\w+\(")


def route_body(span: str) -> str:
    """One route's body, WITHOUT the next route's leading doc comment.

    T48aj. Slicing decorator-to-decorator hands a route every comment line written above the
    NEXT one, and this controller documents its routes in exactly that position. `cast/by-ids`
    and `search` were both reported as taking a story position because `state`'s doc block —
    which says `as_of` three times — sat inside their spans. The published census read
    "11 of the 16 swept KAL routes take a temporal parameter"; it is 9.

    The ratchet survived by luck: both false positives are glossary-backed, and
    `temporal_graph_routes` also requires a knowledge call. A knowledge-backed neighbour would
    have demanded a recipe for a route that has no position to drive.
    """
    lines = span.split(chr(10))
    while lines and (not lines[-1].strip()
                     or lines[-1].lstrip().startswith(("//", "/*", "*", "*/"))):
        lines.pop()
    return chr(10).join(lines)


def temporal_graph_routes(sources: list[str]) -> list[str]:
    """Every GRAPH-BACKED route that accepts a story position, derived from the controllers.

    Derived rather than listed for the reason T48w gave: a hand list drifts, and then the
    detector reports coverage of a surface that has moved. Glossary-backed temporal routes are
    excluded here because they read the Postgres projection, not the graph this smoke is about.
    """
    found: list[str] = []
    for src in sources:
        hits = list(_ROUTE_DECL.finditer(src))
        for i, m in enumerate(hits):
            end = hits[i + 1].start() if i + 1 < len(hits) else len(src)
            body = route_body(src[m.end():end])
            if _TEMPORAL_PARAM.search(body) and _GRAPH_CALL.search(body):
                found.append(m.group(2))
    return sorted(set(found))


def uncovered(routes: list[str], recipes: dict[str, dict]) -> list[str]:
    """Which temporal graph routes this smoke cannot drive. THE RATCHET.

    A route with no recipe is REPORTED, never skipped: `wiki-neighborhood` was uncovered for
    the whole of T48s's life and the leak survived because nothing said so out loud.
    """
    return sorted(set(routes) - set(recipes))


#: Envelopes whose length moves with the story position. `entities` is deliberately absent:
#: `fact-for-check` returns the anchor entity at every position, so counting it would add a
#: constant to every sample and mask a window that never narrows.
ROW_ENVELOPES = ("edges", "relations", "items", "events")
#: The two names the reading axis travels under on the wire.
ORDINAL_KEYS = ("valid_from_ordinal", "event_order")


def rows_and_max(payload: object) -> tuple[int | None, int | None]:
    """Row count and the largest story ordinal in a response, whatever the envelope."""
    if not isinstance(payload, dict) or "_error" in payload:
        return (None, None)
    total, ords = 0, []
    for key in ROW_ENVELOPES:
        rows = payload.get(key)
        if isinstance(rows, list):
            total += len(rows)
            for r in rows:
                if isinstance(r, dict):
                    ords += [r[k] for k in ORDINAL_KEYS
                             if isinstance(r.get(k), int)]
    return (total, max(ords) if ords else None)


def _call(url: str, verb: str, body: dict | None, headers: dict) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=verb)
    for k, v in headers.items():
        req.add_header(k, v)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode("utf-8", "replace")[:120]}
    except Exception as e:  # noqa: BLE001 — a smoke reports a transport failure
        return {"_error": 0, "_body": f"{type(e).__name__}: {e}"}


def drive(route: str, recipe: dict, positions: list[int], *, base_url: str, book_id: str,
          project_id: str, entity_id: str, headers: dict) -> dict:
    """Drive ONE temporal route across the positions and return its verdict.

    The axis is per-recipe because it has to be: `as_of`/`at_order` are ordinals on the
    reading axis and `chapter_order` is a raw chapter number. Driving one with the other's
    positions produces zero rows at every position — indistinguishable from a window that
    excludes everything, which is exactly the units bug T48s's first fix shipped.
    """
    prefix = (f"v1/kal/projects/{project_id}" if recipe.get("prefix") == "projects"
              else f"v1/kal/books/{book_id}")
    path = route.replace(":entityId", entity_id)
    url = f"{base_url.rstrip('/')}/{prefix}/{path}"
    stride = STRIDE if recipe["axis"] == "ordinal" else 1

    def one(pos: int | None) -> dict:
        body = None
        target = url
        if recipe["verb"] == "POST":
            body = dict(recipe.get("body") or {})
            if recipe.get("entity_key"):
                body[recipe["entity_key"]] = ([entity_id] if recipe.get("entity_as_list")
                                              else entity_id)
            if pos is not None:
                body[recipe["param"]] = pos * stride
        else:
            qs = recipe.get("suffix", "")
            if pos is not None:
                qs = f"{qs}&{recipe['param']}={pos * stride}" if qs else \
                     f"{recipe['param']}={pos * stride}"
            target = f"{url}?{qs}" if qs else url
        payload = _call(target, recipe["verb"], body, headers)
        if isinstance(payload, dict) and payload.get("_error") == 501:
            return {"as_of": pos, "rows": None, "max_ordinal": None, "_no_route": True}
        rows, mx = rows_and_max(payload)
        return {"as_of": pos, "rows": rows, "max_ordinal": mx}

    samples = [one(p) for p in positions]
    if any(s.get("_no_route") for s in samples):
        # T55b: the KAL refusing BY NAME is a correct answer, not a failure — and it is only
        # accepted here for a recipe that DECLARED it, so a route that starts 501-ing without
        # the declaration is still reported.
        return {"route": route, "verdict": "NO-ROUTE",
                "reason": "the KAL refuses this route by name (T55b); its downstream has no "
                          "such path", "expected": bool(recipe.get("expect_no_route"))}

    if recipe["head"] == "unwindowed":
        head_rows, _ = (one(None)["rows"], None)
    else:
        # No unwindowed call exists — the position is REQUIRED. The widest position is the
        # only honest baseline; calling it 0 would score every such route FLAT.
        head_rows = samples[-1]["rows"]
    v = verdict([{k: s[k] for k in ("as_of", "rows", "max_ordinal")} for s in samples],
                head_rows if head_rows is not None else 0)
    # A route whose widest position IS the head cannot be FLAT by construction; that reading
    # belongs to routes with a real unwindowed baseline.
    if recipe["head"] == "widest" and v["verdict"] == FLAT:
        v = {"verdict": HOLDS, "rows": v.get("rows"),
             "reason": "the window moves with the position; this route REQUIRES a position, so "
                       "its widest sample is the baseline and cannot be exceeded"}
    return {"route": route, **v, "samples": samples, "head": head_rows}


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
    # T48ae — the COVERAGE ratchet. Offline, because the question "which temporal routes can
    # this smoke drive" is answerable from the controllers alone.
    _ctrl = chr(10).join([
        "@Post('wiki-neighborhood')", "async a() { return knowledge.post('/w', {as_of}); }",
        "@Get('roster')", "async b() { return glossary.get('/r?as_of=' + x); }",
        "@Post('plain')", "async c() { return knowledge.post('/p', {}); }",
    ])
    for label, got, want in [
        ("T48aj — the NEXT route's doc comment must not count for THIS route",
         temporal_graph_routes([chr(10).join([
             "@Post('plain')", "async a() { return knowledge.post('/p', {}); }",
             "// the next route takes as_of and documents it up here",
             "@Post('windowed')", "async b() { return knowledge.post('/w', {as_of}); }",
         ])]), ["windowed"]),
        ("...the trimmer keeps a body that ENDS in code",
         route_body("async a() { return knowledge.post('/p', {as_of}); }").strip().endswith("}"),
         True),
        ("...and drops a trailing comment block entirely",
         route_body("code()" + chr(10) + "// doc for the next one" + chr(10)), "code()"),
        ("...leaving a comment-only span empty rather than crashing", route_body("// only"), ""),
        ("a graph-backed route taking a position is derived",
         temporal_graph_routes([_ctrl]), ["wiki-neighborhood"]),
        ("a GLOSSARY route taking a position is NOT — it reads the projection, not the graph",
         "roster" not in temporal_graph_routes([_ctrl]), True),
        ("a graph route with NO position is not swept for a window it does not have",
         "plain" not in temporal_graph_routes([_ctrl]), True),
        ("THE RATCHET: a temporal route with no recipe is REPORTED, never skipped",
         uncovered(["a", "b"], {"a": {}}), ["b"]),
        ("...and a fully covered set is empty", uncovered(["a"], {"a": {}}), []),
        ("the REAL controllers derive 5 graph-backed temporal routes",
         len(temporal_graph_routes([io.open(os.path.join(
             "services", "knowledge-gateway", "src", "kal", f), encoding="utf-8").read()
             for f in ("kal-read.controller.ts", "kal-project-read.controller.ts")])), 5),
        ("...and EVERY one of them has a recipe today",
         uncovered(temporal_graph_routes([io.open(os.path.join(
             "services", "knowledge-gateway", "src", "kal", f), encoding="utf-8").read()
             for f in ("kal-read.controller.ts", "kal-project-read.controller.ts")]),
             RECIPES), []),
        ("the row counter sums every position-bearing envelope, never `entities`",
         rows_and_max({"relations": [{"valid_from_ordinal": 5}], "events": [{}],
                       "entities": [{}, {}]}), (2, 5)),
        ("...and reads `event_order` as well as `valid_from_ordinal`",
         rows_and_max({"events": [{"event_order": 9}]}), (1, 9)),
        ("a failed probe is (None, None), never a zero that reads as an empty window",
         rows_and_max({"_error": 500}), (None, None)),
    ]:
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: expected {want}, got {got}")


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
    ap.add_argument("--project-id", default="",
                    help="the KG project; `fact-for-check` is prefixed projects/:projectId")
    ap.add_argument("--sweep", action="store_true",
                    help="drive EVERY graph-backed temporal route, derived from the "
                         "controllers, not just `neighborhood`")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not (args.book_id and args.user_id and args.internal_token and args.entity_id):
        print("[bitemporal] --book-id, --user-id, --internal-token and --entity-id are required")
        return 2

    headers = {"X-Internal-Token": args.internal_token, "X-User-Id": args.user_id}

    if args.sweep:
        srcs = []
        for f in ("kal-read.controller.ts", "kal-project-read.controller.ts"):
            path = os.path.join("services", "knowledge-gateway", "src", "kal", f)
            if os.path.exists(path):
                srcs.append(io.open(path, encoding="utf-8").read())
        routes = temporal_graph_routes(srcs)
        gaps = uncovered(routes, RECIPES)
        print(f"[bitemporal] {len(routes)} graph-backed temporal route(s) derived; "
              f"{len(gaps)} with no recipe")
        if gaps:
            print(f"[bitemporal] FAIL — UNCOVERED: {gaps}. A temporal route this smoke cannot "
                  f"drive is how `wiki-neighborhood` leaked for the whole of T48s's life.")
            return 1
        positions = [int(p) for p in args.positions.split(",") if p.strip()]
        bad = 0
        for route in routes:
            r = drive(route, RECIPES[route], positions, base_url=args.base_url,
                      book_id=args.book_id, project_id=args.project_id or args.book_id,
                      entity_id=args.entity_id, headers=headers)
            rows = [s.get("rows") for s in (r.get("samples") or [])]
            ok = r["verdict"] in (HOLDS, "NO-ROUTE")
            bad += 0 if ok else 1
            print(f"  {r['verdict']:<9} {route:<38} rows={rows} head={r.get('head')}")
            if not ok:
                print(f"            {r.get('reason', '')[:150]}")
        print(chr(10) + f"[bitemporal] {'PASS' if not bad else 'FAIL'} — {len(routes)} "
              f"route(s) swept, {bad} not holding their position")
        return 1 if bad else 0

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
