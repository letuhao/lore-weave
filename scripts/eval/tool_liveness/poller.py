"""Async poller — for `_meta.async` tools, the tool call returns a job id (or
enqueues at confirm). Poll the domain's job-status tool to a terminal state, THEN
the effect oracle runs on the JOB'S ARTIFACT, not the job id.

"Started != done." A completion claim that is never preceded by a terminal
status-read is the async-honesty failure the discoverability harness flagged; here
we make the terminal read mandatory before G4.
"""
from __future__ import annotations

import json
import time

import httpx

from .auth import Auth
from .sse import send_turn

_TERMINAL = {"completed", "succeeded", "success", "failed", "cancelled",
             "completed_with_errors", "error", "done", "finished"}

# result keys that carry an async job/operation handle
JOB_ID_KEYS = ("job_id", "operation_id", "task_id", "run_id", "arc_id", "generation_job_id")


def find_job_id(result) -> str | None:
    if isinstance(result, dict):
        for k in JOB_ID_KEYS:
            v = result.get(k)
            if isinstance(v, str) and v:
                return v
        for v in result.values():
            j = find_job_id(v)
            if j:
                return j
    elif isinstance(result, list):
        for v in result:
            j = find_job_id(v)
            if j:
                return j
    return None


def status_of(obj) -> str | None:
    if not isinstance(obj, dict):
        return None
    for k in ("status", "state", "job_status"):
        v = obj.get(k)
        if isinstance(v, str) and v:
            return v.lower()
    return None


def poll_via_tool(client: httpx.Client, auth: Auth, sid: str, status_tool: str,
                  status_args: dict, *, tries: int = 60, delay: float = 8.0,
                  permission_mode: str = "ask") -> dict:
    """Poll by calling a status TOOL through the agent loop with an explicit ask.

    Returns {terminal: bool, status, last_result}. Note: we drive the status tool
    through the same NL surface, instructing the model to call it with fixed args —
    keeps the harness single-surface. For deterministic polling a direct MCP/REST
    call is also acceptable; this path keeps everything on the chat edge.
    """
    last = {"terminal": False, "status": None, "last_result": None}
    ask = (f"Call the tool {status_tool} with exactly these arguments and report the "
           f"status field verbatim: {json.dumps(status_args)}")
    for _ in range(tries):
        try:
            res = send_turn(client, auth, sid, ask, permission_mode=permission_mode)
        except Exception as e:
            last = {"terminal": False, "status": f"poll-error: {type(e).__name__}",
                    "last_result": None}
            time.sleep(delay)
            continue
        for tc in res["tools"]:
            if tc["tool"] == status_tool:
                st = status_of(tc.get("result"))
                last = {"terminal": st in _TERMINAL, "status": st,
                        "last_result": tc.get("result")}
                if st in _TERMINAL:
                    return last
        time.sleep(delay)
    return last
