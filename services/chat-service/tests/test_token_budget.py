"""Wave A1/A2 — script-aware token estimate + context budget.
Wave W1 — per-category context breakdown + the extended contextBudget payload."""
from __future__ import annotations

from app.services.compaction import COMPACT_TRIGGER_RATIO
from app.services.token_budget import (
    BREAKDOWN_CATEGORIES,
    ContextBreakdown,
    compute_budget,
    context_budget_event,
    estimate_messages_tokens,
    estimate_tokens,
    until_compact_pct,
)


class TestScriptAwareEstimate:
    def test_english_is_roughly_chars_over_four(self):
        text = "the quick brown fox jumps over the lazy dog" * 4  # ~172 chars ASCII
        est = estimate_tokens(text)
        # ~chars/4 band (the classic English heuristic still holds for Latin).
        assert 0.2 * len(text) <= est <= 0.35 * len(text)

    def test_chinese_is_NOT_chars_over_four(self):
        # 万古神帝 — Chinese tokenizes ~1 token/char; chars/4 would 4x under-count.
        text = "万古神帝魔女逆天诸天神魔仙侠世界" * 5  # ~80 Han chars
        est = estimate_tokens(text)
        flat_chars_over_4 = len(text) // 4
        assert est >= 0.8 * len(text)          # ~1 token/char, not chars/4
        assert est > 3 * flat_chars_over_4     # decisively above the broken heuristic

    def test_vietnamese_denser_than_plain_english(self):
        # Vietnamese with diacritics tokenizes denser than the same-length English.
        vi = "Ma Nữ Nghịch Thiên — nàng tiểu thư bị phản bội, tái sinh với ma công nghịch thiên"
        en_same_len = "x" * len(vi)
        assert estimate_tokens(vi) > estimate_tokens(en_same_len)

    def test_empty_and_none(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens(None) == 0

    def test_messages_include_overhead(self):
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        assert estimate_messages_tokens(msgs) > 0
        # content-parts form (text blocks) is summed too.
        parts = [{"role": "user", "content": [{"type": "text", "text": "万古神帝"}]}]
        assert estimate_messages_tokens(parts) >= estimate_tokens("万古神帝")

    def test_assistant_tool_calls_args_are_counted(self):
        # a tool-call turn (content=None) carries its weight in the arguments JSON;
        # ignoring it under-counts the resume / tool-loop path.
        big_args = '{"selection": "' + ("x" * 2000) + '"}'
        with_call = [{
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "propose_edit", "arguments": big_args}}],
        }]
        empty = [{"role": "assistant", "content": None}]
        # the big arguments blob must dominate the estimate, not the +4 overhead.
        assert estimate_messages_tokens(with_call) > estimate_messages_tokens(empty) + 100


class TestComputeBudget:
    def test_pct_against_effective_limit(self):
        b = compute_budget(used_tokens=10_000, context_length=40_000, max_output_tokens=4_000)
        # effective = 40000 - 4000 - 512 = 35488; pct = 10000/35488 ≈ 0.2818
        assert b.effective_limit == 40_000 - 4_000 - 512
        assert 0.28 <= (b.pct or 0) <= 0.29
        assert b.to_event()["pct"] is not None

    def test_null_context_length_is_unknown(self):
        b = compute_budget(used_tokens=10_000, context_length=None, max_output_tokens=4_000)
        assert b.pct is None
        assert b.effective_limit is None
        assert b.to_event()["context_length"] is None

    def test_overflowed_pct_exceeds_one(self):
        b = compute_budget(used_tokens=40_000, context_length=40_000, max_output_tokens=4_000)
        assert (b.pct or 0) > 1.0  # over budget → meter goes red


class TestComputeTarget:
    def test_band_for_large_window(self):
        # 200K window: floor = min(6K, 20K) = 6K; surface_max = min(32K, 70K) = 32K.
        from app.services.token_budget import compute_target

        assert compute_target(200_000, task_weight=0.0) == 6_000       # floor
        assert compute_target(200_000, task_weight=1.0) == 32_000      # surface_max
        mid = compute_target(200_000, task_weight=0.5)
        assert 6_000 < mid < 32_000

    def test_band_scales_with_small_window(self):
        # 20K window: floor = min(6K, 2K) = 2K; surface_max = min(32K, 7K) = 7K.
        from app.services.token_budget import compute_target

        assert compute_target(20_000, task_weight=0.0) == 2_000
        assert compute_target(20_000, task_weight=1.0) == 7_000

    def test_task_weight_clamped(self):
        from app.services.token_budget import compute_target

        assert compute_target(200_000, task_weight=5.0) == 32_000   # >1 clamps to max
        assert compute_target(200_000, task_weight=-1.0) == 6_000   # <0 clamps to floor

    def test_unknown_window_is_none(self):
        from app.services.token_budget import compute_target

        assert compute_target(None) is None
        assert compute_target(0) is None

    def test_nan_task_weight_fails_safe_roomy(self):
        # T2 review COSMETIC-2: a Planner NaN must fail SAFE = surface_max (roomy),
        # never be silently masked as "lean" (floor) → over-compaction.
        from app.services.token_budget import compute_target

        assert compute_target(200_000, task_weight=float("nan")) == 32_000  # surface_max


