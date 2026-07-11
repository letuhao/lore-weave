"""Step 5 — the DESCRIPTION-QUALITY (F5) selection signal, safely and at $0.

The question this answers is NOT the workflow gate (a workflow step names its tool; nothing
selects it — that decision was made explicitly). It is the **chat-surface** question: *given
a tool's description, can a model tell when to use it?* A tool a model cannot pick from its
own words is a **description bug**, and hiding it would guarantee it is never picked.

Why a CLASSIFICATION proxy, not the real agent loop:
  * The real loop runs writes. Bulk-driving a model over 146 tools would execute them — a
    user-scoped write against the real account is not acceptable for a measurement.
  * The loop also uses lazy tool-loading (`tool_list`→`tool_load`→call), so a single turn
    rarely reaches the target tool cleanly (verified: `plan`/`ask` modes stop at discovery).
So we take the model OUT of the loop: present the whole catalog as text and ask which ONE
tool fits a natural-language request. Nothing executes. It is a PROXY — it isolates
description-discriminability with every sibling present as a distractor (a hard, honest test)
— not a reproduction of the lazy-loaded chat experience. Real-loop selection is a stricter,
separate bar.

The request is the tool's OWN `_meta.synonyms` (the trigger phrases the tool ships as "this
is what a user would say"). If the model cannot map a tool's own synonym back to it with the
catalog in front of it, the description does not distinguish it from its siblings.

Routes through provider-registry via the `loreweave_llm` SDK (sanctioned model path), local
gemma, $0.
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
from .sweep import _list_tools

OUT_DIR = Path("docs/eval/tool-liveness")


def _synonym_ask(tool: dict) -> str | None:
    """The user request to route — the tool's longest synonym (the most descriptive trigger
    phrase it ships). None ⇒ no synonyms, so this tool cannot be probed this way."""
    syns = (tool.get("meta") or {}).get("synonyms") or []
    syns = [s for s in syns if isinstance(s, str) and s.strip()]
    return max(syns, key=len) if syns else None


def _catalog_text(tools: list[dict]) -> str:
    """Every tool as `name: description` — the full distractor set."""
    lines = []
    for t in tools:
        desc = (t.get("description") or "").strip().replace("\n", " ")
        lines.append(f"{t['name']}: {desc[:160]}")
    return "\n".join(lines)


def _prompt(catalog: str, ask: str) -> str:
    return (
        "You are a tool router. Below is the full catalog of available tools, one per line "
        "as `name: description`.\n\n"
        f"{catalog}\n\n"
        f'A user says: "{ask}"\n\n'
        "Which ONE tool should be called to satisfy that request? "
        "Reply with ONLY the exact tool name from the catalog — no punctuation, no explanation."
    )


def _score(answer: str, expected: str, all_names: set[str]) -> tuple[str, str]:
    """(verdict, picked). HIT if the model named the expected tool; MISS-<other> if it named
    a different real tool; MISS-none if it named nothing recognizable."""
    a = (answer or "").strip().strip("`\"'.").splitlines()[0].strip() if answer else ""
    a = a.strip().strip("`\"'.")
    if a == expected:
        return "HIT", a
    # tolerant: the expected name appears as a token in the answer
    if expected in a.split():
        return "HIT", expected
    picked = next((n for n in all_names if n == a or n in a.split()), None)
    return (f"MISS", picked or "(unrecognized)")


async def _complete(client: Client, model_ref: str, prompt: str) -> str:
    req = StreamRequest(
        model_source="user_model", model_ref=UUID(model_ref),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=40, temperature=0.0, reasoning_effort="none")
    out: list[str] = []
    # Drain to DoneEvent — never break early (that races the async-gen aclose).
    async for ev in client.stream(req, user_id=config.USER_ID):
        if isinstance(ev, TokenEvent):
            out.append(ev.delta)
        elif isinstance(ev, DoneEvent):
            pass
    return "".join(out)


def _discoverable(tools: list[dict]) -> list[dict]:
    """Drop `visibility: legacy` tools — production EXCLUDES them from the agent's
    discoverable set (they stay callable only via an explicit per-session pin). Including
    them as distractors makes the test unfaithful and manufactures misses against
    already-deprecated siblings (e.g. `glossary_book_delete`, superseded by
    `glossary_ontology_delete`). The proxy must see the set the agent actually sees."""
    return [t for t in tools if (t.get("meta") or {}).get("visibility") != "legacy"]


async def run(limit: int | None, only_service: str | None) -> list[dict]:
    tools = _discoverable(await _list_tools())
    all_names = {t["name"] for t in tools}
    catalog = _catalog_text(tools)
    probeable = [t for t in tools if _synonym_ask(t)
                 and (not only_service or t["name"].startswith(only_service))]
    if limit:
        probeable = probeable[:limit]
    print(f"catalog {len(tools)} tools · {len(probeable)} probeable (have synonyms)"
          + (f" · filtered to {only_service}*" if only_service else ""))

    client = Client(base_url=config.DOMAIN_BASE.get("provider_registry",
                                                    "http://localhost:8208"),
                    auth_mode="internal", internal_token=config.INTERNAL_TOKEN,
                    user_id=config.USER_ID)
    rows: list[dict] = []
    try:
        for i, t in enumerate(probeable):
            ask = _synonym_ask(t)
            try:
                answer = await _complete(client, config.MODEL_REF, _prompt(catalog, ask))
                verdict, picked = _score(answer, t["name"], all_names)
            except Exception as e:
                verdict, picked, answer = "ERROR", f"{type(e).__name__}", str(e)[:120]
            rows.append({"tool": t["name"], "ask": ask, "verdict": verdict,
                         "picked": picked, "answer": answer[:80]})
            if (i + 1) % 10 == 0:
                hits = sum(1 for r in rows if r["verdict"] == "HIT")
                print(f"  {i+1}/{len(probeable)} · {hits} hit so far")
    finally:
        await client.aclose()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="probe only the first N tools")
    ap.add_argument("--service", default=None, help="only tools whose name starts with this")
    ap.add_argument("--date", default="selection", help="output subdir")
    args = ap.parse_args()

    rows = asyncio.run(run(args.limit, args.service))
    hits = [r for r in rows if r["verdict"] == "HIT"]
    misses = [r for r in rows if r["verdict"] == "MISS"]
    errs = [r for r in rows if r["verdict"] == "ERROR"]
    n = len(rows) or 1
    print(f"\nselection (description-quality proxy): {len(hits)}/{len(rows)} "
          f"discoverable ({100*len(hits)//n}%) · {len(misses)} miss · {len(errs)} error")
    print("\nDESCRIPTION-QUALITY MISSES (a model could not pick the tool from its own synonym):")
    for r in sorted(misses, key=lambda r: r["tool"]):
        print(f"  {r['tool']:<40} ask={r['ask']!r:<34} → picked {r['picked']}")

    out = OUT_DIR / args.date
    out.mkdir(parents=True, exist_ok=True)
    (out / "selection.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    print(f"\nwrote {out / 'selection.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
