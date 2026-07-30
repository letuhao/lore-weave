#!/usr/bin/env python3
"""Live round-trip proof for the composition `*_edit` atom families — atom-edit F2.

F2's real column is *real-run proven?* and it was empty for every family. The three static
gates the track built (per-family delete contract, `fe-door-scan.py`, derived round-trip
preservation) prove shape, reachability and preservation — they do NOT prove an edit
reaching the row, and the checklist's own evidence rule says a unit test does not tick that
box. Substituting gates for it was caught once already, by the human.

So this is the missing thing, as a SCRIPT rather than a transcript: re-runnable, and it
counts out loud.

**It counts out loud, against a denominator it does NOT get to choose.** `ALL_FAMILIES` is
parsed from `test_atom_delete_contract.py`, the machine-checked SSOT for what a family is —
so a family nobody has written a runner for shows up as PENDING with a stated reason instead
of quietly vanishing from the total. That caught something immediately: the checklist has
said **11** composition families throughout while its own prose lists **12** and the contract
holds **14**. `error_block` and `authoring_run_review` were never counted at all, so every
"N/11" printed before this was measured against a wrong denominator.

Per family the shape is the same, and DELETE-first on purpose: delete/archive is the op
that failed silently on four of six PlanForge kinds (B6), so it is the one worth proving.

    CREATE  → read back, assert present
    PATCH   → read back, assert the field actually CHANGED
    DELETE  → read back, assert GONE — and then assert the REVERSE the delete contract
              declares for that family (soft+restore / pair / revision). Absence alone
              passes identically against a hard delete, which is a different contract.

Channels are not interchangeable and are named per family. Most families are proven over
REST — the same calls the GUI makes. `motif_bind` has no REST write route and the BFF's FE
bridge deliberately excludes every `composition_*` bind/unbind, so its only real caller is an
agent: it is proven over MCP, federated through ai-gateway rather than poked directly at
composition-service, because skipping the federation is how a dead affordance passed a green
smoke earlier in this very track.

Everything project-scoped runs inside a THROWAWAY book that is deleted in a `finally`, and a
failure to clean up is PRINTED rather than assumed away.

Usage:
    python scripts/atom-edit-roundtrip.py               # every implemented family
    python scripts/atom-edit-roundtrip.py --only motif  # one (builds no fixture it needn't)
"""
from __future__ import annotations

import argparse
import os
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

#: The AGENT channel. `motif_bind` has no REST write route, and the BFF's FE bridge
#: allowlist deliberately excludes every `composition_*` bind/unbind ("NOTHING here writes
#: or deletes"), so the browser is not its door by DESIGN. Its real caller is an LLM whose
#: tool-call federates ai-gateway → composition-service. Driving composition's own `/mcp`
#: directly would skip that federation — the same shortcut that let a dead FE affordance
#: pass a green live smoke earlier in this track — so this goes through ai-gateway.
AI_GATEWAY = os.environ.get("AI_GATEWAY_URL", "http://localhost:8218")
#: From the environment, never baked in. The fallback is the value docker-compose already
#: puts in every dev container — a local-only placeholder, not a credential — and any other
#: deployment supplies its own rather than editing this file.
INTERNAL_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev_internal_token")


def mcp_call(tool: str, args: dict, user_id: str) -> dict:
    """One MCP `tools/call` through ai-gateway, as an agent makes it."""
    import json as _j, urllib.error, urllib.request
    req = urllib.request.Request(
        f"{AI_GATEWAY}/mcp",
        data=_j.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": args}}).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "X-Internal-Token": INTERNAL_TOKEN, "X-User-Id": user_id,
                 # The tool context is carried in headers, not args — a call without a
                 # session id is rejected at the tool boundary, not at the transport.
                 "X-Session-Id": str(uuid.uuid4())},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        raise Failed(f"mcp:{tool}", f"HTTP {e.code} {e.read()[:300].decode(errors='replace')}")
    # ai-gateway may answer as an SSE frame; take the last `data:` line when it does.
    if raw.lstrip().startswith("event:") or "\ndata:" in raw:
        raw = [l[5:].strip() for l in raw.splitlines() if l.startswith("data:")][-1]
    body = _j.loads(raw)
    if body.get("error"):
        raise Failed(f"mcp:{tool}", _j.dumps(body["error"])[:300])
    res = body.get("result") or {}
    if res.get("isError"):
        raise Failed(f"mcp:{tool}", _j.dumps(res)[:300])
    # Unwrap the MCP content envelope to the tool's own JSON payload.
    for item in res.get("content") or []:
        if item.get("type") == "text":
            try:
                return _j.loads(item["text"])
            except ValueError:
                return {"text": item["text"]}
    return res.get("structuredContent") or res


