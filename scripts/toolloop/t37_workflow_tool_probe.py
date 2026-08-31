"""DQ-T37 — does registry_propose_workflow still accept a step naming a tool that does not exist?

THE BEFORE, established by direct probe at the boundary and quoted on the question: a step with
tool='totally_not_a_real_tool' was ACCEPTED and proposed. Of 10 proposed steps across 5 live
cards, 3 named `chapter_compose`, which is not among the federated tools — three of five
proposals would have created a recipe that cannot run, saved under a name the author trusts.

This runs the SAME probe against the deployed service, so the two numbers are comparable. It also
runs the control that matters more than the rejection: a workflow whose steps are all REAL tools
must still be accepted, or the gate has traded one defect for a worse one.

WRITES: `propose` mints a card and creates nothing until confirmed; the accepted case is left
unconfirmed. No fixture book is needed — a workflow is not book-scoped here.
"""
import json
import sys

from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError

TOOL = "registry_propose_workflow"


def propose(m, slug, tools):
    return m.call(TOOL, {
        "slug": slug,
        "title": "T37 probe",
        "description": "probe: does a step naming a non-existent tool get through?",
        # 🔴 `surfaces` IS OMITTED BECAUSE NO VALUE SATISFIES BOTH SIDES. The published
        # schema declares enum {book, editor, studio}; the runtime validator answers "invalid
        # surface 'book' — must be one of: chat, compose, translate, admin". A caller obeying
        # the schema is always refused, and a caller obeying the runtime is refused by the
        # schema. It is optional, so omitting it is the only way through. Filed separately —
        # this probe is about step tools, and measuring the wrong refusal would prove nothing.
        # `gate` is REQUIRED on a step alongside id and tool — omitting it refused all four
        # cases identically, the second probe defect the all-real control exposed.
        "steps": [{"id": f"s{i + 1}", "tool": t, "gate": "none"}
                  for i, t in enumerate(tools)],
    })


def main() -> int:
    m = MCPDirect()
    rows = []

    for label, tools in [
        ("FABRICATED  totally_not_a_real_tool", ["totally_not_a_real_tool"]),
        ("HALLUCINATED chapter_compose (the founding instance)", ["chapter_compose"]),
        ("MIXED  one real, one fabricated", ["book_list", "chapter_compose"]),
        ("CONTROL  every step a REAL tool", ["book_list", "glossary_search"]),
    ]:
        slug = "t37-probe-" + label.split()[0].lower()
        try:
            out = propose(m, slug, tools)
            rows.append((label, "ACCEPTED", json.dumps(out)[:110]))
        except MCPToolError as exc:
            rows.append((label, "REFUSED", str(exc)[:160]))

    print()
    for label, verdict, detail in rows:
        print(f"  {verdict:9} {label}")
        print(f"            {detail}")
    print()

    bad = [r for r in rows[:3] if r[1] == "ACCEPTED"]
    ctl = rows[3]
    if bad:
        print(f"REFUTED: {len(bad)} step(s) naming a non-existent tool were still accepted.")
        return 1
    if ctl[1] != "ACCEPTED":
        print("REFUTED BY THE CONTROL: a workflow of REAL tools was refused. The gate rejects "
              "valid work, which is worse than the defect it fixes.")
        return 1
    print("Every fabricated name refused; the all-real control still accepted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
