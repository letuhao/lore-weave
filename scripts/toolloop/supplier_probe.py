#!/usr/bin/env python3
"""Was the SUPPLIER on the wire? — the control P3-NAME-TO-ID has to survive.

    python scripts/toolloop/supplier_probe.py --raw docs/eval/toolloop/2026-08-14/c2-rerun-raw.json

🔴 WHY THIS EXISTS. P3-NAME-TO-ID is stated as "the model will not walk a supplier chain that is ON
THE SAME WIRE", and five recorded instances back it. That last clause is the load-bearing part: it
is the difference between a finding about the MODEL and a finding about the SURFACE. Cycle 1 has
just proved the advertised surface was broken for 37 tools — so the claim cannot be assumed, it has
to be read off the turn.

The archive could not answer it. Gate evidence records only whether the TOOL UNDER TEST surfaced,
never the advertised set, so the supplier's presence was never captured for any of those batches.
That is itself worth knowing: a whole problem statement rested on a property nobody had measured.

WHAT IT READS: the run's own `agentSurface` event — `advertised.{core,frontend,activated,…}` —
which the runner keeps in the raw file. Nothing here is inferred from the tool's behaviour.

THE THREE ANSWERS, and they need different fixes:
    supplier ADVERTISED, never called   the model had it and did not use it — the problem as stated
    supplier NEVER ADVERTISED           the model could not have used it — a surfacing problem
    NO SUPPLIER EXISTS                  nothing to walk to (glossary_entity_restore: a deleted
                                        entity is invisible to search, chapter text and memory)

WHAT IT DOES NOT ANSWER: whether the model UNDERSTOOD that the supplier was the way to get the id.
An advertised, unused supplier is consistent with both "would not" and "did not realise", and this
cannot separate them.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: tool -> the tool that supplies the id it requires, from each ledger row's own blocked_reason.
#: `None` means the row says no supplier exists.
SUPPLIER: dict[str, str | None] = {
    "composition_arc_template_edit": "composition_arc_template_list",
    "composition_authoring_run_review": "composition_authoring_run_list",
    "composition_motif_link_edit": "composition_motif_search",
    "composition_generate": "settings_list_models",
    "world_delete": "world_list",
    "world_map_create": "world_list",
    "world_map_delete": "world_map_list",
    "glossary_entity_restore": None,
}


def advertised(rec: dict) -> set[str]:
    """Every tool name the turn actually advertised, across all of its passes."""
    out: set[str] = set()
    for s in [rec.get("surface")] + list(rec.get("surfaces") or []):
        for v in ((s or {}).get("advertised") or {}).values():
            if isinstance(v, list):
                out |= {str(x) for x in v}
    return out


def called(rec: dict) -> set[str]:
    return {c.get("toolCallName") for c in (rec.get("tool_calls") or [])
            if isinstance(c, dict) and c.get("toolCallName")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="a fe_runner --out raw results file")
    a = ap.parse_args()
    rows = json.loads(pathlib.Path(a.raw).read_text(encoding="utf-8"))

    by_scn: dict[str, list] = collections.defaultdict(list)
    for r in rows:
        by_scn[r.get("scenario") or "?"].append(r)

    print(f"{'tool':34} {'supplier':32} {'advertised':>12} {'called':>8}")
    print("-" * 92)
    tally = collections.Counter()
    for scn, recs in sorted(by_scn.items()):
        tool = next((t for t in SUPPLIER if t.replace("_", "-") == scn), None)
        if tool is None:
            tool = next((t for t in SUPPLIER if scn.replace("-", "_").startswith(t[:24])), None)
        if tool is None:
            continue
        sup = SUPPLIER[tool]
        n = len(recs)
        if sup is None:
            print(f"{tool:34} {'(none exists)':32} {'n/a':>12} {'n/a':>8}")
            tally["no supplier exists"] += 1
            continue
        adv = sum(1 for r in recs if sup in advertised(r))
        cal = sum(1 for r in recs if sup in called(r))
        print(f"{tool:34} {sup:32} {f'{adv}/{n}':>12} {f'{cal}/{n}':>8}")
        if adv == 0:
            tally["supplier NEVER advertised — not a model finding"] += 1
        elif cal == 0:
            tally["advertised and NEVER called — the problem as stated"] += 1
        else:
            tally["advertised AND called"] += 1

    print()
    for k, v in tally.most_common():
        print(f"  {v:>3}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
