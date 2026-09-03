"""Does DQ-T58's shipped refusal actually FIRE when a motif is bound to an ARC?

THE GAP THIS CLOSES. DQ-T58's ruling was built on 2026-08-30 -- composition_motif_bind_edit now
refuses a non-chapter node with a message that NAMES CHAPTERS and says the arc semantic is
deliberately not guessed. It has never run. The row records why in its own words: "it never ran
in 5 live runs because the model cannot FORM the call that would be refused: to be told 'that is
an arc, this tool binds chapters' it must first pass an arc id, and `composition_arc_list` was
advertised 0 of 5."

So the refusal is shipped and unproven, and the live path cannot reach it -- those turns die at
the provider (D-UPSTREAM-ERROR-WITH-NO-MESSAGE, blocked on DQ-T91).

THIS DRIVES IT DIRECTLY, no model in the loop, the same technique that established the gbuild
protocol runs end to end. That cannot show the MODEL reaches the refusal; it shows the refusal
EXISTS and says what it was ruled to say, which is the half that has never been demonstrated.

READ-ONLY IN EFFECT: every call is refused before it reaches a write. Throwaway fixture, torn
down in `finally`.
"""
from __future__ import annotations

import sys

from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError
from scripts.toolloop.provision import Throwaway, _tle_auth  # noqa: F401


def main() -> int:
    m = MCPDirect()
    fx = Throwaway("t58-arcrefusal", mcp=m).build()
    try:
        print(f"fixture book={fx.book_id} project={fx.project_id}\n")

        # 1. Mint an ARC. Its id is a `structure_node`, which is exactly the kind of id the
        #    refusal exists to reject -- an override/motif binding wants an `outline_node`.
        arc = m.call("composition_arc_edit", {
            "op": "create", "book_id": fx.book_id, "kind": "arc",
            "title": "Arc I - the probe", "summary": "seeded to obtain a structure_node id",
        })
        arc_id = (arc.get("node_id") or arc.get("id")
                  or (arc.get("arc") or {}).get("node_id"))
        print(f"  arc created: node_id={arc_id}")
        if not arc_id:
            print(f"  REFUTED: no arc id came back -- {str(arc)[:200]}")
            return 1

        # 2. A motif to bind. The tool needs one that is visible to this caller.
        motifs = m.call("composition_motif_search", {"q": "", "scope": "all"})
        items = (motifs.get("motifs") or [])
        if not items:
            print("  INCONCLUSIVE: no motif visible to bind, so the call cannot be formed")
            return 1
        motif_id = items[0]["id"]
        print(f"  motif: {items[0].get('name')!r} ({motif_id})\n")

        # 3. THE CALL THE MODEL HAS NEVER MANAGED TO FORM: bind a motif to an ARC.
        try:
            out = m.call("composition_motif_bind_edit", {
                "op": "bind", "project_id": fx.project_id,
                "node_id": arc_id, "motif_id": motif_id,
            })
            print(f"  \U0001f534 ACCEPTED -- the arc was NOT refused: {str(out)[:220]}")
            return 1
        except MCPToolError as exc:
            msg = str(exc)

        print(f"  REFUSED: {msg[:300]}\n")
        checks = {
            "names the node's KIND": "is a " in msg,
            "names CHAPTER as what it binds": "CHAPTER" in msg,
            "says the arc semantic is not guessed": "not guessed" in msg or "not something" in msg,
            "names the tool that lists chapters": "composition_list_outline" in msg,
        }
        for k, ok in checks.items():
            print(f"    {'PASS' if ok else 'FAIL'}  {k}")
        allok = all(checks.values())
        print(f"\n{'CONFIRMED' if allok else 'INCOMPLETE'}: the ruled refusal "
              f"{'fires and says what it was ruled to say' if allok else 'fired but is missing a part'}")
        return 0 if allok else 1
    finally:
        fx.teardown()


if __name__ == "__main__":
    sys.exit(main())
