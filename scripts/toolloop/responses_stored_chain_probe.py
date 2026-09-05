"""Does a chained pass 2 fail once pass 1 has filled the STORED chain?

D-UPSTREAM-ERROR-WITH-NO-MESSAGE's live shape: `store: true`, `previous_response_id` set, and a
pass 1 that spent ~14 s reasoning under a 16,384-token output ceiling. Every probe so far had a
pass 1 that answered in a sentence, so the chain pass 2 extends was nearly empty — the one
structural property of the failing request that no reconstruction has reproduced.

This makes pass 1 do real work first, then chains. Prints the token usage of each pass so the
answer is a number rather than an impression.

READ-ONLY: completions against the local model. Writes nothing on this platform.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:1234/v1/responses"
MODEL = "google/gemma-4-26b-a4b-qat"
MAX_OUT = 16384  # the live value, from the failure-shape log

TOOL = {"type": "function", "name": "composition_arc_list",
        "description": "List a book's arcs (saga/arc/sub-arc spec tree).",
        "parameters": {"type": "object", "properties": {"book_id": {"type": "string"}},
                       "additionalProperties": False}}


def stream(body: dict, label: str) -> tuple[bool, str | None, dict]:
    req = urllib.request.Request(
        BASE, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    kinds: list[str] = []
    rid, usage, err = None, {}, None
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            for raw in r:
                s = raw.decode("utf-8", "replace").strip()
                if not s.startswith("data:"):
                    continue
                p = s[5:].strip()
                if p == "[DONE]":
                    break
                try:
                    d = json.loads(p)
                except Exception:
                    continue
                t = d.get("type", "?")
                if t not in kinds:
                    kinds.append(t)
                resp = d.get("response") or {}
                if resp.get("id"):
                    rid = resp["id"]
                if resp.get("usage"):
                    usage = resp["usage"]
                if "error" in t or d.get("error"):
                    err = json.dumps(d)[:400]
    except urllib.error.HTTPError as e:
        print(f"  FAIL {label}: HTTP {e.code} {e.read().decode('utf-8','replace')[:220]}")
        return False, None, {}
    except Exception as e:  # noqa: BLE001 — a probe reports what it hit
        print(f"  FAIL {label}: {type(e).__name__}: {str(e)[:180]}")
        return False, None, {}

    ok = bool(kinds) and err is None
    print(f"  {'OK  ' if ok else 'FAIL'} {label}: terminal={kinds[-1] if kinds else 'NONE'} "
          f"in={usage.get('input_tokens')} out={usage.get('output_tokens')}")
    if err:
        print(f"      🔴 ERROR FRAME: {err}")
    return ok, rid, usage


def main() -> int:
    # A prompt that MAKES the model work, so the stored chain is real. The live pass 1 spends
    # ~14 s; a one-sentence answer builds nothing for pass 2 to extend.
    long_task = ("Think step by step and write a detailed 12-part outline for an epic fantasy "
                 "novel about a cartographer who maps a city that rearranges itself. Give each "
                 "part a title and three sentences of summary.")

    print("PASS 1 — real work, store=true, the live output ceiling:\n")
    ok1, rid, u1 = stream({
        "model": MODEL, "stream": True, "store": True, "tools": [TOOL],
        "max_output_tokens": MAX_OUT, "reasoning": {"effort": "none"},
        "instructions": "You are LoreWeave's writing assistant.",
        "input": [{"role": "user", "type": "message",
                   "content": [{"type": "input_text", "text": long_task}]}],
    }, "pass 1 (long)")
    if not ok1 or not rid:
        print("\nPass 1 did not complete, so nothing below can be attributed. Stopping.")
        return 1

    print(f"\nPASS 2 — chained onto that filled chain, delta = a tool call + its result:\n")
    ok2, _, u2 = stream({
        "model": MODEL, "stream": True, "store": True, "tools": [TOOL],
        "max_output_tokens": MAX_OUT, "reasoning": {"effort": "none"},
        "instructions": "You are LoreWeave's writing assistant.",
        "previous_response_id": rid,
        "input": [{"type": "function_call", "call_id": "call_p1",
                   "name": "composition_arc_list", "arguments": '{"book_id":"01a0"}'},
                  {"type": "function_call_output", "call_id": "call_p1",
                   "output": '{"nodes":[]}'}],
    }, "pass 2 (chained onto a filled chain)")

    print(f"\n  pass 1 output tokens: {u1.get('output_tokens')}  "
          f"pass 2 input tokens: {u2.get('input_tokens')}")
    if not ok2:
        print("  ^ REPRODUCED: the chain's SIZE, not the request's shape, is what breaks pass 2.")
    else:
        print("  ^ Not reproduced. The filled chain is refuted too; the cause is in the CONTENT.")
    return 0 if ok2 else 2


if __name__ == "__main__":
    sys.exit(main())
