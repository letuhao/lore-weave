#!/usr/bin/env python3
"""Live round-trip proof for the composition `*_edit` atom families — atom-edit F2.

F2's real column is *real-run proven?* and it has been empty for all 11 families. The
three static gates the track built (per-family delete contract, `fe-door-scan.py`,
derived round-trip preservation) prove shape, reachability and preservation — they do NOT
prove an edit reaching the row, and the checklist's own evidence rule says a unit test
does not tick that box. Substituting gates for it was caught once already, by the human.

So this is the missing thing, as a SCRIPT rather than a transcript: re-runnable, and it
counts out loud.

**It reports N of 11 and names the pending ones.** A harness that walks 4 families and
prints "OK" is the silent-cap failure the same board punishes elsewhere — `cold-path-smoke`
reported 10/10 while never running the `world` pass at all. The families needing a Work /
outline fixture are enumerated as PENDING with the fixture they want, so the gap is a line
of output, never an absence.

Per family the shape is the same, and DELETE-first on purpose: delete/archive is the op
that failed silently on four of six PlanForge kinds (B6), so it is the one worth proving.

    CREATE  → read back, assert present
    PATCH   → read back, assert the field actually changed
    DELETE  → read back, assert GONE (not merely "no error")

Usage:
    python scripts/atom-edit-roundtrip.py               # run the implemented families
    python scripts/atom-edit-roundtrip.py --only motif
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
# `cold-path-smoke.py` is not an importable module name (hyphens), so the primitives are
# loaded by path rather than re-implemented — one HTTP/auth shape for both harnesses.
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "cps", str(pathlib.Path(__file__).resolve().parent / "cold-path-smoke.py"))
cps = _ilu.module_from_spec(_spec)          # type: ignore[arg-type]
_spec.loader.exec_module(cps)               # type: ignore[union-attr]

call, ok, Failed = cps.call, cps.ok, cps.Failed


def call_ifmatch(method: str, path: str, body: dict, token: str, version: int):
    """`call` with an `If-Match` header. Optimistic concurrency on these routes is a
    HEADER, not a query param — the first run of this harness sent `?expected_version=`
    and read the resulting 412 as a product bug. It was mine."""
    import json as _j, urllib.error, urllib.request
    req = urllib.request.Request(
        cps.GATEWAY + path, data=_j.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}",
                 "If-Match": str(version)},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (_j.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, _j.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:300].decode(errors="replace")}
C = "/v1/composition"

#: Every family F2 tracks, and how it is proven. A family without a `fn` is PENDING and
#: says which fixture it is waiting on — never omitted, so the count cannot lie.
PENDING_FIXTURE = {
    "canon_rule":         "a Work (project_id)",
    "outline_node":       "a Work + a structure",
    "scene_link":         "two outline nodes",
    "motif_bind":         "a Work + a chapter node",
    "entity_override":    "a derivative Work",
    "derivative":         "a Work with a knowledge project",
    "authoring_run":      "a book with chapters",
}


def _login() -> str:
    st, body = call("POST", "/v1/auth/login",
                    {"email": cps.EMAIL, "password": cps.PASSWORD})
    return ok("login", st, body, 200)["access_token"]


def _code(kind: str) -> str:
    return f"smoke.f2_{kind}_{uuid.uuid4().hex[:8]}"


# ── families ───────────────────────────────────────────────────────────────
def f_motif(t: str) -> str:
    code = _code("motif")
    st, m = call("POST", f"{C}/motifs", {
        "code": code, "name": "F2 Probe", "original_language": "en",
        "kind": "sequence", "summary": "a probe row for the F2 round-trip",
        "beats": [{"key": "one", "label": "First", "intent": "it begins",
                   "tension_target": 2, "order": 1}],
    }, t)
    mid = ok("motif.create", st, m, 201)["id"]

    st, got = call("GET", f"{C}/motifs/{mid}", None, t)
    assert ok("motif.read", st, got, 200)["code"] == code, "created row not readable"

    st, p = call_ifmatch("PATCH", f"{C}/motifs/{mid}",
                         {"summary": "edited by the F2 probe"}, t, got["version"])
    ok("motif.patch", st, p, 200)
    st, got2 = call("GET", f"{C}/motifs/{mid}", None, t)
    assert "F2 probe" in ok("motif.reread", st, got2, 200)["summary"], \
        "PATCH returned 200 and the row did not change"

    st, d = call("DELETE", f"{C}/motifs/{mid}", None, t)
    ok("motif.delete", st, d, 200)
    st, after = call("GET", f"{C}/motifs/{mid}", None, t)
    # archive is a SOFT delete — proven by the status flip, not by a 404.
    assert st == 404 or after.get("status") == "archived", \
        f"DELETE returned 200 and the row is still active: {after.get('status')}"
    return f"created+patched+archived {code}"


def f_motif_link(t: str) -> str:
    ids = []
    for n in (1, 2):
        st, m = call("POST", f"{C}/motifs", {
            "code": _code(f"link{n}"), "name": f"F2 Link {n}",
            "original_language": "en", "kind": "sequence", "summary": "link probe",
        }, t)
        ids.append(ok(f"link.motif{n}", st, m, 201)["id"])

    st, l = call("POST", f"{C}/motifs/{ids[0]}/links",
                 {"to_motif_id": ids[1], "kind": "precedes"}, t)
    lid = ok("link.create", st, l, 201).get("id") or l.get("link_id")

    st, rows = call("GET", f"{C}/motifs/{ids[0]}/links", None, t)
    got = ok("link.read", st, rows, 200)
    assert any(r.get("neighbor_id") == ids[1] for r in got.get("links", got if isinstance(got, list) else [])), \
        "the edge does not come back on the read"

    st, d = call("DELETE", f"{C}/motif-links/{lid}", None, t)
    ok("link.delete", st, d, 200)
    st, rows2 = call("GET", f"{C}/motifs/{ids[0]}/links", None, t)
    after = ok("link.reread", st, rows2, 200)
    assert not any(r.get("neighbor_id") == ids[1]
                   for r in after.get("links", after if isinstance(after, list) else [])), \
        "DELETE returned 200 and the edge is still there"

    for mid in ids:
        call("DELETE", f"{C}/motifs/{mid}", None, t)
    return "created+read+deleted an edge"


def f_arc_template(t: str) -> str:
    code = _code("arc")
    st, a = call("POST", f"{C}/arc-templates", {
        "code": code, "name": "F2 Arc Probe", "original_language": "en",
        "summary": "a probe arc template", "chapter_span": 6,
        "threads": [{"key": "main", "label": "Main"}],
    }, t)
    aid = ok("arc.create", st, a, 201)["id"]

    st, got = call("GET", f"{C}/arc-templates/{aid}", None, t)
    ver = ok("arc.read", st, got, 200)["version"]

    st, p = call_ifmatch("PATCH", f"{C}/arc-templates/{aid}",
                         {"summary": "edited by the F2 probe"}, t, ver)
    ok("arc.patch", st, p, 200)
    st, got2 = call("GET", f"{C}/arc-templates/{aid}", None, t)
    assert "F2 probe" in ok("arc.reread", st, got2, 200)["summary"], \
        "PATCH returned 200 and the row did not change"

    st, d = call("DELETE", f"{C}/arc-templates/{aid}", None, t)
    ok("arc.delete", st, d, 200)
    st, after = call("GET", f"{C}/arc-templates/{aid}", None, t)
    assert st == 404 or after.get("status") == "archived", \
        f"DELETE returned 200 and the row is still active: {after.get('status')}"
    return f"created+patched+archived {code}"


def f_structure_template(t: str) -> str:
    st, s = call("POST", f"{C}/templates", {
        "name": f"F2 Structure Probe {uuid.uuid4().hex[:6]}", "kind": "generic",
        "beats": [{"key": "setup", "label": "Setup"}, {"key": "payoff", "label": "Payoff"}],
    }, t)
    sid = ok("structure.create", st, s, 201)["id"]

    # There is no single-GET route for a template (405) — the read-back is the LIST.
    def _find(sid_: str) -> dict | None:
        st_, rows_ = call("GET", f"{C}/templates", None, t)
        for r in ok("structure.list", st_, rows_, 200).get("templates", []):
            if str(r.get("id")) == sid_:
                return r
        return None
    row = _find(sid)
    assert row is not None, "created template not in the list"
    ver = row["version"]

    st, p = call("PATCH", f"{C}/structure-templates/{sid}?expected_version={ver}",
                 {"name": f"F2 Probe (edited) {uuid.uuid4().hex[:6]}"}, t)
    ok("structure.patch", st, p, 200)
    st, got2 = call("GET", f"{C}/templates/{sid}", None, t)
    assert "(edited)" in ok("structure.reread", st, got2, 200)["name"], \
        "PATCH returned 200 and the row did not change"

    st, d = call("DELETE", f"{C}/templates/{sid}", None, t)
    ok("structure.delete", st, d, 200, 204)
    st, after = call("GET", f"{C}/templates/{sid}", None, t)
    assert st == 404 or after.get("is_archived") or after.get("status") == "archived", \
        "DELETE returned 200 and the row is still live"
    return "created+patched+archived a structure template"


FAMILIES = {
    "motif": f_motif,
    "motif_link": f_motif_link,
    "arc_template": f_arc_template,
    "structure_template": f_structure_template,
}
TOTAL = len(FAMILIES) + len(PENDING_FIXTURE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="one family name")
    args = ap.parse_args()

    t = _login()
    todo = {args.only: FAMILIES[args.only]} if args.only else FAMILIES
    proven, failed = [], []
    for name, fn in todo.items():
        t0 = time.time()
        try:
            detail = fn(t)
            proven.append(name)
            print(f"  ✓ {name:20} {detail}  [{time.time() - t0:.1f}s]")
        except (Failed, AssertionError, KeyError, TypeError) as exc:
            failed.append((name, str(exc)))
            print(f"  ✗ {name:20} {exc}")

    print()
    for name, fixture in sorted(PENDING_FIXTURE.items()):
        print(f"  · {name:20} PENDING — needs {fixture}")
    print(f"\nF2 real-run proven: {len(proven)}/{TOTAL} families "
          f"({len(PENDING_FIXTURE)} pending a fixture, {len(failed)} failed)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
