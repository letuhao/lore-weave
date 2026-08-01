"""A draft that produced tokens but no prose is a FAILURE, not a completed job.

Found by writing a scene through the GUI as a real author. The job recorded

    {"text": "", "truncated": true, "finish_reason": "length", "output_tokens": 800}

with `status: completed`. The compose panel returned to "Ready to draft", the author was billed for
800 output tokens, and nothing anywhere said a word. It is the silent-success law's exact violation,
on the surface an author touches most.

`cowrite` already NAMES the cause in a comment — "the whole budget spent on reasoning_tokens (empty
ghost)" — because `parts` collects only `token` deltas and never `reasoning` ones. Naming it was not
the same as checking for it.
"""

from __future__ import annotations

from app.routers.engine import _empty_draft_error


def test_prose_is_a_success_however_short():
    assert _empty_draft_error("Mira audits the ledger.", 12, "stop") is None
    assert _empty_draft_error("x", 1, "length") is None


def test_whitespace_only_is_NOT_prose():
    """A draft of newlines renders as an empty scene and bills like a real one."""
    assert _empty_draft_error("   \n\n\t ", 40, "stop") is not None


def test_tokens_but_no_text_names_the_LIKELY_CAUSE_and_the_fix():
    """An error the author cannot act on is barely better than silence."""
    msg = _empty_draft_error("", 800, "length")
    assert msg is not None
    assert "800" in msg, "the author paid for these — say how many"
    assert "reasoning" in msg, "the empty-ghost cause is nameable; name it"
    assert "Nothing was written" in msg, "say plainly that no work survived"


def test_no_tokens_and_no_text_is_a_DIFFERENT_message():
    """Zero output is a dead call, not a budget burned on hidden thinking. Conflating them sends the
    author to change a reasoning setting that had nothing to do with it."""
    msg = _empty_draft_error("", 0, None)
    assert msg is not None and "reasoning" not in msg


def test_BOTH_streaming_completion_sites_are_guarded():
    """There are two, and fixing one would leave the other reporting a phantom success. Asserted on
    the source because the sites are inside long SSE generators."""
    import inspect

    from app.routers import engine

    src = inspect.getsource(engine)
    # every place that completes a draft job must consult the guard first
    completions = src.count('await jobs.update_status(job.id, "completed", result=result)')
    guards = src.count("_empty_draft_error(final[\"text\"]")
    assert guards >= completions, (
        f"{completions} streaming completion(s) but only {guards} empty-draft guard(s)"
    )
