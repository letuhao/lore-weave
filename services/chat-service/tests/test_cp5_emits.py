"""CP-5.6 (second half) — an `emits` path checked at PLAN-BUILD time, not at execution.

🔴 **§2's INVERSION, TURNED BACK.** CP-3 declares an `emits` path as a literal string and
`check_emit_path` can only prove it is *syntactically* a path. It cannot prove the path EXISTS,
because until CP-5 no tool declared a result shape — so `EmitPathError` fired at **execution**, a
runtime failure that was built and written up as a feature while §6.2's principle is *"a generation
error, not a runtime one"*.

🔴 **AND THE DECLARATION HAD TO BE VERIFIED BEFORE IT COULD BE TRUSTED.** The first five contracts
authored for this were written from each tool's DESCRIPTION, and **four of the five were wrong**
against recorded results: `book_list` returns `{books, total}`, not `{items, page}`. A declared
shape nobody checks is a lie that looks like a contract — and it would have made this check reject
the one emit path CP-3 actually uses.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.agentruntime.plan import EmitPathError, check_emit_against_contract, check_emit_path

REGISTRY = (pathlib.Path(__file__).resolve().parents[3]
            / "contracts" / "agent-runtime-tool-contracts.json")


def contracts() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["contracts"]


def declared(tool: str) -> list[str]:
    return contracts()[tool]["output_contract"]["emit_paths"]


class TestAPathIsCheckedAgainstTheDeclaredOutput:

    def test_A_DECLARED_PATH_PASSES(self):
        check_emit_against_contract("book_list", "book_id", "books[0].book_id",
                                    declared("book_list"))

    def test_AN_UNDECLARED_PATH_IS_REFUSED_AT_PLAN_BUILD(self):
        with pytest.raises(EmitPathError, match="does not declare an output"):
            check_emit_against_contract("book_list", "x", "volumes[0].id", declared("book_list"))

    def test_THE_REFUSAL_SHOWS_WHAT_IS_DECLARED(self):
        """C-12 — the rejection names what WOULD be legal, or the author has to guess."""
        with pytest.raises(EmitPathError) as exc:
            check_emit_against_contract("book_list", "x", "nope", declared("book_list"))
        assert "books[0].book_id" in str(exc.value)

    def test_A_TOOL_THAT_DECLARES_NOTHING_IS_NOT_BLOCKED(self):
        """Deliberate: six of eleven essential tools are not admitted yet and most of the
        catalogue declares nothing. Refusing their plans would make this member a migration
        blocker rather than a contract — declaring EARNS the earlier error."""
        check_emit_against_contract("some_unmigrated_tool", "x", "anything.at.all", None)
        check_emit_against_contract("some_unmigrated_tool", "x", "anything.at.all", [])

    def test_THE_SYNTAX_CHECK_STILL_RUNS_FIRST(self):
        """The two checks answer different questions and both must hold: `is it a path` and `does
        that path exist`. A declared path that is not a path is still refused."""
        with pytest.raises(EmitPathError):
            check_emit_path("book_list", "book_id", "books[?title=~x].book_id")


class TestTheDeclarationItselfIsVerified:
    """The lesson this row cost: an unverified declaration is worse than none."""

    def test_EVERY_DECLARED_EMIT_PATH_IS_SYNTACTICALLY_A_PATH(self):
        for tool, block in contracts().items():
            for path in block.get("output_contract", {}).get("emit_paths", []):
                check_emit_path(tool, "declared", path)

    def test_EVERY_DECLARED_EMIT_PATH_STARTS_INSIDE_THE_DECLARED_SHAPE(self):
        """A path whose first segment is not in the declared shape is a contract that contradicts
        itself — which is exactly what four of the first five contracts did."""
        for tool, block in contracts().items():
            oc = block.get("output_contract", {})
            shape, paths = oc.get("shape", ""), oc.get("emit_paths", [])
            for path in paths:
                root = path.split(".")[0].split("[")[0]
                assert root in shape, (
                    f"{tool} declares emit path {path!r} whose root {root!r} does not appear in "
                    f"its own declared shape {shape!r}"
                )

    def test_THE_SHAPES_RECORD_THAT_THEY_WERE_VERIFIED_AGAINST_REAL_RESULTS(self):
        for tool, block in contracts().items():
            oc = block.get("output_contract", {})
            if oc.get("emit_paths"):
                assert "_verified_against" in oc, (
                    f"{tool}'s output contract does not say what its shape was checked against; "
                    f"four of the first five were wrong when taken from the tool's description"
                )
