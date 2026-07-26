"""Cross-language drift canary for the Tiptap doc contract (D-COMP-TIPTAP-SHAPE-DRIFT).

`prose_doc.text_to_tiptap_doc` (Python) must stay byte-identical to book-service's
`plainTextToTiptapJSON` (Go) — a divergence silently breaks the `chapter_blocks`
extraction trigger and the editor's plain-text projection. `test_prose_doc.py`
already pins the PYTHON side. This canary guards the GO side: it reads book-
service's `tiptap.go` from the monorepo and asserts the shape-defining tokens are
still present. If book's serializer is restructured (field rename, split/trim
change, wrapper change), this fails LOUDLY → re-sync `prose_doc.py` before the
drift reaches production. (A full cross-lang lock would run the Go serializer in
CI; this catches the same drift class without a Go build.)
"""

from __future__ import annotations

from pathlib import Path

import pytest

# repo root: tests/unit/<this> → composition-service → services → root
_REPO_ROOT = Path(__file__).resolve().parents[4]
_TIPTAP_GO = _REPO_ROOT / "services" / "book-service" / "internal" / "api" / "tiptap.go"

# The shape contract `prose_doc.text_to_tiptap_doc` mirrors. Each token is a
# distinct invariant; a book-side change to ANY of them must force a prose_doc
# re-sync. Kept as substrings (whitespace-insensitive on the Go gofmt alignment
# is impossible, so we match the semantic core, not the column padding).
_REQUIRED_TOKENS = [
    'strings.ReplaceAll(text, "\\r\\n", "\\n")',  # CRLF → LF normalization
    'strings.Split(text, "\\n\\n")',              # paragraph split on blank line
    'strings.TrimRight(p, "\\n")',                # per-paragraph trailing-NL strip
    '"_text"',                                     # top-level snapshot the trigger reads
    '"paragraph"',                                 # paragraph node type
    '"text"',                                      # inner text node type
    '"doc"',                                       # wrapper type
    # F4a also mirrors the markdown variant's heading handling:
    '`^(#{1,6})\\s+(.*\\S)\\s*$`',                 # atxHeadingRe — leading ATX headings
    '"heading"',                                   # heading node type
    'if level > 3',                                # StarterKit level clamp (1-3)
]


@pytest.mark.skipif(not _TIPTAP_GO.exists(), reason="book-service source not in this checkout")
def test_book_tiptap_go_shape_unchanged():
    src = _TIPTAP_GO.read_text(encoding="utf-8")
    missing = [tok for tok in _REQUIRED_TOKENS if tok not in src]
    assert not missing, (
        f"book-service tiptap.go drifted — missing shape tokens {missing}. "
        f"Re-sync services/composition-service/app/engine/prose_doc.py to match "
        f"plainTextToTiptapJSON, then update this canary."
    )


@pytest.mark.skipif(not _TIPTAP_GO.exists(), reason="book-service source not in this checkout")
def test_empty_paragraph_branch_present():
    # The empty-paragraph branch (a blank paragraph → {_text:""} with NO content
    # node) is a distinct invariant prose_doc mirrors; assert book still has it.
    src = _TIPTAP_GO.read_text(encoding="utf-8")
    assert 'if p == ""' in src, (
        "book-service tiptap.go no longer special-cases the empty paragraph — "
        "re-check prose_doc.text_to_tiptap_doc's empty-paragraph branch."
    )
