"""DQ-T54, answered by the owner 2026-08-28.

    "APPEND A DETERMINISTIC SERVER-SIDE LINE to a turn suspended on a Tier-A card — 'Nothing has
     been saved yet; confirm the card above to apply it.'"

The owner declined (b) spending an extra tool-free model pass — 98 extra passes to correct 6
messages, a 16:1 ratio — and declined (c) leaving it to the FE card.

WHY A SERVER LINE AND NOT A PROMPT: when a turn SUSPENDS, the model has already written its
reply and the loop returns without a further pass, so there is no prompt left to steer. Verified
in code: the Tier-W/S confirm path DOES continue and IS already told (`_CONFIRM_CARD_STOP_NOTE`),
which is why that existing remedy could only be mirrored, never extended.

MEASURED: 98 turns ended with a card pending and a non-empty reply; 6 claimed completion with
nothing written and not one mentioned approval. Caught live in c-armrefusal2 — "I've updated
Aldric Vane's occupation to cartographer" while the card sat unclicked.

🔴 THE BUILD NOTE IS THE SUBTLE PART, and it is the owner's: the line must fire on SUSPENSION,
"not on the presence of a card, or a turn whose card was approved in-flight gets told nothing was
saved when it was". The suspend branch runs at the instant the turn suspends, so the statement is
true by construction — the pending call has not executed.
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")


def _suspend_branch() -> str:
    """The suspend branch ONLY — from the pending unpack to the branch's own `return`.

    🔴 THE FIRST VERSION OF THIS SLICE ENDED AT the clean-finish comment, which sits BELOW the
    branch's return — so it swallowed the neighbouring DQ-T33 block and two tests failed on
    code that is not in the branch at all. A slice that reads more than it names produces
    findings about the wrong region.
    """
    marker = "\n            return\n"
    i = SRC.index('pending = suspend_state["pending_tool_call"]')
    j = SRC.index(marker, i) + len(marker)
    return SRC[i:j]


def _constant_body() -> str:
    """Just the parenthesised body of the author-facing constant."""
    i = SRC.index("_NOTHING_SAVED_YET_LINE = (")
    return SRC[i:SRC.index(")", SRC.index('"', i)) + 1]


class TestTheLineItself:
    def test_it_is_the_owners_sentence_verbatim(self):
        """🔴 NOT PARAPHRASED. This loop's standing rule is that it does not invent user-facing
        prose; the one sentence it may show is the one the owner wrote."""
        m = re.search(r"_NOTHING_SAVED_YET_LINE = \(\s*\n\s*(\".*?\")\s*\n\)", SRC, re.S)
        assert m, "the constant is gone or reshaped"
        assert m.group(1) == (
            '"\\n\\nNothing has been saved yet; confirm the card above to apply it."'
        ), m.group(1)

    def test_it_carries_real_escapes_not_literal_newlines(self):
        """A heredoc-generated constant has shipped literal newlines into a string in this repo
        before; the separator must be an ESCAPE the file can round-trip."""
        i = SRC.index("_NOTHING_SAVED_YET_LINE = (")
        body = SRC[i:i + 200]
        assert "\\n\\nNothing has been saved" in body


class TestItFiresOnSUSPENSION:
    """The owner's build note, and the reason the trigger is not 'a card exists'."""

    def test_the_append_is_inside_the_suspend_branch(self):
        assert "full_content.append(_NOTHING_SAVED_YET_LINE)" in _suspend_branch(), (
            "the line is appended outside the suspend branch — it can now fire on a turn whose "
            "card was approved in-flight, telling the author nothing was saved when it was"
        )

    def test_it_is_appended_BEFORE_the_awaiting_input_persist(self):
        """A reload must show the same text the live stream did; if the persist runs first the
        stored message and the streamed one disagree."""
        b = _suspend_branch()
        assert b.index("full_content.append(_NOTHING_SAVED_YET_LINE)") < b.index(
            'finish_reason="awaiting_input"')

    def test_it_is_emitted_BEFORE_the_message_is_closed(self):
        """Emitted after close_message() it would land outside the frame the FE renders."""
        b = _suspend_branch()
        assert b.index("emitter.text_delta(_NOTHING_SAVED_YET_LINE)") < b.index(
            "emitter.close_message()")

    def test_the_clean_finish_path_does_NOT_get_it(self):
        """A turn that finished normally saved whatever it wrote. Telling it 'nothing has been
        saved' would be false — the exact inversion the owner's build note warns about."""
        i = SRC.index("# ARCH-1 C3: token stream is done")
        assert "_NOTHING_SAVED_YET_LINE" not in SRC[i:]


class TestItDoesNotDisturbTheNeighbouringMechanisms:
    def test_the_model_facing_note_is_still_a_separate_string(self):
        """`_CONFIRM_CARD_STOP_NOTE` steers the MODEL on the path that continues; this one is
        read by the AUTHOR on the path that stops. Collapsing them would put a system directive
        in front of a person."""
        assert "_CONFIRM_CARD_STOP_NOTE" in SRC and "_NOTHING_SAVED_YET_LINE" in SRC
        assert "[SYSTEM" in SRC[SRC.index("_CONFIRM_CARD_STOP_NOTE = ("):][:400]
        assert "[SYSTEM" not in _constant_body(), (
            "the author-facing line has acquired system-directive markup"
        )

    def test_the_silent_turn_fallback_is_a_different_line_on_a_different_path(self):
        """DQ-T33's fallback speaks a TOOL ERROR on a turn with no card; this speaks platform
        state on a turn that suspended. Both must not fire on the same turn — the suspend branch
        returns before the silent-turn site."""
        b = _suspend_branch()
        assert "_last_tool_error_for_author" not in b
