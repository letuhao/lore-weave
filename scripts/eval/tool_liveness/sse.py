"""SSE driver — post a natural-language turn, drain the stream, capture the FULL
tool record (name + args + ok + result envelope) per call.

Adapted from `scripts/eval/run_discoverability_scenario.py:198-289` (`_send_turn`)
— the proven agui SSE parse. Difference: TLE needs the tool RESULT (to find a
`confirm_token` / `job_id`) and the assistant text, per call, not just names.

SSE-with-JWT uses fetch-stream semantics (httpx streaming), NOT EventSource —
EventSource can't send an Authorization header (repo lesson
`sse-header-auth-needs-fetch-stream`).
"""
from __future__ import annotations

import json
import uuid

import httpx

from . import config
from .auth import Auth


def create_session(client: httpx.Client, auth: Auth, title: str,
                   base: str | None = None) -> str:
    base = base or config.GATEWAY
    r = client.post(
        f"{base}/v1/chat/sessions",
        json={"title": title, "model_source": "user_model", "model_ref": config.MODEL_REF},
        headers=auth.bearer_header(),
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["session_id"]


def parse_sse_line(line: str) -> dict | None:
    """Parse one `data:` SSE line into an event dict (None if not an event)."""
    if not line or not line.startswith("data:"):
        return None
    raw = line[5:].strip()
    if not raw or raw == "[DONE]":
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def fold_events(events: list[dict]) -> dict:
    """Fold a list of agui events into {assistant, tools[]}.

    Pure function (no I/O) so it is unit-testable against a captured event list.
    Each tool record: {tool, args, ok, result, error}.
    """
    text_parts: list[str] = []
    open_calls: dict[str, dict] = {}
    order: list[str] = []
    for obj in events:
        typ = obj.get("type") or ""
        if "TEXT_MESSAGE_CONTENT" in typ and obj.get("delta"):
            text_parts.append(obj["delta"])
        elif "TOOL_CALL_START" in typ and obj.get("toolCallName"):
            cid = obj.get("toolCallId") or str(uuid.uuid4())
            open_calls[cid] = {"tool": obj["toolCallName"], "args": {},
                               "ok": None, "result": None, "error": None, "_argstr": ""}
            order.append(cid)
        elif "TOOL_CALL_ARGS" in typ:
            cid = obj.get("toolCallId")
            delta = obj.get("delta") or ""
            if cid in open_calls and delta:
                open_calls[cid]["_argstr"] += delta
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
    return {"assistant": "".join(text_parts).strip(), "tools": tools}


def send_turn(client: httpx.Client, auth: Auth, sid: str, content: str, *,
              permission_mode: str = "write", context: dict | None = None,
              enabled_skills: list[str] | None = None,
              base: str | None = None) -> dict:
    """Post a turn as the GUI does; drain SSE; return {assistant, tools, raw_events}."""
    base = base or config.GATEWAY
    hdr = auth.bearer_header()
    hdr["Accept"] = "text/event-stream"
    hdr["x-loreweave-stream-format"] = config.STREAM_FORMAT
    body: dict = {"content": content, "enabled_skills": enabled_skills or []}
    if permission_mode:
        body["permission_mode"] = permission_mode
    if context:
        body.update(context)
    events: list[dict] = []
    with client.stream("POST", f"{base}/v1/chat/sessions/{sid}/messages",
                       json=body, headers=hdr, timeout=config.TURN_TIMEOUT) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            ev = parse_sse_line(line)
            if ev is not None:
                events.append(ev)
    folded = fold_events(events)
    folded["raw_events"] = events
    return folded
