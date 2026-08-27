"""D-A-RECOGNISABLE-PLACEHOLDER-UUID-PASSES-THE-FABRICATION-GUARD
   + D-FABRICATION-GUARD-IS-BLIND-TO-A-VALID-LOOKING-UUID.

    THE INVARIANT. A syntactically valid UUID that is RECOGNISABLE as a placeholder without
    knowing any real id is knowably invented, not merely possibly-wrong.

`_invented_supplier_ids` tests SYNTAX, so a model that invents a well-formed UUID walks through
it, `_missing_required_names` sees the argument as PRESENT, and the call is dispatched to a
Tier-A write tool. Measured live on two tools and two arguments:

    plan_bootstrap_apply  proposal_id=77777777-7777-7777-7777-777777777777   (2 of 5 runs)
    plan_bootstrap_apply  proposal_id=78965432-1234-5678-90ab-cdef12345678   (1 of 5)
    (and 66966666-6666-6666-6666-666666666666 on a different tool entirely)

Both rows said the same thing: a shape test is plausible, its PRECISION is unknown, and "that
measurement is the next step, not the fix". This is that measurement, and then the fix.

🔴 THE MEASUREMENT, 2026-08-27, over TWO populations — the second because it is the one this
function actually sees:

                          38,314 real ids       390 GENUINE ids the model passed
    all-digits-identical         2                      0
    sequential run >= 8          0                      0
    --- measured and REJECTED ---
    distinct hex <= 2           20                      0
    UUID version != 7       11,618                      -

`distinct <= 2` is NOT shipped: its 20 are hand-authored sentinels that DO resolve
(00000000-…-00000000000a and siblings), and refusing a value that exists is a false refusal
even when the value is ugly. `version != 7` is refuted outright by 11,618 genuine v4 ids —
exactly as D-FABRICATION-GUARD-IS-BLIND-TO-A-VALID-LOOKING-UUID warned it would be.

THE ONE COST, NAMED: `11111111-1111-1111-1111-111111111111` exists as a seeded
`chat_messages.message_id`. The rule refuses it. That is the entire false-positive surface
across 38,314 ids, and the nil UUID — the other match — was already refused by `_is_nil_uuid`.

RECALL IS PARTIAL AND THAT IS THE PRICE. Of the nine invented UUIDs in recorded tool arguments
these catch seven; `66966666-…` and `76767676-…` have two distinct digits and no long run, and
reaching them needs the rule that also refuses a sentinel. A guard that is right about what it
flags is worth more than one that flags more, because a false refusal deletes an argument the
model supplied correctly.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import (  # noqa: E402
    _DEGENERATE_SEQ_RUN,
    _invented_supplier_ids,
    _is_degenerate_uuid,
    _is_nil_uuid,
)

REPDIGIT = "77777777-7777-7777-7777-777777777777"
SEQUENTIAL = "78965432-1234-5678-90ab-cdef12345678"
REAL = "01a04107-5b4a-789c-8b22-30f17c8abb00"
SENTINEL = "00000000-0000-0000-0000-00000000000a"
TWO_DIGIT = "66966666-6666-6666-6666-666666666666"


def test_the_measured_call_is_caught():
    """THE FALSIFIER, on the ORIGINAL instance: the exact argument from the live run."""
    assert _invented_supplier_ids({"proposal_id": REPDIGIT}, contract=None) == ["proposal_id"]
    assert _invented_supplier_ids({"proposal_id": SEQUENTIAL}, contract=None) == ["proposal_id"]


def test_it_fires_without_a_contract():
    """The value is wrong for EVERY supplier, so it cannot be conditioned on one — the same
    reasoning the nil-UUID arm beside it already carries."""
    for c in (None, {}, {"proposal_id": {"supplier": "plan"}}):
        assert _invented_supplier_ids({"proposal_id": REPDIGIT}, contract=c) == ["proposal_id"]


def test_a_real_id_is_untouched():
    """The existing rule stands: a valid UUID is accepted even if it is WRONG, because whether
    it is the right row is the tool's question."""
    assert not _is_degenerate_uuid(REAL)
    assert _invented_supplier_ids({"proposal_id": REAL}, contract=None) == []


