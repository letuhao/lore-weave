"""Context Budget OPTIMIZATION SWEEP driver (methodology:
docs/eval/context-budget/OPTIMIZATION-EVAL-METHODOLOGY.md).

A superset of run_quality_gate.py: drives the real chat agent over a scenario set and captures
the MULTI-OBJECTIVE metrics the sweep needs — per turn: reply · contextBudget · input tokens
(post-compaction, the billed prompt) · OUTPUT tokens (script-aware, via the in-container kernel
estimator) · tool calls · COMPACTION events (fired? summarized? tokens before→after) ·
first-token + total latency. Then a per-session AGGREGATION: session input/output totals, the
HIDDEN summarizer/subagent spend, and session_total_est (the $ proxy).

All token figures are estimates (the script-aware estimator, consistent across A/B arms → valid
for RELATIVE comparison), not provider-billed truth (the usage-billing ledger is out of scope).

Runs IN-CONTAINER (docker exec infra-chat-service-1), same as run_quality_gate.py:
  docker cp scripts/eval/run_budget_sweep.py infra-chat-service-1:/tmp/sw.py
  docker exec -e SW_RUN_LABEL=C0_S1 -e SW_MODEL_REF=<uuid> -e SW_KG_PROJECT=<kg> \
    -e SW_SCENARIOS=/tmp/scen.json -e SW_OUT=/tmp/sw-out infra-chat-service-1 python /tmp/sw.py
  docker cp infra-chat-service-1:/tmp/sw-out ./docs/eval/context-budget/runs/
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import httpx
import jwt

try:
    from loreweave_context import estimate_tokens  # in-container: script-aware output estimate
except Exception:  # pragma: no cover — fallback if run outside the container
    def estimate_tokens(t: str | None) -> int:
        return max(1, len(t or "") // 4)

BASE = os.environ.get("SW_BASE", "http://localhost:8090")
SECRET = os.environ["JWT_SECRET"]
USER = os.environ.get("SW_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
MODEL_REF = os.environ.get("SW_MODEL_REF", "019eeb08-8be3-78fb-86c0-3b1eda7e0457")
PROJECT_ID = os.environ.get("SW_PROJECT_ID") or None
KG_PROJECT = os.environ.get("SW_KG_PROJECT") or None
LABEL = os.environ.get("SW_RUN_LABEL", "run")
OUT = Path(os.environ.get("SW_OUT", "/tmp/sw-out"))
ONLY = {s for s in os.environ.get("SW_ONLY", "").split(",") if s}
SCEN_PATH = Path(os.environ.get("SW_SCENARIOS", str(Path(__file__).with_name("context_budget_scenarios.json"))))
SUMMARY_OUTPUT_EST = 900  # compact_service summarizer max_tokens (hidden-spend output upper bound)


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


def _create_session(c: httpx.Client, title: str, bind: bool) -> str:
    body = {"title": title, "model_source": "user_model", "model_ref": MODEL_REF}
    if bind and PROJECT_ID:
        body["project_id"] = PROJECT_ID
    if bind and KG_PROJECT:
        body["project_ids"] = [KG_PROJECT]
    r = c.post(f"{BASE}/v1/chat/sessions", json=body, headers={"Authorization": f"Bearer {_bearer()}"})
    r.raise_for_status()
    return r.json()["session_id"]


def _send_turn(c: httpx.Client, sid: str, content: str) -> dict:
    budget = None
    text_parts: list[str] = []
    tool_calls: list[str] = []
    compactions: list[dict] = []
    t0 = time.time()
    t_first = None
    hdr = {"Authorization": f"Bearer {_bearer()}", "Accept": "text/event-stream",
           "x-loreweave-stream-format": os.environ.get("SW_STREAM_FORMAT", "agui")}
    with c.stream("POST", f"{BASE}/v1/chat/sessions/{sid}/messages",
                  json={"content": content}, headers=hdr, timeout=900) as resp:
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
            elif name == "compaction" and isinstance(obj.get("value"), dict):
                compactions.append(obj["value"])
            typ = obj.get("type") or ""
            if "TEXT_MESSAGE_CONTENT" in typ and obj.get("delta"):
                if t_first is None:
                    t_first = time.time()
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
    return {
        "assistant": text,
        "budget": budget,
        "input_tokens": _budget_total(budget),         # billed prompt (post-compaction)
        "output_tokens": estimate_tokens(text),
        "tool_calls": tool_calls,
        "compactions": compactions,
        "latency_first_s": round(t_first - t0, 2) if t_first else None,
        "latency_turn_s": round(time.time() - t0, 1),
    }


def _aggregate(turns: list[dict]) -> dict:
    """Session-level cost/UX aggregation (the hidden-spend-inclusive $ proxy)."""
    total_in = sum(t["input_tokens"] or 0 for t in turns)
    total_out = sum(t["output_tokens"] or 0 for t in turns)
    comp_turns = [t for t in turns if t["compactions"]]
    summ_calls = 0
    summ_tokens = 0
    for t in comp_turns:
        for c in t["compactions"]:
            steps = c.get("steps") or []
            if c.get("summarized") or "summarize" in steps or "breadcrumb" in steps:
                summ_calls += 1
                # hidden spend: the summarizer processes ~the pre-compaction middle (input)
                # + emits up to SUMMARY_OUTPUT_EST (output). Upper-bound estimate.
                summ_tokens += int(c.get("tokens_before") or 0) + SUMMARY_OUTPUT_EST
    subagent_calls = sum(t["tool_calls"].count("run_subagent") for t in turns)
    convsearch_calls = sum(t["tool_calls"].count("conversation_search") for t in turns)
    session_total = total_in + total_out + summ_tokens
    lat_turns = [t["latency_turn_s"] for t in turns if t["latency_turn_s"] is not None]
    lat_first = [t["latency_first_s"] for t in turns if t["latency_first_s"] is not None]
    return {
        "turns": len(turns),
        "session_input_tokens": total_in,
        "session_output_tokens": total_out,
        "summarizer_calls": summ_calls,
        "summarizer_tokens_est": summ_tokens,
        "subagent_calls": subagent_calls,
        "conversation_search_calls": convsearch_calls,
        "compaction_turns": len(comp_turns),
        "session_total_est": session_total,
        "overhead_ratio": round(summ_tokens / session_total, 3) if session_total else 0.0,
        "latency_turn_avg_s": round(sum(lat_turns) / len(lat_turns), 1) if lat_turns else None,
        "latency_first_avg_s": round(sum(lat_first) / len(lat_first), 2) if lat_first else None,
    }


def main() -> int:
    scen = json.loads(SCEN_PATH.read_text(encoding="utf-8"))
    scenarios = [s for s in scen["scenarios"] if not ONLY or s["id"] in ONLY]
    run_dir = OUT / LABEL
    run_dir.mkdir(parents=True, exist_ok=True)
    bind = bool(PROJECT_ID or KG_PROJECT)
    lines: list[str] = []
    sessions_meta: list[dict] = []
    created: list[str] = []
    print(f"[sweep] run={LABEL} model={MODEL_REF} scenarios={len(scenarios)} lore={'yes' if bind else 'NO'}")
    with httpx.Client() as c:
        for s in scenarios:
            sid = _create_session(c, f"sw-{LABEL}-{s['id']}", bind=bind)
            created.append(sid)
            turns: list[dict] = []
            print(f"  - {s['id']:<22} session={sid[:8]} turns={len(s['turns'])}")
            for i, turn in enumerate(s["turns"]):
                res = _send_turn(c, sid, turn)
                rec = {"scenario": s["id"], "tag": s.get("tag", ""), "turn": i,
                       "needs_lore": bool(s.get("needs_lore")),
                       "ground_truth": s.get("ground_truth", ""),
                       "user": turn, "session_id": sid, **res}
                lines.append(json.dumps(rec, ensure_ascii=False))
                turns.append(res)
                print(f"      t{i}: {len(res['assistant'])}c in={res['input_tokens']} "
                      f"out={res['output_tokens']} comp={len(res['compactions'])} "
                      f"tools={res['tool_calls']} {res['latency_turn_s']}s")
            agg = _aggregate(turns)
            sessions_meta.append({"scenario": s["id"], "session_id": sid, **agg})
            print(f"    => session_total_est={agg['session_total_est']} "
                  f"summ_calls={agg['summarizer_calls']} overhead={agg['overhead_ratio']}")
    (run_dir / "transcript.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run_dir / "session_metrics.json").write_text(
        json.dumps({"label": LABEL, "model_ref": MODEL_REF, "kg_project": KG_PROJECT,
                    "run_id": uuid.uuid4().hex[:12], "sessions": sessions_meta}, indent=2),
        encoding="utf-8")
    print(f"[sweep] wrote {run_dir}/transcript.jsonl + session_metrics.json")
    if created and os.environ.get("SW_KEEP_SESSIONS") != "1":
        with httpx.Client() as c:
            for sid in created:
                try:
                    c.delete(f"{BASE}/v1/chat/sessions/{sid}",
                             headers={"Authorization": f"Bearer {_bearer()}"}, timeout=15)
                except Exception:
                    pass
        print(f"[sweep] cleaned up {len(created)} sessions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
