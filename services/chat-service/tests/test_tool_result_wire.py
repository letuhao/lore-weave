"""T0 / L3 — concise tool-result wire (spec §6a, §14a).

Proves the EFFECT (not existence) of the single funnel helper:
  - ensure_ascii=False kills the \\uXXXX tax on VI/CJK (the measured 2-3× win);
  - drop-None trims optional-field padding;
  - empty containers + falsy scalars are PRESERVED (semantics-safe);
  - round-trips to the same object modulo the dropped nulls.
"""

import json

from app.services.tool_result_wire import (
    prune_none,
    tool_result_content,
    tool_result_content_capped,
)
from loreweave_context.tokens import estimate_tokens


class TestEnsureAsciiFalse:
    def test_vietnamese_not_escaped(self):
        out = tool_result_content({"name": "Lâm Uyển"})
        assert "Lâm Uyển" in out
        assert "\\u" not in out

    def test_cjk_not_escaped(self):
        out = tool_result_content({"title": "第一章 開始"})
        assert "第一章 開始" in out
        assert "\\u" not in out

    def test_vi_bytes_shrink_vs_ensure_ascii_true(self):
        # The core T0 claim: VI content is materially smaller than the old default.
        payload = {"entities": ["Lâm Uyển", "Nguyễn Trãi", "Đại Việt"] * 5}
        old = json.dumps(payload)  # ensure_ascii=True (the pre-T0 default)
        new = tool_result_content(payload)
        assert len(new) < len(old)
        # Diacritic-heavy VI escapes to ~6 bytes/char; expect a large cut.
        assert len(new) <= len(old) * 0.7


class TestDropNone:
    def test_drops_null_fields(self):
        out = json.loads(tool_result_content({"a": 1, "b": None, "c": "x"}))
        assert out == {"a": 1, "c": "x"}

    def test_drops_nested_null_fields(self):
        out = json.loads(tool_result_content({"outer": {"keep": 1, "drop": None}}))
        assert out == {"outer": {"keep": 1}}

    def test_keeps_empty_containers(self):
        # "found nothing" must survive as a signal to the model.
        out = json.loads(tool_result_content({"results": [], "meta": {}}))
        assert out == {"results": [], "meta": {}}

    def test_keeps_falsy_scalars(self):
        out = json.loads(tool_result_content({"success": False, "count": 0, "note": ""}))
        assert out == {"success": False, "count": 0, "note": ""}

    def test_list_elements_recurse_and_preserve_positions(self):
        out = prune_none([{"k": None, "v": 1}, {"v": 2}])
        assert out == [{"v": 1}, {"v": 2}]


class TestRobustness:
    def test_non_json_type_stringified_not_crash(self):
        class Weird:
            def __str__(self):
                return "weird!"

        out = json.loads(tool_result_content({"obj": Weird()}))
        assert out == {"obj": "weird!"}

    def test_error_payload_roundtrips(self):
        out = json.loads(tool_result_content({"error": "chapter not found"}))
        assert out == {"error": "chapter not found"}


class TestD7SingleItemOverflow:
    """D7: a single tool result over the per-contributor ceiling is withheld and
    replaced with a self-correcting overflow notice (never a silent truncation)."""

    def test_under_cap_passes_through_byte_identical(self):
        payload = {"results": [{"id": 1, "name": "Lâm Uyển"}]}
        assert tool_result_content_capped(payload, tool_name="x", token_cap=8000) == \
            tool_result_content(payload)

    def test_over_cap_withheld_with_self_correcting_notice(self):
        big = {"nodes": [{"i": i, "text": "word " * 40} for i in range(400)]}
        raw = tool_result_content(big)
        assert estimate_tokens(raw) > 50  # sanity: the dump is genuinely large
        out = json.loads(tool_result_content_capped(big, tool_name="composition_list_outline", token_cap=50))
        # the giant dump is GONE — replaced by an actionable notice
        assert out["error"] == "tool_result_overflow"
        assert out["tool"] == "composition_list_outline"
        assert out["cap"] == 50
        assert out["tokens"] > 50
        # the notice names the tool + the concrete remedies (T1 knobs)
        assert "composition_list_outline" in out["message"]
        for remedy in ("detail=summary", "limit", "fields"):
            assert remedy in out["message"]

    def test_cap_none_or_zero_disables(self):
        big = {"nodes": [{"i": i, "text": "word " * 40} for i in range(400)]}
        raw = tool_result_content(big)
        assert tool_result_content_capped(big, tool_name="x", token_cap=None) == raw
        assert tool_result_content_capped(big, tool_name="x", token_cap=0) == raw

    def test_cap_trip_is_de_silenced_with_a_warning(self, caplog):
        """A D7 cap trip logs a diagnosable WARNING (de-silence) so a withheld
        result is visible in ops/eval, not silent."""
        import logging

        big = {"nodes": [{"i": i, "text": "word " * 40} for i in range(400)]}
        with caplog.at_level(logging.WARNING, logger="app.services.tool_result_wire"):
            tool_result_content_capped(big, tool_name="composition_list_outline", token_cap=50)
        assert any(
            "tool_result_overflow" in r.message and "composition_list_outline" in r.message
            for r in caplog.records
        ), "expected a de-silencing WARNING on a D7 cap trip"

    def test_under_cap_does_not_warn(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="app.services.tool_result_wire"):
            tool_result_content_capped({"ok": True}, tool_name="x", token_cap=8000)
        assert not any("tool_result_overflow" in r.message for r in caplog.records)

    def test_capped_ex_reports_tokens_for_inspector_trace(self):
        """`_ex` returns the over-cap token count when it caps (so the D7 span can
        record it) and None when it doesn't — the Inspector-trace hook."""
        from app.services.tool_result_wire import tool_result_content_capped_ex

        big = {"nodes": [{"i": i, "text": "word " * 40} for i in range(400)]}
        content, capped = tool_result_content_capped_ex(big, tool_name="x", token_cap=50)
        assert capped is not None and capped > 50
        assert json.loads(content)["error"] == "tool_result_overflow"

        content2, capped2 = tool_result_content_capped_ex({"ok": True}, tool_name="x", token_cap=8000)
        assert capped2 is None
        assert json.loads(content2) == {"ok": True}

    def test_overflow_notice_itself_is_small(self):
        big = {"nodes": [{"i": i, "text": "word " * 40} for i in range(400)]}
        notice = tool_result_content_capped(big, tool_name="x", token_cap=50)
        assert estimate_tokens(notice) < 200  # the remedy can't itself blow the budget

    def test_missing_tool_name_uses_generic_phrasing(self):
        big = {"blob": "x" * 20000}
        out = json.loads(tool_result_content_capped(big, token_cap=50))
        assert "tool" not in out  # None tool field is pruned (drop-None funnel)
        assert "the tool" in out["message"]
