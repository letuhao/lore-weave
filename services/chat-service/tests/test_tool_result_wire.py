"""T0 / L3 — concise tool-result wire (spec §6a, §14a).

Proves the EFFECT (not existence) of the single funnel helper:
  - ensure_ascii=False kills the \\uXXXX tax on VI/CJK (the measured 2-3× win);
  - drop-None trims optional-field padding;
  - empty containers + falsy scalars are PRESERVED (semantics-safe);
  - round-trips to the same object modulo the dropped nulls.
"""

import json

from app.services.tool_result_wire import prune_none, tool_result_content


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
