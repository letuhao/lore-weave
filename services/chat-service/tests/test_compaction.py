"""Wave A4 — provider-agnostic compaction (micro → full → fail)."""
from __future__ import annotations

import pytest

from app.services.compaction import (
    COMPACT_TRIGGER_RATIO,
    CompactionReport,
    compact_messages,
    extract_breadcrumb,
    inject_recovery_hint,
    recovery_hint_message,
    summary_message,
    _PLACEHOLDER,
    _DUP_PLACEHOLDER,
)

pytestmark = pytest.mark.asyncio


class TestW1ReportSurface:
    async def test_trigger_ratio_named_constant_is_the_default(self):
        # W1 — until_compact_pct reuses THIS constant; the default trigger must
        # be the same number (no duplicated 0.75 anywhere).
        import inspect

        sig = inspect.signature(compact_messages)
        assert sig.parameters["trigger_ratio"].default == COMPACT_TRIGGER_RATIO == 0.75

    async def test_did_work_false_when_nothing_changed(self):
        assert CompactionReport().did_work is False
        assert CompactionReport(triggered=True).did_work is False  # no-op pass

    async def test_did_work_true_per_tier(self):
        assert CompactionReport(tool_results_cleared=1).did_work is True
        assert CompactionReport(summarized=True).did_work is True
        assert CompactionReport(turns_truncated=3).did_work is True


def _big(n: int) -> str:
    return "word " * n  # ~ n*1.25 tokens (ASCII)


def _tool(name: str, size: int = 400) -> dict:
    return {"role": "tool", "name": name, "tool_call_id": f"c_{name}", "content": _big(size)}


