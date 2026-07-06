"""D-CANON-CHECK-SDK-UNIFY — shared canon-check plumbing (loreweave_canon_check)."""

from __future__ import annotations

from loreweave_canon_check import (
    CanonCandidateBase,
    apply_verdicts,
    build_judge_request,
    extract_judge_text,
    find_span,
    gone_entities_referenced,
    parse_judge_verdicts,
)


class TestFindSpan:
    def test_ascii_word_boundary_match(self):
        assert find_span("Kai walked into the room.", "Kai") == ("Kai", "Kai walked into the room.")

    def test_ascii_avoids_substring_false_positive(self):
        assert find_span("Always be kind.", "Al") is None

    def test_cjk_plain_containment(self):
        matched, span = find_span("凯走进了房间。", "凯")
        assert matched == "凯"
        assert "凯" in span

    def test_no_match_returns_none(self):
        assert find_span("Nothing here.", "Zhao") is None

    def test_empty_name_returns_none(self):
        assert find_span("Some text", "") is None
        assert find_span("Some text", "   ") is None

    def test_pads_and_ellipses_long_excerpt(self):
        text = "x " * 50 + "Kai" + " y" * 50
        matched, span = find_span(text, "Kai", pad=10)
        assert matched == "Kai"
        assert span.startswith("…") and span.endswith("…")


class TestParseJudgeVerdicts:
    def test_parses_plain_json(self):
        content = '{"verdicts":[{"entity_id":"e1","violated":true,"why":"acting"}]}'
        assert parse_judge_verdicts(content) == {"e1": {"violated": True, "why": "acting"}}

    def test_strips_markdown_fence(self):
        content = '```json\n{"verdicts":[{"entity_id":"e1","violated":false,"why":"memory"}]}\n```'
        assert parse_judge_verdicts(content) == {"e1": {"violated": False, "why": "memory"}}

    def test_self_correction_double_json_block_uses_last(self):
        # Observed live from a $0 local model: it "thinks out loud", emits a
        # first (wrong) verdict, notices the mistake in prose, then emits a
        # corrected second block. A naive first-'{'..last-'}' span would
        # swallow the prose between them and fail to parse at all -- the
        # fix takes the LAST block that parses as {"verdicts": [...]}.
        content = (
            '```json\n{"verdicts":[{"entity_id":"e1","violated":false,"why":"wrong"}]}\n```\n\n'
            "*(Self-correction: re-evaluating...)*\n\n"
            '```json\n{"verdicts":[{"entity_id":"e1","violated":true,"why":"corrected"}]}\n```'
        )
        assert parse_judge_verdicts(content) == {"e1": {"violated": True, "why": "corrected"}}

    def test_brace_inside_quoted_why_does_not_break_depth_counting(self):
        content = '{"verdicts":[{"entity_id":"e1","violated":true,"why":"a {stray} brace"}]}'
        assert parse_judge_verdicts(content) == {"e1": {"violated": True, "why": "a {stray} brace"}}

    def test_unterminated_json_degrades_to_empty(self):
        content = '{"verdicts":[{"entity_id":"e1","violated":true'
        assert parse_judge_verdicts(content) == {}

    def test_prose_only_no_json_degrades_to_empty(self):
        assert parse_judge_verdicts("I cannot determine this.") == {}

    def test_empty_content_returns_empty(self):
        assert parse_judge_verdicts("") == {}

    def test_malformed_json_returns_empty(self):
        assert parse_judge_verdicts("not json at all") == {}

    def test_missing_entity_id_skipped(self):
        content = '{"verdicts":[{"violated":true,"why":"x"}]}'
        assert parse_judge_verdicts(content) == {}

    def test_non_bool_why_defaults(self):
        content = '{"verdicts":[{"entity_id":"e1","violated":true}]}'
        assert parse_judge_verdicts(content) == {"e1": {"violated": True, "why": ""}}


