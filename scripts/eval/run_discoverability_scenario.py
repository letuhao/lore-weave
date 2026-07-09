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
REPORT_DATE = os.environ.get("QG_REPORT_DATE", "run")

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
    "plan_propose_spec", "kg_build_graph", "kg_build_wiki",
    "composition_generate", "glossary_extract_entities_from_doc",
    "translation_start", "translation_run",
}
# Result keys that carry an async job/operation handle.
_JOB_ID_KEYS = ("job_id", "operation_id", "task_id", "run_id", "arc_id")
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

# Thresholds (S06 §10). Breach = degraded-pass, recorded (not a hard fail).
THRESH_TURN_SECONDS = 250          # no single turn > 250s (loop-termination line)
THRESH_TTFUO_SECONDS = 90          # time-to-first-useful-output per movement
THRESH_CONSEC_SAME_TOOL = 3        # > 3 consecutive same-tool, no state change


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
    return jwt.encode({"sub": USER, "iat": now, "exp": now + 3600}, SECRET, algorithm="HS256")


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
               permission_mode: str | None) -> dict:
    """POST a turn as the GUI does; drain the SSE; capture assistant text, the
    full tool records (name + args + result ok/error) correlated by toolCallId,
    and the context budget."""
    budget = None
    text_parts: list[str] = []
    # tool records keyed by toolCallId while streaming, flushed to a list in order
    open_calls: dict[str, dict] = {}
    order: list[str] = []
    hdr = {"Authorization": f"Bearer {_bearer()}", "Accept": "text/event-stream"}
    hdr["x-loreweave-stream-format"] = os.environ.get("QG_STREAM_FORMAT", "agui")
    body: dict = {"content": content, "enabled_skills": enabled_skills}
    if permission_mode:
        body["permission_mode"] = permission_mode
    if context:
        body.update(context)  # {"book_context": {...}} etc.
    with c.stream("POST", f"{BASE}/v1/chat/sessions/{sid}/messages",
                  json=body, headers=hdr, timeout=TURN_TIMEOUT) as resp:
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
            name = obj.get("name")
            if name == "contextBudget" and isinstance(obj.get("value"), dict):
                budget = obj["value"]
            typ = obj.get("type") or ""
            if "TEXT_MESSAGE_CONTENT" in typ and obj.get("delta"):
                text_parts.append(obj["delta"])
            elif "TOOL_CALL_START" in typ and obj.get("toolCallName"):
                cid = obj.get("toolCallId") or str(uuid.uuid4())
                open_calls[cid] = {"tool": obj["toolCallName"], "args": {},
                                   "ok": None, "result": None, "error": None}
                order.append(cid)
            elif "TOOL_CALL_ARGS" in typ:
                cid = obj.get("toolCallId")
                delta = obj.get("delta") or ""
                if cid in open_calls and delta:
                    prev = open_calls[cid].get("_argstr", "")
                    open_calls[cid]["_argstr"] = prev + delta
            elif "TOOL_CALL_RESULT" in typ:
                cid = obj.get("toolCallId")
                if cid in open_calls:
                    try:
                        env = json.loads(obj.get("content") or "{}")
                        open_calls[cid]["ok"] = env.get("ok")
                        open_calls[cid]["result"] = env.get("result")
                        open_calls[cid]["error"] = env.get("error")
                    except Exception:
                        open_calls[cid]["result"] = obj.get("content")
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
        # count effectful (non-read, non-discovery) successful tool calls this turn
        for tc in rec["tools"]:
            nm = tc["tool"]
            if (nm not in DISCOVERY_TOOLS and not _READONLY_RE.search(nm)
                    and tc.get("ok") is not False):
                cumulative_write_tools += 1
        # false-persistence candidate: a "saved/locked/permanent" claim while the
        # session has persisted NOTHING (zero effectful tool calls so far).
        if cumulative_write_tools == 0:
            mclaim = _PERSIST_CLAIM_RE.search(rec["assistant"] or "")
            if mclaim:
                snip = rec["assistant"]
                idx = mclaim.start()
                persist_claims_without_write.append({
                    "turn": turn,
                    "claim": snip[max(0, idx - 30): idx + 80].replace("\n", " ").strip(),
                })
        hits = _scan_jargon(rec["assistant"], denylist)
        if hits:
            jargon_candidates.append({"turn": turn, "words": hits})

    # per-movement rollup
    movements: dict[str, dict] = {}
    for rec in records:
        mv = rec.get("movement") or "-"
        m = movements.setdefault(mv, {
            "turns": 0, "tool_calls": 0, "discovery_calls": 0,
            "empty_intent": 0, "max_turn_s": 0.0, "ttfuo_s": None,
            "label": rec.get("movement_label", ""),
        })
        m["turns"] += 1
        m["tool_calls"] += len(rec["tools"])
        m["discovery_calls"] += sum(1 for tc in rec["tools"] if tc["tool"] in DISCOVERY_TOOLS)
        m["empty_intent"] += sum(1 for tc in rec["tools"]
                                 if _is_empty_intent(tc["tool"], tc.get("args") or {}))
        m["max_turn_s"] = max(m["max_turn_s"], rec["latency_s"])
        if m["ttfuo_s"] is None and rec["assistant"].strip():
            m["ttfuo_s"] = rec["latency_s"]

    # auto no-thrash verdict per movement (purely instrumental — allowed to be auto)
    for mv, m in movements.items():
        thrash = (m["empty_intent"] > 0 or m["max_turn_s"] > THRESH_TURN_SECONDS
                  or max_consec > THRESH_CONSEC_SAME_TOOL)
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
            for i, turn in enumerate(s["turns"]):
                utext = turn["user"] if isinstance(turn, dict) else str(turn)
                mv = turn.get("movement") if isinstance(turn, dict) else None
                t0 = time.time()
                res = _send_turn(c, sid, utext, context=context,
                                 enabled_skills=enabled_skills, permission_mode=perm)
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
