"""D-CACHE-PLANNER-WIRING Part 1 — estimate_extraction_cost is SPLIT-AWARE via the PLAN-lane
planner: a chapter that exceeds the model context fans out to N windows × batches in the
quote (the flat heuristic was windowing-blind). Pure (no Postgres)."""
from app.workers.extraction_prompt import estimate_extraction_cost

_PROFILE = {"character": {"name": "replace"}}
_KINDS = [{"code": "character", "name": "Character", "attributes": [{"code": "name"}]}]


def _chapters(n, text_length):
    return [{"chapter_id": f"c{i}", "text_length": text_length} for i in range(n)]


def test_estimate_keys_and_small_chapters_no_split():
    # Small chapters against a real model context → one call per (chapter × batch), no fan-out.
    res = estimate_extraction_cost(_chapters(3, 4000), _PROFILE, _KINDS,
                                   model_context_window=128_000)
    for k in ("estimated_input_tokens", "estimated_output_tokens", "estimated_total_tokens",
              "llm_calls", "chapters_count", "batches_per_chapter"):
        assert k in res
    assert res["batches_per_chapter"] == 1
    assert res["chapters_count"] == 3
    assert res["llm_calls"] == 3  # 3 chapters × 1 batch, no split
    # Planner path adds these:
    assert res.get("calls_per_chapter") == 1.0
    assert res.get("unplannable") == 0


def test_estimate_splits_oversized_chapter_into_windows():
    # A huge chapter against a small context window must fan out to many window-calls — the
    # whole point of split-awareness (the flat heuristic would report just 1 call).
    big = estimate_extraction_cost(
        _chapters(1, 400_000), _PROFILE, _KINDS, model_context_window=8000)
    assert big["llm_calls"] > 1                      # windowed, not a single call
    assert big["calls_per_chapter"] > 1
    # Pathological fan-out is surfaced, never silently truncated.
    assert big["model_fit_warning"] is not None
    # The split estimate's input ≈ the original chapter input (split divides, doesn't inflate).
    flat = estimate_extraction_cost(_chapters(1, 400_000), _PROFILE, _KINDS,
                                    model_context_window=10_000_000)  # fits → no split
    assert big["estimated_input_tokens"] <= flat["estimated_input_tokens"] * 2


def test_estimate_calls_scale_with_chapters_and_batches():
    one = estimate_extraction_cost(_chapters(1, 4000), _PROFILE, _KINDS,
                                   model_context_window=128_000)["llm_calls"]
    five = estimate_extraction_cost(_chapters(5, 4000), _PROFILE, _KINDS,
                                    model_context_window=128_000)["llm_calls"]
    assert five == one * 5


def test_estimate_output_grows_with_effort():
    # D-RE-EFFORT-COST-ESTIMATE: a reasoning model spends extra output tokens on its thinking
    # trace, so the quote's output must grow none < medium < high.
    def _out(effort):
        return estimate_extraction_cost(_chapters(2, 4000), _PROFILE, _KINDS,
                                        model_context_window=128_000,
                                        reasoning_effort=effort)["estimated_output_tokens"]
    assert _out("none") < _out("medium") < _out("high")


def test_estimate_falls_back_without_planner(monkeypatch):
    # If the planner SDK isn't importable, the estimate degrades to the flat heuristic
    # (windowing-blind) rather than failing — the D-SDK-DISTRIBUTION-SPLIT safety net.
    import builtins
    real_import = builtins.__import__

    def _block_planner(name, *a, **k):
        if name == "loreweave_extraction":
            raise ImportError("simulated SDK-distribution split")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _block_planner)
    res = estimate_extraction_cost(_chapters(2, 4000), _PROFILE, _KINDS)
    assert res["llm_calls"] == 2  # flat: 2 chapters × 1 batch
    assert "calls_per_chapter" not in res  # planner-only key absent in the fallback