def _login() -> str:
    st, body = call("POST", "/v1/auth/login",
                    {"email": cps.EMAIL, "password": cps.PASSWORD})
    return ok("login", st, body, 200)["access_token"]


def _code(kind: str) -> str:
    return f"smoke.f2_{kind}_{uuid.uuid4().hex[:8]}"


class Fixture:
    """The Work-and-outline scaffolding the project-scoped families need.

    Built **lazily** (so `--only motif` pays nothing) and **once** per run, entirely inside a
    THROWAWAY book that `close()` deletes. Never the dogfood book — smoke debris left in real
    content reads as a product bug to whoever finds it later.

    Every step here already existed. The earlier PENDING notes claimed these families needed
    infrastructure; they needed a POST. Notably `POST /books/{id}/work` is documented in the
    contract as "PLANNED — not yet implemented" and has been implemented all along
    (`works.py:154`) — verified against code, because a stale doc that says "missing" is the
    exact thing this repo has twice mistaken for a blocker.
    """

    def __init__(self, t: str) -> None:
        self.t = t
        self._book: str | None = None
        self._pid: str | None = None
        self._chapter: str | None = None
        self._book_chapter: str | None = None
        self._plan_run: str | None = None
        self._scenes: list[str] = []
        self._deriv: str | None = None

    @property
    def user_id(self) -> str:
        """Decoded from the JWT rather than hardcoded, so the harness is not welded to one
        test account. The MCP channel needs it as `X-User-Id`."""
        import base64, json as _j
        payload = self.t.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = _j.loads(base64.urlsafe_b64decode(payload))
        uid = claims.get("sub") or claims.get("user_id")
        if not uid:
            raise Failed("fixture.user_id", f"no sub in the JWT claims: {list(claims)}")
        return str(uid)

    @property
    def book_id(self) -> str:
        if self._book is None:
            st, b = call("POST", "/v1/books", {
                "title": "ATOM-EDIT F2 FIXTURE (throwaway — safe to delete)",
                "source_language": "en",
            }, self.t)
            self._book = ok("fixture.book", st, b, 200, 201)["book_id"]
        return self._book

    @property
    def project_id(self) -> str:
        """The Work. Idempotent server-side, so a re-entry is free."""
        if self._pid is None:
            st, w = call("POST", f"{C}/books/{self.book_id}/work", {}, self.t)
            self._pid = str(ok("fixture.work", st, w, 200, 201)["project_id"])
        return self._pid

    @property
    def book_chapter_id(self) -> str:
        """A real book-service chapter. The outline chapter NODE carries this as its
        `chapter_id`, and that column — not the node's parent — is what the per-chapter
        reads key on (`scenes_for_chapter`: `WHERE project_id = $1 AND chapter_id = $2`).
        A chapter node without it is invisible to every one of those routes."""
        if self._book_chapter is None:
            st, c = call("POST", f"/v1/books/{self.book_id}/chapters", {
                "title": "F2 Fixture Chapter", "original_language": "en",
                "sort_order": 1, "body": "The lantern census began at dusk.",
            }, self.t)
            body = ok("fixture.book_chapter", st, c, 200, 201)
            self._book_chapter = str(body.get("chapter_id") or body.get("id"))
        return self._book_chapter

    @property
    def chapter_node(self) -> str:
        if self._chapter is None:
            st, n = call("POST", f"{C}/works/{self.project_id}/outline/nodes",
                         {"kind": "chapter", "title": "F2 Fixture Chapter",
                          "chapter_id": self.book_chapter_id}, self.t)
            self._chapter = ok("fixture.chapter", st, n, 201)["id"]
        return self._chapter

    def scene(self, i: int) -> str:
        """Scene nodes under the fixture chapter. `scene_link` needs two."""
        while len(self._scenes) <= i:
            n_ = len(self._scenes)
            st, n = call("POST", f"{C}/works/{self.project_id}/outline/nodes", {
                "kind": "scene", "parent_id": self.chapter_node,
                "title": f"F2 Fixture Scene {n_ + 1}",
            }, self.t)
            self._scenes.append(ok(f"fixture.scene{n_}", st, n, 201)["id"])
        return self._scenes[i]

    @property
    def plan_run_id(self) -> str:
        """A PlanForge run in `rules` mode — a deterministic parse of the source markdown
        with NO model call, so the authoring-run fixture costs nothing."""
        if self._plan_run is None:
            st, r = call("POST", f"{C}/books/{self.book_id}/plan/runs",
                         {"mode": "rules", "source_markdown": cps.SOURCE_MD}, self.t)
            self._plan_run = str(ok("fixture.plan_run", st, r, 200, 201)["id"])
        return self._plan_run

    @property
    def derivative_pid(self) -> str:
        """A dị bản of the fixture Work — what `entity_override` hangs off."""
        if self._deriv is None:
            st, d = call("POST", f"{C}/works/{self.project_id}/derive", {
                "name": f"F2 Fixture Derivative {uuid.uuid4().hex[:6]}",
            }, self.t)
            self._deriv = str(ok("fixture.derive", st, d, 200, 201)["project_id"])
        return self._deriv

    def close(self) -> str | None:
        """Delete the throwaway book. Returns a note if it could NOT be cleaned, so a leak is
        reported rather than assumed away."""
        if self._book is None:
            return None
        st, _ = call("DELETE", f"/v1/books/{self._book}", None, self.t)
        return None if st in (200, 202, 204) else f"book {self._book} not deleted (HTTP {st})"


