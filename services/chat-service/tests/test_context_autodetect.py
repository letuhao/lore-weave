"""D-LONG-WORK-CONTEXT-MODE — auto-detect decision truth table."""

from app.services.context_autodetect import (
    GLOSSARY_LARGE,
    HISTORY_FRACTION,
    resolve_context_pressure,
)

WINDOW = 100_000


def test_mode_off_never_allows():
    r = resolve_context_pressure("off", window=WINDOW, history_tokens=90_000, glossary_size=9999)
    assert r.tiers_allowed is False
    assert r.reason == "user_off" and r.source == "user"


def test_mode_on_always_allows():
    r = resolve_context_pressure("on", window=WINDOW, history_tokens=0, glossary_size=0)
    assert r.tiers_allowed is True
    assert r.reason == "user_on" and r.source == "user"


def test_auto_small_book_short_chat_stays_off():
    # The common case: tiny history, small glossary → tiers OFF (identical to
    # today's default; keeps the existing small-context suite green).
    r = resolve_context_pressure("auto", window=WINDOW, history_tokens=2_000, glossary_size=20)
    assert r.tiers_allowed is False
    assert r.reason == "auto_below_threshold"


# NOTE: the history-pressure arm below is HELPER-GENERAL but currently UNWIRED in
# the live gate — `stream_response` passes history_tokens=0 (the gate runs before
# history assembly), so long-conversation pressure is handled by adaptive
# compaction, not this arm. These tests pin the helper contract for a future
# caller that supplies history; they do NOT prove long-chat enables tiers in prod.
def test_auto_long_conversation_trips_on_history():
    r = resolve_context_pressure("auto", window=WINDOW, history_tokens=70_000, glossary_size=10)
    assert r.tiers_allowed is True
    assert r.reason == "auto_history"
    assert r.pressure == 0.7


def test_auto_huge_book_short_chat_trips_on_glossary():
    # The user's headline case: a fresh chat (short history) about a 4000-chapter
    # book — history pressure is ~0 but the glossary is huge → tiers ON.
    r = resolve_context_pressure("auto", window=WINDOW, history_tokens=500, glossary_size=1200)
    assert r.tiers_allowed is True
    assert r.reason == "auto_glossary"


def test_auto_both_signals():
    r = resolve_context_pressure("auto", window=WINDOW, history_tokens=80_000, glossary_size=1000)
    assert r.tiers_allowed is True
    assert r.reason == "auto_history+glossary"


def test_auto_at_exact_thresholds_trips_biased_to_include():
    r = resolve_context_pressure(
        "auto", window=WINDOW,
        history_tokens=int(WINDOW * HISTORY_FRACTION), glossary_size=GLOSSARY_LARGE,
    )
    assert r.tiers_allowed is True


def test_auto_unknown_window_falls_back_to_glossary_only():
    # No window ⇒ history fraction can't be computed; the glossary signal still works.
    off = resolve_context_pressure("auto", window=None, history_tokens=10**9, glossary_size=10)
    assert off.tiers_allowed is False
    on = resolve_context_pressure("auto", window=0, history_tokens=0, glossary_size=GLOSSARY_LARGE)
    assert on.tiers_allowed is True


def test_unrecognized_mode_treated_as_auto():
    r = resolve_context_pressure("banana", window=WINDOW, history_tokens=90_000, glossary_size=0)
    assert r.tiers_allowed is True and r.source == "auto"
