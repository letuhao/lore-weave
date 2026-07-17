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


# ── A1 (ML-1): per-language routing supersedes the P0-7 blanket degrade ──


def test_chinese_relational_routes_via_keyword_not_degrade():
    # Post-A1: a zh relational query matches its OWN vocabulary (是什么关系) and
    # routes RELATIONAL through the real cascade — no longer the blanket net.
    r = classify("凯和林大师之间是什么关系？")  # relationship between Kai and Master Lin
    assert r.intent is Intent.RELATIONAL
    assert r.hop_count == 2
    assert "multilingual_degrade_open" not in r.signals  # a REAL signal won
    assert any(s.startswith("relational") for s in r.signals)


def test_vietnamese_recent_routes_via_keyword_not_degrade():
    # Post-A1: "chương này" (this chapter) is a Vietnamese RECENT anchor, so this
    # routes RECENT_EVENT — real routing, not the pre-A1 blanket RELATIONAL.
    r = classify("Chuyện gì đã xảy ra ở chương này?")  # what happened in this chapter
    assert r.intent is Intent.RECENT_EVENT
    assert "multilingual_degrade_open" not in r.signals


def test_english_general_unchanged_by_degrade_open():
    # Pure-ASCII English never enters the degrade-open branch — byte-identical.
    r = classify("What is love?")
    assert r.intent is Intent.GENERAL
    assert r.hop_count == 1
    assert r.recency_weight == 1.0
    assert "multilingual_degrade_open" not in r.signals


def test_english_with_punctuation_dash_not_treated_as_non_english():
    # A non-ASCII em-dash / ellipsis is PUNCTUATION, not a letter — must NOT
    # trip the multilingual rule; this stays GENERAL.
    r = classify("What is love — really…?")
    assert r.intent is Intent.GENERAL
    assert "multilingual_degrade_open" not in r.signals


def test_english_cascade_still_wins_for_ascii_queries():
    # Degrade-open must not shadow the English cascade. A clear English
    # relational/recent query keeps its normal routing.
    assert classify("How does Kai know Master Lin?").intent is Intent.RELATIONAL
    assert classify("What is Kai doing right now?").intent is Intent.RECENT_EVENT


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


def test_long_input_still_classifies_without_quadratic_blowup():
    # R8 regression: a pathological 10k-char message must not blow up the
    # classifier. The property under test is ALGORITHMIC — the priority
    # cascade is simple regex scans, so cost must grow ~linearly with input.
    #
    # This deliberately asserts a SCALING RATIO, not an absolute wall-clock
    # budget. An absolute `elapsed < 15ms` on one sample measures the machine,
    # not the code: it false-REDs whenever the CPU is contended (this suite's
    # own `-n auto` workers, a parallel vitest run, a busy CI box) while a real
    # quadratic regression on a fast box could still sneak under it. Doubling
    # the input must roughly double the work (linear ≈ 2x, quadratic ≈ 4x);
    # both samples absorb the same contention, so the ratio stays meaningful.
    def median_ms(msg: str, runs: int = 7) -> float:
        samples = []
        for _ in range(runs):
            t0 = time.perf_counter()
            classify(msg)
            samples.append((time.perf_counter() - t0) * 1000.0)
        return sorted(samples)[len(samples) // 2]

    def message(repeats: int) -> str:
        return "Tell me about Kai " + ("and his sword " * repeats) + " please."

    classify(message(50))  # warm up any lazy imports / regex compilation

    half = median_ms(message(500))    # ~7k chars
    full = median_ms(message(1000))   # ~14k chars — double the input

    # Guard against a degenerate baseline: if `half` rounds to ~0 the ratio is
    # noise, and a sub-millisecond 14k-char classify is proof enough of linearity.
    if half > 0.05:
        ratio = full / half
        assert ratio < 3.0, (
            f"classify() scales super-linearly: {half:.3f}ms at 7k chars vs "
            f"{full:.3f}ms at 14k chars (ratio {ratio:.2f}x, expected ~2x for a "
            f"linear scan; ~4x indicates quadratic backtracking)"
        )

    r = classify(message(1000))
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


# ── A1 (ML-1) — per-language routing ──────────────────────────────────


@pytest.fixture(scope="module")
def multilingual_queries() -> list[tuple[str, Intent]]:
    path = Path(__file__).parent / "fixtures" / "intent_queries_multilingual.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: list[tuple[str, Intent]] = []
    for label, queries in raw.items():
        intent = Intent(label)
        for q in queries:
            out.append((q, intent))
    return out


def test_multilingual_queries_route_to_real_intent(multilingual_queries):
    """zh/ja/ko/vi queries route to their correct intent via per-language
    keywords — NOT the old blanket-RELATIONAL degrade. Requires 100% here
    (a small hand-verified set), and specifically that non-relational cases
    are NOT swept into RELATIONAL."""
    misses = []
    for q, expected in multilingual_queries:
        got = classify(q).intent
        if got is not expected:
            misses.append((q, expected.value, got.value))
    assert not misses, f"multilingual routing misses: {misses}"


def test_non_relational_multilingual_not_swept_to_relational(multilingual_queries):
    # The whole point of A1: a CJK/vi query that isn't relational must not be
    # blanket-routed to RELATIONAL (the pre-A1 degrade behavior).
    for q, expected in multilingual_queries:
        if expected is not Intent.RELATIONAL:
            assert classify(q).intent is not Intent.RELATIONAL, (
                f"{q!r} (expected {expected.value}) was swept to RELATIONAL"
            )


def test_english_routing_byte_identical_after_multilingual_union():
    # Union-compiling the CJK/vi keywords must not change English outcomes
    # (disjoint scripts). Spot-check one per class.
    assert classify("Tell me about Kai").intent is Intent.SPECIFIC_ENTITY
    assert classify("What just happened to Kai?").intent is Intent.RECENT_EVENT
    assert classify("Long ago, who ruled?").intent is Intent.HISTORICAL
    assert classify("How does Kai know Master Lin?").intent is Intent.RELATIONAL


def test_uncovered_script_degrades_open_to_relational():
    # An uncovered non-ASCII script (Arabic) with no keyword + no entity still
    # degrades OPEN to RELATIONAL/2-hop (the retained net), not narrow GENERAL.
    r = classify("مرحبا بالعالم")
    assert r.intent is Intent.RELATIONAL
    assert r.hop_count == 2
    assert "multilingual_degrade_open" in r.signals


def test_english_no_signal_stays_general_not_degraded():
    # Pure-ASCII with no signal must stay GENERAL (never enters the net).
    r = classify("the weather is nice today and everything feels calm")
    assert r.intent is Intent.GENERAL
    assert "multilingual_degrade_open" not in r.signals