# ── families ───────────────────────────────────────────────────────────────
def f_motif(t: str, fx: Fixture) -> str:
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


def f_motif_link(t: str, fx: Fixture) -> str:
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

    # The neighbour is NESTED (`neighbor: {id, code, name}`) — `motif_repo.list_links`
    # joins it as a stub. This harness first asserted a FLAT `neighbor_id` and read its own
    # miss as "the edge does not come back", which is also the exact shape the FRONTEND had
    # wrong: it declared the flat fields and rendered blank labels on every edge for a
    # release. So the harness bug and the product bug were the same misreading.
    def _has_edge(body: dict) -> bool:
        rows_ = body.get("links", body if isinstance(body, list) else [])
        return any((r.get("neighbor") or {}).get("id") == ids[1] for r in rows_)

    st, rows = call("GET", f"{C}/motifs/{ids[0]}/links", None, t)
    assert _has_edge(ok("link.read", st, rows, 200)), \
        "the edge does not come back on the read"

    st, d = call("DELETE", f"{C}/motif-links/{lid}", None, t)
    ok("link.delete", st, d, 200)
    st, rows2 = call("GET", f"{C}/motifs/{ids[0]}/links", None, t)
    assert not _has_edge(ok("link.reread", st, rows2, 200)), \
        "DELETE returned 200 and the edge is still there"

    for mid in ids:
        call("DELETE", f"{C}/motifs/{mid}", None, t)
    return "created+read+deleted an edge"


def f_arc_template(t: str, fx: Fixture) -> str:
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


def f_structure_template(t: str, fx: Fixture) -> str:
    # Named with the same `smoke.f2_` prefix as every other probe. These kinds archive
    # SOFT and no route hard-deletes them, so each run leaves an archived row behind —
    # one shared prefix makes the leftovers a single greppable predicate instead of three.
    code = _code("structure")
    st, s = call("POST", f"{C}/templates", {
        "name": code, "kind": "generic",
        "beats": [{"key": "setup", "label": "Setup"}, {"key": "payoff", "label": "Payoff"}],
    }, t)
    sid = ok("structure.create", st, s, 201)["id"]

    # There is no single-GET route for a template (405) — every read-back is the LIST.
    def _find(sid_: str, *, archived: bool = False) -> dict | None:
        q = "?include_archived=true" if archived else ""
        st_, rows_ = call("GET", f"{C}/templates{q}", None, t)
        for r in ok("structure.list", st_, rows_, 200).get("templates", []):
            if str(r.get("id")) == sid_:
                return r
        return None
    row = _find(sid)
    assert row is not None, "created template not in the list"

    # PATCH is `/templates/{id}` with an If-Match HEADER. This harness first sent
    # `/structure-templates/{id}?expected_version=` — a route that does not exist — and read
    # the resulting `404 {"detail": "Not Found"}` as "no such row" when FastAPI meant "no
    # such route". Two different 404s; only one is a product bug.
    st, p = call_ifmatch("PATCH", f"{C}/templates/{sid}",
                         {"name": f"{code} (edited)"}, t, row["version"])
    ok("structure.patch", st, p, 200)
    row2 = _find(sid)
    assert row2 and "(edited)" in row2["name"], \
        "PATCH returned 200 and the row did not change"

    st, d = call("DELETE", f"{C}/templates/{sid}", None, t)
    ok("structure.delete", st, d, 204)
    # Archive is SOFT (there is a /restore route), so prove BOTH halves: gone from the
    # active list AND still present with include_archived. "Absent from one list" alone
    # would pass just as well if the row had been hard-deleted, which is a different
    # contract — and the delete-contract test declares this kind soft.
    assert _find(sid) is None, "DELETE returned 204 and the row is still in the active list"
    assert _find(sid, archived=True) is not None, \
        "archive HARD-deleted the row; this kind is declared soft (it has a /restore route)"
    return f"created+patched+archived {code}"


