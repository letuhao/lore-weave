"""What selects between WAITING for a model reload and FAILING FAST in 317 ms?

THE GAP THIS CLOSES. D-UPSTREAM-ERROR-WITH-NO-MESSAGE names a mechanism with a measurement
behind it -- the turn asks the provider for TWO models, and the vector search's embedding call
evicts the chat model between pass 1 and pass 2. The row is explicit that this is NOT yet a
cause, and says why in its own words:

    "My probe WAITED 15.5 s for the reload; the live pass 2 DIES in 317-338 ms. Waiting and
     failing-fast are different behaviours and I have not shown what selects between them."

THE EMPTY CELL. Reading the arms already run, they form a 2x2 with one cell never filled:

                          no eviction        eviction injected
    fresh connection      ACCEPTED           ACCEPTED, waited 15.5 s
    reused keep-alive     ACCEPTED           <-- NEVER RUN

That missing cell is what provider-registry actually does: Go's http.Client pools connections,
so pass 2 goes out on a socket that was already open when the model was dropped. urllib opens a
new one every time, which is why every probe so far has been in the top row. If LM Studio resets
pooled sockets when it unloads a model, a reused connection fails INSTANTLY while a fresh one
waits for the reload -- which is exactly the 317 ms / 15.5 s split the row cannot account for.

THE TWO CONTROLS ARE THE POINT. Arms A and B have known results (ACCEPTED, and ACCEPTED after
~15 s). If they do not reproduce, this instrument is wrong and arm C means nothing. A probe whose
controls are not checked is how this row already collected four over-claims.

THE EVICTION MUST BE OBSERVED, NOT ASSUMED. Both models can be resident at once on this host, in
which case the embedding call evicts NOTHING and every arm passes for a reason that has no
bearing on the theory. Model state is polled around the embedding call, and an arm that did not
actually evict is reported INCONCLUSIVE rather than counted as a refutation.

READ-ONLY: completions and an embedding against the local model. Writes nothing on the platform.
"""
from __future__ import annotations

import http.client
import json
import sys
import time
import urllib.request

HOST, PORT = "127.0.0.1", 1234
CHAT = "google/gemma-4-26b-a4b-qat"
EMBED = "text-embedding-bge-m3"

TOOL = {"type": "function", "name": "composition_arc_list",
        "description": "List a book's arcs (saga/arc/sub-arc spec tree).",
        "parameters": {"type": "object",
                       "properties": {"book_id": {"type": "string"}},
                       "additionalProperties": False}}


def model_state() -> dict:
    """id -> state, straight from LM Studio. The eviction witness."""
    try:
        with urllib.request.urlopen(
                f"http://{HOST}:{PORT}/api/v0/models", timeout=20) as r:
            return {m["id"]: m.get("state") for m in json.load(r).get("data", [])}
    except Exception as e:  # noqa: BLE001 - the witness reports its own failure
        print(f"      (model_state unavailable: {type(e).__name__})")
        return {}


def send_stream(conn, body: dict, label: str):
    """One streaming /v1/responses call on a CALLER-OWNED connection, so the caller decides
    whether the socket is reused. Returns (ok, response_id, calls, elapsed_ms, detail)."""
    t0 = time.time()
    try:
        conn.request("POST", "/v1/responses", body=json.dumps(body),
                     headers={"Content-Type": "application/json", "Connection": "keep-alive"})
        r = conn.getresponse()
        if r.status != 200:
            payload = r.read().decode("utf-8", "replace")[:300]
            return False, None, [], (time.time() - t0) * 1000, f"HTTP {r.status}: {payload}"
        rid, calls, kinds, errframe = None, [], [], None
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
            if (d.get("response") or {}).get("id"):
                rid = d["response"]["id"]
            if t == "response.output_item.done":
                it = d.get("item") or {}
                if it.get("type") == "function_call":
                    calls.append(it)
            # Keyed on the EVENT TYPE plus a non-null error: `"error": null` rides along in every
            # response.completed frame and once scored every run in a bisect as a failure.
            if t in ("response.failed", "error") or (d.get("error") is not None):
                errframe = json.dumps(d)[:300]
        ms = (time.time() - t0) * 1000
        return (errframe is None and bool(kinds)), rid, calls, ms, errframe or ""
    except Exception as e:  # noqa: BLE001 - a probe reports what it hit
        return False, None, [], (time.time() - t0) * 1000, f"{type(e).__name__}: {str(e)[:200]}"


def pass1_body():
    return {"model": CHAT, "stream": True, "store": True, "tools": [TOOL],
            "instructions": "You are a writing assistant. Use the tools available.",
            "input": [{"role": "user", "type": "message", "content": [
                {"type": "input_text",
                 "text": "List the arcs for book 11111111-1111-1111-1111-111111111111."}]}]}


