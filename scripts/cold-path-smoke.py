#!/usr/bin/env python
"""COLD-PATH SMOKE — create a book from nothing and walk it to a scene plan.

Why this exists. The atom-edit sweep spent hours on static analysis, contract gates, door scans and
mutation testing, and every one of those found something. None of them found the bug that broke
100% of new books: a fresh book has no glossary ontology, so its very first cast proposal could not
be applied, and the only signal was a 422 naming a screen in another feature — arriving AFTER the
author had reviewed and approved a cast. That bug was found by USING the product cold, once, while
proving something else.

The reason no gate caught it is structural: every fixture, every test book, and the dogfood book
itself were created BEFORE the gate they trip over, or by a path that skips it. A cold path is not a
path anyone tests; it is the path every new user takes exactly once, and it is the only impression
they get.

So this drives the real stack over HTTP, as an author would, on a THROWAWAY book:

    login → create book → plan run → compile → cast → seed proposal → approve → apply
          → motifs → world → beats → character_arcs → scenes → self_heal

Each step asserts, times, and reports. It creates content, so it cleans up after itself (the book is
trashed unless --keep) and it must NEVER be pointed at a real book — smoke debris in an author's
library reads as a product bug later.

    python scripts/cold-path-smoke.py                 # full walk, trash the book
    python scripts/cold-path-smoke.py --keep          # leave it for inspection
    python scripts/cold-path-smoke.py --until cast    # stop early (the cheap half, no LLM passes)

Exit 0 = the cold path works. Exit 1 = it does not, and the step that broke is named.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

GATEWAY = "http://localhost:3123"
EMAIL, PASSWORD = "claude-test@loreweave.dev", "Claude@Test2026"

#: A local, $0 chat model. Override with --model when the machine has a different one loaded; the
#: point of this smoke is the PATH, not the prose, so any chat-capable model_ref will do.
DEFAULT_MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"

#: `# 1. Arc Overview` → `## <arc>` → `### <chapter>` + synopsis is the shape the rules-mode parser
#: expects. Anything else yields `arcs: []` and compile has nothing to take an arc_id from — which
#: is itself a cold-path trap worth failing loudly on rather than working around.
SOURCE_MD = """# 1. Arc Overview
## The Lantern Census
### The Counting
Wren is sent to count the harbour's lanterns and finds one more than the register allows.
### The Extra Light
The unlisted lantern burns in a window of a house the census says was demolished.
### The Keeper
An old keeper admits she has been lighting it for someone who never came home.
"""

STEPS = ["book", "run", "compile", "cast", "seed", "motifs", "world", "beats", "arcs",
         "scenes", "heal"]


class Failed(Exception):
    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step, self.detail = step, detail


def call(method: str, path: str, body: dict | None = None, token: str | None = None
         ) -> tuple[int, dict]:
    req = urllib.request.Request(
        GATEWAY + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:400].decode(errors="replace")}
    except OSError as exc:                      # the stack is down — not a product failure
        raise Failed("gateway", f"unreachable at {GATEWAY} ({exc})") from exc


def ok(step: str, status: int, body: dict, *expect: int) -> dict:
    if status not in expect:
        raise Failed(step, f"HTTP {status} {json.dumps(body)[:300]}")
    return body


def wait_pass(token: str, book: str, run: str, pass_id: str, timeout_s: int = 900) -> str:
    """Poll the run until `pass_id` reaches a terminal state. Returns the status."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        _, d = call("GET", f"/v1/composition/books/{book}/plan/runs/{run}", token=token)
        for p in d.get("passes") or []:
            if p.get("pass_id") == pass_id and p.get("status") in ("completed", "failed"):
                return str(p["status"])
        time.sleep(6)
    raise Failed(pass_id, f"still running after {timeout_s}s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL, help="a chat-capable user_model_id")
    ap.add_argument("--keep", action="store_true", help="do not trash the throwaway book")
    ap.add_argument("--until", choices=STEPS, default="heal", help="stop after this step")
    args = ap.parse_args()
    stop_after = STEPS.index(args.until)

    def done(step: str) -> bool:
        return STEPS.index(step) >= stop_after

    t0 = time.time()
    marks: list[tuple[str, float, str]] = []

    def mark(step: str, note: str = "") -> None:
        marks.append((step, time.time() - t0, note))
        print(f"  {step:10s} {time.time() - t0:6.1f}s  {note}")

    book = None
    token = ""
    try:
        _, auth = call("POST", "/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
        token = auth.get("access_token") or ""
        if not token:
            raise Failed("login", f"no access_token in {json.dumps(auth)[:200]}")

        print("cold path:")
        s, b = call("POST", "/v1/books", {
            "title": "COLD-PATH SMOKE (throwaway — safe to delete)",
            "source_language": "en", "genre_tags": ["fantasy"]}, token)
        book = ok("book", s, b, 200, 201)["book_id"]
        mark("book", book)
        if done("book"):
            return 0

        s, r = call("POST", f"/v1/composition/books/{book}/plan/runs",
                    {"mode": "rules", "source_markdown": SOURCE_MD}, token)
        run = ok("run", s, r, 200, 201)["id"]
        arcs = r.get("arcs") or []
        if not arcs:
            raise Failed("run", "the source parsed to ZERO arcs — compile has no arc_id to take")
        mark("run", f"{run}  arc={arcs[0]['id']}")
        if done("run"):
            return 0

        s, c = call("POST", f"/v1/composition/books/{book}/plan/runs/{run}/compile",
                    {"arc_id": arcs[0]["id"]}, token)
        ok("compile", s, c, 200)
        mark("compile", f"premise {len((c.get('package') or {}).get('premise') or '')} chars")
        if done("compile"):
            return 0

        s, j = call("POST", f"/v1/composition/books/{book}/plan/runs/{run}/passes/cast/run",
                    {"model_ref": args.model}, token)
        ok("cast", s, j, 200)
        if wait_pass(token, book, run, "cast") != "completed":
            raise Failed("cast", "the pass failed")
        mark("cast")
        if done("cast"):
            return 0

        # THE COLD-PATH TRAP. On a brand-new book this is where everything used to stop: no glossary
        # ontology, so the seed could not apply and the author was sent to another feature's screen.
        _, d = call("GET", f"/v1/composition/books/{book}/plan/runs/{run}", token=token)
        prop = next((p.get("bootstrap_proposal_id") for p in (d.get("passes") or [])
                     if p.get("pass_id") == "cast" and p.get("bootstrap_proposal_id")), None)
        if not prop:
            raise Failed("seed", "the cast pass produced no bootstrap proposal")
        ok("seed", *call("POST", f"/v1/composition/books/{book}/plan/bootstrap/{prop}/approve",
                         {}, token), 200)
        s, ap_ = call("POST", f"/v1/composition/books/{book}/plan/bootstrap/{prop}/apply", {}, token)
        if s == 422:
            raise Failed("seed", f"THE COLD-START DEAD END IS BACK — {json.dumps(ap_)[:200]}")
        ok("seed", s, ap_, 200)
        seeded = [v for v in (ap_.get("applied_results") or {}).values()
                  if isinstance(v, dict) and v.get("entity_id")]
        if not seeded:
            raise Failed("seed", "apply reported success but seeded NO entity")
        ok("seed", *call("POST", f"/v1/composition/books/{book}/plan/runs/{run}/checkpoint",
                         {"approved": True, "pass_id": "cast"}, token), 200)
        mark("seed", f"{len(seeded)} entity(ies) seeded + cast accepted")
        if done("seed"):
            return 0

        # `world` (pass 3) was MISSING from the first version of this walk — the smoke reported
        # 10/10 while never exercising a pass at all. Found by trying to MCP-edit `world_plan` on a
        # book this script had "fully" walked and discovering the artifact did not exist.
        for step, pass_id, accept in (("motifs", "motifs", False), ("world", "world", False),
                                      ("beats", "beats", True),
                                      ("arcs", "character_arcs", False),
                                      ("scenes", "scenes", False), ("heal", "self_heal", False)):
            s, j = call("POST",
                        f"/v1/composition/books/{book}/plan/runs/{run}/passes/{pass_id}/run",
                        {"model_ref": args.model}, token)
            ok(step, s, j, 200)
            if wait_pass(token, book, run, pass_id) != "completed":
                raise Failed(step, "the pass failed")
            if accept:
                ok(step, *call("POST",
                               f"/v1/composition/books/{book}/plan/runs/{run}/checkpoint",
                               {"approved": True, "pass_id": pass_id}, token), 200)
            mark(step)
            if done(step):
                return 0
        return 0

    except Failed as exc:
        print(f"\nFAILED at {exc.step}\n  {exc.detail}", file=sys.stderr)
        return 1
    finally:
        # Content-creating: clean up. Debris in a real library reads as a product bug later.
        if book and not args.keep:
            st, _ = call("DELETE", f"/v1/books/{book}", token=token)
            print(f"  cleanup    trashed {book} (HTTP {st})")
        elif book:
            print(f"  cleanup    KEPT {book}")
        print(f"\n{len(marks)}/{stop_after + 1} step(s) in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    sys.exit(main())