# ── project-scoped families (need the Work fixture) ────────────────────────
def f_canon_rule(t: str, fx: Fixture) -> str:
    pid = fx.project_id
    st, r = call("POST", f"{C}/works/{pid}/canon-rules",
                 {"text": "The lantern census is counted at dusk.", "scope": "world"}, t)
    rid = ok("canon.create", st, r, 201)["id"]

    def _find(archived: bool = False) -> dict | None:
        q = "?include_archived=true" if archived else ""
        st_, rows = call("GET", f"{C}/works/{pid}/canon-rules{q}", None, t)
        body = ok("canon.list", st_, rows, 200)
        for x in (body.get("rules") if isinstance(body, dict) else body) or []:
            if str(x.get("id")) == rid:
                return x
        return None
    assert _find() is not None, "created rule not in the list"

    st, p = call("PATCH", f"{C}/canon-rules/{rid}",
                 {"text": "The lantern census is counted at DAWN."}, t)
    ok("canon.patch", st, p, 200)
    row = _find()
    assert row and "DAWN" in row["text"], "PATCH returned 200 and the row did not change"

    st, d = call("DELETE", f"{C}/canon-rules/{rid}", None, t)
    ok("canon.delete", st, d, 200)
    # Declared SOFT with a /restore reverse — so prove both halves, not just absence.
    assert _find() is None, "DELETE returned 200 and the rule is still active"
    assert _find(archived=True) is not None, \
        "archive HARD-deleted the rule; the delete contract declares it soft"
    return "created+patched+archived a canon rule"


def f_outline_node(t: str, fx: Fixture) -> str:
    pid = fx.project_id
    st, n = call("POST", f"{C}/works/{pid}/outline/nodes",
                 {"kind": "chapter", "title": "F2 Outline Probe"}, t)
    nid = ok("node.create", st, n, 201)["id"]

    st, got = call("GET", f"{C}/outline/nodes/{nid}", None, t)
    ver = ok("node.read", st, got, 200)["version"]

    st, p = call_ifmatch("PATCH", f"{C}/outline/nodes/{nid}",
                         {"title": "F2 Outline Probe (edited)"}, t, ver)
    ok("node.patch", st, p, 200)
    st, got2 = call("GET", f"{C}/outline/nodes/{nid}", None, t)
    assert "(edited)" in ok("node.reread", st, got2, 200)["title"], \
        "PATCH returned 200 and the row did not change"

    st, d = call("DELETE", f"{C}/outline/nodes/{nid}", None, t)
    ok("node.delete", st, d, 200)
    st, after = call("GET", f"{C}/outline/nodes/{nid}", None, t)
    assert st == 404 or after.get("status") == "archived" or after.get("is_archived"), \
        "DELETE returned 200 and the node is still active"
    return "created+patched+archived an outline node"


