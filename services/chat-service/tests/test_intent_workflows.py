"""Intent -> workflow pinning: the user's words must pin the rail they describe (M2).

This is the fix for the measured rail-discovery ceiling (S03 0/3, S04 1/3, S09 improvises): a
mid-tier model doesn't reliably DISCOVER a non-pinned rail, so we pin it from the request text the
same way the mode binding pins vision-to-book.
"""
from app.services.intent_workflows import intent_pinned_workflows

ALL = {"entity-triage", "canon-check", "kg-build", "build-a-book", "translation-pass",
       "autonomous-drafting", "vision-to-book", "draw-a-map", "chapter-compose"}


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


def test_chapter_compose_from_single_write_requests():
    # the measured step-8 phrasing (write ONE scene/chapter once the world is built)
    assert "chapter-compose" in pins("Please write the opening scene of chapter 1 now.")
    assert "chapter-compose" in pins("draft chapter 3")
    assert "chapter-compose" in pins("put down a first version of this scene")
    assert "chapter-compose" in pins("write this next part")


def test_chapter_compose_does_not_fire_on_world_building_or_planning():
    # must NOT steal vision-to-book's bootstrap or a planning turn
    assert "chapter-compose" not in pins("I want to write a novel about a cartographer.")
    assert "chapter-compose" not in pins("set up the world knowledge and seed the core entities")
    assert "chapter-compose" not in pins("propose a story plan with an arc and beats")


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


def test_draw_a_map_from_the_s10_prompts():
    assert "draw-a-map" in pins("I want to see my world laid out — make a map for it.")
    assert "draw-a-map" in pins("draw a map of my world")
    assert "draw-a-map" in pins("Put my capital city, Ironhold, on the map.")


class TestAVerbStemIsNotTheWordAUserWrites:
    """🔴 MEASURED LIVE 2026-08-12, journey `translation-pass`, book 019f8027.

    "Check what in this book still needs translating into Vietnamese, and bring the translation up
    to date" pinned NOTHING. `\btranslate\b` matches neither "translating" nor "translation" — the
    two forms a user is most likely to write — for the rail literally named `translation-pass`. The
    turn engaged a stale vision-to-book rail instead and no translation tool was ever called.

    This whole table is regexes matched against a human sentence, so a bare verb STEM behind word
    boundaries is blind to ordinary English morphology. Reproducible with no model in the loop.
    """

    LIVE = ("Check what in this book still needs translating into Vietnamese, "
            "and bring the translation up to date.")

    def test_the_LIVE_sentence_pins_the_translation_rail(self):
        from app.services.intent_workflows import intent_pinned_workflows
        assert "translation-pass" in intent_pinned_workflows(self.LIVE)

    def test_every_ordinary_form_of_the_verb_pins_it(self):
        from app.services.intent_workflows import intent_pinned_workflows
        for form in ("translate", "translates", "translated", "translating", "translation"):
            assert "translation-pass" in intent_pinned_workflows(f"please {form} this book"), form

    def test_triage_has_the_same_forms(self):
        from app.services.intent_workflows import intent_pinned_workflows
        for form in ("triage", "triaging", "triaged"):
            assert "entity-triage" in intent_pinned_workflows(f"start {form} the pile"), form

    def test_a_WORD_THAT_MERELY_CONTAINS_THE_STEM_does_not_pin(self):
        """The control. Widening a stem to `translat\w*` would pin on "transatlantic"-shaped noise;
        the enumerated suffixes plus the trailing boundary are what keep it honest."""
        from app.services.intent_workflows import intent_pinned_workflows
        assert intent_pinned_workflows("The transatlantic cable was laid in 1858.") == []
        assert intent_pinned_workflows("Draw a triangle on the map.") == []
        assert intent_pinned_workflows("translator") == []


class TestTheWorkflowsOwnDescriptionMustPinIt:
    """🔴 MEASURED LIVE 2026-08-12, journey `autonomous-drafting`, book 019ff497.

    The workflow's own description is "drafting itself chapter by chapter, on its own", and not one
    of its patterns matched a user who wrote exactly that. "Set this book drafting itself chapter by
    chapter from the plan, and pause for me to review before it goes too far" pinned NOTHING — the
    only rail computed was a completed vision-to-book — so none of its five steps was ever reached.
    """

    LIVE = ("Set this book drafting itself chapter by chapter from the plan, "
            "and pause for me to review before it goes too far.")

    def test_the_LIVE_sentence_pins_autonomous_drafting(self):
        from app.services.intent_workflows import intent_pinned_workflows
        assert "autonomous-drafting" in intent_pinned_workflows(self.LIVE)

    def test_the_phrases_that_make_it_autonomous_pin_it(self):
        from app.services.intent_workflows import intent_pinned_workflows
        for s in ("go chapter by chapter", "let the book draft itself",
                  "let it run on its own and draft"):
            assert "autonomous-drafting" in intent_pinned_workflows(s), s

    def test_a_SINGLE_chapter_request_still_belongs_to_chapter_compose(self):
        """The control. autonomous-drafting is the MANY-chapters, unattended rail; widening it until
        it swallowed "write this chapter" would take the single-chapter case from chapter-compose."""
        from app.services.intent_workflows import intent_pinned_workflows
        got = intent_pinned_workflows("Please write this chapter for me.")
        assert "chapter-compose" in got
        assert "autonomous-drafting" not in got