def pass2_body(rid, call):
    """Pass 2's real shape: chained on previous_response_id, carrying only the tool RESULT."""
    return {"model": CHAT, "stream": True, "store": True, "tools": [TOOL],
            "previous_response_id": rid,
            "input": [{"type": "function_call_output",
                       "call_id": call.get("call_id") or call.get("id"),
                       "output": json.dumps({"arcs": [{"title": "Arc I"}], "ok": True})}]}


def embed(conn):
    """The eviction trigger: composition_motif_search is a VECTOR search and asks this same
    provider for a different model mid-turn."""
    before = model_state()
    t0 = time.time()
    try:
        conn.request("POST", "/v1/embeddings",
                     body=json.dumps({"model": EMBED, "input": "a motif about rain"}),
                     headers={"Content-Type": "application/json", "Connection": "keep-alive"})
        r = conn.getresponse()
        r.read()
        ok = r.status == 200
    except Exception as e:  # noqa: BLE001
        print(f"      embedding failed: {type(e).__name__}: {str(e)[:160]}")
        ok = False
    after = model_state()
    evicted = before.get(CHAT) == "loaded" and after.get(CHAT) != "loaded"
    tail = "   <- EVICTED" if evicted else ""
    print(f"      embedding {'ok' if ok else 'FAILED'} in {(time.time() - t0) * 1000:.0f} ms; "
          f"chat model {before.get(CHAT)} -> {after.get(CHAT)}{tail}")
    return evicted


def arm(name, *, evict: bool, reuse: bool):
    print(f"\n--- {name} ---")
    c1 = http.client.HTTPConnection(HOST, PORT, timeout=300)
    ok1, rid, calls, ms1, det1 = send_stream(c1, pass1_body(), "pass 1")
    print(f"      pass 1: {'ok' if ok1 else 'FAIL'} in {ms1:.0f} ms, "
          f"function_calls={len(calls)} {det1[:120]}")
    if not ok1 or not rid or not calls:
        c1.close()
        return {"arm": name, "result": "INCONCLUSIVE",
                "why": "pass 1 did not produce a chain to extend"}

    evicted = None
    if evict:
        # The embedding rides the SAME pooled connection Go would use for it.
        evicted = embed(c1)

    conn2 = c1 if reuse else http.client.HTTPConnection(HOST, PORT, timeout=300)
    ok2, _, _, ms2, det2 = send_stream(conn2, pass2_body(rid, calls[0]), "pass 2")
    print(f"      pass 2: {'ok' if ok2 else 'FAIL'} in {ms2:.0f} ms  {det2[:200]}")
    c1.close()
    if conn2 is not c1:
        conn2.close()

    if evict and evicted is False:
        return {"arm": name, "result": "INCONCLUSIVE", "ms": round(ms2),
                "why": "the embedding evicted nothing (both models resident) — this arm never "
                       "created the condition it exists to test"}
    return {"arm": name, "result": "pass2_ok" if ok2 else "pass2_FAILED",
            "ms": round(ms2), "evicted": evicted, "detail": det2[:200]}


def main() -> int:
    print("THE 2x2, with the two known-result arms run FIRST as controls.\n")
    print(f"model state at start: {json.dumps(model_state())[:300]}")
    out = [
        arm("A  control: no eviction, REUSED keep-alive  (known: ACCEPTED)",
            evict=False, reuse=True),
        arm("B  control: eviction, FRESH connection      (known: ACCEPTED, ~15 s)",
            evict=True, reuse=False),
        arm("C  THE EMPTY CELL: eviction, REUSED keep-alive connection",
            evict=True, reuse=True),
    ]
    print("\n" + "=" * 78)
    for r in out:
        print(f"  {r['arm'][:52]:54} {r['result']:14} {r.get('ms', '?')} ms")
        if r.get("why"):
            print(f"      {r['why']}")
    print("=" * 78)

    a, b, c = out
    if a["result"] != "pass2_ok":
        print("\nINSTRUMENT WRONG, not a finding: control A was expected to be ACCEPTED and was "
              "not. Nothing in arm C can be read until A reproduces.")
        return 1
    if c["result"] == "pass2_FAILED" and b["result"] == "pass2_ok":
        print(f"\nTHE SPLIT REPRODUCES: the only difference between B (ok) and C (failed) is "
              f"whether pass 2 reused a socket held open across the eviction. C died in "
              f"{c.get('ms')} ms; live dies in 317-338 ms.")
    elif "INCONCLUSIVE" in (b["result"], c["result"]):
        print("\nINCONCLUSIVE: the eviction never happened, so the empty cell is still empty. "
              "Both models fit in memory on this host right now, which is itself worth "
              "recording — it means the row's mechanism cannot fire in the current "
              "configuration.")
    else:
        print("\nREFUTED, and this is the useful outcome: a reused connection across an eviction "
              "does NOT fail fast. Connection reuse is not what selects waiting from dying, and "
              "the row must say so rather than carry it as the leading idea.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
