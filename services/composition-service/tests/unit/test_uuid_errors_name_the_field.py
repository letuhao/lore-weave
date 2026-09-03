"""TOOLV2 LOOP #148 — a malformed uuid named no argument and echoed nothing.

Measured across seven composition tools with a deliberately bad id, the answer was identical every
time and came from the standard library:

    Error executing tool composition_arc_get: badly formed hexadecimal UUID string

composition_arc_edit alone accepts seven uuid fields (node_id, book_id, parent_arc_id,
new_parent_arc_id, after_id, structure_node_id, arc_template_id), so a caller was told one of them
was wrong without being told which.

The corpus holds one real occurrence in 1448 tool-call messages, and it is the reason echoing
matters more than naming: composition_arc_suggest received
"...cb-1bc5-7384-9fb4-9fb4-3435368886d0" — a model that had DUPLICATED a uuid segment. Handed its
own string back it can see that; told the string is badly formed it cannot. This adds information
the caller has no other way to obtain, which is what separates it from rewording.
"""

import re
from pathlib import Path

import pytest

from app.mcp.server import _uuid

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_a_valid_uuid_still_parses_unchanged():
    """The control. A helper that always raised would satisfy every other assertion here."""
    assert str(_uuid("019f0d28-1b5e-7b6a-9185-0e2bb58c7090", "arc_template_id")) == (
        "019f0d28-1b5e-7b6a-9185-0e2bb58c7090"
    )


def test_the_refusal_names_the_field_and_echoes_the_value():
    with pytest.raises(ValueError) as exc:
        _uuid("019f64cb-1bc5-7384-9fb4-9fb4-3435368886d0", "node_id")
    msg = str(exc.value)
    assert "node_id" in msg, "the caller cannot fix an argument it has not been named"
    # The echo is the point: the duplicated 9fb4 group is only visible in the caller's own string.
    assert "9fb4-9fb4" in msg
    assert "badly formed hexadecimal" not in msg


def test_none_is_reported_the_same_way_rather_than_as_a_type_error():
    """`UUID(None)` raised TypeError, which reads like a server fault rather than a bad argument."""
    with pytest.raises(ValueError) as exc:
        _uuid(None, "book_id")
    assert "book_id" in str(exc.value)


def test_no_tool_parses_an_argument_uuid_without_naming_it():
    """The helper is worth nothing where a call site skips it, and this is a 204-site sweep —
    exactly the shape where one missed site hides for months.

    The first pass covered only `UUID(args.x)` and the live A/B caught it: composition_arc_edit and
    composition_arc_suggest still leaked the stdlib message, because tools taking plain parameters
    parse `UUID(book_id)` instead. A guard asserting only the first shape was zero would have
    called that sweep complete.
    """
    for shape in (r"\bUUID\(args\.", r"\bUUID\([a-z][a-z0-9_]*_id\)"):
        bare = len(re.findall(shape, BODY))
        assert bare == 0, f"{bare} caller arguments still parse through a bare UUID() call ({shape})"
    named = re.findall(r'_uuid\((?:args\.)?([a-z_]+), "([a-z_]+)"\)', BODY)
    assert len(named) >= 204, f"expected the full sweep, found {len(named)} sites"
    # The declared name must match the field it came from, or the message misdirects.
    mismatched = [(a, b) for a, b in named if a != b]
    assert not mismatched, f"these sites name a different field than they read: {mismatched}"


def test_server_supplied_ids_deliberately_keep_the_raw_parse():
    """Not every UUID() call is a caller argument, and the ones that are not must stay raw.

    An owner_user_id read back from the database, a book_id decoded from a confirm token this
    service signed, or tc.user_id from the request envelope are all SERVER-supplied. If one of
    those is malformed the caller did nothing wrong and there is no argument to name — dressing it
    up as "book_id must be a UUID" would send the caller hunting for a mistake it did not make.
    """
    assert "UUID(str(owner_user_id" in BODY, (
        "a database-supplied owner id was rewritten as if the caller had sent it"
    )
    assert 'UUID(str(payload["book_id"' in BODY, (
        "a confirm-token payload is this service's own signed value, not a caller argument"
    )
