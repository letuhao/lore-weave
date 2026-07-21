"""Tool-selection benchmark — does a model route a REALISTIC user request to the
right tool, ACROSS models? ($0, local, out-of-loop classification proxy.)

Motivation (dogfood 2026-07-21): the auto-gate `book_update_details` (renamed from
the engineer-jargon `book_update_meta`) is CORRECT and ADVERTISED, yet local
Gemma-4 26B never selected it for "update the book's description" — it stopped at
`book_get` or reached for `book_chapter_save_draft`. Is that this one weak model,
or the phrasing/description? This benchmark answers it by running a CURATED set of
natural user requests (the phrasings a person actually types — NOT each tool's own
synonym, which `selection.py` already covers) through EACH model and scoring which
tool it picks, with the full catalog present as distractors.

Difference from `selection.py`:
  * selection.py asks with the tool's OWN longest synonym (description self-consistency).
  * THIS asks with a human's words ("change the blurb", "update the description") and a
    KNOWN expected tool — the routing question that actually failed live.
It is still a PROXY (whole catalog as text, pick one; nothing executes, no lazy
tool_load) — the real chat loop is a stricter, separate bar. But it isolates the
name/description routing signal and compares models head-to-head cheaply.

Usage (host, stack up):
  python -m scripts.eval.tool_liveness.tool_selection_benchmark \\
      --model 019ebb72-27a2-72f3-a42d-d2d0e0ded179:Gemma-4-26B-200K \\
      --model 019f837d-abe9-7bb0-9698-80329c9a24af:Nemotron-3-Nano
  # no --model → the built-in default set (Gemma 200K + Nemotron).
Env: see config.py (INTERNAL_TOKEN, USER_ID, provider_registry base).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from loreweave_llm.client import Client
from loreweave_llm.models import DoneEvent, StreamRequest, TokenEvent

from . import config
from .selection import _catalog_text, _score
from .sweep import _list_tools

OUT_DIR = Path("docs/eval/tool-liveness")

# The CURATED routing cases — realistic user phrasings → the ONE right tool. The
# `book_update_details` cases are the live bug (a person says "description/blurb/
# genre", never "meta"); the rest are the sibling distractors that must NOT win.
CASES: list[dict] = [
    # book DETAILS (the renamed metadata tool) — the failure class
    {"ask": "update the book's description", "expect": "book_update_details"},
    {"ask": "change the blurb", "expect": "book_update_details"},
    {"ask": "rewrite the synopsis", "expect": "book_update_details"},
    {"ask": "rename the book", "expect": "book_update_details"},
    {"ask": "set the genre to dark fantasy", "expect": "book_update_details"},
    {"ask": "fix the book's summary", "expect": "book_update_details"},
    # chapter prose / lifecycle — the distractors that stole the pick live
    {"ask": "write chapter one", "expect": "book_chapter_create"},
    {"ask": "save the chapter text I just wrote", "expect": "book_chapter_save_draft"},
    {"ask": "edit the prose of this chapter", "expect": "book_chapter_save_draft"},
    {"ask": "delete a chapter", "expect": "book_chapter_delete"},
    {"ask": "publish the chapter as canon", "expect": "book_chapter_publish"},
    # book lifecycle / read
    {"ask": "start a new novel", "expect": "book_create"},
    {"ask": "show my library of books", "expect": "book_list"},
    {"ask": "open the table of contents", "expect": "book_list_chapters"},
]

# Built-in default models (test account, provider-registry). Extend via --model.
DEFAULT_MODELS: list[tuple[str, str]] = [
    ("019ebb72-27a2-72f3-a42d-d2d0e0ded179", "Gemma-4-26B-200K"),
    ("019f837d-abe9-7bb0-9698-80329c9a24af", "Nemotron-3-Nano"),
]


def _prompt(catalog: str, ask: str) -> str:
    return (
        "You are a tool router. Below is the full catalog of available tools, one per line "
        "as `name: description`.\n\n"
        f"{catalog}\n\n"
        f'A user says: "{ask}"\n\n'
        "Which ONE tool should be called to satisfy that request? "
        "Reply with ONLY the exact tool name from the catalog — no punctuation, no explanation."
    )


async def _complete(client: Client, model_ref: str, prompt: str) -> str:
    req = StreamRequest(
        model_source="user_model", model_ref=UUID(model_ref),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=40, temperature=0.0, reasoning_effort="none")
    out: list[str] = []
    async for ev in client.stream(req, user_id=config.USER_ID):
        if isinstance(ev, TokenEvent):
            out.append(ev.delta)
        elif isinstance(ev, DoneEvent):
            pass
    return "".join(out)


async def run(models: list[tuple[str, str]]) -> dict:
    tools = await _list_tools()
    all_names = {t["name"] for t in tools}
    missing = {c["expect"] for c in CASES} - all_names
    if missing:
        print(f"⚠ expected tools not in the live catalog (renamed? not federated?): {sorted(missing)}")
    catalog = _catalog_text(tools)
    print(f"catalog {len(tools)} tools · {len(CASES)} cases · {len(models)} models\n")

    client = Client(base_url=config.DOMAIN_BASE.get("provider_registry", "http://localhost:8208"),
                    auth_mode="internal", internal_token=config.INTERNAL_TOKEN, user_id=config.USER_ID)
    results: dict = {"catalog_size": len(tools), "cases": CASES, "models": {}}
    try:
        for ref, label in models:
            rows: list[dict] = []
            for c in CASES:
                try:
                    answer = await _complete(client, ref, _prompt(catalog, c["ask"]))
                    verdict, picked = _score(answer, c["expect"], all_names)
                except Exception as e:  # noqa: BLE001 — record, never abort the matrix
                    verdict, picked, answer = "ERROR", type(e).__name__, str(e)[:120]
                rows.append({"ask": c["ask"], "expect": c["expect"],
                             "verdict": verdict, "picked": picked, "answer": (answer or "")[:60]})
            hits = sum(1 for r in rows if r["verdict"] == "HIT")
            results["models"][label] = {"model_ref": ref, "hits": hits, "total": len(rows), "rows": rows}
            pct = 100 * hits // (len(rows) or 1)
            print(f"── {label:<20} {hits}/{len(rows)}  ({pct}%)")
            for r in rows:
                mark = "✓" if r["verdict"] == "HIT" else "✗"
                extra = "" if r["verdict"] == "HIT" else f"  → picked {r['picked']}"
                print(f"     {mark} {r['ask']:<38} expect {r['expect']}{extra}")
            print()
    finally:
        await client.aclose()
    return results


def _parse_models(args_models: list[str] | None) -> list[tuple[str, str]]:
    if not args_models:
        return DEFAULT_MODELS
    out = []
    for m in args_models:
        ref, _, label = m.partition(":")
        out.append((ref.strip(), (label.strip() or ref.strip()[:8])))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Head-to-head tool-selection benchmark across models.")
    ap.add_argument("--model", action="append", help="user_model_id[:label] (repeatable). "
                    "Default: built-in Gemma-200K + Nemotron.")
    ap.add_argument("--out", default="tool-selection-benchmark", help="output subdir under docs/eval/tool-liveness/")
    args = ap.parse_args()

    results = asyncio.run(run(_parse_models(args.model)))

    print("═══ SUMMARY (higher = better routing) ═══")
    for label, m in sorted(results["models"].items(), key=lambda kv: -kv[1]["hits"]):
        pct = 100 * m["hits"] // (m["total"] or 1)
        print(f"  {label:<22} {m['hits']:>2}/{m['total']}  ({pct}%)")
    # The headline: the book_update_details ("description") sub-score per model.
    print("\n  book_update_details sub-score (the live bug — 'description/blurb/genre'):")
    for label, m in results["models"].items():
        det = [r for r in m["rows"] if r["expect"] == "book_update_details"]
        dh = sum(1 for r in det if r["verdict"] == "HIT")
        print(f"    {label:<22} {dh}/{len(det)}")

    out = OUT_DIR / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out / 'benchmark.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
