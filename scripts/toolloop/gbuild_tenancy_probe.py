"""TENANCY audit for composition_build_cast_and_graph — one seeded row, torn down.

Every other SHIP case for this tool is exercised by `gbuild_ship_probe.py`. Tenancy was not, and
it cannot be: a run the CALLER owns is the only kind the harness can create through the tool, so
the question "does a stranger's run leak?" has nothing to ask about until a stranger's run exists.

🔴 BOTH ARMS ARE REQUIRED. "A stranger's run is not found" passes just as well when the tool
cannot find ANY run — a different bug wearing a green tick. So the caller's own run is created
through the tool in the same probe and must come back. Absent-and-present together are what make
the result mean tenancy.

The seeded row is a direct INSERT because the tool has no way to mint a run for somebody else,
which is the point. It is deleted in `finally` and the table re-counted.
"""
import json
import os
import subprocess
import sys
import uuid

sys.path.insert(0, ".")
import httpx  # noqa: E402

from scripts.eval.tool_liveness import config as cfg  # noqa: E402
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError  # noqa: E402
from scripts.toolloop.provision import Throwaway, _tle_auth  # noqa: E402

m = MCPDirect()
TOOL = "composition_build_cast_and_graph"
REAL_MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"
STRANGER = "01900000-0000-7000-8000-00000000dead"  # owned by nobody — a fixture id, never a login
DSN = ("postgres://loreweave:loreweave_dev@localhost:5555/"
       "loreweave_composition?sslmode=disable")
STORY = ("Aldric Vane climbs the black stair of Hollow Keep as the storm breaks; Mira Solene "
         "waits at the waterline where the Obsidian Trench is walkable only at low tide.")


def sql(statement: str) -> str:
    r = subprocess.run(["psql", DSN, "-At", "-c", statement], capture_output=True, text=True,
                       env={**os.environ, "PGPASSWORD": "loreweave_dev"})
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:400])
    return r.stdout.strip()


def call(**args):
    try:
        return {"verdict": "SUCCEEDED", "detail": json.dumps(m.call(TOOL, args),
                                                             ensure_ascii=False)[:200]}
    except MCPToolError as e:
        return {"verdict": "refused", "detail": str(e)[:240]}


fx = fx2 = None
seeded = str(uuid.uuid4())
out: dict = {}
try:
    fx = Throwaway("gb-tenancy", mcp=m).build()
    httpx.post(f"{cfg.DOMAIN_BASE['glossary']}/v1/glossary/books/{fx.book_id}/adopt",
               headers=_tle_auth().bearer_header(),
               json={"genres": ["universal"], "kinds": ["character"]}, timeout=90)

    # ARM 1 — the caller's OWN run, created through the tool, must be readable.
    started = m.call(TOOL, {"op": "start", "book_id": fx.book_id, "source_text": STORY,
                            "model_ref": REAL_MODEL, "model_source": "user_model"})
    mine = str(started.get("run_id"))
    out["own_run"] = call(op="status", book_id=fx.book_id, run_id=mine)
    out["own_run"]["asked"] = "op=status on a run this caller started — must be READABLE"

    # ARM 2 — a run owned by somebody else must NOT be.
    # A SECOND book, because `uq_glossary_build_active_book` allows one active run per book and
    # arm 1 already holds the first one. Caught by the constraint on the first attempt.
    fx2 = Throwaway("gb-tenancy-b", mcp=m).build()
    sql("insert into glossary_build_runs (run_id, owner_user_id, book_id, params, status) "
        f"values ('{seeded}', '{STRANGER}', '{fx2.book_id}', '{{}}'::jsonb, 'plan_ready');")
    out["stranger_run"] = call(op="status", book_id=fx2.book_id, run_id=seeded)
    out["stranger_run"]["asked"] = (
        "op=status on a run owned by another user, seeded directly because the tool has no way "
        "to mint one for somebody else — must be REFUSED")

    out["PASSES"] = (out["own_run"]["verdict"] == "SUCCEEDED"
                     and out["stranger_run"]["verdict"] == "refused")
finally:
    try:
        sql(f"delete from glossary_build_runs where run_id = '{seeded}';")
        left = sql(f"select count(*) from glossary_build_runs where run_id = '{seeded}';")
        out["torn_down"] = {"seeded_row_remaining": left}
    except Exception as e:
        out["torn_down"] = f"FAILED: {str(e)[:200]}"
    for _f in (fx, fx2):
        if _f is not None:
            _f.teardown()

print(json.dumps(out, indent=2, ensure_ascii=False))
