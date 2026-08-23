"""A NAME dropped from an `*_id` must come back as the query to search with.

🔴 THE RUN THIS PINS. composition_motif_link_edit, K=5, 2026-08-23. The model resolved both
endpoints to names ("Throwaway Loop Alpha Kutomere"), the whitespace arm of
`_invented_supplier_ids` dropped them — correctly, a name is not an id — and the refusal then
told the model the arguments were MISSING. The tool's description already says to search by name
and pass the id, and the model did call `composition_motif_search`: with blank arguments, twice,
because the only string it could have searched for had just been deleted out of its own call.
The turn died there, five times out of five, and it was recorded against the tool for fifteen runs.

CP-5.4 separated "you forgot something" from "I owe you this". This is the third state — the model
DID supply a value and it was the wrong KIND — and it is the only one of the three where the
refusal is already holding the information the model needs.
"""
from app.services.stream_service import _name_like_dropped_ids


def test_a_dropped_name_comes_back_as_the_query_to_search_with():
    msg = _name_like_dropped_ids({
        "from_motif_id": "Throwaway Loop Alpha Kutomere",
        "to_motif_id": "Throwaway Loop Beta Kutomere",
    })
    assert msg, "a dropped name must produce a sentence; silence is what cost fifteen runs"
    # the VALUE, not merely the argument name — searching needs the string
    assert "Throwaway Loop Alpha Kutomere" in msg
    assert "Throwaway Loop Beta Kutomere" in msg
    assert "NAME" in msg
    assert "missing" in msg.lower()   # says explicitly that this is NOT the missing case


def test_a_placeholder_is_never_echoed_back_as_something_to_search_for():
    """D-FJ-11 exists to refuse inventions. Handing one back invites a better-formatted one."""
    assert _name_like_dropped_ids({"run_id": "run_12345_placeholder"}) == ""
    assert _name_like_dropped_ids({"reference_id": "UNKNOWN_ID_PLEASE_PROVIDE"}) == ""
    assert _name_like_dropped_ids({"reference_id": "REPLACE_WITH_ACTUAL_REFERENCE_ID"}) == ""


def test_a_uuid_and_a_single_token_are_not_names():
    assert _name_like_dropped_ids({"motif_id": "019ebb72-27a2-72f3-a42d-d2d0e0ded179"}) == ""
    # one token with no whitespace is a slug or a vendor ref, not a name we can search with
    assert _name_like_dropped_ids({"world_id": "Ashfall"}) == ""


def test_nothing_dropped_says_nothing():
    assert _name_like_dropped_ids({}) == ""
    assert _name_like_dropped_ids(None) == ""
