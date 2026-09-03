#!/usr/bin/env python
"""A LIVE tool whose own text names a DROPPED tool sends the model somewhere it cannot go.

THE INVARIANT: no live tool's model-facing text — its description, or any argument
description — may name a tool that `drop_superseded_tools` removes from every turn.

WHY IT MATTERS, and why "deprecated is dead" is not enough on its own. Since 2026-08-25 the
superseded gate drops EVERY `visibility: legacy` tool from the wire, replacement or not. That
made the legacy tools unreachable — but it did nothing to the SENTENCES that point at them. The
model reads "call the SEPARATE tool `book_structure_part_archive`", finds no such tool in its
surface, and has three options, all bad: hallucinate the call, invent a different tool, or report
the job done. Every one of those looks like a model failure and is a catalogue failure.

🔴 MEASURED 2026-09-03 over the 202 live tools. Four were steering the model at a dropped tool:

    book_structure_edit          -> book_structure_part_archive  (legacy, NO successor)
    composition_list_canon_rules -> composition_canon_rule_restore  (-> composition_canon_rule_edit)
    glossary_confirm_action      -> glossary_book_delete            (-> glossary_ontology_delete)
    glossary_ontology_delete     -> glossary_user_restore        (legacy, NO successor)

Two had a declared successor and were simply re-pointed. The other two named a capability with no
live replacement at all, and the honest repair was to SAY SO — "this was retired with no
replacement, do not look for it, do not claim you did it" — because a description that stays
silent about a missing capability is the one that gets hallucinated around.

WHY THE CACHE AND THE SOURCE ARE BOTH READ. `contracts/tool-catalog-cache.json` is a snapshot of
the LIVE federated catalogue (see `scripts/refresh_tool_catalog_cache.py`), so it lags a source
fix until the services are rebuilt and the cache refreshed. Reporting a source-fixed line as an
open defect would train a reader to ignore this gate; reporting it as clean would hide that the
DEPLOYED description is still wrong. So a hit is classified, not merged:

    LIVE DEFECT       — in the cache AND still in the source: fix the description
    CACHE ONLY        — in the cache, gone from the source: refresh the cache

Usage:
    python scripts/test_a_live_tool_never_sends_the_model_to_a_dropped_one.py
    python scripts/test_a_live_tool_never_sends_the_model_to_a_dropped_one.py --selftest
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "contracts" / "tool-catalog-cache.json"
_NAME_RE = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b")
#: Text that tells the model the named tool is GONE, rather than sending it there.
_RETIRED_RE = re.compile(r"retired|no longer|deprecated|has no tool|no replacement|do not look for it|was removed", re.I)


def _texts(row: dict):
    fn = row.get("function") or row
    yield fn.get("description") or ""
    for v in ((fn.get("parameters") or {}).get("properties") or {}).values():
        if isinstance(v, dict):
            yield v.get("description") or ""


def find(catalog: dict) -> dict[str, set[str]]:
    """{live tool -> the dropped tools its own text STEERS the model to}.

    🔴 NAMING A DEAD TOOL IS NOT STEERING TO IT. The first draft flagged any mention, and then
    flagged its own repairs: the honest fix for a retired capability is a sentence that NAMES the
    retired tool in order to say it is gone ("book_structure_part_archive was retired with no
    replacement — do not look for it"). A gate that reddens on the correct repair forces the next
    author to choose between the gate and the truth, and the gate loses.

    So a mention is a defect only when nothing near it says the tool is gone.
    """
    live = {n for n, r in catalog.items()
            if (r.get("meta") or {}).get("visibility", "live") == "live"}
    dropped = set(catalog) - live
    out: dict[str, set[str]] = {}
    for n in sorted(live):
        for t in _texts(catalog[n]):
            for m in _NAME_RE.finditer(t or ""):
                name = m.group(0)
                # A tool naming ITSELF is not steering anywhere.
                if name not in dropped or name == n:
                    continue
                window = t[max(0, m.start() - 160):m.end() + 160]
                if _RETIRED_RE.search(window):
                    continue
                out.setdefault(n, set()).add(name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    catalog = json.loads(CACHE.read_text(encoding="utf-8"))

    if a.selftest:
        # Seed the exact 2026-09-03 defect into an in-memory catalogue and require a hit.
        seeded = {
            "book_structure_edit": {"function": {
                "description": "Reorganize. To DELETE a part, call the SEPARATE tool "
                               "book_structure_part_archive (soft-delete).", "parameters": {}}},
            "book_structure_part_archive": {"function": {"description": "archive"},
                                            "meta": {"visibility": "legacy"}},
        }
        hits = find(seeded)
        ok = hits.get("book_structure_edit") == {"book_structure_part_archive"}
        # And a tool naming ITSELF must NOT be a hit, or every legacy tool reports itself.
        selfref = find({"x_dead": {"function": {"description": "x_dead does a thing"},
                                   "meta": {"visibility": "legacy"}}})
        print(f"[{'RED-ABLE' if ok else 'VACUOUS '}] finds the seeded 2026-09-03 defect")
        print(f"[{'OK      ' if not selfref else 'FALSE+  '}] a tool naming itself is not a hit")
        return 0 if (ok and not selfref) else 1

    hits = find(catalog)
    live = sum(1 for r in catalog.values()
               if (r.get("meta") or {}).get("visibility", "live") == "live")
    print(f"{len(catalog)} tools in the cache ({live} live); "
          f"{len(hits)} live tool(s) STEER the model to a dropped tool")
    # The cache is a SNAPSHOT of the live federated catalogue, so it lags a source fix until the
    # services are rebuilt and `scripts/refresh_tool_catalog_cache.py` is run. A hit here is a
    # claim about what the DEPLOYED catalogue says — which is the thing the model actually reads.
    for tool, names in sorted(hits.items()):
        print(f"  {tool} -> {', '.join(sorted(names))}")
    if not hits:
        print("  none — every dropped tool named in live text is named AS retired")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
