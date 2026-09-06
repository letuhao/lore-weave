#!/usr/bin/env python3
"""Was the supplier STARVED off the wire by the hot-seed token budget? Offline, deterministic.

    python scripts/toolloop/hotseed_starvation_probe.py            # P3's suppliers, per surface
    python scripts/toolloop/hotseed_starvation_probe.py --control  # agree with observed runs

🔴 WHY THIS EXISTS. `P3-NAME-TO-ID` is stated as "the model will not walk a supplier chain that is
ON THE SAME WIRE", and two of its ledger rows say so in as many words — "sat unused on the same
wire", "even though that tool is on the same wire". Nobody measured the wire. Gate evidence records
whether the TOOL UNDER TEST surfaced and never the advertised set, so the load-bearing clause of
the problem statement was the one thing not in evidence.

It matters because the two readings need opposite fixes. If the supplier was advertised, the
finding is about the MODEL and the fix is in declarations, refusals or the turn loop. If it was
never advertised, the finding is about the SURFACE and every one of those fixes is aimed at the
wrong layer — which is how world_map_delete's declaration fix came to be shipped, measured, and
recorded as REFUTED.

WHAT IT READS, all of it the platform's:
  * `_budget_names_impl`, `hot_tool_names`, `surface_hot_domains` — imported, never reimplemented.
    A reimplementation would measure my copy of the rule, and agreeing with myself is not evidence.
  * `contracts/tool-catalog-cache.json` — the catalogue as the model receives it.

THE CONTROL, and it is the reason this file is not a scratch script. `--control` replays the
COMPUTED hot seed against the ADVERTISED sets recorded in the cycle-1 raw evidence, which kept the
agentSurface event. If what this computes disagrees with what those turns actually offered, the
mechanism modelled here is not the mechanism that runs, and every "STARVED" below is noise. It
prints the disagreements by name rather than a rate, because a rate hides which way it failed.

WHAT IT CANNOT TELL YOU: the hot seed is one of several paths onto the wire — sticky domains, a
binding's categories, the session's activated_tools and answerability all add tools this does not
model. So STARVED means "the hot seed did not carry it", never "it was absent from the turn". Only
a run's own agentSurface event says that, which is what supplier_probe.py reads.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

from app.services.tool_discovery import hot_tool_names, surface_hot_domains  # noqa: E402
from app.services.tool_surface import (  # noqa: E402
    ALWAYS_HOT_READS, HOT_SEED_TOKEN_BUDGET, _budget_names_impl, _tool_tokens,
)

CACHE = ROOT / "contracts" / "tool-catalog-cache.json"
EVID = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14"

#: tool -> the supplier its ledger row names. `None` means the row says none exists.
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

SURFACES = [
    ("editor", dict(editor=True, book_scoped=True)),
    ("studio", dict(studio=True)),
    ("book_scoped", dict(book_scoped=True)),
    ("universal", dict()),
]


def catalog() -> list[dict]:
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    defs = [{"type": "function", "function": {
        "name": n, "description": t.get("description") or "",
        "parameters": t.get("inputSchema") or {}, "_meta": t.get("meta") or {}}}
        for n, t in raw.items()]
    # The adapter control. `_tool_tokens` counts the serialised declaration, so a conversion that
    # dropped `parameters` would make every tool cheap and NOTHING would ever read as starved —
    # precisely the answer that would retire this whole line of enquiry.
    sizes = [_tool_tokens(d) for d in defs]
    if max(sizes) < 100:
        raise SystemExit(f"ADAPTER BROKEN - largest declaration is {max(sizes)} tokens")
    return defs


def seed_for(defs: list[dict], **kw) -> tuple[set[str], set[str]]:
    doms = surface_hot_domains(**kw)
    cand = set(hot_tool_names(defs, doms))
    return cand, set(_budget_names_impl(defs, cand, token_budget=HOT_SEED_TOKEN_BUDGET))


def cmd_report(defs: list[dict]) -> int:
    by_name = {d["function"]["name"]: d for d in defs}
    print(f"HOT_SEED_TOKEN_BUDGET={HOT_SEED_TOKEN_BUDGET}   "
          f"ALWAYS_HOT_READS={len(ALWAYS_HOT_READS)}\n")
    verdict: dict[str, str] = {}
    for label, kw in SURFACES:
        cand, kept = seed_for(defs, **kw)
        print(f"{label:12} domains={sorted(surface_hot_domains(**kw))}")
        print(f"{'':12} candidates={len(cand)}  kept={len(kept)}")
        for tool, sup in SUPPLIER.items():
            if sup is None or sup not in cand:
                continue
            ok = sup in kept
            verdict[sup] = "KEPT" if ok else "STARVED"
            print(f"{'':12}   {sup:32} {'KEPT' if ok else 'STARVED':8}"
                  f" {_tool_tokens(by_name[sup]):>5} tok   (for {tool})")
        print()
    print("Suppliers never in ANY surface's hot-seed candidate set - they reach the wire, when they")
    print("do, by another path (sticky domain, binding category, activation, answerability):")
    for tool, sup in SUPPLIER.items():
        if sup is not None and sup not in verdict:
            print(f"  {sup:32} (for {tool})")
    return 0


def cmd_control(defs: list[dict]) -> int:
    """Does the COMPUTED seed agree with what cycle-1 runs actually advertised?"""
    files = sorted(EVID.glob("c1-*-raw.json"))
    if not files:
        raise SystemExit(f"no cycle-1 raw evidence under {EVID}")
    observed: dict[str, set[str]] = {}
    for f in files:
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in rows if isinstance(rows, list) else []:
            names: set[str] = set()
            for s in [r.get("surface")] + list(r.get("surfaces") or []):
                for v in ((s or {}).get("advertised") or {}).values():
                    if isinstance(v, list):
                        names |= {str(x) for x in v}
            if names:
                observed.setdefault(r.get("scenario") or "?", set()).update(names)

    # The union over every surface: a tool the hot seed can carry ANYWHERE.
    seeded: set[str] = set()
    for _, kw in SURFACES:
        seeded |= seed_for(defs, **kw)[1]

    print(f"observed advertised sets: {len(observed)} scenario(s) with an agentSurface event\n")
    miss = collections.Counter()
    for sup in sorted({s for s in SUPPLIER.values() if s}):
        seen = sorted(s for s, names in observed.items() if sup in names)
        tag = "seeded" if sup in seeded else "NOT seeded"
        print(f"  {sup:32} {tag:11} advertised on {len(seen)}/{len(observed)} scenario(s)")
        if sup not in seeded and seen:
            miss["advertised though the seed cannot carry it"] += 1
            print(f"{'':36} -> {', '.join(seen[:4])}")
    print()
    print("READ THIS AS: 'NOT seeded' + advertised anywhere means ANOTHER PATH put it on the wire,")
    print("so a starvation fix would be aimed at the wrong layer for that tool. 'NOT seeded' +")
    print("advertised nowhere is consistent with starvation but does not prove it - only the")
    print("turn's own agentSurface event does, which is supplier_probe.py's job.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", action="store_true",
                    help="replay the computed seed against observed advertised sets")
    a = ap.parse_args()
    defs = catalog()
    return cmd_control(defs) if a.control else cmd_report(defs)


if __name__ == "__main__":
    raise SystemExit(main())
