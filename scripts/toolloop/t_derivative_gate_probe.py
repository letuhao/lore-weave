"""Do the three ops that inherited a phantom gate now refuse a CANONICAL Work by name?

THE BEFORE: `_require_derivative` was documented as gating the not-a-derivative case and never
read `source_work_id`. composition_entity_override_update / _delete / _restore trusted the name
and never checked, so a canonical project_id fell through to whatever the repo said — "not found
or not accessible", which tells the author nothing about their own book.

This calls each op with the book's CANONICAL project_id (the ambient one a chat turn supplies)
and asserts the refusal now NAMES the kind of Work and how to find the right one.

READ-ONLY in effect: every call is refused before it reaches a write.
"""
import sys
import uuid

from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError
from scripts.toolloop.provision import Throwaway, _tle_auth  # noqa: F401

OPS = [
    ("composition_entity_override_edit", {"op": "list", "include_archived": True}),
    ("composition_entity_override_edit", {"op": "update", "override_id": None,
                                          "overridden_fields": {"occupation": "x"}}),
    ("composition_entity_override_edit", {"op": "delete", "override_id": None}),
    ("composition_entity_override_edit", {"op": "restore", "override_id": None}),
]


def main() -> int:
    m = MCPDirect()
    fx = Throwaway("t-derivgate", mcp=m).build()
    try:
        rows = []
        for tool, base in OPS:
            args = {k: v for k, v in base.items() if v is not None}
            args["project_id"] = fx.project_id          # the CANONICAL Work
            if base.get("override_id", "absent") is None:
                args["override_id"] = str(uuid.uuid4())  # shape-valid, never reached
            try:
                out = m.call(tool, args)
                rows.append((base["op"], "ACCEPTED", str(out)[:110]))
            except MCPToolError as exc:
                # 🔴 KEEP THE FULL MESSAGE AND TRUNCATE ONLY FOR DISPLAY. The first version
                # stored str(exc)[:150] and then searched THAT for the tool name — reporting
                # "named the lookup tool: 0/4" about a message that names it at character 300.
                # The instrument was measuring its own truncation.
                rows.append((base["op"], "REFUSED", str(exc)))

        print()
        for op, verdict, detail in rows:
            print(f"  {verdict:9} op={op}")
            print(f"            {detail[:150]}")
        print()

        named = [op for op, _, d in rows if "NOT_A_DERIVATIVE" in d]
        lists = [op for op, _, d in rows if "composition_list_derivatives" in d]
        accepted = [op for op, v, _ in rows if v == "ACCEPTED"]
        ok = not accepted and len(named) == len(rows) and len(lists) == len(rows)
        print(f"refused: {len(rows) - len(accepted)}/{len(rows)}   "
              f"named NOT_A_DERIVATIVE: {len(named)}/{len(rows)}   "
              f"named the lookup tool: {len(lists)}/{len(rows)}")
        if accepted:
            print(f"REFUTED: {accepted} accepted a CANONICAL project_id.")
        return 0 if ok else 1
    finally:
        fx.teardown()


if __name__ == "__main__":
    sys.exit(main())
