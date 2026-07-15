"""D4 (Phase G · G0) — the both-sides book-state contract, chat-service half.

The rail governance joins THREE places by a bare string: a step's `done_when` key (seeded in
agent-registry), the chat-service `BOOK_STATE_KEYS` grammar, and the `/internal` probe route each
key reads. A rename in any one silently disables the gate — the step reads satisfied, or falls
back to the call log, and nothing says a word (`silent-success-is-a-bug`). So both sides check ONE
SoT: `contracts/book-state-keys.contract.json`. THIS test is the chat-service half; the
agent-registry half is migrate_lint_test.go::TestSchemaSQL_SeededDoneWhenMatchesTheClosedGrammar.

It reds on: a key added to `BOOK_STATE_KEYS` but not the contract (or vice-versa), a key with no
`_STATE_LABELS` entry, a key with no `BookState` field, or a probe route the contract names that the
probe module does not actually request.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from app.services import book_state_probe
from app.services.rail_progress import _STATE_LABELS, BOOK_STATE_KEYS, BookState


def _contract() -> dict:
    # Walk up from this test to the repo root (the dir that holds `contracts/`).
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "contracts" / "book-state-keys.contract.json"
        if cand.exists():
            return json.loads(cand.read_text(encoding="utf-8"))
    raise AssertionError("contracts/book-state-keys.contract.json not found walking up from the test")


def test_book_state_keys_match_the_contract_exactly():
    contract_keys = set(_contract()["keys"])
    assert set(BOOK_STATE_KEYS) == contract_keys, (
        "BOOK_STATE_KEYS drifted from contracts/book-state-keys.contract.json — "
        f"only in code: {set(BOOK_STATE_KEYS) - contract_keys}; "
        f"only in contract: {contract_keys - set(BOOK_STATE_KEYS)}"
    )


def test_every_key_has_a_render_label_matching_the_contract():
    keys = _contract()["keys"]
    for key in BOOK_STATE_KEYS:
        assert key in _STATE_LABELS, f"{key} has no _STATE_LABELS entry — it would render unlabelled"
        # The label is part of the contract: the snapshot the model reads must match the SoT, so a
        # reworded label can't silently drift from what the contract (and any doc) advertises.
        assert _STATE_LABELS[key] == keys[key]["label"], (
            f"label for {key!r} drifted: code={_STATE_LABELS[key]!r} contract={keys[key]['label']!r}"
        )


def test_every_key_is_a_bookstate_field():
    fields = {f.name for f in dataclasses.fields(BookState)}
    for key in BOOK_STATE_KEYS:
        assert key in fields, f"{key} is in BOOK_STATE_KEYS but not a BookState field — always UNKNOWN"


def test_every_contract_probe_route_is_actually_requested_by_the_probe():
    """A route the contract names for a key MUST appear literally in the probe module — otherwise
    the contract claims a source the probe never reads (a stored-but-unread contract)."""
    src = Path(book_state_probe.__file__).read_text(encoding="utf-8")
    for key, meta in _contract()["keys"].items():
        route = meta["probe_route"]
        # The probe builds the path as an f-string with {book_id}; the literal text in source is
        # the prefix and suffix around that placeholder. Assert BOTH appear (a rename of either
        # end reds).
        prefix, _, suffix = route.partition("{book_id}")
        assert prefix in src and suffix in src, (
            f"contract key {key!r} names probe route {route!r}, but chat-service's book_state_probe "
            f"never requests it (prefix {prefix!r} / suffix {suffix!r}) — renamed on one side only"
        )
