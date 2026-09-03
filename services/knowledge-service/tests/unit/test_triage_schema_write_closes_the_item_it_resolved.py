"""TOOLV2 LOOP #260 — the agent path changed the ontology and left the queue entry pending.

kg_triage_schema_write's refusals are precise: an out-of-enum action names all four valid values
and the one sent, and the no-adopted-schema precondition names the tools that clear it.

The happy path needed a real item. Only `proposed_edge` items exist instance-wide (22 pending, 7
resolved) — the four types this tool serves are parked by extraction, and none had ever been
produced here — so one `unknown_edge_type` row was seeded and then driven entirely through the
real tools. Measured:

    kg_triage_list      -> the item, suggested_actions ["map", "add_to_schema", "dismiss"]
    kg_triage_schema_write(add_to_schema) -> confirm_token
    card                -> "Schema write: add_to_schema 'venerates_260'", 5 → 6
    confirm             -> {"applied": true, "schema_version": 6, "stamped": 0}
    SSOT kg_edge_types  -> venerates_260 | Venerates          ← the write landed
    SSOT kg_triage_items-> status "pending", resolution null  ← the item never closed

Two callers reach this effect and arrive in DIFFERENT states. The REST resolve route applies the
mutation itself and marks the batch resolved in the same request, leaving schema_version=None for
E3 to backfill — which is all this block did. The MCP tool only MINTS a token and never touches
the items, so at confirm they are still pending, and `stamp_schema_version` filters
`status = 'resolved'` and matched nothing.

The effect's own comment records the assumption it was written under: "the resolve route set it to
None". On the agent path there is no prior resolve. So an agent could add the edge type, see the
same triage entry on its next list, and add it again — the second attempt failing on the
duplicate-code conflict, with the queue still dirty.

`stamped: 0` was the only tell, and it cannot distinguish "the queue was untouched" from "the
queue was already tidy". The response now reports `resolved` alongside it.

The ordering matters: resolve-then-stamp. `resolve_signature` only touches PENDING rows, so it is
a no-op for the REST path, and stamping after it means the newly-resolved batch gets the version
too.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "ontology" / "triage_schema_write_effect.py"


def _body() -> str:
    return SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_effect_resolves_still_pending_items():
    body = _body()
    assert "await triage.resolve_signature(" in body, (
        "the confirm effect no longer closes pending items; the MCP path mutates the ontology "
        "and leaves the triage entry that prompted it pending forever"
    )
    assert 'new_status="resolved"' in body


def test_it_resolves_before_it_stamps():
    """stamp_schema_version filters status='resolved'. Stamping first would leave the batch this
    confirm just resolved without a version — the exact gap in the other direction."""
    body = _body()
    assert body.index("resolve_signature(") < body.index("stamp_schema_version("), (
        "the stamp runs before the resolve; the newly-closed items would miss their version"
    )


def test_the_stamp_is_kept_not_replaced():
    """The REST path's rows are already resolved and carry schema_version=None. Replacing the
    stamp with the resolve would leave those permanently unversioned."""
    body = _body()
    assert "await triage.stamp_schema_version(" in body


def test_both_writes_stay_best_effort():
    """Bookkeeping must never unwind an applied schema change — the mutation is already
    committed by the time either runs."""
    body = _body()
    after = body[body.index("resolved = 0"):]
    assert after.count("except Exception:") == 2, (
        "both the resolve and the stamp must stay wrapped; an exception here would surface as a "
        "failed confirm over a schema change that DID apply"
    )


def test_the_response_distinguishes_untouched_from_already_tidy():
    body = _body()
    assert '"resolved": resolved,' in body, (
        "`stamped: 0` alone cannot tell a caller whether the queue was left dirty or was "
        "already clean — which is why this defect was invisible in the response"
    )


def test_the_stale_assumption_is_no_longer_stated_as_fact():
    """The old comment asserted the items were '(already-resolved)' and that 'the resolve route
    set it to None'. That is true of one caller and was the reason the other was never handled."""
    body = _body()
    assert "(already-resolved) triage items" not in body
    assert "Two callers reach this effect" in body, (
        "record that the two entry points arrive in different states, or the next reader "
        "re-derives the same wrong assumption"
    )
