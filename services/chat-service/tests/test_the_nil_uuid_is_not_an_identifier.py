"""D-NIL-UUID-MINTS-A-CARD — a confirm card must represent a call that could succeed.

MEASURED LIVE 2026-08-14, batch 7, K=3. Asked *"Draw an area on my Ashfall map covering the whole
eastern half and call it The Trench"*, the model called `world_map_add_region` on 3 of 3 runs with:

    {"name": "The Trench",
     "map_id": "00000000-0000-0000-0000-000000000000",
     "polygon": [[0.5, 0], [1, 0], [1, 1], [0.5, 1]]}

The polygon is RIGHT — that is the eastern half. The map was never looked up. And because the nil
UUID *parses*, `_invented_supplier_ids` accepted it and a Tier-A CONFIRM CARD was minted, putting
in front of the author a write whose target does not exist. Verified at the tool boundary: the
same arguments answer `map not found`.

THE INVARIANT: the all-zero UUID is not an identifier. It is reserved, no table here holds it, so
an `*_id` argument carrying it is knowably invented rather than merely possibly-wrong.

That distinction is why this belongs INSIDE `_invented_supplier_ids` rather than beside it. Its
existing rule is deliberate — "a valid UUID is accepted even if it is wrong, because whether it is
the right row is the tool's question, not ours" — and the nil UUID is the single value that rule
should never have covered.

The remedy reuses the path already there: the argument is dropped and reported MISSING, which
gives the model the one sentence that sends it to look the id up.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import (  # noqa: E402
    _invented_supplier_ids,
    _is_nil_uuid,
)

NIL = "00000000-0000-0000-0000-000000000000"
REAL = "01a02028-9cd6-7692-acd5-25191d801747"


def test_the_measured_call_is_caught():
    """THE FALSIFIER. These are the exact arguments from the live run."""
    assert _invented_supplier_ids(
        {"name": "The Trench", "map_id": NIL, "polygon": [[0.5, 0], [1, 0], [1, 1], [0.5, 1]]},
        contract=None,
    ) == ["map_id"]


def test_it_fires_without_a_contract():
    """The map tools declare no supplier contract, so a contract-gated guard would never have
    run — and that is exactly the case that was measured. The value is wrong for EVERY supplier,
    so it cannot be conditioned on one."""
    assert _invented_supplier_ids({"map_id": NIL}, contract=None) == ["map_id"]
    assert _invented_supplier_ids({"map_id": NIL}, contract={}) == ["map_id"]


def test_a_real_id_is_untouched():
    """The existing rule stands: a valid UUID is accepted even if it is wrong, because whether it
    is the RIGHT row is the tool's question. Only the nil value is knowably not a row."""
    assert _invented_supplier_ids({"map_id": REAL}, contract=None) == []


def test_non_id_arguments_are_never_touched():
    """Scoped to the `*_id` convention. A polygon of zeros is a legitimate coordinate, and a
    guard that reached into content would refuse real work."""
    assert _invented_supplier_ids(
        {"polygon": [[0, 0], [0, 0]], "name": NIL}, contract=None) == []


class TestEverySpellingOfNil:
    """Compared through UUID() rather than by string, so the equivalent spellings cannot slip
    past a literal match — a guard that catches one spelling teaches the model to use another."""

    def test_hyphenated(self):
        assert _is_nil_uuid(NIL) is True

    def test_braced_and_urn_and_bare(self):
        assert _is_nil_uuid("{00000000-0000-0000-0000-000000000000}") is True
        assert _is_nil_uuid("urn:uuid:00000000-0000-0000-0000-000000000000") is True
        assert _is_nil_uuid("00000000000000000000000000000000") is True

    def test_a_real_uuid_is_not_nil(self):
        assert _is_nil_uuid(REAL) is False

    def test_rubbish_is_not_nil_and_does_not_raise(self):
        """A non-UUID is the ORIGINAL guard's business (it reports it as invented). This arm must
        neither claim it nor blow up on it."""
        assert _is_nil_uuid("run_12345_placeholder") is False
        assert _is_nil_uuid("") is False
        assert _is_nil_uuid(None) is False  # type: ignore[arg-type]


def test_the_original_non_uuid_arm_still_works():
    """The measured 2026-08-12 case this function was built for — a `plan`-supplied id filled in
    with a non-UUID placeholder — must be unaffected."""
    # Shape taken from `declared_supplier`, not invented: it reads contract["argument_supplier"],
    # a flat {param: "declaration"} map. My first version guessed a nested {"arguments": {...}}
    # and the test failed for the fixture rather than for the code.
    contract = {"argument_supplier": {"run_id": "plan — emitted by plan_propose_spec"}}
    assert _invented_supplier_ids({"run_id": "run_12345_placeholder"}, contract) == ["run_id"]
