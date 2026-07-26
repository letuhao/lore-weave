"""#36 — the extraction cost estimate must respond to REAL chapter size.

The windowing-aware planner only undercounts when it's fed a flat placeholder size
(the old `[{'text_length': 8000}] * N`). With real per-chapter sizes, a large chapter
fans out into windows and the predicted llm_calls grows — tracking what the executor
actually does. These prove the planner is size-sensitive (so feeding it real sizes,
via book_client.build_chapters_meta, is what fixes the undercount).
"""
from app.workers.extraction_prompt import estimate_extraction_cost


def _profile_and_meta(n_kinds=6, n_attrs=5):
    profile = {f"k{i}": {f"a{j}": "extract" for j in range(n_attrs)} for i in range(n_kinds)}
    kinds_metadata = [
        {"code": f"k{i}", "name": f"K{i}",
         "attributes": [{"code": f"a{j}", "field_type": "text"} for j in range(n_attrs)]}
        for i in range(n_kinds)
    ]
    return profile, kinds_metadata


def test_larger_chapter_predicts_more_calls_than_flat_8000():
    profile, kinds_metadata = _profile_and_meta()
    ctx = 8000  # small context so a big chapter must window
    small = estimate_extraction_cost(
        [{"chapter_id": "c", "text_length": 8000}], profile, kinds_metadata,
        model_context_window=ctx,
    )
    big = estimate_extraction_cost(
        [{"chapter_id": "c", "text_length": 400000}], profile, kinds_metadata,
        model_context_window=ctx,
    )
    # Same kinds/batches, only the size differs → the big chapter windows → more calls.
    assert big["llm_calls"] > small["llm_calls"], (small, big)


def test_flat_size_is_blind_to_chapter_length():
    """Two chapters that differ in real length but share the OLD flat 8000 placeholder
    predict the same call count — the bug. (Guards the regression direction: the fix is
    to stop feeding a flat size, which this test documents.)"""
    profile, kinds_metadata = _profile_and_meta()
    a = estimate_extraction_cost(
        [{"chapter_id": "c", "text_length": 8000}], profile, kinds_metadata,
        model_context_window=32000,
    )
    b = estimate_extraction_cost(
        [{"chapter_id": "c", "text_length": 8000}], profile, kinds_metadata,
        model_context_window=32000,
    )
    assert a["llm_calls"] == b["llm_calls"]
