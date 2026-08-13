#!/usr/bin/env python
"""Drive MANY REAL chat turns concurrently, through the path the FE actually uses.

🔴 WHY NOT A UNIT TEST, AND WHY NOT THE MCP SWEEP. Two things make this system untestable by
either, and the 31-cycle ledger is the evidence:

  1. THE DEFECTS LIVE ABOVE THE TOOL. 14 of 23 proven defects are in chat-service — surfacing,
     the hot-seed budget, the rail driver, arg injection/repair, the dispatch chokepoint — not in
     the tool being tested. A probe that talks straight to an MCP endpoint starts BELOW all of
     them. It marked `composition_list_outline` clean, correctly, while the real turn had the
     model answer "your outline is currently empty" with seven rows in the store.

  2. THE CONSUMER IS AN LLM, SO ONE SAMPLE PROVES NOTHING. The model is local gemma-4-26b and it
     is stochastic: the same prompt reaches the tool on one run and narrates a fabricated answer
     on the next. A single green run is not evidence, which is why every scenario here runs N
     times and the report is a DISTRIBUTION, never a verdict from one sample.

So this runner is the real environment: the same endpoint, headers, body and streaming contract
the browser sends, against the real chat-service and the real model. Captured from a live browser
turn (reqid=168) rather than reconstructed from the FE source, so it cannot drift into a
plausible-but-different request.

What it still does NOT cover, stated so its silence is never read as proof: React rendering,
confirm-card UI, and the context panel. A tool whose story involves those needs a browser.

  POST /v1/chat/sessions/{id}/messages
  headers: authorization: Bearer …, content-type: application/json,
           x-loreweave-stream-format: agui
  body:    {"content", "thinking", "reasoning_effort", "editor_context", "book_context"}
  reply:   text/event-stream of AG-UI events, including the `agentSurface` CUSTOM event that
           carries hot_seed_count / advertised{core,frontend,activated} / schema_tokens

Usage:
    python scripts/toolloop/fe_runner.py scenarios.json --repeats 5 --concurrency 4
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import sys
from collections import Counter

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from store_snapshot import diff as store_diff, snapshot  # noqa: E402
from provision import Throwaway  # noqa: E402
from approvals import ApprovalState  # noqa: E402

BASE = "http://localhost:5174"
ENV_FILE = pathlib.Path(__file__).resolve().parents[2] / "docs" / "dev" / "LOCAL_TEST_ENV.md"


def read_credential() -> tuple[str, str]:
    """The account the loop runs as, read from the git-ignored local env file.

    Deliberately NOT a default, an env var with a fallback, or a constant in this file. A
    harness that can silently run as SOMEONE ELSE is the failure that put three fabricated
    chapters into the author's real book: the safe account has to be the only account it can
    find, and its absence has to stop the run rather than degrade it.
    """
    if not ENV_FILE.exists():
        raise SystemExit(
            f"{ENV_FILE} does not exist. Copy docs/dev/LOCAL_TEST_ENV.example.md to it and "
            "fill in the harness account. Do not invent a credential and do not scavenge one "
            "out of docs/plans/**.")
    txt = ENV_FILE.read_text(encoding="utf-8")
    email = re.search(r"^email:\s*(\S+)", txt, re.M)
    pw = re.search(r"^password:\s*(\S.*?)\s*$", txt[email.end():] if email else "", re.M)
    if not (email and pw) or pw.group(1).startswith("<"):
        raise SystemExit(f"{ENV_FILE} has no filled-in email/password pair.")
    return email.group(1), pw.group(1)


class Auth:
    """Log in. Do not scrape.

    🔴 THE PREVIOUS VERSION READ A TOKEN OUT OF THE BROWSER, AND IT COST WHOLE RUNS. The
    refresh token in localStorage is ROTATED and single-use, so a copied one is normally
    already spent by the time the harness starts; the access token beside it lasts 2h. Past
    that boundary every turn 401s, and a 401 mid-stream looks EXACTLY like "the model chose
    not to call anything" in the report. The harness was therefore recording model behaviour
    that was really an expired credential — the most expensive kind of wrong evidence,
    because it is indistinguishable from a real finding.

    Logging in with a durable password removes the whole class: the credential cannot be
    stale, and re-login on a 401 is unlimited rather than one-shot.
    """

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.access = ""
        self.user_id = ""
        self.logins = 0

    async def login(self, client: httpx.AsyncClient) -> None:
        r = await client.post(f"{BASE}/v1/auth/login",
                              json={"email": self.email, "password": self.password})
        if r.status_code != 200:
            raise SystemExit(
                f"login as {self.email} failed ({r.status_code}: {r.text[:160]}). Fix the "
                f"credential in {ENV_FILE} — a harness must never fall back to another "
                "account.")
        d = r.json()
        self.access = d.get("access_token") or d.get("accessToken") or ""
        self.user_id = (d.get("user_profile") or {}).get("user_id", "")
        self.logins += 1
        if not self.access:
            raise SystemExit(f"login returned no access token: {sorted(d)}")

    async def refresh(self, client: httpx.AsyncClient) -> None:
        """Kept under the old name so every 401 handler keeps working — but it is now a
        re-login, which cannot be exhausted."""
        await self.login(client)

    def headers(self) -> dict:
        return {"authorization": f"Bearer {self.access}",
                "content-type": "application/json",
                "x-loreweave-stream-format": "agui"}


async def _json(client, auth, method, path, **kw):
    for attempt in (1, 2):
        r = await client.request(method, f"{BASE}{path}", headers=auth.headers(), **kw)
        if r.status_code == 401 and attempt == 1:
            await auth.refresh(client)
            continue
        r.raise_for_status()
        return r.json() if r.content else {}
    raise RuntimeError("unreachable")


async def _drain(client, auth, method, url, body, out, timeout):
    """Read one AG-UI stream into `out`. Returns True if it completed, False on a 401 retry."""
    async with client.stream(method, url, headers=auth.headers(), json=body,
                             timeout=timeout) as r:
        if r.status_code == 401:
            await r.aread()
            await auth.refresh(client)
            return False
        r.raise_for_status()
        async for line in r.aiter_lines():
            if not line.startswith("data: "):
                continue
            try:
                ev = json.loads(line[6:])
            except ValueError:
                continue
            t = ev.get("type")
            out["events"][t] += 1
            if t == "RUN_STARTED":
                out["run_id"] = ev.get("runId")
            elif t == "TEXT_MESSAGE_CONTENT":
                out["text"] += ev.get("delta", "")
            elif t == "CUSTOM" and ev.get("name") == "agentSurface":
                # 🔴 KEEP EVERY PASS, NOT THE LAST ONE. Keeping only the last inverted a
                # real measurement: `composition_list_canon_rules` was CALLED on 3 of 3
                # runs and the report said it was surfaced on 0 of 3, because the model
                # called it in pass 1 and the final pass — the one whose surface survived
                # — no longer advertised it. "Called a tool it was never shown" is an
                # impossible reading that a single sample made look real.
                out["surfaces"].append(ev.get("value") or {})
                out["surface"] = ev.get("value")
            elif t == "TOOL_CALL_RESULT":
                # 🔴 WITHOUT THE RESULT, A FAILED WRITE AND A SUCCESSFUL ONE ARE THE SAME EVENT.
                # book_chapter_create was called with a book id that does not exist, the approval
                # was granted, and the harness recorded "called + approved, no error" — because it
                # was only reading START/ARGS/END. The tool's own answer is the only thing that
                # separates "it refused" from "it wrote nothing and said ok".
                out["results"].append({"id": ev.get("toolCallId"),
                                       "content": str(ev.get("content"))[:4000]})
                out["tool_calls"].append(ev)
            elif t in ("TOOL_CALL_START", "TOOL_CALL_END", "TOOL_CALL_ARGS"):
                out["tool_calls"].append(ev)
                # TOOL_CALL_ARGS arrives as JSON deltas keyed by call id; the approval card
                # is only readable once they are joined.
                if t == "TOOL_CALL_ARGS":
                    cid = ev.get("toolCallId")
                    if cid:
                        out["_args"][cid] = out["_args"].get(cid, "") + (ev.get("delta") or "")
            elif t == "RUN_FINISHED":
                # 🔴 THE RESUME ID LIVES HERE, NOT ON RUN_STARTED. `RUN_FINISHED.result
                # .pendingToolCall` carries {runId, toolCallId, toolName} and it is the ONLY
                # id the resume accepts — chat-service stores the suspension under a run id of
                # its own, which is NOT the one RUN_STARTED announced. Posting the RUN_STARTED
                # id made load_suspended_run miss, and every approval came back "This
                # suggestion has expired. Please ask again." on 9 of 9 runs, with the store
                # unchanged. A flawless, reproducible, entirely self-inflicted failure that
                # read exactly like a broken approve button. runChatStream.ts reads this field
                # and nothing else; so does this.
                res = (ev.get("result") or {})
                out["status"] = res.get("status")
                p = res.get("pendingToolCall")
                if isinstance(p, dict):
                    out["pending"] = p
            elif t == "RUN_ERROR":
                out["error"] = str(ev)[:300]
    return True


def pending_approval(out) -> dict | None:
    """The suspension this turn ended on, if any — read from the server's own statement of it.

    🔴 A SUSPENDED RUN IS NOT A QUIET RUN, AND READING IT AS ONE INVERTS THE WHOLE WRITE BAR.
    When a Tier-A tool is not on the user's allowlist the run SUSPENDS: the stream ends normally,
    the store is untouched, and nothing errored. A harness that does not look for the card reads
    that as "the model declined to write" — so every write tool in the catalogue would report a
    clean, empty, entirely fictional result, and 153 of 315 tools are Tier A.
    """
    p = out.get("pending")
    if not isinstance(p, dict) or not p.get("runId"):
        return None
    card = {"run_id": p["runId"], "tool_call_id": p.get("toolCallId"),
            "tool": p.get("toolName"), "kind": "frontend_tool"}
    # The card's own args say whether this is the Tier-A approval prompt or an ordinary
    # frontend-tool proposal; the two resume through the same endpoint with different outcomes.
    raw = (out.get("_args") or {}).get(p.get("toolCallId") or "")
    if raw:
        try:
            a = json.loads(raw)
            if isinstance(a, dict):
                card["kind"] = a.get("kind") or card["kind"]
                card["tier"] = a.get("tier")
                card["proposed_tool"] = a.get("tool")
        except ValueError:
            pass
    return card


async def send_turn(client, auth, session_id, content, *, book_id=None, chapter_id=None,
                    thinking=False, effort="off", timeout=180.0,
                    permission_mode="write", approve=None, max_approvals=3):
    """One real turn, including the approvals a user would have clicked.

    `approve` is the outcome to send when the run suspends on a Tier-A card — `approved_once`,
    `approved_always`, `denied`, `denied_always`, or None to leave it suspended. None is the
    DEFAULT and read-intent scenarios must keep it: approving on a turn that only asked to look
    would make the harness itself the thing that wrote, and the store diff would then be evidence
    about me rather than about the product.
    """
    body = {"content": content, "thinking": thinking, "reasoning_effort": effort,
            # The FE sends this on every message (useChatMessages, default 'write'); omitting it
            # falls back to the ACCOUNT pref before 'write', so a harness that leaves it out runs
            # in whatever mode the account happens to carry while the browser runs in the mode
            # the user picked. Currently identical on this account (behavior={}), which is
            # exactly why it would have gone unnoticed.
            "permission_mode": permission_mode}
    if book_id and chapter_id:
        body["editor_context"] = {"book_id": book_id, "chapter_id": chapter_id}
    if book_id:
        body["book_context"] = {"book_id": book_id}

    out = {"text": "", "tool_calls": [], "surface": None, "surfaces": [], "run_id": None,
           "events": Counter(), "error": None, "_args": {}, "approvals": [],
           "pending": None, "status": None, "results": []}
    url = f"{BASE}/v1/chat/sessions/{session_id}/messages"
    for attempt in (1, 2):
        try:
            if await _drain(client, auth, "POST", url, body, out, timeout):
                break
        except httpx.HTTPError as e:
            if attempt == 2:
                out["error"] = f"{type(e).__name__}: {e}"
                return out

    # Resume loop — one pass per card, capped. The cap is not politeness: a model that
    # re-proposes the same write after every approval would otherwise run forever, and an
    # unbounded approver is indistinguishable from a harness that wants the write to happen.
    for _ in range(max_approvals if approve else 0):
        card = pending_approval(out)
        if not card:
            break
        out["approvals"].append({"tool": card.get("proposed_tool") or card["tool"],
                                 "outcome": approve, "kind": card["kind"]})
        resume_run_id = card["run_id"]
        out["_args"] = {}
        out["pending"] = None
        try:
            ok = await _drain(
                client, auth, "POST",
                f"{BASE}/v1/chat/sessions/{session_id}/tool-results",
                {"run_id": resume_run_id, "tool_call_id": card["tool_call_id"],
                 "outcome": approve},
                out, timeout)
            if not ok:
                break
        except httpx.HTTPError as e:
            out["error"] = f"resume {type(e).__name__}: {e}"
            break
    out["pending_approval"] = pending_approval(out)
    return out


async def run_scenario(client, auth, sc, idx, fx):
    """One scenario, one repetition, in its OWN session AND its OWN book.

    The session is per-repeat so repeats cannot contaminate each other through conversation
    history. The BOOK is per-repeat for the same reason one level down: if repeat 1 writes
    when it should not have, repeat 2 would otherwise start from the damaged store and its
    own diff would come back empty — the defect would appear to happen once and then heal.
    Per-repeat books make the distribution honest: "3 of 5 runs wrote" is a sentence the
    harness can actually support.
    """
    sess = await _json(client, auth, "POST", "/v1/chat/sessions", json={
        # `user_model`, NOT `user`. Guessed wrong once and every turn 502'd with
        # "credential resolution failed" from provider-registry — the session was created
        # happily (201) and only the TURN failed, so the harness reported it as a model
        # failure. Read from the working session's own row rather than invented.
        "model_source": sc.get("model_source", "user_model"),
        "model_ref": sc["model_ref"],
        "title": f"loop {sc['id']} #{idx}",
        **({"book_id": fx.book_id} if fx.book_id else {}),
    })
    sid = sess.get("session_id") or sess.get("id")
    # editor_context says "the user is looking at THIS chapter", and that is not a neutral
    # detail: with it set, "write a chapter" plausibly means "write THIS chapter's prose", which
    # is exactly what the model did (save_draft, 3/3). A scenario about creating a chapter has to
    # be able to run from the chat panel, where no chapter is open.
    res = await send_turn(client, auth, sid, sc["prompt"],
                          book_id=fx.book_id,
                          chapter_id=fx.chapter_id if sc.get("editor_context", True) else None,
                          permission_mode=sc.get("permission_mode", "write"),
                          approve=sc.get("approve"))
    res["session_id"] = sid
    res["scenario"] = sc["id"]
    res["rep"] = idx
    res["book_id"] = fx.book_id
    res["project_id"] = fx.project_id
    return res


async def main_async(scenarios, repeats, concurrency, approval_mode="none"):
    auth = Auth(*read_credential())
    sem = asyncio.Semaphore(concurrency)
    results = []

    # 🔴 SWEEP BEFORE, NOT ONLY AFTER. 16 fixtures leaked from one batch when teardown failed,
    # and on the next run the model found one through `book_list` and proposed writes into it. A
    # leaked fixture is not litter — it is an extra, plausible, wrongly-scoped write target
    # sitting on the account, and it makes the NEXT batch's evidence unattributable.
    from provision import sweep_orphans
    swept = await asyncio.to_thread(sweep_orphans)
    if swept:
        print(f"swept {len(swept)} leaked fixture(s) from a previous run before starting")

    async with httpx.AsyncClient(timeout=180.0) as client:
        await auth.login(client)
        print(f"authenticated as {auth.email} ({auth.user_id})")

        async def one_repeat(sc, i):
            """Provision, run, measure, tear down — one independent repetition.

            🔴 THE FIXTURE IS BUILT AND TORN DOWN INSIDE THE MEASURED UNIT, and the snapshot
            is taken AFTER seeding. If the seed were inside the before/after window, every
            scenario would report a store change and the DATA bar would be meaningless —
            the harness would flag its own setup as the defect.

            MCPDirect calls asyncio.run internally, so provisioning cannot happen on this
            event loop; to_thread keeps the scenarios genuinely concurrent instead of
            serialising them behind a nested-loop error.
            """
            fx = None
            try:
                fx = await asyncio.to_thread(
                    lambda: Throwaway(f"{sc['id']}-{i}").build(seed=sc.get("seed") or []))
                before = await asyncio.to_thread(snapshot, fx.book_id)
                try:
                    r = await run_scenario(client, auth, sc, i, fx)
                except Exception as e:  # noqa: BLE001 — one bad repeat must not kill the run
                    r = {"scenario": sc["id"], "rep": i, "text": "", "tool_calls": [],
                         "surface": None, "surfaces": [], "error": f"{type(e).__name__}: {e}"}
                after = await asyncio.to_thread(snapshot, fx.book_id)
                r["store"] = {"before": before, "after": after}
                r["store_diff"] = store_diff(before, after)
                return r
            except Exception as e:  # noqa: BLE001 — a provisioning failure is REPORTED, never
                # silently skipped: a scenario that vanishes from the report reads as passing.
                return {"scenario": sc["id"], "rep": i, "text": "", "tool_calls": [],
                        "surface": None, "surfaces": [], "store_diff": {},
                        "error": f"PROVISION {type(e).__name__}: {e}"}
            finally:
                if fx is not None and not KEEP_FIXTURES:
                    try:
                        await asyncio.to_thread(fx.teardown)
                        if not await asyncio.to_thread(fx.is_gone):
                            LEAKED.append(fx.book_id)
                    except Exception as e:  # noqa: BLE001
                        LEAKED.append(fx.book_id)
                        print(f"\n  ! teardown failed for {fx.book_id}: {e}")

        async def scenario_block(sc):
            """One scenario: K independent repeats, sequential.

            🔴 CONCURRENCY IS ACROSS SCENARIOS, NEVER ACROSS REPEATS OF ONE. Repeats are
            sequential so the local model serves them one at a time — overlapping them on a
            single GPU turns a latency measurement into a queueing measurement, and a turn
            that times out behind three others reads as "the model did not call the tool".
            """
            async with sem:
                out = []
                for i in range(repeats):
                    r = await one_repeat(sc, i)
                    out.append(r)
                    print("!" if r.get("error") else ".", end="", flush=True)
                return out

        blocks = await asyncio.gather(*[scenario_block(sc) for sc in scenarios])
        for grp in blocks:
            results.extend(grp)
    print()
    if LEAKED:
        print(f"!! {len(LEAKED)} FIXTURE(S) SURVIVED TEARDOWN: {chr(44).join(LEAKED[:5])}")
        print("   Clean up: python scripts/toolloop/provision.py --sweep")
        print("   A leaked fixture becomes a book the model can find via book_list and "
              "write into on the NEXT batch — which is how a cross-book write got into "
              "this evidence.")
    return results


def called_names(r) -> set:
    """The tools the model actually invoked.

    Reads TOOL_CALL_START's own name field rather than searching the serialised events for the
    string. A substring search over the dump counts a tool as "called" when its name merely
    appears inside another call's ARGUMENTS — and `tool_load` takes tool names as arguments, so
    that false positive fires on exactly the discovery path this loop spends its time in.
    """
    out = set()
    for e in (r.get("tool_calls") or []):
        n = e.get("toolCallName") or e.get("toolName") or e.get("name")
        if n:
            out.add(n)
    return out


def surfaced_names(r) -> set:
    """Every tool advertised in ANY pass of the turn — core, frontend and activated alike."""
    out = set()
    for s in (r.get("surfaces") or ([r["surface"]] if r.get("surface") else [])):
        adv = (s or {}).get("advertised") or {}
        for bucket in adv.values():
            if isinstance(bucket, list):
                out.update(str(x) for x in bucket)
    return out


def report(results, scenarios, repeats):
    by = {sc["id"]: sc for sc in scenarios}
    print(f"\n{'scenario':<28} {'runs':<5} {'tool called':<12} {'surface has tool':<17} {'err':<7} store")
    print("-" * 108)
    for sid, sc in by.items():
        rs = [r for r in results if r.get("scenario") == sid]
        want = sc.get("expect_tool")
        called = sum(1 for r in rs if want and want in called_names(r))
        surfaced = sum(1 for r in rs if want and want in surfaced_names(r))
        errs = sum(1 for r in rs if r.get("error"))
        susp = sum(1 for r in rs if r.get("pending_approval"))
        # Each repeat has its OWN book, so each diff belongs to exactly one turn. Reporting
        # the COUNT rather than the first non-empty one is the difference between "the store
        # changed at some point" and "2 of 5 turns wrote" — only the second is a distribution,
        # and a stochastic consumer can only be described by a distribution.
        wrote = [r for r in rs if r.get("store_diff")]
        tables = sorted({t for r in wrote for t in (r.get("store_diff") or {})})
        store = (f"WROTE {len(wrote)}/{len(rs)}: " + ", ".join(tables)) if wrote else "unchanged"
        print(f"{sid:<28} {len(rs):<5} {f'{called}/{len(rs)}':<12} "
              f"{f'{surfaced}/{len(rs)}':<17} {errs:<7} {store}")
        if susp:
            print(f"    ^ left SUSPENDED on a Tier-A approval card in {susp}/{len(rs)} runs "
                  f"— not a refusal by the model, a card waiting for a click")
        if wrote and sc.get("intent") == "read":
            # The strongest assertion in the loop, and it needs no per-tool knowledge: a turn
            # that asked to LOOK must not change anything. Measured 2026-08-13: five read
            # turns took outline_node from 3 to 6 while the reply called it "your current
            # plan".
            print(f"    ^ READ-INTENT TURN WROTE TO THE STORE in {len(wrote)}/{len(rs)} runs "
                  f"— a defect whatever it said")
    print("\nA scenario is only informative across REPEATS — the consumer is stochastic, so "
          "'1/5 called' is a finding and '5/5 surfaced, 0/5 called' is a different finding "
          "from '0/5 surfaced'.")


APPROVAL_MODE = "none"
#: Investigation only. A kept fixture is a book left on the account, so the sweep in
#: provision.py --sweep is the way back.
KEEP_FIXTURES = False
#: Fixtures that survived their own teardown. Reported at the END of the run — a warning
#: printed mid-stream is a warning I scrolled past, and I did: 16 leaked books went
#: unnoticed for an hour, and one became a write target in the next batch.
LEAKED: list = []


def emit_batch(results, scenarios, batch_id: str) -> dict:
    """Write the gate's evidence file FROM THE RUN, never by hand.

    🔴 THE FIELDS THE GATE CHECKS MUST BE MACHINE-FILLED. The bar says "never a typed count",
    and a batch file I author by hand is precisely where a typed count enters: I would be
    copying the store diff out of a terminal into the evidence that is then used to prove the
    store diff. The run writes what it measured; I only ever add the fields that require
    judgement (falsifier, defects, invariant, ship_audit), and those are the fields the gate
    checks for PRESENCE rather than for truth.

    One tool row per scenario, because a scenario is the unit that has an expected tool and an
    intent. Runs carry their own store snapshots — with a book per repeat, every diff belongs to
    exactly one turn.
    """
    by = {sc["id"]: sc for sc in scenarios}
    tools = []
    for sid, sc in by.items():
        rs = [r for r in results if r.get("scenario") == sid]
        runs = []
        for r in rs:
            runs.append({
                "via": "fe_runner",
                "rep": r.get("rep"),
                "book_id": r.get("book_id"),
                "session_id": r.get("session_id"),
                "prompt": sc["prompt"],
                "called": sc.get("expect_tool") in called_names(r),
                "surfaced": sc.get("expect_tool") in surfaced_names(r),
                "called_tools": sorted(called_names(r)),
                "error": r.get("error"),
                # A suspended run has no error, no store change and a perfectly calm reply.
                # Recording the card is what stops that reading as "the model declined to write".
                "approvals": r.get("approvals") or [],
                "left_suspended": bool(r.get("pending_approval")),
                "store": r.get("store") or {},
                "store_diff": r.get("store_diff") or {},
                "answer": (r.get("text") or "")[:2000],
            })
        tools.append({
            "tool": sc.get("expect_tool"),
            "scenario": sid,
            "intent": sc.get("intent"),
            # Judgement fields ride through from the SCENARIO SPEC rather than being edited into
            # the evidence file afterwards. Hand-editing the file the gate reads puts my
            # keyboard on both sides of the check — the measured fields and the asserted ones
            # would live in the same document, one save away from each other.
            "falsifier": sc.get("falsifier"),
            "ship_audit": sc.get("ship_audit"),
            "defects": sc.get("defects") or [],
            "runs": runs,
            "surfaced_count": sum(1 for r in runs if r["surfaced"]),
            "called_count": sum(1 for r in runs if r["called"]),
            "wrote_count": sum(1 for r in runs if r["store_diff"]),
            "suspended_count": sum(1 for r in runs if r["left_suspended"]),
        })
    return {"batch": batch_id, "generated_by": "fe_runner",
            "approval_mode": APPROVAL_MODE, "tools": tools}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--out", default="")
    ap.add_argument("--batch-out", default="", help="gate-ready evidence file")
    ap.add_argument("--batch-id", default="batch")
    ap.add_argument("--keep-fixtures", action="store_true",
                    help="do not tear down (investigation); clean up with provision.py --sweep")
    ap.add_argument("--approvals", default="none", choices=("none", "standing", "as-is"),
                    help="standing tool approvals for this batch; 'none' clears and restores")
    a = ap.parse_args()
    scenarios = json.loads(pathlib.Path(a.scenarios).read_text(encoding="utf-8"))["scenarios"]
    globals()["APPROVAL_MODE"] = a.approvals
    globals()["KEEP_FIXTURES"] = a.keep_fixtures
    with ApprovalState(a.approvals):
        results = asyncio.run(main_async(scenarios, a.repeats, a.concurrency, a.approvals))
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(results, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
        print(f"raw results -> {a.out}")
    if a.batch_out:
        pathlib.Path(a.batch_out).write_text(
            json.dumps(emit_batch(results, scenarios, a.batch_id), indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"gate evidence -> {a.batch_out}")
    report(results, scenarios, a.repeats)


if __name__ == "__main__":
    sys.exit(main())
