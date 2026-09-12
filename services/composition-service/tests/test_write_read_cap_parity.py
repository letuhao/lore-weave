"""T11 — a field capped on the way OUT must be capped on the way IN.

WHY THIS EXISTS, and it is not hypothetical. Issue #224: ``StructureNode.goal``/``OutlineNode.goal``
were capped at 2000 on the Pydantic RESPONSE model while every write path declared a bare ``str``.
Postgres has no constraint either (plain TEXT), so an over-long write always SUCCEEDED and then
poisoned every later read of that node — and because the arcs-list endpoint validates all of a
book's arc nodes in one response, one bad arc returned a bare 500 for the entire book's Plan Hub.
A 2026-09-06 human-sim run hit it by typing a perfectly ordinary ~2800-character chapter plan into
a field labelled "Goal (reaches the prompt)".

That was point-fixed. The SHAPE was not: #224's own follow-up recorded that ``title``/``summary``
carry the identical unguarded shape, "just not yet hit by real content".

A one-time sweep would not have helped. It is ``default-uncovered`` for every field added
tomorrow — NV-3, "the scope never reaches it". So this is a mechanical parity check instead: it
derives BOTH sides from the source and fails on any capped response field whose write schema
leaves it unbounded.

MCP tool-arg schemas are covered by their own drift tests (IN-8's 4-source discipline); this
guards the REST pair, which is what #224 actually broke.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[1] / "app"

# Response-model aliases and their caps, read from the source rather than hardcoded, so renaming
# or re-tuning one cannot leave this test asserting a number nobody uses any more.
_MODELS = _APP / "db" / "models.py"

# The write schemas whose fields must not out-run their response caps.
_WRITE_SCHEMAS = [
    _APP / "routers" / "outline.py",
    _APP / "routers" / "arc.py",
]

# Fields that are deliberately NOT mirrored, each with the reason it is safe. Anything absent from
# here and unbounded is a finding — that asymmetry is the point.
_EXEMPT: dict[str, str] = {
    "rank": "a fractional-index token generated server-side, never author prose",
    "cursor": "an opaque pagination token, not stored on the node",
    "next_cursor": "an opaque pagination token, not stored on the node",
    "q": "a search query, never persisted",
    "if_match": "an ETag/version token, not stored",
    "label": "scene-link label; short by construction and not on a capped response model",
    "beat_role": "a closed-set-ish token validated elsewhere, not free prose",
    "story_time": "a short time expression, not on a capped response model",
}


def _capped_response_fields() -> dict[str, int]:
    """{field_name: max_length} for every field a response model caps."""
    src = _MODELS.read_text(encoding="utf-8")
    aliases = {
        name: int(cap)
        for name, cap in re.findall(
            r"^(_\w+)\s*=\s*Annotated\[str,\s*StringConstraints\(max_length=(\d+)\)\]", src, re.M
        )
    }
    assert aliases, "no capped aliases found — did models.py change shape?"
    out: dict[str, int] = {}
    for field, alias in re.findall(r"^\s{4}(\w+):\s*(_\w+)\b", src, re.M):
        if alias in aliases:
            # Keep the LARGEST cap when a name appears on several models: the write side only has
            # to be no looser than the loosest reader to stay safe.
            out[field] = max(out.get(field, 0), aliases[alias])
    return out


def _write_fields(path: Path) -> list[tuple[str, str, str]]:
    """(class_name, field_name, whole declaration) for Create/Patch request models.

    The WHOLE declaration, deliberately. A cap can live in the annotation (`_NodeTitle`) or in the
    default (`= Field(max_length=500)`), and an earlier version of this check read only the
    annotation — which reported `PartCreate.title` as a gap when it was already bounded. A parity
    check with false positives is one people learn to ignore, which is worse than not having it.
    """
    src = path.read_text(encoding="utf-8")
    found: list[tuple[str, str, str]] = []
    for cls_name, body in re.findall(
        r"^class (\w*(?:Create|Patch))\(BaseModel\):\n(.*?)(?=^class |\Z)", src, re.M | re.S
    ):
        for line in body.splitlines():
            m = re.match(r"^\s{4}(\w+):\s*(.+)$", line)
            if m:
                found.append((cls_name, m.group(1), m.group(2).strip()))
    return found


def _is_bounded(declaration: str) -> bool:
    """A string field is bounded when its annotation OR its default carries a length cap."""
    if "str" not in declaration:
        return True  # not a string field at all
    return bool(re.search(r"_[A-Z]\w+|StringConstraints|max_length", declaration))


@pytest.mark.parametrize("path", _WRITE_SCHEMAS + [_MODELS], ids=lambda p: p.name)
def test_the_files_this_check_reads_are_valid_python(path: Path):
    """A source-TEXT check happily passes on a file that cannot be imported.

    This is not hypothetical: while adding the caps below I wrote literal backslash-escapes into
    `outline.py` (a raw-string replacement gone wrong). The parity assertions stayed green because
    they only ever read the text — the module was syntactically broken and this file said nothing.
    A check that cannot notice its own subject is unparseable is reporting coverage it lacks.
    """
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@pytest.mark.parametrize("path", _WRITE_SCHEMAS, ids=lambda p: p.name)
def test_every_capped_response_field_is_bounded_on_write(path: Path):
    capped = _capped_response_fields()
    gaps: list[str] = []
    for cls_name, field, annotation in _write_fields(path):
        if field in _EXEMPT or field not in capped:
            continue
        if not _is_bounded(annotation):
            gaps.append(
                f"{path.name}::{cls_name}.{field} is `{annotation}` (unbounded) but the response "
                f"model caps `{field}` at {capped[field]} — an over-long write will succeed and "
                f"then 500 every later read of that row (issue #224's shape)"
            )
    assert not gaps, "write/read cap parity broken:\n  " + "\n  ".join(gaps)


def test_the_check_can_actually_see_a_gap():
    """NV-2 — the subject must be able to vary.

    A parity check that never finds anything is indistinguishable from one that cannot look. Feed
    it a known-bad annotation and confirm it is judged unbounded, and a known-good one bounded.
    """
    assert not _is_bounded('str = ""'), "an unbounded str was judged bounded — the check is blind"
    assert not _is_bounded("str | None = None"), "an optional unbounded str was judged bounded"
    assert _is_bounded('_NodeGoal = ""'), "an aliased capped field was judged unbounded"
    assert _is_bounded("Annotated[str, StringConstraints(max_length=20000)]")
    # The OTHER way a cap is expressed in this codebase — missing it produced a false positive.
    assert _is_bounded('str = Field(default="", max_length=500)'), "a Field() cap was not seen"
    assert _is_bounded("UUID | None = None"), "a non-string field should never be reported"


def test_known_capped_fields_are_actually_discovered():
    """NV-3 — the scope must reach the thing. If the models regex silently matched nothing, every
    parity assertion above would pass vacuously."""
    capped = _capped_response_fields()
    for expected in ("goal", "synopsis", "summary"):
        assert expected in capped, f"`{expected}` is capped in models.py but the scan missed it"
        assert capped[expected] > 0
