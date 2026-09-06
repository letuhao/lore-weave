"""Does the SECOND pass of a chained /v1/responses turn fail — the shape that dies live?

D-UPSTREAM-ERROR-WITH-NO-MESSAGE's reproducer shows a consistent split: pass 1 succeeds in
~14 s, pass 2 fails in 186-600 ms. Pass 2 is the one that chains on `previous_response_id` and
carries the tool RESULTS back as a delta. buildResponsesBody sends `store: true` and then only
the new items, so the provider is holding the conversation and we are appending to it.

This reproduces exactly that, against the real endpoint, on the STREAMING transport the turns
use. Sixteen hypotheses on this row were tested against something other than the failing
request; this one IS the failing request's shape.

READ-ONLY: two completions against the local model. Writes nothing on this platform.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:1234/v1/responses"
MODEL = "google/gemma-4-26b-a4b-qat"

TOOL = {"type": "function", "name": "composition_arc_list",
        "description": "List a book's arcs (saga/arc/sub-arc spec tree).",
        "parameters": {"type": "object",
                       "properties": {"book_id": {"type": "string"}},
                       "additionalProperties": False}}


def stream(body: dict, label: str) -> tuple[bool, str | None, list[dict]]:
    """Returns (ok, response_id, function_calls). Prints what the provider actually said."""
    req = urllib.request.Request(
        BASE, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    rid, calls, kinds, errframe = None, [], [], None
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
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
                if d.get("response", {}).get("id"):
                    rid = d["response"]["id"]
                if t == "response.output_item.done":
                    it = d.get("item") or {}
                    if it.get("type") == "function_call":
                        calls.append(it)
                if "error" in t or d.get("error"):
                    errframe = json.dumps(d)[:400]
    except urllib.error.HTTPError as e:
        print(f"  {label}: HTTP {e.code}\n      {e.read().decode('utf-8','replace')[:300]}")
        return False, None, []
    except Exception as e:  # noqa: BLE001 — a probe reports what it hit
        print(f"  {label}: {type(e).__name__}: {str(e)[:200]}")
        return False, None, []

    ok = bool(kinds) and errframe is None
    print(f"  {'OK  ' if ok else 'FAIL'} {label}: terminal={kinds[-1] if kinds else 'NONE'} "
          f"id={rid} function_calls={len(calls)}")
    if errframe:
        print(f"      🔴 ERROR FRAME: {errframe}")
    return ok, rid, calls


def main() -> int:
    print("PASS 1 — user message + tools, store=true (the shape that SUCCEEDS live):\n")
    ok1, rid, calls = stream({
        "model": MODEL, "stream": True, "store": True, "tools": [TOOL],
        "instructions": "You are a writing assistant. Use the tools available.",
        "input": [{"role": "user", "type": "message",
                   "content": [{"type": "input_text",
                                "text": "List the arcs of this book, then tell me the first one."}]}],
    }, "pass 1")
    if not ok1:
        print("\nPass 1 failed — the control is broken, nothing below can be read.")
        return 1
    if not rid:
        print("\nNo response id came back, so the chain cannot be built. Stopping rather than "
              "guessing one.")
        return 1

    call_id = calls[0].get("call_id") if calls else "call_probe_1"
    print(f"\nPASS 2 — previous_response_id={rid}, delta = the tool RESULT only "
          f"(call_id={call_id}):\n")
    ok2, _, _ = stream({
        "model": MODEL, "stream": True, "store": True, "tools": [TOOL],
        "instructions": "You are a writing assistant. Use the tools available.",
        "previous_response_id": rid,
        "input": [{"type": "function_call_output", "call_id": call_id,
                   "output": '{"nodes":[{"id":"01a0","kind":"arc","title":"Arc I"}]}'}],
    }, "pass 2 (chained)")

    # 🔴 THE SHAPE THE LIVE REQUEST ACTUALLY SENDS, read off provider-registry's own
    # failure-shape log rather than reconstructed: chained=true AND a delta of TWO items,
    # {function_call: 1, function_call_output: 1}. The pass above sends only the output, which
    # is what a chained turn would need — the provider already holds the call it generated.
    # Repeating it is the one difference between the reconstruction that SUCCEEDS and the
    # request that FAILS.
    print("\nPASS 2b — CHAINED, and the delta REPEATS the function_call the provider holds:\n")
    ok2b, _, _ = stream({
        "model": MODEL, "stream": True, "store": True, "tools": [TOOL],
        "instructions": "You are a writing assistant. Use the tools available.",
        "previous_response_id": rid,
        "input": [{"type": "function_call", "call_id": call_id,
                   "name": "composition_arc_list", "arguments": '{"book_id":"01a0"}'},
                  {"type": "function_call_output", "call_id": call_id,
                   "output": '{"nodes":[{"id":"01a0","kind":"arc","title":"Arc I"}]}'}],
    }, "pass 2b (chained + repeated call)")
    if not ok2b:
        print("      ^ THIS is the live shape, and it is the one that fails.")

    print("\nCONTROL — the same delta WITHOUT the chain, so a failure can be attributed:\n")
    stream({
        "model": MODEL, "stream": True, "store": True, "tools": [TOOL],
        "input": [{"role": "user", "type": "message",
                   "content": [{"type": "input_text", "text": "List the arcs."}]},
                  {"type": "function_call", "call_id": call_id, "name": "composition_arc_list",
                   "arguments": '{"book_id":"01a0"}'},
                  {"type": "function_call_output", "call_id": call_id,
                   "output": '{"nodes":[{"id":"01a0","kind":"arc","title":"Arc I"}]}'}],
    }, "unchained, full input")

    return 0 if ok2 else 2


if __name__ == "__main__":
    sys.exit(main())
