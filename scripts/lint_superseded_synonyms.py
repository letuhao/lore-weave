#!/usr/bin/env python
"""A superseded tool must not out-declare its successor.

🔴 THE DEFECT THIS CATCHES, MEASURED LIVE 2026-08-14. "Rename the chapter called The Ember Codex
in my outline to The Ember Codex Opens" routed to `composition_outline_node_update`, which is
marked `superseded_by: composition_outline_node_edit`. The DEPRECATED tool declares the words a
person actually types — "rename chapter", "edit scene", "update node". Its SUCCESSOR, the unified
entry point that exists to serve exactly those requests, declares "edit outline node", "manage
outline node" and a handful of CREATE verbs. So the successor was surfaced on 0 of 3 runs and the
request naming its precise job could not reach it.

Swept across the live federated catalogue: **59 of 62 supersession pairs orphan at least one
phrasing.** `book_get` → `book_read` loses "open book" and "show book". `book_scene_list` →
`book_list` loses "scenes" and "scene index". `composition_arc_create` → `composition_arc_edit`
loses "create story arc" and "start a saga". This is not a scatter of per-tool slips; it is the
predictable consequence of splitting or unifying a tool and leaving the synonyms on the old name.

Why a LINT and not 59 edits: an edit is correct the day it is made and silent the next time a tool
is superseded. The runtime union in `tool_surface.answerable_tools` keeps the surface correct
today; this makes the DECLARATIONS converge and fails the next pair automatically.

Usage:
    python scripts/lint_superseded_synonyms.py                  # against the cached catalogue
    python scripts/lint_superseded_synonyms.py --max-orphans 0  # enforce (exit 1 on any orphan)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "contracts" / "tool-catalog-cache.json"


def _syn(entry: dict) -> set[str]:
    meta = entry.get("meta") or {}
    for holder in (meta, meta.get("loreweave") or {}):
        v = holder.get("synonyms") if isinstance(holder, dict) else None
        if isinstance(v, list) and v:
            return {str(x).strip().lower() for x in v if isinstance(x, str)}
    return set()


def audit(cat: dict) -> list[dict]:
    out = []
    for name, entry in sorted(cat.items()):
        succ = (entry.get("meta") or {}).get("superseded_by")
        if not isinstance(succ, str) or not succ:
            continue
        old = _syn(entry)
        if succ not in cat:
            out.append({"tool": name, "successor": succ, "why": "successor not in the catalogue",
                        "orphans": sorted(old)})
            continue
        orphans = sorted(old - _syn(cat[succ]))
        if orphans:
            out.append({"tool": name, "successor": succ,
                        "why": "phrasings only the DEPRECATED tool claims", "orphans": orphans})
    return out


_PROSE_SUPERSEDED = re.compile(r"superseded by ([a-z][a-z0-9_]+)", re.I)


def prose_only_supersession(cat: dict) -> list[tuple[str, str]]:
    """Tools whose DESCRIPTION says "superseded by X" while `_meta.superseded_by` is unset.

    🔴 A SUPERSESSION THE PLATFORM CANNOT READ IS NOT A SUPERSESSION. `glossary_list_ai_suggestions`
    ends its description "NOTE: superseded by glossary_curation_list — kept for existing callers
    only", is marked VisibilityLegacy, and deliberately declares no synonyms — all correct, and all
    invisible to the routing layer, because the machine-readable link is absent. So the successor
    inherits nothing: the runtime union added for R2 cannot fire, and a user's words reach neither
    tool. Measured live 2026-08-14: "Are there any suggested entries waiting for me to review?"
    surfaced nothing on 3 of 3 runs and the model called no tool at all.

    24 tools are in this state. It also corrects an over-claim worth stating plainly: "87 tools
    declare no synonyms, therefore 87 are unreachable" is too strong. A legacy tool SHOULD be
    unreachable by a user's words — its successor should take them. The defect is not the silence,
    it is that the link pointing at the successor was written for humans only.
    """
    out = []
    for name, entry in sorted(cat.items()):
        if (entry.get("meta") or {}).get("superseded_by"):
            continue
        m = _PROSE_SUPERSEDED.search(entry.get("description") or "")
        if m:
            out.append((name, m.group(1)))
    return out


def undeclared(cat: dict) -> list[str]:
    """Federated tools that declare no synonyms at all.

    🔴 WHY THIS IS A HARD CONTRACT AND NOT A NICETY, measured 2026-08-14. The surfacing design is
    a small budgeted hot seed PLUS a lazy tail the model reaches through `tool_list`/`tool_load`.
    Across 30 live runs of five ordinary authoring requests, `tool_list` was called ONCE and
    `tool_load` NEVER — with both advertised on every run. So the tail is not a fallback in
    practice; whatever the deterministic pre-filter puts on the wire is the entire reachable
    catalogue for that turn.

    A tool that declares nothing to match on therefore cannot be pre-filtered in, and nothing else
    will fetch it — it is not "harder to reach", it is unreachable on an ordinary turn.

    🔴 BUT NOT EVERY SILENCE IS A DEFECT, and my first framing of this number was too strong. A
    LEGACY tool SHOULD be unreachable by a user's words; its successor should take them. Many of
    these are exactly that — `VisibilityLegacy`, `nil` synonyms, deliberately. The count is a
    denominator to work through, not a defect count: subtract the legacy ones, and what remains is
    the set that genuinely has no way in. `prose_only_supersession` above is where the legacy half
    actually goes wrong.
    """
    return sorted(n for n, e in cat.items() if not _syn(e))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=str(CACHE))
    ap.add_argument("--max-orphans", type=int, default=None,
                    help="fail when more pairs than this orphan a phrasing (0 = strict)")
    ap.add_argument("--max-prose-only", type=int, default=None,
                    help="fail when more tools than this declare supersession in prose only")
    ap.add_argument("--max-undeclared", type=int, default=None,
                    help="fail when more tools than this declare no synonyms (0 = strict)")
    a = ap.parse_args()

    p = pathlib.Path(a.catalog)
    if not p.exists():
        print(f"no catalogue at {p} — run: python scripts/toolloop/catalog.py --refresh")
        return 2
    cat = json.loads(p.read_text(encoding="utf-8"))
    pairs = sum(1 for e in cat.values() if (e.get("meta") or {}).get("superseded_by"))
    bad = audit(cat)

    for b in bad:
        print(f"{b['tool']} -> {b['successor']}: {b['why']}")
        print(f"    {b['orphans']}")
    print(f"\n{pairs} supersession pair(s); {len(bad)} orphan at least one phrasing.")
    if not bad:
        print("Every superseded tool's vocabulary is claimed by its successor.")

    import collections
    undec = undeclared(cat)
    by_provider = collections.Counter(n.split("_")[0] for n in undec)
    legacy_undec = [n for n in undec
                    if (cat[n].get("meta") or {}).get("visibility") == "legacy"]
    print(f"{len(undec)} of {len(cat)} tools declare NO synonyms "
          f"({', '.join(f'{k} {v}' for k, v in by_provider.most_common(4))}) — of which "
          f"{len(legacy_undec)} are marked legacy (correctly silent; their SUCCESSOR should take "
          f"the words) and {len(undec) - len(legacy_undec)} have no way in at all.")

    prose = prose_only_supersession(cat)
    if prose:
        print(f"{len(prose)} tool(s) say 'superseded by X' in PROSE but carry no "
              "meta.superseded_by — the link exists for humans and not for the router, so the "
              "successor inherits nothing:")
        for n, succ in prose[:6]:
            print(f"    {n} -> {succ}")
        if len(prose) > 6:
            print(f"    ... and {len(prose) - 6} more")

    if a.max_orphans is None and a.max_undeclared is None and a.max_prose_only is None:
        # Report-only by default: 59 of 62 pairs and 86 of 315 tools fail today, so a strict
        # gate would block every commit before the declarations are written. Pin the numbers in
        # CI and ratchet them down; a count that only ever decreases is a fix in progress, and
        # a silent report nobody enforces is not.
        return 0
    rc = 0
    if a.max_orphans is not None and len(bad) > a.max_orphans:
        print(f"FAIL: {len(bad)} orphaned pair(s) > --max-orphans {a.max_orphans}")
        rc = 1
    if a.max_undeclared is not None and len(undec) > a.max_undeclared:
        print(f"FAIL: {len(undec)} undeclared tool(s) > --max-undeclared {a.max_undeclared}")
        rc = 1
    if a.max_prose_only is not None and len(prose) > a.max_prose_only:
        print(f"FAIL: {len(prose)} prose-only supersession(s) > --max-prose-only "
              f"{a.max_prose_only}")
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
