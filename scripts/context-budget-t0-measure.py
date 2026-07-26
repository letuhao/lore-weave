#!/usr/bin/env python3
"""context-budget-t0-measure.py — T0 GATE anchor benchmark (spec §8, §9).

Measures the L3 (concise-wire) effect on REAL persisted tool-result payloads:
for every tool call stored in `loreweave_chat.chat_messages.tool_calls`, compare
the pre-T0 serialization (`json.dumps` — ensure_ascii=True default) against the
T0 funnel (`tool_result_content` — ensure_ascii=False + drop-None), in both bytes
and estimated tokens. Reports the aggregate reduction, worst offenders, and a
VI/CJK-only slice (where the \\uXXXX tax is largest).

This is the standing T0 benchmark: the 146K case was VI-heavy tool dumps, so the
real persisted VI tool results are the faithful replay corpus.

Usage:
  PYTHONPATH=services/chat-service python scripts/context-budget-t0-measure.py
  (connects to the dev postgres on the host-exposed port; override with env
   T0_DB_DSN=postgresql://user:pw@host:port/loreweave_chat)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

# Import the SUT helper + the same token estimator the compiler uses.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "chat-service"))
from app.services.tool_result_wire import tool_result_content, prune_none  # noqa: E402
from app.services.token_budget import estimate_tokens  # noqa: E402

DSN = os.environ.get("T0_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")


def _is_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


async def main() -> int:
    import asyncpg

    conn = await asyncpg.connect(DSN)
    rows = await conn.fetch(
        "SELECT tool_calls FROM chat_messages "
        "WHERE tool_calls IS NOT NULL AND jsonb_typeof(tool_calls)='array'"
    )
    await conn.close()

    old_bytes = new_bytes = old_tok = new_tok = 0
    vi_old = vi_new = 0
    vi_n = 0
    n = 0
    # Decompose the two independent effects on total bytes:
    unescape_saved = 0   # ensure_ascii=False alone (the \uXXXX tax)
    nulldrop_saved = 0   # prune_none alone
    worst: list[tuple[int, str, int, int]] = []  # (saved_bytes, tool, old, new)

    for r in rows:
        calls = r["tool_calls"]
        if isinstance(calls, str):
            calls = json.loads(calls)
        for call in calls or []:
            # The model-facing bytes are the tool RESULT (what the funnel serializes).
            result = call.get("result") if isinstance(call, dict) else None
            if result is None:
                continue
            tool = (call.get("tool") or call.get("name") or "?") if isinstance(call, dict) else "?"
            old_s = json.dumps(result)                        # pre-T0 (ensure_ascii=True)
            unesc_s = json.dumps(result, ensure_ascii=False)  # unicode effect only
            new_s = tool_result_content(result)               # T0 funnel (both effects)
            ob = len(old_s.encode("utf-8"))
            ub = len(unesc_s.encode("utf-8"))
            nb = len(new_s.encode("utf-8"))
            ot, nt = estimate_tokens(old_s), estimate_tokens(new_s)
            old_bytes += ob; new_bytes += nb; old_tok += ot; new_tok += nt
            unescape_saved += (ob - ub)
            # null-drop measured on the already-unescaped baseline (isolates it)
            nulldrop_saved += (ub - len(json.dumps(prune_none(result), ensure_ascii=False).encode("utf-8")))
            n += 1
            # VI/CJK slice: the unescaped form carries non-ASCII iff the content does.
            if not _is_ascii(unesc_s):
                vi_old += ob; vi_new += nb; vi_n += 1
            worst.append((ob - nb, str(tool), ob, nb))

    if n == 0:
        print("No tool-result payloads found — nothing to measure.")
        return 1

    def pct(old: int, new: int) -> float:
        return 100.0 * (old - new) / old if old else 0.0

    print(f"T0 / L3 concise-wire — measured over {n} real persisted tool results")
    print("=" * 66)
    print(f"  bytes   : {old_bytes:>10,} → {new_bytes:>10,}   (-{pct(old_bytes, new_bytes):.1f}%)")
    print(f"  tokens  : {old_tok:>10,} → {new_tok:>10,}   (-{pct(old_tok, new_tok):.1f}%)  [est]")
    print(f"    · of which unicode-unescape saved {unescape_saved:,} B, null-drop saved {nulldrop_saved:,} B")
    if vi_n:
        print(f"  VI/CJK slice ({vi_n} results): {vi_old:>9,} → {vi_new:>9,} B   (-{pct(vi_old, vi_new):.1f}%)")
    print()
    worst.sort(reverse=True)
    print("  Top savers (bytes saved · tool · old→new):")
    for saved, tool, ob, nb in worst[:8]:
        print(f"    -{saved:>7,}  {tool:<34}  {ob:>8,} → {nb:>8,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
