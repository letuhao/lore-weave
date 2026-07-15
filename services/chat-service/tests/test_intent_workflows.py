"""Intent -> workflow pinning: the user's words must pin the rail they describe (M2).

This is the fix for the measured rail-discovery ceiling (S03 0/3, S04 1/3, S09 improvises): a
mid-tier model doesn't reliably DISCOVER a non-pinned rail, so we pin it from the request text the
same way the mode binding pins vision-to-book.
"""
from app.services.intent_workflows import intent_pinned_workflows

ALL = {"entity-triage", "canon-check", "kg-build", "build-a-book", "translation-pass",
       "autonomous-drafting", "vision-to-book"}


def pins(text: str):
    return intent_pinned_workflows(text, ALL)


# ── each ceiling rail is pinned by the exact scenario phrasing that failed to discover it ──
def test_entity_triage_from_the_s03_prompts():
    assert "entity-triage" in pins("Clean up the suggested items in my book.")
    assert "entity-triage" in pins("triage the auto-suggestions — keep the real ones, throw out the junk")
    assert "entity-triage" in pins("'Dracula' and 'Count Dracula' are the same person — combine the duplicates")


def test_canon_check_from_the_s09_prompts():
    assert "canon-check" in pins("Run a consistency check across my whole story and flag anything that contradicts itself.")
    assert "canon-check" in pins("I think I've contradicted myself somewhere — find where.")


def test_kg_build_from_the_s04_prompts():
    assert "kg-build" in pins("Map out how everything connects in my world.")
    assert "kg-build" in pins("build the knowledge graph from my lore")


def test_build_a_book_from_the_s07_prompt():
    assert "build-a-book" in pins("Before I start writing, help me lay out the plan for the entire book — the arc and major beats.")


def test_translation_and_autonomous():
    assert "translation-pass" in pins("translate what needs it so English readers can read it")
    assert "autonomous-drafting" in pins("draft the next few chapters for me while I'm away")


# ── it must NOT over-fire (a false pin is bounded, but avoid it anyway) ────────────────────
def test_a_plain_writing_request_pins_nothing_here():
    # "write my novel" is the mode binding's job (vision-to-book), not an intent match here.
    assert pins("I want to write a novel about a bride who is murdered at her wedding.") == []


def test_empty_and_none():
    assert intent_pinned_workflows("", ALL) == []
    assert intent_pinned_workflows(None, ALL) == []


# ── visibility filter: never pin a rail that isn't visible this turn ───────────────────────
def test_visibility_filter():
    # canon-check phrasing, but only entity-triage is visible ⇒ nothing pinned
    assert intent_pinned_workflows("check my story for contradictions", {"entity-triage"}) == []
    assert intent_pinned_workflows("check my story for contradictions", {"canon-check"}) == ["canon-check"]


def test_returns_multiple_when_multiple_match():
    got = pins("clean up the suggestions, then map how everything connects")
    assert "entity-triage" in got and "kg-build" in got
