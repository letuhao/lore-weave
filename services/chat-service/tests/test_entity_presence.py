"""T5 (Context Budget Law D2) — entity-presence intent gate tests.

The gate is the token lever AND the quality risk: gate OUT a truly lore-free turn
(cheap), but NEVER gate out a turn that references book lore or leans (anaphorically)
on lore already loaded. These tests pin the bias-to-include contract.
"""
from __future__ import annotations

from app.services.entity_presence import EntityPresence, detect_entity_presence

TOKENS = frozenset({"lâm uyển", "nguyễn trãi", "万古神帝", "the black spire"})


class TestEntityMatch:
    def test_matched_entity_opens_gate(self):
        r = detect_entity_presence("Tell me about Lâm Uyển's arc", TOKENS)
        assert r.grounding_needed is True
        assert "lâm uyển" in r.matched
        assert r.reason == "entity_match"

    def test_verb_op_with_entity_still_matches(self):
        # The D2 motivating case: a verb-heuristic false-negatives on this.
        r = detect_entity_presence("change the status of Lâm Uyển's arc to drafting", TOKENS)
        assert r.grounding_needed is True
        assert "lâm uyển" in r.matched

    def test_cjk_entity_substring_match(self):
        r = detect_entity_presence("万古神帝这个角色怎么样？", TOKENS)
        assert r.grounding_needed is True
        assert "万古神帝" in r.matched

    def test_multiword_alias_match(self):
        r = detect_entity_presence("what happens at the black spire?", TOKENS)
        assert r.grounding_needed is True
        assert "the black spire" in r.matched


class TestGateOut:
    def test_lore_free_op_gates_out(self):
        r = detect_entity_presence("give me a 3-step plan to draft a chapter", TOKENS)
        assert r.grounding_needed is False
        assert r.matched == ()
        assert r.reason == "no_entity_no_anaphora"

    def test_capabilities_smalltalk_gates_out(self):
        r = detect_entity_presence("what can you help me with?", TOKENS)
        assert r.grounding_needed is False


class TestBiasToInclude:
    def test_no_entity_set_opens_gate(self):
        # Cannot tell → open (a glossary outage / a book with no extracted entities).
        r = detect_entity_presence("give me a 3-step plan", None)
        assert r.grounding_needed is True
        assert r.reason == "no_entity_set"
        r2 = detect_entity_presence("give me a 3-step plan", frozenset())
        assert r2.grounding_needed is True

    def test_anaphoric_followup_opens_gate(self):
        # "make it darker" carries no entity token but leans on loaded lore (D4).
        r = detect_entity_presence("now make it darker and higher-stakes", TOKENS)
        assert r.grounding_needed is True
        assert r.reason == "anaphora_bias_include"

    def test_lore_discovery_question_opens_gate(self):
        # "who is the main character" — a lore question the user can't name yet.
        # No entity token, but a discovery intent → MUST ground (else confident-wrong).
        for q in [
            "Who is the main character of this book?",
            "tell me about the protagonist",
            "how does the main character change over the story?",
            "give me a recap of what happens so far",
        ]:
            r = detect_entity_presence(q, TOKENS)
            assert r.grounding_needed is True, q
            assert r.reason == "lore_intent_bias_include"

    def test_the_character_phrase_opens_gate(self):
        r = detect_entity_presence("deepen the character's core conflict", TOKENS)
        assert r.grounding_needed is True

    def test_empty_message_opens_gate(self):
        r = detect_entity_presence("", TOKENS)
        assert r.grounding_needed is True


class TestMultilingualAndQuestionBias:
    """audit MED-2/MED-3: English-only lexicons must not gate out non-English or
    role-noun/thematic lore questions in this multilingual novel product."""

    def test_cjk_non_entity_question_opens(self):
        # "what is this book about?" in Chinese — no entity token, but non-ASCII → open.
        r = detect_entity_presence("这本书讲什么？", TOKENS)
        assert r.grounding_needed is True
        assert r.reason == "non_ascii_bias_include"

    def test_cjk_pronoun_followup_opens(self):
        r = detect_entity_presence("他会怎么做?", TOKENS)
        assert r.grounding_needed is True

    def test_vietnamese_diacritics_open(self):
        # a VN sentence with no listed entity token still opens on non-ASCII.
        r = detect_entity_presence("nhân vật chính thay đổi thế nào", TOKENS)
        assert r.grounding_needed is True

    def test_role_noun_question_opens(self):
        r = detect_entity_presence("does the emperor betray the general?", TOKENS)
        assert r.grounding_needed is True
        assert r.reason == "question_bias_include"

    def test_thematic_question_opens(self):
        r = detect_entity_presence("what is the significance of the ending?", TOKENS)
        assert r.grounding_needed is True

    def test_meta_capability_question_still_gates_out(self):
        # a question ABOUT the tool/assistant is genuinely lore-free → stays gated out.
        for q in ["what can you help me with?", "what can you do here?",
                  "how do i use this editor?"]:
            r = detect_entity_presence(q, TOKENS)
            assert r.grounding_needed is False, q

    def test_ascii_imperative_op_still_gates_out(self):
        # not a question, ASCII, no entity/anaphora/lore-intent → still the token win.
        r = detect_entity_presence("give me a 3-step plan to draft a chapter", TOKENS)
        assert r.grounding_needed is False


class TestSubstringSafety:
    def test_ascii_token_is_word_bounded(self):
        # 'arc' must not match inside 'search'/'architecture'; only 'the black spire'
        # is a real token here, so a generic sentence stays gated out.
        r = detect_entity_presence("search the architecture for a plan", frozenset({"arc"}))
        assert r.grounding_needed is False

    def test_ascii_token_matches_whole_word(self):
        r = detect_entity_presence("what is the arc here", frozenset({"arc"}))
        assert r.grounding_needed is True


class TestTelemetry:
    def test_as_telemetry_shape(self):
        t = EntityPresence(True, ("lâm uyển",), "entity_match").as_telemetry()
        assert t == {"grounding_needed": True, "matched": ["lâm uyển"], "reason": "entity_match"}
