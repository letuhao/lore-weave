"""Discoverability / workflow scenario SIMULATION driver (Track C · WS-7).

Runs the black-box user scenarios in
`docs/specs/2026-07-09-agent-discoverability-and-workflow/scenarios/` (S00-S12,
flagship S06) against the REAL chat agent on the REAL docker stack, drives each
turn over SSE exactly as the GUI does, and records the §10 instrumented evidence
so a baseline (today's system) and a re-test (after the builds) are produced the
SAME way every time. Reusable: point it at any scenario JSON.

Sibling of `run_skill_gate.py` (skill-authoring Part E) and `run_quality_gate.py`
(context-budget). Same proven pattern — real chat agent, real stack, SSE-drained
turns — but two differences the discoverability effort needs:
  1. It captures the FULL tool record per call — name + ARGS + result-ok — not
     just the tool name. Args are required to detect the north-star failure:
     empty-intent `find_tools({})` spam (S06 §10 hard-red = 0).
  2. It computes the §10 instrumented metrics + renders the §7 baseline report and
     the per-movement checkpoint table (S06 §11) automatically. Instrumented rows
     (thrash, discovery counts, empty-intent, async job ids, jargon candidates) are
     filled by the harness; the BLACK-BOX outcome cells (goal-achieved / honest /
     canon-intact) are marked JUDGE and left for a human/LLM judge — per the
     black-box rule the harness never judges the user outcome from tool calls.

BLACK-BOX DISCIPLINE (README.md "black-box rule"): the turns are the user's own
words. This harness measures HOW the agent behaved (evidence, §10) but does NOT
decide whether the user's goal was met — that is judged from the observable
outcome, never from which tool fired.

Surface note: this drives the chat-service HTTP/SSE surface (the same backend
agent loop the GUI hits — where the find_tools thrash lives), which makes the
run reproducible and re-runnable. The final acceptance gate for FRONTEND-tool
scenarios still needs a live browser smoke (agent-gui-loop lesson); this harness
covers the discovery/loop/continuity surface, not "could the FE execute it".

Scenario JSON shape (see discoverability_scenarios/*.json + its README):
  {
    "scenario": "S06", "title": "...", "maps_to": "W06 vision-to-book",
    "persona": "...", "permission_mode": "write" | "ask" | "plan",
    "context": {"book_context": {"book_id": "<BOOK_ID>"}} | null,
    "enabled_skills": [...],
    "canon_facts": ["fiance identity", ...],       # S06 §10 8-fact checklist (judge)
    "jargon_denylist": ["kind","entity","ontology",...],
    "movements": [{"id":"A","label":"Here's my idea"}, ...],
    "turns": [{"movement":"A","user":"..."}, ...]   # one user utterance per turn
  }
`<BOOK_ID>`/`<PROJECT_ID>`/`<CHAPTER_ID>` in `context` are substituted from
SKILL_BOOK_ID / SKILL_PROJECT_ID / SKILL_CHAPTER_ID env (same as run_skill_gate).

Usage (in-container, same pattern as run_skill_gate.py):
  docker cp scripts/eval/run_discoverability_scenario.py infra-chat-service-1:/tmp/ds.py
  docker cp scripts/eval/discoverability_scenarios/S06-flagship.json infra-chat-service-1:/tmp/scen.json
  docker exec \
    -e QG_RUN_LABEL=S06-baseline -e QG_MODEL_REF=<gemma_user_model_uuid> \
    -e SKILL_BOOK_ID=<fresh_empty_book_id> \
    -e QG_SCENARIOS=/tmp/scen.json -e QG_OUT=/tmp/ds-out -e QG_KEEP_SESSIONS=1 \
    infra-chat-service-1 python /tmp/ds.py
  docker cp infra-chat-service-1:/tmp/ds-out ./docs/eval/discoverability/runs/

Resolve gemma's model_ref live (user_default_models is empty for the test acct):
  SELECT user_model_id, alias, capability_flags FROM user_models
   WHERE owner_user_id='019d5e3c-7cc5-7e6a-8b27-1344e148bf7c' AND is_active;
  -> pass the gemma-4-26b-a4b-qat chat UUID as QG_MODEL_REF.

Env (superset of run_skill_gate):
  JWT_SECRET          (present in the chat-service container) — required
  QG_MODEL_REF        gemma's user_model UUID (chat + tool_calling) — required
  QG_RUN_LABEL        names the output dir/report (default: run)
  QG_USER             owner user id (default: claude-test)
  QG_SCENARIOS        path to a scenario json — required
  QG_OUT              output dir (default: /tmp/ds-out)
  QG_ONLY             comma list of scenario ids to run (default: all in file)
  QG_BASE             chat-service base URL (default: http://localhost:8090)
  QG_KEEP_SESSIONS=1  keep sessions (needed to pull tool_calls JSONB post-run)
  QG_TURN_TIMEOUT     per-turn SSE timeout seconds (default: 600)
  QG_REPORT_DATE      date stamp for the report filename (default: from env or 'run')
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

import httpx
import jwt

BASE = os.environ.get("QG_BASE", "http://localhost:8090")
SECRET = os.environ["JWT_SECRET"]
USER = os.environ.get("QG_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
MODEL_REF = os.environ.get("QG_MODEL_REF", "")
LABEL = os.environ.get("QG_RUN_LABEL", "run")
OUT = Path(os.environ.get("QG_OUT", "/tmp/ds-out"))
ONLY = {s for s in os.environ.get("QG_ONLY", "").split(",") if s}
SCEN_PATH = Path(os.environ["QG_SCENARIOS"])
TURN_TIMEOUT = int(os.environ.get("QG_TURN_TIMEOUT", "600"))
# Host-vs-container clock skew tolerance for the minted `iat` (see _bearer).
_IAT_SKEW_S = int(os.environ.get("QG_IAT_SKEW_S", "120"))
REPORT_DATE = os.environ.get("QG_REPORT_DATE", "run")
# Auto-approve suspended calls (the WARM pass, headless). A propose->confirm /
# Tier-A approval flow suspends on a card a human clicks; with no human the run
# hangs. On a suspend we POST /tool-results to play the human, so the flow can
# COMPLETE and we can judge the real outcome. tool_approval cards →
# QG_APPROVE_OUTCOME (default approved_always = "always allow"); frontend-tool
# edit cards (no human decision we can honestly fabricate) → dismissed.
AUTO_APPROVE = os.environ.get("QG_AUTO_APPROVE", "1") != "0"
APPROVE_OUTCOME = os.environ.get("QG_APPROVE_OUTCOME", "approved_always")
MAX_RESUMES_PER_TURN = int(os.environ.get("QG_MAX_RESUMES", "16"))
# Warm-pass COMMIT of a propose->confirm gate. glossary_confirm_action / confirm_action
# suspend for the human to click Confirm; the FE then POSTs the token to the domain's
# committing endpoint AND resumes. To fully apply a workflow headlessly we do the same:
# commit the token, then resume. Domain -> committing endpoint (reachable in-container).
AUTO_COMMIT = os.environ.get("QG_AUTO_COMMIT", "1") != "0"
# Simulate the FE's auto-rendered confirm card (AssistantMessage.tsx): a class-C propose
# tool mints a confirm_token in its RESULT, and the real GUI auto-renders an approve card
# from that AUTHENTIC token EVEN IF the model never calls (or corrupts) the confirm tool —
# "so a GUI-only user can approve, independent of the model." A headless driver has no such
# net, so it UNDER-counts real-GUI success. With this on, at end of turn we commit any
# minted-but-unconfirmed live token (= the user clicking the auto-card in a warm pass) to
# measure the TRUE product success rate, not just the agent's tool-following. Off by default
# (measures the agent); on to measure what a real user would experience.
SIM_AUTORENDER = os.environ.get("QG_SIM_AUTORENDER", "0") != "0"
_COMMIT_URLS = {
    "glossary": os.environ.get("QG_GLOSSARY_URL", "http://glossary-service:8088")
    + "/v1/glossary/actions/confirm",
    # A Tier-W token from a DIFFERENT domain (translation_retranslate_dirty is a priced Tier-W
    # tool) commits at ITS domain's confirm route, not glossary's. Without this a translation-pass
    # scenario (S05) minted a retranslate token that was never committed → no job was ever created.
    "translation": os.environ.get("QG_TRANSLATION_URL", "http://translation-service:8087")
    + "/v1/translation/actions/confirm",
}


def _commit_any_domain(c: "httpx.Client", token: str) -> bool:
    """Commit a confirm_token without knowing its domain: try each domain's confirm route until one
    accepts it (a token is only valid at its own domain, so the wrong routes 4xx and the right one
    2xx). Robust to multi-domain Tier-W flows where the descriptor→domain map would otherwise drift."""
    for domain in _COMMIT_URLS:
        if _commit_domain_confirm(c, domain, token):
            return True
    return False


def _commit_domain_confirm(c: "httpx.Client", domain: str, token: str) -> bool:
    """POST a confirm_token to the domain's committing endpoint (what the FE does on
    Confirm). True on 2xx. Best-effort: any failure falls back to a dismissed resume."""
    url = _COMMIT_URLS.get(domain)
    if not url or not token:
        return False
    try:
        r = c.post(url, json={"confirm_token": token},
                   headers={"Authorization": f"Bearer {_bearer()}"}, timeout=60)
        return 200 <= r.status_code < 300
    except Exception:
        return False

_PLACEHOLDERS = {
    "<BOOK_ID>": os.environ.get("SKILL_BOOK_ID", ""),
    "<PROJECT_ID>": os.environ.get("SKILL_PROJECT_ID", ""),
    "<CHAPTER_ID>": os.environ.get("SKILL_CHAPTER_ID", ""),
}

# The discovery/search surface. A call to any of these is a "discovery call";
# find_tools with an empty intent is the north-star failure (S06 §10 hard-red).
DISCOVERY_TOOLS = {
    "find_tools", "tool_list", "tool_load", "invoke_tool",
    "workflow_list", "workflow_load",
}
# Tools that start an async job — "started != done"; §10 requires a status-read
# to precede any completion claim (async honesty, F7).
ASYNC_JOB_TOOLS = {
    "kg_build_graph", "kg_build_wiki",
    "composition_generate",
    "translation_start", "translation_run",
}
# NOTE: two tools were removed from this static list because they are CONDITIONALLY async,
# and listing them here flagged their SYNCHRONOUS uses as unpolled async jobs (false §4
# violations). A genuinely-async call is still caught by the `or job_ids` check below, so
# real async work is never missed:
#   - glossary_extract_entities_from_doc — SYNCHRONOUS in the product (the vision-to-book
#     rail authors it `async_job:false`; returns candidates inline, no job handle).
#   - plan_propose_spec — async ONLY in mode="llm" (returns a job handle); in mode="rules"
#     it finalizes synchronously (no job_id, plan_run.active_job_id=NULL). The flagship rail
#     runs it in rules mode, so there is no async job to poll.
# Result keys that carry an ACTUAL async job/operation handle. `run_id` and `arc_id` were
# here but they are RESOURCE identifiers (a plan run, an arc), present in SYNCHRONOUS results
# too — a rules-mode plan_propose_spec returns its `run_id` with NO background job, and the
# harness was counting that as an "async job left unpolled" (a false §4 violation). An actual
# async job is signalled by a job/operation/task handle, or by a populated `active_job_id`
# (the plan run's live background job — set in mode="llm", None/absent in mode="rules").
_JOB_ID_KEYS = ("job_id", "operation_id", "task_id", "active_job_id")
# A later call whose name hints it read a status (used to credit async honesty).
_STATUS_READ_RE = re.compile(r"(status|poll|_get\b|get_|_jobs?\b|coverage|self_check|checkpoint)", re.I)
# find_tools arg keys that carry the intent/query text.
_INTENT_KEYS = ("intent", "query", "q", "keywords", "text", "goal", "task")
# A tool call that only READS (never persists). Everything else that succeeds is
# treated as an effectful/write call for the "did it actually persist?" signal.
_READONLY_RE = re.compile(r"(_read\b|_get\b|^get_|_search\b|_list\b|_ontology_read|coverage|_self_check|list_|_show\b)", re.I)
# Assistant language that CLAIMS something was persisted/built/saved. If such a
# claim appears in a turn while the session has made ZERO effectful tool calls, it
# is a candidate false-"done" (the S06 baseline failure the async-only check missed:
# "I have locked that into the core of the project" / "permanent" with no writes).
# CANDIDATE only — a judge confirms (the claim may be legitimately backed by a write).
_PERSIST_CLAIM_RE = re.compile(
    r"\b(locked (it|that|this)?\s*(in|into)|i(?:'ve| have)\s+(saved|stored|recorded|locked|added|"
    r"created|built|set up|kept)|set up your (world|book|story)|added (it|them|these|those)\s+to\s+your|"
    r"recorded (it|them|these)|it'?s now (saved|stored|recorded|in your)|now (saved|stored)|"
    r"made (it|them) permanent|permanent[,.]?\s+(and\s+)?(structured|undeniable|saved|stored|real|in your)|"
    r"saved to your book|written (it|them) (to|into) your book)\b",
    re.I,
)

# A false-persistence claim is a claim that something WAS persisted. A sentence that says the
# opposite — that nothing is saved, or that it will only be saved LATER, or that the write was
# blocked — is honesty, not a lie, and must NOT be scored as one.
#
# Measured live (S00e, 2026-07-14): with the world-category writers DENIED, the agent behaved
# perfectly — it tried, was blocked, wrote nothing, and told the user "No, nothing has been saved
# yet… Your story bible is currently empty." It then explained the consent flow: *"Only after you
# see a confirmation card and approve it WILL the information actually be saved to your book."*
# The naive substring detector matched "saved to your book" inside that FUTURE-CONDITIONAL clause
# and scored a false-persistence claim against it.
#
# That is a detector punishing the exact behaviour the product is supposed to have — and since the
# DoD requires "0 false-persistence claims", it would have blocked a scenario the product passed
# flawlessly. A metric that cannot tell "I saved it" from "it will not be saved until you approve"
# is not measuring honesty; it is measuring word overlap.
_PERSIST_NEGATED_RE = re.compile(
    r"\b(?:will|would|once|after|unless|until|before you|if you|"
    r"not|nothing|never|no changes|none of|"
    r"can(?:'|no)t|cannot|couldn't|unable|isn't|wasn't|haven't|hasn't|didn't|won't|"
    r"yet|blocked|denied|refused|declined|permission|approve|approval|confirm|"
    r"waiting|pending|need(?:s)? (?:you|your))\b",
    re.I,
)


def _sentence_around(text: str, idx: int) -> str:
    """The sentence containing position `idx` — the unit a tense/polarity check has to run on.
    Matching on a bare fragment is what produced the S00e false positive."""
    start = max(text.rfind(".", 0, idx), text.rfind("\n", 0, idx), text.rfind("!", 0, idx),
                text.rfind("?", 0, idx)) + 1
    ends = [e for e in (text.find(".", idx), text.find("\n", idx), text.find("!", idx),
                        text.find("?", idx)) if e != -1]
    end = min(ends) if ends else len(text)
    return text[start:end + 1].strip()

# Thresholds (S06 §10). Breach = degraded-pass, recorded (not a hard fail).
THRESH_TURN_SECONDS = 250          # no single turn > 250s (loop-termination line)
THRESH_TTFUO_SECONDS = 90          # time-to-first-useful-output per movement
THRESH_CONSEC_SAME_TOOL = 3        # > 3 consecutive same-tool, no state change



def _item_error_counts(result) -> tuple[int, int]:
    """(n_errored_items, n_total_items) for a batch-style tool result.

    A tool can return envelope `ok:true` while EVERY item inside failed —
    e.g. glossary_propose_entities → {"results":[{"status":"error",
    "error":"unknown kind: character"}, ...]}. The agent reads `ok` and thinks it
    worked, so it retries forever. Envelope-ok is NOT effect (the repo's
    silent-success bug class); the harness must not credit such a call as a write.
    """
    if not isinstance(result, dict):
        return (0, 0)
    for key in ("results", "items", "created", "proposed"):
        seq = result.get(key)
        if isinstance(seq, list) and seq and all(isinstance(x, dict) for x in seq):
            n_err = sum(
                1 for x in seq
                if str(x.get("status", "")).lower() == "error" or x.get("error")
            )
            return (n_err, len(seq))
    return (0, 0)


def _is_silent_success(tc: dict) -> bool:
    """Envelope said ok, but every item inside errored ⇒ zero effect."""
    if tc.get("ok") is not True:
        return False
    n_err, n_total = _item_error_counts(tc.get("result"))
    return n_total > 0 and n_err == n_total


def _mints_confirm_token(tc: dict) -> bool:
    """True if this call's result carries a confirm_token — it PROPOSED/minted a pending
    action (adopt_standards, propose_kinds, propose_status_change, propose_merge, plan_*,
    …) and persisted NOTHING yet; the COMMIT (glossary_confirm_action) lands the effect.
    A mint returns ok:true, so counting it as an effectful write would suppress the
    false-persistence hard-red (a mid-tier agent that proposes then claims "done" without
    ever committing). So a mint is NOT an effectful write."""
    res = tc.get("result")
    if isinstance(res, dict):
        if res.get("confirm_token"):
            return True
        inner = res.get("result")
        if isinstance(inner, dict) and inner.get("confirm_token"):
            return True
    return False


def _substitute(obj):
    if isinstance(obj, str):
        return _PLACEHOLDERS.get(obj, obj)
    if isinstance(obj, dict):
        return {k: _substitute(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute(v) for v in obj]
    return obj


def _bearer() -> str:
    now = int(time.time())
    # `iat` is BACKDATED, and that is load-bearing — it is why this eval used to die mid-run with a
    # flaky 401 {"detail":"invalid token"}.
    #
    # This harness runs on the HOST and mints a token for a service in a CONTAINER. Those are two
    # different clocks: measured Docker-Desktop drift here was ~1.3%/s, so the host crosses from
    # behind the container to AHEAD of it within a couple of minutes. The moment it does,
    # `iat = host_now` sits in the CONTAINER's future and PyJWT raises ImmatureSignatureError — a
    # subclass of InvalidTokenError, so `loreweave_authn` reports the generic "invalid token", NOT
    # "token expired". Hence: intermittent, un-debuggable-from-the-message, and fatal several turns
    # into a long run (the earlier failures were at turns 2 and 8).
    #
    # It also explains a WRONG diagnosis this repo carried for a while: the 401s seemed to correlate
    # with another session redeploying chat-service. They did — but backwards. Restarting the
    # container RESYNCS its clock, which temporarily HID the drift. The redeploy was the cure, not
    # the cause (RUN-STATE DR-31).
    #
    # A server-minted token (auth-service) has no such problem — one clock. Only a host-side minter
    # does, so the skew tolerance belongs HERE, not in the platform verifier.
    return jwt.encode({"sub": USER, "iat": now - _IAT_SKEW_S, "exp": now + 3600},
                      SECRET, algorithm="HS256")


def _budget_total(frame: dict | None) -> int | None:
    if not isinstance(frame, dict):
        return None
    for k in ("used_tokens", "total_tokens", "tokens", "context_tokens"):
        v = frame.get(k)
        if isinstance(v, (int, float)):
            return int(v)
    return None


def _create_session(c: httpx.Client, title: str) -> str:
    body = {"title": title, "model_source": "user_model", "model_ref": MODEL_REF}
    r = c.post(f"{BASE}/v1/chat/sessions", json=body,
               headers={"Authorization": f"Bearer {_bearer()}"})
    r.raise_for_status()
    return r.json()["session_id"]


def _is_empty_intent(name: str, args: dict) -> bool:
    """A find_tools call with no usable intent — the empty-intent spam signature."""
    if name != "find_tools":
        return False
    if not isinstance(args, dict) or not args:
        return True
    for k in _INTENT_KEYS:
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return False
        if isinstance(v, list) and any(str(x).strip() for x in v):
            return False
    # args present but none of the known intent keys carried text
    return not any(
        isinstance(v, str) and v.strip() for v in args.values()
    )


def _send_turn(c: httpx.Client, sid: str, content: str, *,
               context: dict | None, enabled_skills: list[str],
               permission_mode: str | None, carry: dict | None = None) -> dict:
    """POST a turn as the GUI does; drain the SSE; capture assistant text, the
    full tool records (name + args + result ok/error) correlated by toolCallId,
    and the context budget.

    ``carry`` persists cross-turn session state (the authentic confirm_token) — a
    propose in one turn and its confirm in a later turn is a real pattern, and the
    token must survive the turn boundary."""
    hdr = {"Authorization": f"Bearer {_bearer()}", "Accept": "text/event-stream"}
    hdr["x-loreweave-stream-format"] = os.environ.get("QG_STREAM_FORMAT", "agui")
    body: dict = {"content": content, "enabled_skills": enabled_skills}
    if permission_mode:
        body["permission_mode"] = permission_mode
    if context:
        body.update(context)  # {"book_context": {...}} etc.

    # shared accumulation across the initial stream + every resume (approve) stream
    st = {"text_parts": [], "open_calls": {}, "order": [], "budget": None,
          "run_id": None, "cid_run_id": {},
          "last_confirm_token": (carry or {}).get("last_confirm_token")}

    def _drain(resp) -> None:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if obj.get("type") == "RUN_STARTED" and obj.get("runId"):
                st["run_id"] = obj["runId"]
            # A SUSPEND mints a FRESH run_id per suspended run (server stream_service.py
            # save_suspended_run) and returns it in RUN_FINISHED.result.pendingToolCall.runId —
            # NOT the RUN_STARTED runId. The real FE resumes with THIS id (runChatStream.ts);
            # resuming with the RUN_STARTED id makes load_suspended_run miss (loaded=False →
            # "expired"), so a CONSENT suspend (tool_approval, e.g. kg_project_create) never
            # executes. Capture the suspend's own run_id, keyed by its toolCallId.
            if obj.get("type") == "RUN_FINISHED":
                _res = obj.get("result") or {}
                _pend = _res.get("pendingToolCall") or {}
                if _res.get("status") == "suspended" and _pend.get("runId"):
                    st["run_id"] = _pend["runId"]
                    if _pend.get("toolCallId"):
                        st["cid_run_id"][_pend["toolCallId"]] = _pend["runId"]
            if obj.get("name") == "contextBudget" and isinstance(obj.get("value"), dict):
                st["budget"] = obj["value"]
            typ = obj.get("type") or ""
            if "TEXT_MESSAGE_CONTENT" in typ and obj.get("delta"):
                st["text_parts"].append(obj["delta"])
            elif "TOOL_CALL_START" in typ and obj.get("toolCallName"):
                cid = obj.get("toolCallId") or str(uuid.uuid4())
                st["open_calls"][cid] = {"tool": obj["toolCallName"], "args": {},
                                         "ok": None, "result": None, "error": None}
                st["order"].append(cid)
            elif "TOOL_CALL_ARGS" in typ:
                cid = obj.get("toolCallId")
                delta = obj.get("delta") or ""
                if cid in st["open_calls"] and delta:
                    st["open_calls"][cid]["_argstr"] = st["open_calls"][cid].get("_argstr", "") + delta
            elif "TOOL_CALL_RESULT" in typ:
                cid = obj.get("toolCallId")
                if cid in st["open_calls"]:
                    try:
                        env = json.loads(obj.get("content") or "{}")
                        st["open_calls"][cid]["ok"] = env.get("ok")
                        st["open_calls"][cid]["result"] = env.get("result")
                        st["open_calls"][cid]["error"] = env.get("error")
                        # Capture the AUTHENTIC server-authored confirm_token from a
                        # propose result (adopt/plan/…). A mid-tier model corrupts a
                        # 519-char token when it copies it into the confirm_action arg
                        # (right length + ends, one wrong middle char → 422). The real FE
                        # commits with the token IT received from the card, never a
                        # model-copied one — so we commit with this authentic token.
                        _res = env.get("result")
                        if isinstance(_res, dict) and _res.get("confirm_token"):
                            _tok = _res["confirm_token"]
                            st["last_confirm_token"] = _tok
                            # Accumulate EVERY minted token, not just the last. A single triage
                            # turn mints several (keep-batch + reject-batch + merge); overwriting
                            # last_confirm_token dropped all but one, so SIM_AUTORENDER committed
                            # one decision and the pile never drained (S03 stuck at triaged≤1).
                            st.setdefault("minted_tokens", []).append(_tok)
                            if carry is not None:
                                carry["last_confirm_token"] = _tok
                                _mt = carry.setdefault("minted_tokens", [])
                                if _tok not in _mt:
                                    _mt.append(_tok)
                    except Exception:
                        st["open_calls"][cid]["result"] = obj.get("content")

    with c.stream("POST", f"{BASE}/v1/chat/sessions/{sid}/messages",
                  json=body, headers=hdr, timeout=TURN_TIMEOUT) as resp:
        _drain(resp)

    # Resume loop — play the human on a suspended call so the flow completes.
    resumes = 0
    while AUTO_APPROVE and resumes < MAX_RESUMES_PER_TURN and st["run_id"]:
        pend_cid = None
        for cid in reversed(st["order"]):
            rec = st["open_calls"][cid]
            if rec["ok"] is None and not rec.get("resumed"):
                pend_cid = cid
                break
        if pend_cid is None:
            break
        rec = st["open_calls"][pend_cid]
        try:
            pargs = json.loads(rec.get("_argstr", "") or "{}")
        except Exception:
            pargs = {}
        is_appr = isinstance(pargs, dict) and pargs.get("kind") == "tool_approval"
        tool_name = rec.get("tool", "")
        _domain = (pargs.get("domain") if isinstance(pargs, dict) else None) or (
            "glossary" if "glossary" in tool_name else "")
        # Prefer the AUTHENTIC token captured from the propose result over the model's
        # (often corrupted) copy in the confirm_action arg — this is what the real FE commits.
        confirm_token = st.get("last_confirm_token") or (
            pargs.get("confirm_token") if isinstance(pargs, dict) else None)
        # Resume with the run_id that belongs to THIS pending call's suspend (each suspend
        # has its own fresh run_id), falling back to the latest suspend's run_id.
        _resume_run_id = st["cid_run_id"].get(pend_cid, st["run_id"])
        resume_body: dict = {"run_id": _resume_run_id, "tool_call_id": pend_cid}
        if is_appr:
            # Tier-A approval card — the resume path executes server-side (approved_always).
            resume_body["outcome"] = APPROVE_OUTCOME
            rec["resumed"] = APPROVE_OUTCOME
        elif AUTO_COMMIT and confirm_token and _domain in _COMMIT_URLS:
            # propose->confirm gate — commit the token (as the FE does), then resume with
            # the applied result so the flow completes and the effect actually lands.
            if _commit_domain_confirm(c, _domain, confirm_token):
                resume_body["result"] = {"confirmed": True, "domain": _domain}
                rec["resumed"] = "committed"
                rec["ok"] = True                 # it applied — count it as effectful
                rec["result"] = {"confirmed": True, "domain": _domain}
                if carry is not None:
                    carry.setdefault("committed", set()).add(confirm_token)
            else:
                resume_body["outcome"] = "dismissed"
                rec["resumed"] = "commit_failed"
        else:
            # a confirm/edit card we cannot honestly apply headlessly — dismiss it.
            resume_body["outcome"] = "dismissed"
            rec["resumed"] = "dismissed"
        resumes += 1
        try:
            with c.stream("POST", f"{BASE}/v1/chat/sessions/{sid}/tool-results",
                          json=resume_body, headers=hdr, timeout=TURN_TIMEOUT) as r2:
                _drain(r2)
        except Exception:
            break

    # Auto-render safety net (see SIM_AUTORENDER): the real GUI renders an approve card
    # from any propose result's AUTHENTIC token even if the model never called confirm.
    # In a warm pass the user clicks it → the effect lands. Replicate that so the headless
    # rate reflects the real product, not just the agent's tool-following.
    if SIM_AUTORENDER and carry is not None:
        committed = carry.setdefault("committed", set())
        # Commit EVERY minted-but-unconfirmed token this session, not just the last — a triage
        # turn stages keep + reject + merge as separate cards a real user clicks one by one.
        # Fall back to last_confirm_token so a run with no accumulator still commits its one token.
        pending = list(carry.get("minted_tokens") or [])
        _last = carry.get("last_confirm_token")
        if _last and _last not in pending:
            pending.append(_last)
        for tok in pending:
            if tok and tok not in committed:
                # Domain-agnostic: a turn may mint glossary AND translation tokens; each commits at
                # its own domain's route (was hardcoded to glossary, so translation tokens were lost).
                if _commit_any_domain(c, tok):
                    committed.add(tok)
                    st["autorender_committed"] = st.get("autorender_committed", 0) + 1

    budget = st["budget"]
    text_parts = st["text_parts"]
    order = st["order"]
    open_calls = st["open_calls"]
    # finalize args (parse the accumulated arg string)
    tools: list[dict] = []
    for cid in order:
        rec = open_calls[cid]
        argstr = rec.pop("_argstr", "")
        if argstr:
            try:
                rec["args"] = json.loads(argstr)
            except Exception:
                rec["args"] = {"_raw": argstr}
        tools.append(rec)
    if budget is None:
        try:
            gb = c.get(f"{BASE}/v1/chat/sessions/{sid}/context-budget",
                       headers={"Authorization": f"Bearer {_bearer()}"}, timeout=30)
            if gb.status_code == 200:
                budget = gb.json().get("budget")
        except Exception:
            pass
    text = "".join(text_parts).strip()
    if not text:  # streaming produced no text — fall back to the persisted message
        try:
            gm = c.get(f"{BASE}/v1/chat/sessions/{sid}/messages",
                       headers={"Authorization": f"Bearer {_bearer()}"}, timeout=30)
            if gm.status_code == 200:
                j = gm.json()
                items = j.get("items") or j.get("messages") or []
                asst = [m for m in items if m.get("role") == "assistant"]
                if asst:
                    text = (asst[-1].get("content") or "").strip()
        except Exception:
            pass
    return {"assistant": text, "budget": budget,
            "budget_total": _budget_total(budget), "tools": tools}


# ---------------------------------------------------------------------------
# Instrumentation (§10) — computed from the captured turn records.
# ---------------------------------------------------------------------------

def _find_job_ids(result) -> list[str]:
    out: list[str] = []
    if isinstance(result, dict):
        for k in _JOB_ID_KEYS:
            v = result.get(k)
            if isinstance(v, str) and v:
                out.append(v)
        for v in result.values():
            out.extend(_find_job_ids(v))
    elif isinstance(result, list):
        for v in result:
            out.extend(_find_job_ids(v))
    return out


def _scan_jargon(text: str, denylist: list[str]) -> list[str]:
    """Return denylist words that appear as whole words in the assistant text.
    These are CANDIDATE leaks — prose mention vs. required-input distinction is a
    human/judge call (the black-box fail is only when success *required* the word).
    """
    hits: list[str] = []
    low = text.lower()
    for w in denylist:
        wl = w.lower()
        pat = r"\b" + re.escape(wl) + r"\b" if wl.isalnum() else re.escape(wl)
        if re.search(pat, low):
            hits.append(w)
    return hits


def _compute_metrics(records: list[dict], scenario: dict) -> dict:
    denylist = scenario.get("jargon_denylist") or []
    empty_intent = 0
    discovery_total = 0
    jargon_candidates: list[dict] = []
    async_jobs: list[dict] = []
    persist_claims_without_write: list[dict] = []
    unresolved_calls: list[dict] = []   # ok is None ⇒ START/ARGS/END with no RESULT
    resumed_calls: list[dict] = []      # suspended, then auto-approved/committed by the driver
    commit_failed_calls: list[dict] = []  # a domain-confirm commit POST failed (real failure)
    silent_success_calls: list[dict] = []  # ok:true but every item errored
    cumulative_write_tools = 0
    max_consec = 0
    prev_sig = None
    consec = 0
    # global-ordered flat list of (seq, turn, tool) so "a status-read came LATER"
    # is unambiguous even within a single turn (started != done must precede a claim).
    flat_calls: list[tuple[int, int, str]] = []
    seq = 0
    for rec in records:
        for tc in rec["tools"]:
            flat_calls.append((seq, rec["turn"], tc["tool"]))
            seq += 1

    gseq = 0
    for rec in records:
        turn = rec["turn"]
        for tc in rec["tools"]:
            name = tc["tool"]
            my_seq = gseq
            gseq += 1
            args = tc.get("args") or {}
            if name in DISCOVERY_TOOLS:
                discovery_total += 1
            if _is_empty_intent(name, args):
                empty_intent += 1
            # A tool call that emitted START/ARGS/END but NO RESULT suspended the run
            # on a client-side card. If the driver resolved it (resumed), the flow
            # completed — UNLESS the resolution was a FAILED commit, which is a real
            # failed application (its own hard-red), NOT a completed resume. Only a
            # suspend we could not resume at all is unresolved (COLD-pass artifact).
            _resumed = tc.get("resumed")
            if _resumed == "commit_failed":
                commit_failed_calls.append({"turn": turn, "tool": name})
            elif _resumed:
                resumed_calls.append({"turn": turn, "tool": name, "outcome": _resumed})
            elif tc.get("ok") is None:
                unresolved_calls.append({"turn": turn, "tool": name})
            # consecutive same-tool with same args (no state change proxy)
            sig = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
            if sig == prev_sig:
                consec += 1
            else:
                consec = 1
                prev_sig = sig
            max_consec = max(max_consec, consec)
            # async job capture
            job_ids = _find_job_ids(tc.get("result"))
            if name in ASYNC_JOB_TOOLS or job_ids:
                # was a status-read observed STRICTLY AFTER this call (global order)?
                later = [nm for (sq, t, nm) in flat_calls
                         if sq > my_seq and _STATUS_READ_RE.search(nm) and nm != name]
                async_jobs.append({
                    "turn": turn, "tool": name, "job_ids": job_ids,
                    "status_read_after": bool(later),
                    "read_by": later[:3],
                })
        # Count effectful (non-read, non-discovery) tool calls that ACTUALLY RAN.
        # `ok is True` only — a failed call (False) persisted nothing, and a pending
        # call (None) never executed at all (it suspended on an approval card).
        for tc in rec["tools"]:
            nm = tc["tool"]
            if _is_silent_success(tc):
                n_err, n_total = _item_error_counts(tc.get("result"))
                sample = ""
                seq = (tc.get("result") or {}).get("results") or []
                if seq and isinstance(seq[0], dict):
                    sample = str(seq[0].get("error") or "")[:80]
                silent_success_calls.append({"turn": turn, "tool": nm,
                                             "failed_items": f"{n_err}/{n_total}",
                                             "sample_error": sample})
                continue  # envelope-ok but zero effect — never credit as a write
            if (nm not in DISCOVERY_TOOLS and not _READONLY_RE.search(nm)
                    and tc.get("ok") is True and not _mints_confirm_token(tc)):
                cumulative_write_tools += 1
        # false-persistence candidate: a "saved/locked/permanent" claim while the
        # session has persisted NOTHING (zero effectful tool calls so far).
        if cumulative_write_tools == 0:
            text = rec["assistant"] or ""
            for mclaim in _PERSIST_CLAIM_RE.finditer(text):
                sentence = _sentence_around(text, mclaim.start())
                # Future / conditional / negated / blocked framing ⇒ the agent is being HONEST
                # about not having persisted. Scoring that as a false claim would punish exactly
                # the behaviour we want (see _PERSIST_NEGATED_RE).
                if _PERSIST_NEGATED_RE.search(sentence):
                    continue
                persist_claims_without_write.append({
                    "turn": turn,
                    "claim": sentence[:160].replace("\n", " ").strip(),
                })
                break
        hits = _scan_jargon(rec["assistant"], denylist)
        if hits:
            jargon_candidates.append({"turn": turn, "words": hits})

    # per-movement rollup
    movements: dict[str, dict] = {}
    _mv_prev_sig: dict[str, object] = {}  # per-movement consecutive-same-call tracking
    _mv_consec: dict[str, int] = {}
    for rec in records:
        mv = rec.get("movement") or "-"
        m = movements.setdefault(mv, {
            "turns": 0, "tool_calls": 0, "discovery_calls": 0,
            "empty_intent": 0, "max_turn_s": 0.0, "ttfuo_s": None,
            "max_consec": 0,
            "label": rec.get("movement_label", ""),
        })
        m["turns"] += 1
        m["tool_calls"] += len(rec["tools"])
        m["discovery_calls"] += sum(1 for tc in rec["tools"] if tc["tool"] in DISCOVERY_TOOLS)
        m["empty_intent"] += sum(1 for tc in rec["tools"]
                                 if _is_empty_intent(tc["tool"], tc.get("args") or {}))
        m["max_turn_s"] = max(m["max_turn_s"], rec["latency_s"])
        # consecutive same-call run WITHIN this movement (review-impl: the per-movement
        # thrash verdict must use a per-movement count, not the global max — else one
        # thrashy movement marks every clean movement ❌ in the §11 table).
        for tc in rec["tools"]:
            sig = (tc["tool"], json.dumps(tc.get("args") or {}, sort_keys=True, ensure_ascii=False))
            if sig == _mv_prev_sig.get(mv):
                _mv_consec[mv] = _mv_consec.get(mv, 0) + 1
            else:
                _mv_consec[mv] = 1
                _mv_prev_sig[mv] = sig
            m["max_consec"] = max(m["max_consec"], _mv_consec[mv])
        if m["ttfuo_s"] is None and rec["assistant"].strip():
            m["ttfuo_s"] = rec["latency_s"]

    # auto no-thrash verdict per movement (purely instrumental — allowed to be auto)
    for mv, m in movements.items():
        thrash = (m["empty_intent"] > 0 or m["max_turn_s"] > THRESH_TURN_SECONDS
                  or m["max_consec"] > THRESH_CONSEC_SAME_TOOL)
        heavy = m["discovery_calls"] > 4
        m["no_thrash"] = "❌" if thrash else ("⚠️" if heavy else "✅")

    total_turn_s = sum(r["latency_s"] for r in records)
    return {
        "empty_intent_find_tools": empty_intent,          # HARD RED must be 0
        "discovery_calls_total": discovery_total,
        "max_consecutive_same_call": max_consec,          # >3 = thrash
        "async_jobs": async_jobs,
        "async_jobs_without_status_read": sum(1 for j in async_jobs if not j["status_read_after"]),
        "effectful_tool_calls": cumulative_write_tools,   # 0 = persisted nothing
        "unresolved_tool_calls": unresolved_calls,        # suspended, NOT resumed
        "resumed_tool_calls": resumed_calls,              # suspended, auto-approved/committed
        "commit_failed_calls": commit_failed_calls,        # a domain-confirm commit POST failed
        "silent_success_calls": silent_success_calls,      # ok:true, all items errored
        "persist_claims_without_write": persist_claims_without_write,  # CANDIDATE false-"done"
        "jargon_candidates": jargon_candidates,           # CANDIDATES — judge confirms
        "total_turn_seconds": round(total_turn_s, 1),
        "max_turn_seconds": round(max((r["latency_s"] for r in records), default=0), 1),
        "movements": movements,
        "canon_facts": scenario.get("canon_facts") or [],  # judge-scored
    }


def _fmt_movement_table(scenario: dict, metrics: dict) -> str:
    """Per-movement checkpoint table (S06 §11). no-thrash is auto; the black-box
    outcome cells are JUDGE (harness never judges user outcome from tool calls)."""
    rows = [
        "| Movement | goal-achieved | no-rescue | no-thrash | honest | canon-intact | discovery | empty-intent | max turn (s) | TTFUO (s) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    order = [mv["id"] for mv in (scenario.get("movements") or [])] or list(metrics["movements"].keys())
    for mid in order:
        m = metrics["movements"].get(mid)
        if not m:
            continue
        label = m.get("label") or ""
        head = f"{mid} {label}".strip()
        ttfuo = m["ttfuo_s"]
        ttfuo_s = f"{ttfuo:.0f}" if isinstance(ttfuo, (int, float)) else "—"
        rows.append(
            f"| {head} | JUDGE | JUDGE | {m['no_thrash']} | JUDGE | JUDGE | "
            f"{m['discovery_calls']} | {m['empty_intent']} | {m['max_turn_s']:.0f} | {ttfuo_s} |"
        )
    return "\n".join(rows)


def _render_report(scenario: dict, records: list[dict], metrics: dict,
                   meta: dict) -> str:
    hard_reds = []
    if metrics["empty_intent_find_tools"] > 0:
        hard_reds.append(f"empty-intent find_tools = {metrics['empty_intent_find_tools']} (must be 0)")
    if metrics["async_jobs_without_status_read"] > 0:
        hard_reds.append(
            f"{metrics['async_jobs_without_status_read']} async job(s) with NO later status-read "
            f"(false-\"done\" risk — judge must confirm)")
    if metrics["persist_claims_without_write"]:
        hard_reds.append(
            f"{len(metrics['persist_claims_without_write'])} \"saved/built/permanent\" claim(s) with "
            f"ZERO effectful tool calls all session (persisted nothing — judge must confirm honesty)")
    if metrics["silent_success_calls"]:
        names = ", ".join(sorted({u["tool"] for u in metrics["silent_success_calls"]}))
        hard_reds.append(
            f"{len(metrics['silent_success_calls'])} SILENT-SUCCESS call(s) ({names}) — envelope "
            f"`ok:true` while every item inside errored. The agent gets no failure signal and retries; "
            f"nothing persists")
    if metrics.get("commit_failed_calls"):
        names = ", ".join(sorted({u["tool"] for u in metrics["commit_failed_calls"]}))
        hard_reds.append(
            f"{len(metrics['commit_failed_calls'])} FAILED-COMMIT call(s) ({names}) — the driver "
            f"tried to commit a proposed action (warm approve) and the commit POST FAILED, so the "
            f"effect did NOT land. A failed application, not a completed step")
    if metrics["unresolved_tool_calls"]:
        names = ", ".join(sorted({u["tool"] for u in metrics["unresolved_tool_calls"]}))
        hard_reds.append(
            f"{len(metrics['unresolved_tool_calls'])} UNRESOLVED tool call(s) ({names}) — the run "
            f"suspended on a client-side approval card this headless driver cannot answer. This is a "
            f"COLD pass: everything after the first suspend is a driver artifact, NOT a product verdict. "
            f"Re-run WARM (pre-seed user_tool_approvals) before judging goal-achievement")
    red_line = "❌ " + "; ".join(hard_reds) if hard_reds else "✅ none auto-detected (judge confirms honesty/canon)"

    sid = records[0]["session_id"] if records else "?"
    L = []
    L.append(f"# {scenario.get('scenario','S??')} · {scenario.get('title','')} — {LABEL}")
    L.append("")
    L.append("> Auto-generated by `scripts/eval/run_discoverability_scenario.py`. Instrumented rows "
             "(§10) are filled by the harness; the **JUDGE** cells (goal-achieved / no-rescue / honest / "
             "canon-intact) are the BLACK-BOX user outcome — fill them from the transcript, never from "
             "the tool calls (README black-box rule).")
    L.append("")
    L.append("## Run")
    L.append("")
    L.append(f"- **Date / stack / model_ref:** {REPORT_DATE} · {BASE} · `{MODEL_REF}` "
             f"({scenario.get('model','gemma-4-26b-a4b-qat')})")
    L.append(f"- **Scenario:** `{SCEN_PATH.name}` · maps to {scenario.get('maps_to','?')} · "
             f"persona {scenario.get('persona','?')} · permission_mode "
             f"`{scenario.get('permission_mode','write')}`")
    L.append(f"- **Session id:** `{sid}` (pull raw tool_calls JSONB from "
             f"`loreweave_chat.chat_messages`; QG_KEEP_SESSIONS=1)")
    L.append(f"- **Turns:** {len(records)} · **wall-clock:** {metrics['total_turn_seconds']}s · "
             f"**max turn:** {metrics['max_turn_seconds']}s")
    L.append("")
    L.append("## Instrumented hard-reds (§10 — any occurrence = instrumented fail)")
    L.append("")
    L.append(f"- **Result:** {red_line}")
    L.append(f"- empty-intent `find_tools`: **{metrics['empty_intent_find_tools']}** (target 0)")
    L.append(f"- total discovery calls: **{metrics['discovery_calls_total']}** "
             f"(threshold ≤ ~15 · ≤2 per user goal)")
    L.append(f"- max consecutive same-call (no state change): **{metrics['max_consecutive_same_call']}** "
             f"(threshold ≤ {THRESH_CONSEC_SAME_TOOL})")
    L.append(f"- async jobs started: **{len(metrics['async_jobs'])}** · "
             f"without a later status-read: **{metrics['async_jobs_without_status_read']}** "
             f"(every completion claim must be preceded by a status-read)")
    L.append(f"- effectful (persisting) tool calls all session: **{metrics['effectful_tool_calls']}** "
             f"(0 ⇒ the book is unchanged — nothing was actually saved)")
    if metrics.get("resumed_tool_calls"):
        names = ", ".join(sorted({r["tool"] for r in metrics["resumed_tool_calls"]}))
        L.append(f"- auto-approved (warm) suspends: **{len(metrics['resumed_tool_calls'])}** ({names}) — "
                 f"the driver played the human on a confirm/approval card so the flow could complete")
    if metrics["silent_success_calls"]:
        L.append(f"- 🛑 **silent-success calls: {len(metrics['silent_success_calls'])}** — `ok:true`, all "
                 f"items errored (no effect, no failure signal to the agent):")
        for sc in metrics["silent_success_calls"]:
            L.append(f"    - turn {sc['turn']}: `{sc['tool']}` items-failed={sc['failed_items']} "
                     f"e.g. \"{sc['sample_error']}\"")
    if metrics["unresolved_tool_calls"]:
        L.append(f"- 🛑 **unresolved (suspended) tool calls: {len(metrics['unresolved_tool_calls'])}** — "
                 f"hit an approval card; COLD pass, re-run WARM:")
        for u in metrics["unresolved_tool_calls"]:
            L.append(f"    - turn {u['turn']}: `{u['tool']}` (no result — suspended)")
    if metrics["persist_claims_without_write"]:
        L.append(f"- ⚠️ **false-persistence candidates: {len(metrics['persist_claims_without_write'])}** "
                 f"— \"saved/built/permanent\" claims made while 0 effectful tools ran:")
        for pc in metrics["persist_claims_without_write"]:
            L.append(f"    - turn {pc['turn']}: …{pc['claim']}…")
    if metrics["jargon_candidates"]:
        allw = sorted({w for jc in metrics["jargon_candidates"] for w in jc["words"]})
        L.append(f"- jargon leak CANDIDATES (judge confirms required-input vs. prose mention): "
                 f"{', '.join(allw)}")
    else:
        L.append("- jargon leak candidates: none")
    L.append("")
    L.append("## Per-movement checkpoint table (§11)")
    L.append("")
    L.append(_fmt_movement_table(scenario, metrics))
    L.append("")
    if metrics["canon_facts"]:
        L.append("## Canon retention (§10 — JUDGE, ≥7/8 to pass)")
        L.append("")
        L.append("Seed the checklist; count survival into the late movements from the transcript:")
        for f in metrics["canon_facts"]:
            L.append(f"- [ ] {f}")
        L.append("")
    if metrics["async_jobs"]:
        L.append("## Async jobs observed (verify honesty)")
        L.append("")
        for j in metrics["async_jobs"]:
            flag = "" if j["status_read_after"] else "  ⚠️ NO later status-read"
            L.append(f"- turn {j['turn']} `{j['tool']}` job_ids={j['job_ids'] or '—'}"
                     f" read_by={j['read_by'] or '—'}{flag}")
        L.append("")
    L.append("## Transcript")
    L.append("")
    L.append("Full per-turn records (user · assistant · tool calls with args · budget) in "
             "`transcript.jsonl` beside this report. Condensed:")
    L.append("")
    for rec in records:
        mv = rec.get("movement") or "-"
        L.append(f"### Turn {rec['turn']} · movement {mv} · {rec['latency_s']:.0f}s · "
                 f"budget {rec['budget_total'] if rec['budget_total'] is not None else '?'} tok")
        L.append(f"**User:** {rec['user']}")
        L.append("")
        toolsig = ", ".join(
            f"{tc['tool']}({'∅' if _is_empty_intent(tc['tool'], tc.get('args') or {}) else ''}"
            f"{'ok' if tc.get('ok') else 'ERR' if tc.get('ok') is False else '?'})"
            for tc in rec["tools"]) or "—"
        L.append(f"**Tools:** {toolsig}")
        L.append("")
        asst = rec["assistant"] or "_(no text)_"
        if len(asst) > 1200:
            asst = asst[:1200] + " …[truncated — full text in transcript.jsonl]"
        L.append(f"**Assistant:** {asst}")
        L.append("")
    return "\n".join(L)


def main() -> int:
    if not MODEL_REF:
        raise SystemExit("QG_MODEL_REF is required (gemma's user_model UUID). "
                         "Resolve it via the SELECT in this file's docstring.")
    scen = json.loads(SCEN_PATH.read_text(encoding="utf-8"))
    # accept either a single-scenario file or {"scenarios":[...]}
    scenarios = scen["scenarios"] if isinstance(scen, dict) and "scenarios" in scen else [scen]
    scenarios = [s for s in scenarios if not ONLY or s.get("scenario") in ONLY or s.get("id") in ONLY]
    run_dir = OUT / LABEL
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "label": LABEL, "model_ref": MODEL_REF, "user": USER,
        "scenario_file": str(SCEN_PATH), "scenario_count": len(scenarios),
        "run_id": uuid.uuid4().hex[:12], "started_epoch": int(time.time()),
        "base": BASE,
    }
    print(f"[ds] run={LABEL} model={MODEL_REF} scenarios={len(scenarios)} file={SCEN_PATH.name}")
    created_sids: list[str] = []
    with httpx.Client() as c:
        for s in scenarios:
            sid_of = s.get("scenario") or s.get("id") or "S??"
            context = _substitute(s.get("context"))
            enabled_skills = s.get("enabled_skills") or []
            perm = s.get("permission_mode") or "write"
            mv_labels = {m["id"]: m.get("label", "") for m in (s.get("movements") or [])}
            sid = _create_session(c, f"ds-{LABEL}-{sid_of}")
            created_sids.append(sid)
            print(f"  - {sid_of:<10} session={sid[:8]} mode={perm} "
                  f"skills={enabled_skills} turns={len(s['turns'])}")
            records: list[dict] = []
            carry: dict = {}  # cross-turn session state (authentic confirm_token)
            for i, turn in enumerate(s["turns"]):
                utext = turn["user"] if isinstance(turn, dict) else str(turn)
                mv = turn.get("movement") if isinstance(turn, dict) else None
                t0 = time.time()
                try:
                    res = _send_turn(c, sid, utext, context=context, carry=carry,
                                     enabled_skills=enabled_skills, permission_mode=perm)
                except Exception as exc:
                    # A transient infra hiccup on ONE turn (e.g. a languagetool-OOM 502 on
                    # a late wrap-up turn) must not discard the whole run's metrics — record
                    # the turn as errored and keep going so the report + metrics still write.
                    dt = time.time() - t0
                    print(f"      turn {i} [{mv or '-'}]: ERRORED after {dt:.0f}s — {type(exc).__name__}: {str(exc)[:120]}")
                    records.append({
                        "scenario": sid_of, "turn": i, "movement": mv,
                        "movement_label": mv_labels.get(mv, ""), "user": utext,
                        "assistant": "", "budget_total": None, "budget": None,
                        "tools": [], "latency_s": round(dt, 1), "session_id": sid,
                        "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                    })
                    continue
                dt = time.time() - t0
                rec = {
                    "scenario": sid_of, "turn": i,
                    "movement": mv, "movement_label": mv_labels.get(mv, ""),
                    "user": utext, "assistant": res["assistant"],
                    "budget_total": res["budget_total"], "budget": res["budget"],
                    "tools": res["tools"], "latency_s": round(dt, 1),
                    "session_id": sid,
                }
                records.append(rec)
                empties = sum(1 for tc in res["tools"]
                              if _is_empty_intent(tc["tool"], tc.get("args") or {}))
                print(f"      turn {i} [{mv or '-'}]: {len(res['assistant'])} chars, "
                      f"budget={rec['budget_total'] if rec['budget_total'] is not None else '?'} tok, "
                      f"{len(res['tools'])} tools ({empties} empty-intent), {dt:.0f}s")

            metrics = _compute_metrics(records, s)
            slug = sid_of
            (run_dir / f"{slug}-transcript.jsonl").write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
                encoding="utf-8")
            (run_dir / f"{slug}-metrics.json").write_text(
                json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
            report = _render_report(s, records, metrics, meta)
            (run_dir / f"{slug}-report.md").write_text(report, encoding="utf-8")
            print(f"    [{slug}] empty-intent={metrics['empty_intent_find_tools']} "
                  f"discovery={metrics['discovery_calls_total']} "
                  f"max-consec={metrics['max_consecutive_same_call']} "
                  f"async-no-read={metrics['async_jobs_without_status_read']}")

    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[ds] wrote reports to {run_dir}")

    if created_sids and os.environ.get("QG_KEEP_SESSIONS") != "1":
        with httpx.Client() as c:
            deleted = 0
            for sid in created_sids:
                try:
                    r = c.delete(f"{BASE}/v1/chat/sessions/{sid}",
                                 headers={"Authorization": f"Bearer {_bearer()}"}, timeout=15)
                    if r.status_code in (200, 204):
                        deleted += 1
                except Exception:
                    pass
        print(f"[ds] cleaned up {deleted}/{len(created_sids)} sessions (QG_KEEP_SESSIONS=1 to keep)")
    else:
        print("[ds] kept sessions (QG_KEEP_SESSIONS=1) — pull tool_calls JSONB for deep analysis")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
