"""D-EXTRACTION-CONFIRMS-A-NO-OP — a confirm card must represent work.

MEASURED 2026-08-14 at the tool boundary, on a throwaway book whose chapters had been removed:

    translation_start_extraction(book_id=<book>, chapter_ids=[])
      -> {"needs_confirm": true, "confirm_token": "..."}

and the token's own payload carried the estimate that proves it is a no-op:

    "estimate": {"chapters_count": 0, "llm_calls": 0, "estimated_total_tokens": 0,
                 "batches_per_chapter": 0, "calls_per_chapter": 0.0}

So the author is shown a card asking them to approve an extraction that will do nothing, and the
one gate they get is spent on a no-op. Worse, approving it hands the worker an empty plan — the
handler's own comment two lines below already notes that shape for the empty-PROFILE case:
"without this the worker plans 0 batches -> 0 entities".

THE INVARIANT: a confirm gate exists to obtain consent for WORK. A proposal whose own estimate is
zero is not a proposal, and must be refused at the point the arguments are read.

The sibling tool already gets this right and its message is the model to follow —
`glossary_propose_batch` refuses with "ops must not be empty — pass the operations to batch",
which names the missing input and what to do about it (C-12).
"""
from __future__ import annotations

import pathlib

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "app" / "mcp" / "server.py").read_text(encoding="utf-8")


def _handler() -> str:
    i = SRC.index("async def translation_start_extraction(")
    return SRC[i:i + 6600]


def test_an_empty_chapter_list_is_refused():
    """THE FALSIFIER. Without this the call mints a confirm_token over zero chapters."""
    h = _handler()
    assert "if not cids:" in h
    assert "chapter_ids must not be empty" in h


def test_the_refusal_comes_before_the_estimate_is_built():
    """A refusal that runs AFTER the cost projection has already done the work it exists to
    avoid — and, worse, could still fall through to minting the card."""
    h = _handler()
    guard = h.index("if not cids:")
    estimate = h.index("estimate = estimate_extraction_cost(")
    assert guard < estimate, "refuse on the arguments, before quoting a job that cannot run"


def test_the_message_names_the_missing_input_and_the_way_forward():
    """C-12: a refusal that names no field and no legal alternative leaves the caller with no
    move. The sibling batch tool's message is the standard here."""
    h = _handler()
    assert "name the chapters to extract from" in h
    assert "book_list_chapters" in h, "point at the tool that supplies the missing ids"


def test_it_says_nothing_was_charged():
    """This tool is cost-gated, so a refusal must make clear no spend occurred — otherwise the
    author cannot tell a refusal from a silently-failed paid run."""
    h = _handler()
    assert "nothing was charged" in h


def test_a_book_with_no_adopted_kinds_is_also_refused():
    """THE SAME INVARIANT ONE LAYER DEEPER, and the first guard did not reach it. Measured on a
    fresh throwaway immediately after fixing the empty-chapter_ids case: chapters_count 1,
    batches_per_chapter 0, llm_calls 0 — a card for a run that extracts nothing, because the book
    has no kinds to extract INTO. The handler already names this shape ("without this the worker
    plans 0 batches -> 0 entities") and then proceeded anyway."""
    h = _handler()
    assert "if not profile:" in h
    assert "no glossary kinds adopted yet" in h
    assert "glossary_adopt_standards" in h, "name the tool that fixes it (C-12)"


def test_both_refusals_say_nothing_was_charged():
    """Cost-gated: the author must be able to tell a refusal from a silently-failed paid run."""
    h = _handler()
    assert h.count("nothing was charged") == 2


def test_a_populated_chapter_list_is_untouched():
    """The guard must be exactly one condition. `cids` non-empty falls straight through to the
    existing profile/estimate path, so the happy case is byte-identical."""
    h = _handler()
    guard_block = h[h.index("if not cids:"):h.index("profile = extraction_profile or {}")]
    assert "raise ToolError(" in guard_block
    # nothing else may be conditioned on cids being empty
    assert guard_block.count("if ") == 1
