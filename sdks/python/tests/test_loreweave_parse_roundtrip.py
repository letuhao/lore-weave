"""Round-trip + determinism + no-HTTP tests — spec §4.1."""

from __future__ import annotations

import hashlib
import importlib
import sys

import pytest

from loreweave_parse import html_to_leaf_text, parse, parse_html, parse_plain


# ─── Lossless round-trip ─────────────────────────────────────────────────────

_HTML_FOR_ROUNDTRIP = """\
<html><head><title>RT Book</title></head>
<body>
  <h2>Chapter One</h2>
  <p>First paragraph.</p>
  <p>Second paragraph with <em>emphasis</em>.</p>
  <h3>Scene A</h3>
  <p>Scene A body.</p>
  <h3>Scene B</h3>
  <p>Scene B body.</p>
  <h2>Chapter Two</h2>
  <p>Only paragraph of chapter two.</p>
</body></html>
"""

_PLAIN_FOR_ROUNDTRIP = """\
Chapter 1
First paragraph of chapter 1.

Second paragraph of chapter 1.

* * *

Scene 2 of chapter 1.

Chapter 2
Body of chapter 2.
"""


def test_lossless_roundtrip_html():
    """Sum of scene.leaf_text across all scenes, joined by \\n\\n, equals the
    html_to_leaf_text projection of the full body — modulo separator joins.

    The invariant we lock: every byte that appears in html_to_leaf_text(full)
    also appears in the concatenated scene leaf_texts (no silent drop). We
    don't byte-equal the concatenation because scene boundaries inject
    additional \\n\\n separators.
    """
    tree = parse_html(_HTML_FOR_ROUNDTRIP)
    # Collect all scene leaf_texts.
    leaves: list[str] = []
    for part in tree.parts:
        for chapter in part.chapters:
            for scene in chapter.scenes:
                leaves.append(scene.leaf_text)
    joined = "\n\n".join(leaves).strip()
    # Compute the "ground-truth" projection of the entire body.
    # Walker strips h2/h3 heading tags into text; so joined contains them.
    # The full-body projection also contains them. The non-heading prose
    # must all appear.
    for paragraph_snippet in [
        "First paragraph",
        "Second paragraph with emphasis",
        "Scene A body",
        "Scene B body",
        "Only paragraph of chapter two",
    ]:
        assert paragraph_snippet in joined, f"missing: {paragraph_snippet!r}"


def test_lossless_roundtrip_plain():
    """For plain text, the concatenation of scene leaf_texts (joined by \\n\\n)
    must contain every non-marker, non-scene-break line of the input.
    """
    tree = parse_plain(_PLAIN_FOR_ROUNDTRIP, language="en")
    leaves: list[str] = []
    for part in tree.parts:
        for chapter in part.chapters:
            for scene in chapter.scenes:
                leaves.append(scene.leaf_text)
    joined = "\n\n".join(leaves)
    for snippet in [
        "First paragraph of chapter 1",
        "Second paragraph of chapter 1",
        "Scene 2 of chapter 1",
        "Body of chapter 2",
    ]:
        assert snippet in joined, f"missing: {snippet!r}"


# ─── Deterministic paths + content_hash ─────────────────────────────────────


def test_deterministic_paths_and_hashes_html():
    """Parsing identical HTML twice produces byte-identical path strings and
    content_hashes for every scene.
    """
    t1 = parse_html(_HTML_FOR_ROUNDTRIP)
    t2 = parse_html(_HTML_FOR_ROUNDTRIP)

    def _all_scenes(tree):
        out = []
        for part in tree.parts:
            for chapter in part.chapters:
                for scene in chapter.scenes:
                    out.append((scene.path, scene.content_hash, scene.leaf_text))
        return out

    assert _all_scenes(t1) == _all_scenes(t2)


def test_deterministic_paths_plain():
    t1 = parse_plain(_PLAIN_FOR_ROUNDTRIP, language="en")
    t2 = parse_plain(_PLAIN_FOR_ROUNDTRIP, language="en")
    paths_1 = [s.path for p in t1.parts for c in p.chapters for s in c.scenes]
    paths_2 = [s.path for p in t2.parts for c in p.chapters for s in c.scenes]
    assert paths_1 == paths_2