def _asst_call(call_id: str, name: str = "propose_edit", args: str = "{}") -> dict:
    """An assistant turn that made a tool call (OpenAI/Anthropic shape)."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": call_id, "type": "function",
                        "function": {"name": name, "arguments": args}}],
    }


def _tool_result(call_id: str, size: int = 400) -> dict:
    """A tool result answering a specific tool_call id (resume-path shape)."""
    return {"role": "tool", "tool_call_id": call_id, "content": _big(size)}


def _has_orphan_tool(msgs: list[dict]) -> bool:
    """A provider (OpenAI/Anthropic) rejects a messages array where a tool result
    has no preceding assistant tool_call of the same id, OR an assistant tool_call
    has no following tool result. Either is an orphan."""
    call_ids = {tc.get("id") for m in msgs for tc in (m.get("tool_calls") or [])}
    result_ids = {m.get("tool_call_id") for m in msgs
                  if m.get("role") == "tool" or "tool_call_id" in m}
    # orphan tool result (no matching call)
    for m in msgs:
        if (m.get("role") == "tool" or "tool_call_id" in m) and m.get("tool_call_id") not in call_ids:
            return True
    # orphan tool call (no matching result)
    for m in msgs:
        for tc in (m.get("tool_calls") or []):
            if tc.get("id") not in result_ids:
                return True
    return False


class TestNoTrigger:
    async def test_under_trigger_is_unchanged(self):
        msgs = [{"role": "user", "content": "hi"}]
        out, rep = await compact_messages(msgs, effective_limit=10_000)
        assert out is msgs
        assert rep.triggered is False

    async def test_null_limit_is_noop(self):
        msgs = [_tool("web_search"), {"role": "user", "content": _big(9999)}]
        out, rep = await compact_messages(msgs, effective_limit=None)
        assert rep.triggered is False


class TestBreadcrumb:
    """T6/D6 — the deterministic verbatim breadcrumb preserved across the LLM summary."""

    def test_extracts_number_facts_and_names(self):
        msgs = [{"role": "user", "content":
                 "The ritual needs exactly SEVEN star-anchors; the blade 'Verithrax' was "
                 "forged by Oldan Vex."}]
        bc = extract_breadcrumb(msgs)
        assert "SEVEN star-anchors" in bc          # whole number-bearing sentence, verbatim
        assert "Verithrax" in bc                    # quoted name (not the possessive trap)
        # multi-word names survive as their component words (single-word extractor)
        assert "Oldan" in bc and "Vex" in bc
        assert bc.startswith("KEY DETAILS")

    def test_preserves_single_word_coined_names(self):
        # the fiction case the multi-word/quoted patterns MISSED (measured: 7/9 dropped),
        # which made a compacted long session lose character/place/spell names → recall
        # failure. Single-word coined names are the highest-value novel facts.
        msgs = [
            {"role": "user", "content": "The secret rune is VORTHANE. Remember it."},
            {"role": "user", "content": "Kael the blacksmith forged Dawnbreaker in Emberfall."},
            {"role": "user", "content": "Sorenth rules Rimehold. Mira is a healer."},
        ]
        bc = extract_breadcrumb(msgs)
        for name in ("VORTHANE", "Kael", "Dawnbreaker", "Emberfall", "Sorenth", "Rimehold", "Mira"):
            assert name in bc, f"{name} dropped from breadcrumb"

    def test_filters_common_openers_and_allcommon_phrases(self):
        # precision: capitalized common words (sentence openers, even after a colon) and
        # all-common multi-word phrases must NOT pollute the breadcrumb.
        bc = extract_breadcrumb([{"role": "user", "content":
            "Kael forged Dawnbreaker. Reply OK. More lore: The chronicle is long."}])
        names = ""
        for line in bc.splitlines():
            if line.startswith("Names"):
                names = line.lower()
        assert "kael" in names and "dawnbreaker" in names
        assert "reply ok" not in names   # all-common phrase filtered
        for junk in ("; the;", "; more;", "; reply;", "; note;", "; here;"):
            assert junk not in names + ";"

    def test_preserves_vietnamese_diacritic_names(self):
        # ASCII-only regexes shredded Vietnamese names at the first diacritic
        # (Nguyên→"Nguy") and dropped the protagonist. Unicode-aware _WORD keeps them whole.
        bc = extract_breadcrumb([{"role": "user", "content":
            "Nhân vật chính là Hàn Lập, tu sĩ Kim Đan. Lăng Thiên tại Thành Bắc."}])
        for name in ("Hàn", "Lập", "Lăng", "Thiên", "Thành", "Kim"):
            assert name in bc, f"{name} dropped/fragmented in VI breadcrumb"

    def test_preserves_cjk_quoted_name_and_figure_sentence(self):
        # CJK has no capitalization signal; a quoted name + a Chinese-numeral figure
        # sentence are the two things the deterministic breadcrumb CAN preserve.
        bc = extract_breadcrumb([{"role": "user", "content":
            "主角叫「叶辰」，在北城大战三百回合，有一万守军。"}])
        assert "叶辰" in bc          # quoted CJK name (via _QUOTED_CJK)
        assert "三百" in bc          # Chinese-numeral figure sentence (via _CJK_NUM split)

    def test_empty_when_nothing_salient(self):
        assert extract_breadcrumb([{"role": "user", "content": "ok thanks"}]) == ""
        assert extract_breadcrumb([]) == ""

    async def test_breadcrumb_survives_a_failed_summarizer(self):
        # the summary LLM returns nothing, but add_breadcrumb still preserves the facts
        # deterministically rather than hard-dropping the middle.
        async def _empty_summarize(_middle):
            return ""
        msgs = [{"role": "system", "content": "sys"}]
        msgs += [{"role": "user", "content": _big(300) + "."} for _ in range(4)]
        msgs.append({"role": "assistant", "content": "The debt is 4,400 salt-marks."})
        msgs += [{"role": "user", "content": _big(300) + "."} for _ in range(2)]
        msgs.append({"role": "user", "content": "latest"})
        out, rep = await compact_messages(
            msgs, effective_limit=2_000, keep_recent=1,
            summarize=_empty_summarize, add_breadcrumb=True)
        joined = " ".join(m.get("content", "") for m in out if m.get("role") == "system")
        assert "4,400 salt-marks" in joined         # the figure survived the empty summary
        assert rep.summarized is True and "breadcrumb" in rep.steps

    async def test_off_by_default_no_breadcrumb(self):
        async def _sum(_m):
            return "SYNOPSIS: stuff"
        msgs = [{"role": "user", "content": _big(400) + " 4,400 salt-marks"} for _ in range(6)]
        msgs.append({"role": "user", "content": "latest"})
        out, _ = await compact_messages(
            msgs, effective_limit=2_000, keep_recent=1, summarize=_sum)  # add_breadcrumb defaults False
        joined = " ".join(m.get("content", "") for m in out if m.get("role") == "system")
        assert "KEY DETAILS" not in joined


class TestRecoveryHint:
    """T6/D6 — the post-compaction recovery hint that points the model at
    conversation_search (so a lossy summary → a SEARCH, not a guess/omission)."""

    async def test_hint_message_is_system_and_names_the_tool(self):
        m = recovery_hint_message()
        assert m["role"] == "system"
        assert "conversation_search" in m["content"]
        # tells the model NOT to guess/omit without searching
        assert "guess" in m["content"].lower()

    async def test_injected_after_leading_pinned_block_incl_summary(self):
        # after compaction the array is [system…, <summary>, …tail]. The hint must land
        # right after the leading pinned block (so it reads as guidance about the summary)
        # and BEFORE the first conversation turn.
        msgs = [
            {"role": "system", "content": "sys"},
            summary_message("old turns condensed here"),
            {"role": "user", "content": "recall the blade name"},
        ]
        inject_recovery_hint(msgs)
        assert len(msgs) == 4
        # inserted at index 2 — after system + summary, before the user turn
        assert msgs[2]["role"] == "system" and "conversation_search" in msgs[2]["content"]
        assert msgs[3]["role"] == "user"

    async def test_injected_at_end_when_all_pinned(self):
        # degenerate: no conversation tail (all pinned) → append at the end, no crash.
        msgs = [{"role": "system", "content": "sys"}]
        inject_recovery_hint(msgs)
        assert len(msgs) == 2 and msgs[-1]["content"] == recovery_hint_message()["content"]


class TestTaskElasticTarget:
    """T2/D3 — the `target` param fires compaction at a SMALLER soft budget than the
    flat 0.75×window trigger (or, when target > window, clamps to the hard ceiling)."""

    async def test_target_triggers_earlier_than_flat(self):
        # ~10K tok: far UNDER the flat 0.75×100_000=75_000 trigger (baseline never
        # compacts), but far OVER a task-elastic target of 3_000 → the target makes
        # it fire. This is the whole mechanism (a light turn compacts sooner).
        msgs = [{"role": "system", "content": "sys"},
                {"role": "user", "content": _big(4_000)},
                {"role": "assistant", "content": _big(4_000)},
                {"role": "user", "content": "latest"}]
        _, base = await compact_messages(
            [dict(m) for m in msgs], effective_limit=100_000)
        assert base.triggered is False  # under the flat trigger
        _, cand = await compact_messages(
            [dict(m) for m in msgs], effective_limit=100_000, target=3_000)
        assert cand.triggered is True   # the soft target fires it

    async def test_none_target_keeps_flat_behavior(self):
        # target=None (flag OFF) is byte-identical to not passing target at all.
        msgs = [{"role": "user", "content": _big(4_000)},
                {"role": "assistant", "content": _big(4_000)}]
        _, a = await compact_messages([dict(m) for m in msgs], effective_limit=100_000)
        _, b = await compact_messages(
            [dict(m) for m in msgs], effective_limit=100_000, target=None)
        assert a.triggered is False and b.triggered is False

    async def test_target_above_ceiling_clamps_and_delays(self):
        # A target ABOVE the effective limit must not push the trigger past the hard
        # ceiling: trigger = min(target, effective_limit). ~7K tok is over the flat
        # 0.75×8_000=6_000 trigger (baseline fires) but under the clamped ceiling
        # 8_000 (candidate does NOT fire — a roomy/high-task_weight turn).
        msgs = [{"role": "user", "content": _big(2_800)},
                {"role": "assistant", "content": _big(2_800)}]
        _, base = await compact_messages([dict(m) for m in msgs], effective_limit=8_000)
        assert base.triggered is True
        _, cand = await compact_messages(
            [dict(m) for m in msgs], effective_limit=8_000, target=999_999)
        assert cand.triggered is False


class TestMicrocompact:
    async def test_evicts_old_tool_results_keeps_last_n(self):
        msgs = [
            {"role": "system", "content": "sys"},
            _tool("a"), _tool("b"), _tool("c"), _tool("d"), _tool("e"),
            {"role": "user", "content": "now"},
        ]
        out, rep = await compact_messages(msgs, effective_limit=1_000, keep_tool_results=2)
        assert rep.triggered and rep.tool_results_cleared == 3  # 5 tools - keep 2
        cleared = [m for m in out if m.get("role") == "tool" and m["content"] == _PLACEHOLDER]
        assert len(cleared) == 3
        # the last two tool results are kept verbatim
        kept = [m for m in out if m.get("role") == "tool" and m["content"] != _PLACEHOLDER]
        assert len(kept) == 2

    async def test_never_evicts_excluded_tool(self):
        msgs = [
            _tool("web_search"), _tool("web_search"), _tool("web_search"),
            _tool("web_search"), {"role": "user", "content": "q"},
        ]
        out, rep = await compact_messages(msgs, effective_limit=500, keep_tool_results=1)
        # web_search is excluded → none cleared even though 4 > keep 1
        assert rep.tool_results_cleared == 0
        assert all(m["content"] != _PLACEHOLDER for m in out if m.get("role") == "tool")

    async def test_legacy_glossary_alias_results_are_also_never_evicted(self):
        # `glossary_web_search` is the superseded alias (still callable by existing public
        # keys). Its results are just as load-bearing/cited as web_search's, so they must
        # survive compaction for as long as the alias exists.
        msgs = [
            _tool("glossary_web_search"), _tool("glossary_web_search"),
            _tool("glossary_web_search"), {"role": "user", "content": "q"},
        ]
        out, rep = await compact_messages(msgs, effective_limit=500, keep_tool_results=1)
        assert rep.tool_results_cleared == 0
        assert all(m["content"] != _PLACEHOLDER for m in out if m.get("role") == "tool")


class TestExcludeToolsAreRealWireNames:
    """The bug this class exists to prevent.

    `DEFAULT_EXCLUDE_TOOLS` was `{"web_search"}` from the day it was written — but no tool
    named `web_search` existed. The only wire name was `glossary_web_search`, so the set
    matched NOTHING and every web-search result was silently evictable, contradicting the
    constant's own docstring. `test_never_evicts_excluded_tool` above passed the whole
    time, because it fed the compactor the same fictional name the constant used: the test
    encoded the assumption instead of reality.

    So: pin the set against names the platform ACTUALLY registers, not against itself.
    """

    async def test_web_search_is_a_real_always_on_core_tool(self):
        import app.services.tool_discovery as td
        from app.services.compaction import DEFAULT_EXCLUDE_TOOLS

        # If this reds, `web_search` stopped being a real advertised tool and the
        # exclusion is dead again — fix the set, don't delete the test.
        assert "web_search" in td.ALWAYS_ON_CORE_NAMES
        assert "web_search" in DEFAULT_EXCLUDE_TOOLS

    async def test_the_superseded_alias_is_excluded_while_it_still_exists(self):
        from app.services.compaction import DEFAULT_EXCLUDE_TOOLS

        # Retire this line only when glossary_web_search is actually deleted (not merely
        # marked legacy) — public keys scoped to `domain:glossary` still call it.
        assert "glossary_web_search" in DEFAULT_EXCLUDE_TOOLS

    async def test_does_not_mutate_caller_messages(self):
        msgs = [_tool("a"), _tool("b"), _tool("c"), _tool("d"), {"role": "user", "content": "x"}]
        original_first = msgs[0]["content"]
        await compact_messages(msgs, effective_limit=500, keep_tool_results=1)
        assert msgs[0]["content"] == original_first  # caller's list untouched


class TestFullCompactAndFailure:
    async def test_summarize_used_when_micro_insufficient(self):
        # one huge non-tool turn micro-compact can't shrink → summarizer runs.
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": _big(4000)},
            {"role": "assistant", "content": _big(4000)},
            {"role": "user", "content": "latest"},
        ]
        out, rep = await compact_messages(
            msgs, effective_limit=2_000, keep_recent=1,
            summarize=lambda _m: "compressed summary of the discussion",
        )
        assert rep.summarized is True
        assert any("<summary>" in (m.get("content") or "") for m in out)

    async def test_async_summarizer_is_awaited_and_used(self):
        # the production summarizer is an async LLM call — prove the await path.
        async def async_summarize(_m):
            return "async-compressed synopsis"

        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": _big(4000)},
            {"role": "assistant", "content": _big(4000)},
            {"role": "user", "content": "latest"},
        ]
        out, rep = await compact_messages(
            msgs, effective_limit=2_000, keep_recent=1, summarize=async_summarize,
        )
        assert rep.summarized is True
        assert any("async-compressed synopsis" in (m.get("content") or "") for m in out)

    async def test_summarize_failure_falls_through_to_truncate(self):
        # edge #2: a broken summarizer must NOT poison context — fall to hard-truncate.
        def bad_summarize(_m):
            raise RuntimeError("local model timed out")

        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": _big(4000)},
            {"role": "assistant", "content": _big(4000)},
            {"role": "user", "content": _big(4000)},
            {"role": "user", "content": "latest"},
        ]
        out, rep = await compact_messages(
            msgs, effective_limit=2_000, keep_recent=1, summarize=bad_summarize,
        )
        assert rep.summarize_failed is True
        assert rep.summarized is False
        assert rep.turns_truncated > 0  # fell through to the deterministic backstop
        assert "hard_truncate" in rep.steps


class TestHardTruncateAndOverflow:
    async def test_hard_truncate_keeps_pinned_and_recent(self):
        msgs = [{"role": "system", "content": "SYS"}] + [
            {"role": "user", "content": _big(2000)} for _ in range(6)
        ] + [{"role": "user", "content": "LAST"}]
        out, rep = await compact_messages(msgs, effective_limit=1_500, keep_recent=2)
        assert out[0]["content"] == "SYS"           # pinned kept, leads the prompt
        assert out[-1]["content"] == "LAST"          # recent tail kept
        assert rep.turns_truncated > 0

    async def test_overflow_when_pinned_alone_exceed_budget(self):
        # edge #4: non-evictable system messages alone blow the budget.
        msgs = [
            {"role": "system", "content": _big(5000)},
            {"role": "user", "content": "x"},
        ]
        out, rep = await compact_messages(msgs, effective_limit=1_000, keep_recent=1)
        assert rep.overflowed is True


class TestToolPairSafety:
    """The resume path (agent→GUI 2nd pass) feeds a `working` array that CONTAINS
    assistant `tool_calls` + `role:tool` results into compaction. Structural
    truncation (hard-truncate, and the summarize tail-slice) must never split a
    tool-call/tool-result pair — an orphan makes the provider reject the turn 400."""

    def _resume_shaped(self) -> list[dict]:
        # system (pinned) + several tool exchanges + a trailing pending→answered pair.
        return [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": _big(600)},
            _asst_call("c_1"), _tool_result("c_1", 600),
            {"role": "assistant", "content": _big(600)},
            {"role": "user", "content": _big(600)},
            _asst_call("c_2"), _tool_result("c_2", 600),
            _asst_call("c_3"), _tool_result("c_3", 600),  # most recent exchange
        ]

    async def test_hard_truncate_never_orphans_a_tool_pair(self):
        # keep_recent=1 would slice the tail to a lone tool result (orphan) pre-fix;
        # keep_tool_results high so microcompact clears nothing → hard-truncate runs.
        msgs = self._resume_shaped()
        out, rep = await compact_messages(
            msgs, effective_limit=1_500, keep_recent=1, keep_tool_results=99,
        )
        assert rep.triggered and rep.turns_truncated > 0
        assert "hard_truncate" in rep.steps
        assert not _has_orphan_tool(out), f"orphaned tool pair after truncate: {[m.get('role') for m in out]}"

    async def test_summarize_tail_slice_never_orphans(self):
        # summarize succeeds → work = pinned + summary + tail[-keep_recent:];
        # that slice must also land on a safe boundary.
        msgs = self._resume_shaped()
        out, rep = await compact_messages(
            msgs, effective_limit=1_500, keep_recent=1, keep_tool_results=99,
            summarize=lambda _m: "the story so far",
        )
        assert rep.triggered
        assert not _has_orphan_tool(out), f"orphaned after summarize slice: {[m.get('role') for m in out]}"

    async def test_microcompact_preserves_pairing(self):
        # microcompact only blanks tool CONTENT (keeps the message + tool_call_id),
        # so pairing is intact even when it clears old results.
        msgs = self._resume_shaped()
        out, rep = await compact_messages(msgs, effective_limit=2_000, keep_tool_results=1)
        assert not _has_orphan_tool(out)


def _result(call_id: str, content: str) -> dict:
    """A tool result with EXPLICIT content (to construct duplicate reads)."""
    return {"role": "tool", "tool_call_id": call_id, "content": content}


class TestDuplicateReadCollapse:
    """T6/D13a — reversible dup-read collapse: an EXACT-duplicate tool result (the model
    re-read an unchanged resource) is collapsed to a reference, keeping the latest full."""

    async def test_collapses_earlier_identical_read_keeps_latest(self):
        dup = _big(400)
        msgs = [
            {"role": "system", "content": "sys"},
            _asst_call("c1"), _result("c1", dup),
            {"role": "user", "content": "and again?"},
            _asst_call("c2"), _result("c2", dup),  # identical re-read (most recent)
            {"role": "user", "content": "now"},
        ]
        # keep_tool_results high so microcompact clears nothing → isolate the collapse tier.
        out, rep = await compact_messages(
            msgs, effective_limit=1_000, keep_tool_results=99, collapse_duplicates=True)
        assert rep.duplicates_collapsed == 1
        assert "collapse_duplicates" in rep.steps
        tool_contents = [m["content"] for m in out if m.get("role") == "tool"]
        assert tool_contents == [_DUP_PLACEHOLDER, dup]  # earlier collapsed, latest full
        assert not _has_orphan_tool(out)  # only content rewritten → pairing intact

    async def test_off_by_default_no_collapse(self):
        dup = _big(400)
        msgs = [
            _asst_call("c1"), _result("c1", dup),
            _asst_call("c2"), _result("c2", dup),
            {"role": "user", "content": "now"},
        ]
        # collapse_duplicates defaults False → the dup contents are never referenced-away.
        out, rep = await compact_messages(
            msgs, effective_limit=1_000, keep_tool_results=99)
        assert rep.duplicates_collapsed == 0
        assert "collapse_duplicates" not in rep.steps
        assert _DUP_PLACEHOLDER not in [m.get("content") for m in out]

    async def test_distinct_reads_are_not_collapsed(self):
        msgs = [
            _asst_call("c1"), _result("c1", _big(400) + " ALPHA"),
            _asst_call("c2"), _result("c2", _big(400) + " BETA"),  # different content
            {"role": "user", "content": "now"},
        ]
        _, rep = await compact_messages(
            msgs, effective_limit=1_000, keep_tool_results=99, collapse_duplicates=True)
        assert rep.duplicates_collapsed == 0

    async def test_excluded_tool_never_collapsed(self):
        dup = _big(400)
        msgs = [
            _asst_call("c1"), {"role": "tool", "name": "web_search", "tool_call_id": "c1", "content": dup},
            _asst_call("c2"), {"role": "tool", "name": "web_search", "tool_call_id": "c2", "content": dup},
            {"role": "user", "content": "now"},
        ]
        _, rep = await compact_messages(
            msgs, effective_limit=1_000, keep_tool_results=99, collapse_duplicates=True)
        assert rep.duplicates_collapsed == 0  # web_search results are load-bearing/cited

    async def test_collapse_never_orphans_on_resume_shape(self):
        # a resume array with a duplicated read: collapse must keep every pair intact.
        dup = _big(500)
        msgs = [
            {"role": "system", "content": "sys"},
            _asst_call("c_1"), _result("c_1", dup),
            {"role": "assistant", "content": _big(300)},
            _asst_call("c_2"), _result("c_2", dup),  # identical re-read
            _asst_call("c_3"), _result("c_3", _big(300)),
        ]
        out, rep = await compact_messages(
            msgs, effective_limit=1_500, keep_tool_results=99, collapse_duplicates=True)
        assert rep.duplicates_collapsed == 1
        assert not _has_orphan_tool(out)

    async def test_did_work_true_when_only_collapse_fired(self):
        assert CompactionReport(duplicates_collapsed=1).did_work is True

    async def test_collapse_survives_microcompact_no_double_count(self):
        # collapse fires, then (still over trigger) microcompact runs. The collapsed dup
        # must be left as its SPECIFIC reference (not re-cleared to _PLACEHOLDER) and must
        # NOT be counted in tool_results_cleared (no double-count vs duplicates_collapsed).
        dup = _big(400)
        msgs = [
            {"role": "system", "content": "sys"},
            _asst_call("c1"), _result("c1", dup),            # oldest dup → collapsed
            _asst_call("c2"), _result("c2", _big(400) + " A"),  # unique
            _asst_call("c3"), _result("c3", _big(400) + " B"),  # unique
            _asst_call("c4"), _result("c4", dup),            # most-recent dup → kept full
            {"role": "user", "content": "now"},
        ]
        out, rep = await compact_messages(
            msgs, effective_limit=1_000, keep_tool_results=1, collapse_duplicates=True)
        assert rep.duplicates_collapsed == 1
        assert "microcompact" in rep.steps
        c1 = next(m for m in out if m.get("tool_call_id") == "c1")
        assert c1["content"] == _DUP_PLACEHOLDER          # NOT overwritten to _PLACEHOLDER
        # only the two UNIQUE results were microcompacted — the collapsed dup isn't re-counted
        assert rep.tool_results_cleared == 2
        assert not _has_orphan_tool(out)
