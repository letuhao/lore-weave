"""§10.2 — the per-engine timestamp token.

The point of this indirection is that the two engines get DIFFERENT text. A renderer that
happened to emit the same string for both would be a no-op wearing a seam's clothes, and the
`{NOW}` templates would read as migrated while still baking one engine's function name in.
"""

from __future__ import annotations

import pytest

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


def test_the_repo_layer_has_no_leftover_token_in_an_UNRENDERED_query():
    """A `{NOW}` that reaches the driver is a syntax error at runtime, not at import.

    So every template carrying the token must be rendered by its caller. This checks the
    inverse of the ratchet in `port-adoption-gate`: that one counts `datetime()` still present,
    this one catches a template that lost its `datetime()` and gained a token nobody renders.

    ⚠️ Scanned PACKAGE-wide, not per module — the first cut checked the defining module and
    failed on `MAINTAIN_FACT_CHAIN_CYPHER`, which `temporal` defines and `facts` renders. A
    template and its renderer do not have to share a file, and requiring it would have forced
    the wrong refactor to satisfy the test.
    """
    import pathlib

    from app.db.neo4j_repos import facts, relations, temporal

    root = pathlib.Path(facts.__file__).resolve().parents[2]
    corpus = chr(10).join(
        p.read_text(encoding="utf-8", errors="replace") for p in root.rglob("*.py")
    )
    for mod in (facts, relations, temporal):
        for name in dir(mod):
            if not name.endswith("CYPHER"):
                continue
            template = getattr(mod, name)
            if not isinstance(template, str) or "{NOW}" not in template:
                continue
            assert f"render({name}" in corpus, (
                f"{mod.__name__}.{name} carries a `{{NOW}}` token but NOTHING under app/ "
                f"renders it — an unrendered token reaches the driver as a map projection "
                f"and fails at query time, not at import"
            )
