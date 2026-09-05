"""SHIP audit for registry_list_workflows — read-only, no fixture, nothing written.

The `surface` filter is the whole reason this tool is not a duplicate of the always-on
consumer-local workflow_list (which declares properties:{} and cannot narrow), so it is
exercised here as a first-class case rather than as a detail.
"""
import json, sys
sys.path.insert(0, ".")
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError

m = MCPDirect()


def call(**args):
    try:
        r = m.call("registry_list_workflows", args)
        items = r.get("workflows") or r.get("items") or []
        return {"verdict": "SUCCEEDED", "count": r.get("count", len(items)),
                "slugs": sorted(x.get("slug") for x in items)}
    except MCPToolError as e:
        return {"verdict": "refused", "detail": str(e)[:240]}


out = {"surface_filter": {}}
for s in (None, "book", "editor", "studio"):
    out["surface_filter"]["(omitted)" if s is None else s] = call(**({} if s is None else {"surface": s}))

out["invalid_surface"] = call(surface="mobile")
out["invalid_surface"]["asked"] = "a surface outside the enum — must be refused, not ignored"

out["empty_surface"] = call(surface="")
out["empty_surface"]["asked"] = (
    "an EMPTY surface string — the description says 'do not send an empty string', so silently "
    "treating it as 'all' would return 12 and read as success")

sets = {k: v.get("slugs") for k, v in out["surface_filter"].items() if v.get("verdict") == "SUCCEEDED"}
out["_distinct_sets"] = {k: len(v or []) for k, v in sets.items()}
out["_studio_is_a_strict_subset_of_book"] = (
    set(sets.get("studio") or []) < set(sets.get("book") or []) if sets.get("studio") else None)
out["_never_empty"] = all(len(v or []) > 0 for v in sets.values())
print(json.dumps(out, indent=2, ensure_ascii=False))
