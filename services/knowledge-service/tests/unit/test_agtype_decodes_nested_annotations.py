"""`decode_agtype` must read a composite value whose INNER members are annotated.

🔴 THE BUG. `GET /v1/knowledge/entities/{id}` returns
`collect({r: r, subj: subj, obj: obj}) AS edges`, and AGE annotates the inner values:

    [{"a": {"id": 1125…, "label": "Event", "properties": {…}}::vertex}]

`_TYPED` is anchored with `$`, so it matched none of those. `json.loads` then failed on the
bare `::vertype` token and `except json.JSONDecodeError: return raw` handed the caller the
STRING it had been given. The caller did `edge["r"]` and got

    TypeError: string indices must be integers, not 'str'

— a 500 on the entity-detail route. Found by a browser e2e (`studio-place-graph-journey`,
STEP 3) whose relation edge never rendered; no unit test touched it, because every other
query returns `RETURN e` or `RETURN collect(e)`, where the annotation IS trailing.

The deeper lesson, which the negative controls below pin: a decoder whose failure path
returns its INPUT converts "I could not read this" into "here is your data". The raw string
is truthy, indexable by integer, and iterable — so it survives a long way before failing
somewhere that names neither the row nor the reason.
"""

from __future__ import annotations

import pytest

from app.db.age_session import AgeVertex, decode_agtype

_VERTEX = '{"id": 1, "label": "Event", "properties": {"name": "Han Li"}}'


def test_a_nested_vertex_annotation_decodes_instead_of_falling_back_to_the_string():
    """The exact shape `collect({r: r, subj: subj, obj: obj})` produces."""
    value = decode_agtype('[{"r": ' + _VERTEX + '::edge, "subj": ' + _VERTEX + '::vertex}]')
    assert isinstance(value, list), f"decoded to {type(value).__name__}, not a list"
    edge = value[0]
    assert isinstance(edge, dict) and not isinstance(edge, str)
    # The caller does exactly this, and it is what raised TypeError.
    assert isinstance(edge["r"], AgeVertex)
    assert isinstance(edge["subj"], AgeVertex)


def test_a_nested_vertex_exposes_its_PROPERTIES_not_the_wrapper():
    """Wrapping matters as much as parsing: an unwrapped dict decodes fine and then reads
    `.get("name")` as None, because the properties live one level down. That is a silently
    empty relation label rather than a crash — the worse of the two failures."""
    value = decode_agtype('[{"subj": ' + _VERTEX + '::vertex}]')
    assert value[0]["subj"].get("name") == "Han Li"


def test_annotations_nested_two_levels_deep_also_decode():
    value = decode_agtype('{"outer": [{"inner": ' + _VERTEX + '::vertex}]}')
    assert value["outer"][0]["inner"].get("name") == "Han Li"


# ── the shapes that already worked, pinned so the fix cannot regress them ─────


def test_a_TRAILING_annotation_still_yields_a_vertex():
    assert isinstance(decode_agtype(_VERTEX + "::vertex"), AgeVertex)


def test_a_bare_list_of_vertices_still_yields_vertices():
    value = decode_agtype("[" + _VERTEX + "::vertex, " + _VERTEX + "::vertex]")
    assert [type(v).__name__ for v in value] == ["AgeVertex", "AgeVertex"]


@pytest.mark.parametrize("raw,expected", [("42", 42), ("null", None), ('"hi"', "hi"),
                                          ("true", True), ("[1, 2]", [1, 2])])
def test_scalars_and_plain_json_are_untouched(raw, expected):
    assert decode_agtype(raw) == expected


def test_none_and_non_strings_pass_through():
    assert decode_agtype(None) is None
    assert decode_agtype(7) == 7


# ── NEGATIVE CONTROLS ────────────────────────────────────────────────────────


def test_a_type_annotation_INSIDE_a_string_literal_is_not_stripped():
    """The reason the stripper is quote-aware. A blind regex sub would edit a property
    VALUE — a title, a summary, a quoted note — and hand back a row that parses cleanly and
    is wrong, which is worse than the crash this fix removes."""
    assert decode_agtype('{"t": "see ::vertex docs"}') == {"t": "see ::vertex docs"}
    assert decode_agtype('{"t": "a::edge b::path"}') == {"t": "a::edge b::path"}


def test_an_escaped_quote_inside_a_string_does_not_end_it():
    """`\\"` closes nothing, so the scanner must stay INSIDE the string across it — otherwise
    it thinks the literal ended, treats the following `::vertex` as syntax, and strips text
    out of a property value.

    (Written with `chr(92)` deliberately: the first attempt emitted TWO backslashes, which
    is an escaped BACKSLASH followed by a real quote — valid JSON that ends the string early
    and made this case fail against a correct decoder. The bug was in the test.)"""
    bs, dq = chr(92), chr(34)
    raw = '{"t": "she said ' + bs + dq + '::vertex' + bs + dq + ' then left"}'
    assert decode_agtype(raw)["t"] == 'she said "::vertex" then left'


def test_genuinely_undecodable_input_still_returns_the_raw_string():
    """The fallback stays — but it must be reached only by input that is REALLY not JSON,
    not by input this decoder simply failed to normalise first."""
    assert decode_agtype("{not json at all") == "{not json at all"
