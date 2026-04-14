"""K18.2a unit tests — query intent classifier.

Acceptance:
  - >= 0.80 accuracy on the 50-query golden fixture
  - Per-class accuracy >= 0.60 (so no class is abandoned to reach 0.80)
  - p95 latency < 15ms on short messages
  - Deterministic on re-run
  - Empty input -> GENERAL, never crashes
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from app.context.intent import Intent, IntentResult, classify


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "intent_queries.yaml"


@pytest.fixture(scope="module")
def golden_queries() -> list[tuple[str, Intent]]:
    raw = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    out: list[tuple[str, Intent]] = []
    for label, queries in raw.items():
        intent = Intent(label)
        for q in queries:
            out.append((q, intent))
    return out


# ── edge cases ────────────────────────────────────────────────────────


def test_empty_message_is_general():
    r = classify("")
    assert r.intent is Intent.GENERAL
    assert r.entities == ()
    assert r.hop_count == 1
    assert r.recency_weight == 1.0


def test_whitespace_only_is_general():
    assert classify("   \n\t ").intent is Intent.GENERAL


def test_deterministic():
    a = classify("How does Kai know Master Lin?")
    b = classify("How does Kai know Master Lin?")
    assert a == b


# ── class-specific anchors ────────────────────────────────────────────


def test_relational_two_entities_plus_keyword():
    r = classify("How does Kai know Master Lin?")
    assert r.intent is Intent.RELATIONAL
    assert r.hop_count == 2
    assert "Kai" in r.entities
    assert "Master Lin" in r.entities


def test_relational_strong_phrasing_with_one_entity():
    # "Who knows Kai?" — strong phrasing is enough, second entity implied.
    r = classify("Who knows Kai?")
    assert r.intent is Intent.RELATIONAL


def test_specific_entity_not_confused_by_know_verb():
    # L-CH-07 trap: "What does Kai know?" should stay SPECIFIC_ENTITY,
    # not RELATIONAL — only 1 entity.
    r = classify("What does Kai know?")
    assert r.intent is Intent.SPECIFIC_ENTITY
    assert r.entities == ("Kai",)


def test_historical_strong_wins_over_entity():
    # "Long ago" overrides any entity presence.
    r = classify("Long ago, what did Master Lin do?")
    assert r.intent is Intent.HISTORICAL
    assert r.recency_weight == -1.0
    assert "Master Lin" in r.entities  # still extracted, just not winning


def test_historical_weak_with_entity_stays_specific():
    # "before the battle" + "Kai" present → specific entity, not historical.
    # Design decision: weak temporal anchors yield to specific entity.
    r = classify("What did Kai do before the battle?")
    assert r.intent is Intent.SPECIFIC_ENTITY
    assert r.entities == ("Kai",)


def test_historical_weak_without_entity_is_historical():
    r = classify("Before the fall, who ruled?")
    assert r.intent is Intent.HISTORICAL


def test_recent_event_boosts_recency():
    r = classify("What is Kai doing right now?")
    assert r.intent is Intent.RECENT_EVENT
    assert r.recency_weight == 2.0


def test_specific_entity_single_name():
    r = classify("Tell me about Kai")
    assert r.intent is Intent.SPECIFIC_ENTITY
    assert r.entities == ("Kai",)
    assert r.hop_count == 1


def test_general_fallback():
    r = classify("What is love?")
    assert r.intent is Intent.GENERAL


# ── golden-set accuracy (the real bar) ────────────────────────────────


def test_golden_set_accuracy(golden_queries):
    correct = 0
    failures: list[tuple[str, Intent, Intent]] = []
    for query, expected in golden_queries:
        got = classify(query).intent
        if got is expected:
            correct += 1
        else:
            failures.append((query, expected, got))

    total = len(golden_queries)
    accuracy = correct / total
    # Print failures on assertion failure for fast debugging.
    msg = f"\nAccuracy: {accuracy:.2%} ({correct}/{total})\nFailures:\n"
    for q, exp, got in failures:
        msg += f"  [{exp.value:18s} -> {got.value:18s}]  {q}\n"
    assert accuracy >= 0.80, msg


def test_per_class_accuracy(golden_queries):
    """No class abandoned to reach overall 0.80 — each class >= 0.60."""
    per_class: dict[Intent, list[bool]] = {}
    for query, expected in golden_queries:
        got = classify(query).intent
        per_class.setdefault(expected, []).append(got is expected)

    failures: list[str] = []
    for intent, results in per_class.items():
        acc = sum(results) / len(results)
        if acc < 0.60:
            failures.append(f"{intent.value}: {acc:.2%} ({sum(results)}/{len(results)})")
    assert not failures, "Per-class accuracy below 0.60:\n" + "\n".join(failures)


# ── latency ───────────────────────────────────────────────────────────


def test_latency_p95_under_15ms(golden_queries):
    """p95 < 15ms on golden set. No LLM, pure regex + extract_candidates."""
    # Warm up — first call imports any lazy modules.
    for q, _ in golden_queries[:5]:
        classify(q)

    timings: list[float] = []
    for _ in range(20):  # 20 * 50 = 1000 samples
        for q, _ in golden_queries:
            t0 = time.perf_counter()
            classify(q)
            timings.append((time.perf_counter() - t0) * 1000.0)  # ms

    timings.sort()
    p95 = timings[int(len(timings) * 0.95)]
    assert p95 < 15.0, f"p95 latency {p95:.2f}ms exceeds 15ms budget"


# ── signals / debuggability ───────────────────────────────────────────


def test_long_input_still_classifies_under_budget():
    # R8 regression: a pathological 10k-char message must not blow the
    # latency budget. Priority cascade uses simple regex scans; no
    # quadratic behavior expected, but assert it.
    msg = "Tell me about Kai " + ("and his sword " * 1000) + " please."
    t0 = time.perf_counter()
    r = classify(msg)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 15.0, f"Long-input latency {elapsed_ms:.2f}ms exceeds budget"
    assert r.intent is Intent.SPECIFIC_ENTITY
    assert "Kai" in r.entities


def test_signals_record_all_hits_not_just_winner():
    # "Who knows Kai right now?" — relational_strong wins, but `right now`
    # should still appear in signals for debuggability (L-CH-08).
    r = classify("Who knows Kai right now?")
    assert r.intent is Intent.RELATIONAL
    joined = " ".join(r.signals)
    assert "relational_strong" in joined
    assert "recent" in joined
