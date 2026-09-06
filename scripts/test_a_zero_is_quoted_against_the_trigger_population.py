"""A "it did not reproduce" zero must be quoted against the runs that COULD have shown it.

🔴 THIS PINS A MISTAKE MADE TWICE IN ONE DAY, not a hypothetical. On 2026-08-30 both of the
loop's long-running "needs a live catch" rows were given a pooled run count as their rate:
270 runs (really 15) and 285 runs (really 22). Both notes carried a prose caveat that the runs
were not chosen to provoke the defect, and both quoted the pooled figure anyway.

So the guard is on the two things the caveat did not do: that the split is computed from what
the model ACTUALLY CALLED, and that a denominator which is zero, or tiny against the pool, says
so LOUDLY rather than being available as a large comforting number.

Synthetic runs throughout. The helper's own `load_runs` is mtime-dated and a checkout resets
every mtime, so a test anchored on real files would rot into a false green.
"""
from __future__ import annotations

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "trigdenom", ROOT / "scripts" / "toolloop" / "trigger_denominator.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _mod()


def _run(*names):
    return {"tool_calls": [{"type": "TOOL_CALL_START", "toolCallName": n} for n in names]}


class TestTheSplitIsOnWhatWasACTUALLYCalled:
    def test_a_run_that_called_no_trigger_tool_is_excluded(self):
        runs = [_run("book_read"), _run("jobs_get"), _run()]
        res = M.trigger_matched(runs, {"jobs_get"})
        assert res["total"] == 3 and res["matched"] == 1

    def test_tool_under_test_does_NOT_count(self):
        """The silent-turn census: `tool_under_test` was a trigger tool in 0 of 285 runs while 22
        runs called one anyway. Intent is not exposure."""
        runs = [{"tool_under_test": "jobs_get", "tool_calls": []}]
        assert M.trigger_matched(runs, {"jobs_get"})["matched"] == 0

    def test_a_result_without_a_START_is_not_a_call(self):
        runs = [{"tool_calls": [{"type": "TOOL_CALL_RESULT", "toolCallName": "jobs_get"}]}]
        assert M.trigger_matched(runs, {"jobs_get"})["matched"] == 0


class TestAnUnexercisedTriggerIsNamed:
    def test_it_names_every_trigger_tool_no_run_touched(self):
        """22 of 285 looks like a sample until you see it covered 2 of 8 families."""
        res = M.trigger_matched([_run("jobs_get")], {"jobs_get", "plan_compile", "jobs_list"})
        assert res["unexercised"] == ["jobs_list", "plan_compile"]

    def test_the_report_says_how_many_of_how_many(self):
        out = M.format_report(
            M.trigger_matched([_run("jobs_get")], {"jobs_get", "plan_compile", "jobs_list"}),
            {"jobs_get", "plan_compile", "jobs_list"})
        assert "NEVER exercised" in out and "2 of 3" in out


class TestTheMisleadingNumberIsCalledOut:
    def test_a_zero_denominator_refuses_to_be_a_rate(self):
        res = M.trigger_matched([_run("book_read")] * 50, {"plan_compile"})
        out = M.format_report(res, {"plan_compile"})
        assert res["matched"] == 0
        assert "THE DENOMINATOR IS ZERO" in out and "Do not quote a zero from it" in out

    def test_a_diluted_pool_states_the_overstatement_factor(self):
        """The exact shape of both real errors: a big total, a small trigger population."""
        runs = [_run("book_read")] * 263 + [_run("jobs_get")] * 22
        out = M.format_report(M.trigger_matched(runs, {"jobs_get"}), {"jobs_get"})
        assert "overstates the sample 13x" in out
        assert "Quote 22, not 285" in out

    def test_an_undiluted_pool_is_NOT_nagged(self):
        """A guard that fires on a healthy sample gets deleted the first time it cries wolf."""
        runs = [_run("jobs_get")] * 20 + [_run("book_read")] * 5
        out = M.format_report(M.trigger_matched(runs, {"jobs_get"}), {"jobs_get"})
        assert "overstates" not in out and "DENOMINATOR IS ZERO" not in out
