#!/usr/bin/env python3
"""The SHIP boundary cases, driven directly at the tool — absent id, another owner's id, no input.

    python scripts/toolloop/ship_probe.py --tools world_map_update_region,jobs_cancel
    python scripts/toolloop/ship_probe.py --batch docs/eval/toolloop/2026-08-14/c1-rerun.json

🔴 WHY DIRECTLY AND NOT THROUGH THE MODEL. The LIVE bar asks whether the MODEL can reach a tool,
and it is measured over the chat edge for exactly that reason. The SHIP bar asks something else —
what the tool DOES at its boundary — and a stochastic consumer is the wrong instrument for it: you
cannot ask a model to reliably pass a foreign id, and if it did you would be measuring its
obedience rather than the handler's refusal. So these go straight at the MCP surface, and the
ledger records them as "EXERCISED by direct probe" so the two are never confused.

SCHEMA-DRIVEN, NOT GUESSED. Every argument name comes from the tool's own `inputSchema` in the
cached catalogue. Five "obvious" argument names were wrong in one session of this loop, and each
wrong guess costs a call whose refusal then means nothing — "missing required argument" is not the
refusal you were testing for.

WHAT EACH CASE MEANS, and why the interesting answer is often "they are identical":
  absent   a syntactically valid id that does not exist   -> must refuse
  tenancy  the SAME shape, but an id belonging to no one  -> must refuse, ideally IDENTICALLY,
           because a refusal that distinguishes "not yours" from "no such thing" is an existence
           oracle: it tells a stranger which ids are real.
  empty    the required field present but empty           -> must refuse and NAME what is missing

SAFETY: every id used is nonexistent by construction (a fresh UUID) or belongs to the run's own
throwaway. Nothing here can write: a refusal is the expected outcome, and a call that SUCCEEDS is
itself the finding and is reported as one.

🔴 IT CANNOT REACH AN OP-DISPATCH TOOL'S ID, AND IT REPORTS "refused" ANYWAY. The cases are built
from the tool's REQUIRED arguments, and a flat-superset tool declares only `op` as required — every
id it acts on is optional in the schema. Measured 2026-08-22 on composition_arc_template_edit and
composition_motif_link_edit: all three cases returned the SAME op-dispatch refusal ("op=create
requires code and name"), so the run read as a clean 3-for-3 while never touching arc_id or the
motif ids at all. A green boundary check that never reached the boundary is worse than no check,
because it is recorded as evidence.

Until this takes an explicit argument override, an op-dispatch tool must be probed by hand with a
concrete op plus the id under test (see docs/eval/toolloop/2026-08-14/c2-ship-probe-opdispatch.txt),
and its ledger row must say WHICH op was exercised. 15 catalogue tools declare `op` as their only
required argument (measured, 2026-08-22).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError  # noqa: E402

CACHE = ROOT / "contracts" / "tool-catalog-cache.json"

# An id that cannot exist. Fixed rather than random so a probe is reproducible and so the same
# string is recognisable in a server log later.
ABSENT = "00000000-0000-4000-8000-0000000000ff"
FOREIGN = "11111111-1111-4111-8111-1111111111ff"


def schema_of(tool: str) -> dict:
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    return (cache.get(tool) or {}).get("inputSchema") or {}


def _fill(schema: dict, value: str, *, blank: bool = False, reach_the_id: bool = False) -> dict:
    """Build the smallest argument object the validator will accept, from the schema itself.

    🔴 `reach_the_id` EXISTS BECAUSE THE FIRST VERSION MEASURED THE WRONG THING. Probing
    `world_map_update_region` with only its required `region_id`, the answer came back
    "provide at least one of polygon, name, entity_id or clear_entity to update" — a
    NOTHING-TO-UPDATE refusal that fires BEFORE the id is ever looked up. Both the absent and the
    tenancy probe returned it, they matched, and "identical wording, no existence oracle" would
    have been recorded for a check that never reached the id.

    Same ordering as `lore_enrichment_auto_enrich` in batch 40, where nested args validated before
    the project lookup. It is not a defect — a caller fixing the id would still have to supply a
    field — but a probe that stops there is measuring argument validation and calling it tenancy.

    So an edit-shaped tool gets ONE optional non-id field filled, which carries the call past that
    guard and into the lookup. Harmless: the id still does not exist, so nothing can be written.
    """
    props = schema.get("properties") or {}
    args: dict = {}
    for name in schema.get("required") or []:
        p = props.get(name) or {}
        t = p.get("type")
        if isinstance(t, list):                      # a union LIST is legal JSON Schema
            t = next((x for x in t if x != "null"), "string")
        enum = p.get("enum")
        if enum:
            args[name] = enum[0]
        elif t == "boolean":
            args[name] = False
        elif t in ("integer", "number"):
            args[name] = 1
        elif t == "array":
            args[name] = []
        elif t == "object":
            args[name] = {}
        else:
            looks_like_id = name.endswith("_id") or name == "id"
            args[name] = ("" if blank else (value if looks_like_id else f"probe-{value[:8]}"))
    # 🔴 A TOOL WITH NO *REQUIRED* ID STILL HAS AN ID UNDER TEST, and the first version missed it.
    # `memory_timeline` declares nothing required, so the probe sent {"detail": "summary"}, the
    # tool correctly answered for the session's CURRENT project, and all three cases came back
    # SUCCEEDED. Read at face value that is "the tenancy boundary does not hold" — a serious
    # accusation about a tool that was behaving exactly as declared. The probe had simply never
    # sent an id. So an optional scoping id is filled explicitly when one exists: that is the
    # argument whose absence or foreignness is the whole question.
    if reach_the_id and not blank:
        for name, p in props.items():
            if name not in args and (name.endswith("_id") or name == "id"):
                args[name] = value
                break

    if reach_the_id and not blank:
        # One optional, non-id field — enough to clear a "nothing to change" guard.
        #
        # 🔴 PREFERENCE ORDER MATTERS, and the first version got it wrong. Iterating the schema's
        # properties in their own order picked `clear_entity` for world_map_update_region and set
        # it to FALSE — which satisfies the JSON schema and provides nothing, so the guard fired
        # anyway and the probe still never reached the id. A boolean set to false is not an edit.
        # Strings and enums carry a real value; booleans are a last resort and are set TRUE.
        def _t(p):
            t = p.get("type")
            return next((x for x in t if x != "null"), None) if isinstance(t, list) else t

        cands = [(n, p) for n, p in props.items()
                 if n not in args and not n.endswith("_id") and n != "id"]
        pick = (next(((n, p) for n, p in cands if _t(p) == "string" and not p.get("enum")), None)
                or next(((n, p) for n, p in cands if p.get("enum")), None)
                or next(((n, p) for n, p in cands if _t(p) == "boolean"), None))
        if pick:
            n, p = pick
            args[n] = (p["enum"][0] if p.get("enum")
                       else (True if _t(p) == "boolean" else f"probe-{value[:8]}"))
    return args


def probe(mcp: MCPDirect, tool: str, args: dict) -> tuple[str, str]:
    try:
        out = mcp.call(tool, args)
        return "SUCCEEDED", json.dumps(out, ensure_ascii=False)[:220]
    except MCPToolError as e:
        return "refused", str(e)[:220]
    except Exception as e:                            # noqa: BLE001 — transport, not a verdict
        return "ERROR", f"{type(e).__name__}: {e}"[:220]


def run(tools: list[str]) -> dict:
    mcp = MCPDirect()
    out = {}
    for tool in tools:
        sch = schema_of(tool)
        if not sch:
            out[tool] = {"_": "no schema in the cached catalogue"}
            continue
        req = sch.get("required") or []
        res = {"required": req}
        res["absent"] = probe(mcp, tool, _fill(sch, ABSENT, reach_the_id=True))
        res["tenancy"] = probe(mcp, tool, _fill(sch, FOREIGN, reach_the_id=True))
        res["empty"] = probe(mcp, tool, _fill(sch, ABSENT, blank=True))
        # The comparison IS the finding: identical wording means no existence oracle.
        res["indistinguishable"] = res["absent"][1] == res["tenancy"][1]
        out[tool] = res
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", help="comma-separated tool names")
    ap.add_argument("--batch", help="probe every tool in a gate evidence file")
    ap.add_argument("--out", help="write the results as JSON")
    a = ap.parse_args()

    if a.batch:
        d = json.loads(pathlib.Path(a.batch).read_text(encoding="utf-8"))
        tools = [e["tool"] for e in d.get("tools", []) if e.get("tool")]
    elif a.tools:
        tools = [t.strip() for t in a.tools.split(",") if t.strip()]
    else:
        ap.print_help()
        return 2

    res = run(tools)
    for tool, r in res.items():
        if "_" in r:
            print(f"{tool}: {r['_']}")
            continue
        print(f"\n{tool}   required={r['required']}")
        for case in ("absent", "tenancy", "empty"):
            verdict, msg = r[case]
            mark = "  🔴 SUCCEEDED — a boundary that does not hold" if verdict == "SUCCEEDED" else ""
            print(f"  {case:8} {verdict:10} {msg}{mark}")
        print(f"  {'oracle':8} {'identical' if r['indistinguishable'] else 'DIFFERENT WORDING — '
                                'the refusal distinguishes not-yours from no-such-thing'}")
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
