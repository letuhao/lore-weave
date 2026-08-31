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
import datetime as _dt
import json
import os
import pathlib
import re
import sys
from collections import Counter

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from store_snapshot import diff as store_diff, snapshot, SnapshotUnavailable  # noqa: E402
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


#: Seconds a single TURN may take before the client gives up. 180 was hard-coded, and seven arms
#: of translation_update_settings were lost to it before anyone looked: that prompt PINS RAILS
#: (measured in chat-service's log — "intent pinned workflow(s) ['translation-pass']", plus
#: vision-to-book at 0/9), the server drives them step by step, and the turn outruns the budget.
#: The client disconnects, the run records "upstream sent 'error' with no error message", and it
#: reads as a provider fault. It is not one — it is this number.
TURN_TIMEOUT = 180.0


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
                # 🔴 A UNION CANNOT DATE A CHOICE. `surfaced` is the union of every pass, so a
                # tool advertised only AFTER the model committed to a pipeline still reads
                # "surfaced 5/5". The timeline interleaves surfaces with calls in arrival order,
                # which is the only way to ask "was it on the wire when the model chose".
                _adv = (ev.get("value") or {}).get("advertised") or {}
                _names = {str(x) for b in _adv.values() if isinstance(b, list) for x in b}
                out["timeline"].append({"surface": sorted(_names)})
            elif t == "TOOL_CALL_RESULT":
                # 🔴 WITHOUT THE RESULT, A FAILED WRITE AND A SUCCESSFUL ONE ARE THE SAME EVENT.
                # book_chapter_create was called with a book id that does not exist, the approval
                # was granted, and the harness recorded "called + approved, no error" — because it
                # was only reading START/ARGS/END. The tool's own answer is the only thing that
                # separates "it refused" from "it wrote nothing and said ok".
                # 🔴 THE CAP WAS 4000 AND SAID NOTHING, AND IT BIT THREE TIMES IN ONE SESSION.
                # 676 of the 4,690 tool results on disk (14.4%) sit exactly at 4000 and end
                # mid-token; ALL 676 fail json.loads. Every sweep that parses a result was
                # therefore under-counting, and always in the direction that looks like a
                # finding: an empty parse reads as "the tool returned nothing", not as "the
                # recording is clipped". It cost a false provenance defect twice
                # (kg_build 0/10, composition_arc_apply 0/5) — both refuted by hand.
                #
                # Measured against the live tools whose results clip most: kg_project_list
                # 4,040 chars, world_list 4,273, settings_list_models 5,606,
                # glossary_list_system_standards 5,859, composition_arc_template_list 23,390.
                # The cap is set an order of magnitude above the largest of those, so today's
                # whole population is recorded COMPLETE.
                #
                # And the length is recorded whether or not it clipped, so a clipped read can
                # never again be mistaken for a short result. THAT is the durable half: a cap
                # can always be exceeded, and a truncation that does not announce itself is
                # indistinguishable from data.
                _content = str(ev.get("content"))
                out["results"].append({"id": ev.get("toolCallId"),
                                       "content": _content[:RESULT_CAP],
                                       "content_length": len(_content),
                                       "truncated": len(_content) > RESULT_CAP})
                out["tool_calls"].append(ev)
            elif t in ("TOOL_CALL_START", "TOOL_CALL_END", "TOOL_CALL_ARGS"):
                out["tool_calls"].append(ev)
                if t == "TOOL_CALL_START":
                    _n = ev.get("toolCallName") or ev.get("toolName") or ev.get("name")
                    if _n:
                        out["timeline"].append({"call": str(_n)})
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
                    thinking=False, effort="off", timeout=None,
                    permission_mode="write", approve=None, max_approvals=3,
                    enabled_skills=None, editor_context_extra=None, studio_context=None):
    """One real turn, including the approvals a user would have clicked.

    🔴 `timeout=None` MEANS "READ THE GLOBAL NOW", AND THE DEFAULT USED TO BE `TURN_TIMEOUT`
    ITSELF — which binds at IMPORT, so `--turn-timeout` set the module global long after this
    signature had frozen the old value, and the flag reached the AsyncClient but never the
    per-turn request that overrides it. The flag was inert.

    That is not a cosmetic bug. D-THE-MOTIF-LINK-SCENARIO-TIMES-OUT-6-OF-10 records "raising the
    per-turn timeout to 300s changed nothing: 3 of 5 both times" as evidence that the timeouts
    are not a slow turn. The experiment never ran at 300s; it ran at 180 both times. That
    conclusion is UNSUPPORTED and is re-opened on the row.

    `approve` is the outcome to send when the run suspends on a Tier-A card — `approved_once`,
    `approved_always`, `denied`, `denied_always`, or None to leave it suspended. None is the
    DEFAULT and read-intent scenarios must keep it: approving on a turn that only asked to look
    would make the harness itself the thing that wrote, and the store diff would then be evidence
    about me rather than about the product.
    """
    # Resolved HERE, not in the signature: see the note above. `None` is the only value that
    # can mean "whatever --turn-timeout set", because a default is evaluated once at import.
    if timeout is None:
        timeout = TURN_TIMEOUT
    body = {"content": content, "thinking": thinking, "reasoning_effort": effort,
            # The FE sends this on every message (useChatMessages, default 'write'); omitting it
            # falls back to the ACCOUNT pref before 'write', so a harness that leaves it out runs
            # in whatever mode the account happens to carry while the browser runs in the mode
            # the user picked. Currently identical on this account (behavior={}), which is
            # exactly why it would have gone unnoticed.
            "permission_mode": permission_mode}
    # 🔴 THE HARNESS COULD NOT PIN A SKILL, AND FIVE TOOLS ARE UNREACHABLE WITHOUT ONE.
    # INTENT_GATED_SETUP_TOOLS (glossary_adopt_standards, glossary_propose_kinds, glossary_plan,
    # glossary_propose_batch, glossary_book_sync_apply) are filtered out of the TURN CATALOG
    # unless the turn carries world-setup intent — signalled by the `glossary_shaping` skill,
    # which skill_registry injects when `"glossary" in enabled_skills`. The gate is deliberate
    # and measured (a co-writer once rebuilt a newcomer's ontology on a plain "write chapter 1"
    # turn), and its own principle is that "guidance and capability move as ONE signal".
    #
    # The FE sends enabled_skills on every message; this harness never did, so it could only
    # ever observe the gated half of that signal. Without it those five tools cannot be measured
    # at all — not because the product cannot reach them, but because the instrument cannot
    # construct the state the product requires.
    if enabled_skills:
        body["enabled_skills"] = list(enabled_skills)
    if book_id and chapter_id:
        body["editor_context"] = {"book_id": book_id, "chapter_id": chapter_id}
        if editor_context_extra:
            # D-PROPOSE-EDIT-ACTS-ON-EDITOR-STATE-THE-TURN-CANNOT-SEE — a live browser sends
            # has_selection/selected_text alongside book_id/chapter_id (context/editorBridge.ts's
            # getEditorTarget().handle.getSelection(), snapshotted at send time). This harness
            # drives no editor, so a scenario states the fact directly via `editor_context_extra`
            # rather than the harness guessing what a real selection would have been.
            body["editor_context"].update(editor_context_extra)
    if book_id:
        body["book_context"] = {"book_id": book_id}
    if studio_context is not None:
        # D-A-FEDERATED-TOOL-DUPLICATED-BY-AN-ALWAYS-ON-CONSUMER-LOCAL-TWIN — the Studio Compose
        # panel sends studio_context alongside editor_context (ComposePanel.tsx). This harness
        # simulated only the legacy chapter editor's shape until now, so no scenario could ever
        # reach the _wf_surface="studio" branch — the very thing the fix under test depends on.
        # book_id is filled in from the already-resolved fixture (like editor_context's own),
        # not from the scenario JSON — a scenario cannot know the throwaway book's real id.
        body["studio_context"] = {**({"book_id": book_id} if book_id else {}), **studio_context}

    out = {"text": "", "tool_calls": [], "surface": None, "surfaces": [], "run_id": None,
           "events": Counter(), "error": None, "_args": {}, "approvals": [],
           "pending": None, "status": None, "results": [], "timeline": []}
    url = f"{BASE}/v1/chat/sessions/{session_id}/messages"
    for attempt in (1, 2):
        try:
            if await _drain(client, auth, "POST", url, body, out, timeout):
                break
        except httpx.HTTPError as e:
            if attempt == 2:
                out["error"] = f"{type(e).__name__}: {e}"
                # 🔴 CAPTURED HERE, WHERE THE ERROR IS ACTUALLY RECORDED. The first attempt at
                # this hooked `run_scenario`, which never sees the exception: BOTH handlers in
                # this function swallow it into `out["error"]` and return. A forced-timeout run
                # proved it — 3 of 3 genuine ReadTimeouts and `dead_turn: null` on every one.
                out["dead_turn"] = capture_dead_turn(session_id, book_id=book_id)
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
                 "outcome": _resume_outcome(card.get("kind"), approve)},
                out, timeout)
            if not ok:
                break
        except httpx.HTTPError as e:
            out["error"] = f"resume {type(e).__name__}: {e}"
            out["dead_turn"] = capture_dead_turn(session_id, book_id=book_id)
            break
    out["pending_approval"] = pending_approval(out)
    return out


def _resume_outcome(kind: str | None, approve: bool) -> str:
    """The outcome STRING this card kind expects — never a bool.

    🔴 THE HARNESS WAS POSTING `outcome: true` AND EVERY APPROVAL 422'd. `ToolResultRequest`
    declares `outcome: str | None`, so a boolean is rejected outright — measured on batch 5,
    where memory_remember was called 3/3, suspended 3/3, and wrote nothing on any run. Read as
    a product result that would have been "the tool reports success and stores nothing", which
    is a defect class this loop has filed before; it was the harness.

    The 422 is the LUCKY failure. `stream_service` resolves the decision with
    `outcome if outcome in ("approved_once", "approved_always", "denied", "denied_always")
    else "denied"` — so any unrecognised string is silently a DENIAL. A harness that sent
    "approve" or "yes" would have denied every card while reporting that it approved them, and
    the store diff would have been empty for a reason nothing in the evidence could show.

    The two card families take different vocabularies, so the kind decides:
      tool_approval (Tier A/W gate) -> approved_once | denied
      frontend-tool cards (propose_edit, glossary_propose_entity_edit) -> applied | dismissed
    """
    if kind == "tool_approval":
        return "approved_once" if approve else "denied"
    return "applied" if approve else "dismissed"


#: The error populations "the transport stall" turns out to be. Keyed by (error kind, did the
#: turn emit ANY tool call) — the two axes D-THE-TRANSPORT-STALL-IS-THREE-DIFFERENT-FAILURES
#: split on, because a cause that explains one third looks REFUTED by the other two when they
#: are counted as one number. Thirteen hypotheses were tested against the mixed population.
ERROR_POPULATIONS = (
    "provision",                  # the SEED could not build the fixture — not the platform
    "no_output_timeout",          # ReadTimeout, ZERO tool calls: nothing was produced at all
    "timeout_after_call",         # ReadTimeout after the turn had already called something
    "upstream_silent_no_call",    # provider failed without saying why, before any call
    "upstream_silent_after_call",  # provider failed without saying why, MID-turn
    "other",
)


