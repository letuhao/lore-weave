"""DQ-T58 (owner 2026-08-28) — an arc is not a chapter, and the refusal must SAY so.

    THE INVARIANT. A motif-bind aimed at something that is not a chapter refuses in words that
    name what the tool DOES bind to.

OWNER: "DECLARE THE ARC PHRASING on composition_motif_bind_edit so the turn reaches the tool and
the author gets an EXPLICIT refusal naming chapters. The tool is not taught to accept an arc."
The owner declined inventing the semantic — is a motif on an arc a property of the arc, or a
shortcut for its chapters? nothing in the model defines it — and declined leaving the request
unreachable. The bar is stated in the ruling: "a refusal that does not name chapters leaves the
author exactly as stuck."

WHAT IT WAS BEFORE. Arcs live in `structure_node` (arc / part / saga) and chapters in
`outline_node` (chapter / scene), and MEASURED against the live store, ZERO ids appear in both:

    outline_node    chapter 255 · scene 385
    structure_node  arc 152 · part 36 · saga 4
    ids in both     0

So an arc id reached `outline.get_node()`, came back None, and took the uniform
not-accessible path — "not found or not accessible", which tells the author nothing about
chapters and is exactly the refusal the ruling rejects.

🔴 THIS FILE READS THE SOURCE, NOT A LIVE CALL, and says so rather than implying more. The
handler needs a pool, a grant check and two repositories; asserting the refusal TEXT and the
declaration is what a unit test can honestly hold. The live half is a batch, recorded on the row.
"""
from __future__ import annotations

import pathlib

SRC = (pathlib.Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py").read_text(
    encoding="utf-8")


def _bind_handler() -> str:
    """The WHOLE handler, via AST.

    🔴 THIS SLICED 2,600 CHARACTERS FROM AN ANCHOR AND THREE OF THIS FILE'S FOUR
    ASSERTIONS WENT RED WHEN A COMMENT WAS ADDED ABOVE THE REFUSAL. The refusal text had not
    changed; it had moved past the end of the window. A fixed-width window over source is an
    instrument that reports on its own boundaries, and this file's messages ("the refusal no
    longer names chapters") would have sent the next reader after a regression that did not
    exist."""
    import ast

    for n in ast.walk(ast.parse(SRC)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and                 n.name == "composition_motif_bind":
            return ast.unparse(n)
    raise AssertionError("composition_motif_bind not found — renamed?")


class TestTheRefusalNamesWhatTheToolDoesBindTo:
    def test_an_arc_id_is_told_it_is_an_arc_and_that_chapters_are_the_target(self):
        block = _bind_handler()
        assert "binds a motif to a CHAPTER" in block, (
            "the refusal no longer names chapters — DQ-T58's whole bar is that it must")
        assert "composition_list_outline" in block, (
            "the refusal names no way to GET a chapter's node_id, which leaves the author as "
            "stuck as the uniform message did")

    def test_it_does_not_silently_guess_the_semantic(self):
        """The owner declined inventing it. The refusal must say that is why, or the next reader
        will assume nobody thought about it."""
        block = _bind_handler()
        assert "not something this platform defines" in block

    def test_a_SCENE_is_refused_too_and_by_the_same_words(self):
        """`outline_node` holds scenes as well as chapters. A scene is not a chapter either, and
        an author who passes one deserves the same sentence rather than a silent bind."""
        block = _bind_handler()
        # Quote-agnostic: the block now comes from `ast.unparse`, which normalises string
        # quoting, so a test written against the source's double quotes would fail on a
        # formatting difference and read as a missing guard.
        assert ('node.kind != "chapter"' in block or "node.kind != 'chapter'" in block), (
            "only the arc case is handled — a scene node_id would still fall through to the bind")

    def test_the_uniform_refusal_still_covers_a_genuinely_unknown_id(self):
        """🔴 THE SECURITY HALF, and it must not be traded for a friendlier message. An id that
        belongs to NOBODY, or to another user's project, must keep the uniform not-accessible
        answer — telling a caller 'that is an arc' about a row they cannot see is a disclosure."""
        block = _bind_handler()
        assert block.count("uniform_not_accessible()") >= 2, (
            "the not-accessible path was collapsed; an unknown or foreign id must still get the "
            "uniform answer")
        # 🔴 THIS ASSERTION PINNED A CONDITION THAT COULD NEVER BE TRUE. It required
        # `getattr(_sn, "project_id", None) == pid`, and StructureNode's own docstring says the
        # field is deliberately absent: "`book_id` is the SCOPE key, set directly — NO
        # composition_work join, NO project_id, NO user_id". So the scope check always failed,
        # every arc fell through to the uniform refusal, and the arc-shaped message this file
        # exists to guard had NEVER FIRED — proven 2026-09-01 by driving the call directly
        # (scripts/toolloop/t58_arc_refusal_probe.py): an arc got "not found or not accessible"
        # with none of the four things the ruling requires.
        #
        # THE SECURITY INTENT IS UNCHANGED AND IS NOW ACTUALLY ENFORCED. The scope key for the
        # structure tree is the BOOK, and `_book_or_deny` has already verified the caller holds
        # EDIT on that book — so comparing the arc's book to the gated book confirms nothing the
        # caller cannot already see. An arc in another book still gets the uniform answer.
        assert "getattr(_sn, 'book_id', None) == meta.book_id" in block, (
            "the arc-shaped refusal is not scoped to the caller's own book — it would confirm "
            "the existence of an arc in a book they cannot see")


class TestTheArcPhrasingIsDeclared:
    def test_arc_synonyms_reach_the_tool(self):
        i = SRC.index('name="composition_motif_bind_edit"')
        block = SRC[i:SRC.index("async def composition_motif_bind_edit", i)]
        for syn in ("attach motif to arc", "bind motif to arc", "set the arc's motif"):
            assert f'"{syn}"' in block, (
                f"{syn!r} is not declared, so the arc request never reaches this tool and the "
                "explicit refusal cannot fire")

    def test_the_chapter_phrasings_are_KEPT(self):
        """Additive. Trading a chapter phrasing for an arc one would move the gap, not close it."""
        i = SRC.index('name="composition_motif_bind_edit"')
        block = SRC[i:SRC.index("async def composition_motif_bind_edit", i)]
        for syn in ("bind motif", "attach pattern to chapter", "set chapter motif"):
            assert f'"{syn}"' in block, syn
