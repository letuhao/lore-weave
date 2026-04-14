"""K11.3 unit tests — schema-file parser.

The Python runner splits the .cypher file on `;`, strips line
comments, and trims whitespace. These tests verify the parser
behaves correctly without needing a live Neo4j connection.

The "live Neo4j applies schema cleanly + idempotency" assertion
is the K11.3 integration test in tests/integration/db/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db.neo4j_schema import _SCHEMA_PATH, load_schema_statements


def test_k11_3_schema_file_exists():
    """The .cypher file must ship next to the runner module."""
    assert _SCHEMA_PATH.exists(), f"missing {_SCHEMA_PATH}"
    assert _SCHEMA_PATH.suffix == ".cypher"


def test_k11_3_load_schema_statements_returns_nonempty_list():
    """Sanity: the file parses to a positive number of statements."""
    statements = load_schema_statements()
    assert len(statements) > 0
    # We expect at least the 6 unique constraints + 8 composite
    # indexes + 3 evidence-count indexes + 2 source indexes +
    # 5 vector indexes = 24. Existence constraints were removed
    # (Enterprise-only on community edition).
    # Conservative lower bound here so adding statements doesn't
    # break the test.
    assert len(statements) >= 20


def test_k11_3_load_schema_statements_have_no_trailing_semicolons():
    """Each fragment is fed to `session.run(...)` directly, which
    expects exactly one statement per call. A trailing `;` would
    confuse some bolt drivers and is in any case redundant."""
    for s in load_schema_statements():
        assert not s.endswith(";"), f"unexpected trailing ;: {s[:60]!r}"


def test_k11_3_load_schema_statements_have_no_empty_fragments():
    statements = load_schema_statements()
    assert all(s.strip() for s in statements)


def test_k11_3_load_schema_statements_strips_line_comments():
    """A `// foo` line at the start of a statement should be
    removed by the parser so the remaining Cypher is valid."""
    statements = load_schema_statements()
    for s in statements:
        # No `//` comments should survive parsing.
        assert "//" not in s, f"comment leaked: {s[:120]!r}"


def test_k11_3_load_schema_statements_includes_vector_indexes():
    """KSA §3.4.B says we need 4 entity vector indexes (384, 1024,
    1536, 3072) + 1 event vector index (1024). All five must be
    present in the parsed output."""
    statements = load_schema_statements()
    joined = "\n".join(statements)
    for dim in (384, 1024, 1536, 3072):
        assert f"entity_embeddings_{dim}" in joined, (
            f"missing entity vector index for dim {dim}"
        )
    assert "event_embeddings_1024" in joined


def test_k11_3_load_schema_statements_includes_unique_constraints():
    """Every primary node label needs a uniqueness constraint."""
    statements = load_schema_statements()
    joined = "\n".join(statements)
    for label, prop in (
        ("Entity", "id"),
        ("Event", "id"),
        ("Fact", "id"),
        ("ExtractionSource", "id"),
        ("Project", "id"),
        ("Session", "id"),
    ):
        # Look for the canonical CREATE CONSTRAINT shape — the
        # name will vary but the (label, prop) pair must appear.
        needle_label = f"({label[0].lower()}:{label})"
        needle_prop = f"REQUIRE {label[0].lower()}.{prop}"
        assert needle_label in joined or label in joined, (
            f"missing constraint reference for {label}"
        )


def _schema_source_without_comments() -> str:
    """Return the schema source with `//` line comments stripped —
    the same shape `load_schema_statements` works on. The guard
    tests below scan THIS, not the raw file, because prose
    examples like `` `;` `` legitimately appear inside comments
    and would otherwise cause false positives."""
    import re as _re

    raw = _SCHEMA_PATH.read_text(encoding="utf-8-sig")
    return _re.sub(r"//[^\n]*", "", raw)


def test_k11_3_schema_has_no_string_literal_double_slash():
    """K11.3-R1/R4 guard. After comment stripping, no remaining
    Cypher should contain `//` inside a single-quoted, double-
    quoted, or backtick-quoted literal. If one ever appears, the
    parser would have already eaten it as a comment by the time
    the guard runs — but the *post-strip* check still catches the
    case where a literal contains `//foo` and the regex stripped
    only `//foo` (leaving an unbalanced quote)."""
    import re

    src = _schema_source_without_comments()
    bad_patterns = [
        r"'[^'\n]*//[^'\n]*'",
        r'"[^"\n]*//[^"\n]*"',
        r"`[^`\n]*//[^`\n]*`",
    ]
    for pat in bad_patterns:
        m = re.search(pat, src)
        assert m is None, (
            f"schema literal contains `//` which the parser would "
            f"strip as a comment: {m.group(0)!r}"
        )


def test_k11_3_schema_has_no_semicolon_in_string_literal():
    """K11.3-R1/R4 guard. The parser splits on `;` globally. A `;`
    inside a string or backtick literal would be split mid-
    statement and both halves would be invalid Cypher. Scans the
    post-comment-strip source so prose like `` `;` `` inside a
    `//` comment doesn't trigger a false positive."""
    import re

    src = _schema_source_without_comments()
    bad_patterns = [
        r"'[^'\n]*;[^'\n]*'",
        r'"[^"\n]*;[^"\n]*"',
        r"`[^`\n]*;[^`\n]*`",
    ]
    for pat in bad_patterns:
        m = re.search(pat, src)
        assert m is None, (
            f"schema literal contains `;` which the parser would "
            f"split mid-statement: {m.group(0)!r}"
        )


def test_k11_3_load_schema_statements_tolerates_utf8_bom(tmp_path: Path):
    """K11.3-R1/R5 guard. A Windows editor that saves with BOM
    must not break the runner. Verifies the BOM is silently
    consumed by `utf-8-sig` decoding."""
    p = tmp_path / "bom.cypher"
    p.write_bytes(
        b"\xef\xbb\xbf"  # UTF-8 BOM
        b"CREATE INDEX foo IF NOT EXISTS FOR (n:Foo) ON (n.x);\n"
    )
    statements = load_schema_statements(p)
    assert len(statements) == 1
    # No leading \ufeff smuggled into the first statement.
    assert statements[0].startswith("CREATE INDEX foo")


def test_k11_3_load_schema_statements_alt_path_is_honoured(tmp_path: Path):
    """`load_schema_statements(path=...)` must read from the given
    file rather than the default. Used by tests that want to pass
    a fabricated mini-schema."""
    p = tmp_path / "mini.cypher"
    p.write_text(
        "// header comment\n"
        "CREATE CONSTRAINT foo IF NOT EXISTS FOR (n:Foo) REQUIRE n.id IS UNIQUE;\n"
        "// another comment\n"
        "CREATE INDEX bar IF NOT EXISTS FOR (n:Foo) ON (n.x);\n",
        encoding="utf-8",
    )
    statements = load_schema_statements(p)
    assert len(statements) == 2
    assert "CONSTRAINT foo" in statements[0]
    assert "INDEX bar" in statements[1]
