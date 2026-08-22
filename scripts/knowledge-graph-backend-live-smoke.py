#!/usr/bin/env python3
"""knowledge-graph-backend-live-smoke.py — prove the knowledge HTTP surface on ONE graph engine.

Drives a RUNNING knowledge-service end-to-end and asserts the reader surface actually
answers from whichever engine `KNOWLEDGE_GRAPH_BACKEND` selected. It writes through the
repo layer (`/internal/knowledge/enriched-writeback`) and reads back through BOTH halves —
the `GraphStore` port (`/internal/knowledge/wiki-neighborhood`) and the repo layer's own
reader routes — so a run that passes is a run in which one store served both.

WHY LIVE, AND WHY THIS SHAPE
────────────────────────────
T89 is the argument. `GraphStore.neighborhood` raised `ValidationError` on EVERY AGE call
and shipped that way: 4336 unit tests, 634 DB integration tests and a conformance suite
parameterised over four adapters were all green, because no rule and no test ever called
it. The first thing that did was a live HTTP request, which returned 500.

So the thing worth automating is not "does the suite pass" but "does a real request reach
a real engine and come back with the row we put in".

THE THREE WAYS THIS PROBE COULD LIE, AND WHAT STOPS EACH
───────────────────────────────────────────────────────
Every one of these was walked into BY HAND during T90's sweep, which is why they are
mechanised rather than remembered:

  1. `200` with an empty body.  A project with no data answers `{"nodes": []}` on any
     engine, including one that is not being consulted at all. A probe marked
     `expect_marker` must find the entity it wrote; `200` alone never satisfies it.

  2. The grant `404`.  `app/auth/grant_deps._not_found()` returns `{"detail": "not found"}`
     BEFORE the graph is touched — deliberately, so a project's existence never leaks. It
     is indistinguishable from success if you only read the status code, and five endpoints
     in the hand sweep were counted as fine while they had short-circuited at authorization.
     It is a HARD FAIL here, never a skip.

  3. Every probe empty.  If no probe anywhere carried data, the surface answered nothing
     and the run proves nothing — even at 100% `2xx`. That is the CONTROL ARM (NV-7): a
     check that fires on everything tells you nothing by firing. `--min-data` is its floor.

Run:
    python scripts/knowledge-graph-backend-live-smoke.py \
        --base-url http://localhost:28216 --expect-backend age
    python scripts/knowledge-graph-backend-live-smoke.py --selftest

`--expect-backend` is not decoration: it is compared against the value the container
reports, so pointing this at a stack that quietly fell back to the other engine FAILS
rather than passing for the wrong reason.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

GRANT_404_BODY = "not found"


# ── the pure half: verdicts over (status, payload), so --selftest can drive them ────────


def evaluate(probe: dict, status: int, payload) -> tuple[bool, str]:
    """`(ok, reason)` for one probe's response. NO I/O — this is what the selftest drives.

    Kept pure on purpose. A smoke whose judgement lives inside the request loop can only be
    validated by standing up a broken service, so in practice it never is, and the judgement
    is the part most likely to be wrong.
    """
    if status == 404 and _detail_of(payload) == GRANT_404_BODY:
        return False, (
            "grant-404: the request was refused at authorization and never reached the "
            "graph. This is the failure that reads as success — see the module docstring."
        )
    if status != probe.get("expect_status", 200):
        return False, f"HTTP {status} (wanted {probe.get('expect_status', 200)})"
    marker = probe.get("expect_marker")
    if marker is None:
        return True, "2xx"
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    if marker not in body:
        return False, (
            f"200 but the marker {marker!r} is absent — the endpoint answered without the "
            f"row this smoke wrote, so nothing proves the engine was consulted"
        )
    return True, f"2xx + {marker!r}"


def _detail_of(payload) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
        return payload["detail"]
    return None


def verdict(results: list[dict], min_data: int) -> tuple[bool, str]:
    """The CONTROL ARM. All-green is not a pass if nothing carried data.

    A surface with no rows in it returns `200 []` from every read on every engine — and on
    an engine that is not wired at all. Without this floor the smoke's headline number is
    reachable by a service talking to an empty store, which is precisely the state a broken
    cutover leaves behind.
    """
    failed = [r for r in results if not r["ok"]]
    carried = sum(1 for r in results if r["ok"] and r["probe"].get("expect_marker"))
    if failed:
        return False, f"{len(failed)} probe(s) failed"
    if carried < min_data:
        return False, (
            f"every probe was 2xx and only {carried} carried DATA (floor {min_data}). "
            f"An empty store answers 2xx on any engine, including one nothing is reading. "
            f"This is a vacuous green, not a pass."
        )
    return True, f"{len(results)} probe(s), {carried} carrying data"


# ── the live half ───────────────────────────────────────────────────────────────────────


def _req(url: str, *, headers: dict, body=None, method=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    for k, v in headers.items():
        r.add_header(k, v)
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, _maybe_json(raw)
    except urllib.error.HTTPError as e:
        return e.code, _maybe_json(e.read().decode("utf-8", "replace"))
    except Exception as e:                                    # noqa: BLE001
        return 0, {"detail": f"transport: {e}"}


def _maybe_json(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _mint_jwt(secret: str, user_id: str) -> str:
    import jwt                                                # PyJWT, already a service dep
    now = int(time.time())
    return jwt.encode({"sub": user_id, "user_id": user_id, "iat": now, "exp": now + 3600},
                      secret, algorithm="HS256")


def run(args) -> int:
    base = args.base_url.rstrip("/")
    internal = {"X-Internal-Token": args.internal_token}
    user_id = str(uuid.uuid4())
    bearer = {"Authorization": f"Bearer {_mint_jwt(args.jwt_secret, user_id)}"}

    # ── the engine must be the one we were told to prove ────────────────────────────────
    #
    # Checked, not assumed. Without this the smoke passes against a stack running the OTHER
    # engine and prints the engine it was ASKED about in its headline — a green that names
    # the wrong thing, which is worse than a red. `/health` reports `graph_backend` from
    # `configured_backend()` so the answer comes from the same place the adapters read.
    st, health = _req(f"{base}/health", headers={})
    if st != 200 or not isinstance(health, dict):
        print(f"[graph-backend-smoke] FAIL — the service is not answering ({st}): {health}")
        return 1
    running = health.get("graph_backend")
    if running is None:
        print("[graph-backend-smoke] FAIL — /health does not report `graph_backend`, so "
              "--expect-backend cannot be verified and a green would name an engine this "
              "run never confirmed. Deploy a build that reports it.")
        return 1
    if running != args.expect_backend:
        print(f"[graph-backend-smoke] FAIL — asked to prove {args.expect_backend!r} but the "
              f"service is running {running!r}. Every probe below would have passed and "
              f"attributed the result to the wrong engine.")
        return 1
    print(f"[graph-backend-smoke] backend confirmed from /health: {running!r}")

    # ── setup: a real project row, or every read 404s at the grant check ────────────────
    st, proj = _req(f"{base}/v1/knowledge/projects", headers=bearer,
                    body={"name": "graph-backend live smoke", "project_type": "book"})
    if st != 201 or not isinstance(proj, dict) or "project_id" not in proj:
        print(f"[graph-backend-smoke] FAIL — could not create the project ({st}): {proj}")
        return 1
    project_id = proj["project_id"]

    # ── the write, through the REPO LAYER ───────────────────────────────────────────────
    glossary_id = str(uuid.uuid4())
    run_tag = uuid.uuid4().hex[:6]
    name = f"Smoke Entity {run_tag}"
    st, wb = _req(f"{base}/internal/knowledge/enriched-writeback", headers=internal, body={
        "user_id": user_id, "project_id": project_id, "proposal_id": str(uuid.uuid4()),
        "glossary_entity_id": glossary_id, "canonical_name": name, "entity_kind": "person",
        "technique": "livesmoke",
        "facts": [{"dimension": "attribute", "content": f"{name} exists.",
                   "confidence": 0.72}],
    })
    if st != 200:
        print(f"[graph-backend-smoke] FAIL — the repo-layer write did not land ({st}): {wb}")
        return 1

    # ── the reads. `expect_marker` is what separates a real answer from an empty one. ────
    # ── the WORKLOAD half (T93) ──────────────────────────────────────────────────────────
    #
    # T90 shipped this smoke with a stated gap: "eight probes are a read surface, not a
    # workload: no extraction run, no relation edges, no cross-chapter window." Everything
    # above writes ONE anchored entity through `enriched-writeback`. This drives the path
    # extraction itself uses — `persist-pass2`, the one call that lands entities, relations,
    # events and evidence together — so the smoke exercises what the architecture is FOR
    # rather than only what it serves.
    #
    # No LLM: the candidates are supplied, which is exactly the seam `persist-pass2` exposes.
    import hashlib

    def _cid(n: str) -> str:
        return hashlib.sha256(f"{user_id}:{n}".encode()).hexdigest()[:32]

    a, b = f"Corvin {run_tag}", f"Lyra {run_tag}"
    ev_title = f"The oath at {run_tag}"
    st, p2 = _req(f"{base}/internal/extraction/persist-pass2", headers=internal, body={
        "user_id": user_id, "project_id": project_id, "source_type": "chapter",
        "source_id": str(uuid.uuid4()), "job_id": str(uuid.uuid4()),
        "extraction_model": "live-smoke",
        "entities": [
            {"name": n, "kind": "character", "aliases": [], "confidence": 0.9,
             "canonical_name": n.lower(), "canonical_id": _cid(n)} for n in (a, b)
        ],
        "relations": [{"subject": a, "predicate": "ally_of", "object": b,
                       "polarity": "positive", "modality": "asserted", "confidence": 0.88,
                       "subject_id": _cid(a), "object_id": _cid(b), "relation_id": None}],
        "events": [{"name": ev_title, "kind": "scene", "participants": [a, b],
                    "participant_ids": [_cid(a), _cid(b)], "location": None,
                    "time_cue": None, "summary": "Two allies swore an oath.",
                    "confidence": 0.8, "event_id": None}],
        "facts": [], "chapter_index": 7, "provenance": "human_authored",
        "writer_autocreate": True,
    })
    if st != 200:
        print(f"[graph-backend-smoke] FAIL — the extraction write path did not land ({st}): {p2}")
        return 1
    # ⚠️ Assert the COUNTS, not just the 200. `persist-pass2` returns a summary, and a write
    # that merged nothing returns 200 with zeroes — which would make every probe below pass
    # against an empty graph and prove exactly nothing.
    for field, want in (("entities_merged", 2), ("relations_created", 1), ("events_merged", 1)):
        if p2.get(field) != want:
            print(f"[graph-backend-smoke] FAIL — extraction wrote {field}={p2.get(field)}, "
                  f"expected {want}. A 200 with zeroes is a write that did nothing.")
            return 1

    probes = [
        {"name": "port: wiki-neighborhood", "method": "POST",
         "path": "/internal/knowledge/wiki-neighborhood", "auth": "internal",
         "body": {"user_id": user_id, "glossary_entity_id": glossary_id, "rel_cap": 10},
         "expect_marker": name,
         "why": "the GraphStore PORT — the half that returned 500 on AGE (T89)"},
        {"name": "repo: entity list", "path": f"/v1/knowledge/entities?project_id={project_id}",
         "auth": "bearer", "expect_marker": name,
         "why": "the reader's main surface, and T87's spoiler-window comprehension"},
        {"name": "repo: entity statuses",
         "path": f"/v1/knowledge/entities/statuses?project_id={project_id}",
         "auth": "bearer", "expect_marker": "active",
         "why": "status_at_order's fail-OPEN — T89 found the fake omitting the key"},
        {"name": "repo: project subgraph",
         "path": f"/v1/knowledge/projects/{project_id}/subgraph", "auth": "bearer",
         "expect_marker": name, "why": "entities AND edges in one projection"},
        {"name": "repo: graph stats",
         "path": f"/v1/knowledge/projects/{project_id}/graph-stats", "auth": "bearer",
         "why": "counts by label — past the grant check, so a 404 here is the trap"},
        {"name": "kg: project graph", "path": f"/v1/kg/projects/{project_id}/graph",
         "auth": "bearer", "why": "the graph view the FE renders"},
        {"name": "kg: observed schema",
         "path": f"/v1/kg/projects/{project_id}/schema/observed", "auth": "bearer",
         "why": "an aggregate over labels — the construct family AGE differs on"},
        {"name": "repo: timeline", "path": f"/v1/knowledge/timeline?project_id={project_id}",
         "auth": "bearer", "why": "events_page through the port"},
        # ── the workload's own read-back (T93) ───────────────────────────────────────────
        {"name": "workload: entity list", "auth": "bearer",
         "path": f"/v1/knowledge/entities?project_id={project_id}&limit=50",
         "expect_marker": a,
         "why": "an entity the EXTRACTION path wrote, not the enrichment one"},
        {"name": "workload: subgraph edge", "auth": "bearer",
         "path": f"/v1/knowledge/projects/{project_id}/subgraph",
         "expect_marker": "ally_of",
         "why": "the RELATION — T90 had no edge in it at all"},
    ]

    results = []
    for p in probes:
        headers = internal if p["auth"] == "internal" else bearer
        st, payload = _req(f"{base}{p['path']}", headers=headers,
                           body=p.get("body"), method=p.get("method"))
        ok, reason = evaluate(p, st, payload)
        results.append({"probe": p, "ok": ok, "reason": reason})
        print(f"  {'OK  ' if ok else 'FAIL'}  {p['name']:28} {reason}")
        if not ok:
            print(f"        why it matters: {p['why']}")

    ok, summary = verdict(results, args.min_data)
    print(f"\n[graph-backend-smoke] {'PASS' if ok else 'FAIL'} — backend "
          f"{args.expect_backend!r}: {summary}")
    return 0 if ok else 1


# ── selftest ────────────────────────────────────────────────────────────────────────────


def selftest() -> int:
    """Drives the two pure functions. Required because a hand-run is invisible to CI, and
    because every case below is a way this smoke could report PASS while proving nothing."""
    ok = True

    def check(label, got, want):
        nonlocal ok
        if got != want:
            print(f"  FAIL  {label}: expected {want}, got {got}")
            ok = False
        else:
            print(f"  PASS  {label}")

    marker = {"name": "p", "expect_marker": "Aurelia", "why": "w"}
    plain = {"name": "p", "why": "w"}

    check("a 200 carrying the marker passes",
          evaluate(marker, 200, {"name": "Aurelia Vane"})[0], True)
    # The empty-200. This is what a service reading NO store returns.
    check("a 200 WITHOUT the marker fails",
          evaluate(marker, 200, {"entities": []})[0], False)
    check("a probe with no marker is satisfied by 2xx",
          evaluate(plain, 200, {"nodes": []})[0], True)
    # The grant-404 — indistinguishable from success by status code alone.
    got, why = evaluate(plain, 404, {"detail": "not found"})
    check("the grant-404 is a HARD FAIL, not a skip", got, False)
    check("...and it says so by name", "grant-404" in why, True)
    # A 404 that is NOT the grant one must not be mislabelled as it.
    check("an ordinary 404 is a plain status failure",
          "grant-404" in evaluate(plain, 404, {"detail": "project not found"})[1], False)
    check("a 500 fails", evaluate(plain, 500, {"detail": "internal server error"})[0], False)
    # A string body must not crash the marker search — the surface returns text on some paths.
    check("a non-JSON body is searched, not crashed",
          evaluate(marker, 200, "<html>Aurelia Vane</html>")[0], True)

    # ── the control arm ────────────────────────────────────────────────────────────────
    all_green_no_data = [{"probe": plain, "ok": True, "reason": "2xx"} for _ in range(8)]
    got, why = verdict(all_green_no_data, min_data=1)
    check("8 green probes carrying NO data is NOT a pass", got, False)
    check("...and it says the green was vacuous", "vacuous" in why, True)
    check("one probe carrying data clears the floor",
          verdict(all_green_no_data + [{"probe": marker, "ok": True, "reason": "2xx"}],
                  min_data=1)[0], True)
    check("a failed probe fails the run even with data",
          verdict([{"probe": marker, "ok": True, "reason": ""},
                   {"probe": plain, "ok": False, "reason": ""}], min_data=1)[0], False)
    # Validated on a case it was NOT derived from: the floor is a floor, not a flag.
    check("a floor of 2 is not met by one data probe",
          verdict(all_green_no_data + [{"probe": marker, "ok": True, "reason": ""}],
                  min_data=2)[0], False)

    print(f"\n[graph-backend-smoke] SELFTEST {'PASS' if ok else 'FAIL'} — distinguishes an "
          f"empty 200 from a real answer, a grant-404 from an ordinary one, and an "
          f"all-green run that proves nothing from one that does")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default="http://localhost:28216")
    ap.add_argument("--internal-token")
    ap.add_argument("--jwt-secret")
    ap.add_argument("--expect-backend", default="age", choices=["age", "neo4j"])
    ap.add_argument("--min-data", type=int, default=4,
                    help="probes that must carry a written row, not merely answer 2xx")
    ap.add_argument("--selftest", action="store_true", help="prove this smoke can go red")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.internal_token or not args.jwt_secret:
        print("[graph-backend-smoke] FAIL — --internal-token and --jwt-secret are required "
              "for a live run (read them off the running container).")
        return 2
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
