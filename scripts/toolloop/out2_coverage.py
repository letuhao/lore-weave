"""What fraction of list-shaped tools the OUT-2 defaults lint actually inspects.

D-THE-OUT2-LINT-ONLY-INSPECTS-TOOLS-THAT-ARE-ALREADY-COMPLIANT.
`scripts/context-budget-defaults-lint.py` is the cross-service enforcement for OUT-2, and
`docs/standards/mcp-tool-io.md` cites it as the partial coverage that "blocks NEW violations".
Its trigger is the presence of the compliance machinery:

    line 222   if "detail" not in params or "limit" not in params: continue
    line 238   if "detail" in fields and "limit" in fields:

So it checks that a tool which ALREADY has `detail` and `limit` defaults them well. 🔴 A TOOL IS
EXEMPTED BY BEING MORE NON-COMPLIANT, NOT LESS.

RE-DERIVED 2026-08-27 against the cached catalogue, and it is WORSE than the row recorded:

    41  list-shaped tools (name ends `_list`/`_search`, or contains `_list_`)
     8  carry BOTH detail and limit          — the lint sees these
    12  carry EXACTLY ONE of the two         — skipped by both triggers
    21  carry NEITHER                        — skipped by both triggers
    ---
    33 of 41 skipped; recall 8/41 = 20%

The row counted the 21 and not the 12, so it under-stated its own finding. Both triggers need
BOTH names: `detail` alone or `limit` alone falls through exactly as neither does.

AND IT IS PYTHON-ONLY. 32 files under services/ register MCP tools through Go's `NewToolMeta`,
and the lint walks Python ASTs over paths containing `/mcp/`. Every Go tool — provider-registry,
glossary, book, catalog, agent-registry — is outside it entirely.

🔴 SKIPPED IS NOT THE SAME AS OVER BUDGET, and nothing here claims 33 offenders. Exactly ONE was
ever measured — settings_list_models at 10,380 bytes — because it was the one a scenario already
called. Calling 32 unexamined tools on a live account to measure their payloads is what the
standing constraint forbids, so the population behind this recall gap is UNKNOWN and needs a
harness that seeds fixtures.

DERIVED, NEVER TYPED: `python scripts/toolloop/out2_coverage.py`.
"""
from __future__ import annotations

import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "out2-lint-coverage.json"
CACHE = ROOT / "contracts" / "tool-catalog-cache.json"


def is_list_shaped(name: str) -> bool:
    return name.endswith("_list") or name.endswith("_search") or "_list_" in name


def derive() -> dict:
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    both, one, neither = [], [], []
    for name in sorted(raw):
        if not is_list_shaped(name):
            continue
        props = set(((raw[name].get("inputSchema") or {}).get("properties") or {}))
        d, l = "detail" in props, "limit" in props
        (both if (d and l) else one if (d or l) else neither).append(name)
    try:
        go = subprocess.run(["git", "grep", "-l", "NewToolMeta", "--", "services/"],
                            cwd=ROOT, capture_output=True, text=True, timeout=120).stdout.split()
    except Exception:  # noqa: BLE001 — a census must not fail on a missing git
        go = []
    total = len(both) + len(one) + len(neither)
    return {
        "list_shaped": total,
        "inspected": len(both),
        "skipped": len(one) + len(neither),
        "recall": round(len(both) / total, 3) if total else None,
        "both_detail_and_limit": both,
        "exactly_one": one,
        "neither": neither,
        "go_files_registering_mcp_tools": len(go),
    }


if __name__ == "__main__":
    d = derive()
    CONTRACT.write_text(json.dumps(
        {"_what": __doc__.strip().splitlines()[0],
         "_derived_by": "python scripts/toolloop/out2_coverage.py", **d},
        indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"list-shaped {d['list_shaped']} · inspected {d['inspected']} · "
          f"skipped {d['skipped']} · recall {d['recall']:.0%} · "
          f"Go files outside the lint: {d['go_files_registering_mcp_tools']}")
