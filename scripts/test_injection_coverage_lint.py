"""Teeth for `injection-coverage-lint.py` — S4.

The lint had none, and it needed them: every one of its three signals was matched against
RAW FILE TEXT, so comments and docstrings were read as evidence about behaviour. That is
wrong in both directions, and only one of them is loud.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "inj", pathlib.Path(__file__).resolve().parent / "injection-coverage-lint.py"
)
inj = importlib.util.module_from_spec(_SPEC)
# Registered BEFORE exec, and it is load-bearing rather than tidy. The lint declares a
# `@dataclass` under `from __future__ import annotations`, so its field types are strings and
# `dataclasses._is_type` resolves them via `sys.modules[cls.__module__].__dict__`. Absent that
# entry it dereferences None, and the failure lands at COLLECTION — which aborts the whole
# `-q` batch this file shares with fourteen other gate-test files in `foundation-ci.yml`, so
# none of them run. Found by an audit sweep on 2026-08-02; the same workflow's own comment
# says "148 tests across 8 files, and not one of them ran anywhere".
sys.modules[_SPEC.name] = inj
_SPEC.loader.exec_module(inj)


def _flags(src: str) -> bool:
    """True ⇒ the lint would flag a module with this source."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(src)
        path = fh.name
    try:
        assembles, retrieved, sanitized = inj.classify_file(path)
        return assembles and retrieved and not sanitized
    finally:
        os.unlink(path)


_ASSEMBLE = 'return [{"role": "system", "content": passage}]'


def test_a_real_unsanitized_assembly_is_FLAGGED():
    """The gate's whole job. If this ever goes clean the rest of the file is decoration."""
    assert _flags(f"def f(passage):\n    {_ASSEMBLE}\n") is True


def test_a_real_sanitizer_call_clears_it():
    assert _flags(
        f"def f(passage):\n    passage = neutralize(passage)\n    {_ASSEMBLE}\n"
    ) is False


# ── prose is not behaviour, in BOTH directions ────────────────────────────────────────────

@pytest.mark.parametrize("prose", [
    "    # this builds the prompt from a passage\n",
    '    """Folds the retrieved passage into a prompt."""\n',
])
def test_a_marker_that_appears_only_in_PROSE_does_not_flag(prose):
    """The false positive. MEASURED 2026-08-02: three modules were flagged — or carried a
    BASELINE row calling them a "genuine gap" — on the strength of a marker word appearing
    ONLY in a comment, with zero occurrences in code. One of them was reddened by a comment
    added in an unrelated slice earlier the same day.
    """
    src = f'def f(x):\n{prose}    return [{{"role": "system", "content": x}}]\n'
    assert _flags(src) is False


def test_a_sanitizer_claimed_only_in_a_COMMENT_still_FLAGS():
    """The false NEGATIVE, and the dangerous half.

    `SANITIZER_REF` matched raw text too, so a module whose only mention of `neutralize(` was
    in a comment counted as PROTECTED. Measured today: zero files exploited this — but nothing
    prevented it, and a security gate that can be silenced by a sentence is worse than no gate
    because it reports coverage. Same rule the deferral registry enforces: a claim in a
    comment is not a mechanism.
    """
    src = (f"def f(passage):\n"
           f"    # neutralize(passage) already happened upstream, honest\n"
           f"    {_ASSEMBLE}\n")
    assert _flags(src) is True


def test_a_docstring_claiming_sanitization_still_FLAGS():
    src = (f'def f(passage):\n'
           f'    """Safe — the caller ran neutralize_injection(passage) first."""\n'
           f"    {_ASSEMBLE}\n")
    assert _flags(src) is True


# ── what the detector deliberately does NOT do ────────────────────────────────────────────

def test_an_UPPERCASE_marker_in_a_prompt_template_is_not_a_signal():
    """Pinned as a KNOWN LIMIT, not as correct-by-design perfection.

    `RETRIEVED_TEXT` matches identifier-shaped names (`passage`, `chunk_text`), so a template
    string `"PASSAGE:\n" + x` does not register — and never did, before or after the prose
    fix. I expected it to flag while writing these teeth; measuring showed the detector had
    always behaved this way, so this records the real boundary rather than my assumption
    about it. Widening the regex to catch it is a separate change with its own false-positive
    budget.
    """
    src = 'def f(x):\n    return [{"role": "system", "content": "PASSAGE:\n" + x}]\n'
    assert _flags(src) is False


def test_an_unparseable_file_falls_back_to_RAW_text():
    """The conservative direction. If the source cannot be tokenized or parsed, prose is not
    stripped — so a syntax error cannot be used to hide a marker from the scan."""
    src = "def f(passage):\n    this is not python(((\n"
    lines = inj._code_lines(src)
    assert any("passage" in ln for ln in lines), "a broken file lost its markers"


# ── the baseline must be able to shrink ───────────────────────────────────────────────────

def test_no_baseline_row_is_stale():
    """Every row is documented as "a tracked hole". A row for a module the scan no longer
    flags is a claim about a hole that does not exist — and it is a live exemption that would
    silence the gate if that module ever grew a real one. Two were found on 2026-08-02.

    Runs the REAL full scan (`iter_full_scan`), not a reconstruction of it. The first draft
    guarded on `hasattr(inj, "iter_files")` — a name that does not exist — so it SKIPPED, and
    a skipped test reads as a passing one. That is the exact shape ROT-0 audited 200 tests for.
    """
    stale = sorted(set(inj.BASELINE) - set(inj.flagged_files(inj.iter_full_scan())))
    assert stale == [], f"BASELINE rows no longer flagged: {stale}"
