"""Regenerate contracts/tool-names.json — the EXISTENCE contract two services read.

🔴 WHY A UNION AND NOT THE CATALOGUE ALONE. registry_propose_workflow must reject a step naming
a tool that does not exist (DQ-T37, owner 2026-08-31) without rejecting one that merely is not
in whichever snapshot happens to be handy. Measured 2026-09-01: the liveness manifest carries
223 tools, the live federated catalogue 316, and 94 REAL tools are in the catalogue and not the
manifest. Absence from either source alone is not evidence of non-existence; absence from BOTH
is the signal, and it is what `chapter_compose` — the hallucinated name that opened DQ-T37 —
looks like.

The embedded copy under services/agent-registry-service/internal/api/ must stay byte-identical;
TestToolNamesMatchContract reds if it drifts, the same lock the liveness manifest already has.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "tool-names.json"
EMBEDDED = ROOT / "services" / "agent-registry-service" / "internal" / "api" / "tool-names.json"


def build() -> str:
    cat = json.loads((ROOT / "contracts" / "tool-catalog-cache.json").read_text(encoding="utf-8"))
    live = json.loads((ROOT / "contracts" / "tool-liveness.json").read_text(encoding="utf-8"))
    names = sorted(set(cat) | set(live.get("tools") or {}))
    return json.dumps({
        "schema_version": 1,
        "source": "contracts/tool-catalog-cache.json (federated MCP catalogue) UNION "
                  "contracts/tool-liveness.json",
        "note": (
            "EXISTENCE, not liveness. registry_propose_workflow validates that a step's `tool` "
            "names a tool the platform has heard of (DQ-T37, owner 2026-08-31). The UNION is "
            "deliberate: the liveness manifest covers 223 tools and the live catalogue 316, and "
            "94 real tools are in the catalogue but not the manifest -- so absence from either "
            "alone is NOT evidence a tool does not exist. Regenerate with "
            "scripts/toolloop/tool_names.py."
        ),
        "count": len(names),
        "tools": names,
    }, indent=1, ensure_ascii=False) + "\n"


def main() -> int:
    doc = build()
    check = "--check" in sys.argv
    stale = [p for p in (CONTRACT, EMBEDDED)
             if not p.exists() or p.read_text(encoding="utf-8") != doc]
    if check:
        for p in stale:
            print(f"STALE: {p.relative_to(ROOT)}", file=sys.stderr)
        return 1 if stale else 0
    for p in (CONTRACT, EMBEDDED):
        p.write_text(doc, encoding="utf-8")
    print(f"wrote {json.loads(doc)['count']} tool names to both copies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
