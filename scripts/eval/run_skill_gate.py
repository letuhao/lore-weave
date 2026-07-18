"""Skill quality-gate DRIVER (docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-
standard.md Part E). A sibling of `run_quality_gate.py` (Context Budget effort) —
same proven pattern (real chat agent, real docker stack, SSE-drained turns, judge
scores blind afterward) — but scenarios test a SKILL's own stated tool-use rules
(e.g. "don't conflate write_prose with generate") rather than context-budget/lore
retrieval quality. The key difference: a skill scenario must FORCE the right surface
+ skill pin per turn (`book_context`/`editor_context`/`studio_context` +
`enabled_skills`), which `run_quality_gate.py`'s driver never needed to send.

Scenario shape (see scripts/eval/skill_scenarios/*.json):
  {"id", "tag", "skill", "context": {"book_context": {"book_id": "<BOOK_ID>"}} | null,
   "enabled_skills": [...], "ground_truth", "turns": [...]}

`<BOOK_ID>` / `<PROJECT_ID>` / `<CHAPTER_ID>` placeholders in `context` are
substituted from SKILL_BOOK_ID / SKILL_PROJECT_ID / SKILL_CHAPTER_ID env vars before
sending — the scenario authors never see a real id (kept swappable across accounts).

Usage (in-container, same pattern as run_quality_gate.py):
  docker cp scripts/eval/run_skill_gate.py infra-chat-service-1:/tmp/sg.py
  docker cp scripts/eval/skill_scenarios/book.json infra-chat-service-1:/tmp/scen.json
  docker exec \
    -e QG_RUN_LABEL=book -e QG_MODEL_REF=019ebb72-27a2-72f3-a42d-d2d0e0ded179 \
    -e SKILL_BOOK_ID=<book_id> -e SKILL_PROJECT_ID=<project_id> \
    -e QG_SCENARIOS=/tmp/scen.json -e QG_OUT=/tmp/sg-out \
    infra-chat-service-1 python /tmp/sg.py
  docker cp infra-chat-service-1:/tmp/sg-out ./docs/eval/skill-authoring/runs/

Env:
  JWT_SECRET             (present in the chat-service container)
  QG_RUN_LABEL            names the output dir + transcript (default: run)
  QG_MODEL_REF            a chat+tool_calling user_model UUID
  QG_USER                 owner user id (default: claude-test)
  SKILL_BOOK_ID            substituted for the "<BOOK_ID>" placeholder
  SKILL_PROJECT_ID         substituted for the "<PROJECT_ID>" placeholder
  SKILL_CHAPTER_ID         substituted for the "<CHAPTER_ID>" placeholder
  QG_SCENARIOS            path to a skill scenario json
  QG_OUT                  output dir (default: /tmp/sg-out)
  QG_ONLY                 comma list of scenario ids to run (default: all)
  QG_BASE                 chat-service base URL (default: http://localhost:8090)
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
USER = os.environ.get("QG_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
MODEL_REF = os.environ.get("QG_MODEL_REF", "019ebb72-27a2-72f3-a42d-d2d0e0ded179")
LABEL = os.environ.get("QG_RUN_LABEL", "run")
OUT = Path(os.environ.get("QG_OUT", "/tmp/sg-out"))
ONLY = {s for s in os.environ.get("QG_ONLY", "").split(",") if s}
SCEN_PATH = Path(os.environ["QG_SCENARIOS"])

_PLACEHOLDERS = {
    "<BOOK_ID>": os.environ.get("SKILL_BOOK_ID", ""),
    "<PROJECT_ID>": os.environ.get("SKILL_PROJECT_ID", ""),
    "<CHAPTER_ID>": os.environ.get("SKILL_CHAPTER_ID", ""),
}


def _substitute(obj):
    """Recursively replace placeholder strings in a scenario's `context` dict."""
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
    r = c.post(f"{BASE}/v1/chat/sessions", json=body, headers={"Authorization": f"Bearer {_bearer()}"})
    r.raise_for_status()
    return r.json()["session_id"]


def _send_turn(c: httpx.Client, sid: str, content: str, *, context: dict | None, enabled_skills: list[str]) -> dict:
    """POST a turn WITH the scenario's forced context (book/editor/studio) +
    enabled_skills pin, drain the SSE stream, capture reply + tools + budget."""
    budget = None
    text_parts: list[str] = []
    tool_calls: list[str] = []
    hdr = {"Authorization": f"Bearer {_bearer()}", "Accept": "text/event-stream"}
    hdr["x-loreweave-stream-format"] = os.environ.get("QG_STREAM_FORMAT", "agui")
    body: dict = {"content": content, "enabled_skills": enabled_skills}
    if context:
        body.update(context)  # e.g. {"book_context": {...}} or {"studio_context": {...}}
    with c.stream("POST", f"{BASE}/v1/chat/sessions/{sid}/messages",
                  json=body, headers=hdr, timeout=600) as resp:
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
        "scenario_file": str(SCEN_PATH), "scenario_count": len(scenarios),
        "run_id": uuid.uuid4().hex[:12], "started_epoch": int(time.time()),
    }
    print(f"[sg] run={LABEL} model={MODEL_REF} scenarios={len(scenarios)} file={SCEN_PATH.name}")
    lines: list[str] = []
    created_sids: list[str] = []
    with httpx.Client() as c:
        for s in scenarios:
            context = _substitute(s.get("context"))
            enabled_skills = s.get("enabled_skills") or []
            sid = _create_session(c, f"sg-{LABEL}-{s['id']}")
            created_sids.append(sid)
            print(f"  - {s['id']:<40} session={sid[:8]} skills={enabled_skills} turns={len(s['turns'])}")
            for i, turn in enumerate(s["turns"]):
                t0 = time.time()
                res = _send_turn(c, sid, turn, context=context, enabled_skills=enabled_skills)
                dt = time.time() - t0
                rec = {
                    "scenario": s["id"], "tag": s.get("tag", ""), "skill": s.get("skill", ""),
                    "turn": i, "ground_truth": s.get("ground_truth", ""),
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
    print(f"[sg] wrote {transcript} ({len(lines)} turn records)")

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
        print(f"[sg] cleaned up {deleted}/{len(created_sids)} sessions "
              f"(QG_KEEP_SESSIONS=1 to keep)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
