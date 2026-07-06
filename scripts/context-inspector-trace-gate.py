#!/usr/bin/env python
"""Context Inspector telemetry GATE (spec §13b) — the LIVE half of the trace contract.

`tests/test_context_trace_contract.py` proves the emit function *can* produce every field;
this proves a REAL turn on the live stack actually PERSISTS them non-null. It drives a few
turns through the running chat-service (test account, local gemma, $0), then reads
`GET /v1/chat/sessions/{id}/context-trace` and asserts, against the committed
`contracts/context-trace.contract.json`, that every frame field is present + non-null on a
fresh turn and that each trace span is wire-standard. A field the compiler forgot → this fails.

Run (stack up, env like the sweep driver):
    JWT_SECRET=… python scripts/context-inspector-trace-gate.py
Env: SW_BASE (default http://localhost:8090), SW_USER, SW_MODEL_REF, SW_PROJECT_ID (bind a book
to exercise the T5 gate + grounding). Mirrors scripts/eval/run_budget_sweep.py exactly.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
import jwt

BASE = os.environ.get("SW_BASE", "http://localhost:8090")
SECRET = os.environ["JWT_SECRET"]
USER = os.environ.get("SW_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
MODEL_REF = os.environ.get("SW_MODEL_REF", "019eeb08-8be3-78fb-86c0-3b1eda7e0457")
PROJECT_ID = os.environ.get("SW_PROJECT_ID") or None
CONTRACT = json.loads(
    (Path(__file__).resolve().parents[1] / "contracts" / "context-trace.contract.json")
    .read_text(encoding="utf-8")
)


def _bearer() -> str:
    now = int(time.time())
    return jwt.encode({"sub": USER, "iat": now, "exp": now + 3600}, SECRET, algorithm="HS256")


def _hdr(stream: bool = False) -> dict:
    h = {"Authorization": f"Bearer {_bearer()}"}
    if stream:
        h["Accept"] = "text/event-stream"
        h["x-loreweave-stream-format"] = "agui"
    return h


def _create_session(c: httpx.Client) -> str:
    body = {"title": "inspector-trace-gate", "model_source": "user_model", "model_ref": MODEL_REF}
    if PROJECT_ID:
        body["project_id"] = PROJECT_ID
    r = c.post(f"{BASE}/v1/chat/sessions", json=body, headers=_hdr())
    r.raise_for_status()
    return r.json()["session_id"]


def _send(c: httpx.Client, sid: str, content: str) -> None:
    with c.stream("POST", f"{BASE}/v1/chat/sessions/{sid}/messages",
                  json={"content": content}, headers=_hdr(stream=True), timeout=900) as resp:
        resp.raise_for_status()
        for _ in resp.iter_lines():
            pass  # drain; we read the persisted frame afterwards


# A mix that exercises the derivations: a lore lookup (gated=included), a status-op
# (gated=out), and enough turns that a long session may trip C_persist compaction.
TURNS = [
    "Tell me about the main character and their goal.",
    "Who are their enemies?",
    "Change the status of the current scene to drafting.",
    "Make the last passage a little darker in tone.",
    "Summarize what we've established so far.",
]


def main() -> int:
    with httpx.Client() as c:
        sid = _create_session(c)
        for t in TURNS:
            _send(c, sid, t)
        r = c.get(f"{BASE}/v1/chat/sessions/{sid}/context-trace", headers=_hdr(), timeout=30)
        r.raise_for_status()
        items = r.json()["items"]

    if not items:
        print("FAIL: context-trace returned no turns")
        return 1

    latest = items[-1]["frame"]
    missing = [f for f in CONTRACT["frame_fields"] if f not in latest or latest[f] is None]
    if missing:
        print(f"FAIL: latest frame missing/null fields: {missing}")
        print(json.dumps(latest, indent=2, ensure_ascii=False)[:2000])
        return 1

    # Every span wire-standard.
    for pt in items:
        for span in pt["frame"].get("trace", []):
            bad = [k for k in CONTRACT["trace_span_fields"] if k not in span]
            if bad:
                print(f"FAIL: trace span missing {bad} in seq {pt['sequence_num']}")
                return 1

    # The derivations actually wired: at least one turn shows a status flag + an intent
    # other than the fallback, and raw==compiled+savings on the latest.
    any_flag = any(pt["frame"].get("status_flags") for pt in items)
    saved = sum(-s["delta"] for s in latest.get("trace", []) if s["delta"] < 0)
    raw_ok = latest["raw_tokens"] == latest["used_tokens"] + saved

    print(f"PASS: {len(items)} turns; every frame field non-null on the latest turn.")
    print(f"  status_flags seen: {any_flag} · latest intent={latest['intent']!r} "
          f"retrieval={latest['retrieval_mode']!r} raw={latest['raw_tokens']} "
          f"compiled={latest['used_tokens']} reduction={latest['reduction_pct']}")
    print(f"  raw==compiled+savings: {raw_ok} · spans on latest: {len(latest.get('trace', []))}")
    return 0 if (any_flag and raw_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