def f_scene_link(t: str, fx: Fixture) -> str:
    pid = fx.project_id
    a, b = fx.scene(0), fx.scene(1)
    st, l = call("POST", f"{C}/works/{pid}/scene-links",
                 {"from_node_id": a, "to_node_id": b, "kind": "setup_payoff",
                  "label": "F2 probe: the lantern set up, then paid off"}, t)
    lid = ok("scenelink.create", st, l, 201)["id"]

    def _present() -> bool:
        st_, rows = call("GET", f"{C}/works/{pid}/outline", None, t)
        body = ok("scenelink.read", st_, rows, 200)
        return any(str(x.get("id")) == lid for x in (body.get("scene_links") or []))
    assert _present(), "the scene link does not come back on the outline read"

    st, d = call("DELETE", f"{C}/scene-links/{lid}", None, t)
    ok("scenelink.delete", st, d, 204)
    assert not _present(), "DELETE returned 204 and the link is still on the outline"
    # F3 made this SOFT precisely because the row carries an authored `label`; the reverse
    # must therefore exist and work, or the "soft" claim is decorative.
    st, r = call("POST", f"{C}/scene-links/{lid}/restore", {}, t)
    ok("scenelink.restore", st, r, 200)
    assert _present(), "restore returned 200 and the link did not come back"
    call("DELETE", f"{C}/scene-links/{lid}", None, t)
    return "created+read+archived+restored a scene link"


def f_derivative(t: str, fx: Fixture) -> str:
    # A derivative IS a composition_work, so its "delete" is a status flip via the generic
    # PATCH — the delete contract declares that reverse explicitly rather than assuming a
    # /restore, because assuming one shape is the mistake that contract exists to catch.
    dpid = fx.derivative_pid
    st, w = call("GET", f"{C}/works/{dpid}", None, t)
    got = ok("deriv.read", st, w, 200)
    assert got.get("source_work_id"), "the derived Work has no source_work_id"

    st, p = call_ifmatch("PATCH", f"{C}/works/{dpid}",
                         {"status": "archived"}, t, got["version"])
    ok("deriv.archive", st, p, 200)
    st, w2 = call("GET", f"{C}/works/{dpid}", None, t)
    got2 = ok("deriv.reread", st, w2, 200)
    assert got2.get("status") == "archived", \
        f"PATCH returned 200 and status is still {got2.get('status')}"

    st, p2 = call_ifmatch("PATCH", f"{C}/works/{dpid}", {"status": "active"}, t,
                          got2["version"])
    ok("deriv.restore", st, p2, 200)
    return "derived+archived+restored a derivative Work"


def f_entity_override(t: str, fx: Fixture) -> str:
    dpid = fx.derivative_pid
    target = str(uuid.uuid4())   # the override stores the target id; it is not a glossary FK
    st, o = call("POST", f"{C}/works/{dpid}/entity-overrides",
                 {"target_entity_id": target,
                  "overridden_fields": {"name": "F2 probe alias"}}, t)
    oid = ok("override.create", st, o, 201)["id"]

    def _find() -> dict | None:
        st_, rows = call("GET", f"{C}/works/{dpid}/entity-overrides", None, t)
        body = ok("override.list", st_, rows, 200)
        for x in (body.get("overrides") if isinstance(body, dict) else body) or []:
            if str(x.get("id")) == oid:
                return x
        return None
    assert _find() is not None, "created override not in the list"

    st, p = call("PATCH", f"{C}/works/{dpid}/entity-overrides/{oid}",
                 {"overridden_fields": {"name": "F2 probe alias (edited)"}}, t)
    ok("override.patch", st, p, 200)
    row = _find()
    assert row and "(edited)" in str(row.get("overridden_fields")), \
        "PATCH returned 200 and the override did not change"

    st, d = call("DELETE", f"{C}/works/{dpid}/entity-overrides/{oid}", None, t)
    ok("override.delete", st, d, 204)
    assert _find() is None, "DELETE returned 204 and the override is still active"
    # `list_entity_overrides` takes no `include_archived`, so an archived row is simply not
    # visible there — the softness has to be proven the way the contract's declared reverse
    # proves it: restore by id and see the row come back. (I first asserted an
    # include_archived listing, got an empty result, and nearly filed "archive HARD-deleted
    # it" as a product bug. The route was fine; my proof was aimed at the wrong surface.)
    st, r = call("POST", f"{C}/works/{dpid}/entity-overrides/{oid}/restore", {}, t)
    ok("override.restore", st, r, 200)
    row2 = _find()
    assert row2 is not None, "restore returned 200 and the override did not come back"
    assert "(edited)" in str(row2.get("overridden_fields")), \
        "restore brought the row back but LOST the authored overridden_fields"
    call("DELETE", f"{C}/works/{dpid}/entity-overrides/{oid}", None, t)
    return "created+patched+archived+restored an entity override"


