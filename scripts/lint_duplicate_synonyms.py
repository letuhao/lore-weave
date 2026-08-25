#!/usr/bin/env python
"""Two UNRELATED tools must not declare the same synonym.

🔴 THE DEFECT THIS CATCHES, MEASURED 2026-08-25. `composition_build_cast_and_graph` and `kg_build`
both declared **"build the knowledge graph"** — the same five words, verbatim, in two tools that
do different jobs from different inputs (one reads the book's chapters, the other reads prose the
caller hands it).

`tool_surface.answerable_tools` is ADDITIVE and ranks by match LENGTH, so an identical string is a
tie nothing downstream can break: there is nothing to break it *with*. Both tools land on the wire
indistinguishable, and whichever the model happens to prefer wins every time.

What that cost: the `composition-glossary-build-with-an-ontology` scenario built its prompt from
that exact phrase, on the sound reasoning that a tool declaring words verbatim should be reachable
by them. It is — and so is its twin. The tool measured **0/10, 0/20 and 0/5** across three
separate conditions and was recorded blocked, while what was actually being measured was the tie.
De-duplicating the phrase moved it off zero on the first run.

**A LEGACY TOOL SHARING WITH ITS SUCCESSOR IS NOT A DEFECT AND IS NOT REPORTED.** That overlap is
deliberate — `answerable_tools`' R2 rule exists to guarantee that whatever phrasing reaches a
superseded tool also reaches the tool that replaced it. Swept live: of 92 shared phrases, **75 are
exactly that** and only 17 are ties between unrelated tools.

Usage:
    python scripts/lint_duplicate_synonyms.py                # report
    python scripts/lint_duplicate_synonyms.py --max-ties 0   # enforce (exit 1 on any live tie)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "contracts" / "tool-catalog-cache.json"


def load() -> dict[str, dict]:
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    tools = raw.get("tools") or raw
    if isinstance(tools, dict):
        return {name: (td.get("meta") or td.get("_meta") or {}) for name, td in tools.items()}
    out = {}
    for td in tools:
        name = td.get("name") or (td.get("function") or {}).get("name")
        if name:
            out[name] = (td.get("meta") or (td.get("function") or {}).get("_meta") or {})
    return out


#: A tie that was DELIBERATELY LEFT IN PLACE because a live A/B said breaking it was worse.
#: Every entry must name the evidence, because "we meant to do that" with no measurement behind it
#: is how a lint stops meaning anything. This is not the same as the legacy<->successor family
#: above: those ties cannot be contested (one side is dropped from the catalogue); these are two
#: live tools that genuinely contest the phrase, and the contest was measured.
MEASURED_TIES = {
    "pause the translation": (
        "jobs_pause vs translation_job_control. Removing it from jobs_pause on the reasoning that "
        "a GENERIC tool must not claim a DOMAIN phrase took the tool from surfaced 5/5 / called "
        "5/5 to surfaced 2/5 / called 0/5, and translation_job_control did NOT pick up the calls "
        "(0/5 in both arms). Restoring it recovered surfacing to 5/5. Evidence: "
        "docs/eval/toolloop/2026-08-14/c-jobspause-{control,reword,restored}.json. Whether the "
        "domain tool SHOULD win the phrase is DQ-T41 and is the owner's."
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-ties", type=int, default=None,
                    help="fail when more live ties than this remain")
    a = ap.parse_args()

    meta = load()
    by_phrase: dict[str, set[str]] = {}
    for name, m in meta.items():
        for syn in (m.get("synonyms") or []):
            if isinstance(syn, str) and syn.strip():
                by_phrase.setdefault(syn.strip().lower(), set()).add(name)

    def supersession_family(names: set[str]) -> bool:
        """Every pair linked by superseded_by, in either direction — R2's deliberate overlap."""
        for x in names:
            for y in names:
                if x == y:
                    continue
                if meta.get(x, {}).get("superseded_by") == y:
                    continue
                if meta.get(y, {}).get("superseded_by") == x:
                    continue
                return False
        return True

    shared = {p: n for p, n in by_phrase.items() if len(n) > 1}
    intentional = {p: n for p, n in shared.items() if supersession_family(n)}
    ties = {p: n for p, n in shared.items()
            if p not in intentional and p not in MEASURED_TIES}
    # A tie only BITES when every tool in it can still reach the wire. A legacy tool is dropped
    # from the turn catalog, so a tie involving one cannot be contested in practice.
    live = {p: n for p, n in ties.items()
            if all(meta.get(x, {}).get("visibility") != "legacy" for x in n)}

    measured = {p: n for p, n in shared.items() if p in MEASURED_TIES}

    print(f"phrases declared by more than one tool : {len(shared)}")
    print(f"  intentional (legacy <-> successor)   : {len(intentional)}   [not a defect]")
    print(f"  MEASURED and deliberately kept       : {len(measured)}   [listed below, not hidden]")
    print(f"  ties between unrelated tools         : {len(ties)}")
    print(f"  ...still LIVE (every tool advertised): {len(live)}")
    # An allowlist that does not PRINT what it excused is a remainder bucket by another name.
    for p, n in sorted(measured.items()):
        print(f"\nKEPT BY MEASUREMENT: {p!r} -> {sorted(n)}\n  {MEASURED_TIES[p]}")
    if live:
        print("\nLIVE TIES — answerability cannot separate these:")
        for p, n in sorted(live.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            print(f"  {p!r:44} -> {sorted(n)}")
        print("\nFix by making each phrase name what distinguishes the tools — usually their "
              "INPUT or their scope — rather than by picking a winner. `kg_build` reads the "
              "book's chapters and `composition_build_cast_and_graph` reads prose it is handed, "
              "so neither kept the bare phrase: each says which.")

    if a.max_ties is not None and len(live) > a.max_ties:
        print(f"\nFAIL: {len(live)} live tie(s) > --max-ties {a.max_ties}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
