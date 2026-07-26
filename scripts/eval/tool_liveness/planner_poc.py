"""Planner-executor POC — does a ONE-SHOT planner produce the right tool SEQUENCE
for weak models? ($0, live, across models.)

The executor half is unit-proven (app/services/tool_plan.py restrict_tools_to_plan:
the wrong sibling is not offered, so the model can't wander). The open question is
the PLANNER: given the catalog + a realistic request, does a weak model emit the
correct ordered tool names? The benchmark already showed weak models pick the right
SINGLE tool one-shot (Qwen3.6 6/6, Gemma 5/6); this checks the SEQUENCE.

Reuses the benchmark's catalog + $0 provider-registry path. The prompt/parse below
MIRROR app/services/tool_plan.py (kept inline so this harness has no chat-service
import); if you change one, change both.

Usage: python -m scripts.eval.tool_liveness.planner_poc \\
         --model 019ebb72-...:Gemma-200K --model 019f8384-...:Qwen3.6
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from uuid import UUID

from loreweave_llm.client import Client
from loreweave_llm.models import DoneEvent, StreamRequest, TokenEvent

from . import config
from .selection import _catalog_text
from .sweep import _list_tools

OUT_DIR = Path("docs/eval/tool-liveness")

# request -> the tool that MUST appear in the plan (the routing that failed live)
CASES = [
    {"ask": "Update this book's description to something more dramatic.", "must": "book_update_details"},
    {"ask": "Change the book's blurb.", "must": "book_update_details"},
    {"ask": "Set the genre to dark fantasy.", "must": "book_update_details"},
    {"ask": "Write a first chapter for my book.", "must": "book_chapter_create"},
    {"ask": "Save the chapter prose I just wrote.", "must": "book_chapter_save_draft"},
    {"ask": "Publish chapter 3 as canon.", "must": "book_chapter_publish"},
]

DEFAULT_MODELS = [
    ("019ebb72-27a2-72f3-a42d-d2d0e0ded179", "Gemma-4-26B-200K"),
    ("019f8384-b27e-76b4-bf4c-ba5ea0b46973", "Qwen3.6-35B-A3B"),
]


def _plan_prompt(catalog: str, ask: str) -> str:  # mirrors tool_plan.build_plan_prompt
    return (
        "You are a tool-use PLANNER. Below is the catalog of available tools, one "
        "per line as `name: description`.\n\n"
        f"{catalog}\n\n"
        f'The user says: "{ask}"\n\n'
        "Output ONLY a JSON array of the exact tool NAMES to call, in the order "
        "they should run, to fulfil the request — e.g. "
        '["book_list", "book_update_details"]. Include a read tool first only if '
        "you need an id you don't have. No prose, JSON array only. If NO tool is "
        "needed, output []."
    )


def _parse_plan(raw: str, known: set[str]) -> list[str]:  # mirrors tool_plan.parse_plan
    if not raw:
        return []
    s = raw.strip()
    f = re.search(r"```(?:json)?\s*(.+?)```", s, re.DOTALL)
    if f:
        s = f.group(1).strip()
    m = re.search(r"\[.*?\]", s, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except (json.JSONDecodeError, TypeError):
        return []
    out, seen = [], set()
    for it in arr if isinstance(arr, list) else []:
        n = it.strip() if isinstance(it, str) else ""
        if n in known and n not in seen:
            out.append(n); seen.add(n)
    return out


async def _complete(client: Client, ref: str, prompt: str) -> str:
    req = StreamRequest(model_source="user_model", model_ref=UUID(ref),
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=80, temperature=0.0, reasoning_effort="none")
    out: list[str] = []
    async for ev in client.stream(req, user_id=config.USER_ID):
        if isinstance(ev, TokenEvent):
            out.append(ev.delta)
        elif isinstance(ev, DoneEvent):
            pass
    return "".join(out)


async def run(models):
    tools = await _list_tools()
    known = {t["name"] for t in tools}
    catalog = _catalog_text(tools)
    client = Client(base_url=config.DOMAIN_BASE.get("provider_registry", "http://localhost:8208"),
                    auth_mode="internal", internal_token=config.INTERNAL_TOKEN, user_id=config.USER_ID)
    results = {"models": {}}
    try:
        for ref, label in models:
            rows, hits = [], 0
            for c in CASES:
                try:
                    plan = _parse_plan(await _complete(client, ref, _plan_prompt(catalog, c["ask"])), known)
                    ok = c["must"] in plan
                except Exception as e:  # noqa: BLE001
                    plan, ok = [f"ERROR:{type(e).__name__}"], False
                hits += ok
                rows.append({"ask": c["ask"], "must": c["must"], "plan": plan, "ok": ok})
            results["models"][label] = {"hits": hits, "total": len(rows), "rows": rows}
            print(f"── {label:<20} {hits}/{len(rows)} plans contain the right tool")
            for r in rows:
                print(f"     {'✓' if r['ok'] else '✗'} {r['ask']:<44} -> {r['plan']}")
            print()
    finally:
        await client.aclose()
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", help="uuid[:label] (repeatable)")
    ap.add_argument("--out", default="planner-poc")
    a = ap.parse_args()
    models = DEFAULT_MODELS if not a.model else [
        (m.split(":", 1)[0], (m.split(":", 1)[1] if ":" in m else m[:8])) for m in a.model]
    res = asyncio.run(run(models))
    print("═══ PLANNER SEQUENCE ACCURACY ═══")
    for label, m in sorted(res["models"].items(), key=lambda kv: -kv[1]["hits"]):
        print(f"  {label:<22} {m['hits']}/{m['total']}")
    out = OUT_DIR / a.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "planner.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out / 'planner.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