class TestExtractJudgeText:
    def test_reads_messages_array_content(self):
        result = {"messages": [{"role": "assistant", "content": "hello"}]}
        assert extract_judge_text(result) == "hello"

    def test_none_result_returns_empty(self):
        assert extract_judge_text(None) == ""

    def test_missing_messages_returns_empty(self):
        assert extract_judge_text({}) == ""

    def test_result_content_field_is_not_used(self):
        # LOAD-BEARING: content lives at messages[0].content, NOT result.content.
        result = {"content": "wrong place"}
        assert extract_judge_text(result) == ""


class TestBuildJudgeRequest:
    def test_shape_and_defaults(self):
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
        req = build_judge_request(messages, usage_purpose="canon_check", extractor="judge_canon")
        assert req["input"]["messages"] == messages
        assert req["input"]["response_format"] == {"type": "text"}
        assert req["input"]["temperature"] == 0.0
        assert req["input"]["max_tokens"] == 1024
        assert req["input"]["reasoning_effort"] == "none"
        assert req["input"]["chat_template_kwargs"] == {"thinking": False, "enable_thinking": False}
        assert req["job_meta"] == {"usage_purpose": "canon_check", "extractor": "judge_canon"}

    def test_max_tokens_override(self):
        req = build_judge_request([], usage_purpose="x", extractor="y", max_tokens=2048)
        assert req["input"]["max_tokens"] == 2048


class _Candidate(CanonCandidateBase):
    kind: str = "test_kind"


class TestApplyVerdicts:
    def test_applies_matching_verdict(self):
        c = _Candidate(entity_id="e1", name="Alice")
        apply_verdicts([c], {"e1": {"violated": True, "why": "acting"}})
        assert c.confirmed is True
        assert c.source == "llm_judge"
        assert c.why == "acting"

    def test_leaves_unmatched_candidate_untouched(self):
        c = _Candidate(entity_id="e1", name="Alice")
        apply_verdicts([c], {"e2": {"violated": True, "why": "x"}})
        assert c.confirmed is None
        assert c.source == "score_symbolic"


class TestGoneEntitiesReferenced:
    def _snap(self, **overrides):
        ent = {"entity_id": "e1", "name": "Alice", "canonical_name": "alice", "status": "gone"}
        ent.update(overrides)
        return {"entities": [ent]}

    def test_flags_gone_entity_mentioned_in_text(self):
        out = gone_entities_referenced("Alice smiled.", self._snap())
        assert len(out) == 1
        assert out[0]["entity_id"] == "e1"
        assert out[0]["matched"] == "Alice"

    def test_active_entity_not_flagged(self):
        out = gone_entities_referenced("Alice smiled.", self._snap(status="active"))
        assert out == []

    def test_absent_from_text_not_flagged(self):
        out = gone_entities_referenced("Nothing relevant.", self._snap())
        assert out == []

    def test_none_snapshot_degrades_to_empty(self):
        assert gone_entities_referenced("Alice smiled.", None) == []

    def test_empty_text_degrades_to_empty(self):
        assert gone_entities_referenced("", self._snap()) == []

    def test_dedup_per_entity_first_name_form_wins(self):
        out = gone_entities_referenced("Alice, also known as alice, smiled.", self._snap())
        assert len(out) == 1

    def test_extra_field_carried_through(self):
        out = gone_entities_referenced(
            "Alice smiled.", self._snap(gone_from_order=1000), extra_field="gone_from_order",
        )
        assert out[0]["gone_from_order"] == 1000

    def test_extra_field_omitted_when_not_requested(self):
        out = gone_entities_referenced("Alice smiled.", self._snap(gone_from_order=1000))
        assert "gone_from_order" not in out[0]


class TestCanonCandidateBase:
    def test_subclass_shares_base_fields(self):
        c = _Candidate(entity_id="e1", name="Alice")
        assert c.kind == "test_kind"
        assert c.source == "score_symbolic"
        assert c.status == "gone"
        assert c.confirmed is None