def error_population(err: str | None, tool_call_count: int) -> str | None:
    """Which of the populations an errored run belongs to, or None when it did not error.

    Derived from what the record already holds, so every batch labels its own errors instead of
    waiting for someone to split 121 of them by hand. Re-derived 2026-08-27 over the corpus:

        provision                    25      upstream_silent_after_call   45
        no_output_timeout            30      upstream_silent_no_call      13
        timeout_after_call            8      other                         0

    The row's table showed 5 zero-call upstream errors; there are 13. Same error string in both
    cells — "upstream sent 'error' with no error message" — and the tool-call count is the only
    thing that separates them.
    """
    if not err:
        return None
    e = str(err)
    if e.startswith("PROVISION") or "ProvisionError" in e:
        return "provision"
    silent = "upstream sent" in e and "no error message" in e
    timeout = "ReadTimeout" in e
    if timeout:
        return "timeout_after_call" if tool_call_count else "no_output_timeout"
    if silent:
        return "upstream_silent_after_call" if tool_call_count else "upstream_silent_no_call"
    return "other"


def retry_gap_verdict(rows_by_role: dict) -> dict:
    """How long the client waited before retrying, and whether that was its REAL budget.

    A NAMED function rather than an inline block, because the guard for it has to call the
    SHIPPED rule — the first version of that guard re-derived the gap itself and greped the
    source for `TURN_TIMEOUT`, so BOTH falsifiers (hard-code the threshold, stop recording the
    gap) stayed green. A test that recomputes what it is checking cannot fail when that
    computation changes.
    """
    u = (rows_by_role or {}).get("user") or {}
    if not (u.get("first") and u.get("last")) or u.get("n", 0) <= 1:
        return {}
    try:
        from datetime import datetime  # noqa: PLC0415
        a = datetime.fromisoformat(str(u["first"]).replace("+00", "+00:00"))
        b = datetime.fromisoformat(str(u["last"]).replace("+00", "+00:00"))
    except (ValueError, TypeError) as e:
        return {"retry_gap_error": f"{type(e).__name__}: {e}"[:120]}
    gap = round((b - a).total_seconds(), 1)
    # ORGANIC means the client waited out the budget it actually had. A gap far below it means
    # the deadline was artificially short — an instrument test, not a dead turn. Derived from
    # TURN_TIMEOUT rather than a constant, so the label cannot go stale when the budget moves.
    return {"retry_gap_s": gap, "organic_timeout": gap >= 0.5 * (TURN_TIMEOUT or 180)}


def capture_dead_turn(session_id: str, since: str = "20m", book_id: str | None = None) -> dict:
    """Everything a TIMED-OUT turn leaves behind, captured AT THE MOMENT it happens.

    🔴 THE EVIDENCE IS GONE BY THE TIME ANYONE LOOKS, and that is the whole reason
    D-THE-MOTIF-LINK-SCENARIO-TIMES-OUT-6-OF-10 has an unexplained residual. Its own record
    says so twice: the original sessions' logs had ROTATED before they were read, and two
    later batches run with `docker logs -f` open both came back 0/5 — at a 10% rate, catching
    one is a lottery and a scenario batch is not a cheap way to buy a ticket.

    So the capture stops being a thing someone runs afterwards and becomes a thing the failure
    does to itself. Two readings, both cheap, both taken only on the error path:

      * THE STORE SIGNATURE the row already identified — a timed-out session holds TWO user
        rows about TURN_TIMEOUT apart (the runner's retry) and ZERO assistant rows. "The turn
        produced nothing, twice" is a different fact from "the tool was slow", and the counts
        say which.
      * THE SERVICE LOG for this session id, from the last `since` window.

    Best-effort by construction: a capture that raises would replace a timeout with a harness
    crash and destroy the very run it exists to explain."""
    out: dict = {"session_id": session_id, "book_id": book_id}
    try:
        from provision import oracle  # noqa: PLC0415 — the oracle lives beside the loop
        rows = oracle.db_query(
            CHAT_DB,
            "SELECT role, count(*), min(created_at)::text, max(created_at)::text "
            f"FROM chat_messages WHERE session_id = '{session_id}' GROUP BY role")
        out["rows_by_role"] = {r[0]: {"n": int(r[1]), "first": r[2], "last": r[3]}
                               for r in rows if len(r) >= 4}
        # 🔴 A SESSION THAT DOES NOT EXIST HAS NO ASSISTANT ROW EITHER, and reporting the same
        # signature for both would hand a later reader a dead-turn diagnosis for a session id
        # that was never created. The signature is USER ROWS WITH NO ANSWER — which is also
        # exactly what the row measured: two user rows about TURN_TIMEOUT apart, zero assistant.
        out["user_rows"] = out["rows_by_role"].get("user", {}).get("n", 0)
        out["no_assistant_row"] = bool(out["user_rows"]) and "assistant" not in out["rows_by_role"]
        # 🔴 THE GAP IS WHAT SEPARATES A DEFECT FROM A DEMONSTRATION, and without it every
        # capture reads the same. Measured across the 13 captures on disk 2026-08-27: ten sit
        # at 178.9s — the runner's retry after a genuine TURN_TIMEOUT — and three sit at 0.7s,
        # because the batch that PROVED this instrument forced its timeouts with a sub-second
        # read deadline. All thirteen otherwise carry an identical signature (two user rows, no
        # assistant row, surface advertised, orphaned turn), so a reader counting captures would
        # have read three demonstrations as three instances of the defect. I did, for a minute.
        out.update(retry_gap_verdict(out["rows_by_role"]))
    except (RuntimeError, OSError, ValueError, IndexError) as e:
        out["store_error"] = f"{type(e).__name__}: {e}"[:200]
    try:
        import subprocess  # noqa: PLC0415
        p = subprocess.run(["docker", "logs", "--since", since, "infra-chat-service-1"],
                           capture_output=True, text=True, errors="replace", timeout=120)
        # Python logging goes to the container's STDERR; reading stdout alone finds nothing,
        # which is a mistake this loop has already made once against this very container.
        # 🔴 THE MOST DIAGNOSTIC LINE FOR A DEAD TURN IS NOT KEYED BY SESSION. Found the first
        # time this capture met the defect it was built for: the rail step-runner logs
        # `rail translation-pass: 0/3 steps done, next=… (book=…)` — the line that shows a rail
        # re-driving without progress — and it carries the BOOK id, not the session. Filtering
        # on the session alone returned 10 useful lines and ZERO rail lines, which is the half
        # that explains why the turn never ends.
        _keys = [k for k in (session_id, book_id) if k]
        lines = [ln for ln in (p.stdout + p.stderr).splitlines()
                 if any(k in ln for k in _keys)]
        out["log_lines"] = lines[-60:]
        out["log_line_count"] = len(lines)
    except Exception as e:  # noqa: BLE001 — never let the capture kill the run
        out["log_error"] = f"{type(e).__name__}: {e}"[:200]
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
    # 🔴 SOME DEFECTS ONLY EXIST ON TURN 2+, AND A ONE-TURN HARNESS IS BLIND TO THEM BY
    # CONSTRUCTION. DQ-T30 is the case: with two canon rules in the store, turn A (rail-driven)
    # called the tool and answered correctly, and the RE-ASK answered "one rule" from
    # conversation memory with zero tool calls. Every single-turn scenario in this harness would
    # have recorded that scenario as a clean pass on the strength of turn A.
    #
    # `follow_ups` sends further prompts in the SAME session, and THE LAST TURN IS THE MEASURED
    # ONE — the re-ask is the thing under test, not the setup that precedes it. The earlier
    # turns are kept in `prior_turns` so the evidence can show turn A worked, which is exactly
    # what makes the failure of turn B a finding rather than a broken fixture.
    # 🔴 THE PROMPT GETS THE SAME SUBSTITUTION THE SEEDS DO. It did not until 2026-08-21,
    # and batch 29 paid the whole batch for it: five ACCOUNT-scoped scenarios named their
    # fixture "Emberfall Reach {run_id}" so the world would be unique among the account's
    # 200, the seed created "Emberfall Reach a1b2c3", and the model was then asked about
    # "Emberfall Reach {run_id}" LITERALLY. Every run was measured against a world that
    # existed under a different name.
    #
    # The model was RIGHT every time — "I can't use the placeholder `{run_id}`" is the
    # invented-id guard working exactly as designed — which is what made the batch read as
    # five tool failures instead of one fixture bug. A nonce the seed expands and the prompt
    # does not is a scenario that cannot be written correctly, so it is fixed here rather
    # than worked around per scenario.
    turns = [fx.substitute_text(t) for t in (sc["prompt"], *(sc.get("follow_ups") or []))]
    assert turns[-1] == fx.substitute_text(measured_turn(sc)), (
        "measured_turn() and the turn loop disagree about which turn is measured — they are "
        "the same rule and must not drift")
    prior = []
    # ── D-THE-BEFORE-SNAPSHOT-IS-NOT-THE-STATE-THE-TURN-STARTS-FROM ────────────────────────
    # 🔴 THE RUN RECORD CARRIED NO TURN-START TIME AT ALL — `started_at` is None on every row
    # on disk — so refuting a single false flag needed a live DB query against a six-day-old
    # session, and the answer would have been gone a week later.
    #
    # Measured 2026-08-30, session 01a04fe3-bd8e-7d21-81f2-4555c920a8c7: the DATA bar flagged a
    # READ-intent scenario as a lifecycle write. The store's own timestamps refute it — the
    # composition_work row was created at 23:38:37 with `updated_at == created_at`, and the
    # turn's first message is 23:38:40 — so nothing wrote inside the measured window. The
    # `before` snapshot is taken immediately after seeding, which is right, and something still
    # replaced that row between the snapshot and the turn.
    #
    # This does NOT reshape the measured unit (that is the row's open recommendation and is not
    # taken here). It records the one fact the run was missing, so a change whose `latest`
    # PREDATES the turn can be told from one the turn caused, without an exception list.
    _turn_started_at = _dt.datetime.now(_dt.UTC).isoformat()
    try:
        r = await _drive_turns(client, auth, sc, idx, fx, sid, turns, prior)
        if isinstance(r, dict):
            r["turn_started_at"] = _turn_started_at
        return r
    except Exception as e:  # noqa: BLE001 — a BACKSTOP, not the main path
        # The two handlers inside send_turn swallow every httpx error into `out["error"]`, so
        # they carry the capture; this catches an error that escapes some OTHER way (a bad
        # session response, a JSON shape) and still has a session id to capture against.
        try:
            e.dead_turn = capture_dead_turn(sid)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        raise