def f_arc(t: str, fx: Fixture) -> str:
    # `arc` shares the outline_node TABLE with the outline_node family but has its own
    # book-scoped routes (`/books/{id}/arcs`, `/arcs/{id}`), so proving outline_node proves
    # nothing about it. Counting one for the other is the assumption the delete contract
    # keeps them as separate rows to prevent.
    book = fx.book_id
    st, a = call("POST", f"{C}/books/{book}/arcs",
                 {"kind": "arc", "title": "F2 Arc Probe", "summary": "a probe arc"}, t)
    nid = ok("arc.create", st, a, 201)["id"]

    st, got = call("GET", f"{C}/arcs/{nid}", None, t)
    ver = ok("arc.read", st, got, 200)["version"]

    st, p = call_ifmatch("PATCH", f"{C}/arcs/{nid}",
                         {"title": "F2 Arc Probe (edited)"}, t, ver)
    ok("arc.patch", st, p, 200)
    st, got2 = call("GET", f"{C}/arcs/{nid}", None, t)
    assert "(edited)" in ok("arc.reread", st, got2, 200)["title"], \
        "PATCH returned 200 and the row did not change"

    st, d = call("DELETE", f"{C}/arcs/{nid}", None, t)
    ok("arc.delete", st, d, 200)
    st, after = call("GET", f"{C}/arcs/{nid}", None, t)
    gone = st == 404 or (after or {}).get("status") == "archived" or (after or {}).get("is_archived")
    assert gone, "DELETE returned 200 and the arc is still active"
    st, r = call("POST", f"{C}/arcs/{nid}/restore", {}, t)
    ok("arc.restore", st, r, 200)
    st, back = call("GET", f"{C}/arcs/{nid}", None, t)
    assert ok("arc.reread2", st, back, 200)["title"].startswith("F2 Arc Probe"), \
        "restore returned 200 and the arc did not come back"
    return "created+patched+archived+restored an arc"


def f_motif_bind(t: str, fx: Fixture) -> str:
    """The one family proven on the AGENT channel, because it has no other.

    Its delete semantic is declared `pair`: `unbind` is not a delete, it is the other half
    of one toggle. So the round-trip here is bind → read the binding back → unbind → read
    it gone, and the tool must expose BOTH halves or the "reverse is always reachable"
    justification in the delete contract is decorative.
    """
    pid, node = fx.project_id, fx.chapter_node
    st, m = call("POST", f"{C}/motifs", {
        "code": _code("bind"), "name": "F2 Bind Probe", "original_language": "en",
        "kind": "sequence", "summary": "a probe motif to bind",
        "beats": [{"key": "one", "label": "First", "intent": "it begins",
                   "tension_target": 2, "order": 1}],
    }, t)
    mid = ok("bind.motif", st, m, 201)["id"]

    def _bound() -> set[str]:
        """The motif ids bound anywhere under the fixture chapter.

        Two traps, both of which cost me a run:
        · the read is per-SCENE, not per-chapter — binding instantiates the motif's beats as
          scene nodes and the route answers `{chapter_id, bindings: {scene_node_id:
          BoundMotif | null}}`, so looking for the chapter's own id finds nothing forever;
        · `?chapter_id=` is the BOOK chapter id, not the outline chapter NODE id
          (`scenes_for_chapter` is `WHERE project_id = $1 AND chapter_id = $2` over a column
          the node merely carries). Passing the node id returns an empty dict and a 200,
          which reads exactly like "the bind did nothing"."""
        st_, rows = call(
            "GET",
            f"{C}/works/{pid}/outline/motif-bindings?chapter_id={fx.book_chapter_id}",
            None, t)
        body = ok("bind.read", st_, rows, 200)
        out: set[str] = set()
        for bound in (body.get("bindings") or {}).values():
            if isinstance(bound, dict):
                got = bound.get("motif_id") or bound.get("id")
                if got:
                    out.add(str(got))
        return out

    mcp_call("composition_motif_bind_edit",
             {"op": "bind", "project_id": pid, "node_id": node, "motif_id": mid},
             fx.user_id)
    assert mid in _bound(), "bind returned OK and no scene under the chapter is bound"

    mcp_call("composition_motif_bind_edit",
             {"op": "unbind", "project_id": pid, "node_id": node}, fx.user_id)
    assert mid not in _bound(), "unbind returned OK and the binding is still there"
    call("DELETE", f"{C}/motifs/{mid}", None, t)
    return "bound+read+unbound via MCP through ai-gateway"


