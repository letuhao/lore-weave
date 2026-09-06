"""A work of fiction's proper noun must not open the world-setup gate.

🔴 MEASURED 2026-08-23 over 186 distinct corpus prompts. `_WORLD_SETUP_MARKERS` held "codex", and
it fired exactly twice — both on a chapter TITLE, never on a setup request:

    'Write chapter — use the cowrite engine to draft the prose for "Chapter I — The Ember Codex".'
    'Rename the chapter called The Ember Codex in my outline to The Ember Codex, Revised.'

Opening the gate injects `glossary_shaping` and un-gates all five INTENT_GATED_SETUP_TOOLS. That is
the precise over-reach the gate exists to stop — tool_discovery records that keeping those tools
advertised "made the co-writer rebuild a newcomer's ontology on a plain write-a-chapter turn" — and
the guard's own keyword was letting it through whenever a chapter was NAMED a codex.
"""
from app.services.skill_registry import _WORLD_SETUP_MARKERS, _is_world_setup_intent


def test_a_chapter_titled_the_ember_codex_is_not_world_setup():
    assert not _is_world_setup_intent(
        'Write chapter — use the cowrite engine to draft the prose for "Chapter I — The Ember Codex".')
    assert not _is_world_setup_intent(
        "Rename the chapter called The Ember Codex in my outline to The Ember Codex, Revised.")


def test_codex_is_not_a_marker():
    """Pinned by name: it is a proper noun as often as a concept, and it earned 0 recall."""
    assert "codex" not in _WORLD_SETUP_MARKERS


def test_the_real_setup_phrasings_still_open_it():
    """Removing a marker must not cost the recall the list is FOR."""
    for q in ("Set up several kinds and attributes at once for this book's ontology.",
              "Plan my ontology for this book — how should I structure the world?",
              "Adopt standard kinds for this book.",
              "Help me with worldbuilding for this book.",
              "Let's set up the world for this book."):
        assert _is_world_setup_intent(q), q
