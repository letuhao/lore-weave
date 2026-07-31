"""translation-service's call-profile registry — the codes must match the call sites.

`budget_for` raises on an unknown code (deliberately — a silent fallback would re-introduce
the unattributed budget the registry removes). But nothing asserted that the codes the call
sites actually PASS exist in `PROFILES`, and two of those call sites are inside workers
processing a real user's chapter. A typo would have shipped as a runtime KeyError on a live
translation rather than a red test.

`/review-impl` also caught one of these labels being wrong: `decoupled_translate` routed its
translate branch to `translate_chunk`, but that branch threads `session_history` +
`compact_memo` through `build_chunk_messages` — it is a SESSION chunk. Both rows resolve to
MIRROR today, so the mismatch was invisible; it becomes a silent wrong-budget the moment
either row grows a real cap. That is what the call-site test below pins.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.llm_budget import PROFILES, budget_for

_APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def test_every_profile_resolves_to_the_omit_sentinel():
    """Translation length is set by the source text; the model's natural stop is the bound.
    0 is the platform's existing wire sentinel for "omit the cap" — the SDK strips it
    (loreweave_llm/models.py), so declaring it is byte-identical to omitting it."""
    assert PROFILES, "an empty registry would make budget_for unreachable"
    for code, budget in PROFILES.items():
        assert budget.max_output_tokens == 0, f"{code} resolved to {budget.max_output_tokens}"
        assert budget.source == "default", f"{code} has no recorded source"


def test_budget_for_raises_on_an_unknown_code():
    """A silent default here would quietly re-create the unattributed budget."""
    with pytest.raises(KeyError, match="unknown translation call profile"):
        budget_for("no_such_call")


def _call_site_codes() -> set[str]:
    """Every string literal passed to `budget_for(...)` anywhere in app/."""
    codes: set[str] = set()
    for p in _APP.rglob("*.py"):
        if "__pycache__" in p.as_posix():
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if fn != "budget_for":
                continue
            for arg in n.args:
                codes |= _literal_codes(arg)
    return codes


def _literal_codes(node: ast.AST) -> set[str]:
    """The string literals that can actually REACH `budget_for` as its argument.

    `budget_for(x if cond else y)` must contribute both branches — that conditional form is
    how `decoupled_translate` picks its profile, and walking only the outer node would miss
    it entirely. But a naive `ast.walk` over the whole expression also picks up the literal
    in the CONDITION (`action[0] == "compact"`), which is not a profile code at all — this
    test reported exactly that on its first run. So descend the branches, never the test."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _literal_codes(node.body) | _literal_codes(node.orelse)
    return set()


def test_every_call_site_code_exists_in_the_registry():
    used = _call_site_codes()
    assert used, "found no budget_for() call sites — the AST walk is not seeing them"
    missing = sorted(used - set(PROFILES))
    assert missing == [], f"call sites pass codes with no PROFILES row: {missing}"


def test_the_registry_has_no_row_nothing_uses():
    """A dead row is a budget decision nobody reads — the write-only-config smell."""
    unused = sorted(set(PROFILES) - _call_site_codes())
    assert unused == [], f"PROFILES rows no call site uses: {unused}"


def test_the_session_chunk_row_is_the_one_the_session_paths_use():
    """Pins the label `/review-impl` found wrong. Both the stateful session translator and
    the decoupled worker thread history + memo, so both take the session row; only the
    stateless `/translate-text` route takes `translate_chunk`."""
    used = _call_site_codes()
    assert "translate_session_chunk" in used, \
        "no call site uses the session row — the decoupled/session paths are mislabelled"


# ── the truncation signal MIRROR depends on ───────────────────────────────────────────────

class _FakeJob:
    def __init__(self, finish_reason=None):
        self.job_id = "job-1"
        self.finish_reason = finish_reason
        self.result = {
            "messages": [{"role": "assistant", "content": "translated"}],
            "usage": {"input_tokens": 10, "output_tokens": 9000},
        }


def test_a_provider_truncated_translation_is_reported_not_silent(caplog):
    """MIRROR sends no cap on purpose — correct everywhere except Anthropic, which has 8192
    substituted for a missing one (provider/adapters.go). Without this the clipped text was
    persisted as a COMPLETE translation. Advisory, so a detector never breaks a working path."""
    from app.workers.session_translator import _parse_sdk_response

    with caplog.at_level("WARNING"):
        content, _, out_tok = _parse_sdk_response(_FakeJob(finish_reason="length"))
    assert content == "translated", "the check must not swallow the text it is warning about"
    assert out_tok == 9000
    assert any("TRUNCATED" in r.message or "TRUNCATED" in r.getMessage()
               for r in caplog.records), "a truncated translation logged nothing"


def test_a_normal_completion_does_not_warn(caplog):
    """A warning on every call is a warning nobody reads."""
    from app.workers.session_translator import _parse_sdk_response

    with caplog.at_level("WARNING"):
        _parse_sdk_response(_FakeJob(finish_reason="stop"))
    assert not [r for r in caplog.records if "TRUNCATED" in r.getMessage()]


def test_a_job_with_no_finish_reason_attribute_does_not_crash():
    """The gateway's aggregators stamp `finish_reason`, but a degraded/older result may not
    carry one — a truncation DETECTOR that raises is worse than the truncation."""
    from app.workers.session_translator import _parse_sdk_response

    class _Bare:
        result = {"messages": [{"content": "x"}], "usage": {}}

    assert _parse_sdk_response(_Bare()) == ("x", 0, 0)
