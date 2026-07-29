"""D-PF-NORMALIZE — deterministic post-materialize / post-refine fixes.

## Why this module now normalizes NOTHING, and why the hook survives anyway

It used to do two things, both of which welded ONE novel into the engine every book runs through:

1. It renamed any character called `Female Protagonist` — and, when the open questions mentioned a
   name, any `[TBD]` protagonist — to the Vietnamese literal **`Nữ chính`**. On an English document
   that is not a normalization, it is a translation nobody asked for. Measured 2026-07-29 across the
   real `plan_run` corpus: an English grimdark braindump and a plain-English premise both came back
   with a protagonist named `Nữ chính`, a string that appears in neither document.

2. Worse, it REPLACED a mechanic's `rules` with two fixed Vietnamese sentences whenever the rules
   were not Vietnamese enough (`_vn_char_ratio < 0.15`) and the name matched a yin-yang hint.
   Verified live, exactly as written:

       in   ["Partners share body heat to survive the cold vacuum of the derelict.",
             "Resonance decays with distance and cannot be forced."]
       out  ["Âm Dương Hợp Hoan: hấp thụ linh khí qua đối tác; cường độ tỷ lệ thân mật",
             "Không gắn với cảnh giới tu luyện — chỉ theo trải nghiệm và biến số PA/HA"]

   The author's own two rules were **deleted** and replaced with another book's. Silently, on every
   propose, on both the rules and the LLM path.

Same disease as the format-bound parser (`ingest._section_level`), and the same one
`tests/unit/test_prompts_defixtured.py` already guards — that file even bans the exact literal
`Nữ chính`, but it only ever scanned `prompts.py`, so the deterministic path did the banned thing
unwatched. The guard now covers this module too.

Nothing depended on the rename: placeholder DETECTION lives in `existing_state._PLACEHOLDER_NAMES`,
which recognises `female protagonist` / `protagonist` / `main character` / `[TBD]` / empty on its
own. Removing the rewrite therefore leaves A1 cast injection working unchanged.

The hook stays because a *genuinely* book-agnostic deterministic fix belongs somewhere, and the call
sites (`propose.propose_spec`, `propose_llm.materialize_from_analyze`) are the right place for it.
It is identity today, and `test_normalize_never_rewrites_authored_content` keeps it honest: whatever
lands here later must not rename what the author named or replace what the author wrote.
"""

from __future__ import annotations

from typing import Any


def post_normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Deterministic, book-AGNOSTIC normalizations after materialize / refine.

    Currently none. See the module docstring: everything that used to live here was specific to one
    novel and destroyed authored content on every other one. Returns `spec` unchanged.
    """
    return spec