def f_error_block(t: str, fx: Fixture) -> str:
    """A reader's mark on a chapter's prose. Never counted by the checklist's "11" at all —
    it is in the delete contract but absent from F2's own list."""
    pid, ch = fx.project_id, fx.book_chapter_id
    quote = "The lantern census began at dusk."
    st, b = call("POST", f"{C}/works/{pid}/chapters/{ch}/error-blocks", {
        "start_offset": 0, "end_offset": len(quote), "quote": quote,
        "source_fingerprint": f"f2-{uuid.uuid4().hex[:12]}", "kind": "continuity",
        "note": "F2 probe: the census is at dawn elsewhere.",
    }, t)
    bid = ok("errblock.create", st, b, 201)["id"]

    def _find(include_resolved: bool = False) -> dict | None:
        q = "?include_resolved=true" if include_resolved else ""
        st_, rows = call("GET", f"{C}/works/{pid}/chapters/{ch}/error-blocks{q}", None, t)
        body = ok("errblock.list", st_, rows, 200)
        for x in (body.get("blocks") if isinstance(body, dict) else body) or []:
            if str(x.get("id")) == bid:
                return x
        return None
    assert _find() is not None, "created error block not in the list"

    st, p = call("PATCH", f"{C}/error-blocks/{bid}",
                 {"note": "F2 probe: the census is at dawn elsewhere. (edited)"}, t)
    ok("errblock.patch", st, p, 200)
    row = _find()
    assert row and "(edited)" in row["note"], \
        "PATCH returned 200 and the note did not change"

    st, d = call("DELETE", f"{C}/error-blocks/{bid}", None, t)
    ok("errblock.delete", st, d, 200)
    assert _find() is None, "DELETE returned 200 and the block is still listed"
    st, r = call("POST", f"{C}/error-blocks/{bid}/restore", {}, t)
    ok("errblock.restore", st, r, 200)
    row2 = _find()
    assert row2 is not None, "restore returned 200 and the block did not come back"
    assert "(edited)" in row2["note"], "restore brought it back but LOST the authored note"
    call("DELETE", f"{C}/error-blocks/{bid}", None, t)
    return "created+patched+archived+restored an error block"


def f_authoring_run_manage(t: str, fx: Fixture) -> str:
    """Proven for $0, deliberately.

    This family's headline op is `revert_all`, which is why the earlier note said it
    "SPENDS money". Reading the routes rather than assuming: `POST /authoring-runs` only
    writes the run row — generation starts at `POST /{id}/gate`, which this never calls.
    The plan run it needs is `rules` mode, a deterministic parse with no model call. So the
    manage surface is fully exercisable without a cent, and "it costs money" turns out to
    have been true of one op, not of the family.
    """
    st, r = call("POST", "/v1/composition/authoring-runs", {
        "book_id": fx.book_id, "plan_run_id": fx.plan_run_id, "level": 3,
        "scope": [fx.book_chapter_id], "budget_usd": 0,
        "pause_after_each_unit": False,
    }, t)
    created = ok("arun.create", st, r, 201)
    rid = created["run_id"]          # `run_id`, not `id` — this row names its own key
    assert created.get("status") == "draft", \
        f"a freshly created run should be draft, not {created.get('status')}"

    st, got = call("GET", f"/v1/composition/authoring-runs/{rid}", None, t)
    before = ok("arun.read", st, got, 200)
    assert before.get("pause_after_each_unit") is False, \
        f"the run did not take the requested pause policy: {before.get('pause_after_each_unit')}"

    st, p = call("PATCH", f"/v1/composition/authoring-runs/{rid}/pause-policy",
                 {"pause_after_each_unit": True}, t)
    ok("arun.pause_policy", st, p, 200)
    st, got2 = call("GET", f"/v1/composition/authoring-runs/{rid}", None, t)
    after = ok("arun.reread", st, got2, 200)
    assert after.get("pause_after_each_unit") is True, \
        "PATCH returned 200 and the pause policy did not flip"
    # The whole point of never gating: prove the run cost nothing.
    assert float(after.get("spent_usd") or 0) == 0.0, \
        f"an ungated run spent money: {after.get('spent_usd')}"
    # No delete assertion: this family's row is `revision` tier in the delete contract — it
    # destroys no row, it rolls authored prose back. Asserting a delete here would be
    # inventing a semantic the contract explicitly says this family does not have.
    return "created a run + flipped its pause policy ($0 — never gated)"


