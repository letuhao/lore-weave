"""D-EXTRACTION-CONTEXT-WINDOW — context-aware chapter windowing for extraction.

A chapter larger than the model context is split into sub-chapter windows (whole
paragraph blocks, reusing the translation block batcher) that fit, extracted from each,
then accumulated. These cover the pure helpers; the LLM call + end-to-end is proven by
the live extraction run.
"""

from __future__ import annotations

from app.workers.extraction_worker import _merge_window_entities, _plan_chapter_windows


def _para(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def test_plan_windows_splits_large_chapter_by_context():
    # 6 sizable paragraphs + a deliberately TINY context → must split into >1 window.
    paras = [_para("Paragraph number %d. " % i + "word " * 200) for i in range(6)]
    chapter = {"body": {"content": paras}}
    text = "\n\n".join(p["content"][0]["text"] for p in paras)
    windows = _plan_chapter_windows(chapter, text, context_window=2048, source_language="en")
    assert len(windows) > 1, "a large chapter on a small context must split into multiple windows"
    # Every window is non-empty prose; no window is empty.
    assert all(w.strip() for w in windows)
    # No content lost: every paragraph's marker text appears in some window.
    joined = "\n".join(windows)
    for i in range(6):
        assert ("Paragraph number %d." % i) in joined


def test_plan_windows_single_window_when_it_fits():
    paras = [_para("Short paragraph %d." % i) for i in range(3)]
    chapter = {"body": {"content": paras}}
    text = "\n\n".join(p["content"][0]["text"] for p in paras)
    windows = _plan_chapter_windows(chapter, text, context_window=40000, source_language="en")
    assert len(windows) == 1


def test_plan_windows_fallback_when_no_blocks():
    # Legacy text_content (no Tiptap body) → a single window = the whole text.
    chapter = {"text_content": "Some legacy plain text."}
    windows = _plan_chapter_windows(chapter, "Some legacy plain text.", context_window=4096, source_language="en")
    assert windows == ["Some legacy plain text."]


def test_merge_window_entities_dedups_and_unions_links():
    ents = [
        {"kind": "character", "name": "Count Dracula",
         "chapter_links": [{"chapter_id": "c1"}]},
        {"kind": "character", "name": "count dracula",  # same entity, other window
         "chapter_links": [{"chapter_id": "c2"}]},
        {"kind": "location", "name": "Castle Dracula",
         "chapter_links": [{"chapter_id": "c1"}]},
    ]
    merged = _merge_window_entities(ents)
    assert len(merged) == 2  # the two Draculas collapse to one
    dracula = next(e for e in merged if e["kind"] == "character")
    link_ids = {l["chapter_id"] for l in dracula["chapter_links"]}
    assert link_ids == {"c1", "c2"}  # links unioned across windows


def test_merge_window_entities_skips_nameless():
    merged = _merge_window_entities([{"kind": "character", "name": "  "}])
    assert merged == []


def test_estimate_cost_scales_with_reasoning_effort():
    # D-RE-EFFORT-COST-ESTIMATE: a higher reasoning_effort reserves MORE output
    # (hidden reasoning tokens the entity JSON estimate alone misses), so the quote
    # grows monotonically; 'none' is the baseline and an omitted arg == 'none'.
    from app.workers.extraction_prompt import estimate_extraction_cost

    profile = {"character": {"name": "fill", "role": "fill"}}
    kinds = [{"code": "character", "attributes": [{"code": "name"}, {"code": "role"}]}]
    chapters = [{"text_length": 8000}]

    none_est = estimate_extraction_cost(chapters, profile, kinds, reasoning_effort="none")
    low = estimate_extraction_cost(chapters, profile, kinds, reasoning_effort="low")
    high = estimate_extraction_cost(chapters, profile, kinds, reasoning_effort="high")
    default = estimate_extraction_cost(chapters, profile, kinds)  # omitted == none

    assert default["estimated_output_tokens"] == none_est["estimated_output_tokens"]
    assert low["estimated_output_tokens"] > none_est["estimated_output_tokens"]
    assert high["estimated_output_tokens"] > low["estimated_output_tokens"]
    # Effort grows the OUTPUT reservation; input is essentially unaffected (main's
    # planner-based estimate has a ≤ few-token rounding variance as the output
    # reservation feeds the per-call budget → window count → prompt overhead).
    assert abs(high["estimated_input_tokens"] - none_est["estimated_input_tokens"]) <= 5
    # An unknown/garbage effort degrades to the baseline (defensive .get).
    assert estimate_extraction_cost(chapters, profile, kinds, reasoning_effort="bogus")[
        "estimated_output_tokens"
    ] == none_est["estimated_output_tokens"]


def test_estimate_cost_scales_effort_once_not_twice():
    """/review-impl: estimate_extraction_cost used to apply reasoning-effort output
    scaling TWICE on the planner path — this file's own _EFFORT_OUTPUT_MULTIPLIER
    table (none/off=1.0, low=1.5, medium=2.5, high=4.0) computed `output_per_call`,
    then planner.py's SEPARATE table (none=1.0, low=1.3, medium=1.8, high=2.5) scaled
    that already-scaled value AGAIN. For 'high' that compounded to 2000*4.0*2.5=20,000
    instead of the intended single 2000*4.0=8,000. The sibling test above only asserts
    monotonic growth (high > low > none), which a compounded value also satisfies —
    this pins the actual expected magnitude so a re-introduced double-scale is caught."""
    from app.workers.extraction_prompt import estimate_extraction_cost

    profile = {"character": {"name": "fill", "role": "fill"}}
    kinds = [{"code": "character", "attributes": [{"code": "name"}, {"code": "role"}]}]
    chapters = [{"text_length": 8000}]  # one chapter, one kind batch

    # Splitting (driven by the input budget here) preserves the SUM of est_output
    # modulo small integer-rounding growth from math.ceil on each sub-unit — allow a
    # tolerance well under the ~2.5x a reintroduced double-scale would produce.
    for effort, base in (("none", 2000), ("low", 3000), ("medium", 5000), ("high", 8000)):
        out = estimate_extraction_cost(chapters, profile, kinds, reasoning_effort=effort)
        assert base <= out["estimated_output_tokens"] <= base + 10, (
            f"{effort}: expected ~{base}, got {out['estimated_output_tokens']} "
            "(double-scaling regression?)"
        )
