"""F10 — the author's declared cast must be in the premise the cast pass reads.

Measured on the pass-rail journey: the spec held Diep Van Vu, Bach Su and To Diep, compile turned
them into `glossary_seeds`, and pass 2 received a premise with no names in it. The model replied
"the premise provided does not contain any character names", the cast came back empty, and the PF-7
seed gate refused the checkpoint — the product behaving correctly on an input it should never have
been given.
"""

from __future__ import annotations

from app.engine.plan_forge.compile import compile_artifacts


def _spec(characters):
    return {
        "arcs": [{"id": "arc_1", "title": "Arc I — The Discarded Miss", "theme": "awakening"}],
        "events": [],
        "layers": {"characters": characters},
        "charter": {},
        "meta": {},
    }


def test_the_declared_cast_is_in_the_premise():
    pkg = compile_artifacts(_spec([
        {"name": "Diep Van Vu", "role": "protagonist, ", "traits": []},
        {"name": "Bach Su", "role": "mentor", "traits": []},
    ]), "arc_1")["planning_package"]
    assert "Cast: Diep Van Vu (protagonist); Bach Su (mentor)" in pkg["premise"]


def test_the_cast_line_comes_before_the_arc():
    pkg = compile_artifacts(_spec([{"name": "Bach Su", "role": "mentor", "traits": []}]), "arc_1")["planning_package"]
    assert pkg["premise"].index("Cast:") < pkg["premise"].index("Arc:")


def test_no_cast_means_no_empty_cast_line():
    """An empty `Cast:` would read as "this book has no characters" — worse than saying nothing."""
    pkg = compile_artifacts(_spec([]), "arc_1")["planning_package"]
    assert "Cast:" not in pkg["premise"]


def test_a_nameless_row_is_skipped_not_rendered():
    pkg = compile_artifacts(_spec([{"name": "", "role": "ghost", "traits": []},
                                   {"name": "To Diep", "role": "", "traits": []}]), "arc_1")["planning_package"]
    cast_lines = [ln for ln in pkg["premise"].splitlines() if ln.startswith("Cast:")]
    assert cast_lines == ["Cast: To Diep"]
    assert "ghost" not in pkg["premise"]
