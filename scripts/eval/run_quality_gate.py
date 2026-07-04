"""Context Budget quality-gate DRIVER (spec docs/specs/context-budget-quality-gate.md §2).

Drives the REAL chat agent (context assembly → tool calls → prose reply) over the
scenario set and records, per turn, the agent's reply + the persisted `contextBudget`
frame (token cost). One run = one config (baseline vs candidate); the judge subagent
then scores the transcripts BLIND (it never learns which run is which).

Runs INSIDE the docker network (reaches chat-service by localhost:8090 from within
its own container, or by service name from a sibling) so it can mint a JWT from
JWT_SECRET and use the real HTTP path — the true stack, not a mock.

Usage (in-container, the proven pattern from scripts/smoke_compose_generate_live.py):
  docker cp scripts/eval/run_quality_gate.py infra-chat-service-1:/tmp/qg.py
  docker cp scripts/eval/context_budget_scenarios.json infra-chat-service-1:/tmp/scen.json
  docker exec \
    -e QG_RUN_LABEL=baseline \
    -e QG_MODEL_REF=019ebb72-27a2-72f3-a42d-d2d0e0ded179 \
    -e QG_PROJECT_ID=<book_id> -e QG_KG_PROJECT=<kg_project_id> \
    -e QG_SCENARIOS=/tmp/scen.json -e QG_OUT=/tmp/qg-out \
    infra-chat-service-1 python /tmp/qg.py
  docker cp infra-chat-service-1:/tmp/qg-out ./docs/eval/context-budget/runs/

Env:
  JWT_SECRET, INTERNAL_SERVICE_TOKEN   (present in the chat-service container)
  QG_RUN_LABEL   baseline|candidate|<free>   (names the output dir + transcript)
  QG_MODEL_REF   a chat+tool_calling user_model UUID (default: gemma-4-26b 200K)
  QG_USER        owner user id (default: claude-test)
  QG_PROJECT_ID  book_id to bind (grounding context); optional
  QG_KG_PROJECT  knowledge project id for memory/graph grounding; optional
  QG_SCENARIOS   path to scenarios json (default: alongside this file)
  QG_OUT         output dir (default: /tmp/qg-out)
  QG_ONLY        comma list of scenario ids to run (default: all)
  QG_BASE        chat-service base URL (default: http://localhost:8090)
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import httpx
import jwt

BASE = os.environ.get("QG_BASE", "http://localhost:8090")
SECRET = os.environ["JWT_SECRET"]
INTERNAL = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
USER = os.environ.get("QG_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
MODEL_REF = os.environ.get("QG_MODEL_REF", "019ebb72-27a2-72f3-a42d-d2d0e0ded179")
PROJECT_ID = os.environ.get("QG_PROJECT_ID") or None
KG_PROJECT = os.environ.get("QG_KG_PROJECT") or None
LABEL = os.environ.get("QG_RUN_LABEL", "run")
OUT = Path(os.environ.get("QG_OUT", "/tmp/qg-out"))
ONLY = {s for s in os.environ.get("QG_ONLY", "").split(",") if s}
SCEN_PATH = Path(os.environ.get("QG_SCENARIOS", str(Path(__file__).with_name("context_budget_scenarios.json"))))


def _bearer() -> str:
    now = int(time.time())
    return jwt.encode({"sub": USER, "iat": now, "exp": now + 3600}, SECRET, algorithm="HS256")


def _budget_total(frame: dict | None) -> int | None:
    """The single token number the meter shows — tolerant to key drift."""
    if not isinstance(frame, dict):
        return None
    for k in ("total_tokens", "total", "used_tokens", "tokens", "context_tokens"):
        v = frame.get(k)
        if isinstance(v, (int, float)):
            return int(v)
    return None


def _create_session(c: httpx.Client, title: str, bind_lore: bool) -> str:
    body = {
        "title": title,
        "model_source": "user_model",
        "model_ref": MODEL_REF,
    }
    if bind_lore and PROJECT_ID:
        body["project_id"] = PROJECT_ID
    if bind_lore and KG_PROJECT:
        body["project_ids"] = [KG_PROJECT]
    r = c.post(f"{BASE}/v1/chat/sessions", json=body, headers={"Authorization": f"Bearer {_bearer()}"})
    r.raise_for_status()
    return r.json()["session_id"]


def _send_turn(c: httpx.Client, sid: str, content: str) -> dict:
    """POST a turn, drain the SSE stream (runs the agent), capture the contextBudget
    frame + assistant text from the stream; fall back to the GET endpoints. Tolerant
    to stream-format so it survives an AG-UI vs legacy toggle."""
    budget = None
    text_parts: list[str] = []
    tool_calls: list[str] = []
    hdr = {"Authorization": f"Bearer {_bearer()}", "Accept": "text/event-stream"}
    with c.stream("POST", f"{BASE}/v1/chat/sessions/{sid}/messages",
                  json={"content": content}, headers=hdr, timeout=600) as resp:
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
            if "TOOL_CALL_START" in typ and obj.get("toolCallName"):
                tool_calls.append(obj["toolCallName"])
    # fallbacks (format-independent)
    if budget is None:
        try:
            gb = c.get(f"{BASE}/v1/chat/sessions/{sid}/context-budget",
                       headers={"Authorization": f"Bearer {_bearer()}"}, timeout=30)
            if gb.status_code == 200:
                budget = gb.json().get("budget")
        except Exception:
            pass
    text = "".join(text_parts).strip()
    if not text:
        try:
            gm = c.get(f"{BASE}/v1/chat/sessions/{sid}/messages",
                       headers={"Authorization": f"Bearer {_bearer()}"}, timeout=30)
            if gm.status_code == 200:
                items = gm.json().get("items") or gm.json().get("messages") or []
                asst = [m for m in items if m.get("role") == "assistant"]
                if asst:
                    text = (asst[-1].get("content") or "").strip()
        except Exception:
            pass
    return {"assistant": text, "budget": budget, "budget_total": _budget_total(budget),
            "tool_calls": tool_calls}


def main() -> int:
    scen = json.loads(SCEN_PATH.read_text(encoding="utf-8"))
    scenarios = [s for s in scen["scenarios"] if not ONLY or s["id"] in ONLY]
    run_dir = OUT / LABEL
    run_dir.mkdir(parents=True, exist_ok=True)
    transcript = run_dir / "transcript.jsonl"
    meta = {
        "label": LABEL, "model_ref": MODEL_REF, "user": USER,
        "project_id": PROJECT_ID, "kg_project": KG_PROJECT,
        "scenario_count": len(scenarios), "run_id": uuid.uuid4().hex[:12],
        "started_epoch": int(time.time()),
    }
    print(f"[qg] run={LABEL} model={MODEL_REF} scenarios={len(scenarios)} "
          f"lore_bound={'yes' if (PROJECT_ID or KG_PROJECT) else 'NO'}")
    lines: list[str] = []
    with httpx.Client() as c:
        for s in scenarios:
            needs = bool(s.get("needs_lore"))
            if needs and not (PROJECT_ID or KG_PROJECT):
                print(f"  - {s['id']:<24} SKIP (needs_lore but no QG_PROJECT_ID/QG_KG_PROJECT)")
                lines.append(json.dumps({"scenario": s["id"], "tag": s["tag"], "skipped": "needs_lore"}))
                continue
            sid = _create_session(c, f"qg-{LABEL}-{s['id']}", bind_lore=needs)
            print(f"  - {s['id']:<24} session={sid[:8]} turns={len(s['turns'])}")
            for i, turn in enumerate(s["turns"]):
                t0 = time.time()
                res = _send_turn(c, sid, turn)
                dt = time.time() - t0
                rec = {
                    "scenario": s["id"], "tag": s["tag"], "turn": i,
                    "needs_lore": needs, "ground_truth": s.get("ground_truth", ""),
                    "user": turn, "assistant": res["assistant"],
                    "budget_total": res["budget_total"], "budget": res["budget"],
                    "tool_calls": res["tool_calls"], "latency_s": round(dt, 1),
                    "session_id": sid,
                }
                lines.append(json.dumps(rec, ensure_ascii=False))
                bt = res["budget_total"]
                print(f"      turn {i}: {len(res['assistant'])} chars, "
                      f"budget={bt if bt is not None else '?'} tok, "
                      f"tools={res['tool_calls']}, {dt:.0f}s")
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[qg] wrote {transcript} ({len(lines)} turn records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