async def _drive_turns(client, auth, sc, idx, fx, sid, turns, prior):
    for _ti, _prompt in enumerate(turns):
        res = await send_turn(client, auth, sid, _prompt,
                              book_id=fx.book_id,
                              chapter_id=fx.chapter_id if sc.get("editor_context", True) else None,
                              permission_mode=sc.get("permission_mode", "write"),
                              enabled_skills=sc.get("enabled_skills"),
                              editor_context_extra=sc.get("editor_context_extra"),
                              studio_context=sc.get("studio_context"),
                              approve=sc.get("approve"),
                              # 🔴 A HARNESS CONSTANT WAS DECIDING A MEASUREMENT. max_approvals
                              # defaulted to 3 with no way to say otherwise. Measured 2026-08-23 on
                              # kg_propose_edge: all five runs used EXACTLY 3, four of them landed,
                              # and the fifth spent its three on a longer chain and left its final
                              # card unapproved — reported as the tool failing 4/5. That is the
                              # same shape as `approve=None` making the tool read 0/5: a harness
                              # limit wearing the tool's name. Default unchanged, so every existing
                              # scenario measures exactly what it measured before.
                              max_approvals=int(sc.get("max_approvals", 3)))
        if _ti < len(turns) - 1:
            # 🔴 THE SURFACES OF EVERY TURN BUT THE LAST WERE THROWN AWAY, and the loop then
            # read "advertised in N of M snapshots" off what survived as if it covered the
            # session. It does not: chat-service logs the real per-pass wire set for the whole
            # session, so on 01a02e76 the log showed composition_arc_apply on 4 of 6 passes while
            # the record showed it in 0 of 6 snapshots. Both were right about different turns.
            #
            # Measured over the corpus 2026-08-27: 412 of 1,420 recorded runs are multi-turn, and
            # in 32 of those a tool PROVEN CALLED in an earlier turn appears nowhere in the
            # instrument's surface set (translation_start_job 14, composition_arc_apply 12,
            # plan_bootstrap_propose 5). That is a floor, not the total — a tool advertised and
            # not called in an earlier turn left no trace at all to count.
            #
            # Kept per PASS, because a union cannot date a choice (the same reason `timeline`
            # exists). NOT the full snapshot: `servers`, `schema_tokens`, `phase` and the counters
            # stay with the measured turn only, so an earlier turn answers "was it on the wire",
            # not "what did the inspector show".
            prior.append(prior_turn_record(_prompt, res))
    if res.get("error"):
        res["error_population"] = error_population(res["error"], len(called_names(res)))
    res["prior_turns"] = prior
    # The AUTHORITY for "was it on the wire", covering every turn — see wire_passes(). Recorded
    # beside the SSE snapshots rather than instead of them: the snapshots are what the INSPECTOR
    # showed a user, which is a different question and its own defect surface.
    res["wire_passes"] = wire_passes(sid)
    # THE STORE'S COUNT AGAINST THE WIRE'S, taken while both still exist. A gap here is
    # D-THE-PERSISTED-PER-PASS-RECORDER-DROPS-A-PASS-ON-THE-SECOND-TURN measuring itself
    # instead of waiting to be hunted; None on either side means ABSENCE, never zero.
    _logn = wire_log_pass_count(sid)
    res["pass_ledger"] = {"store": len(res["wire_passes"]), "wire_log": _logn,
                          "gap": (None if _logn is None else _logn - len(res["wire_passes"]))}
    # The measured prompt is the one the bars are read against.
    res["prompt"] = turns[-1]
    res["session_id"] = sid
    res["scenario"] = sc["id"]
    res["rep"] = idx
    res["book_id"] = fx.book_id
    res["project_id"] = fx.project_id
    res["seed_ids"] = seed_ids(fx)
    return res


def seed_ids(fx) -> dict:
    """Every id the FIXTURE created, so a cross-wired argument can be IDENTIFIED later.

    🔴 WITHOUT THIS, A CROSS-WIRE IS UNDIAGNOSABLE AFTER THE FACT — AND ONE WAS
    MISDIAGNOSED FOR A WHOLE CYCLE. composition_authoring_run_manage sent a plan_run_id that was
    a real UUIDv7 (a model cannot fabricate one: the creation timestamp is IN the id), the create
    failed with a bare 400, and the batch held nothing that could say what that id WAS. It got a
    confident blocked reason — "a run_id nothing can look up" — that was simply wrong.

    provision.py already knows all of it: `fx.project_id` and `fx.seeded`, which carries every
    seed step's RESULT. The batch writer picked fields explicitly and kept neither. So the ids are
    collected here as {value: what-it-is} — the direction a reader actually needs, because the
    question is always "the model sent THIS; what is it?" rather than "what is the project id?".
    """
    out: dict[str, str] = {}
    # EVERY id the fixture holds, not the two that were convenient. The first version of this
    # recorded book_id and project_id only, and the very first cross-wire it was built to
    # diagnose turned out to be NEITHER — leaving a map that proved the id was not the two
    # things I had guessed and could not say what it was. An identifying instrument that
    # covers part of the space produces confident eliminations and no identification.
    for attr, what in (
        ("book_id", "fixture book_id"),
        ("project_id", "fixture project_id (composition_work)"),
        ("chapter_id", "fixture chapter_id (the EDITOR CONTEXT the turn carries)"),
        ("world_id", "fixture world_id"),
        ("user_model_id", "fixture user_model_id"),
    ):
        v = getattr(fx, attr, None)
        if v:
            out.setdefault(str(v), what)
    for i, step in enumerate(fx.seeded or []):
        what = step.get("tool") or (step.get("rest") or {}).get("path") or "seed"
        _collect_uuids(step.get("result"), f"seed[{i}] {what}", out)
    return out


_UUIDISH = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _collect_uuids(node, where: str, out: dict, key: str = "", depth: int = 0) -> None:
    """Every UUID-shaped leaf in a seed result, labelled by the KEY it arrived under.

    The key is what makes the record useful: "seed[0] plan_propose_spec.run_id" identifies a
    cross-wire on sight, where a bare list of uuids would not. Bounded depth because a seed
    result is arbitrary provider JSON and this is an instrument, not a crawler. An id already
    recorded keeps its FIRST label — the fixture's own book/project names win over a seed echo.
    """
    if depth > 6:
        return
    if isinstance(node, str):
        if _UUIDISH.match(node):
            out.setdefault(node, f"{where}.{key}" if key else where)
    elif isinstance(node, dict):
        for k, v in node.items():
            _collect_uuids(v, where, out, f"{key}.{k}" if key else str(k), depth + 1)
    elif isinstance(node, list):
        for j, v in enumerate(node[:20]):
            _collect_uuids(v, where, out, f"{key}[{j}]", depth + 1)


