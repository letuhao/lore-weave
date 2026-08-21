"""A tool description that names an `op` its own enum lacks sends the model to a dead end.

FOUND LIVE 2026-08-21, deriving batch 28. `book_structure_edit` ends its description with:

    "To DELETE a part, use this same tool's archive op - there is no separate delete tool."

Both halves are false, and the file itself proves it. The `op` enum declared eleven lines below
that sentence is {create_part, rename_part, reorder_parts, home_chapter, reorder_chapters}, the
Go switch has exactly those five cases, and the file's OWN header comment says the opposite of
its description:

    "Destructive part-archive is the separate visibility:legacy book_structure_part_archive
     (CAT-2 destructive split)."

So an author who says "delete Book One" gets a model that reads the description, sends
op="archive", and is refused by the closed set. It will not then go looking for the real tool,
because the same sentence told it no such tool exists.

WHY THAT SECOND CLAUSE IS THE WORSE HALF. `book_structure_part_archive` is visibility:legacy -
it is NOT in the default tool_list. A legacy tool is reachable only by tool_load, and only if
the model knows its NAME. The description is the one place that name could have come from, and
it denies the tool exists. A real capability with its only signpost pointing the wrong way is
the shape this loop already named D-RESTORE-WITH-NO-WAY-TO-SEE-WHAT-IS-RESTORABLE.

THE INVARIANT, AND WHY IT IS THE CONVERSE OF AN EXISTING ONE. book-service already has
TestEveryEnumeratedClosedSetHasAnEnum: a closed set written in prose must also be declared as a
real enum, so the validator can hold it. That catches prose the schema does not back. It cannot
catch this - prose that CONTRADICTS the schema it does have. Same seam, opposite direction:

    that gate: description enumerates X  =>  enum must exist
    this gate: description names op X    =>  X must be IN the enum

MEASURED ACROSS ALL TEN PROVIDERS: 19 tools carry an `op` enum; exactly ONE names an op it does
not have. The gate therefore ships at zero baseline - unlike the undeclared-required-args gate
beside it, there is nothing here to freeze, so any future violation is a regression.

WHY THE DETERMINER. The naive pattern (<token> followed by "op") fires on ordinary English:
"...via op=create" reads as the token `via`, "...then op" as `then`. Requiring a determiner -
"the archive op", "this tool's archive op", "its archive op" - is what an author actually writes
when directing the model to an operation, and it drops all seven false positives while keeping
the one true one.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

# "the archive op" / "this same tool's archive op" / "its archive op".
_DETERMINER = r"(?:the|this|that|its|a|an|[a-z]+'s)"
_NAMED_OP = re.compile(rf"\b{_DETERMINER}\s+([a-z][a-z0-9_]{{2,}})\s+op\b", re.IGNORECASE)


def _catalog() -> dict:
    try:
        import catalog  # noqa: PLC0415 - the cache reader lives beside the loop
        return catalog.load()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"catalogue unavailable: {exc}")


def _op_enum(tool: dict) -> set[str]:
    props = (tool.get("inputSchema") or {}).get("properties") or {}
    return set(((props.get("op") or {}).get("enum")) or [])


def _offenders(cat: dict) -> dict[str, tuple[list[str], list[str]]]:
    """{tool: (ops named in prose but absent from the enum, the real enum)}."""
    out: dict[str, tuple[list[str], list[str]]] = {}
    for name, tool in cat.items():
        enum = _op_enum(tool)
        if not enum:
            continue
        named = {m.group(1).lower() for m in _NAMED_OP.finditer(tool.get("description") or "")}
        missing = sorted(named - enum)
        if missing:
            out[name] = (missing, sorted(enum))
    return out


@pytest.fixture(scope="module")
def cat() -> dict:
    return _catalog()


class TestNoDescriptionNamesAnOpItDoesNotHave:
    def test_the_whole_federated_catalogue_is_clean(self, cat):
        bad = _offenders(cat)
        assert not bad, "\n".join(
            f"{tool}: description names {missing!r}, but its op enum is {enum!r}"
            for tool, (missing, enum) in sorted(bad.items()))

    def test_book_structure_edit_specifically(self, cat):
        """The tool the gate was written for - kept as its own case so a regression here is
        named rather than buried in a catalogue-wide diff."""
        tool = cat.get("book_structure_edit")
        if tool is None:
            pytest.skip("book_structure_edit not in the catalogue")
        named = {m.group(1).lower() for m in _NAMED_OP.finditer(tool.get("description") or "")}
        assert "archive" not in named, (
            "book_structure_edit still directs the model to an `archive` op it does not have; "
            "the real one is the separate visibility:legacy book_structure_part_archive")

    def test_it_does_not_deny_the_tool_that_exists(self, cat):
        """The clause that suppressed discovery. book_structure_part_archive IS a separate tool,
        and being visibility:legacy it is absent from the default tool_list - so a description
        claiming it does not exist removes the only pointer to its name."""
        tool = cat.get("book_structure_edit")
        if tool is None:
            pytest.skip("book_structure_edit not in the catalogue")
        desc = (tool.get("description") or "").lower()
        assert "no separate delete tool" not in desc, (
            "the description denies a tool that exists (book_structure_part_archive)")


class TestTheGateCanActuallyFail:
    """A gate nobody has watched go red is a gate nobody knows works."""

    def test_it_catches_the_original_defect_verbatim(self):
        original = ("Reorganize the manuscript STRUCTURE. `op` selects the operation: create_part "
                    "(title) . rename_part (part_id, title). Every op is reversible (Undo). "
                    "To DELETE a part, use this same tool's archive op - there is no separate "
                    "delete tool.")
        synthetic = {"book_structure_edit": {
            "description": original,
            "inputSchema": {"properties": {"op": {"enum": [
                "create_part", "rename_part", "reorder_parts", "home_chapter",
                "reorder_chapters"]}}}}}
        bad = _offenders(synthetic)
        assert "book_structure_edit" in bad
        assert bad["book_structure_edit"][0] == ["archive"]

    def test_it_does_not_fire_on_ordinary_english(self):
        """The seven false positives the determiner rule drops: `via op=create`, `then op`."""
        benign = {"composition_arc_edit": {
            "description": "Edit an arc. Delete it via op=delete, then op=restore brings it back.",
            "inputSchema": {"properties": {"op": {"enum": ["delete", "restore"]}}}}}
        assert _offenders(benign) == {}

    def test_a_tool_with_no_op_enum_is_out_of_scope(self):
        assert _offenders({"x": {"description": "use the archive op", "inputSchema": {}}}) == {}
