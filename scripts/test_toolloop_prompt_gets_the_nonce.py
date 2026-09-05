"""A scenario PROMPT that names its own fixture must get the same substitution the seed did.

FOUND 2026-08-21, and it cost the whole of batch 29. Five ACCOUNT-scoped scenarios (world/map
tools, scope=none) named their fixture "Emberfall Reach {run_id}" so the seeded world would be
unique among the account's 200 - the lesson batch 20 paid for, where a fixed account-scoped code
collided with itself across repeats. The SEED expanded the nonce and created "Emberfall Reach
a1b2c3". The PROMPT did not, so the model was asked about "Emberfall Reach {run_id}" literally.

Every one of the 25 runs was measured against a world that existed under a different name.

THE MODEL WAS RIGHT EVERY TIME, which is what made this so easy to misread:

    "I can't open the map using `{run_id}` because that looks like a placeholder."
    "I need its unique ID, and 'Emberfall Reach {run_id}' is not a valid ID."

That is the invented-id guard behaving exactly as designed - the same guard this loop added arms
to (nil-UUID, whitespace, declared-UUID, placeholder tokens, SCREAMING_SNAKE). Read without the
fixture in mind, the batch looked like five tools failing to resolve a name. It was one harness
gap, and the tools were never exercised at all.

THE FIX IS AT THE CHOKEPOINT. `Throwaway._substitute` already expanded {book_id}, {chapter_id},
{project_id}, {step:N:path} and {run_id} for seeds; the prompt simply never went through it. A
nonce the seed expands and the prompt does not makes an account-scoped scenario impossible to
write correctly, so the prompt now goes through the same substitution rather than each scenario
working around it.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

FE_RUNNER = ROOT / "scripts" / "toolloop" / "fe_runner.py"
PROVISION = ROOT / "scripts" / "toolloop" / "provision.py"


class _FakeFixture:
    """Only the substitution surface, so the test needs no live stack."""

    def __init__(self):
        import provision  # noqa: PLC0415

        self._t = provision.Throwaway.__new__(provision.Throwaway)
        self._t.run_id = "a1b2c3d4"
        self._t.run_word = provision._pronounceable("a1b2c3d4")
        self._t.book_id = "BOOK"
        self._t.chapter_id = "CHAP"
        self._t.project_id = "PROJ"
        self._t._steps = []

    def substitute_text(self, s):
        return self._t.substitute_text(s)


class TestTheFixtureCanSubstituteAPrompt:
    def test_run_id_is_expanded(self):
        fx = _FakeFixture()
        assert fx.substitute_text("Show me the world called Emberfall Reach {run_id}.") == (
            "Show me the world called Emberfall Reach a1b2c3d4.")

    def test_the_other_ids_are_expanded_too(self):
        fx = _FakeFixture()
        assert fx.substitute_text("{book_id}/{chapter_id}/{project_id}") == "BOOK/CHAP/PROJ"

    def test_a_prompt_with_no_placeholder_is_untouched(self):
        fx = _FakeFixture()
        plain = "Delete the map called The Obsidian Trench."
        assert fx.substitute_text(plain) == plain

    def test_no_placeholder_survives_substitution(self):
        """The exact string the model objected to must not be able to reach it again."""
        fx = _FakeFixture()
        out = fx.substitute_text("Delete my world called Emberfall Reach {run_id}.")
        assert "{run_id}" not in out


class TestTheRunnerActuallyUsesIt:
    """A helper nobody calls is the defect, not the fix — guard the CALL SITE."""

    def test_the_turns_list_is_substituted(self):
        src = FE_RUNNER.read_text(encoding="utf-8")
        m = re.search(r"^\s*turns = .*$", src, re.MULTILINE)
        assert m, "the `turns = ...` line is gone — find where prompts are built and re-point this"
        assert "substitute_text" in m.group(0), (
            "the prompt list no longer goes through the fixture's substitution; a scenario that "
            "names its own {run_id}-suffixed fixture will be asked about the literal placeholder")

    def test_the_reason_is_recorded_beside_it(self):
        src = FE_RUNNER.read_text(encoding="utf-8")
        assert "placeholder" in src and "batch 29" in src, (
            "the comment explaining what an unsubstituted prompt cost is gone")

    def test_substitute_text_is_public_on_the_fixture(self):
        src = PROVISION.read_text(encoding="utf-8")
        assert "def substitute_text(self" in src