def _other_runner_pids() -> list[int]:
    """PIDs of OTHER live fe_runner processes. Windows-aware on purpose — see the caller.

    Returns [] when it cannot tell. A probe that cannot see the thing must not be read as
    evidence the thing is absent, so this refuses to guess: an empty list means "nothing found",
    and the caller treats that as permission to run, exactly as it did before this existed.
    """
    import subprocess as _sp
    me = os.getpid()
    try:
        if sys.platform == "win32":
            out = _sp.run(["powershell", "-NoProfile", "-Command",
                           "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                           "ForEach-Object { $_.ProcessId.ToString() + '::' + $_.CommandLine }"],
                          capture_output=True, text=True, timeout=25).stdout
        else:
            out = _sp.run(["ps", "-eo", "pid,args"], capture_output=True,
                          text=True, timeout=25).stdout
    except Exception:
        return []
    pids: list[int] = []
    for line in out.splitlines():
        if "fe_runner" not in line:
            continue
        head = line.split("::")[0] if "::" in line else line.strip().split(" ")[0]
        try:
            pid = int(head.strip())
        except ValueError:
            continue
        if pid != me:
            pids.append(pid)
    return pids


async def main_async(scenarios, repeats, concurrency, approval_mode="none"):
    auth = Auth(*read_credential())
    sem = asyncio.Semaphore(concurrency)
    results = []

    # 🔴 ONE RUNNER AT A TIME, AND THIS IS CHECKED RATHER THAN ASSUMED. Measured 2026-08-23:
    # two fe_runners ran concurrently against the same harness account for several minutes because
    # the kill that was supposed to stop the first one silently did nothing — `ps aux | grep
    # fe_runner` under Git Bash does not enumerate native Windows processes, so it printed nothing
    # and "no output" was read as "stopped".
    #
    # The cost is not politeness. Two runners seed into the SAME account-scoped library, so each
    # one's store diff sees the other's writes, each one's provider calls contend with the other's
    # (PARALLEL 4 upstream), and the transport-error rate one of them measures is partly the other
    # one's load. That confound was already recorded once in this loop against
    # composition_motif_link_edit and then reintroduced by accident.
    _other = _other_runner_pids()
    if _other:
        print("REFUSED — another fe_runner is already running: " +
              ", ".join(str(x) for x in _other))
        print("  Two runners seed into the same account and each measures the other's contention.")
        print("  Stop it first. On Windows, `ps aux` does NOT see it — use:")
        print("    powershell -NoProfile -Command \"Get-CimInstance Win32_Process -Filter "
              "\\\"Name='python.exe'\\\" | Where-Object { $_.CommandLine -like '*fe_runner*' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }\"")
        raise SystemExit(2)

    # 🔴 SWEEP BEFORE, NOT ONLY AFTER. 16 fixtures leaked from one batch when teardown failed,
    # and on the next run the model found one through `book_list` and proposed writes into it. A
    # leaked fixture is not litter — it is an extra, plausible, wrongly-scoped write target
    # sitting on the account, and it makes the NEXT batch's evidence unattributable.
    from provision import (sweep_orphan_translation_jobs, sweep_orphans,
                           sweep_phantom_job_projections, sweep_archived_structure_templates)
    swept = await asyncio.to_thread(sweep_orphans)
    if swept:
        print(f"swept {len(swept)} leaked fixture(s) from a previous run before starting")
    # 🔴 AND THE JOBS THOSE FIXTURES LEFT BEHIND. sweep_orphan_translation_jobs existed and
    # NOTHING CALLED IT — it was run once by hand on 2026-08-24 (310 rows -> 6) and the debris
    # came straight back: measured 2026-08-26, 14 controllable translation jobs referencing 14
    # books, ZERO of which still existed. Every translation scenario seeds a job on its throwaway
    # book, teardown removes the book, and the job survives in another database with no FK to it.
    #
    # A one-time cleanup for a per-run leak is not a fix, and the symptom is not litter: jobs_list
    # advertises control_caps ["cancel"] for every orphan and each cancel refuses, so the next
    # batch measures the harness's own debris (D-JOBS-LIST-ADVERTISES-CANCEL-ON-JOBS-THAT-CANNOT-
    # BE-CANCELLED). Book-scoped and conservative: a job goes only when its book_id is absent
    # from loreweave_book.books.
    swept_jobs = await asyncio.to_thread(sweep_orphan_translation_jobs)
    if swept_jobs:
        print(f"swept {swept_jobs} orphaned translation job(s) whose book no longer exists")
    # 🔴 AND THE PROJECTION ROWS THE SWEEP ABOVE ORPHANS, which is a worse leak than the one it
    # repairs. Deleting a translation_jobs row leaves loreweave_jobs.job_projection untouched — a
    # different database, no FK — and job_projection is the table jobs_list actually READS.
    # Measured 2026-08-28: 92 controllable translation rows in the projection, 0 of them with a
    # job row still present, all 92 on the harness account. Every one was advertised with
    # control_caps ["cancel"] against a job that cannot be found.
    #
    # Called HERE and not only from inside the book sweep, because that function returns early
    # when no orphaned BOOKS remain — which is exactly today's state, so the 92 phantoms it had
    # already created were unreachable by their own cleanup.
    swept_phantoms = await asyncio.to_thread(sweep_phantom_job_projections)
    if swept_phantoms:
        print(f"swept {swept_phantoms} phantom job_projection row(s) whose job row is gone")
    # 🔴 AND THE ARCHIVED STRUCTURE TEMPLATES A RESTORE-DISCOVERY SCENARIO LEAVES. USER-scoped,
    # not book-scoped, so no throwaway-book teardown ever reaches them — measured 2026-08-28: one
    # seeded probe arrived alongside 32 other archived templates dated back to 2026-07-30, and the
    # model refused to guess which one the author meant among 33 candidates.
    swept_templates = await asyncio.to_thread(sweep_archived_structure_templates)
    if swept_templates:
        print(f"swept {swept_templates} archived structure_template row(s) from the harness account")

    async with httpx.AsyncClient(timeout=TURN_TIMEOUT) as client:
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
                # A seed is a CLAIM about the world; this checks it against the store before any
                # turn runs. Three scenarios in a row measured something other than what they
                # claimed, and the third inverted the reading of three experiments.
                await asyncio.to_thread(fx.assert_seeded, sc.get("seed_assert"))
                before = await asyncio.to_thread(snapshot, fx.book_id, fx.project_id, fx.world_id, fx.chapter_id, fx.user_model_id,
                    fx.run_id, auth.user_id)
                try:
                    r = await run_scenario(client, auth, sc, i, fx)
                except Exception as e:  # noqa: BLE001 — one bad repeat must not kill the run
                    r = {"scenario": sc["id"], "rep": i, "text": "", "tool_calls": [],
                         "surface": None, "surfaces": [], "error": f"{type(e).__name__}: {e}"}
                    # 🔴 AN ERRORED RUN USED TO CARRY A STRING AND NOTHING ELSE, which is why
                    # D-THE-MOTIF-LINK-SCENARIO-TIMES-OUT-6-OF-10 still has an unexplained
                    # residual: by the time anyone read the batch the service log had rotated,
                    # and two deliberate capture attempts both came back 0/5 because a 10% rate
                    # makes catching one a lottery. The failure now brings its own evidence.
                    # Every errored run labels its own population — see error_population.
                    r["error_population"] = error_population(r["error"], 0)
                    dead = getattr(e, "dead_turn", None)
                    if dead:
                        r["dead_turn"] = dead
                        r["session_id"] = dead.get("session_id")
                after = await asyncio.to_thread(snapshot, fx.book_id, fx.project_id, fx.world_id, fx.chapter_id, fx.user_model_id,
                    fx.run_id, auth.user_id)
                r["store"] = {"before": before, "after": after}
                r["store_diff"] = store_diff(before, after)
                return r
            except SnapshotUnavailable as e:
                # D-FAILED-SNAPSHOT-COUNTED-AS-A-STORE-CHANGE, the diagnosis half. The raise
                # already makes the run unusable, which is the invariant — but labelling it
                # PROVISION made the gate report "the SEED could not build the fixture", and a
                # failed AFTER snapshot has nothing to do with the seed. That is the same error
                # the gate's own comment records making once already ("A PROVISION FAILURE IS NOT
                # A TRANSPORT FAILURE, and calling it one sends the reader at the platform").
                # The verdict is identical — this is not evidence about the tool — and the
                # DIAGNOSIS is a different place to go looking.
                return {"scenario": sc["id"], "rep": i, "text": "", "tool_calls": [],
                        "surface": None, "surfaces": [], "store_diff": {},
                        "error": f"SNAPSHOT {type(e).__name__}: {e}"}
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


def compact_timeline(r, expect_tool=None) -> list:
    """Surfaces and calls in ARRIVAL ORDER, so a selection finding can be dated.

    A surface entry keeps the pass's SIZE and, because the whole set would swamp the file, only
    the advertised names that were CALLED in this turn PLUS THE TOOL UNDER TEST. That last part
    is not a detail: the tool under test is the one that was never called, so filtering to "the
    called" alone would drop the only name the question is about and every pass would look
    innocent. `surfaced_tools` beside it still carries the full union.

    Written after a third cycle in which the batch had computed the answer and kept a summary
    of it: one boolean for the surface, then no call outcomes, now no ordering.
    """
    called = called_names(r) | ({expect_tool} if expect_tool else set())
    out = []
    for e in (r.get("timeline") or []):
        if "call" in e:
            out.append({"call": e["call"]})
        else:
            names = e.get("surface") or []
            out.append({"pass_size": len(names),
                        "of_the_called": sorted(n for n in names if n in called)})
    return out


def call_records(r) -> list:
    """Each call as {tool, result_head} — enough to see a REFUSAL in the evidence file.

    The harness already keeps TOOL_CALL_RESULT content (it has to: "a failed write and a
    successful one are the same event" without it), and the batch writer kept only the tool
    NAMES. So a batch could show a tool called five times and say nothing about five refusals,
    which is how a violated falsifier sat one probe away from `proven`.

    The result head is deliberately raw and short: this is for a reader deciding whether a call
    did anything, not a parser. Args are NOT recorded here — `_args` is cleared by the approval
    loop, so anything read from it after a resume would be silently partial, and a
    half-populated argument record is worse than none.
    """
    names, out = {}, []
    for e in (r.get("tool_calls") or []):
        cid = e.get("toolCallId")
        n = e.get("toolCallName") or e.get("toolName") or e.get("name")
        if cid and n:
            names.setdefault(cid, n)
    for res in (r.get("results") or []):
        out.append({"tool": names.get(res.get("id")) or "?",
                    "result_head": (res.get("content") or "")[:300]})
    return out


#: The chat DB. `chat_messages.advertised_tools` is the recorder chat-service itself writes —
#: **one entry per model pass, appended, never replaced** — from the SAME list the chokepoint
#: hands the provider. It is the authority the wire log is printed from, it covers EVERY turn of
#: the session, and it is on disk after the run, so the harness need not scrape a container log.
CHAT_DB = "loreweave_chat"


def wire_passes(session_id: str) -> list[dict]:
    """The session's per-pass advertised sets, in order, straight from the store.

    D-HARNESS-agentSurface-DISAGREES-WITH-THE-WIRE-LOG. The SSE `agentSurface` event is NOT a
    pass: it fires on every phase transition and is SUPPRESSED on a pass whose surface did not
    change (`AgentSurfaceTracker.advertised_pass` returns None unless something moved). So a
    count of snapshots is not a count of passes in either direction, and every "advertised in N
    of M snapshots" this loop published was reading one as the other. Verified 2026-08-27 on
    01a03f32: 4 snapshots in the measured turn, 6 passes in the session, and the store's
    per-message counts (4 + 2) reproduce the wire log exactly.

    Returns [] rather than raising when the store cannot be read — a batch must not die on its
    own instrumentation, and an empty list is absence, which `wire_surfaced_names` treats as
    unknown rather than as none."""
    # 🔴 IMPORTED HERE ON PURPOSE, AND THE EXCEPT IS NARROW. A sibling counter once imported the
    # oracle inside its function, raised NameError on every call, and a bare `except Exception:
    # continue` turned that into "no rows" — a dead reader that looked exactly like an honest
    # empty. RuntimeError/OSError is a store that would not answer; anything else is a bug and
    # must reach the runner.
    from provision import oracle  # noqa: PLC0415 — the oracle lives beside the loop
    try:
        rows = oracle.db_query(CHAT_DB,
                               "SELECT sequence_num, advertised_tools::text FROM chat_messages "
                               f"WHERE session_id = '{session_id}' AND advertised_tools IS NOT NULL "
                               "ORDER BY sequence_num")
    except (RuntimeError, OSError):
        return []
    out: list[dict] = []
    for row in rows:
        if len(row) < 2:
            continue
        try:
            entries = json.loads(row[1])
        except (ValueError, TypeError):
            continue
        for e in entries or []:
            if isinstance(e, dict) and isinstance(e.get("names"), list):
                out.append({"turn": int(row[0]), "pass": e.get("pass"),
                            "names": sorted(str(x) for x in e["names"])})
    return out


def wire_log_pass_count(session_id: str, since: str = "30m") -> int | None:
    """How many passes chat-service's own INFO log printed for this session.

    D-THE-PERSISTED-PER-PASS-RECORDER-DROPS-A-PASS-ON-THE-SECOND-TURN. `advertised_tools` is
    documented as ONE ENTRY PER MODEL PASS, and on 1 of 10 live sessions it held one fewer than
    the log. Finding that took reading a container log that had already rotated on the first
    attempt — so the comparison is taken HERE, while both numbers still exist, and recorded on
    the run.

    Returns None when the log cannot be read or the window has rolled past the session, which is
    ABSENCE. A zero would claim the service printed nothing, and this loop has already once
    compared against a silently-empty log capture and drawn a conclusion from it.
    """
    try:
        import subprocess  # noqa: PLC0415
        p = subprocess.run(["docker", "logs", "--since", since, "infra-chat-service-1"],
                           capture_output=True, text=True, errors="replace", timeout=120)
        # STDERR too: python logging goes there, and reading stdout alone finds only the
        # access log — which is how a comparison silently found zero matches once already.
        n = sum(1 for ln in (p.stdout + p.stderr).splitlines()
                if "agent-surface advertised" in ln and session_id in ln)
    except Exception:  # noqa: BLE001 — an instrument must not fail the run it measures
        return None
    return n or None


def wire_surfaced_names(r) -> set:
    """Every tool on the wire in ANY pass of the WHOLE SESSION, per the store.

    This — not `surfaces` — is what an "advertised in N of M" figure must be read from."""
    return {n for p in (r.get("wire_passes") or []) for n in p.get("names") or []}


#: How much of a tool result is kept in the recorded run. See the comment at the recording
#: site: an order of magnitude above the largest result this loop's tools actually return.
RESULT_CAP = 250_000


class TruncatedResult(ValueError):
    """A recorded tool result was clipped, so parsing it would answer the wrong question."""


def parsed_result(res: dict):
    """`json.loads` a recorded tool result, REFUSING a clipped one.

    D-RECORDED-TOOL-RESULTS-ARE-TRUNCATED-AT-4000-CHARS. A bare `json.loads` on a clipped
    result raises, an analysis catches it, and the tool reads as having returned nothing —
    which is how this loop twice reported a provenance defect that did not exist. Refusing
    LOUDLY is the difference between "no evidence" and "evidence I cannot read".

    Handles the 676 records already on disk, which predate `truncated`: a pre-2026-08-27 run
    has no length field at all, and a content of EXACTLY the old 4000-char cap is the
    signature of a clip. A result that genuinely ends at 4000 would be refused too — a false
    refusal, and the safe direction, since the caller is told to re-run rather than told a
    number."""
    if res.get("truncated"):
        raise TruncatedResult(
            f"clipped at {RESULT_CAP} of {res.get('content_length')} chars")
    content = res.get("content") or ""
    if "content_length" not in res and len(content) == _LEGACY_CAP:
        raise TruncatedResult(
            f"this record predates the length field and is exactly {_LEGACY_CAP} chars — the "
            "signature of the old cap. Re-run the batch rather than parsing it.")
    return json.loads(content)


#: The cap every record written before 2026-08-27 was clipped at.
_LEGACY_CAP = 4000


def measured_turn(sc: dict) -> str:
    """The turn a scenario's bars are read against — `follow_ups[-1]` if any, else `prompt`.

    ONE HOME for a rule two other files were re-deriving. D-FE-RUNNER-MEASURES-THE-LAST-TURN-
    SO-A-PROMPT-EDIT-CAN-MISS: editing `prompt` on a scenario that declares follow_ups changes
    a turn nobody reads, and it fails SILENTLY — two prompts were rewritten on 2026-08-23 to
    ask for the tool's real action and the runs still measured 'Open the first one and show me
    its detail.' and 'Cancel that job.'. The edit was inert and the batch read as a refutation
    of it. Its sibling gate re-derived the same rule and got it WRONG in the other direction,
    judging `prompt`, which flagged 60 setup reads as defects.

    Returns the raw scenario text — substitution happens in the runner, so this is what the
    AUTHOR wrote, which is what an author needs to see."""
    fu = sc.get("follow_ups") or []
    return (fu[-1] if fu else sc.get("prompt")) or ""


def prior_turn_record(prompt: str, res: dict) -> dict:
    """What survives of a turn that is NOT the measured one.

    ONE PLACE, because the loop had inlined it and the thing it dropped was invisible there.
    `surface_passes` is a list of per-pass NAME SETS — a union cannot date a choice, the same
    reason `timeline` exists. Deliberately NOT the whole snapshot: `phase`, the counters,
    `servers` and `schema_tokens` describe the inspector, and only the measured turn's
    inspector is under test."""
    return {
        "prompt": prompt,
        "called": sorted(called_names(res)),
        "surface_passes": [
            sorted({str(x)
                    for b in ((s or {}).get("advertised") or {}).values()
                    if isinstance(b, list) for x in b})
            for s in (res.get("surfaces") or [])],
        "text": (res.get("text") or "")[:800],
    }


def surfaced_names(r) -> set:
    """Every tool advertised in any pass OF THE MEASURED TURN — core, frontend, activated.

    TURN-SCOPED ON PURPOSE, and it must stay that way: the bars ask "could the model see it
    when it chose", and the choice happens in the measured turn. Unioning earlier turns in
    here would turn a tool that was displaced BEFORE the measured turn into a surfaced one,
    which is the opposite error to the one this file just fixed. Ask
    `earlier_surfaced_names()` for the rest of the session, separately."""
    out = set()
    for s in (r.get("surfaces") or ([r["surface"]] if r.get("surface") else [])):
        adv = (s or {}).get("advertised") or {}
        for bucket in adv.values():
            if isinstance(bucket, list):
                out.update(str(x) for x in bucket)
    return out


def earlier_surfaced_names(r) -> set:
    """Every tool advertised in a pass of an EARLIER turn of the same session.

    D-HARNESS-agentSurface-DISAGREES-WITH-THE-WIRE-LOG: chat-service's INFO log covers the
    session, the record covered one turn, and reading one as the other is what made
    "advertised 0/40" sit next to a live catalogue that had the tool. Reads
    `prior_turns[].surface_passes`, so it is empty for records written before 2026-08-27 —
    absent evidence, never a zero."""
    out = set()
    for t in (r.get("prior_turns") or []):
        for names in (t.get("surface_passes") or []):
            out.update(str(x) for x in (names or []))
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
        # ONLY-EARLIER: the tool was on the wire in this session, but not in the turn the bars
        # read. Counted apart from `surfaced` rather than folded into it — it is the answer to a
        # different question, and merging them is exactly the conflation this column had.
        earlier_only = sum(1 for r in rs
                           if want and want not in surfaced_names(r)
                           and want in earlier_surfaced_names(r))
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
        # 🔴 "unchanged" IS A STATEMENT ABOUT THE TOOL ONLY IF A WRITE WAS EVER PERMITTED.
        # D-A-TIER-A-SCENARIO-THAT-NEVER-APPROVES-CANNOT-MOVE-ITS-STORE: composition_motif_link_
        # edit is Tier A, its scenario sets `approve: null`, the batch ran with approvals `none`,
        # and every correct call was recorded {tier: A, pending: true, call_outcome: deferred}.
        # `wrote 0/5` said nothing about the tool, and the ledger's blocked reason then blamed
        # the model for a supplier call it had in fact made on 3 of 3 runs.
        #
        # 🔴 SCOPED TO THE TOOL UNDER TEST, AND A LIVE CONTROL IS WHY. The first version asked
        # whether the BATCH wrote anything, and batch c-nowrite1 refuted it on the spot: 2 runs
        # called jobs_cancel and stopped on its card, while the other 3 never called it at all
        # and wandered into translation_start_job, which wrote. "WROTE 3/5" was true and had
        # nothing to do with the tool. Re-derived over the corpus, the two triggers are not the
        # same question — 37 batches for the batch-wide rule, 34 for this one, 27 shared.
        #
        # The COLUMN keeps its meaning (another tool's write is a real write). The annotation is
        # about the tool the bars are read for, which is the thing that was misread.
        called_rs = [r for r in rs if want and want in called_names(r)]
        if (called_rs and all(r.get("pending_approval") for r in called_rs)
                and not any(r.get("store_diff") for r in called_rs)):
            print(f"    ^ THE STORE BAR CANNOT SEE {want}: all {len(called_rs)} run(s) that "
                  f"called it ended on an approval card and none of their stores moved, so no "
                  f"write was ever permitted. Whatever the column says, it is not about "
                  f"{want}.")
        # 🔴 "CALLED 0/N" UNDER approve=None IS NOT "THE MODEL DECLINED THIS TOOL".
        # D-A-NEVER-APPROVE-SCENARIO-MEASURES-REACH-BEFORE-ANY-CARD: a run ends at the FIRST
        # Tier-A card, whatever raised it. When that card belongs to some OTHER tool, the tool
        # under test never gets its turn — and the batch records `called 0/5` as though the model
        # had considered and rejected it. Those are different sentences.
        #
        # The proof that they are: glossary_create_evidence read "suspended 5/5, called 0/5" and
        # looked like a model that would not use it. Once the harness was allowed to click, the
        # tool was called 4/5 and failed on its ACTUAL defect — a required id with no supplier.
        #
        # Measured over every raw record on disk 2026-08-27: 24 scenario-batches recorded
        # `called 0/N` where EVERY run ended on a card belonging to a different tool. The cards
        # doing the blocking are a short list — glossary_propose_entities 21, kg_add_nodes 20,
        # book_chapter_save_draft 20, kg_project_create 18, glossary_adopt_standards 16.
        #
        # The record already named the owner: `pending_approval.tool`, present on all 482
        # suspended runs on disk. Nothing read it.
        if want and not called and rs:
            blockers = Counter(
                (r.get("pending_approval") or {}).get("tool")
                for r in rs
                if isinstance(r.get("pending_approval"), dict)
                and (r["pending_approval"].get("tool") or "") != want)
            if sum(blockers.values()) == len(rs):
                who = ", ".join(f"{t} ({n})" for t, n in blockers.most_common())
                print(f"    ^ NOT REACHED, NOT DECLINED: {want} was never called, and all "
                      f"{len(rs)} run(s) stopped at a card belonging to another tool — {who}. "
                      f"`called 0/{len(rs)}` here says the turn ended before {want}'s turn came, "
                      "not that the model rejected it.")
        # THE DENOMINATOR THE LOOP SHOULD HAVE BEEN QUOTING. `surface has tool` counts RUNS whose
        # measured turn advertised it; "advertised in N of M" was then written as though M were
        # passes. Passes come from the store, cover every turn, and are what the wire log prints.
        wire_rs = [r for r in rs if r.get("wire_passes")]
        if want and wire_rs:
            wp = [p for r in wire_rs for p in r["wire_passes"]]
            hit_p = sum(1 for p in wp if want in (p.get("names") or []))
            hit_r = sum(1 for r in wire_rs if want in wire_surfaced_names(r))
            print(f"    ^ ON THE WIRE (store, every turn): {hit_r}/{len(wire_rs)} runs, "
                  f"{hit_p}/{len(wp)} passes — the figure to quote. The column above counts "
                  f"SNAPSHOTS of the measured turn, which is neither.")
        # THE SENTENCE THAT WAS ACTUALLY ASKED. Nothing printed it, so an edit to a turn the
        # bars do not read looked exactly like an edit that landed — see measured_turn().
        if sc.get("follow_ups"):
            print(f"    ^ MEASURED TURN is turn {len(sc['follow_ups']) + 1} of "
                  f"{len(sc['follow_ups']) + 1}: {measured_turn(sc)!r}")
            print(f"      `prompt` is SETUP and no bar above reads it: {sc.get('prompt')!r}")
        if earlier_only:
            print(f"    ^ on the wire in an EARLIER turn only, in {earlier_only}/{len(rs)} runs "
                  f"— the `surface has tool` column reads the MEASURED turn, and the session's "
                  f"own wire log will disagree with it by this much")
        # 🔴 ONE ERROR NUMBER OVER THREE POPULATIONS CANNOT MOVE.
        # D-THE-TRANSPORT-STALL-IS-THREE-DIFFERENT-FAILURES: thirteen hypotheses were refuted
        # for composition_motif_link_edit because each was tested against a MIXED population —
        # its own runs contain both ReadTimeout-with-no-calls and upstream-error-after-a-search,
        # counted as one ~49%. A cause that explains one third looks refuted by the other two.
        _pops = Counter(r.get("error_population") or error_population(
            r.get("error"), len(called_names(r))) for r in rs if r.get("error"))
        if _pops:
            print("    ^ the errors are NOT one population: "
                  + ", ".join(f"{n}x {p}" for p, n in _pops.most_common())
                  + " — each needs its own question, and a single rate over them cannot move")
        _false_done = claimed_done_while_carded(rs)
        _false_denied = denied_a_write_that_landed(rs)
        if _false_done:
            print(f"    ^ CLAIMED DONE WHILE ITS OWN CARD WAS PENDING in "
                  f"{len(_false_done)}/{len(rs)} runs — the write is staged and unapproved and "
                  f"the author is told it happened, so they have no reason to approve it")
            print(f'      e.g. {(_false_done[0].get("text") or "").strip()[:120]!r}')
        if _false_denied:
            print(f"    ^ DENIED A WRITE ITS OWN TOOL RESULT CONFIRMS in "
                  f"{len(_false_denied)}/{len(rs)} runs — the call returned ok, the store moved, "
                  f"and the reply's CLOSING words tell the author it did not. Worse than the "
                  f"inverse: they will do it again, and a non-idempotent op then writes twice")
            print(f'      e.g. …{_false_denied[0]["tail"][-110:]!r}')
        _promised = promised_work_that_cannot_continue(rs)
        if _promised:
            print(f"    ^ PROMISED AN UPDATE THAT CANNOT ARRIVE in {len(_promised)}/{len(rs)} "
                  f"runs — the turn is over, nothing is queued, and no later message will come")
            print(f'      e.g. {(_promised[0].get("text") or "").strip()[:120]!r}')
        _refused_claim = claimed_a_write_its_own_call_refused(rs)
        if _refused_claim:
            print(f"    ^ CLAIMED A WRITE ITS OWN CALL REFUSED in "
                  f"{len(_refused_claim)}/{len(rs)} runs — the tool answered, said why, and "
                  f"the reply says the opposite, with the refusal in the model's own context")
            print(f'      e.g. {(_refused_claim[0].get("text") or "").strip()[:120]!r}')
        if susp:
            print(f"    ^ left SUSPENDED on a Tier-A approval card in {susp}/{len(rs)} runs "
                  f"— not a refusal by the model, a card waiting for a click")
        # D-A-READ-INTENT-TURN-WRITES-TO-EXTRACTION-PENDING — the violation is computed over the
        # tables a TOOL could have touched, not over every row the platform writes while a turn
        # happens. `extraction_pending` is queued by knowledge-service's `handle_chat_turn` on
        # the `chat.turn_completed` event, for EVERY turn whose project has extraction enabled,
        # whatever tool ran. Traced to that handler, and the evidence on disk agrees: it appears
        # in 349 runs across 90 batches, spanning composition_arc_apply, catalog_get_book,
        # jobs_cancel, kg_triage_schema_write and book_sync — no tool spans 90 batches.
        #
        # It is asynchronous, which is why it showed up on 1 of 5 runs rather than all five: the
        # enqueue sometimes lands before the "after" snapshot and sometimes after.
        #
        # MEASURED PRECISION of this exclusion over every evidence file: 295 runs where it is the
        # ONLY change (a pure false signal) stop being flagged; the 54 where it appears BESIDE a
        # real change still are, because the real change is what triggers. The store LINE above
        # is unchanged and still lists it — this hides nothing, it stops mis-attributing.
        _real = read_intent_violations(wrote)
        if _real and sc.get("intent") == "read":
            # The strongest assertion in the loop, and it needs no per-tool knowledge: a turn
            # that asked to LOOK must not change anything. Measured 2026-08-13: five read
            # turns took outline_node from 3 to 6 while the reply called it "your current
            # plan".
            print(f"    ^ READ-INTENT TURN WROTE TO THE STORE in {len(_real)}/{len(rs)} runs "
                  f"— a defect whatever it said")
        elif wrote and sc.get("intent") == "read":
            # 🔴 NAME THE TABLES THAT WERE ACTUALLY TOUCHED, AND THE RIGHT REASON FOR EACH.
            # This line used to print the bookkeeping set unconditionally — so a batch whose
            # only write was `entity_access_log` was explained as "turn-bookkeeping, written by
            # chat.turn_completed", which is false about that table twice over: it is written
            # BY the tool, and writing it is correct. A message that names the wrong reason is
            # worse than none, because it teaches a reader the wrong exemption.
            _touched = {t for r in wrote for t in (r.get("store_diff") or {})}
            _why = {
                "turn-bookkeeping, written for every turn by chat.turn_completed whatever tool "
                "ran": sorted(_touched & TURN_BOOKKEEPING_TABLES),
                "a read AUDIT row — the tool recording that it read, which is correct and is "
                "not a lifecycle move": sorted(_touched & READ_AUDIT_TABLES),
                "an UNSCOPED global count that any concurrent run moves, so it is attributable "
                "to nobody": sorted(_touched & UNATTRIBUTABLE_GLOBAL_COUNTS),
            }
            for reason, tables in _why.items():
                if tables:
                    print(f"    ^ {len(wrote)}/{len(rs)} runs touched {', '.join(tables)} — "
                          f"{reason}")
    print("\nA scenario is only informative across REPEATS — the consumer is stochastic, so "
          "'1/5 called' is a finding and '5/5 surfaced, 0/5 called' is a different finding "
          "from '0/5 surfaced'.")


def _sha(text) -> str:
    """Stable fingerprint of a judgement field, or "" when there is nothing to fingerprint."""
    import hashlib
    if not text:
        return ""
    return hashlib.sha256(str(text).strip().encode("utf-8")).hexdigest()[:16]


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
                # The fixture's OWN ids, so a cross-wired argument can be named rather than
                # guessed at. See seed_ids(): a batch that records only book_id cannot tell a
                # hallucinated id from a real one the fixture made, and the difference decides
                # whether the defect is the model's or the surface's.
                "project_id": r.get("project_id"),
                "seed_ids": r.get("seed_ids") or {},
                "session_id": r.get("session_id"),
                # 🔴 THE MEASURED TURN, not the scenario's first line. These differ for every
                # multi-turn scenario, and recording the wrong one is not cosmetic: reading
                # batch 34 back, world_map_remove_marker's evidence was labelled "List my
                # worlds." and it took a detour through the answers to establish that the
                # follow-ups had run at all. Evidence that misnames what it measured is
                # evidence that will be misread. `prior_turns` rides along for the same
                # reason: the setup turns are what make the last one interpretable.
                "prompt": (r.get("prompt") or sc["prompt"]),
                "scenario_prompt": sc["prompt"],
                "prior_turns": r.get("prior_turns") or [],
                "called": sc.get("expect_tool") in called_names(r),
                "surfaced": sc.get("expect_tool") in surfaced_names(r),
                "called_tools": sorted(called_names(r)),
                # 🔴 THE SET, NOT JUST THE BIT ABOUT THE TOOL UNDER TEST. `surfaced_names` already
                # computes every tool advertised in every pass and the writer kept one boolean of
                # it, so no batch on file could answer "was the tool's SUPPLIER advertised" — the
                # question every selection finding turns on. composition_generate needs a
                # model_ref from settings_list_models; whether the model COULD have obtained one
                # was unanswerable from five batches that all recorded it as "surfaced: true".
                "surfaced_tools": sorted(surfaced_names(r)),
                # 🔴 "CALLED" DOES NOT MEAN "WORKED", AND THE BATCH COULD NOT TELL THE DIFFERENCE.
                # b18-gen-control recorded composition_generate called 5/5 and passed 8 of 9 gate
                # bars; every one of those calls carried model_ref="default" and came back
                # ok=false — the exact invention that scenario's own falsifier says REFUTES the
                # run. The names alone read as success. See call_records().
                "calls": call_records(r),
                "timeline": compact_timeline(r, sc.get("expect_tool")),
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
            # The machine-checkable half of the falsifier. Prose states what would refute the
            # conclusion; this states it in terms the gate can evaluate against the recorded
            # reply, so whether the falsifier FIRED is not my judgement call.
            "answer_expect": sc.get("answer_expect"),
            # 🔴 STAMPED BY THE RUN, SO A LATER EDIT CANNOT HIDE. A falsifier written after the
            # results are in is not a falsifier, it is a description of what happened — and
            # `gate.py refresh` (which exists so a defect noticed while reading results need not
            # cost a ten-minute re-run) is exactly the door that lets one be back-dated. The hash
            # of the falsifier AS IT STOOD WHEN THE TURNS RAN is recorded here by the machine;
            # refresh compares against it and the gate fails on a mismatch.
            "falsifier_sha": _sha(sc.get("falsifier")),
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


#: Tables the PLATFORM writes for every turn, whatever tool ran — so a row here is not
#: evidence that the tool under test wrote anything.
#:
#: `extraction_pending` is queued by knowledge-service `handle_chat_turn` on the
#: `chat.turn_completed` event whenever the turn's project has extraction enabled. Adding a
#: table here WEAKENS the loop's strongest assertion, so the bar is: it must be traced to a
#: per-turn writer in the platform AND shown to span unrelated tools in the evidence on disk.
#: This one appears in 349 runs across 90 batches, over composition, catalog, jobs, kg and
#: book-sync scenarios alike.
TURN_BOOKKEEPING_TABLES = frozenset({"loreweave_knowledge.extraction_pending"})

#: A READ recording that it read. D-A-TIER-R-TOOL-WRITES-TO-THE-STORE's own sweep separates
#: three shapes and only one is the defect: turn bookkeeping (above), a read AUDIT row (here),
#: and a read tool ADVANCING A LIFECYCLE (the defect). Kept as its own set rather than folded
#: into the bookkeeping one, because the REASONS differ and a reader who sees one name will
#: assume the other's justification: bookkeeping is written by chat.turn_completed whatever
#: tool ran, while this IS written by the tool — and writing it is correct.
READ_AUDIT_TABLES = frozenset({"loreweave_knowledge.entity_access_log"})

#: 🔴 GLOBAL COUNTERS, ATTRIBUTABLE TO NOBODY. `neo4j.Fact.total` counts every Fact in the
#: database with no scope at all, so ANY concurrent run moves it — and this loop runs batches
#: at concurrency 2-3. Measured 2026-08-27: of 20 read-intent runs flagged as writing to the
#: store, 15 were the audit row above and 5 were this counter. Not one was a real write.
#:
#: It stays in the SNAPSHOT, where a global count is context. What it must not do is make a
#: turn accountable for it — the same lesson `_world_counts` and the arc_template run-nonce
#: paid for, arriving through a counter this loop added itself.
UNATTRIBUTABLE_GLOBAL_COUNTS = frozenset({"neo4j.Fact.total", "neo4j.Fact.invalidated"})


#: A PAST-TENSE completion claim. Deliberately a closed verb list rather than "sounds done":
#: `prepared`, `checked`, `ready`, and `I'll` are all HONEST beside a pending card and must not
#: be caught — sampled 12 unflagged replies and every one of them is one of those.
_CLAIMED_DONE = re.compile(
    r"\b(i(?:'ve| have) (?:now )?(?:added|created|noted|recorded|saved|updated|linked|attached"
    r"|set|removed|deleted|cancelled|applied|bound|written)"
    r"|has been (?:added|created|saved|updated|recorded|applied)"
    r"|i(?:'ve| have) gone ahead)\b", re.I)

#: Words that make a completion claim TRUE while a card is pending — the reply is describing a
#: staged action rather than a finished one.
_QUALIFIES_AS_STAGED = re.compile(
    r"\b(await|pending|approve|approval|confirm|for you to|once you|ready for|prepared"
    r"|proposed|staged|review)\b", re.I)


#: Deterministic sentences the SERVER appends. They are not the model speaking, and two of them
#: legitimately contain the words a denial uses.
_SERVER_APPENDED_LINES = (
    "their effects stand",                                    # the turn-ceiling close (DQ-T56)
    "Nothing has been saved yet; confirm the card above",     # the suspend line (DQ-T54)
    # 🔴 THE TURN BRIEF (DQ-T71, shipped 2026-08-31) — REGISTERED IN THE SAME COMMIT THAT SHIPS
    # IT, because the alternative is the defect this constant exists for. `_CLAIMED_DONE` once
    # matched "has been saved" inside the server's own "NOTHING has been saved yet", and 13 runs
    # across two batches read as a decisive regression at p = 0.0000 until the replies were
    # actually read. Neither phrase below matches today's patterns — checked, not assumed — so
    # these entries buy nothing THIS minute; they buy that a later widening of either pattern
    # cannot quietly start counting the platform's own sentences as the model's claims.
    "Already applied in this turn:",                          # the brief's success half
    "in this turn did not run:",                              # the brief's refusal half
)

#: Phrases in which a turn tells the author the work did NOT happen. Anchored on the negation,
#: never on the verb — "restored" appears in both the true and the false report, and the whole
#: difference is what is said around it.
_DENIED_THE_WRITE = re.compile(
    r"\b(?:has|have)\s+not\s+been\s+(?:restored|saved|created|updated|applied|changed)\b"
    r"|\bremains?\s+(?:archived|unchanged|deleted)\b"
    r"|\bnot\s+made\s+any\s+changes\b"
    r"|\bdid\s+not\s+(?:successfully\s+)?(?:execute|complete|save|apply)\b"
    r"|\bcannot\s+perform\s+this\s+action\b"
    r"|\bpreventing\s+the\s+(?:restoration|update|change)\b"
    r"|\bplease\s+(?:go\s+to|use)\s+the\s+\*{0,2}Studio\s*UI\b",
    re.I,
)


def denied_a_write_that_landed(runs: list[dict]) -> list[dict]:
    """Runs whose OWN tool result says the write succeeded and whose reply says it did not.

    D-A-TURN-DENIES-THE-WRITE-ITS-OWN-TOOL-RESULT-CONFIRMS — the exact inverse of
    `claimed_done_while_carded` above, and the worse one for a write. A turn that CLAIMS work it
    did not do leaves the author believing something false about their book; a turn that DENIES
    work it DID do sends them to do it again, and for a non-idempotent operation that is a second
    row.

    🔴 READ THE TAIL, NOT THE WHOLE REPLY, and that distinction is why this function exists. A
    turn spans several passes — the model narrates, a card is raised, it is approved, the tool
    runs, the model narrates again — and the recorded `text` glues every pass together. Read
    whole, EVERY run in the founding batch looks like it retracts, and that is exactly the
    mistake the row was filed with: it claimed 5 of 5 when the tails showed 3. The author is left
    with the END of the reply, so that is what is judged.

    THE MECHANISM, established from those tails: the model claims success PREMATURELY, in the
    pass that mints the card and before anything has executed ("I've restored the rule" is the
    first thing every run says). It then notices it spoke too soon and apologises — and the
    apology lands correctly on some runs and OVERSHOOTS into denying the now-completed write on
    others. The retraction is a correction of the model's own premature claim, never a report of
    a failed call.

    Measured: 3 of 5 on c-canonrestore3, 2 of 5 on c-denywrite1 — both n=5, so the rate is not
    established, only the existence.
    """
    out = []
    for r in runs:
        landed = False
        for c in r.get("tool_calls", []):
            if c.get("type") != "TOOL_CALL_RESULT":
                continue
            try:
                res = json.loads(c.get("content") or "{}")
            except Exception:
                continue
            if isinstance(res, dict) and res.get("ok") is True:
                landed = True
        if not landed:
            continue
        text = (r.get("text") or "").strip()
        # The TAIL is what the author is left with. 400 chars covers the closing paragraph
        # without reaching back into the premature claim the turn is correcting.
        tail = text[-400:]
        if not tail or not _DENIED_THE_WRITE.search(tail):
            continue
        # 🔴 A SERVER LINE IS NOT A MODEL DENIAL, and the first version of this counted five of
        # them. The turn-ceiling message (DQ-T56) says "the turn did not complete … Any tool
        # calls already made in this turn ran, and THEIR EFFECTS STAND" — which is both true and
        # the opposite of a denial, and it matched on "did not complete". Every deterministic
        # line the platform appends is excluded by a phrase only it uses; a detector that counts
        # the platform's own honest sentences as the defect measures itself.
        if any(marker in tail for marker in _SERVER_APPENDED_LINES):
            continue
        out.append({
            "rep": r.get("rep"),
            "session_id": r.get("session_id"),
            "denial": _DENIED_THE_WRITE.search(tail).group(0),
            "tail": tail[-200:],
        })
    return out


def claimed_done_while_carded(runs: list[dict]) -> list[dict]:
    """Runs that told the author the action is DONE while their own card was still PENDING.

    D-CLAIMS-DONE-WHILE-ITS-OWN-CARD-IS-STILL-PENDING. P1/P2 catch a turn that reports a write
    with NO card; this turn HAS one, so a card-presence check passes it. The lie is about TENSE:
    the write is staged and unapproved and the author is told it happened — so they have no
    reason to approve, the card is abandoned, and they believe their book records something it
    does not.

    RE-DERIVED THROUGH THIS FUNCTION 2026-08-27 over 152 raw batches / 1,516 runs: 98 ended
    with a card pending and a non-empty reply; 6 make an unqualified past-tense claim with no
    real write, and NOT ONE of the six mentions approval anywhere. 10 more claimed completion
    and had actually written — those are TRUE and not flagged. The row's own instance is among
    the 6 — "I've noted that Aldric Vane and Mira Solene know each other."
    (An earlier inline pass of mine reported 507 carded runs; that number was wrong and is
    superseded by this one, which the shipped predicate produced.)
    The staged-phrase clause below excludes 0 OF THE 98 — it is precision insurance for a
    phrasing the corpus contains but never beside a pending card and an empty store.

    The store test uses the same exemptions as `read_intent_violations`: bookkeeping, the read
    audit row and the unscoped global counts are not a write, and `entity_access_log` is exactly
    what moved on the measured instance.
    """
    ignore = TURN_BOOKKEEPING_TABLES | READ_AUDIT_TABLES | UNATTRIBUTABLE_GLOBAL_COUNTS
    out = []
    for r in runs:
        if not r.get("pending_approval"):
            continue
        text = (r.get("text") or "").strip()
        if not text or not _CLAIMED_DONE.search(text):
            continue
        if _QUALIFIES_AS_STAGED.search(text):
            continue
        if any(t not in ignore for t in (r.get("store_diff") or {})):
            continue
        out.append(r)
    return out


def failed_call_names(run: dict) -> list[str]:
    """The tool calls this run made that came back NOT ok, read from its own recorded results.

    A named helper rather than an inline loop, because the guard has to call the shipped
    predicate rather than a copy of it — and because `results` carries the outcome as JSON
    inside `content`, which is exactly the sort of shape a second implementation gets wrong.
    """
    out: list[str] = []
    for c in (run.get("results") or []):
        try:
            payload = json.loads(c.get("content") or "{}")
        except Exception:  # noqa: BLE001 — a malformed record is not an outcome
            continue
        if isinstance(payload, dict) and not payload.get("ok"):
            out.append(str(payload.get("_tool") or c.get("id") or "?"))
    return out


def claimed_a_write_its_own_call_refused(runs: list[dict]) -> list[dict]:
    """Runs whose reply asserts a write while a call THIS TURN failed and nothing was written.

    D-THE-MODEL-CLAIMED-A-CANCEL-THAT-THE-TOOL-REFUSED. The row's own next step, in its words:
    "a sweep for 'reply asserts a write while its own last call failed' is mechanisable across
    the batches on disk rather than needing new runs".

    🔴 THIS IS NOT THE CARDED ROW. There, the platform withheld the call after the model had
    already spoken, so it could not have known. HERE THE REFUSAL IS IN ITS CONTEXT: the tool
    answered, said why, and the model wrote the opposite. A card-pending run is excluded so the
    two populations cannot be double-counted against each other.

    MEASURED 2026-08-27 over 154 batches / 1,531 runs:

        488   had a FAILED call and a non-empty reply
        332     …and made no completion claim — the honest majority
        114     …but the store DID move, so the claim is about something that happened
         22     …but a card was pending — `claimed_done_while_carded`'s population
         20   >>> CLAIMED A WRITE ANYWAY

    The 20 concentrate: 8 composition-motif-link-edit-approved ("I've linked the motifs: Alpha
    now precedes Beta" with no link in the store), 7 memory-forget, 2 translation-patch-block,
    and one each from three more. The row's own instance shape — a cancel that did not happen —
    is there, and so is a fresh one from c-hollowdoc2: "I've saved that text as the draft for
    Chapter 1" after the hollow-document guard refused it three times in the same turn.

    THE EXEMPTION SETS WERE CHECKED AGAINST THIS BAR RATHER THAN ASSUMED TO FIT IT. The worry
    was that they hide the only evidence a memory write leaves — `neo4j.Fact.invalidated` is in
    UNATTRIBUTABLE_GLOBAL_COUNTS, and memory facts live in the graph. Measured: NO flagged run
    carries a `neo4j.*` key at all. The only exempted keys present are `extraction_pending` (3)
    and `entity_access_log` (2), which are turn-bookkeeping and a read audit row. So the
    exemptions are not manufacturing these 20.
    """
    ignore = TURN_BOOKKEEPING_TABLES | READ_AUDIT_TABLES | UNATTRIBUTABLE_GLOBAL_COUNTS
    out = []
    for r in runs:
        text = (r.get("text") or "").strip()
        # 🔴 THE SERVER'S OWN SENTENCE IS NOT THE MODEL'S CLAIM, and this detector counted it as
        # one for three days. `_CLAIMED_DONE` matches `has been saved`, which is a SUBSTRING of
        # the suspend line the platform appends — "Nothing has been saved yet; confirm the card
        # above to apply it." The negation is invisible to the pattern, so every carded turn
        # carrying that line looked like a completion claim.
        #
        # MEASURED 2026-08-30: 13 of this detector's 39 corpus-wide hits were the server line
        # ALONE, all of them dated on or after 2026-08-28 — the day the line shipped. They
        # concentrated so hard (8 of 8 runs of one scenario, 5 of 5 of another) that they read as
        # a REGRESSION, and I recorded one before checking the text. The replies were honest:
        # "I've attempted to apply the override … but I cannot find an existing what-if derivative".
        #
        # The exclusion set already existed and was already used by `denied_a_write_that_landed`,
        # whose own docstring records counting five server sentences as defects. The mechanism was
        # here; it simply was not applied on this side.
        for _line in _SERVER_APPENDED_LINES:
            text = text.replace(_line, " ")
        if not text or not _CLAIMED_DONE.search(text):
            continue
        if r.get("pending_approval"):        # the carded row's population, not this one
            continue
        if not failed_call_names(r):         # nothing refused it, so there is nothing to lie about
            continue
        if any(t not in ignore for t in (r.get("store_diff") or {})):
            continue
        out.append(r)
    return out


#: A promise of a LATER MESSAGE, or a request to WAIT — the two things a synchronous turn
#: cannot keep, because when it ends nothing else will ever speak. Deliberately NOT future
#: tense: "I'll cancel them now" is an intention INSIDE the turn and is fine.
#:
#: 🔴 `in a moment` WAS MEASURED AND REJECTED. It produced 4 of 9 hits and every one was the
#: assistant telling the USER to retry — "perhaps try asking again in a moment?", "you can try
#: again in a moment" — the opposite of a promise it owes. The DETERMINER is the whole
#: discrimination: `one/just a/give me a moment` is the assistant asking to be waited for.
#:
#: AND IT IS NOT ANCHORED TO A SENTENCE BOUNDARY, though it was for one round. The anchor
#: looked free and cost a true positive: the corpus's single mid-sentence occurrence is
#: "…**The Last Tide** One moment while I refresh that for you", after a list item with no
#: full stop. A falsifier that removed the anchor stayed GREEN, which is what sent me to
#: look at what the anchor was actually excluding.
_PROMISES_A_LATER_MESSAGE = re.compile(
    r"i'?(?:ll| will) let you know"
    r"|i'?(?:ll| will) update you"
    r"|i'?(?:ll| will) (?:come |get )?back to you"
    r"|(?:one|just a|give me a) moment"
    r"|stand ?by\b|bear with me|hold on while"
    r"|as soon as [^.]{0,60}(?:ready|live|done|complete|finished)"
    r"|i'?(?:m| am) (?:currently )?working on"
    r"|i'?(?:m| am) going to (?:attempt|take a moment)"
    r"|i'?(?:m| am) (?:now )?in the process of",
    re.I,
)

def promised_work_that_cannot_continue(runs: list[dict]) -> list[dict]:
    """Runs that end promising an update the platform has no way to send.

    D-A-TURN-PROMISES-WORK-THAT-CONTINUES-AFTER-IT-ENDS. The row closes with 'Recorded so the
    population is countable' and nobody had counted it. This does.

    It is the FUTURE tense of the narrated-write error and the existing bars miss it by
    construction: 'I have created the chapters' and 'I am creating the chapters, one moment'
    are both false when the store is unmoved, and only the first is a completion claim.

    MEASURED 2026-08-27 over 158 batches / 1,551 runs:

        26   promise a later message or ask the author to wait
        20     …but the store DID move — the work happened, only the promise is unkeepable
         1     …but a card is pending, which IS a real wait
         5   >>> NOTHING QUEUED AND NOTHING WRITTEN

    All five read as the defect, and they are not one scenario:

        "I will let you know as soon as the extraction and mapping are complete."
        "I'll find the ID for you now. One moment."            (twice, world-map-delete)
        "I'll need to list your templates first … One moment. I'm sorry, but I cannot archive
         the template because I don't have its unique ID."     — promised and contradicted
                                                                 itself inside one reply
        "I'll let you know as soon as it's finalized."

    WHAT IT DOES NOT COVER, and the row says the same: whether the platform should GUARD this is
    a decision about what the assistant may say. The row's own recommendation is that the honest
    remedy is upstream — a turn that cannot act should say so — and this bar takes no position
    on that. It counts.
    """
    ignore = TURN_BOOKKEEPING_TABLES | READ_AUDIT_TABLES | UNATTRIBUTABLE_GLOBAL_COUNTS
    out = []
    for r in runs:
        text = " ".join((r.get("text") or "").split())
        if not text or not _PROMISES_A_LATER_MESSAGE.search(text):
            continue
        if r.get("pending_approval"):          # a card IS something the author can act on
            continue
        wrote = [t for t in (r.get("store_diff") or {}) if t not in ignore]
        if wrote:
            # 🔴 ONE BRANCH, NOT TWO. This had a separate arm for a job/queue table above
            # it, and a falsifier that DELETED that arm stayed green — because anything
            # asynchronous also moves the store, so the arm never changed an outcome. The
            # distinction is real and belongs in the COUNT (see the docstring), not here,
            # where it was a clause that could never fire.
            continue
        out.append(r)
    return out


def read_intent_violations(wrote: list[dict]) -> list[dict]:
    """The runs a read-intent scenario is actually accountable for.

    A NAMED function rather than an inline comprehension, because the guard for this has to
    call the SHIPPED predicate. The first version of that guard re-implemented it and passed
    an over-broad injection — dropping every run that MENTIONS the bookkeeping table, which
    would have hidden the 54 runs where a real write appears beside it. A test that copies the
    logic it is guarding cannot fail when that logic changes.
    """
    ignore = TURN_BOOKKEEPING_TABLES | READ_AUDIT_TABLES | UNATTRIBUTABLE_GLOBAL_COUNTS
    return [r for r in wrote
            if any(t not in ignore and _changed_during_the_turn(r, d)
                   for t, d in (r.get("store_diff") or {}).items())]


def _changed_during_the_turn(run: dict, table_diff) -> bool:
    """Did this table's change happen INSIDE the measured window?

    🔴 D-THE-BEFORE-SNAPSHOT-IS-NOT-THE-STATE-THE-TURN-STARTS-FROM. The DATA bar reads
    `store_diff` as "what this TURN changed", and once it was not: a READ-intent scenario was
    flagged as a lifecycle write because the book's composition_work row was REPLACED between
    the `before` snapshot and the first user message. The store's own timestamps refuted it —
    the row's `created_at == updated_at` at 23:38:37, the turn's first message at 23:38:40 —
    but the run record carried no turn-start time, so refuting ONE flag needed a live query
    against a six-day-old session.

    `turn_started_at` is now recorded, and a change whose `after.latest` PREDATES it did not
    happen in the measured window. That is a fact about time, not a judgement about intent,
    which is why it can be applied here rather than parked in an exception list.

    FAILS OPEN, deliberately and in the direction that keeps evidence: a run without the
    timestamp (every row recorded before 2026-08-30) or a diff without a readable `latest` is
    treated as IN the window, exactly as before. A guard that started ignoring changes because
    it could not date them would be the more dangerous mistake.
    """
    started = run.get("turn_started_at")
    if not started or not isinstance(table_diff, dict):
        return True
    after = table_diff.get("after")
    if not isinstance(after, dict):
        return True
    latest = after.get("latest")
    if not isinstance(latest, str) or not latest.strip() or latest.strip() == "-":
        return True
    try:
        t_change = _dt.datetime.fromisoformat(latest.strip().replace(" ", "T"))
        t_start = _dt.datetime.fromisoformat(started)
    except ValueError:
        return True
    if t_change.tzinfo is None:
        t_change = t_change.replace(tzinfo=_dt.UTC)
    if t_start.tzinfo is None:
        t_start = t_start.replace(tzinfo=_dt.UTC)
    return t_change >= t_start


def preflight_seed_asserts(scenarios) -> list[str]:
    """Run every seed_assert query ONCE, before the batch spends a turn.

    🔴 WHY THIS EXISTS. Batch 32 lost all 25 runs to a single typo: the assertion said
    `WHERE id=` and knowledge_projects' primary key is `project_id`. Every run failed in
    provisioning, the report read "0/5 called, 5 err" for five tools, and nothing about any
    tool was measured. The same class had already cost batch 31 four of five runs (an
    account-wide `label='Ironhold'` matching earlier arms) and batch 29 a whole arm.

    A seed assertion is SQL I wrote against a schema I did not read. Executing it once with a
    placeholder is two seconds and turns a 25-turn loss into a message before anything starts.
    The placeholders are substituted with a syntactically valid UUID rather than a real one, so
    the query is CHECKED but its RESULT is meaningless here — this catches a bad column, a bad
    table or bad syntax, never a wrong expectation. The real assertion still runs per-run
    against the real fixture, where it belongs.
    """
    import re as _re

    import provision as _prov  # noqa: PLC0415 — the oracle lives beside the loop

    dummy = "00000000-0000-4000-8000-000000000000"
    problems: list[str] = []
    for sc in scenarios:
        for c in (sc.get("seed_assert") or []):
            sql = _re.sub(r"\{[a-z_]+(?::[^}]*)?\}", dummy, c.get("query", ""))
            try:
                _prov.oracle.db_query(c["db"], sql)
            except Exception as exc:  # noqa: BLE001 — any failure here is a broken assertion
                problems.append(f"{sc.get('id') or sc.get('tool_under_test')}: "
                                f"[{c['db']}] {str(exc).strip()[:200]}")
    return problems


def missing_sibling_arms(scenarios: list[dict]) -> list[tuple[str, str]]:
    """[(arm, missing_sibling)] for every split arm whose partner is not in this run.

    DQ-T50, owner 2026-08-28: "ALLOW THE SPLIT — one arm that NAMES the tool and tests the safety
    prediction, one that tests SELECTION — with BOTH arms reported. The both-arms condition is
    THE WHOLE BAR … naming the tool must never be used to quietly retire the selection question.
    A split that reports only the named arm converts 'the model never picks this' into silence."

    🔴 THAT CONDITION HAS TO BE ENFORCED, NOT REMEMBERED. The named arm is the pleasant one — it
    is the arm where the tool gets called and the falsifier finally evaluates — so it is exactly
    the arm someone re-runs alone when they want a green result. Running it by itself turns a
    measured 0/5 selection rate into no measurement at all, which is the failure the owner
    described, and nothing in a scenario file stops it.

    So an arm declares its partner in `_sibling_arm`, and running one without the other is
    REFUSED before any provider call is made. Cheap, symmetric (either arm alone fails), and it
    cannot be satisfied by intending to run the sibling later.
    """
    present = {s.get("id") for s in scenarios}
    return [
        (s["id"], s["_sibling_arm"])
        for s in scenarios
        if s.get("_sibling_arm") and s["_sibling_arm"] not in present
    ]


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
    ap.add_argument("--turn-timeout", type=float, default=TURN_TIMEOUT,
                    help="seconds a single turn may take; raise it for a prompt that pins a RAIL, "
                         "which the server drives step by step (see TURN_TIMEOUT)")
    ap.add_argument("--approvals", default="none",
                    choices=("none", "standing", "as-is", "allow-under-test"),
                    help="standing tool approvals for this batch; 'none' clears and restores; "
                         "'allow-under-test' grants `allow` to exactly the batch's tools_under_test "
                         "so their WRITES LAND WITHOUT A CARD (owner decision 2026-08-22, throwaway "
                         "fixtures only) — the second half of the pair whose first half is 'none'")
    a = ap.parse_args()
    scenarios = json.loads(pathlib.Path(a.scenarios).read_text(encoding="utf-8"))["scenarios"]
    globals()["TURN_TIMEOUT"] = a.turn_timeout
    globals()["APPROVAL_MODE"] = a.approvals
    globals()["KEEP_FIXTURES"] = a.keep_fixtures
    orphans = missing_sibling_arms(scenarios)
    if orphans:
        print("REFUSING to run — a SPLIT scenario is being run without its sibling arm. DQ-T50 "
              "allows a split only if BOTH arms are reported; running the named arm alone "
              "converts 'the model never picks this' into silence:", file=sys.stderr)
        for arm, sib in orphans:
            print(f"  {arm}  needs  {sib}", file=sys.stderr)
        return 2

    bad = preflight_seed_asserts(scenarios)
    if bad:
        print("REFUSING to run — a seed assertion is not valid SQL against its own database. "
              "A scenario whose assertion cannot execute measures nothing, and every run would "
              "fail in provisioning:", file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        return 2

    with ApprovalState(a.approvals,
                       tools=[s.get("tool_under_test") for s in scenarios
                              if s.get("tool_under_test")]):
        results = asyncio.run(main_async(scenarios, a.repeats, a.concurrency, a.approvals))
    # 🔴 THE DIRECTORY IS CREATED HERE BECAUSE ITS ABSENCE HAS TWICE DESTROYED A FINISHED BATCH.
    # Both times the K=5 runs COMPLETED — real provider, real fixtures, ~15 minutes of live
    # traffic — and then `write_text` raised FileNotFoundError on a dated folder that did not
    # exist yet, losing every result. The evidence had to be reconstructed from the store, which
    # only worked because these scenarios happen to write rows.
    #
    # It is the cheapest possible failure and the most expensive possible moment to have it: the
    # runs are already spent. A dated output path is the NORMAL way this harness is invoked
    # (docs/eval/toolloop/<date>/…), so the first batch of every new day hits it.
    def _write(path: str, payload: str, label: str) -> None:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload, encoding="utf-8")
        print(f"{label} -> {path}")

    if a.out:
        _write(a.out, json.dumps(results, indent=2, ensure_ascii=False), "raw results")
    if a.batch_out:
        _write(a.batch_out,
               json.dumps(emit_batch(results, scenarios, a.batch_id), indent=2, ensure_ascii=False),
               "gate evidence")
    report(results, scenarios, a.repeats)


if __name__ == "__main__":
    sys.exit(main())