FAMILIES = {
    "motif": f_motif,
    "arc": f_arc,
    "motif_bind": f_motif_bind,
    "error_block": f_error_block,
    "authoring_run_manage": f_authoring_run_manage,
    "motif_link": f_motif_link,
    "arc_template": f_arc_template,
    "structure_template": f_structure_template,
    "canon_rule": f_canon_rule,
    "outline_node": f_outline_node,
    "scene_link": f_scene_link,
    "derivative": f_derivative,
    "entity_override": f_entity_override,
}
#: The DENOMINATOR — PARSED from the atom-delete contract, which is the machine-checked SSOT
#: for what an atom family IS. Deriving it from `FAMILIES` instead would mean forgetting a
#: family silently shrinks the total and 9/9 reads as done: the same silent-cap failure this
#: module's docstring exists to prevent. Read it from the SSOT and a family I have not
#: written yet shows up as PENDING, loudly.
#:
#: This immediately paid for itself. The checklist has said **11** composition families all
#: along, while its own prose lists **12** and the contract holds **14** — `error_block` and
#: `authoring_run_review` were never in the checklist's count at all. Every "N/11" this
#: harness printed before was measured against a denominator that was simply wrong.
_CONTRACT_SRC = (pathlib.Path(__file__).resolve().parent.parent / "services"
                 / "composition-service" / "tests" / "unit" / "test_atom_delete_contract.py")


def _all_families() -> tuple[str, ...]:
    import re
    marker = "CONTRACT: dict[str, AtomDelete] = {"
    src = _CONTRACT_SRC.read_text(encoding="utf-8")
    if marker not in src:
        # Either path here must be LOUD. A denominator that silently comes back empty makes
        # the score read "13/13 — done", which is the precise lie this file exists to refuse.
        raise Failed("denominator", f"{_CONTRACT_SRC} no longer contains `{marker}` — the "
                                    "family SSOT moved or was renamed")
    tools = re.findall(r'^    "([a-z_]+)": AtomDelete\(', src[src.index(marker):], re.M)
    if not tools:
        raise Failed("denominator", f"no families parsed from {_CONTRACT_SRC}")
    # composition_outline_node_edit → outline_node; the manage/review tools keep their
    # suffix because they are two distinct surfaces, not one family counted twice.
    return tuple(t[len("composition_"):].removesuffix("_edit") for t in tools)


#: Why a family in ALL_FAMILIES has no runner yet. Printed verbatim — a pending family with
#: no stated reason prints "no reason recorded", which is the loud version of forgetting.
PENDING_REASON = {
    "motif_bind": "MCP channel — it has no REST write route (only GET …/motif-bindings)",
    # The ONE genuinely blocked family, and the reason is external (cost), not "unbuilt".
    # accept/reject operate on DRAFTED units, and drafting them means gating the run — real
    # generation against a real model. Everything up to that point is already proven by
    # `authoring_run_manage`; what is missing cannot be faked without also faking the thing
    # under test. Left PENDING deliberately rather than asserted around.
    "authoring_run_review": "accept/reject act on DRAFTED units, which requires gating the "
                            "run — i.e. real generation and real spend",
}
ALL_FAMILIES = _all_families()
TOTAL = len(ALL_FAMILIES)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="one family name")
    args = ap.parse_args()

    t = _login()
    fx = Fixture(t)
    todo = {args.only: FAMILIES[args.only]} if args.only else FAMILIES
    proven, failed = [], []
    try:
        for name, fn in todo.items():
            t0 = time.time()
            try:
                detail = fn(t, fx)
                proven.append(name)
                print(f"  ✓ {name:20} {detail}  [{time.time() - t0:.1f}s]")
            except (Failed, AssertionError, KeyError, TypeError) as exc:
                failed.append((name, str(exc)))
                print(f"  ✗ {name:20} {exc}")
    finally:
        leak = fx.close()
        if leak:
            print(f"\n  ⚠ fixture NOT cleaned up: {leak}")

    print()
    for name in ALL_FAMILIES:
        if name in FAMILIES:
            continue
        print(f"  · {name:20} PENDING — {PENDING_REASON.get(name, 'no reason recorded')}")
    pending = [n for n in ALL_FAMILIES if n not in FAMILIES]
    print(f"\nF2 real-run proven: {len(proven)}/{TOTAL} families "
          f"({len(pending)} pending, {len(failed)} failed)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
