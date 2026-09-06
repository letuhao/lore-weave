"""TENANCY audit for registry_list_workflows — two seeded rows, both torn down.

The tool is ScopeUser and describes itself as returning "System defaults + their own", but the
registry holds ZERO tier='user' rows, so there is nothing for a tenancy claim to bite on. This
seeds the missing population for the length of one probe.

🔴 BOTH ARMS ARE REQUIRED. A negative-only check ("another user's workflow is not returned")
passes just as well when the tool ignores user-tier rows ALTOGETHER, which would be a different
bug wearing a green tick. So a row owned by the CALLER is seeded at the same time and must come
back. Absent-and-present together are what make the result mean tenancy.

Teardown runs in `finally` and is verified by re-counting, so a failure mid-probe still leaves
the registry as it was found.
"""
import json
import os
import subprocess
import sys
import uuid

sys.path.insert(0, ".")
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError

CALLER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"  # the harness account (claude-test@loreweave.dev)
STRANGER = "01900000-0000-7000-8000-00000000dead"  # owned by nobody — a fixture id, never an account
MINE = "zzz-toolloop-tenancy-mine"
THEIRS = "zzz-toolloop-tenancy-theirs"
DSN = os.environ.get(
    "REGISTRY_DSN",
    "postgres://loreweave:loreweave_dev@localhost:5555/loreweave_agent_registry?sslmode=disable")


def sql(statement: str) -> str:
    r = subprocess.run(["psql", DSN, "-At", "-c", statement],
                       capture_output=True, text=True,
                       env={**os.environ, "PGPASSWORD": "loreweave_dev"})
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:400])
    return r.stdout.strip()


def user_tier_rows() -> str:
    return sql("select coalesce(string_agg(slug,','),'') from workflows where tier='user';")


out: dict = {}
# ── SELECT BEFORE ANY DML ────────────────────────────────────────────────────────
before = user_tier_rows()
out["before"] = {"tier_user_slugs": before or "(none)",
                 "asked": "the registry must hold no user-tier rows, so teardown is unambiguous"}
if before:
    print(json.dumps({"verdict": "ABORTED — pre-existing tier='user' rows, refusing to seed",
                      "rows": before}, indent=2))
    raise SystemExit(1)

try:
    for slug, owner in ((MINE, CALLER), (THEIRS, STRANGER)):
        sql(
            "insert into workflows (workflow_id, tier, owner_user_id, slug, title, description, "
            "surfaces, source, status) values "
            f"('{uuid.uuid4()}', 'user', '{owner}', '{slug}', 'toolloop tenancy fixture', "
            "'seeded by regwf_tenancy_probe, deleted in the same run', "
            "'{book,editor,studio}', 'user', 'published');")
    out["seeded"] = {MINE: f"owner={CALLER} (the caller)", THEIRS: f"owner={STRANGER} (a stranger)"}

    m = MCPDirect()
    try:
        r = m.call("registry_list_workflows", {})
        slugs = sorted(x.get("slug") for x in (r.get("workflows") or r.get("items") or []))
        verdict = "SUCCEEDED"
    except MCPToolError as e:
        slugs, verdict = [], f"refused: {str(e)[:200]}"

    out["tenancy"] = {
        "verdict": verdict,
        "count": len(slugs),
        "caller_own_row_returned": MINE in slugs,
        "stranger_row_returned": THEIRS in slugs,
        "PASSES": (MINE in slugs) and (THEIRS not in slugs),
        "asked": "the caller's own user-tier workflow must come back AND a stranger's must not; "
                 "either half alone is satisfiable by a tool that is simply wrong in one direction",
    }
    out["tenancy"]["slugs"] = slugs
finally:
    sql(f"delete from workflows where slug in ('{MINE}','{THEIRS}');")
    after = user_tier_rows()
    out["torn_down"] = {"tier_user_slugs_after": after or "(none)", "clean": after == ""}

print(json.dumps(out, indent=2, ensure_ascii=False))
