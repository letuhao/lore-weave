"""§10.2 — the per-engine timestamp token.

The point of this indirection is that the two engines get DIFFERENT text. A renderer that
happened to emit the same string for both would be a no-op wearing a seam's clothes, and the
`{NOW}` templates would read as migrated while still baking one engine's function name in.
"""

from __future__ import annotations

import re

import pytest

#: A Cypher `//` comment — the engine-literal scan must not read prose as code.
_CYPHER_COMMENT = re.compile(r"//[^" + chr(92) + "n]*")

from app.db.cypher_dialect import NOW_BY_ENGINE, render

_TEMPLATE = "MATCH (f:Fact) SET f.updated_at = {NOW} RETURN f"


def test_the_two_engines_render_DIFFERENTLY():
    """The non-vacuity check, and the reason this module exists at all."""
    neo, age = render(_TEMPLATE, "neo4j"), render(_TEMPLATE, "age")
    assert neo != age, (
        "both engines rendered the same text — the token is not doing anything, and every "
        "`{NOW}` template is still one engine's dialect with extra steps"
    )
    assert "datetime()" in neo and "{NOW}" not in neo
    assert "timestamp()" in age and "{NOW}" not in age


def test_datetime_and_timestamp_are_NOT_interchangeable_and_the_map_says_so():
    """T63 measured why this is a token and not a rename: on Neo4j `datetime()` yields a
    ZONED DATETIME and `timestamp()` an INTEGER, and a mixed-type `ORDER BY` sorts by TYPE
    rather than raising. The map must therefore never give two engines the same spelling by
    accident — that would put both types in one property across a fleet."""
    assert len(set(NOW_BY_ENGINE.values())) == len(NOW_BY_ENGINE), (
        f"two engines share a timestamp spelling: {NOW_BY_ENGINE} — if that is deliberate, "
        f"it needs a note in §10.2 saying the stored types are known to match"
    )


def test_a_template_with_no_token_is_returned_UNCHANGED():
    """Most queries carry no timestamp. Rendering must not disturb them, or every untouched
    query would need re-reviewing for what the renderer did to it."""
    plain = "MATCH (e:Entity {id: $id}) RETURN e"
    assert render(plain, "neo4j") == plain
    assert render(plain, "age") == plain


def test_EVERY_occurrence_is_replaced_not_just_the_first():
    """`MAINTAIN_*_CHAIN` sets one timestamp, but `merge_event` sets `created_at` AND
    `updated_at`. A single-shot replace would leave the second one as literal `{NOW}` — which
    Neo4j reads as a map projection and fails on far from here."""
    two = "SET a = {NOW}, b = {NOW}"
    assert render(two, "neo4j") == "SET a = datetime(), b = datetime()"


def test_an_unknown_engine_RAISES_rather_than_defaulting_to_neo4j():
    """Rule 9. A silent default is how a third engine would inherit Neo4j's function name and
    fail at the database with a message about a missing function, three layers from the cause."""
    with pytest.raises(ValueError, match="unknown engine"):
        render(_TEMPLATE, "memgraph")  # type: ignore[arg-type]


def test_NO_repo_call_site_NAMES_an_engine():
    """The rule this replaces was the exact inverse, and it was enforcing the defect.

    ⚠️ Until T83 this file asserted that every `{NOW}` template had a `render(NAME` somewhere —
    i.e. that each call site chose the engine itself. The dialect ratchet duly reached zero
    while **51 call sites across 11 modules said `render(TEMPLATE, "neo4j")`**, and running a
    real repo function against AGE failed on `function datetime does not exist`. The templates
    were portable; the RENDERING was pinned, and this test was holding it there.

    The engine now comes from the SESSION, in `run_read`/`run_write`/`run_read_any_owner`. A
    literal engine name anywhere in the repo layer puts it back, so that is what is forbidden.

    One site is exempt and named: `maintenance.invalidate_stale_quarantined_facts` bypasses the
    helpers (its `user_id` is legitimately `None`), so it renders for itself — using
    `engine_of(session)`, not a literal, which is why it passes this check unaided.
    """
    import pathlib

    from app.db.neo4j_repos import facts

    root = pathlib.Path(facts.__file__).resolve().parent
    offenders = []
    for path in sorted(root.glob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = _CYPHER_COMMENT.sub("", line.split("#", 1)[0])
            for engine in ('"neo4j"', "'neo4j'", '"age"', "'age'"):
                if engine in code:
                    offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "the repo layer names an engine in a string literal. The engine belongs to the "
        "session — `run_read`/`run_write` render with `engine_of(session)` — and a literal "
        "here pins the layer to one engine while the dialect ratchet still reads zero:\n  "
        + ("\n  ".join(offenders))
    )


def test_the_engine_LITERAL_scan_can_see_one():
    """Non-vacuity, on a case it was not derived from: the scan must ignore a mention in a
    comment (where this file's own prose lives) and catch one in code."""
    assert '"neo4j"' in _CYPHER_COMMENT.sub("", 'x = render(Q, "neo4j")')
    assert '"neo4j"' not in _CYPHER_COMMENT.sub("", '// render(Q, "neo4j") is what T83 removed')
