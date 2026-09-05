#!/usr/bin/env python3
"""A tool that declares "favorite" and not "favourite" is invisible to half its users.

    python scripts/lint_synonym_spelling_variants.py            # report
    python scripts/lint_synonym_spelling_variants.py --write    # refresh the baseline

FOUND 2026-08-22, cycle 1 of the resolution loop. `settings_model_set_favorite` surfaced 0/5. It
declares the synonym `favorite`; the author typed "Mark the first one as a **favourite**." The
answerability matcher is exact on word boundaries, so the two spellings are simply different words
and the tool was never on the wire. Nothing about the request was ambiguous.

🔴 WHY THIS IS THE ONLY DECLARATION LINT HERE, AND WHAT WAS TRIED FIRST. Cycle 1's measurement
split the answerability misses into three modes, and mode 3 — "the word the tool declares was
never said" — is 12 of 27 tools and cannot be reached by any matcher. It looked mechanically
closable. Three designs were prototyped against the live 315-tool catalogue and **all three were
too noisy to act on**:

    a distinctive word of the tool's own NAME missing from its synonyms   49 flags,  2 real
    a verb declared with one of the FAMILY's object nouns but not another 178 flags,  9 real
    a tool's OWN verb x noun cross-product, cells unfilled               150 flags,  5 real

The third produced cells like "book book", "draft draft" and "open detail", because the declared
pairs are not all verb-noun — "book detail", "story bible" and "table contents" are noun-noun. The
second treats every noun in a family as interchangeable, and in `world_map_*` that lumps `map`,
`image` and `detail` in with `region`. **Whether two nouns name the same object is not derivable
from the declarations**, and a lint that flags 178 of 267 tools is a lint nobody reads.

So mode 3 is NOT closed mechanically, and saying so is the finding. What closes it is
`scripts/toolloop/answerability_probe.py` run against REAL measured turns — it knows what authors
actually said, which no lint over declarations can. This file covers the one slice that IS exact:
a spelling pair is the same word, so declaring one and not the other is unambiguously a gap.

BASELINE, not a hard failure: the current gaps are real and worth fixing, but failing the suite on
them would block every unrelated change. The test beside this asserts the set does not GROW — the
same shape as `contracts/undeclared-required-args-baseline.json`.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

from app.services.tool_surface import _answer_norm  # noqa: E402

CACHE = ROOT / "contracts" / "tool-catalog-cache.json"
BASELINE = ROOT / "contracts" / "synonym-spelling-variants-baseline.json"

# en-US / en-GB pairs that appear in authoring vocabulary. Each entry is the SAME word, so a tool
# declaring one and not the other has a gap by construction — there is no judgement call here,
# which is exactly what the three rejected designs lacked.
PAIRS: list[tuple[str, str]] = [
    ("favorite", "favourite"), ("favorites", "favourites"),
    ("color", "colour"), ("colors", "colours"),
    ("catalog", "catalogue"), ("catalogs", "catalogues"),
    ("organize", "organise"), ("organized", "organised"),
    ("analyze", "analyse"), ("analyzed", "analysed"),
    ("summarize", "summarise"), ("customize", "customise"),
    ("license", "licence"), ("canceled", "cancelled"), ("canceling", "cancelling"),
    ("center", "centre"), ("labeled", "labelled"), ("traveled", "travelled"),
    ("gray", "grey"),
]
# 🔴 TWO PAIRS WERE REMOVED AFTER THE FIRST RUN, and they are recorded rather than deleted quietly
# — the first version of this lint reproduced the exact fault it was written to avoid.
#
#   ("draft", "draught")   flagged EIGHT tools on its own, and every one was noise. A draught is a
#                          current of air or a drink; the manuscript sense is "draft" in en-GB and
#                          en-US alike. 8 of the 13 initial findings were this pair.
#   ("dialog", "dialogue") inert on this catalogue, and wrong in principle: "dialogue" is standard
#                          in both dialects for character speech, so declaring it is not a gap.
#
# The rule for this list is narrow on purpose: a pair belongs here ONLY when the two spellings are
# the same word in the same sense. Anything softer makes it the 178-flag lint that got rejected.


def find_gaps(cache: dict | None = None) -> dict[str, list[str]]:
    """{tool: ["declares 'favorite', not 'favourite'", ...]} — deterministic, sorted.

    `cache` is injectable so the gate can drive the detector over a SYNTHETIC catalogue. Its
    red-able test used to anchor on a live tool and inverted the day that tool was fixed."""
    cache = cache if cache is not None else json.loads(CACHE.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for name in sorted(cache):
        syns = [s for s in ((cache[name].get("meta") or {}).get("synonyms") or [])
                if isinstance(s, str)]
        if not syns:
            continue
        words = set()
        for s in syns:
            words |= set(_answer_norm(s).split())
        gaps = []
        for a, b in PAIRS:
            if a in words and b not in words:
                gaps.append(f"declares '{a}', not '{b}'")
            elif b in words and a not in words:
                gaps.append(f"declares '{b}', not '{a}'")
        if gaps:
            out[name] = sorted(gaps)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="refresh the baseline from the catalogue")
    a = ap.parse_args()
    gaps = find_gaps()
    if a.write:
        BASELINE.write_text(json.dumps({
            "_note": ("Tools declaring one spelling of a word and not its variant. A gap here is "
                      "exact, not a judgement: the two spellings are the same word, and the "
                      "answerability matcher is exact on word boundaries. The test beside this "
                      "asserts the set does not GROW; fixing an entry means adding the missing "
                      "spelling to the tool's synonyms and re-running with --write."),
            "_generated_by": "scripts/lint_synonym_spelling_variants.py --write",
            "gaps": gaps,
        }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"baseline written: {len(gaps)} tool(s)")
        return 0
    print(f"{len(gaps)} tool(s) declare one spelling and not its variant:")
    for name, gs in gaps.items():
        for g in gs:
            print(f"  {name:38} {g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