class TestBudgetTarget:
    def test_budget_carries_target_and_pct_of_target(self):
        # default task_weight=1.0 → surface_max target.
        b = compute_budget(used_tokens=16_000, context_length=200_000, max_output_tokens=4_000)
        assert b.target == 32_000
        assert b.pct_of_target == 16_000 / 32_000  # 0.5 — half the soft budget
        ev = b.to_event()
        assert ev["target"] == 32_000
        assert 0.49 <= ev["pct_of_target"] <= 0.51

    def test_task_weight_shrinks_target(self):
        lean = compute_budget(
            used_tokens=8_000, context_length=200_000, max_output_tokens=4_000, task_weight=0.0)
        assert lean.target == 6_000
        assert (lean.pct_of_target or 0) > 1.0  # 8K > 6K floor → over the lean target

    def test_unknown_window_target_none(self):
        b = compute_budget(used_tokens=10, context_length=None, max_output_tokens=0)
        assert b.target is None
        assert b.to_event()["target"] is None
        assert b.to_event()["pct_of_target"] is None


# ── W1: per-category breakdown + extended frame payload ───────────────────────


def _full_breakdown() -> ContextBreakdown:
    return ContextBreakdown(
        categories={
            "system_prompt": 100,
            "memory_knowledge": 800,
            "working_memory": 50,
            "steering": 30,
            "skills": 400,
            "plan_nudge": 10,
            "book_note": 20,
            "attached_context": 60,
            "history": 2000,
            "tool_results": 300,
            "frontend_tool_schemas": 250,
            "mcp_tool_schemas": 1500,
        },
        knowledge_sections={"glossary_entities": 500, "facts": 200, "instructions": 100},
    )


class TestContextBreakdown:
    def test_payload_has_every_category_exactly_once(self):
        payload = _full_breakdown().to_payload()
        assert list(payload.keys()) == list(BREAKDOWN_CATEGORIES)

    def test_missing_categories_default_zero(self):
        payload = ContextBreakdown(categories={"history": 7}).to_payload()
        assert payload["history"] == 7
        assert payload["steering"] == 0
        assert payload["memory_knowledge"] == {"total": 0, "sections": {}}

    def test_memory_knowledge_nests_total_and_sections(self):
        payload = _full_breakdown().to_payload()
        assert payload["memory_knowledge"] == {
            "total": 800,
            "sections": {"glossary_entities": 500, "facts": 200, "instructions": 100},
        }

    def test_baseline_is_system_parts_plus_tool_schemas(self):
        bd = _full_breakdown()
        # baseline = everything present before the first user word:
        # system_prompt + memory + wm + steering + skills + plan_nudge +
        # book_note + both tool-schema buckets. NOT history / attached /
        # tool_results (those depend on the user's messages).
        assert bd.baseline_tokens == 100 + 800 + 50 + 30 + 400 + 10 + 20 + 250 + 1500

    def test_totals_consistent_each_category_counted_once(self):
        bd = _full_breakdown()
        payload = bd.to_payload()
        flat_total = sum(
            v["total"] if isinstance(v, dict) else v for v in payload.values()
        )
        assert flat_total == sum(bd.categories.values())
        # sections are the DETAIL of memory_knowledge, not an extra summand.
        assert flat_total < sum(bd.categories.values()) + sum(bd.knowledge_sections.values())


class TestUntilCompactPct:
    def test_reuses_the_compaction_trigger_constant(self):
        # distance = trigger - pct (no duplicated 0.75 literal).
        assert until_compact_pct(0.0) == round(COMPACT_TRIGGER_RATIO, 4)
        assert until_compact_pct(0.5) == round(COMPACT_TRIGGER_RATIO - 0.5, 4)

    def test_clamps_at_zero_past_trigger(self):
        assert until_compact_pct(COMPACT_TRIGGER_RATIO) == 0.0
        assert until_compact_pct(0.99) == 0.0

    def test_none_when_budget_unknown(self):
        assert until_compact_pct(None) is None


class TestContextBudgetEvent:
    def test_old_keys_byte_identical(self):
        b = compute_budget(used_tokens=10_000, context_length=40_000, max_output_tokens=4_000)
        payload = context_budget_event(b, _full_breakdown())
        # the pre-W1 FE meter contract: exact keys, exact values.
        for key, val in b.to_event().items():
            assert payload[key] == val
        assert {"used_tokens", "context_length", "effective_limit", "pct"} <= set(payload)

    def test_additive_keys_present(self):
        b = compute_budget(used_tokens=10_000, context_length=40_000, max_output_tokens=4_000)
        payload = context_budget_event(b, _full_breakdown())
        assert payload["baseline_tokens"] == _full_breakdown().baseline_tokens
        assert payload["until_compact_pct"] == until_compact_pct(b.pct)
        assert payload["breakdown"]["mcp_tool_schemas"] == 1500

    def test_no_breakdown_still_carries_until_compact(self):
        # the resume path has no assembly-time breakdown — old keys +
        # until_compact_pct only, no breakdown/baseline keys at all.
        b = compute_budget(used_tokens=10_000, context_length=40_000, max_output_tokens=4_000)
        payload = context_budget_event(b, None)
        assert "breakdown" not in payload and "baseline_tokens" not in payload
        assert payload["until_compact_pct"] is not None

    def test_unknown_budget_none_fields(self):
        b = compute_budget(used_tokens=10, context_length=None, max_output_tokens=0)
        payload = context_budget_event(b, None)
        assert payload["pct"] is None
        assert payload["until_compact_pct"] is None
