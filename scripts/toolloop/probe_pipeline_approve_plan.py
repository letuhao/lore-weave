"""DQ-T64 — does op=approve_plan work when it is actually called?

The corpus says the pipeline tool produces a cast in 0 of 80 turns, and that op=approve_plan was
called in 0 of 70 sessions. Its own result tells the model to show a worklist and wait. So the
open question is which of these is true:

    RIGHT BUT UNREACHABLE   approve_plan works; the model simply never gets there
    BROKEN                  approve_plan does not deliver a cast either

This drives the protocol directly through the harness's own authenticated seed steps — no model
in the loop, so a failure cannot be blamed on selection — and then READS THE STORE.

Throwaway fixture, torn down in a finally.
"""
import json
import sys

sys.path.insert(0, "scripts/toolloop")

import provision  # noqa: E402

STORY = ("Aldric Vane climbs the black stair of Hollow Keep as the storm breaks; "
         "Mira Solene waits at the waterline where the Obsidian Trench is walkable "
         "only at low tide.")
MODEL_REF = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"

SEED = [
    {"rest": {"domain": "glossary", "method": "POST",
              "path": "/v1/glossary/books/{book_id}/adopt",
              "json": {"genres": ["universal"], "kinds": ["character", "place"]}}},
    {"tool": "composition_build_cast_and_graph", "args": {
        "op": "start", "book_id": "{book_id}", "source_text": STORY,
        "model_source": "user_model", "model_ref": MODEL_REF}},
]

fx = provision.Throwaway("t64approve")
try:
    fx.build(seed=SEED, chapter=True)
    print(f"fixture book: {fx.book_id}")
    start = fx.seeded[-1].get("result") or {}
    print("op=start ->", json.dumps({k: str(v)[:70] for k, v in start.items()})[:400])
    run_id = start.get("run_id")
    if not run_id:
        print("NO run_id — cannot drive approve_plan")
        raise SystemExit(2)

    # The step the model never reaches.
    r = fx.mcp.call("composition_build_cast_and_graph",
                    {"op": "approve_plan", "book_id": fx.book_id, "run_id": run_id})
    print("\nop=approve_plan ->", json.dumps({k: str(v)[:90] for k, v in (r or {}).items()})[:600])

    # 🔴 approve_plan returns status=building and says "poll op=status" — the build is ASYNC.
    # Reading the store immediately proves nothing; the first version of this probe did exactly
    # that and would have reported "approve_plan does not deliver" about a build that had just
    # started. Poll to a terminal status first.
    import time
    import subprocess
    for i in range(40):
        st = fx.mcp.call("composition_build_cast_and_graph",
                         {"op": "status", "book_id": fx.book_id, "run_id": run_id}) or {}
        status = str(st.get("status") or "")
        if i % 5 == 0 or status not in ("building", "running", "pending"):
            print(f"   poll {i:2d}: status={status!r} {json.dumps({k: str(v)[:50] for k, v in st.items() if k != 'status'})[:150]}")
        if status and status not in ("building", "running", "pending"):
            break
        time.sleep(6)
    q = (f"SELECT count(*) FROM glossary_entities WHERE book_id='{fx.book_id}';")
    out = subprocess.run(["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave",
                          "-d", "loreweave_glossary", "-tAf", "-"],
                         input=q, capture_output=True, text=True).stdout.strip()
    print(f"\nglossary_entities on the fixture AFTER approve_plan: {out}")

    # THE GRAPH HALF. The cast is only half of what the description promises ("Build the
    # KNOWLEDGE GRAPH and the CAST ... in ONE call"). The schema declares two more ops for the
    # other half, so the full protocol is start -> approve_plan -> project_kg -> approve_edges.
    # Nothing in the corpus has ever exercised past the second.
    import time as _t
    for op in ("project_kg", "approve_edges"):
        try:
            rr = fx.mcp.call("composition_build_cast_and_graph",
                             {"op": op, "book_id": fx.book_id, "run_id": run_id}) or {}
            print(f"op={op} -> " + json.dumps({k: str(v)[:80] for k, v in rr.items()})[:340])
        except Exception as e:  # noqa: BLE001 - a refusal IS the finding here
            print(f"op={op} REFUSED -> {str(e)[:220]}")
        _t.sleep(3)
    for _i in range(30):
        st = fx.mcp.call("composition_build_cast_and_graph",
                         {"op": "status", "book_id": fx.book_id, "run_id": run_id}) or {}
        if str(st.get("status") or "") not in ("building", "running", "pending"):
            print("final status:", st.get("status"), "| edges:", str(st.get("edges"))[:100])
            break
        _t.sleep(6)
finally:
    try:
        fx.teardown()
        print("fixture torn down")
    except Exception as e:  # noqa: BLE001
        print("teardown failed:", e)