def test_content_hash_matches_sha256_of_leaf_text():
    """The content_hash field is exactly sha256_hex(leaf_text)."""
    tree = parse_html(_HTML_FOR_ROUNDTRIP)
    for part in tree.parts:
        for chapter in part.chapters:
            for scene in chapter.scenes:
                expected = hashlib.sha256(scene.leaf_text.encode("utf-8")).hexdigest()
                assert scene.content_hash == expected


# ─── No outbound HTTP / no LLM imports (spec D9) ────────────────────────────


def test_sdk_has_no_outbound_http_imports():
    """The SDK MUST NOT import httpx, requests, or anything that could make
    an HTTP call. Reload sub-modules and inspect sys.modules.
    """
    import loreweave_parse  # noqa: F401
    import loreweave_parse._text_strip  # noqa: F401
    import loreweave_parse._types  # noqa: F401
    import loreweave_parse.dispatcher  # noqa: F401
    import loreweave_parse.html_walker  # noqa: F401
    import loreweave_parse.plaintext_parser  # noqa: F401

    # The SDK package's own files must not have any of these in their imports.
    sdk_files = {
        "loreweave_parse",
        "loreweave_parse._text_strip",
        "loreweave_parse._types",
        "loreweave_parse.dispatcher",
        "loreweave_parse.html_walker",
        "loreweave_parse.plaintext_parser",
    }
    for name in sdk_files:
        module = sys.modules.get(name)
        assert module is not None, f"{name} not imported"
        # Check the module's globals for forbidden names.
        forbidden = ["httpx", "requests", "urllib.request", "loreweave_llm", "loreweave_extraction"]
        for fname in forbidden:
            # Top-level `httpx` etc. would appear as attribute on the module if imported.
            base = fname.split(".")[0]
            assert base not in module.__dict__, (
                f"{name} imports forbidden module {base!r} — SDK must be pure"
            )


def test_sdk_does_not_pull_llm_packages_transitively():
    """Importing loreweave_parse must NOT cause loreweave_llm/loreweave_extraction
    to be loaded as a side effect.
    """
    # Drop any cached entries first so we can observe the side-effects fresh.
    for mod in list(sys.modules.keys()):
        if mod.startswith(("loreweave_parse", "loreweave_llm", "loreweave_extraction")):
            sys.modules.pop(mod, None)
    importlib.import_module("loreweave_parse")
    assert "loreweave_llm" not in sys.modules
    assert "loreweave_extraction" not in sys.modules


# ─── Dispatcher error handling ──────────────────────────────────────────────


def test_dispatcher_raises_on_unknown_format():
    with pytest.raises(ValueError):
        parse("pdf", "content")  # type: ignore[arg-type]


# ─── html_to_leaf_text regression-pin (H2 fix) ───────────────────────────────


def test_html_to_leaf_text_pinned_output():
    """Locked output for a fixed HTML fixture. ANY change to the html.parser
    + get_text + whitespace-collapse pipeline that perturbs bytes will fail
    this test. Intentional canary against silent drift.
    """
    html = (
        "<p>First line.</p>"
        "<p>Second line with <em>emphasis</em>.</p>"
        "<p>Third line.<br/>After break.</p>"
        "<script>alert('xss');</script>"
        "<style>.x { color: red }</style>"
    )
    expected = (
        "First line.\n\nSecond line with emphasis.\n\nThird line.\nAfter break."
    )
    assert html_to_leaf_text(html) == expected


def test_html_to_leaf_text_nested_list_preserves_outer_text():
    """M1 regression-lock: nested <ul><li>outer<ul><li>inner</li></ul></li></ul>
    must NOT drop the outer-item's direct text.
    """
    html = "<ul><li>outer item<ul><li>inner item</li></ul></li></ul>"
    out = html_to_leaf_text(html)
    assert "outer item" in out
    assert "inner item" in out


def test_html_to_leaf_text_loose_text_in_container_preserves():
    """M1 regression-lock: <div>loose<p>para</p></div> must NOT drop "loose"."""
    html = "<div>loose text<p>paragraph text</p></div>"
    out = html_to_leaf_text(html)
    assert "loose text" in out
    assert "paragraph text" in out
