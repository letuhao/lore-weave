"""Context-trace CONTRACT guard (spec §11a / §13b) — the Inspector's per-turn telemetry.

The Context Compiler · Trace Inspector (spec §11) reads the persisted per-turn contextBudget
frame. That frame doubles as the **compiler telemetry contract**: if the compiler forgets to
emit a field (raw_tokens, the trace spans, status_flags, …), the Inspector silently renders a
blank — the same silent-drift class the frontend-tool contract guards against. So this test:

  1. Snapshots the required frame fields + the TraceSpan shape into a committed
     `contracts/context-trace.contract.json` (regen with WRITE_CONTEXT_TRACE_CONTRACT=1).
  2. Builds a frame through the REAL emit function (`context_budget_event`) + the REAL derive
     helpers on a normal fresh-assembly turn, and asserts EVERY contract field is present AND
     non-null (a forgotten field → red, not a runtime blank). This mirrors
     `test_frontend_tools_contract.py` — do NOT hand-roll a parallel mechanism.

The "runs a REAL turn on the live stack and asserts each field non-null" GATE (§13b) is the
sibling script `scripts/context-inspector-trace-gate.py`; this is the fast unit half.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from loreweave_context import TraceAccumulator, reduction_pct
from loreweave_context.trace import TraceSpan

from app.services.token_budget import (
    BREAKDOWN_CATEGORIES,
    ContextBreakdown,
    compute_budget,
    context_budget_event,
    derive_intent,
    derive_status_flags,
)

# ── the frozen contract ───────────────────────────────────────────────────────
# Required frame fields on a fresh-assembly turn (the Inspector reads each). Legacy
# W1 keys (used_tokens/context_length/…) stay too, but THESE are the §11a Inspector
# telemetry the FE cannot render without.
REQUIRED_FRAME_FIELDS: list[str] = [
    "used_tokens",        # compiled tokens actually sent
    "context_length",     # model window (ceiling)
    "target",             # task-elastic soft budget
    "raw_tokens",         # naive-concat baseline (compiled + Σ savings)
    "reduction_pct",      # raw → compiled
    "breakdown",          # the allocation map (per-category tokens)
    "baseline_tokens",    # fixed per-turn overhead
    "entity_presence",    # T5 gate decision (why grounding was/wasn't pulled)
    "status_flags",       # gated/included/compacted/elastic/overflow/wire chips
    "retrieval_mode",     # prepend/hybrid/pull (sealed #1)
    "intent",             # coarse turn-intent label
    "trace",              # ordered compile-trace spans (the waterfall)
    "until_compact_pct",  # headroom to the compaction trigger
]

# The TraceSpan shape (each span in `trace[]`). Drift on either side → red.
REQUIRED_SPAN_FIELDS: list[str] = [
    "phase", "tier", "category", "action", "delta", "is_error",
]

_CONTRACT_PATH = (
    Path(__file__).resolve().parents[3] / "contracts" / "context-trace.contract.json"
)


def _build_contract() -> dict:
    return {
        "frame_fields": sorted(REQUIRED_FRAME_FIELDS),
        "trace_span_fields": sorted(REQUIRED_SPAN_FIELDS),
        # T2 LOW-2: the authoritative allocation-map category VOCABULARY (ordered, BE is
        # SoT). The Inspector FE (ContextBreakdownPanel.BREAKDOWN_CATEGORIES) must render
        # exactly this set — a FE⊆BE/BE⊆FE parity test on both sides keys off it, so a
        # category added to one side without the other reds (the `story_state`-dropped
        # class: added to the emit dict but not the tuple → to_payload silently omits it).
        "breakdown_categories": list(BREAKDOWN_CATEGORIES),
    }


def _normal_fresh_frame() -> dict:
    """A frame built exactly the way `_emit_chat_turn` builds it on a normal fresh turn
    (known-context model, T5 gate ran + gated, C_persist compaction fired, T0 wire saved).
    Exercises the REAL emit function + derive helpers — not a hand-written dict."""
    entity_presence = {
        "grounding_needed": False,
        "matched": [],
        "reason": "no_entity_no_anaphora",
    }
    trace = TraceAccumulator()
    trace.add("compiler", "T6", "summary", "C_persist: summarized 14 earlier msgs", delta=-9800)
    trace.add("compiler", "T0", "results", "wire hygiene: ensure_ascii=false + drop nulls", delta=-1600)
    trace_payload = trace.to_payload()
    breakdown = ContextBreakdown(
        categories={"system_prompt": 1200, "history": 4100, "tool_results": 3000},
        knowledge_sections={},
    )
    used = 18400
    return context_budget_event(
        compute_budget(used_tokens=used, context_length=131072, max_output_tokens=2048),
        breakdown,
        entity_presence=entity_presence,
        trace=trace_payload,
        raw_tokens=used + trace.saved(),
        status_flags=derive_status_flags(
            grounding_needed=entity_presence["grounding_needed"],
            compacted=True, elastic=False, overflowed=False, wire=True,
        ),
        retrieval_mode="prepend",
        intent=derive_intent(entity_presence),
    )


class TestContextTraceContract:
    def test_contract_json_matches_the_declared_fields(self):
        built = _build_contract()
        if os.environ.get("WRITE_CONTEXT_TRACE_CONTRACT") == "1":
            _CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CONTRACT_PATH.write_text(
                json.dumps(built, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            import pytest
            pytest.skip("regenerated contracts/context-trace.contract.json")
        assert _CONTRACT_PATH.exists(), (
            "contracts/context-trace.contract.json missing — generate with "
            "WRITE_CONTEXT_TRACE_CONTRACT=1 pytest tests/test_context_trace_contract.py"
        )
        on_disk = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
        assert on_disk == built, (
            "context-trace frame fields drifted from the committed contract — regenerate "
            "with WRITE_CONTEXT_TRACE_CONTRACT=1 and update the Inspector FE"
        )

    def test_fresh_frame_carries_every_required_field_non_null(self):
        # THE conformance check: a real emitted frame has every Inspector field present
        # AND non-null. A field the compiler forgot to emit → this reds (not a blank panel).
        frame = _normal_fresh_frame()
        for field in REQUIRED_FRAME_FIELDS:
            assert field in frame, f"frame is missing required field {field!r}"
            assert frame[field] is not None, f"frame field {field!r} is null on a fresh turn"

    def test_trace_spans_are_wire_standard(self):
        frame = _normal_fresh_frame()
        spans = frame["trace"]
        assert isinstance(spans, list) and spans, "trace must be a non-empty list on this turn"
        for span in spans:
            for key in REQUIRED_SPAN_FIELDS:
                assert key in span, f"trace span missing {key!r}"
            assert span["phase"] in ("planner", "compiler")
            assert span["tier"] in ("T0", "T1", "T2", "T3", "T4", "T5", "T6")
            assert isinstance(span["delta"], int)
            assert isinstance(span["is_error"], bool)

    def test_raw_tokens_reconstructs_from_compiled_plus_savings(self):
        # The honesty invariant: raw = compiled + Σ|saved deltas|. reduction_pct agrees.
        frame = _normal_fresh_frame()
        saved = sum(-s["delta"] for s in frame["trace"] if s["delta"] < 0)
        assert frame["raw_tokens"] == frame["used_tokens"] + saved
        assert frame["reduction_pct"] == reduction_pct(frame["raw_tokens"], frame["used_tokens"])


class TestTraceAccumulator:
    def test_saved_sums_only_negative_deltas(self):
        acc = TraceAccumulator()
        acc.add("compiler", "T6", "history", "compacted", delta=-5000)
        acc.add("planner", "T5", "grounding", "included", delta=+3200)  # not a saving
        acc.add("compiler", "T0", "results", "wire", delta=-800)
        assert acc.saved() == 5800
        assert len(acc.spans) == 3

    def test_reduction_pct_edges(self):
        assert reduction_pct(0, 0) is None
        assert reduction_pct(-1, 5) is None
        assert reduction_pct(100, 100) == 0.0           # nothing cut → honest 0, not None
        assert reduction_pct(100, 40) == 0.6

    def test_span_payload_shape(self):
        span = TraceSpan("compiler", "T0", "results", "wire hygiene", delta=-800, is_error=False)
        p = span.to_payload()
        assert p == {
            "phase": "compiler", "tier": "T0", "category": "results",
            "action": "wire hygiene", "delta": -800, "is_error": False,
        }


class TestDeriveHelpers:
    def test_intent_maps_known_reasons(self):
        assert derive_intent({"reason": "entity_match"}) == "lore-lookup"
        assert derive_intent({"reason": "no_entity_no_anaphora"}) == "status-op"
        assert derive_intent({"reason": "meta_question"}) == "meta"
        assert derive_intent({"reason": "totally_unknown"}) == "general"  # never invented
        assert derive_intent(None) == "general"

    def test_status_flags_included_vs_gated_mutually_exclusive(self):
        assert derive_status_flags(grounding_needed=True) == ["included"]
        assert derive_status_flags(grounding_needed=False) == ["gated"]
        # gate didn't run → neither chip
        assert derive_status_flags(grounding_needed=None) == []

    def test_status_flags_full_set_stable_order(self):
        flags = derive_status_flags(
            grounding_needed=False, compacted=True, elastic=True, overflowed=True, wire=True,
        )
        assert flags == ["gated", "compacted", "elastic", "overflow", "wire"]
