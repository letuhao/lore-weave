"""A guard that reads a field its table does not have never fires.

DQ-T58, owner 2026-08-28: "DECLARE THE ARC PHRASING ... so the turn reaches the tool and the
author gets an EXPLICIT refusal naming chapters", with the bar that "a refusal that does not name
chapters leaves the author exactly as stuck."

    THE INVARIANT. A guard's condition is written against a key the record actually carries.

🔴 THE REFUSAL WAS SHIPPED ON 2026-08-30 AND HAD NEVER FIRED. Its condition was

    if _sn is not None and getattr(_sn, "project_id", None) == pid:

and `StructureNode`'s own docstring says the field is deliberately absent: "`book_id` is the
SCOPE key, set directly -- NO composition_work join, NO project_id, NO user_id". So `getattr`
returned None, None != pid, and every arc fell through to the uniform "not found or not
accessible" -- the exact dead end the ruling exists to replace.

MEASURED by driving the call directly, no model in the loop
(scripts/toolloop/t58_arc_refusal_probe.py): seed an arc, bind a motif to it, and the answer was
"not found or not accessible" with none of the four things the ruling requires. The row had
attributed the silence to the model never forming the call -- which is true, and was hiding this.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

from app.mcp import server as mcp

SRC = pathlib.Path(inspect.getfile(mcp)).read_text(encoding="utf-8")


def _fn(name: str):
    for n in ast.walk(ast.parse(SRC)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"{name} not found — renamed?")


class TestTheGuardReadsAKeyTheRecordHas:
    def test_it_does_not_read_project_id_off_a_structure_node(self):
        """The exact defect. `structure_node` has no such column — verified against the live
        schema, and asserted by the model's own docstring."""
        body = ast.unparse(_fn("composition_motif_bind"))
        assert 'getattr(_sn, \'project_id\'' not in body and \
               'getattr(_sn, "project_id"' not in body, (
            "the arc guard reads _sn.project_id, a field StructureNode documents as deliberately "
            "absent — the condition can never be true and the refusal can never fire")

    def test_it_scopes_by_the_BOOK(self):
        body = ast.unparse(_fn("composition_motif_bind"))
        assert "book_id" in body and "meta.book_id" in body, (
            "the arc guard does not compare the node's book to the Work's book, which is the "
            "only scope key the structure tree has")

    def test_the_model_still_declares_no_project_id(self):
        """🔴 THE FIX RESTS ON A FACT ABOUT ANOTHER MODULE, so the fact is asserted rather than
        remembered. If StructureNode ever gains a project_id, this guard should be revisited
        deliberately instead of silently becoming right for a new reason."""
        from app.db.models import StructureNode

        assert "project_id" not in StructureNode.model_fields, (
            "StructureNode now HAS a project_id — re-read the arc guard, which was written "
            "because it did not")
        assert "book_id" in StructureNode.model_fields


class TestTheRefusalStillSaysWhatItWasRuledToSay:
    def test_it_names_the_kind_the_chapter_and_the_lister(self):
        """The ruling's bar, unchanged: 'a refusal that does not name chapters leaves the author
        exactly as stuck.' Read from the string CONSTANTS, so a reflow cannot break the match."""
        fn = _fn("composition_motif_bind")
        joined = " ".join(
            " ".join(c.value.split()) for c in ast.walk(fn)
            if isinstance(c, ast.Constant) and isinstance(c.value, str))
        assert "binds a motif to a CHAPTER" in joined, "the refusal does not name CHAPTER"
        assert "composition_list_outline" in joined, "it does not name how to list chapters"
        assert "not something this platform defines" in joined or "not guessed" in joined, (
            "it does not say the arc semantic is deliberately not guessed, which is the half the "
            "owner explicitly declined to invent")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
