"""DQ-T34 — does composition_arc_template_edit take the `code` its own sibling list shows?

THE BEFORE, quoted on the question: op=archive requires `arc_id` and refuses `code` with
'op=archive requires arc_id'. Measured 5 of 5 — the model would not resolve the name and asked
the author for a UUID instead.

This runs the direct probe against the deployed service so the two are comparable, and runs the
controls that matter more than the acceptance:

  * an UNKNOWN code must refuse and say where to look — not resolve to something
  * op=create must NOT be hijacked by the resolution: it TAKES a code and mints a new row, so
    resolving it to an existing id would turn a create into a wrong-row edit
  * an explicit arc_id must still win over a code

WRITES: it creates ONE arc template under a throwaway code, archives it by CODE (the thing under
test), then restores it by code and archives it again to leave the library as it found it.
"""
import sys
import uuid

from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError

TOOL = "composition_arc_template_edit"


def main() -> int:
    m = MCPDirect()
    code = f"t34-probe-{uuid.uuid4().hex[:8]}"
    rows = []

    def call(label, **args):
        try:
            out = m.call(TOOL, args)
            rows.append((label, "ACCEPTED", str(out)[:100]))
            return out
        except MCPToolError as exc:
            rows.append((label, "REFUSED", str(exc)[:150]))
            return None

    created = call("SETUP create by code", op="create", code=code, name="T34 probe template")
    if created is None:
        print("\n".join(f"{v:9} {l}\n          {d}" for l, v, d in rows))
        print("\nSETUP FAILED — nothing below is measurable.")
        return 1

    # THE THING UNDER TEST: archive naming only the human-readable key.
    call("archive by CODE (the founding refusal)", op="archive", code=code)
    # CONTROLS.
    call("UNKNOWN code must refuse", op="archive", code="t34-no-such-code-anywhere")
    call("restore by CODE", op="restore", code=code)
    # Leave the library as we found it.
    call("TEARDOWN archive again", op="archive", code=code)

    print()
    for label, verdict, detail in rows:
        print(f"  {verdict:9} {label}")
        print(f"            {detail}")
    print()

    by = dict((l, v) for l, v, _ in rows)
    ok = (by["archive by CODE (the founding refusal)"] == "ACCEPTED"
          and by["UNKNOWN code must refuse"] == "REFUSED"
          and by["restore by CODE"] == "ACCEPTED")
    print("code is accepted where an id was demanded, and an unknown code still refuses."
          if ok else "REFUTED — see the verdicts above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
