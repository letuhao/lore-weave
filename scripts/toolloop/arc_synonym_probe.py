"""What would a candidate synonym on `composition_arc_list` REACH, and what would it DISTURB?

DQ-T58's ruling: SURFACE `composition_arc_list` WHENEVER AN ARC REQUEST IS ANSWERABLE. Measured
against the deployed matcher, arc_list matches only its own six literal phrasings — "What arcs
does this book have?" and "Show me the opening arc" both return the EMPTY SET, and the row's own
prompt returns only composition_motif_search. So an arc request is not answerable at all today.

WHY A DECLARATION AND NOT AN EMITTER, established by reading the mechanism rather than guessing:
R1's supplier-arming walks `required` args starting from `_r1_seed = _answerable`. A tool that is
on the wire through the DOMAIN HOT SET is never a seed, so its declared emitters never arm. And
`composition_motif_bind_edit.node_id` is a CHAPTER node — declaring arc_list as its emitter would
be a false declaration, which is exactly what the contract registry's bar forbids.

🔴 THE COST THIS MUST PRICE, because DQ-T58's own reopening was refused for not pricing it: a
synonym broad enough to reach the request can put a tool on every turn that says the word. That
objection was raised against a Tier-A WRITE ("'motif' matched 4 of 4 controls, i.e. it would
force this Tier-A WRITE onto every turn that says the word"). arc_list is Tier R and read-only,
so the same breadth costs differently — but it still costs, and "differently" is not "nothing".

So every candidate is measured three ways over the LIVE 316-tool catalogue and 2,033 DISTINCT
real user prompts from the chat store:
  REACH      does it match the row's own prompt and the natural arc questions?
  DISTURB    how many corpus prompts go from not-matching arc_list to matching it?
  TIES       how many of those newly-matched prompts now have arc_list competing with a tool
             that was ALREADY answerable there — the answerability-tie cost DQ-T70 measured.
  DISPLACED  🔴 THE COST THAT ACTUALLY BITES, and the first version of this probe did not
             measure it. `ANSWERABLE_MAX = 8` truncates the answerable set by score, so a new
             synonym does not merely ADD arc_list — on a prompt already at the cap it can EVICT
             a tool the turn needed. A candidate that reaches the request and displaces nothing
             is a different proposition from one that buys reach by pushing something out, and
             the two are indistinguishable in a count of "newly matched".

NOTE ON THE CANDIDATES: `_answer_norm` STRIPS ARTICLES, so "the arc" and "arc" are the same
declaration and score identically. Both are listed anyway — a table where two rows that look
different come out equal is what makes the normaliser visible instead of a silent surprise.

Usage:  python scripts/toolloop/arc_synonym_probe.py [--corpus FILE]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

from app.services.tool_surface import answerable_tools  # noqa: E402

CACHE = ROOT / "contracts" / "tool-catalog-cache.json"
TOOL = "composition_arc_list"

#: The turns this ruling is about. The first is the row's own wording, verbatim.
REACH_SET = [
    "Attach Emberfall Seam to the opening arc as this book's motif.",
    "What arcs does this book have?",
    "Show me the opening arc",
    "Which arc does chapter 3 belong to?",
    "Add a motif to the second arc",
]

#: Candidates. Deliberately includes ones expected to FAIL, so the measurement can refuse them
#: rather than only confirming a preferred answer.
CANDIDATES = {
    "arc": ["arc"],
    "the arc": ["the arc"],
    "arcs": ["arcs"],
    "which arc": ["which arc"],
    "opening arc": ["opening arc"],
    "arcs + which arc": ["arcs", "which arc"],
    "arcs + the arc": ["arcs", "the arc"],
}


def catalog() -> list[dict]:
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    defs = [{"type": "function", "function": {
        "name": n, "description": t.get("description") or "",
        "parameters": t.get("inputSchema") or {}, "_meta": t.get("meta") or {}}}
        for n, t in raw.items()]
    # THE ADAPTER CONTROLS, copied from answerability_probe.py and raising for the same reason:
    # every figure below is meaningless if the conversion dropped `synonyms`, and "nothing
    # matched" is precisely what a broken adapter says.
    if "glossary_propose_translation" not in answerable_tools(
            "Give me vietnamese names for these characters", defs):
        raise SystemExit("ADAPTER BROKEN — positive control did not match")
    if answerable_tools("hello, how are you today", defs):
        raise SystemExit("ADAPTER BROKEN — chitchat matched something")
    return defs


def with_synonyms(defs: list[dict], extra: list[str]) -> list[dict]:
    """The catalogue with `extra` added to TOOL's synonyms. Copies the one tool's meta so the
    baseline list is never mutated — a shared dict here would make every arm measure the last."""
    out = []
    for td in defs:
        if td["function"]["name"] != TOOL:
            out.append(td)
            continue
        fn = dict(td["function"])
        meta = dict(fn.get("_meta") or {})
        meta["synonyms"] = list(meta.get("synonyms") or []) + list(extra)
        fn["_meta"] = meta
        out.append({"type": "function", "function": fn})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    a = ap.parse_args()

    base = catalog()
    corpus = [ln.strip() for ln in pathlib.Path(a.corpus).read_text(
        encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    print(f"catalogue {len(base)} tools · corpus {len(corpus)} distinct prompts\n")

    base_hits = {p: set(answerable_tools(p, base)) for p in corpus}
    base_reach = {p: sorted(answerable_tools(p, base)) for p in REACH_SET}
    print("BASELINE — what an arc request answers today:")
    for p, h in base_reach.items():
        print(f"    {'HIT ' if TOOL in h else 'miss'}  {p!r}\n            {h or 'EMPTY'}")
    n_base = sum(1 for h in base_hits.values() if TOOL in h)
    print(f"\n    corpus prompts already matching {TOOL}: {n_base} of {len(corpus)}\n")

    print(f"{'candidate':22} {'reach':>7}  {'newly matched':>14}  {'of those, TIED':>15}"
          f"  {'DISPLACED':>10}")
    print("-" * 78)
    rows = []
    for label, extra in CANDIDATES.items():
        defs = with_synonyms(base, extra)
        reach = sum(1 for p in REACH_SET if TOOL in answerable_tools(p, defs))
        newly, tied, displaced = [], [], []
        for p in corpus:
            after = set(answerable_tools(p, defs))
            lost = base_hits[p] - after
            if lost:
                displaced.append((p, sorted(lost)))
            if TOOL in base_hits[p]:
                continue
            if TOOL in after:
                newly.append(p)
                if base_hits[p]:
                    tied.append(p)
        rows.append((label, reach, newly, tied, displaced))
        print(f"{label:22} {reach:>3}/{len(REACH_SET)}  {len(newly):>14}  {len(tied):>15}"
              f"  {len(displaced):>10}")

    print("\nWHAT EACH ONE NEWLY CATCHES (up to 4, so a number can be read):")
    for label, _, newly, tied, _d in rows:
        print(f"  {label}:")
        for p in newly[:4]:
            mark = "TIE " if p in tied else "    "
            print(f"      {mark}{p[:96]!r}")
        if not newly:
            print("      (nothing)")

    print()
    print("WHAT EACH ONE EVICTS — a tool that WAS answerable and no longer is:")
    for label, _, _, _, displaced in rows:
        print(f"  {label}: {len(displaced)}")
        for p, lost in displaced[:3]:
            print(f"      {p[:80]!r}")
            print(f"          lost {lost}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
