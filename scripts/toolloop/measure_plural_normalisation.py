#!/usr/bin/env python3
"""DQ-T6 (i): what does trailing-s normalisation COST, measured before it ships?

THE OWNER'S BAR, stated in the ruling: "loosening a matcher whose whole value is precision has a
measurable false-positive cost. That cost is to be MEASURED across the live 316-tool catalogue
BEFORE the change ships, not asserted."

THE DEFECT IT WOULD FIX, measured 2026-09-02:
    "Suggest some arc structures for this book."  -> [composition_arc_list]
    "Suggest an arc structure for this book."     -> the arc tools match
`composition_arc_suggest` was advertised 0/5 and the model used a WRITE
(composition_structure_template_edit) on 5 of 5.

WHAT IS MEASURED HERE, over every recorded user prompt in the corpus:
  1. how many prompts GAIN an answerable tool they did not have
  2. how many prompts LOSE nothing (the rule only ever adds, so losses should be zero --
     asserted rather than assumed)
  3. the tools gained, so a human can read whether each is a plausible answer or noise

A GAIN IS NOT AUTOMATICALLY GOOD. A synonym matching a request it does not answer is the exact
failure `_synonym_pattern` exists to prevent ("cat" inside "category" cost a live run). So the
gained pairs are printed, not just counted.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

from app.services.tool_surface import (  # noqa: E402
    _answer_norm, _synonym_pattern, tool_name,
)

#: The candidate rule: a trailing 's' on a word, and nothing else. No stemmer, no plural table.
_TRAILING_S = re.compile(r"(\w{3,})s\b")


def depluralise(text: str) -> str:
    """Strip a trailing 's' from words of 4+ characters.

    The 3-char floor is deliberate: it keeps 'is', 'as', 'us' and every two-letter word intact,
    and it is the smallest guard that stops the rule inventing words.
    """
    return _TRAILING_S.sub(r"\1", text)


def answerable(prompt: str, catalog: dict, mode: str) -> set[str]:
    """mode: 'off' | 'request' (the ruling as worded) | 'both' (symmetric).

    🔴 THE DISTINCTION IS THE WHOLE MEASUREMENT. The ruling says "MATCH A DECLARED
    SYNONYM AGAINST A LIGHTLY NORMALISED REQUEST" -- the REQUEST is normalised, the declaration
    is not. Normalising both sides is a different, much wider rule: it turns the synonym
    "list my books" into "list my book", which then matches "...add a character to my book".
    """
    raw = _answer_norm(prompt)
    if not raw:
        return set()
    dep = depluralise(raw)
    # 'additive' tries BOTH forms of the request and never rewrites the declaration, so it is a
    # superset of the shipped behaviour by construction -- it cannot lose a match. The other two
    # modes REPLACE the request (and, for 'both', the synonym too), which is why they can.
    targets = {"off": [raw], "request": [dep], "both": [dep], "additive": [raw, dep]}[mode]
    out = set()
    for name, meta in catalog.items():
        for syn in ((meta.get("meta") or {}).get("synonyms") or []):
            if not isinstance(syn, str):
                continue
            ns = _answer_norm(syn)
            if mode == "both":
                ns = depluralise(ns)
            if not ns:
                continue
            pat = _synonym_pattern(ns)
            if any((pat.search(t) if pat is not None else ns in t) for t in targets):
                out.add(name)
                break
    return out


def prompts_from_corpus() -> list[str]:
    seen = set()
    for path in glob.glob(str(ROOT / "docs" / "eval" / "toolloop" / "*" / "*-raw.json")):
        try:
            recs = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(recs, list):
            continue
        for r in recs:
            if isinstance(r, dict) and isinstance(r.get("prompt"), str):
                seen.add(r["prompt"].strip())
    return sorted(p for p in seen if p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=25)
    ap.add_argument("--mode", choices=["request", "both", "additive"], default="request")
    a = ap.parse_args()
    global MODE
    MODE = a.mode

    catalog = json.loads(
        (ROOT / "contracts" / "tool-catalog-cache.json").read_text(encoding="utf-8"))
    catalog = {k: v for k, v in catalog.items()
               if isinstance(v, dict) and (v.get("meta") or {}).get("visibility") != "legacy"}
    prompts = prompts_from_corpus()
    print(f"MODE: {MODE}")
    print(f"live tools: {len(catalog)}   distinct recorded prompts: {len(prompts)}")

    gained = collections.Counter()
    lost = collections.Counter()
    gain_examples: list[tuple[str, set]] = []
    n_gain = n_loss = n_same = 0
    empty_before = empty_after = 0

    for p in prompts:
        before = answerable(p, catalog, "off")
        after = answerable(p, catalog, MODE)
        empty_before += not before
        empty_after += not after
        g, l = after - before, before - after
        for t in g:
            gained[t] += 1
        for t in l:
            lost[t] += 1
        if g and not l:
            n_gain += 1
            if len(gain_examples) < a.show:
                gain_examples.append((p, g))
        elif l:
            n_loss += 1
        else:
            n_same += 1

    print(f"\nprompts UNCHANGED           {n_same}")
    print(f"prompts that GAIN a tool    {n_gain}   ({n_gain/len(prompts):.1%})")
    print(f"prompts that LOSE a tool    {n_loss}   <- must be 0: the rule only ever widens")
    print(f"prompts with NO answerable set: before {empty_before}, after {empty_after}")
    print(f"\ntotal (prompt, tool) pairs gained: {sum(gained.values())}")

    print(f"\nTOOLS GAINED (read these: a gain is only good if the tool ANSWERS the request):")
    for t, n in gained.most_common(20):
        print(f"   {n:4d}  {t}")

    print(f"\nEXAMPLES, to be read rather than counted:")
    for p, g in gain_examples:
        print(f"   {p[:96]!r}\n      + {sorted(g)}")

    if lost:
        print("\n\U0001f534 LOSSES — the rule was supposed to be purely additive:")
        for t, n in lost.most_common(10):
            print(f"   {n:4d}  {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