def test_a_RESOLVING_sentinel_is_left_alone():
    """🔴 THE RULE THAT WAS MEASURED AND REJECTED. `distinct <= 2` would catch two more
    fabrications and would also refuse twenty ids that exist in the stores. Refusing a value
    that resolves is a false refusal even when the value is ugly."""
    assert not _is_degenerate_uuid(SENTINEL)
    assert not _is_degenerate_uuid(TWO_DIGIT)
    assert _invented_supplier_ids({"proposal_id": SENTINEL}, contract=None) == []


def test_the_threshold_has_a_measured_margin():
    """Eight is not a taste. The longest sequential run across 38,314 real ids is SIX, so the
    threshold carries a two-nibble margin — and a run of exactly 6 or 7 must NOT fire."""
    assert _DEGENERATE_SEQ_RUN == 8
    assert not _is_degenerate_uuid("019f01e0-f456-789b-8840-8446f03f7b53")  # a real id, run 6
    assert _is_degenerate_uuid("789e4567-89ab-cdef-0123-456789abcdef")


def test_non_uuids_and_junk_are_not_this_functions_business():
    for v in ("", "not-a-uuid", "run_12345_placeholder", None, 7, []):
        assert not _is_degenerate_uuid(v)


def test_the_nil_arm_is_unchanged():
    """It was there first and is still the one that catches the all-zero value."""
    assert _is_nil_uuid("00000000-0000-0000-0000-000000000000")
    assert _invented_supplier_ids(
        {"map_id": "00000000-0000-0000-0000-000000000000"}, contract=None) == ["map_id"]


def test_only_identifier_shaped_names_are_touched():
    """PRECISION on the other axis: the guard reads `*_id` / `*_ref`, and a placeholder-looking
    value in some other field is not its business."""
    assert _invented_supplier_ids({"title": REPDIGIT}, contract=None) == []
    assert _invented_supplier_ids({"proposal_ref": REPDIGIT}, contract=None) == ["proposal_ref"]


@pytest.mark.skipif(subprocess.run(["docker", "ps"], capture_output=True).returncode != 0,
                    reason="needs the local stack to re-derive the precision")
def test_the_precision_holds_against_the_LIVE_stores():
    """🔴 RE-DERIVED, NOT REMEMBERED. The threshold rests on a measurement of the real id
    population; if that population changes the number must be re-measured, not inherited.

    Re-reads every uuid column in every database and asserts the rule fires on nothing except
    the two values this row already names."""
    dbs = ["loreweave_book", "loreweave_composition", "loreweave_knowledge", "loreweave_glossary",
           "loreweave_translation", "loreweave_jobs", "loreweave_chat"]

    def q(db, sql):
        r = subprocess.run(["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave",
                            "-d", db, "-At", "-c", sql], capture_output=True, text=True)
        return r.stdout.strip().splitlines() if r.returncode == 0 else []

    ids = set()
    for db in dbs:
        for tc in q(db, "SELECT table_name||'.'||column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND data_type='uuid' LIMIT 400;"):
            t, _, c = tc.partition(".")
            ids.update(v for v in q(
                db, f'SELECT DISTINCT "{c}"::text FROM public."{t}" '
                    f'WHERE "{c}" IS NOT NULL LIMIT 200;') if v)
    if len(ids) < 5000:
        pytest.skip(f"only {len(ids)} ids readable; not a precision measurement")
    fired = sorted(u for u in ids if _is_degenerate_uuid(u))
    assert fired == ["00000000-0000-0000-0000-000000000000",
                     "11111111-1111-1111-1111-111111111111"], fired


def test_the_fabrications_this_does_NOT_catch_are_recorded():
    """Every fix states what it does not cover, and here the uncovered part is a list."""
    for missed in (TWO_DIGIT, "76767676-7676-7676-7676-767676767676"):
        assert not _is_degenerate_uuid(missed), (
            "this now fires — the recall/precision trade recorded on the row has changed and "
            "must be re-measured rather than quietly widened"
        )
